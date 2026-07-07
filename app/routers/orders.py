from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Coupon, Order, OrderItem, Product
from app.schemas import (
    CheckCouponRequest,
    CheckCouponResponse,
    OrderCreate,
    OrderPaymentUpdate,
    OrderResponse,
)

router = APIRouter(prefix="/orders", tags=["Orders"])


def calculate_coupon_discount(db: Session, coupon_code: str | None, subtotal_price: float):
    if not coupon_code:
        return None, 0

    code = coupon_code.strip().upper()
    coupon = db.query(Coupon).filter(Coupon.code == code).first()

    if not coupon:
        raise HTTPException(status_code=400, detail="Invalid coupon code")

    if coupon.is_active is False:
        raise HTTPException(status_code=400, detail="Coupon is not active")

    if coupon.expires_at and coupon.expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Coupon has expired")

    if coupon.usage_limit is not None and coupon.used_count >= coupon.usage_limit:
        raise HTTPException(status_code=400, detail="Coupon usage limit reached")

    if subtotal_price < coupon.min_order_amount:
        raise HTTPException(
            status_code=400,
            detail=f"Minimum order amount for this coupon is {coupon.min_order_amount}",
        )

    if coupon.discount_type == "percent":
        discount_amount = subtotal_price * (coupon.discount_value / 100)
    elif coupon.discount_type == "fixed":
        discount_amount = coupon.discount_value
    else:
        raise HTTPException(status_code=400, detail="Invalid coupon type")

    if discount_amount > subtotal_price:
        discount_amount = subtotal_price

    return coupon, round(discount_amount, 2)


def validate_order_item(db: Session, product_id: int, quantity: int):
    product = db.query(Product).filter(Product.id == product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.is_active is False:
        raise HTTPException(status_code=400, detail=f"Product {product.name} is not available")

    if quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")

    if product.stock < quantity:
        raise HTTPException(status_code=400, detail="Not enough stock")

    return product


@router.post("/check-coupon", response_model=CheckCouponResponse)
def check_coupon(data: CheckCouponRequest, db: Session = Depends(get_db)):
    if not data.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    subtotal_price = 0.0
    for item in data.items:
        validate_order_item(db, item.product_id, item.quantity)
        product = db.query(Product).filter(Product.id == item.product_id).first()
        subtotal_price += product.price * item.quantity

    coupon, discount_amount = calculate_coupon_discount(
        db=db,
        coupon_code=data.coupon_code,
        subtotal_price=subtotal_price,
    )

    total_price = subtotal_price - discount_amount

    return {
        "coupon_code": coupon.code if coupon else None,
        "subtotal_price": subtotal_price,
        "discount_amount": discount_amount,
        "total_price": total_price,
        "message": "Coupon applied successfully",
    }


@router.post("/", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    if not order.items:
        raise HTTPException(status_code=400, detail="At least one item is required")

    subtotal_price = 0.0
    validated_items = []

    for item in order.items:
        product = validate_order_item(db, item.product_id, item.quantity)
        subtotal_price += product.price * item.quantity
        validated_items.append((product, item.quantity))

    coupon, discount_amount = calculate_coupon_discount(
        db=db,
        coupon_code=order.coupon_code,
        subtotal_price=subtotal_price,
    )

    total_price = subtotal_price - discount_amount

    new_order = Order(
        customer_name=order.customer_name,
        phone=order.phone,
        email=order.email,
        governorate=order.governorate,
        address=order.address,
        note=order.note,
        product_id=order.items[0].product_id,
        quantity=sum(item.quantity for item in order.items),
        subtotal_price=subtotal_price,
        coupon_code=coupon.code if coupon else None,
        discount_amount=discount_amount,
        total_price=total_price,
        payment_method="Not selected yet",
        payment_status="Waiting for customer payment choice",
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

        db.add(
            OrderItem(
                order_id=new_order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=product.price,
                total_price=product.price * quantity,
            )
        )

    if coupon:
        coupon.used_count += 1

    db.commit()
    db.refresh(new_order)

    return new_order


@router.get("/", response_model=list[OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    return db.query(Order).order_by(Order.created_at.desc()).all()


@router.get("/{order_id}", response_model=OrderResponse)
def get_order(order_id: int, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    return order


@router.patch("/{order_id}/status")
def update_order_status(order_id: int, status: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.status = status
    db.commit()
    db.refresh(order)

    return {
        "message": "Order status updated successfully",
        "order_id": order.id,
        "status": order.status,
    }


@router.patch("/{order_id}/payment")
def update_order_payment(order_id: int, payment: OrderPaymentUpdate, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.id == order_id).first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")

    order.payment_method = payment.payment_method
    order.payment_status = payment.payment_status
    order.payment_details = payment.payment_details

    db.commit()
    db.refresh(order)

    return {
        "message": "Payment details updated successfully",
        "order_id": order.id,
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "payment_details": order.payment_details,
    }