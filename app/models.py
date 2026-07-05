from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    description = Column(Text, nullable=True)
    price = Column(Float, nullable=False)
    image_url = Column(String(500), nullable=True)
    category = Column(String(100), nullable=True)
    stock = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)

    orders = relationship("Order", back_populates="product")


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(Integer, primary_key=True, index=True)
    code = Column(String(50), unique=True, index=True, nullable=False)

    # discount_type يكون percent أو fixed
    discount_type = Column(String(20), nullable=False)
    discount_value = Column(Float, nullable=False)

    min_order_amount = Column(Float, default=0)
    usage_limit = Column(Integer, nullable=True)
    used_count = Column(Integer, default=0)

    is_active = Column(Boolean, default=True)
    expires_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)

    customer_name = Column(String(150), nullable=False)
    phone = Column(String(30), nullable=False)
    email = Column(String(150), nullable=True)

    governorate = Column(String(100), nullable=False)
    address = Column(Text, nullable=False)
    note = Column(Text, nullable=True)

    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    quantity = Column(Integer, default=1)

    subtotal_price = Column(Float, nullable=False, default=0)
    coupon_code = Column(String(50), nullable=True)
    discount_amount = Column(Float, nullable=False, default=0)
    total_price = Column(Float, nullable=False)

    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="orders")