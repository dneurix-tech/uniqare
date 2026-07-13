from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Coupon, Order, OrderItem, Product
from app.schemas import (
    CheckCouponRequest,
    CheckCouponResponse,
    OrderAdminUpdate,
    OrderCreate,
    OrderPaymentUpdate,
)

router = APIRouter(prefix="/orders", tags=["Orders"])

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
                "product_name": item.product.name if item.product else None,
                "product_image": (
                    item.product.image_url if item.product else None
                ),
                "quantity": item.quantity,
                "unit_price": item.unit_price,
                "total_price": item.total_price,
            }
            for item in order.items
        ],
    }


def get_order_with_items(db: Session, order_id: int):
    return (
        db.query(Order)
        .options(
            joinedload(Order.items).joinedload(OrderItem.product)
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

        merged[product_id] = merged.get(product_id, 0) + quantity

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

    if coupon.expires_at and coupon.expires_at < datetime.utcnow():
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
            subtotal_price * (coupon.discount_value / 100)
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
    if not discount_type or discount_value is None:
        return 0.0

    if discount_type == "percent":
        value = subtotal_price * (discount_value / 100)

    elif discount_type == "fixed":
        value = discount_value

    else:
        value = 0

    return round(
        min(value, subtotal_price),
        2,
    )


def calculate_cart_discount(subtotal_price: float):
    """
    يمنح العميل خصم 10% تلقائيًا عندما يكون إجمالي
    المنتجات 1000 جنيه بالضبط أو أكثر.
    """

    if subtotal_price >= CART_DISCOUNT_THRESHOLD:
        return round(
            subtotal_price * CART_DISCOUNT_PERCENT,
            2,
        )

    return 0.0


def calculate_best_discount(
    coupon_discount: float,
    cart_discount: float,
    subtotal_price: float,
):
    """
    اختيار الخصم الأكبر فقط، بدون جمع خصم الكوبون
    مع الخصم التلقائي.
    """

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

    discount_type = order.coupon_discount_type
    discount_value = order.coupon_discount_value

    # دعم الطلبات القديمة التي لم تكن تحفظ بيانات الكوبون.
    if not discount_type or discount_value is None:
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

            order.coupon_discount_type = discount_type
            order.coupon_discount_value = discount_value

        elif order.subtotal_price and order.discount_amount:
            # في حالة حذف الكوبون، يتم الاحتفاظ بنسبة
            # الخصم القديمة للطلب.
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


def get_product_for_new_order(
    db: Session,
    product_id: int,
    quantity: int,
):
    product = (
        db.query(Product)
        .filter(Product.id == product_id)
        .with_for_update()
        .first()
    )

    if not product:
        raise HTTPException(
            status_code=404,
            detail="Product not found",
        )

    if product.is_active is False:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Product {product.name} is not available"
            ),
        )

    if product.stock < quantity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Only {product.stock} item(s) are "
                f"available for {product.name}"
            ),
        )

    return product


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
            detail="At least one product is required",
        )

    old_items = list(order.items)

    old_quantity_by_product = {
        item.product_id: item.quantity
        for item in old_items
    }

    old_unit_price_by_product = {
        item.product_id: item.unit_price
        for item in old_items
    }

    all_product_ids = (
        set(old_quantity_by_product)
        | set(quantities)
    )

    products = (
        db.query(Product)
        .filter(Product.id.in_(all_product_ids))
        .with_for_update()
        .all()
    )

    products_by_id = {
        product.id: product
        for product in products
    }

    missing_products = (
        set(quantities)
        - set(products_by_id)
    )

    if missing_products:
        missing_id = sorted(missing_products)[0]

        raise HTTPException(
            status_code=404,
            detail=f"Product #{missing_id} not found",
        )

    # التحقق من الكمية المطلوبة مقارنة بالمخزون،
    # مع إضافة كمية الطلب الحالية إلى المخزون المتاح.
    for product_id, requested_quantity in quantities.items():
        product = products_by_id[product_id]

        previous_quantity = (
            old_quantity_by_product.get(
                product_id,
                0,
            )
        )

        available_quantity = (
            product.stock
            + previous_quantity
        )

        if (
            product.is_active is False
            and requested_quantity > previous_quantity
        ):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Product {product.name} "
                    "is not available"
                ),
            )

        if requested_quantity > available_quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Only {available_quantity} item(s) "
                    f"are available for {product.name}"
                ),
            )

    # إعادة كميات المنتجات القديمة إلى المخزون.
    for item in old_items:
        product = products_by_id.get(
            item.product_id
        )

        if product:
            product.stock += item.quantity

            if product.stock > 0:
                product.is_active = True

    # حذف عناصر الطلب القديمة وإعادة إنشائها.
    order.items.clear()
    db.flush()

    subtotal_price = 0.0

    for product_id, quantity in quantities.items():
        product = products_by_id[product_id]

        unit_price = old_unit_price_by_product.get(
            product_id,
            product.price,
        )

        item_total = round(
            unit_price * quantity,
            2,
        )

        if product.stock < quantity:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Only {product.stock} item(s) "
                    f"are available for {product.name}"
                ),
            )

        product.stock -= quantity

        if product.stock <= 0:
            product.stock = 0
            product.is_active = False

        order.items.append(
            OrderItem(
                product_id=product_id,
                quantity=quantity,
                unit_price=unit_price,
                total_price=item_total,
            )
        )

        subtotal_price += item_total

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

    subtotal_price = 0.0

    for product_id, quantity in quantities.items():
        product = get_product_for_new_order(
            db=db,
            product_id=product_id,
            quantity=quantity,
        )

        subtotal_price += (
            product.price * quantity
        )

    subtotal_price = round(
        subtotal_price,
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
        coupon_discount=coupon_discount_amount,
        cart_discount=cart_discount_amount,
        subtotal_price=subtotal_price,
    )

    # إذا كان الخصمان متساويين، نستخدم الخصم
    # التلقائي حتى لا يتم استهلاك الكوبون بدون داعٍ.
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
        subtotal_price = 0.0
        validated_items = []

        for product_id, quantity in quantities.items():
            product = get_product_for_new_order(
                db=db,
                product_id=product_id,
                quantity=quantity,
            )

            subtotal_price += (
                product.price * quantity
            )

            validated_items.append(
                (product, quantity)
            )

        subtotal_price = round(
            subtotal_price,
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

        # تطبيق الخصم الأكبر فقط.
        discount_amount = calculate_best_discount(
            coupon_discount=coupon_discount_amount,
            cart_discount=cart_discount_amount,
            subtotal_price=subtotal_price,
        )

        total_price = round(
            subtotal_price - discount_amount,
            2,
        )

        # يتم اعتبار الكوبون مستخدمًا فقط عندما يكون
        # خصمه أكبر من خصم الـ10% التلقائي.
        #
        # في حالة تساوي الخصمين، نستخدم الخصم التلقائي
        # ولا نستهلك الكوبون.
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
            quantity=sum(quantities.values()),
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
            payment_method="Not selected yet",
            payment_status=(
                "Waiting for customer payment choice"
            ),
            payment_details="",
            status="pending",
        )

        db.add(new_order)
        db.flush()

        for product, quantity in validated_items:
            product.stock -= quantity

            if product.stock <= 0:
                product.stock = 0
                product.is_active = False

            order_item = OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=product.price,
                total_price=round(
                    product.price * quantity,
                    2,
                ),
            )

            db.add(order_item)

        # زيادة عدد استخدامات الكوبون فقط إذا كان
        # الكوبون هو الخصم الذي تم تطبيقه فعليًا.
        if applied_coupon:
            applied_coupon.used_count += 1

        db.commit()

        saved_order = get_order_with_items(
            db=db,
            order_id=new_order.id,
        )

        return order_to_dict(saved_order)

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
            .joinedload(OrderItem.product)
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
                requested_items=requested_items,
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
            product = item.product

            if product:
                product.stock += item.quantity

                if product.stock > 0:
                    product.is_active = True

        # الطلب لا يحفظ coupon_code إلا إذا كان
        # الكوبون هو الخصم المطبق فعليًا.
        if order.coupon_code:
            coupon = (
                db.query(Coupon)
                .filter(
                    Coupon.code
                    == order.coupon_code.strip().upper()
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
            )
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

    order.payment_method = payment.payment_method
    order.payment_status = payment.payment_status
    order.payment_details = payment.payment_details

    db.commit()

    updated_order = get_order_with_items(
        db=db,
        order_id=order_id,
    )

    return order_to_dict(updated_order)