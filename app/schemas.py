from datetime import datetime
from typing import Optional

from pydantic import BaseModel, EmailStr, Field


class ProductBase(BaseModel):
    name: str
    short_description: Optional[str] = None
    long_description: Optional[str] = None
    price: float
    old_price: Optional[float] = None
    image_url: Optional[str] = None
    category: Optional[str] = None
    stock: int = 0
    is_active: bool = True
    is_bundle: bool = False


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
    is_bundle: Optional[bool] = None


class ProductResponse(ProductBase):
    id: int

    class Config:
        from_attributes = True


class BundleImageResponse(BaseModel):
    id: int
    image_url: str
    sort_order: int

    class Config:
        from_attributes = True


class BundleItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: str
    product_image: Optional[str] = None
    quantity: int
    product_stock: int


class BundleResponse(ProductResponse):
    configured_stock: int = 0
    
    images: list[BundleImageResponse] = Field(
        default_factory=list,
    )
    bundle_items: list[BundleItemResponse] = Field(
        default_factory=list,
    )


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
    payment_method: str = Field(min_length=1, max_length=100)
    payment_status: str = Field(min_length=1, max_length=150)
    payment_details: Optional[str] = Field(default=None, max_length=1000)


class OrderItemCreate(BaseModel):
    product_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=1000)


class OrderItemComponentResponse(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    product_image: Optional[str] = None
    quantity: int

    class Config:
        from_attributes = True


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    product_name: Optional[str] = None
    product_image: Optional[str] = None
    quantity: int
    unit_price: float
    total_price: float
    bundle_components: list[OrderItemComponentResponse] = Field(
        default_factory=list,
    )

    class Config:
        from_attributes = True


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=1, max_length=150)
    phone: str = Field(min_length=1, max_length=30)
    email: EmailStr
    governorate: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=2000)
    note: Optional[str] = Field(default=None, max_length=2000)
    coupon_code: Optional[str] = Field(default=None, max_length=50)
    items: list[OrderItemCreate] = Field(
        min_length=1,
        max_length=100,
    )


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
    product_id: int = Field(ge=1)
    quantity: int = Field(default=1, ge=1, le=1000)


class CheckCouponRequest(BaseModel):
    coupon_code: str = Field(min_length=1, max_length=50)
    items: list[CheckCouponItem] = Field(
        min_length=1,
        max_length=100,
    )


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

    items: Optional[list[OrderItemCreate]] = None


class AnnouncementCreate(BaseModel):
    content: str = Field(min_length=1, max_length=500)
    is_active: bool = True


class AnnouncementUpdate(BaseModel):
    content: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None


class AnnouncementResponse(BaseModel):
    id: int
    content: str
    is_active: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class AdminTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
