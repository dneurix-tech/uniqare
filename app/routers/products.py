from typing import Optional

import cloudinary.uploader
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.image_security import validated_image_stream
from app.models import BundleItem, Product
from app.schemas import ProductResponse
from app.security import require_admin


router = APIRouter(
    prefix="/products",
    tags=["Products"],
)


def regular_products_query(db: Session):
    return (
        db.query(Product)
        .filter(Product.is_bundle.is_(False))
    )


def get_regular_product_or_404(
    db: Session,
    product_id: int,
) -> Product:
    product = (
        regular_products_query(db)
        .filter(Product.id == product_id)
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    return product


def upload_image_to_cloudinary(
    image: UploadFile,
) -> str:
    if (
        not image.content_type
        or not image.content_type.startswith("image/")
    ):
        raise HTTPException(
            status_code=400,
            detail="Uploaded file must be an image",
        )

    try:
        upload_result = cloudinary.uploader.upload(
            validated_image_stream(image),
            folder="uniqare/products",
            resource_type="image",
        )

        image_url = upload_result.get("secure_url")

        if not image_url:
            raise HTTPException(
                status_code=500,
                detail=(
                    "Cloudinary did not return image URL"
                ),
            )

        return image_url

    except HTTPException:
        raise

    except Exception as error:
        print(
            "Cloudinary upload error:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail="Image upload failed",
        )


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


def validate_product_prices(
    price: float,
    old_price: Optional[float],
) -> None:
    if price <= 0:
        raise HTTPException(
            status_code=400,
            detail=(
                "Current price must be greater than 0"
            ),
        )

    if (
        old_price is not None
        and old_price <= price
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "Old price must be greater than "
                "current price"
            ),
        )


@router.get(
    "/",
    response_model=list[ProductResponse],
)
def get_products(
    db: Session = Depends(get_db),
):
    # Storefront intentionally returns both available and sold-out products.
    # Product data is public; admin-only operations remain protected.
    return (
        regular_products_query(db)
        .order_by(Product.id.desc())
        .all()
    )


@router.get(
    "/admin/all",
    response_model=list[ProductResponse],
)
def get_all_products(
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    return (
        regular_products_query(db)
        .order_by(Product.id.desc())
        .all()
    )


@router.post(
    "/",
    response_model=ProductResponse,
)
def create_product(
    name: str = Form(...),
    short_description: Optional[str] = Form(None),
    long_description: Optional[str] = Form(None),
    price: float = Form(...),
    old_price: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    stock: int = Form(0),
    is_active: bool = Form(True),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    cleaned_name = name.strip()

    if not cleaned_name:
        raise HTTPException(
            status_code=400,
            detail="Product name is required",
        )

    if stock < 0:
        raise HTTPException(
            status_code=400,
            detail="Stock cannot be negative",
        )

    parsed_old_price = parse_optional_old_price(
        old_price
    )

    validate_product_prices(
        price=price,
        old_price=parsed_old_price,
    )

    image_url = None

    if image:
        image_url = upload_image_to_cloudinary(
            image
        )

    if stock <= 0:
        stock = 0
        is_active = False

    new_product = Product(
        name=cleaned_name,
        short_description=short_description,
        long_description=long_description,
        price=price,
        old_price=parsed_old_price,
        image_url=image_url,
        category=category,
        stock=stock,
        is_active=is_active,
        is_bundle=False,
    )

    db.add(new_product)
    db.commit()
    db.refresh(new_product)

    return new_product


@router.get(
    "/{product_id}",
    response_model=ProductResponse,
)
def get_product(
    product_id: int,
    db: Session = Depends(get_db),
):
    return get_regular_product_or_404(
        db=db,
        product_id=product_id,
    )


@router.patch(
    "/{product_id}",
    response_model=ProductResponse,
)
def update_product(
    product_id: int,
    name: Optional[str] = Form(None),
    short_description: Optional[str] = Form(None),
    long_description: Optional[str] = Form(None),
    price: Optional[float] = Form(None),
    old_price: Optional[str] = Form(None),
    category: Optional[str] = Form(None),
    stock: Optional[int] = Form(None),
    is_active: Optional[bool] = Form(None),
    image: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    product = get_regular_product_or_404(
        db=db,
        product_id=product_id,
    )

    if (
        name is not None
        and not name.strip()
    ):
        raise HTTPException(
            status_code=400,
            detail="Product name cannot be empty",
        )

    if stock is not None and stock < 0:
        raise HTTPException(
            status_code=400,
            detail="Stock cannot be negative",
        )

    old_price_was_provided = (
        old_price is not None
    )

    parsed_old_price = (
        parse_optional_old_price(old_price)
        if old_price_was_provided
        else product.old_price
    )

    effective_price = (
        price
        if price is not None
        else product.price
    )

    validate_product_prices(
        price=effective_price,
        old_price=parsed_old_price,
    )

    if name is not None:
        product.name = name.strip()

    if short_description is not None:
        product.short_description = short_description

    if long_description is not None:
        product.long_description = long_description

    if price is not None:
        product.price = price

    if old_price_was_provided:
        product.old_price = parsed_old_price

    if category is not None:
        product.category = category

    if stock is not None:
        product.stock = stock

    if is_active is not None:
        product.is_active = is_active

    if image:
        product.image_url = upload_image_to_cloudinary(
            image
        )

    if product.stock <= 0:
        product.stock = 0
        product.is_active = False

    elif is_active is None:
        product.is_active = True

    db.commit()
    db.refresh(product)

    return product


@router.delete("/{product_id}")
def delete_product(
    product_id: int,
    db: Session = Depends(get_db),
    _admin: dict = Depends(require_admin),
):
    product = get_regular_product_or_404(
        db=db,
        product_id=product_id,
    )

    used_in_bundle = (
        db.query(BundleItem)
        .filter(
            BundleItem.child_product_id == product_id
        )
        .first()
    )

    if used_in_bundle:
        raise HTTPException(
            status_code=400,
            detail=(
                "This product is used inside a bundle. "
                "Remove it from the bundle first."
            ),
        )

    try:
        db.delete(product)
        db.commit()

    except IntegrityError:
        db.rollback()

        raise HTTPException(
            status_code=400,
            detail=(
                "This product cannot be deleted because "
                "it is used in an existing order."
            ),
        )

    return {
        "message": "Product deleted successfully",
    }
