from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class ProductBase(BaseModel):
    name: str
    description: Optional[str] = None
    price: float
    image_url: Optional[str] = None
    category: Optional[str] = None
    stock: int = 0
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    stock: Optional[int] = None
    is_active: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True


class CouponCreate(BaseModel):
    code: str
    discount_type: str
    discount_value: float
    min_order_amount: float = 0
    usage_limit: Optional[int] = None
    is_active: bool = True
    expires_at: Optional[datetime] = None


class CouponResponse(CouponCreate):
    id: int
    used_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    customer_name: str
    phone: str
    email: Optional[str] = None
    governorate: str
    address: str
    note: Optional[str] = None
    product_id: int
    quantity: int = 1
    coupon_code: Optional[str] = None


class OrderResponse(BaseModel):
    id: int
    customer_name: str
    phone: str
    email: Optional[str] = None
    governorate: str
    address: str
    note: Optional[str] = None
    product_id: int
    quantity: int

    subtotal_price: float
    coupon_code: Optional[str] = None
    discount_amount: float
    total_price: float

    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class CheckCouponRequest(BaseModel):
    product_id: int
    quantity: int = 1
    coupon_code: str


class CheckCouponResponse(BaseModel):
    coupon_code: str
    subtotal_price: float
    discount_amount: float
    total_price: float
    message: str