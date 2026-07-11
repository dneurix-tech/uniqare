import os
import tempfile
import unittest
from pathlib import Path

os.environ["DATABASE_URL"] = f"sqlite:///{Path(tempfile.gettempdir()) / 'uniqare_orders_delete_test.db'}"

from sqlalchemy import text

from app.database import SessionLocal, engine, ensure_schema_compatibility
from app.models import Order, OrderItem, Product
from app.routers.orders import delete_order


class DeleteOrderCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS order_items"))
            conn.execute(text("DROP TABLE IF EXISTS orders"))
            conn.execute(text("DROP TABLE IF EXISTS products"))

            conn.execute(
                text(
                    """
                    CREATE TABLE products (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(150) NOT NULL,
                        price FLOAT NOT NULL,
                        image_url VARCHAR(500),
                        category VARCHAR(100),
                        stock INTEGER DEFAULT 0,
                        is_active BOOLEAN DEFAULT 1
                    )
                    """
                )
            )
            ensure_schema_compatibility()
            conn.execute(
                text(
                    """
                    CREATE TABLE orders (
                        id INTEGER PRIMARY KEY,
                        customer_name VARCHAR(150) NOT NULL,
                        phone VARCHAR(30) NOT NULL,
                        email VARCHAR(150),
                        governorate VARCHAR(100) NOT NULL,
                        address TEXT NOT NULL,
                        note TEXT,
                        product_id INTEGER,
                        quantity INTEGER DEFAULT 1,
                        subtotal_price FLOAT NOT NULL DEFAULT 0,
                        coupon_code VARCHAR(50),
                        discount_amount FLOAT NOT NULL DEFAULT 0,
                        total_price FLOAT NOT NULL,
                        payment_method VARCHAR(100),
                        payment_status VARCHAR(150) DEFAULT 'Not selected yet',
                        payment_details TEXT,
                        status VARCHAR(50) DEFAULT 'pending',
                        created_at DATETIME
                    )
                    """
                )
            )
            conn.execute(
                text(
                    """
                    CREATE TABLE order_items (
                        id INTEGER PRIMARY KEY,
                        order_id INTEGER NOT NULL,
                        product_id INTEGER NOT NULL,
                        quantity INTEGER NOT NULL,
                        unit_price FLOAT NOT NULL,
                        total_price FLOAT NOT NULL,
                        FOREIGN KEY(order_id) REFERENCES orders(id),
                        FOREIGN KEY(product_id) REFERENCES products(id)
                    )
                    """
                )
            )

    @classmethod
    def tearDownClass(cls):
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS order_items"))
            conn.execute(text("DROP TABLE IF EXISTS orders"))
            conn.execute(text("DROP TABLE IF EXISTS products"))

    def setUp(self):
        self.db = SessionLocal()

    def tearDown(self):
        self.db.close()

    def test_delete_order_succeeds_when_product_table_is_older_schema(self):
        self.db.execute(
            text(
                "INSERT INTO products (id, name, price, image_url, category, stock, is_active) VALUES (:id, :name, :price, :image_url, :category, :stock, :is_active)"
            ),
            {
                "id": 1,
                "name": "Test Product",
                "price": 100.0,
                "image_url": None,
                "category": None,
                "stock": 5,
                "is_active": True,
            },
        )
        self.db.flush()

        order = Order(
            customer_name="Test Customer",
            phone="123456789",
            governorate="Cairo",
            address="Address",
            subtotal_price=100.0,
            total_price=100.0,
            status="pending",
        )
        self.db.add(order)
        self.db.flush()

        self.db.add(
            OrderItem(
                order_id=order.id,
                product_id=1,
                quantity=1,
                unit_price=100.0,
                total_price=100.0,
            )
        )
        self.db.commit()

        response = delete_order(order.id, self.db)

        self.assertEqual(response["message"], "Order deleted successfully")
        self.assertIsNone(self.db.query(Order).filter(Order.id == order.id).first())
        product_row = self.db.query(Product).filter(Product.id == 1).first()
        self.assertEqual(product_row.stock, 6)


if __name__ == "__main__":
    unittest.main()
