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

class OrderPaymentUpdate(BaseModel):
    payment_method: str
    payment_status: str
    payment_details: Optional[str] = None


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: float
    total_price: float

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    customer_name: str
    phone: str
    email: Optional[str] = None
    governorate: str
    address: str
    note: Optional[str] = None
    coupon_code: Optional[str] = None

    # New multi-product order
    items: list[OrderItemCreate]

    # Old fields - مش هنستخدمهم في الأوردر الجديد
    # بس مش هنحطهم هنا عشان نجبر الفرونت يبعت items


class OrderResponse(BaseModel):
    id: int
    customer_name: str
    phone: str
    email: Optional[str] = None
    governorate: str
    address: str
    note: Optional[str] = None

    # Old compatibility fields
    product_id: Optional[int] = None
    quantity: int

    subtotal_price: float
    coupon_code: Optional[str] = None
    discount_amount: float
    total_price: float

    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    payment_details: Optional[str] = None

    status: str
    created_at: datetime

    # New order items
    items: list[OrderItemResponse] = []

    class Config:
        from_attributes = True


class CheckCouponItem(BaseModel):
    product_id: int
    quantity: int = 1


class CheckCouponRequest(BaseModel):
    coupon_code: str

    # New multi-products coupon check
    items: list[CheckCouponItem]


class CheckCouponResponse(BaseModel):
    coupon_code: Optional[str] = None
    subtotal_price: float
    discount_amount: float
    total_price: float
    message: str