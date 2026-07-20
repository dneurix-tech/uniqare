import json
from collections import defaultdict
from typing import Annotated, Optional

import cloudinary.uploader
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile as FastAPIUploadFile,
)
from pydantic import WithJsonSchema
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.image_security import validated_image_stream
from app.models import (
    BundleItem,
    OrderItem,
    Product,
    ProductImage,
)
from app.schemas import BundleResponse
from app.security import require_admin


router = APIRouter(
    prefix="/bundles",
    tags=["Bundles"],
)

MAX_BUNDLE_IMAGES = 8

# FastAPI 0.129.1+ may generate contentMediaType for UploadFile.
# Swagger UI currently expects format=binary to render a file picker.
SwaggerUploadFile = Annotated[
    FastAPIUploadFile,
    WithJsonSchema(
        {
            "type": "string",
            "format": "binary",
        }
    ),
]


def parse_optional_old_price(
    old_price: Optional[str],
) -> Optional[float]:
    if old_price is None:
        return None

    cleaned_value = old_price.strip()

    if cleaned_value == "":
        return None

    try:
        parsed_value = float(cleaned_value)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=400,
            detail="Old price must be a valid number",
        )

    if parsed_value <= 0:
        raise HTTPException(
            status_code=400,
            detail="Old price must be greater than 0",
        )

    return parsed_value


def validate_prices(
    price: float,
    old_price: Optional[float],
) -> None:
    if price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Bundle price must be greater than 0",
        )

    if (
        old_price is not None
        and old_price <= price
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Old price must be greater than "
                "the bundle price"
            ),
        )


def parse_bundle_items(
    items_json: str,
) -> dict[int, int]:
    try:
        raw_items = json.loads(items_json)
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=400,
            detail="Invalid bundle products data",
        )

    if not isinstance(raw_items, list):
        raise HTTPException(
            status_code=400,
            detail="Bundle products must be a list",
        )

    merged_items: dict[int, int] = defaultdict(int)

    for item in raw_items:
        if not isinstance(item, dict):
            raise HTTPException(
                status_code=400,
                detail="Invalid bundle product item",
            )

        try:
            product_id = int(item.get("product_id"))
            quantity = int(item.get("quantity", 1))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="Invalid bundle product or quantity",
            )

        if product_id <= 0:
            raise HTTPException(
                status_code=400,
                detail="Invalid product ID",
            )

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Bundle quantity must be greater than 0",
            )

        merged_items[product_id] += quantity

    if len(merged_items) < 2:
        raise HTTPException(
            status_code=400,
            detail=(
                "A bundle must contain at least "
                "two different products"
            ),
        )

    return dict(merged_items)


def get_regular_products(
    db: Session,
    quantities: dict[int, int],
) -> dict[int, Product]:
    product_ids = list(quantities)

    products = (
        db.query(Product)
        .filter(
            Product.id.in_(product_ids),
            Product.is_bundle.is_(False),
        )
        .all()
    )

    products_by_id = {
        product.id: product
        for product in products
    }

    missing_ids = (
        set(product_ids)
        - set(products_by_id)
    )

    if missing_ids:
        missing_id = sorted(missing_ids)[0]

        raise HTTPException(
            status_code=404,
            detail=(
                f"Regular product #{missing_id} "
                "was not found"
            ),
        )

    return products_by_id


def calculate_bundle_stock(
    bundle: Product,
) -> int:
    """
    العدد المتاح هو الأقل بين:

    1. عدد العروض المتبقية الذي حدده الأدمن.
    2. عدد العروض التي يمكن تكوينها من مخزون المنتجات.
    """

    manual_bundle_stock = max(
        0,
        int(bundle.stock or 0),
    )

    if manual_bundle_stock <= 0:
        return 0

    if not bundle.bundle_items:
        return 0

    products_capacity = []

    for item in bundle.bundle_items:
        child_product = item.child_product

        if (
            not child_product
            or child_product.is_active is False
            or int(item.quantity or 0) <= 0
        ):
            return 0

        products_capacity.append(
            int(child_product.stock or 0)
            // int(item.quantity)
        )

    if not products_capacity:
        return 0

    return min(
        manual_bundle_stock,
        min(products_capacity),
    )


def serialize_bundle(
    bundle: Product,
) -> dict:
    available_stock = calculate_bundle_stock(bundle)

    images = [
        {
            "id": image.id,
            "image_url": image.image_url,
            "sort_order": image.sort_order,
        }
        for image in sorted(
            bundle.images,
            key=lambda item: item.sort_order,
        )
    ]

    bundle_items = [
        {
            "id": item.id,
            "product_id": item.child_product_id,
            "product_name": (
                item.child_product.name
                if item.child_product
                else f"Product #{item.child_product_id}"
            ),
            "product_image": (
                item.child_product.image_url
                if item.child_product
                else None
            ),
            "quantity": item.quantity,
            "product_stock": (
                int(item.child_product.stock or 0)
                if item.child_product
                else 0
            ),
        }
        for item in bundle.bundle_items
    ]

    return {
        "id": bundle.id,
        "name": bundle.name,
        "short_description": bundle.short_description,
        "long_description": bundle.long_description,
        "price": bundle.price,
        "old_price": bundle.old_price,
        "image_url": (
            images[0]["image_url"]
            if images
            else bundle.image_url
        ),
        "category": bundle.category,

        # Actual quantity the customer is allowed to buy.
        "stock": available_stock,

        # Remaining bundle quantity configured by the admin.
        "configured_stock": int(bundle.stock or 0),

        "is_active": bool(bundle.is_active),
        "is_bundle": True,
        "images": images,
        "bundle_items": bundle_items,
    }


def get_bundle_query(db: Session):
    return (
        db.query(Product)
        .options(
            joinedload(Product.images),
            joinedload(Product.bundle_items)
            .joinedload(BundleItem.child_product),
        )
        .filter(Product.is_bundle.is_(True))
    )


def get_bundle_or_404(
    db: Session,
    bundle_id: int,
) -> Product:
    bundle = (
        get_bundle_query(db)
        .filter(Product.id == bundle_id)
        .first()
    )

    if not bundle:
        raise HTTPException(
            status_code=404,
            detail="Bundle not found",
        )

    return bundle


def upload_bundle_images(
    images: list[FastAPIUploadFile],
) -> list[dict]:
    if not images:
        raise HTTPException(
            status_code=400,
            detail="Upload at least one bundle image",
        )

    if len(images) > MAX_BUNDLE_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"A bundle can have at most "
                f"{MAX_BUNDLE_IMAGES} images"
            ),
        )

    uploaded_images = []

    try:
        for image in images:
            if (
                not image.content_type
                or not image.content_type.startswith("image/")
            ):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"{image.filename or 'Uploaded file'} "
                        "must be an image"
                    ),
                )

            result = cloudinary.uploader.upload(
                validated_image_stream(image),
                folder="uniqare/bundles",
                resource_type="image",
            )

            image_url = result.get("secure_url")
            public_id = result.get("public_id")

            if not image_url:
                raise HTTPException(
                    status_code=500,
                    detail=(
                        "Cloudinary did not return "
                        "an image URL"
                    ),
                )

            uploaded_images.append(
                {
                    "image_url": image_url,
                    "public_id": public_id,
                }
            )

        return uploaded_images

    except Exception:
        for uploaded_image in uploaded_images:
            public_id = uploaded_image.get("public_id")

            if public_id:
                try:
                    cloudinary.uploader.destroy(
                        public_id,
                        resource_type="image",
                    )
                except Exception:
                    pass

        raise


@router.get(
    "/",
    response_model=list[BundleResponse],
)
def get_public_bundles(
    db: Session = Depends(get_db),
):
    bundles = (
        get_bundle_query(db)
        .filter(Product.is_active.is_(True))
        .order_by(Product.id.desc())
        .all()
    )

    serialized_bundles = [
        serialize_bundle(bundle)
        for bundle in bundles
    ]

    return [
        bundle
        for bundle in serialized_bundles
        if bundle["stock"] > 0
    ]


@router.get(
    "/admin/all",
    response_model=list[BundleResponse],
)
def get_admin_bundles(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    bundles = (
        get_bundle_query(db)
        .order_by(Product.id.desc())
        .all()
    )

    return [
        serialize_bundle(bundle)
        for bundle in bundles
    ]


@router.get(
    "/{bundle_id}",
    response_model=BundleResponse,
)
def get_bundle(
    bundle_id: int,
    db: Session = Depends(get_db),
):
    bundle = get_bundle_or_404(
        db=db,
        bundle_id=bundle_id,
    )

    return serialize_bundle(bundle)


@router.post(
    "/",
    response_model=BundleResponse,
)
def create_bundle(
    name: Annotated[
        str,
        Form(),
    ],
    price: Annotated[
        float,
        Form(),
    ],
    stock: Annotated[
        int,
        Form(),
    ],
    items_json: Annotated[
        str,
        Form(),
    ],
    images: Annotated[
        list[SwaggerUploadFile],
        File(
            description=(
                "Select one or more bundle images "
                "from your device"
            ),
        ),
    ],
    short_description: Annotated[
        Optional[str],
        Form(),
    ] = None,
    long_description: Annotated[
        Optional[str],
        Form(),
    ] = None,
    old_price: Annotated[
        Optional[str],
        Form(),
    ] = None,
    category: Annotated[
        Optional[str],
        Form(),
    ] = "Bundle Offers",
    is_active: Annotated[
        bool,
        Form(),
    ] = True,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    cleaned_name = name.strip()

    if stock <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Available bundle quantity "
                "must be greater than 0"
            ),
        )

    if not cleaned_name:
        raise HTTPException(
            status_code=400,
            detail="Bundle name is required",
        )

    parsed_old_price = parse_optional_old_price(
        old_price
    )

    validate_prices(
        price=price,
        old_price=parsed_old_price,
    )

    quantities = parse_bundle_items(
        items_json
    )

    get_regular_products(
        db=db,
        quantities=quantities,
    )

    uploaded_images = upload_bundle_images(
        images
    )

    try:
        first_image_url = (
            uploaded_images[0]["image_url"]
        )

        bundle = Product(
            name=cleaned_name,
            short_description=short_description,
            long_description=long_description,
            price=price,
            old_price=parsed_old_price,
            image_url=first_image_url,
            category=category or "Bundle Offers",
            stock=stock,
            is_active=is_active,
            is_bundle=True,
        )

        db.add(bundle)
        db.flush()

        for product_id, quantity in quantities.items():
            db.add(
                BundleItem(
                    bundle_product_id=bundle.id,
                    child_product_id=product_id,
                    quantity=quantity,
                )
            )

        for index, uploaded_image in enumerate(
            uploaded_images
        ):
            db.add(
                ProductImage(
                    product_id=bundle.id,
                    image_url=uploaded_image["image_url"],
                    public_id=uploaded_image["public_id"],
                    sort_order=index,
                )
            )

        db.commit()

        saved_bundle = get_bundle_or_404(
            db=db,
            bundle_id=bundle.id,
        )

        return serialize_bundle(saved_bundle)

    except Exception:
        db.rollback()

        for uploaded_image in uploaded_images:
            public_id = uploaded_image.get("public_id")

            if public_id:
                try:
                    cloudinary.uploader.destroy(
                        public_id,
                        resource_type="image",
                    )
                except Exception:
                    pass

        raise


@router.patch(
    "/{bundle_id}",
    response_model=BundleResponse,
)
def update_bundle(
    bundle_id: int,
    name: Optional[str] = Form(None),
    short_description: Optional[str] = Form(None),
    long_description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    stock: Optional[int] = Form(None),
    old_price: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    is_active: Optional[bool] = Form(None),
    items_json: Optional[str] = Form(None),
    images: Annotated[
        Optional[list[SwaggerUploadFile]],
        File(
            description=(
                "Select additional bundle images "
                "from your device"
            ),
        ),
    ] = None,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    bundle = get_bundle_or_404(
        db=db,
        bundle_id=bundle_id,
    )

    if stock is not None and stock < 0:
        raise HTTPException(
            status_code=400,
            detail="Bundle quantity cannot be negative",
        )

    if (
        name is not None
        and not name.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Bundle name cannot be empty",
        )

    old_price_was_provided = (
        old_price is not None
    )

    parsed_old_price = (
        parse_optional_old_price(old_price)
        if old_price_was_provided
        else bundle.old_price
    )

    effective_price = (
        price
        if price is not None
        else bundle.price
    )

    validate_prices(
        price=effective_price,
        old_price=parsed_old_price,
    )

    quantities = None

    if items_json is not None:
        quantities = parse_bundle_items(
            items_json
        )

        get_regular_products(
            db=db,
            quantities=quantities,
        )

    uploaded_images = []

    if images:
        if (
            len(bundle.images) + len(images)
            > MAX_BUNDLE_IMAGES
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"A bundle can have at most "
                    f"{MAX_BUNDLE_IMAGES} images"
                ),
            )

        uploaded_images = upload_bundle_images(
            images
        )

    try:
        if name is not None:
            bundle.name = name.strip()

        if short_description is not None:
            bundle.short_description = short_description

        if long_description is not None:
            bundle.long_description = long_description

        if price is not None:
            bundle.price = price

        if stock is not None:
            bundle.stock = stock

            if stock <= 0:
                bundle.is_active = False

        if old_price_was_provided:
            bundle.old_price = parsed_old_price

        if category is not None:
            bundle.category = category

        if is_active is not None:
            bundle.is_active = is_active

        if quantities is not None:
            bundle.bundle_items.clear()
            db.flush()

            for product_id, quantity in quantities.items():
                bundle.bundle_items.append(
                    BundleItem(
                        child_product_id=product_id,
                        quantity=quantity,
                    )
                )

        next_sort_order = (
            max(
                (
                    image.sort_order
                    for image in bundle.images
                ),
                default=-1,
            )
            + 1
        )

        for index, uploaded_image in enumerate(
            uploaded_images
        ):
            bundle.images.append(
                ProductImage(
                    image_url=uploaded_image["image_url"],
                    public_id=uploaded_image["public_id"],
                    sort_order=next_sort_order + index,
                )
            )

        db.flush()

        if bundle.images:
            first_image = sorted(
                bundle.images,
                key=lambda item: item.sort_order,
            )[0]

            bundle.image_url = first_image.image_url

        db.commit()

        saved_bundle = get_bundle_or_404(
            db=db,
            bundle_id=bundle_id,
        )

        return serialize_bundle(saved_bundle)

    except Exception:
        db.rollback()

        for uploaded_image in uploaded_images:
            public_id = uploaded_image.get("public_id")

            if public_id:
                try:
                    cloudinary.uploader.destroy(
                        public_id,
                        resource_type="image",
                    )
                except Exception:
                    pass

        raise


@router.delete(
    "/{bundle_id}/images/{image_id}",
)
def delete_bundle_image(
    bundle_id: int,
    image_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    bundle = get_bundle_or_404(
        db=db,
        bundle_id=bundle_id,
    )

    image = next(
        (
            item
            for item in bundle.images
            if item.id == image_id
        ),
        None,
    )

    if not image:
        raise HTTPException(
            status_code=404,
            detail="Bundle image not found",
        )

    if len(bundle.images) <= 1:
        raise HTTPException(
            status_code=400,
            detail=(
                "A bundle must keep at least one image"
            ),
        )

    public_id = image.public_id

    db.delete(image)
    db.flush()

    remaining_images = sorted(
        (
            item
            for item in bundle.images
            if item.id != image_id
        ),
        key=lambda item: item.sort_order,
    )

    bundle.image_url = remaining_images[0].image_url

    db.commit()

    if public_id:
        try:
            cloudinary.uploader.destroy(
                public_id,
                resource_type="image",
            )
        except Exception:
            pass

    return {
        "message": "Bundle image deleted successfully",
    }


@router.delete("/{bundle_id}")
def delete_bundle(
    bundle_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    bundle = get_bundle_or_404(
        db=db,
        bundle_id=bundle_id,
    )

    used_in_order = (
        db.query(OrderItem)
        .filter(OrderItem.product_id == bundle_id)
        .first()
    )

    if used_in_order:
        raise HTTPException(
            status_code=400,
            detail=(
                "This bundle is used in an order. "
                "Disable it instead of deleting it."
            ),
        )

    public_ids = [
        image.public_id
        for image in bundle.images
        if image.public_id
    ]

    db.delete(bundle)
    db.commit()

    for public_id in public_ids:
        try:
            cloudinary.uploader.destroy(
                public_id,
                resource_type="image",
            )
        except Exception:
            pass

    return {
        "message": "Bundle deleted successfully",
    }