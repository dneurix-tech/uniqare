import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker


load_dotenv()

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite:///./app.db",
)

engine_kwargs = {}

if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {
        "check_same_thread": False,
    }

engine = create_engine(
    DATABASE_URL,
    **engine_kwargs,
)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# Register all models before create_all.
import app.models  # noqa: E402,F401


def add_column_if_missing(
    conn,
    table_name,
    existing_columns,
    column_name,
    column_sql,
):
    if column_name in existing_columns:
        return

    conn.execute(
        text(
            f"ALTER TABLE {table_name} "
            f"ADD COLUMN {column_sql}"
        )
    )

    existing_columns.add(column_name)


def ensure_schema_compatibility():
    """
    Create missing tables and safely add newer columns to
    existing SQLite or PostgreSQL databases.
    """

    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    with engine.begin() as conn:
        if "products" in table_names:
            existing_columns = {
                column["name"]
                for column in inspector.get_columns("products")
            }

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "short_description",
                "short_description TEXT",
            )

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "long_description",
                "long_description TEXT",
            )

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "old_price",
                "old_price FLOAT",
            )

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "category",
                "category VARCHAR(100)",
            )

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "stock",
                "stock INTEGER DEFAULT 0",
            )

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "is_active",
                "is_active BOOLEAN DEFAULT TRUE",
            )

            add_column_if_missing(
                conn,
                "products",
                existing_columns,
                "is_bundle",
                "is_bundle BOOLEAN DEFAULT FALSE",
            )

            conn.execute(
                text(
                    """
                    UPDATE products
                    SET is_bundle = FALSE
                    WHERE is_bundle IS NULL
                    """
                )
            )

        if "orders" in table_names:
            existing_columns = {
                column["name"]
                for column in inspector.get_columns("orders")
            }

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "subtotal_price",
                "subtotal_price FLOAT DEFAULT 0",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "coupon_code",
                "coupon_code VARCHAR(50)",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "coupon_discount_type",
                "coupon_discount_type VARCHAR(20)",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "coupon_discount_value",
                "coupon_discount_value FLOAT",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "discount_amount",
                "discount_amount FLOAT DEFAULT 0",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "payment_method",
                "payment_method VARCHAR(100)",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "payment_status",
                "payment_status VARCHAR(150)",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "payment_details",
                "payment_details TEXT",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "status",
                "status VARCHAR(50) DEFAULT 'pending'",
            )

            add_column_if_missing(
                conn,
                "orders",
                existing_columns,
                "created_at",
                "created_at TIMESTAMP",
            )

        # Create any newly added tables such as bundle tables.
        Base.metadata.create_all(bind=engine)

        refreshed_inspector = inspect(engine)
        refreshed_tables = refreshed_inspector.get_table_names()

        if (
            "orders" in refreshed_tables
            and "order_items" in refreshed_tables
            and "products" in refreshed_tables
        ):
            conn.execute(
                text(
                    """
                    INSERT INTO order_items (
                        order_id,
                        product_id,
                        quantity,
                        unit_price,
                        total_price
                    )
                    SELECT
                        o.id,
                        o.product_id,
                        COALESCE(o.quantity, 1),
                        COALESCE(p.price, 0),
                        COALESCE(p.price, 0)
                            * COALESCE(o.quantity, 1)
                    FROM orders o
                    JOIN products p
                        ON p.id = o.product_id
                    WHERE o.product_id IS NOT NULL
                    AND NOT EXISTS (
                        SELECT 1
                        FROM order_items oi
                        WHERE oi.order_id = o.id
                    )
                    """
                )
            )


ensure_schema_compatibility()


def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
