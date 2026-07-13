from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class ProductBase(BaseModel):
    name: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None

    # Current selling price.
    price: float

    # Optional previous price displayed with a line through it.
    old_price: Optional[float] = None

    image_url: Optional[str] = None
    category: Optional[str] = None
    stock: int = 0
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    price: Optional[float] = None
    old_price: Optional[float] = None
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
    discount_type: str = "percent"
    discount_value: float
    min_order_amount: float = 0
    usage_limit: Optional[int] = None
    is_active: bool = True
    expires_at: Optional[datetime] = None


class CouponUpdate(BaseModel):
    code: Optional[str] = None
    discount_type: Optional[str] = None
    discount_value: Optional[float] = None
    min_order_amount: Optional[float] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None
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
    product_name: Optional[str] = None
    product_image: Optional[str] = None
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
    items: list[OrderItemCreate]


class OrderResponse(BaseModel):
    id: int
    customer_name: str
    phone: str
    email: Optional[str] = None
    governorate: str
    address: str
    note: Optional[str] = None

    product_id: Optional[int] = None
    quantity: int

    subtotal_price: float
    coupon_code: Optional[str] = None
    coupon_discount_type: Optional[str] = None
    coupon_discount_value: Optional[float] = None
    discount_amount: float
    total_price: float

    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    payment_details: Optional[str] = None

    status: str
    created_at: datetime

    items: list[OrderItemResponse] = Field(
        default_factory=list,
    )

    class Config:
        from_attributes = True


class CheckCouponItem(BaseModel):
    product_id: int
    quantity: int = 1


class CheckCouponRequest(BaseModel):
    coupon_code: str
    items: list[CheckCouponItem]


class CheckCouponResponse(BaseModel):
    coupon_code: Optional[str] = None
    subtotal_price: float
    discount_amount: float
    total_price: float
    message: str


class OrderAdminUpdate(BaseModel):
    customer_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    governorate: Optional[str] = None
    address: Optional[str] = None
    note: Optional[str] = None

    status: Optional[str] = None

    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    payment_details: Optional[str] = None

    # When supplied, this list fully replaces
    # the current products in the order.
    items: Optional[list[OrderItemCreate]] = None