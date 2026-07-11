from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Coupon
from app.schemas import CouponCreate, CouponResponse, CouponUpdate

router = APIRouter(prefix="/coupons", tags=["Coupons"])


def validate_coupon_values(
    discount_type: str,
    discount_value: float,
    min_order_amount: float,
    usage_limit: int | None,
):
    if discount_type not in {"percent", "fixed"}:
        raise HTTPException(
            status_code=400,
            detail="discount_type must be percent or fixed",
        )

    if discount_value <= 0:
        raise HTTPException(
            status_code=400,
            detail="discount_value must be greater than 0",
        )

    if discount_type == "percent" and discount_value > 100:
        raise HTTPException(
            status_code=400,
            detail="Percent discount cannot be more than 100",
        )

    if min_order_amount < 0:
        raise HTTPException(
            status_code=400,
            detail="min_order_amount cannot be negative",
        )

    if usage_limit is not None and usage_limit <= 0:
        raise HTTPException(
            status_code=400,
            detail="usage_limit must be greater than 0",
        )


@router.get("/admin/all", response_model=list[CouponResponse])
def get_admin_coupons(db: Session = Depends(get_db)):
    return db.query(Coupon).order_by(Coupon.created_at.desc()).all()


# Kept for backward compatibility.
@router.get("/", response_model=list[CouponResponse])
def get_coupons(db: Session = Depends(get_db)):
    return db.query(Coupon).order_by(Coupon.created_at.desc()).all()


@router.post("/", response_model=CouponResponse)
def create_coupon(coupon: CouponCreate, db: Session = Depends(get_db)):
    code = coupon.code.strip().upper()

    if not code:
        raise HTTPException(status_code=400, detail="Coupon code is required")

    existing_coupon = db.query(Coupon).filter(Coupon.code == code).first()

    if existing_coupon:
        raise HTTPException(status_code=400, detail="Coupon already exists")

    validate_coupon_values(
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        min_order_amount=coupon.min_order_amount,
        usage_limit=coupon.usage_limit,
    )

    new_coupon = Coupon(
        code=code,
        discount_type=coupon.discount_type,
        discount_value=coupon.discount_value,
        min_order_amount=coupon.min_order_amount,
        usage_limit=coupon.usage_limit,
        is_active=coupon.is_active,
        expires_at=coupon.expires_at,
    )

    db.add(new_coupon)
    db.commit()
    db.refresh(new_coupon)

    return new_coupon


@router.patch("/{coupon_id}", response_model=CouponResponse)
def update_coupon(
    coupon_id: int,
    data: CouponUpdate,
    db: Session = Depends(get_db),
):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    update_data = data.model_dump(exclude_unset=True)

    if "code" in update_data:
        new_code = (update_data["code"] or "").strip().upper()

        if not new_code:
            raise HTTPException(status_code=400, detail="Coupon code is required")

        duplicate = (
            db.query(Coupon)
            .filter(Coupon.code == new_code, Coupon.id != coupon_id)
            .first()
        )

        if duplicate:
            raise HTTPException(status_code=400, detail="Coupon already exists")

        coupon.code = new_code

    new_discount_type = update_data.get(
        "discount_type",
        coupon.discount_type,
    )
    new_discount_value = update_data.get(
        "discount_value",
        coupon.discount_value,
    )
    new_min_order_amount = update_data.get(
        "min_order_amount",
        coupon.min_order_amount,
    )
    new_usage_limit = update_data.get(
        "usage_limit",
        coupon.usage_limit,
    )

    validate_coupon_values(
        discount_type=new_discount_type,
        discount_value=new_discount_value,
        min_order_amount=new_min_order_amount,
        usage_limit=new_usage_limit,
    )

    allowed_fields = [
        "discount_type",
        "discount_value",
        "min_order_amount",
        "usage_limit",
        "is_active",
        "expires_at",
    ]

    for field in allowed_fields:
        if field in update_data:
            setattr(coupon, field, update_data[field])

    db.commit()
    db.refresh(coupon)

    return coupon


@router.delete("/{coupon_id}")
def delete_coupon(coupon_id: int, db: Session = Depends(get_db)):
    coupon = db.query(Coupon).filter(Coupon.id == coupon_id).first()

    if not coupon:
        raise HTTPException(status_code=404, detail="Coupon not found")

    db.delete(coupon)
    db.commit()

    return {"message": "Coupon deleted successfully"}
