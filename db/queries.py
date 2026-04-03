from db.connection import get_cursor
from config.logging_config import get_logger

logger = get_logger(__name__)


# ─── Products ───────────────────────────────────────────────────────────────

def upsert_product(product: dict) -> None:
    sql = """
        INSERT INTO products (id, title, vendor, product_type, status, created_at, updated_at)
        VALUES (%(id)s, %(title)s, %(vendor)s, %(product_type)s, %(status)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            vendor = EXCLUDED.vendor,
            product_type = EXCLUDED.product_type,
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, product)
    logger.debug(f"Upserted product {product['id']}")


# ─── Variants ───────────────────────────────────────────────────────────────

def upsert_variant(variant: dict) -> None:
    sql = """
        INSERT INTO variants (id, product_id, title, sku, price, inventory_quantity, updated_at)
        VALUES (%(id)s, %(product_id)s, %(title)s, %(sku)s, %(price)s, %(inventory_quantity)s, %(updated_at)s)
        ON CONFLICT (id) DO UPDATE SET
            title = EXCLUDED.title,
            sku = EXCLUDED.sku,
            price = EXCLUDED.price,
            inventory_quantity = EXCLUDED.inventory_quantity,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, variant)
    logger.debug(f"Upserted variant {variant['id']}")


# ─── Customers ──────────────────────────────────────────────────────────────

def upsert_customer(customer: dict) -> None:
    sql = """
        INSERT INTO customers (id, email, first_name, last_name, orders_count, total_spent, created_at, updated_at)
        VALUES (%(id)s, %(email)s, %(first_name)s, %(last_name)s, %(orders_count)s, %(total_spent)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO UPDATE SET
            email = EXCLUDED.email,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            orders_count = EXCLUDED.orders_count,
            total_spent = EXCLUDED.total_spent,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, customer)
    logger.debug(f"Upserted customer {customer['id']}")


# ─── Orders ─────────────────────────────────────────────────────────────────

def upsert_order(order: dict) -> None:
    sql = """
        INSERT INTO orders (id, customer_id, email, total_price, subtotal_price, total_discounts, financial_status, fulfillment_status, created_at, updated_at)
        VALUES (%(id)s, %(customer_id)s, %(email)s, %(total_price)s, %(subtotal_price)s, %(total_discounts)s, %(financial_status)s, %(fulfillment_status)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (id) DO UPDATE SET
            financial_status = EXCLUDED.financial_status,
            fulfillment_status = EXCLUDED.fulfillment_status,
            total_price = EXCLUDED.total_price,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, order)
    logger.debug(f"Upserted order {order['id']}")


# ─── Order Items ─────────────────────────────────────────────────────────────

def upsert_order_item(item: dict) -> None:
    sql = """
        INSERT INTO order_items (id, order_id, product_id, variant_id, title, quantity, price, total_discount, vendor)
        VALUES (%(id)s, %(order_id)s, %(product_id)s, %(variant_id)s, %(title)s, %(quantity)s, %(price)s, %(total_discount)s, %(vendor)s)
        ON CONFLICT (id) DO NOTHING;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, item)
    logger.debug(f"Upserted order item {item['id']}")


# ─── Inventory ───────────────────────────────────────────────────────────────

def upsert_inventory(inventory: dict) -> None:
    sql = """
        INSERT INTO inventory (variant_id, inventory_item_id, location_id, available)
        VALUES (%(variant_id)s, %(inventory_item_id)s, %(location_id)s, %(available)s)
        ON CONFLICT (variant_id, location_id) DO UPDATE SET
            available = EXCLUDED.available,
            synced_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, inventory)
    logger.debug(f"Upserted inventory for variant {inventory['variant_id']}")