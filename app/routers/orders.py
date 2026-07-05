from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Order, Product, Coupon
from app.schemas import OrderCreate, OrderResponse, CheckCouponRequest, CheckCouponResponse

router = APIRouter(
    prefix="/orders",
    tags=["Orders"]
)


def calculate_coupon_discount(
    db: Session,
    coupon_code: str | None,
    subtotal_price: float
):
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
            detail=f"Minimum order amount for this coupon is {coupon.min_order_amount}"
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


@router.post("/check-coupon", response_model=CheckCouponResponse)
def check_coupon(data: CheckCouponRequest, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == data.product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if data.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")

    subtotal_price = product.price * data.quantity

    coupon, discount_amount = calculate_coupon_discount(
        db=db,
        coupon_code=data.coupon_code,
        subtotal_price=subtotal_price
    )

    total_price = subtotal_price - discount_amount

    return {
        "coupon_code": coupon.code,
        "subtotal_price": subtotal_price,
        "discount_amount": discount_amount,
        "total_price": total_price,
        "message": "Coupon applied successfully"
    }


@router.post("/", response_model=OrderResponse)
def create_order(order: OrderCreate, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == order.product_id).first()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if product.is_active is False:
        raise HTTPException(status_code=400, detail="Product is not available")

    if order.quantity <= 0:
        raise HTTPException(status_code=400, detail="Quantity must be greater than 0")

    if product.stock < order.quantity:
        raise HTTPException(status_code=400, detail="Not enough stock")

    subtotal_price = product.price * order.quantity

    coupon, discount_amount = calculate_coupon_discount(
        db=db,
        coupon_code=order.coupon_code,
        subtotal_price=subtotal_price
    )

    total_price = subtotal_price - discount_amount

    new_order = Order(
        customer_name=order.customer_name,
        phone=order.phone,
        email=order.email,
        governorate=order.governorate,
        address=order.address,
        note=order.note,
        product_id=order.product_id,
        quantity=order.quantity,
        subtotal_price=subtotal_price,
        coupon_code=coupon.code if coupon else None,
        discount_amount=discount_amount,
        total_price=total_price,
        status="pending"
    )

    product.stock -= order.quantity

    if product.stock <= 0:
        product.stock = 0
        product.is_active = False

    if coupon:
        coupon.used_count += 1

    db.add(new_order)
    db.commit()
    db.refresh(new_order)

    return new_order


@router.get("/", response_model=list[OrderResponse])
def get_orders(db: Session = Depends(get_db)):
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    return orders


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
        "status": order.status
    }