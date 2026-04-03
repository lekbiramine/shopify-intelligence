from db.connection import get_connection
from config.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)


def seed_data() -> None:
    """
    Inserts fake data into the database for testing purposes.
    Only use against development stores.
    """
    logger.info("Seeding database with test data...")

    conn = get_connection()
    conn.autocommit = True

    try:
        with conn.cursor() as cursor:

            # Products
            cursor.execute("""
                INSERT INTO products (id, title, vendor, product_type, status, created_at, updated_at)
                VALUES
                    (1001, 'Test Shirt', 'VendorA', 'Apparel', 'active', NOW(), NOW()),
                    (1002, 'Test Shoes', 'VendorB', 'Footwear', 'active', NOW(), NOW()),
                    (1003, 'Test Hat', 'VendorA', 'Apparel', 'active', NOW(), NOW())
                ON CONFLICT (id) DO NOTHING;
            """)

            # Variants
            cursor.execute("""
                INSERT INTO variants (id, product_id, title, sku, price, inventory_quantity, updated_at)
                VALUES
                    (2001, 1001, 'Small', 'SHIRT-S', 29.99, 3, NOW()),
                    (2002, 1001, 'Large', 'SHIRT-L', 29.99, 0, NOW()),
                    (2003, 1002, 'Size 42', 'SHOE-42', 89.99, 1, NOW()),
                    (2004, 1003, 'One Size', 'HAT-OS', 19.99, 8, NOW())
                ON CONFLICT (id) DO NOTHING;
            """)

            # Inventory
            cursor.execute("""
                INSERT INTO inventory (variant_id, inventory_item_id, location_id, available)
                VALUES
                    (2001, 3001, 4001, 3),
                    (2002, 3002, 4001, 0),
                    (2003, 3003, 4001, 1),
                    (2004, 3004, 4001, 8)
                ON CONFLICT (variant_id, location_id) DO NOTHING;
            """)

            # Customers
            cursor.execute("""
                INSERT INTO customers (id, email, first_name, last_name, orders_count, total_spent, created_at, updated_at)
                VALUES
                    (5001, 'alice@example.com', 'Alice', 'Smith', 5, 450.00, NOW() - INTERVAL '200 days', NOW()),
                    (5002, 'bob@example.com', 'Bob', 'Jones', 1, 89.99, NOW() - INTERVAL '120 days', NOW()),
                    (5003, 'carol@example.com', 'Carol', 'White', 3, 220.00, NOW() - INTERVAL '10 days', NOW()),
                    (5004, 'dave@example.com', 'Dave', 'Brown', 1, 29.99, NOW() - INTERVAL '95 days', NOW())
                ON CONFLICT (id) DO NOTHING;
            """)

            # Orders
            cursor.execute("""
                INSERT INTO orders (id, customer_id, email, total_price, subtotal_price, total_discounts, financial_status, fulfillment_status, created_at, updated_at)
                VALUES
                    (6001, 5001, 'alice@example.com', 89.99, 89.99, 0.00, 'paid', 'fulfilled', NOW() - INTERVAL '200 days', NOW()),
                    (6002, 5001, 'alice@example.com', 29.99, 29.99, 0.00, 'paid', 'fulfilled', NOW() - INTERVAL '10 days', NOW()),
                    (6003, 5002, 'bob@example.com', 89.99, 89.99, 0.00, 'refunded', NULL, NOW() - INTERVAL '120 days', NOW()),
                    (6004, 5003, 'carol@example.com', 29.99, 39.99, 10.00, 'paid', 'fulfilled', NOW() - INTERVAL '10 days', NOW()),
                    (6005, 5004, 'dave@example.com', 29.99, 29.99, 0.00, 'paid', 'fulfilled', NOW() - INTERVAL '95 days', NOW())
                ON CONFLICT (id) DO NOTHING;
            """)

            # Order Items
            cursor.execute("""
                INSERT INTO order_items (id, order_id, product_id, variant_id, title, quantity, price, total_discount, vendor)
                VALUES
                    (7001, 6001, 1002, 2003, 'Test Shoes', 1, 89.99, 0.00, 'VendorB'),
                    (7002, 6002, 1001, 2001, 'Test Shirt', 1, 29.99, 0.00, 'VendorA'),
                    (7003, 6003, 1002, 2003, 'Test Shoes', 1, 89.99, 0.00, 'VendorB'),
                    (7004, 6004, 1001, 2001, 'Test Shirt', 1, 29.99, 10.00, 'VendorA'),
                    (7005, 6005, 1001, 2002, 'Test Shirt', 1, 29.99, 0.00, 'VendorA')
                ON CONFLICT (id) DO NOTHING;
            """)

        logger.info("Seed data inserted successfully.")

    except Exception as e:
        logger.error(f"Failed to seed data: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    seed_data()