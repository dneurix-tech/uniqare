from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    name = Column(
        String(150),
        nullable=False,
    )

    short_description = Column(
        Text,
        nullable=True,
    )

    long_description = Column(
        Text,
        nullable=True,
    )

    price = Column(
        Float,
        nullable=False,
    )

    old_price = Column(
        Float,
        nullable=True,
    )

    image_url = Column(
        String(500),
        nullable=True,
    )

    category = Column(
        String(100),
        nullable=True,
    )

    stock = Column(
        Integer,
        default=0,
        nullable=False,
    )

    is_active = Column(
        Boolean,
        default=True,
        nullable=False,
    )

    is_bundle = Column(
        Boolean,
        default=False,
        nullable=False,
    )

    orders = relationship(
        "Order",
        back_populates="product",
    )

    order_items = relationship(
        "OrderItem",
        back_populates="product",
    )

    images = relationship(
        "ProductImage",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductImage.sort_order",
    )

    bundle_items = relationship(
        "BundleItem",
        foreign_keys="BundleItem.bundle_product_id",
        back_populates="bundle_product",
        cascade="all, delete-orphan",
    )

    included_in_bundles = relationship(
        "BundleItem",
        foreign_keys="BundleItem.child_product_id",
        back_populates="child_product",
        passive_deletes=True,
    )


class ProductImage(Base):
    __tablename__ = "product_images"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    product_id = Column(
        Integer,
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    image_url = Column(
        String(500),
        nullable=False,
    )

    public_id = Column(
        String(300),
        nullable=True,
    )

    sort_order = Column(
        Integer,
        default=0,
        nullable=False,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

    product = relationship(
        "Product",
        back_populates="images",
    )


class BundleItem(Base):
    __tablename__ = "bundle_items"

    __table_args__ = (
        UniqueConstraint(
            "bundle_product_id",
            "child_product_id",
            name="uq_bundle_child_product",
        ),
    )

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    bundle_product_id = Column(
        Integer,
        ForeignKey(
            "products.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    child_product_id = Column(
        Integer,
        ForeignKey(
            "products.id",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )

    quantity = Column(
        Integer,
        nullable=False,
        default=1,
    )

    bundle_product = relationship(
        "Product",
        foreign_keys=[bundle_product_id],
        back_populates="bundle_items",
    )

    child_product = relationship(
        "Product",
        foreign_keys=[child_product_id],
        back_populates="included_in_bundles",
    )


class Coupon(Base):
    __tablename__ = "coupons"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    code = Column(
        String(50),
        unique=True,
        index=True,
        nullable=False,
    )

    discount_type = Column(
        String(20),
        nullable=False,
    )

    discount_value = Column(
        Float,
        nullable=False,
    )

    min_order_amount = Column(
        Float,
        default=0,
    )

    usage_limit = Column(
        Integer,
        nullable=True,
    )

    used_count = Column(
        Integer,
        default=0,
    )

    is_active = Column(
        Boolean,
        default=True,
    )

    expires_at = Column(
        DateTime,
        nullable=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class Order(Base):
    __tablename__ = "orders"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    customer_name = Column(
        String(150),
        nullable=False,
    )

    phone = Column(
        String(30),
        nullable=False,
    )

    email = Column(
        String(150),
        nullable=True,
    )

    governorate = Column(
        String(100),
        nullable=False,
    )

    address = Column(
        Text,
        nullable=False,
    )

    note = Column(
        Text,
        nullable=True,
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=True,
    )

    quantity = Column(
        Integer,
        default=1,
    )

    subtotal_price = Column(
        Float,
        nullable=False,
        default=0,
    )

    coupon_code = Column(
        String(50),
        nullable=True,
    )

    coupon_discount_type = Column(
        String(20),
        nullable=True,
    )

    coupon_discount_value = Column(
        Float,
        nullable=True,
    )

    discount_amount = Column(
        Float,
        nullable=False,
        default=0,
    )

    total_price = Column(
        Float,
        nullable=False,
    )

    payment_method = Column(
        String(100),
        nullable=True,
    )

    payment_status = Column(
        String(150),
        default="Not selected yet",
    )

    payment_details = Column(
        Text,
        nullable=True,
    )

    status = Column(
        String(50),
        default="pending",
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    product = relationship(
        "Product",
        back_populates="orders",
    )

    items = relationship(
        "OrderItem",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderItem(Base):
    __tablename__ = "order_items"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    order_id = Column(
        Integer,
        ForeignKey(
            "orders.id",
            ondelete="CASCADE",
        ),
        nullable=False,
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    unit_price = Column(
        Float,
        nullable=False,
    )

    total_price = Column(
        Float,
        nullable=False,
    )

    order = relationship(
        "Order",
        back_populates="items",
    )

    product = relationship(
        "Product",
        back_populates="order_items",
    )

    components = relationship(
        "OrderItemComponent",
        back_populates="order_item",
        cascade="all, delete-orphan",
    )


class OrderItemComponent(Base):
    __tablename__ = "order_item_components"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    order_item_id = Column(
        Integer,
        ForeignKey(
            "order_items.id",
            ondelete="CASCADE",
        ),
        nullable=False,
        index=True,
    )

    product_id = Column(
        Integer,
        ForeignKey("products.id"),
        nullable=False,
        index=True,
    )

    quantity = Column(
        Integer,
        nullable=False,
    )

    order_item = relationship(
        "OrderItem",
        back_populates="components",
    )

    product = relationship(
        "Product",
    )


class Review(Base):
    __tablename__ = "reviews"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    customer_name = Column(
        String(150),
        nullable=True,
    )

    description = Column(
        Text,
        nullable=True,
    )

    image_url = Column(
        String(500),
        nullable=True,
    )

    rating = Column(
        Integer,
        default=5,
    )

    is_active = Column(
        Boolean,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )


class Announcement(Base):
    __tablename__ = "announcements"

    id = Column(
        Integer,
        primary_key=True,
        index=True,
    )

    content = Column(
        Text,
        nullable=False,
    )

    is_active = Column(
        Boolean,
        default=True,
    )

    created_at = Column(
        DateTime,
        default=datetime.utcnow,
    )

    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
    )
