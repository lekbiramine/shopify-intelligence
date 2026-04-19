from db.connection import get_cursor
from config.logging_config import get_logger

logger = get_logger(__name__)


# ─── Stores ─────────────────────────────────────────────────────────────────

def upsert_store_connection(
    shop_domain: str,
    access_token: str,
    scope: str | None = None,
    contact_email: str | None = None,
) -> None:
    sql = """
        INSERT INTO stores (shop_domain, access_token, scope, contact_email, is_active, connected_at, updated_at)
        VALUES (%s, %s, %s, %s, TRUE, NOW(), NOW())
        ON CONFLICT (shop_domain) DO UPDATE SET
            access_token = EXCLUDED.access_token,
            scope = EXCLUDED.scope,
            contact_email = COALESCE(EXCLUDED.contact_email, stores.contact_email),
            is_active = TRUE,
            connected_at = NOW(),
            updated_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (shop_domain, access_token, scope, contact_email))
    logger.info(f"Connected store saved: {shop_domain}")


def upsert_store_contact_email(shop_domain: str, contact_email: str) -> None:
    """
    Persist contact email even before OAuth callback completes.
    This avoids losing the email when session cookies are missing on callback.
    """
    sql = """
        INSERT INTO stores (shop_domain, contact_email, is_active, updated_at)
        VALUES (%s, %s, TRUE, NOW())
        ON CONFLICT (shop_domain) DO UPDATE SET
            contact_email = EXCLUDED.contact_email,
            updated_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (shop_domain, contact_email))


def get_store_by_domain(shop_domain: str) -> dict | None:
    sql = """
        SELECT id,
               shop_domain,
               access_token,
               scope,
               contact_email,
               is_active,
               last_report_sent_at,
               report_schedule_time,
               report_schedule_active,
               report_timezone,
               connected_at
        FROM stores
        WHERE shop_domain = %s
        LIMIT 1;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (shop_domain,))
        row = cursor.fetchone()
        return dict(row) if row else None


def claim_report_send_slot(shop_domain: str) -> bool:
    """
    Atomically enforce:
    - store must be active
    - at most 1 report send per 24 hours
    """
    sql = """
        UPDATE stores
        SET last_report_sent_at = NOW(),
            updated_at = NOW()
        WHERE shop_domain = %s
          AND is_active = TRUE
          AND (
            last_report_sent_at IS NULL
            OR last_report_sent_at < (NOW() - INTERVAL '24 hours')
          )
        RETURNING id;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (shop_domain,))
        row = cursor.fetchone()
        return bool(row)


def set_store_schedule(shop_domain: str, daily_time: str, active: bool = True) -> None:
    sql = """
        UPDATE stores
        SET report_schedule_time = %s,
            report_schedule_active = %s,
            updated_at = NOW()
        WHERE shop_domain = %s;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (daily_time, active, shop_domain))


def update_store_timezone(shop_domain: str, report_timezone: str) -> None:
    sql = """
        UPDATE stores
        SET report_timezone = %s,
            updated_at = NOW()
        WHERE shop_domain = %s;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (report_timezone, shop_domain))


def get_active_scheduled_stores() -> list[dict]:
    sql = """
        SELECT shop_domain,
               access_token,
               contact_email,
               report_schedule_time,
               report_timezone,
               last_report_sent_at
        FROM stores
        WHERE is_active = TRUE
          AND report_schedule_active = TRUE
          AND report_schedule_time IS NOT NULL
          AND contact_email IS NOT NULL;
    """
    with get_cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def update_store_contact_email(shop_domain: str, contact_email: str) -> None:
    sql = """
        UPDATE stores
        SET contact_email = %s,
            updated_at = NOW()
        WHERE shop_domain = %s;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (contact_email, shop_domain))
    logger.info(f"Updated contact email for store: {shop_domain}")


# ─── Products ───────────────────────────────────────────────────────────────

def upsert_product(product: dict, cursor=None) -> None:
    sql = """
        INSERT INTO products (store_id, id, title, vendor, product_type, status, created_at, updated_at)
        VALUES (%(store_id)s, %(id)s, %(title)s, %(vendor)s, %(product_type)s, %(status)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (store_id, id) DO UPDATE SET
            title = EXCLUDED.title,
            vendor = EXCLUDED.vendor,
            product_type = EXCLUDED.product_type,
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    if cursor is not None:
        cursor.execute(sql, product)
    else:
        with get_cursor(commit=True) as _cursor:
            _cursor.execute(sql, product)
    logger.debug(f"Upserted product {product['id']} (store_id={product.get('store_id')})")


# ─── Variants ───────────────────────────────────────────────────────────────

def upsert_variant(variant: dict, cursor=None) -> None:
    sql = """
        INSERT INTO variants (store_id, id, product_id, title, sku, price, inventory_quantity, updated_at)
        VALUES (%(store_id)s, %(id)s, %(product_id)s, %(title)s, %(sku)s, %(price)s, %(inventory_quantity)s, %(updated_at)s)
        ON CONFLICT (store_id, id) DO UPDATE SET
            title = EXCLUDED.title,
            sku = EXCLUDED.sku,
            price = EXCLUDED.price,
            inventory_quantity = EXCLUDED.inventory_quantity,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    if cursor is not None:
        cursor.execute(sql, variant)
    else:
        with get_cursor(commit=True) as _cursor:
            _cursor.execute(sql, variant)
    logger.debug(f"Upserted variant {variant['id']} (store_id={variant.get('store_id')})")


# ─── Customers ──────────────────────────────────────────────────────────────

def upsert_customer(customer: dict, cursor=None) -> None:
    sql = """
        INSERT INTO customers (store_id, id, email, first_name, last_name, orders_count, total_spent, created_at, updated_at)
        VALUES (%(store_id)s, %(id)s, %(email)s, %(first_name)s, %(last_name)s, %(orders_count)s, %(total_spent)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (store_id, id) DO UPDATE SET
            email = EXCLUDED.email,
            first_name = EXCLUDED.first_name,
            last_name = EXCLUDED.last_name,
            orders_count = EXCLUDED.orders_count,
            total_spent = EXCLUDED.total_spent,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    if cursor is not None:
        cursor.execute(sql, customer)
    else:
        with get_cursor(commit=True) as _cursor:
            _cursor.execute(sql, customer)
    logger.debug(f"Upserted customer {customer['id']} (store_id={customer.get('store_id')})")


# ─── Orders ─────────────────────────────────────────────────────────────────

def upsert_order(order: dict, cursor=None) -> None:
    sql = """
        INSERT INTO orders (store_id, id, customer_id, email, total_price, subtotal_price, total_discounts, financial_status, fulfillment_status, created_at, updated_at)
        VALUES (%(store_id)s, %(id)s, %(customer_id)s, %(email)s, %(total_price)s, %(subtotal_price)s, %(total_discounts)s, %(financial_status)s, %(fulfillment_status)s, %(created_at)s, %(updated_at)s)
        ON CONFLICT (store_id, id) DO UPDATE SET
            financial_status = EXCLUDED.financial_status,
            fulfillment_status = EXCLUDED.fulfillment_status,
            total_price = EXCLUDED.total_price,
            updated_at = EXCLUDED.updated_at,
            synced_at = NOW();
    """
    if cursor is not None:
        cursor.execute(sql, order)
    else:
        with get_cursor(commit=True) as _cursor:
            _cursor.execute(sql, order)
    logger.debug(f"Upserted order {order['id']} (store_id={order.get('store_id')})")


# ─── Order Items ─────────────────────────────────────────────────────────────

def upsert_order_item(item: dict, cursor=None) -> None:
    sql = """
        INSERT INTO order_items (store_id, id, order_id, product_id, variant_id, title, quantity, price, total_discount, vendor)
        VALUES (%(store_id)s, %(id)s, %(order_id)s, %(product_id)s, %(variant_id)s, %(title)s, %(quantity)s, %(price)s, %(total_discount)s, %(vendor)s)
        ON CONFLICT (store_id, id) DO NOTHING;
    """
    if cursor is not None:
        cursor.execute(sql, item)
    else:
        with get_cursor(commit=True) as _cursor:
            _cursor.execute(sql, item)
    logger.debug(f"Upserted order item {item['id']} (store_id={item.get('store_id')})")


# ─── Inventory ───────────────────────────────────────────────────────────────

def upsert_inventory(inventory: dict, cursor=None) -> None:
    sql = """
        INSERT INTO inventory (store_id, variant_id, inventory_item_id, location_id, available)
        VALUES (%(store_id)s, %(variant_id)s, %(inventory_item_id)s, %(location_id)s, %(available)s)
        ON CONFLICT (store_id, variant_id, location_id) DO UPDATE SET
            available = EXCLUDED.available,
            synced_at = NOW();
    """
    if cursor is not None:
        cursor.execute(sql, inventory)
    else:
        with get_cursor(commit=True) as _cursor:
            _cursor.execute(sql, inventory)
    logger.debug(f"Upserted inventory for variant {inventory['variant_id']} (store_id={inventory.get('store_id')})")