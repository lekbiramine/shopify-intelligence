from db.connection import get_cursor
from config.logging_config import get_logger

logger = get_logger(__name__)


def _require_store_id(store_id: int) -> int:
    if store_id is None:
        raise ValueError("store_id is required")
    store_id_int = int(store_id)
    if store_id_int <= 0:
        raise ValueError("store_id must be a positive integer")
    return store_id_int


# ─── Stores ─────────────────────────────────────────────────────────────────

def upsert_store_connection(
    shop_domain: str,
    access_token: str,
    refresh_token: str | None = None,
    access_token_expires_at=None,
    scope: str | None = None,
    contact_email: str | None = None,
    display_name: str | None = None,
    referral_code_used: str | None = None,
    referral_code_id: int | None = None,
) -> None:
    sql = """
        INSERT INTO stores (
            shop_domain,
            display_name,
            access_token,
            refresh_token,
            access_token_expires_at,
            scope,
            contact_email,
            referral_code_used,
            referral_code_id,
            is_active,
            connected_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE, NOW(), NOW())
        ON CONFLICT (shop_domain) DO UPDATE SET
            display_name = COALESCE(NULLIF(EXCLUDED.display_name, ''), stores.display_name),
            access_token = EXCLUDED.access_token,
            refresh_token = COALESCE(EXCLUDED.refresh_token, stores.refresh_token),
            access_token_expires_at = COALESCE(EXCLUDED.access_token_expires_at, stores.access_token_expires_at),
            scope = EXCLUDED.scope,
            contact_email = COALESCE(EXCLUDED.contact_email, stores.contact_email),
            referral_code_used = COALESCE(EXCLUDED.referral_code_used, stores.referral_code_used),
            referral_code_id = COALESCE(EXCLUDED.referral_code_id, stores.referral_code_id),
            is_active = TRUE,
            connected_at = NOW(),
            updated_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            sql,
            (
                shop_domain,
                display_name,
                access_token,
                refresh_token,
                access_token_expires_at,
                scope,
                contact_email,
                referral_code_used,
                referral_code_id,
            ),
        )
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
               refresh_token,
               access_token_expires_at,
               scope,
               contact_email,
               referral_code_used,
               referral_code_id,
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


def set_store_referral_code(shop_domain: str, referral_code: str | None) -> None:
    sql = """
        INSERT INTO stores (shop_domain, referral_code_used, is_active, updated_at)
        VALUES (%s, %s, TRUE, NOW())
        ON CONFLICT (shop_domain) DO UPDATE SET
            referral_code_used = EXCLUDED.referral_code_used,
            updated_at = NOW();
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (shop_domain, referral_code))


def create_referral_code(
    code: str,
    partner_name: str,
    discount_percent: float = 20.0,
) -> dict:
    sql = """
        INSERT INTO referral_codes (code, partner_name, discount_percent, is_active, created_at, updated_at)
        VALUES (%s, %s, %s, TRUE, NOW(), NOW())
        RETURNING id, code, partner_name, discount_percent, is_active, created_at;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (code, partner_name, discount_percent))
        row = cursor.fetchone()
        return dict(row)


def deactivate_referral_code(code: str) -> bool:
    sql = """
        UPDATE referral_codes
        SET is_active = FALSE,
            updated_at = NOW()
        WHERE code = %s
        RETURNING id;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (code,))
        row = cursor.fetchone()
        return bool(row)


def get_active_referral_code_by_code(code: str) -> dict | None:
    sql = """
        SELECT id, code, partner_name, discount_percent, is_active, created_at
        FROM referral_codes
        WHERE code = %s AND is_active = TRUE
        LIMIT 1;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (code,))
        row = cursor.fetchone()
        return dict(row) if row else None


def attach_store_referral(shop_domain: str, referral_code_id: int, referral_code: str) -> bool:
    sql = """
        WITH updated_store AS (
            UPDATE stores
            SET referral_code_id = %s,
                referral_code_used = %s,
                updated_at = NOW()
            WHERE shop_domain = %s
            RETURNING id
        )
        INSERT INTO store_referrals (store_id, referral_code_id, installed_at, source)
        SELECT id, %s, NOW(), 'oauth_install'
        FROM updated_store
        ON CONFLICT (store_id) DO UPDATE SET
            referral_code_id = EXCLUDED.referral_code_id,
            installed_at = EXCLUDED.installed_at,
            source = EXCLUDED.source
        RETURNING store_id;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (referral_code_id, referral_code, shop_domain, referral_code_id))
        row = cursor.fetchone()
        return bool(row)


def list_referral_codes_with_stats() -> list[dict]:
    sql = """
        SELECT rc.id,
               rc.code,
               rc.partner_name,
               rc.discount_percent,
               rc.is_active,
               rc.created_at,
               COUNT(sr.id) AS store_count
        FROM referral_codes rc
        LEFT JOIN store_referrals sr ON sr.referral_code_id = rc.id
        GROUP BY rc.id, rc.code, rc.partner_name, rc.discount_percent, rc.is_active, rc.created_at
        ORDER BY rc.created_at DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def get_referral_code_details(code: str) -> dict | None:
    details_sql = """
        SELECT id, code, partner_name, discount_percent, is_active, created_at, updated_at
        FROM referral_codes
        WHERE code = %s
        LIMIT 1;
    """
    stores_sql = """
        SELECT s.shop_domain, sr.installed_at
        FROM store_referrals sr
        JOIN stores s ON s.id = sr.store_id
        JOIN referral_codes rc ON rc.id = sr.referral_code_id
        WHERE rc.code = %s
        ORDER BY sr.installed_at DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(details_sql, (code,))
        details = cursor.fetchone()
        if not details:
            return None
        cursor.execute(stores_sql, (code,))
        stores = cursor.fetchall() or []
        payload = dict(details)
        payload["stores"] = [dict(s) for s in stores]
        payload["store_count"] = len(payload["stores"])
        return payload


def create_oauth_state(state_hash: str, shop_domain: str, ttl_seconds: int = 600) -> None:
    sql = """
        INSERT INTO oauth_states (state_hash, shop_domain, expires_at, consumed_at)
        VALUES (%s, %s, NOW() + (%s || ' seconds')::interval, NULL)
        ON CONFLICT (state_hash) DO UPDATE SET
            shop_domain = EXCLUDED.shop_domain,
            expires_at = EXCLUDED.expires_at,
            consumed_at = NULL;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (state_hash, shop_domain, ttl_seconds))


def consume_oauth_state(state_hash: str, shop_domain: str) -> bool:
    sql = """
        UPDATE oauth_states
        SET consumed_at = NOW()
        WHERE state_hash = %s
          AND shop_domain = %s
          AND consumed_at IS NULL
          AND expires_at >= NOW()
        RETURNING state_hash;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (state_hash, shop_domain))
        row = cursor.fetchone()
        return bool(row)


def update_store_auth_tokens(
    shop_domain: str,
    *,
    access_token: str,
    refresh_token: str | None = None,
    access_token_expires_at=None,
) -> None:
    sql = """
        UPDATE stores
        SET access_token = %s,
            refresh_token = COALESCE(%s, refresh_token),
            access_token_expires_at = COALESCE(%s, access_token_expires_at),
            updated_at = NOW()
        WHERE shop_domain = %s;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (access_token, refresh_token, access_token_expires_at, shop_domain))
    logger.info(f"Updated auth tokens for store: {shop_domain}")


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


def disable_report_schedule_by_email(contact_email: str) -> int:
    sql = """
        UPDATE stores
        SET report_schedule_active = FALSE,
            updated_at = NOW()
        WHERE LOWER(TRIM(contact_email)) = LOWER(TRIM(%s))
        RETURNING id;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (contact_email,))
        rows = cursor.fetchall() or []
        return len(rows)


def enable_report_schedule_by_email(contact_email: str) -> int:
    sql = """
        UPDATE stores
        SET report_schedule_active = TRUE,
            updated_at = NOW()
        WHERE LOWER(TRIM(contact_email)) = LOWER(TRIM(%s))
        RETURNING id;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (contact_email,))
        rows = cursor.fetchall() or []
        return len(rows)


def list_manual_reportable_stores() -> list[dict]:
    sql = """
        SELECT id,
               shop_domain,
               access_token,
               refresh_token,
               access_token_expires_at,
               contact_email
        FROM stores
        WHERE is_active = TRUE
          AND report_schedule_active = TRUE
          AND contact_email IS NOT NULL
          AND access_token IS NOT NULL
          AND connected_at IS NOT NULL
          -- Filter out legacy test/demo shops that should never be scheduled.
          AND shop_domain NOT ILIKE 'live-%'
          AND shop_domain NOT ILIKE '%test%'
        ORDER BY id ASC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def list_connected_stores_for_cron() -> list[dict]:
    """
    Stores eligible for cron-driven ETL/reporting runs.
    """
    sql = """
        SELECT id,
               shop_domain,
               access_token,
               refresh_token,
               access_token_expires_at,
               contact_email
        FROM stores
        WHERE is_active = TRUE
          AND connected_at IS NOT NULL
          AND access_token IS NOT NULL
        ORDER BY id ASC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def deactivate_likely_test_stores() -> list[dict]:
    """
    Hardens the DB against legacy demo/test shops being accidentally scheduled.

    This does NOT delete rows (for auditability). It simply deactivates scheduling.
    """
    sql = """
        UPDATE stores
        SET report_schedule_active = FALSE,
            is_active = FALSE,
            updated_at = NOW()
        WHERE is_active = TRUE
          AND report_schedule_active = TRUE
          AND (
            shop_domain ILIKE 'live-%'
            OR shop_domain ILIKE '%test%'
          )
        RETURNING id, shop_domain, contact_email;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql)
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


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


# ─── Job Monitoring ──────────────────────────────────────────────────────────

def create_job_run(store_id: int, shop_domain: str) -> int:
    sql = """
        INSERT INTO job_runs (store_id, shop_domain, status, started_at)
        VALUES (%s, %s, 'running', NOW())
        RETURNING id;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (store_id, shop_domain))
        row = cursor.fetchone()
        if not row:
            raise RuntimeError("Failed to create job run row.")
        return int(row["id"])


def complete_job_run(job_run_id: int, *, status: str, email_sent: bool, error_message: str | None = None) -> None:
    raise RuntimeError("complete_job_run is not allowed without explicit store_id. Use complete_job_run_for_store().")


def complete_job_run_for_store(
    store_id: int,
    job_run_id: int,
    *,
    status: str,
    email_sent: bool,
    report_path: str | None = None,
    recipient_email: str | None = None,
    error_message: str | None = None,
) -> None:
    scoped_store_id = _require_store_id(store_id)
    sql = """
        UPDATE job_runs
        SET status = %s,
            email_sent = %s,
            report_path = %s,
            recipient_email = %s,
            error_message = %s,
            finished_at = NOW()
        WHERE id = %s
          AND store_id = %s;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            sql,
            (status, email_sent, report_path, recipient_email, error_message, job_run_id, scoped_store_id),
        )


def get_recent_job_runs(limit: int = 20) -> list[dict]:
    sql = """
        SELECT id,
               store_id,
               shop_domain,
               status,
               started_at,
               finished_at,
               email_sent,
               error_message
        FROM job_runs
        ORDER BY started_at DESC
        LIMIT %s;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (limit,))
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def create_report_record(*, store_id: int, report_path: str, recipient_email: str) -> dict:
    scoped_store_id = _require_store_id(store_id)
    sql = """
        INSERT INTO reports (store_id, report_path, recipient_email, created_at)
        VALUES (%s, %s, %s, NOW())
        RETURNING id, store_id, report_path, recipient_email, created_at;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (scoped_store_id, report_path, recipient_email))
        row = cursor.fetchone()
        return dict(row) if row else {}


def get_store_contact_email_by_id(store_id: int) -> str | None:
    scoped_store_id = _require_store_id(store_id)
    sql = """
        SELECT contact_email
        FROM stores
        WHERE id = %s
        LIMIT 1;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (scoped_store_id,))
        row = cursor.fetchone() or {}
        email = (row.get("contact_email") or "").strip()
        return email or None


def update_store_display_name_by_id(*, store_id: int, display_name: str) -> None:
    scoped_store_id = _require_store_id(store_id)
    name = (display_name or "").strip()
    if not name:
        return
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'stores'
              AND column_name = 'display_name'
            LIMIT 1;
            """
        )
        if not cursor.fetchone():
            return
        cursor.execute(
            """
            UPDATE stores
            SET display_name = %s,
                updated_at = NOW()
            WHERE id = %s;
            """,
            (name, scoped_store_id),
        )


def get_store_display_name_by_id(store_id: int) -> str | None:
    """
    Returns a human-meaningful store label for emails/reports.

    Prefers stores.display_name when present; otherwise falls back to shop_domain.
    """
    scoped_store_id = _require_store_id(store_id)
    with get_cursor() as cursor:
        cursor.execute(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'stores'
              AND column_name = 'display_name'
            LIMIT 1;
            """
        )
        has_display_name = bool(cursor.fetchone())

        if has_display_name:
            cursor.execute(
                """
                SELECT COALESCE(NULLIF(display_name, ''), shop_domain) AS display_name
                FROM stores
                WHERE id = %s
                LIMIT 1;
                """,
                (scoped_store_id,),
            )
            row = cursor.fetchone() or {}
            name = (row.get("display_name") or "").strip()
            return name or None

        cursor.execute(
            """
            SELECT shop_domain
            FROM stores
            WHERE id = %s
            LIMIT 1;
            """,
            (scoped_store_id,),
        )
        row = cursor.fetchone() or {}
        name = (row.get("shop_domain") or "").strip()
        return name or None


# ─── Tasks ──────────────────────────────────────────────────────────────────

def get_task_by_fingerprint(store_id: int, fingerprint: str) -> dict | None:
    sql = """
        SELECT *
        FROM tasks
        WHERE store_id = %s
          AND fingerprint = %s
        LIMIT 1;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (store_id, fingerprint))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_task(
    *,
    store_id: int,
    task_type: str,
    title: str,
    description: str,
    status: str,
    priority: str,
    due_at,
    expected_impact: float,
    fingerprint: str,
    primary_entity_id: str | None,
    metadata_json: str,
) -> dict:
    sql = """
        INSERT INTO tasks (
            store_id, type, title, description, status, priority,
            created_at, updated_at, last_status_change_at,
            due_at, expected_impact, fingerprint, primary_entity_id, metadata_json
        )
        VALUES (%s, %s, %s, %s, %s, %s, NOW(), NOW(), NOW(), %s, %s, %s, %s, %s::jsonb)
        RETURNING *;
    """
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            sql,
            (
                store_id,
                task_type,
                title,
                description,
                status,
                priority,
                due_at,
                expected_impact,
                fingerprint,
                primary_entity_id,
                metadata_json,
            ),
        )
        row = cursor.fetchone()
        return dict(row)


def update_task_metadata(
    *,
    task_id: int,
    store_id: int,
    title: str,
    description: str,
    priority: str,
    expected_impact: float,
    due_at,
    metadata_json: str,
) -> dict:
    sql = """
        UPDATE tasks
        SET title = %s,
            description = %s,
            priority = %s,
            expected_impact = %s,
            due_at = %s,
            metadata_json = %s::jsonb,
            updated_at = NOW()
        WHERE id = %s
          AND (%s IS NULL OR store_id = %s)
        RETURNING *;
    """
    scoped_store_id = _require_store_id(store_id)
    with get_cursor(commit=True) as cursor:
        cursor.execute(
            sql,
            (title, description, priority, expected_impact, due_at, metadata_json, task_id, scoped_store_id, scoped_store_id),
        )
        row = cursor.fetchone()
        return dict(row) if row else {}


def update_task_status(
    *,
    task_id: int,
    store_id: int,
    status: str,
    completed_at=None,
    due_at=None,
    baseline_metric=None,
) -> dict | None:
    sql = """
        UPDATE tasks
        SET status = %s,
            completed_at = COALESCE(%s, completed_at),
            due_at = COALESCE(%s, due_at),
            baseline_metric = COALESCE(%s, baseline_metric),
            last_status_change_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
          AND (%s IS NULL OR store_id = %s)
        RETURNING *;
    """
    scoped_store_id = _require_store_id(store_id)
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (status, completed_at, due_at, baseline_metric, task_id, scoped_store_id, scoped_store_id))
        row = cursor.fetchone()
        return dict(row) if row else None


def set_task_actual_impact(task_id: int, actual_impact: float, store_id: int) -> None:
    sql = """
        UPDATE tasks
        SET actual_impact = %s,
            updated_at = NOW()
        WHERE id = %s
          AND (%s IS NULL OR store_id = %s);
    """
    scoped_store_id = _require_store_id(store_id)
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (actual_impact, task_id, scoped_store_id, scoped_store_id))


def touch_task_reminder(task_id: int, store_id: int) -> None:
    sql = """
        UPDATE tasks
        SET last_reminded_at = NOW(),
            updated_at = NOW()
        WHERE id = %s
          AND (%s IS NULL OR store_id = %s);
    """
    scoped_store_id = _require_store_id(store_id)
    with get_cursor(commit=True) as cursor:
        cursor.execute(sql, (task_id, scoped_store_id, scoped_store_id))


def list_tasks_for_store(store_id: int, limit: int = 100) -> list[dict]:
    sql = """
        SELECT *
        FROM tasks
        WHERE store_id = %s
        ORDER BY
            CASE status WHEN 'pending' THEN 0 WHEN 'in_progress' THEN 1 WHEN 'completed' THEN 2 ELSE 3 END,
            CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END,
            expected_impact DESC,
            created_at DESC
        LIMIT %s;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (store_id, limit))
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def get_task_by_id(task_id: int) -> dict | None:
    raise RuntimeError("get_task_by_id is not allowed without explicit store_id. Use get_task_by_id_for_store().")


def get_task_by_id_for_store(task_id: int, store_id: int) -> dict | None:
    scoped_store_id = _require_store_id(store_id)
    sql = """
        SELECT *
        FROM tasks
        WHERE id = %s
          AND store_id = %s
        LIMIT 1;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (task_id, scoped_store_id))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_tasks_for_report(store_id: int) -> list[dict]:
    sql = """
        SELECT *
        FROM tasks
        WHERE store_id = %s
        ORDER BY updated_at DESC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (store_id,))
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def get_due_task_evaluations(store_id: int) -> list[dict]:
    sql = """
        SELECT *
        FROM tasks
        WHERE store_id = %s
          AND status = 'completed'
          AND due_at IS NOT NULL
          AND due_at <= NOW()
          AND actual_impact IS NULL
        ORDER BY due_at ASC;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (store_id,))
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def get_tasks_needing_reminders(store_id: int) -> list[dict]:
    sql = """
        SELECT *
        FROM tasks
        WHERE store_id = %s
          AND (
            (status = 'pending' AND (last_reminded_at IS NULL OR last_reminded_at < NOW() - INTERVAL '24 hours'))
            OR
            (status = 'in_progress' AND last_status_change_at < NOW() - INTERVAL '48 hours'
             AND (last_reminded_at IS NULL OR last_reminded_at < NOW() - INTERVAL '24 hours'))
          );
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (store_id,))
        rows = cursor.fetchall() or []
        return [dict(r) for r in rows]


def count_new_customers_in_window(store_id: int, start_at, end_at) -> int:
    sql = """
        WITH first_orders AS (
            SELECT customer_id, MIN(created_at) AS first_order_at
            FROM orders
            WHERE store_id = %s
              AND customer_id IS NOT NULL
              AND financial_status = 'paid'
            GROUP BY customer_id
        )
        SELECT COUNT(*)
        FROM first_orders
        WHERE first_order_at >= %s
          AND first_order_at < %s;
    """
    with get_cursor() as cursor:
        cursor.execute(sql, (store_id, start_at, end_at))
        row = cursor.fetchone() or {}
        return int(row.get("count") or 0)