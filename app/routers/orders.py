from collections import defaultdict
from datetime import datetime

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
)
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    BundleItem,
    Coupon,
    Order,
    OrderItem,
    OrderItemComponent,
    Product,
)
from app.schemas import (
    CheckCouponRequest,
    CheckCouponResponse,
    OrderAdminUpdate,
    OrderCreate,
    OrderPaymentUpdate,
)
from app.services.email_service import send_order_emails


router = APIRouter(
    prefix="/orders",
    tags=["Orders"],
)

CART_DISCOUNT_THRESHOLD = 1000
CART_DISCOUNT_PERCENT = 0.10


def order_to_dict(order: Order):
    return {
        "id": order.id,
        "customer_name": order.customer_name,
        "phone": order.phone,
        "email": order.email,
        "governorate": order.governorate,
        "address": order.address,
        "note": order.note,
        "product_id": order.product_id,
        "quantity": order.quantity,
        "subtotal_price": order.subtotal_price,
        "coupon_code": order.coupon_code,
        "coupon_discount_type": order.coupon_discount_type,
        "coupon_discount_value": order.coupon_discount_value,
        "discount_amount": order.discount_amount,
        "total_price": order.total_price,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "payment_details": order.payment_details,
        "status": order.status,
        "created_at": order.created_at,
        "items": [
            {
                "id": item.id,
                "product_id": item.product_id,
                "product_name": (
                    item.product.name
                    if item.product
                    else None
                ),
                "product_image": (
                    item.product.image_url
                    if item.product
                    else None
                ),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
                "bundle_components": [
                    {
                        "id": component.id,
                        "product_id": component.product_id,
                        "product_name": (
                            component.product.name
                            if component.product
                            else None
                        ),
                        "product_image": (
                            component.product.image_url
                            if component.product
                            else None
                        ),
                        "quantity": component.quantity,
                    }
                    for component in item.components
                ],
            }
            for item in order.items
        ],
    }


def create_order_email_snapshot(
    order_data: dict,
):
    email_snapshot = {
        **order_data,
        "items": [
            {
                **dict(item),
                "bundle_components": [
                    dict(component)
                    for component in item.get(
                        "bundle_components",
                        [],
                    )
                ],
            }
            for item in order_data.get("items", [])
        ],
    }

    email_snapshot["customer_email"] = (
        order_data.get("email") or ""
    )

    return email_snapshot


def get_order_with_items(
    db: Session,
    order_id: int,
):
    return (
        db.query(Order)
        .options(
            joinedload(Order.items)
            .joinedload(OrderItem.product),
            joinedload(Order.items)
            .joinedload(OrderItem.components)
            .joinedload(OrderItemComponent.product),
        )
        .filter(Order.id == order_id)
        .first()
    )


def merge_item_quantities(items):
    merged: dict[int, int] = {}

    for item in items:
        if isinstance(item, dict):
            product_id = int(item["product_id"])
            quantity = int(item["quantity"])
        else:
            product_id = int(item.product_id)
            quantity = int(item.quantity)

        if quantity <= 0:
            raise HTTPException(
                status_code=400,
                detail="Quantity must be greater than 0",
            )

        merged[product_id] = (
            merged.get(product_id, 0)
            + quantity
        )

    return merged


def calculate_coupon_discount(
    db: Session,
    coupon_code: str | None,
    subtotal_price: float,
):
    if not coupon_code:
        return None, 0.0

    code = coupon_code.strip().upper()

    coupon = (
        db.query(Coupon)
        .filter(Coupon.code == code)
        .first()
    )

    if not coupon:
        raise HTTPException(
            status_code=400,
            detail="Invalid coupon code",
        )

    if coupon.is_active is False:
        raise HTTPException(
            status_code=400,
            detail="Coupon is not active",
        )

    if (
        coupon.expires_at
        and coupon.expires_at < datetime.utcnow()
    ):
        raise HTTPException(
            status_code=400,
            detail="Coupon has expired",
        )

    if (
        coupon.usage_limit is not None
        and coupon.used_count >= coupon.usage_limit
    ):
        raise HTTPException(
            status_code=400,
            detail="Coupon usage limit reached",
        )

    if subtotal_price < coupon.min_order_amount:
        raise HTTPException(
            status_code=400,
            detail=(
                "Minimum order amount for this coupon is "
                f"{coupon.min_order_amount}"
            ),
        )

    if coupon.discount_type == "percent":
        discount_amount = (
            subtotal_price
            * (coupon.discount_value / 100)
        )

    elif coupon.discount_type == "fixed":
        discount_amount = coupon.discount_value

    else:
        raise HTTPException(
            status_code=400,
            detail="Invalid coupon type",
        )

    discount_amount = round(
        min(discount_amount, subtotal_price),
        2,
    )

    return coupon, discount_amount


def calculate_snapshot_coupon_discount(
    discount_type: str | None,
    discount_value: float | None,
    subtotal_price: float,
):
    if (
        not discount_type
        or discount_value is None
    ):
        return 0.0

    if discount_type == "percent":
        value = (
            subtotal_price
            * (discount_value / 100)
        )

    elif discount_type == "fixed":
        value = discount_value

    else:
        value = 0

    return round(
        min(value, subtotal_price),
        2,
    )


def calculate_cart_discount(
    subtotal_price: float,
):
    if subtotal_price >= CART_DISCOUNT_THRESHOLD:
        return round(
            subtotal_price
            * CART_DISCOUNT_PERCENT,
            2,
        )

    return 0.0


def calculate_best_discount(
    coupon_discount: float,
    cart_discount: float,
    subtotal_price: float,
):
    best_discount = max(
        coupon_discount,
        cart_discount,
    )

    return round(
        min(best_discount, subtotal_price),
        2,
    )


def calculate_existing_order_discount(
    db: Session,
    order: Order,
    subtotal_price: float,
):
    cart_discount = calculate_cart_discount(
        subtotal_price
    )

    if not order.coupon_code:
        return cart_discount

    discount_type = (
        order.coupon_discount_type
    )

    discount_value = (
        order.coupon_discount_value
    )

    if (
        not discount_type
        or discount_value is None
    ):
        coupon = (
            db.query(Coupon)
            .filter(
                Coupon.code
                == order.coupon_code.strip().upper()
            )
            .first()
        )

        if coupon:
            discount_type = coupon.discount_type
            discount_value = coupon.discount_value

            order.coupon_discount_type = (
                discount_type
            )

            order.coupon_discount_value = (
                discount_value
            )

        elif (
            order.subtotal_price
            and order.discount_amount
        ):
            old_ratio = (
                order.discount_amount
                / order.subtotal_price
            )

            old_discount = round(
                min(
                    subtotal_price * old_ratio,
                    subtotal_price,
                ),
                2,
            )

            return calculate_best_discount(
                coupon_discount=old_discount,
                cart_discount=cart_discount,
                subtotal_price=subtotal_price,
            )

    coupon_discount = (
        calculate_snapshot_coupon_discount(
            discount_type=discount_type,
            discount_value=discount_value,
            subtotal_price=subtotal_price,
        )
    )

    return calculate_best_discount(
        coupon_discount=coupon_discount,
        cart_discount=cart_discount,
        subtotal_price=subtotal_price,
    )


def build_stock_plan(
    db: Session,
    quantities: dict[int, int],
    lock: bool,
):
    """
    Build one combined stock plan.

    Regular products consume their own stock.
    Bundles consume the stock of their component products.
    The combined plan prevents over-selling when the same product
    exists both individually and inside one or more bundles.
    """

    ordered_product_ids = list(quantities)

    ordered_query = (
        db.query(Product)
        .filter(
            Product.id.in_(
                ordered_product_ids
            )
        )
    )

    if lock:
        ordered_query = (
            ordered_query.with_for_update()
        )

    ordered_products = ordered_query.all()

    ordered_products_by_id = {
        product.id: product
        for product in ordered_products
    }

    missing_ids = (
        set(ordered_product_ids)
        - set(ordered_products_by_id)
    )

    if missing_ids:
        missing_id = sorted(missing_ids)[0]

        raise HTTPException(
            status_code=404,
            detail=(
                f"Product #{missing_id} not found"
            ),
        )

    bundle_ids = [
        product_id
        for product_id, product
        in ordered_products_by_id.items()
        if product.is_bundle
    ]

    bundle_items_by_bundle: dict[
        int,
        list[BundleItem],
    ] = defaultdict(list)

    if bundle_ids:
        bundle_items = (
            db.query(BundleItem)
            .filter(
                BundleItem.bundle_product_id.in_(
                    bundle_ids
                )
            )
            .all()
        )

        for bundle_item in bundle_items:
            bundle_items_by_bundle[
                bundle_item.bundle_product_id
            ].append(bundle_item)

    stock_requirements: dict[int, int] = (
        defaultdict(int)
    )

    bundle_components: dict[
        int,
        list[tuple[int, int]],
    ] = {}

    for product_id, order_quantity in (
        quantities.items()
    ):
        product = ordered_products_by_id[
            product_id
        ]

        if product.is_active is False:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Product {product.name} "
                    "is not available"
                ),
            )

        if product.is_bundle:
            component_rows = (
                bundle_items_by_bundle.get(
                    product_id,
                    [],
                )
            )

            if not component_rows:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Bundle {product.name} "
                        "has no products"
                    ),
                )

            bundle_components[product_id] = []

            for component in component_rows:
                required_quantity = (
                    int(component.quantity)
                    * order_quantity
                )

                stock_requirements[
                    component.child_product_id
                ] += required_quantity

                bundle_components[
                    product_id
                ].append(
                    (
                        component.child_product_id,
                        int(component.quantity),
                    )
                )

        else:
            stock_requirements[
                product_id
            ] += order_quantity

    stock_product_ids = list(
        stock_requirements
    )

    stock_query = (
        db.query(Product)
        .filter(
            Product.id.in_(
                stock_product_ids
            )
        )
    )

    if lock:
        stock_query = (
            stock_query.with_for_update()
        )

    stock_products = stock_query.all()

    stock_products_by_id = {
        product.id: product
        for product in stock_products
    }

    missing_stock_products = (
        set(stock_product_ids)
        - set(stock_products_by_id)
    )

    if missing_stock_products:
        missing_id = sorted(
            missing_stock_products
        )[0]

        raise HTTPException(
            status_code=404,
            detail=(
                f"Bundle component #{missing_id} "
                "was not found"
            ),
        )

    for (
        stock_product_id,
        required_quantity,
    ) in stock_requirements.items():
        stock_product = (
            stock_products_by_id[
                stock_product_id
            ]
        )

        if stock_product.is_bundle:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Nested bundles are not supported"
                ),
            )

        if stock_product.is_active is False:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Product {stock_product.name} "
                    "is not available"
                ),
            )

        available_stock = int(
            stock_product.stock or 0
        )

        if available_stock < required_quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Only {available_stock} item(s) "
                    f"are available for "
                    f"{stock_product.name}"
                ),
            )

    return {
        "ordered_products": (
            ordered_products_by_id
        ),
        "stock_requirements": dict(
            stock_requirements
        ),
        "stock_products": (
            stock_products_by_id
        ),
        "bundle_components": (
            bundle_components
        ),
    }


def deduct_stock_plan(
    stock_requirements: dict[int, int],
    stock_products: dict[int, Product],
):
    for (
        product_id,
        required_quantity,
    ) in stock_requirements.items():
        product = stock_products[product_id]

        product.stock -= required_quantity

        if product.stock <= 0:
            product.stock = 0
            product.is_active = False


def restore_order_item_stock(
    item: OrderItem,
):
    if item.components:
        for component in item.components:
            product = component.product

            if product:
                product.stock += (
                    component.quantity
                )

                if product.stock > 0:
                    product.is_active = True

        return

    product = item.product

    if product:
        product.stock += item.quantity

        if product.stock > 0:
            product.is_active = True


def add_order_item_with_snapshot(
    db: Session,
    order: Order,
    product: Product,
    quantity: int,
    unit_price: float,
    bundle_components: dict[
        int,
        list[tuple[int, int]],
    ],
):
    order_item = OrderItem(
        order_id=order.id,
        product_id=product.id,
        quantity=quantity,
        unit_price=unit_price,
        total_price=round(
            unit_price * quantity,
            2,
        ),
    )

    db.add(order_item)
    db.flush()

    for (
        component_product_id,
        component_quantity_per_bundle,
    ) in bundle_components.get(
        product.id,
        [],
    ):
        db.add(
            OrderItemComponent(
                order_item_id=order_item.id,
                product_id=(
                    component_product_id
                ),
                quantity=(
                    component_quantity_per_bundle
                    * quantity
                ),
            )
        )

    return order_item


def replace_order_items(
    db: Session,
    order: Order,
    requested_items,
):
    quantities = merge_item_quantities(
        requested_items
    )

    if not quantities:
        raise HTTPException(
            status_code=400,
            detail=(
                "At least one product is required"
            ),
        )

    old_items = list(order.items)

    old_unit_price_by_product = {
        item.product_id: item.unit_price
        for item in old_items
    }

    for item in old_items:
        restore_order_item_stock(item)

    stock_plan = build_stock_plan(
        db=db,
        quantities=quantities,
        lock=True,
    )

    deduct_stock_plan(
        stock_requirements=(
            stock_plan["stock_requirements"]
        ),
        stock_products=(
            stock_plan["stock_products"]
        ),
    )

    order.items.clear()
    db.flush()

    subtotal_price = 0.0

    for product_id, quantity in (
        quantities.items()
    ):
        product = (
            stock_plan["ordered_products"][
                product_id
            ]
        )

        unit_price = (
            old_unit_price_by_product.get(
                product_id,
                product.price,
            )
        )

        order_item = (
            add_order_item_with_snapshot(
                db=db,
                order=order,
                product=product,
                quantity=quantity,
                unit_price=unit_price,
                bundle_components=(
                    stock_plan[
                        "bundle_components"
                    ]
                ),
            )
        )

        subtotal_price += (
            order_item.total_price
        )

    subtotal_price = round(
        subtotal_price,
        2,
    )

    first_product_id = next(
        iter(quantities)
    )

    total_quantity = sum(
        quantities.values()
    )

    discount_amount = (
        calculate_existing_order_discount(
            db=db,
            order=order,
            subtotal_price=subtotal_price,
        )
    )

    order.product_id = first_product_id
    order.quantity = total_quantity
    order.subtotal_price = subtotal_price
    order.discount_amount = discount_amount
    order.total_price = round(
        subtotal_price - discount_amount,
        2,
    )


@router.post(
    "/check-coupon",
    response_model=CheckCouponResponse,
)
def check_coupon(
    data: CheckCouponRequest,
    db: Session = Depends(get_db),
):
    quantities = merge_item_quantities(
        data.items
    )

    if not quantities:
        raise HTTPException(
            status_code=400,
            detail="At least one item is required",
        )

    stock_plan = build_stock_plan(
        db=db,
        quantities=quantities,
        lock=False,
    )

    subtotal_price = round(
        sum(
            (
                stock_plan[
                    "ordered_products"
                ][product_id].price
                * quantity
            )
            for product_id, quantity
            in quantities.items()
        ),
        2,
    )

    coupon, coupon_discount_amount = (
        calculate_coupon_discount(
            db=db,
            coupon_code=data.coupon_code,
            subtotal_price=subtotal_price,
        )
    )

    cart_discount_amount = (
        calculate_cart_discount(
            subtotal_price
        )
    )

    discount_amount = calculate_best_discount(
        coupon_discount=(
            coupon_discount_amount
        ),
        cart_discount=(
            cart_discount_amount
        ),
        subtotal_price=subtotal_price,
    )

    coupon_is_applied = (
        coupon is not None
        and coupon_discount_amount
        > cart_discount_amount
    )

    if coupon_is_applied:
        message = (
            "Coupon discount applied because "
            "it is the larger discount"
        )

    elif cart_discount_amount > 0:
        message = (
            "Automatic 10% discount applied because "
            "it is the larger discount"
        )

    else:
        message = "Coupon applied successfully"

    return {
        "coupon_code": (
            coupon.code
            if coupon_is_applied
            else None
        ),
        "subtotal_price": subtotal_price,
        "discount_amount": discount_amount,
        "total_price": round(
            subtotal_price - discount_amount,
            2,
        ),
        "message": message,
    }


@router.post("/")
def create_order(
    order: OrderCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    quantities = merge_item_quantities(
        order.items
    )

    if not quantities:
        raise HTTPException(
            status_code=400,
            detail="At least one item is required",
        )

    try:
        stock_plan = build_stock_plan(
            db=db,
            quantities=quantities,
            lock=True,
        )

        subtotal_price = round(
            sum(
                (
                    stock_plan[
                        "ordered_products"
                    ][product_id].price
                    * quantity
                )
                for product_id, quantity
                in quantities.items()
            ),
            2,
        )

        coupon, coupon_discount_amount = (
            calculate_coupon_discount(
                db=db,
                coupon_code=order.coupon_code,
                subtotal_price=subtotal_price,
            )
        )

        cart_discount_amount = (
            calculate_cart_discount(
                subtotal_price
            )
        )

        discount_amount = (
            calculate_best_discount(
                coupon_discount=(
                    coupon_discount_amount
                ),
                cart_discount=(
                    cart_discount_amount
                ),
                subtotal_price=subtotal_price,
            )
        )

        total_price = round(
            subtotal_price - discount_amount,
            2,
        )

        applied_coupon = (
            coupon
            if (
                coupon is not None
                and coupon_discount_amount
                > cart_discount_amount
            )
            else None
        )

        first_product_id = next(
            iter(quantities)
        )

        new_order = Order(
            customer_name=order.customer_name,
            phone=order.phone,
            email=order.email,
            governorate=order.governorate,
            address=order.address,
            note=order.note,
            product_id=first_product_id,
            quantity=sum(
                quantities.values()
            ),
            subtotal_price=subtotal_price,
            coupon_code=(
                applied_coupon.code
                if applied_coupon
                else None
            ),
            coupon_discount_type=(
                applied_coupon.discount_type
                if applied_coupon
                else None
            ),
            coupon_discount_value=(
                applied_coupon.discount_value
                if applied_coupon
                else None
            ),
            discount_amount=discount_amount,
            total_price=total_price,
            payment_method=(
                "Not selected yet"
            ),
            payment_status=(
                "Waiting for customer "
                "payment choice"
            ),
            payment_details="",
            status="pending",
        )

        db.add(new_order)
        db.flush()

        deduct_stock_plan(
            stock_requirements=(
                stock_plan[
                    "stock_requirements"
                ]
            ),
            stock_products=(
                stock_plan[
                    "stock_products"
                ]
            ),
        )

        for product_id, quantity in (
            quantities.items()
        ):
            product = (
                stock_plan[
                    "ordered_products"
                ][product_id]
            )

            add_order_item_with_snapshot(
                db=db,
                order=new_order,
                product=product,
                quantity=quantity,
                unit_price=product.price,
                bundle_components=(
                    stock_plan[
                        "bundle_components"
                    ]
                ),
            )

        if applied_coupon:
            applied_coupon.used_count += 1

        db.commit()

        saved_order = get_order_with_items(
            db=db,
            order_id=new_order.id,
        )

        if not saved_order:
            db.refresh(new_order)
            saved_order = new_order

        saved_order_data = order_to_dict(
            saved_order
        )

        email_snapshot = (
            create_order_email_snapshot(
                saved_order_data
            )
        )

        background_tasks.add_task(
            send_order_emails,
            email_snapshot,
        )

        return saved_order_data

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


@router.get("/")
def get_orders(
    db: Session = Depends(get_db),
):
    orders = (
        db.query(Order)
        .options(
            joinedload(Order.items)
            .joinedload(OrderItem.product),
            joinedload(Order.items)
            .joinedload(OrderItem.components)
            .joinedload(OrderItemComponent.product),
        )
        .order_by(Order.created_at.desc())
        .all()
    )

    return [
        order_to_dict(order)
        for order in orders
    ]


@router.get("/{order_id}")
def get_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    return order_to_dict(order)


@router.patch("/{order_id}")
def update_order_admin(
    order_id: int,
    data: OrderAdminUpdate,
    db: Session = Depends(get_db),
):
    order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    try:
        update_data = data.model_dump(
            exclude_unset=True
        )

        requested_items = update_data.pop(
            "items",
            None,
        )

        allowed_fields = [
            "customer_name",
            "phone",
            "email",
            "governorate",
            "address",
            "note",
            "status",
            "payment_method",
            "payment_status",
            "payment_details",
        ]

        for field in allowed_fields:
            if field in update_data:
                setattr(
                    order,
                    field,
                    update_data[field],
                )

        if requested_items is not None:
            replace_order_items(
                db=db,
                order=order,
                requested_items=(
                    requested_items
                ),
            )

        db.commit()

        updated_order = get_order_with_items(
            db=db,
            order_id=order_id,
        )

        return order_to_dict(updated_order)

    except HTTPException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise


@router.delete("/{order_id}")
def delete_order(
    order_id: int,
    db: Session = Depends(get_db),
):
    order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    try:
        for item in order.items:
            restore_order_item_stock(item)

        if order.coupon_code:
            coupon = (
                db.query(Coupon)
                .filter(
                    Coupon.code
                    == order.coupon_code
                    .strip()
                    .upper()
                )
                .first()
            )

            if (
                coupon
                and coupon.used_count > 0
            ):
                coupon.used_count -= 1

        db.delete(order)
        db.commit()

        return {
            "message": (
                "Order deleted successfully"
            ),
        }

    except Exception:
        db.rollback()
        raise


@router.patch("/{order_id}/status")
def update_order_status(
    order_id: int,
    status: str,
    db: Session = Depends(get_db),
):
    order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order.status = status

    db.commit()

    updated_order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    return order_to_dict(updated_order)


@router.patch("/{order_id}/payment")
def update_order_payment(
    order_id: int,
    payment: OrderPaymentUpdate,
    db: Session = Depends(get_db),
):
    order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    if not order:
        raise HTTPException(
            status_code=404,
            detail="Order not found",
        )

    order.payment_method = (
        payment.payment_method
    )

    order.payment_status = (
        payment.payment_status
    )

    order.payment_details = (
        payment.payment_details
    )

    db.commit()

    updated_order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    return order_to_dict(updated_order)
