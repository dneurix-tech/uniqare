from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Coupon
from app.schemas import CouponCreate, CouponResponse

router = APIRouter(
    prefix="/coupons",
    tags=["Coupons"]
)


@router.post("/", response_model=CouponResponse)
def create_coupon(coupon: CouponCreate, db: Session = Depends(get_db)):
    code = coupon.code.strip().upper()

    existing_coupon = db.query(Coupon).filter(Coupon.code == code).first()

    if existing_coupon:
        raise HTTPException(status_code=400, detail="Coupon already exists")

    if coupon.discount_type not in ["percent", "fixed"]:
        raise HTTPException(
            status_code=400,
            detail="discount_type must be percent or fixed"
        )

    if coupon.discount_value <= 0:
        raise HTTPException(
            status_code=400,
            detail="discount_value must be greater than 0"
        )

    if coupon.discount_type == "percent" and coupon.discount_value > 100:
        raise HTTPException(
            status_code=400,
            detail="Percent discount cannot be more than 100"
        )

    new_coupon = Coupon(
        code=code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        min_order_amount=coupon.min_order_amount,
        usage_limit=coupon.usage_limit,
        is_active=coupon.is_active,
        expires_at=coupon.expires_at
    )

    db.add(new_coupon)
    db.commit()
    db.refresh(new_coupon)

    return new_coupon


@router.get("/", response_model=list[CouponResponse])
def get_coupons(db: Session = Depends(get_db)):
    return db.query(Coupon).order_by(Coupon.id.desc()).all()


@router.delete("/{coupon_id}")
def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    db.delete(coupon)
    db.commit()

    return {"message": "Coupon deleted successfully"}