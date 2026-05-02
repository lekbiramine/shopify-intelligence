"""
Populate Postgres with realistic synthetic data when Shopify denies GraphQL `orders`.
--replace clears customers, orders, order_items, abandoned_checkouts for the store.

  python scripts/seed_test_data.py --replace
  python scripts/seed_test_data.py --replace --store-id 1
"""
from __future__ import annotations

import argparse
import sys
import random
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
from datetime import datetime, timedelta, timezone

import psycopg2
from psycopg2.extras import execute_batch

from config import settings
from config.logging_config import get_logger, setup_logging

setup_logging()
logger = get_logger(__name__)

CUSTOMER_ID_START = 80_000_000
ORDER_ID_START = 90_000_000
ORDER_ITEM_ID_START = 95_000_000
# Top spend quintile / “VIP” cohort in synthetic data (20% of 50 seeded customers).
VIP_CUSTOMER_COUNT = 10

FIRST_NAMES = (
    "Jordan", "Alex", "Taylor", "Riley", "Morgan", "Casey", "Quinn", "Jamie", "Avery",
    "Reese", "Cameron", "Skyler", "Drew", "Emerson", "Hayden", "Parker", "Logan", "Rowan",
    "Sage", "Blake",
)
LAST_NAMES = (
    "Miller", "Chen", "Garcia", "Thompson", "Patel", "Johnson", "Williams", "Brown",
    "Davis", "Wilson", "Moore", "Taylor", "Anderson", "Martin", "Lee", "Clark", "Lewis",
    "Walker", "Hall", "Young",
)


def _connect():
    return psycopg2.connect(
        host=settings.DB_HOST,
        port=settings.DB_PORT,
        dbname=settings.DB_NAME,
        user=settings.DB_USER,
        password=settings.DB_PASSWORD,
    )


def _dt(days: float) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days)


def ensure_abandoned_checkouts_table(conn) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS abandoned_checkouts (
                id BIGSERIAL PRIMARY KEY,
                store_id BIGINT NOT NULL REFERENCES stores(id) ON DELETE CASCADE,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_abandoned_checkouts_store_created
            ON abandoned_checkouts (store_id, created_at DESC);
            """
        )
    conn.commit()


def clear_store_analytics(conn, store_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM order_items WHERE store_id = %s", (store_id,))
        cur.execute("DELETE FROM orders WHERE store_id = %s", (store_id,))
        cur.execute("DELETE FROM customers WHERE store_id = %s", (store_id,))
        cur.execute("DELETE FROM abandoned_checkouts WHERE store_id = %s", (store_id,))
    conn.commit()
    logger.info("Cleared analytics tables for store_id=%s", store_id)


def load_catalog(conn, store_id: int) -> tuple[list[dict], list[int]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT v.id AS variant_id,
                   v.product_id,
                   v.price,
                   v.sku,
                   p.title AS product_title,
                   p.vendor,
                   COALESCE(p.status, 'active') AS status
            FROM variants v
            JOIN products p ON p.store_id = v.store_id AND p.id = v.product_id
            WHERE v.store_id = %s
              AND COALESCE(p.status, 'active') = 'active'
            ORDER BY p.id, v.id;
            """,
            (store_id,),
        )
        cols = [c[0] for c in cur.description]
        rows = [dict(zip(cols, r)) for r in cur.fetchall()]
    pids = sorted({r["product_id"] for r in rows})
    if len(pids) < 4:
        raise RuntimeError(
            f"Need >= 4 active products with variants for store_id={store_id} (found {len(pids)})."
        )
    return rows, pids


def resolve_store_id(conn, explicit: int | None) -> int:
    if explicit is not None:
        return explicit
    try:
        from db.queries import get_store_by_domain
    except ImportError:
        get_store_by_domain = None  # type: ignore[misc, assignment]
    url = (settings.SHOPIFY_STORE_URL or "").strip()
    if get_store_by_domain and url:
        store = get_store_by_domain(url)
        if store:
            return int(store["id"])
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM stores ORDER BY id LIMIT 1;")
        row = cur.fetchone()
        if row:
            return int(row[0])
    raise RuntimeError("Pass --store-id or set SHOPIFY_STORE_URL with a store row.")


def seed_customers(conn, store_id: int) -> None:
    rnd = random.Random(42)
    batch = []
    for i in range(50):
        fn, ln = rnd.choice(FIRST_NAMES), rnd.choice(LAST_NAMES)
        batch.append(
            {
                "store_id": store_id,
                "id": CUSTOMER_ID_START + i,
                "email": f"{fn.lower()}.{ln.lower()}.{i}.seed@example.com",
                "first_name": fn,
                "last_name": ln,
                "orders_count": 0,
                "total_spent": 0,
                "created_at": _dt(400),
                "updated_at": _dt(1),
            }
        )
    sql = """
        INSERT INTO customers (store_id, id, email, first_name, last_name, orders_count, total_spent, created_at, updated_at)
        VALUES (%(store_id)s, %(id)s, %(email)s, %(first_name)s, %(last_name)s, %(orders_count)s, %(total_spent)s, %(created_at)s, %(updated_at)s);
    """
    with conn.cursor() as cur:
        execute_batch(cur, sql, batch)
    conn.commit()


def seed_abandoned(conn, store_id: int) -> None:
    rnd = random.Random(7)
    rows = []
    for _ in range(88):
        ts = _dt(rnd.uniform(0, 6.5))
        rows.append({"store_id": store_id, "created_at": ts})
    for _ in range(24):
        ts = _dt(rnd.uniform(7, 13.5))
        rows.append({"store_id": store_id, "created_at": ts})
    with conn.cursor() as cur:
        execute_batch(
            cur,
            "INSERT INTO abandoned_checkouts (store_id, created_at) VALUES (%(store_id)s, %(created_at)s);",
            rows,
        )
    conn.commit()


def refresh_customer_aggregates(conn, store_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE customers c
            SET orders_count = s.cnt,
                total_spent = s.spend
            FROM (
                SELECT customer_id,
                       COUNT(*)::int AS cnt,
                       COALESCE(SUM(total_price), 0)::numeric(10,2) AS spend
                FROM orders
                WHERE store_id = %s AND customer_id IS NOT NULL
                GROUP BY customer_id
            ) s
            WHERE c.store_id = %s AND c.id = s.customer_id;
            """,
            (store_id, store_id),
        )
    conn.commit()


def upsert_dead_inventory(conn, store_id: int, dead_pids: set[int], rows: list[dict]) -> None:
    rnd = random.Random(99)
    loc = 910_000_001
    dead_variant_ids = [r["variant_id"] for r in rows if r["product_id"] in dead_pids]
    if not dead_variant_ids:
        return
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM inventory WHERE store_id = %s AND variant_id = ANY(%s);",
            (store_id, dead_variant_ids),
        )
        for r in rows:
            if r["product_id"] not in dead_pids:
                continue
            qty = rnd.randint(15, 45)
            ii = int(r["variant_id"]) + 1_000_000
            cur.execute(
                """
                INSERT INTO inventory (store_id, variant_id, inventory_item_id, location_id, available)
                VALUES (%s, %s, %s, %s, %s);
                """,
                (store_id, r["variant_id"], ii, loc, qty),
            )
    conn.commit()


def _random_order_total(rnd: random.Random) -> float:
    """Target store AOV ~ $45–$85 when averaged across many orders."""
    return round(max(45.0, min(155.0, rnd.gauss(63.5, 17.0))), 2)


def _random_order_total_vip(rnd: random.Random) -> float:
    """Heavier order totals for top-spend customers so lifetime LTV lands ~$300–$2,000."""
    return round(max(72.0, min(195.0, rnd.gauss(108.0, 22.0))), 2)


def _n_line_items(rnd: random.Random) -> int:
    return rnd.choices([1, 2, 3], weights=[0.46, 0.36, 0.18], k=1)[0]


def _partition_line_prices(order_total: float, n_lines: int, rnd: random.Random) -> list[float]:
    """Split order_total into n_lines amounts, each in [15, 120]."""
    lo, hi = 15.0, 120.0
    ot = round(float(order_total), 2)
    if n_lines <= 1:
        return [round(max(lo, min(hi, ot)), 2)]
    for _ in range(150):
        parts: list[float] = []
        remaining = ot
        ok = True
        for i in range(n_lines - 1):
            slots_left = n_lines - 1 - i
            min_share = max(lo, remaining - hi * slots_left)
            max_share = min(hi, remaining - lo * slots_left)
            if min_share > max_share + 1e-6:
                ok = False
                break
            share = round(rnd.uniform(min_share, max_share), 2)
            parts.append(share)
            remaining -= share
        if not ok:
            continue
        last = round(remaining, 2)
        if lo <= last <= hi and abs(sum(parts) + last - ot) < 0.05:
            parts.append(last)
            return parts
    each = round(max(lo, min(hi, ot / n_lines)), 2)
    out = [each] * (n_lines - 1)
    out.append(round(max(lo, min(hi, ot - sum(out))), 2))
    return out


def _line_specs_hot(hot_row: dict, order_total: float, n_lines: int, rnd: random.Random) -> list[tuple[dict, int, float]]:
    prices = _partition_line_prices(order_total, n_lines, rnd)
    return [(hot_row, 1, p) for p in prices]


def _line_specs_pool_only(pool: list[dict], order_total: float, n_lines: int, rnd: random.Random) -> list[tuple[dict, int, float]]:
    prices = _partition_line_prices(order_total, n_lines, rnd)
    return [(rnd.choice(pool), 1, p) for p in prices]


def _line_specs_cheap_led(
    cheap_row: dict, pool: list[dict], rnd: random.Random
) -> list[tuple[dict, int, float]]:
    """At least one cheap-SKU line; 1–3 lines; order total gaussian ~ target AOV."""
    base = round(float(cheap_row["price"]), 2)
    base = max(15.0, min(120.0, base))
    n = _n_line_items(rnd)
    target = _random_order_total(rnd)
    target = max(target, base + 15.0 * max(0, n - 1))
    remainder = round(max(15.0, target - base), 2)
    if n == 1:
        unit = round(max(15.0, min(120.0, target)), 2)
        return [(cheap_row, 1, unit)]
    other_n = n - 1
    rest = _partition_line_prices(remainder, other_n, rnd)
    specs: list[tuple[dict, int, float]] = [(cheap_row, 1, base)]
    for p in rest:
        specs.append((rnd.choice(pool), 1, p))
    return specs


def run_seed(conn, store_id: int) -> None:
    cat_rows, pids = load_catalog(conn, store_id)
    dead_pids = set(pids[-3:])
    usable = [r for r in cat_rows if r["product_id"] not in dead_pids]
    hot_row = usable[0]

    cheap = min(usable, key=lambda x: float(x["price"]))
    cheap_row = dict(cheap)
    cheap_row["price"] = 32.99
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE variants SET price = %s WHERE store_id = %s AND id = %s;",
            (cheap_row["price"], store_id, cheap_row["variant_id"]),
        )
    conn.commit()

    pool = [r for r in usable if r["variant_id"] != cheap_row["variant_id"]]
    rnd = random.Random(42)

    order_rows: list[dict] = []
    item_rows: list[dict] = []
    oid = ORDER_ID_START
    liid = ORDER_ITEM_ID_START

    hot_refund_positions = set(range(41))
    templates: list[dict] = []

    pos = 0
    for w in range(5):
        cid = CUSTOMER_ID_START + w
        for _ in range(8):
            st = "refunded" if pos in hot_refund_positions else "paid"
            templates.append(
                {
                    "cid": cid,
                    "when": _dt(70 + rnd.uniform(-2.5, 2.5)),
                    "status": st,
                    "seg": "hot",
                }
            )
            pos += 1
        for _ in range(2):
            st = "refunded" if pos in hot_refund_positions else "paid"
            templates.append(
                {
                    "cid": cid,
                    "when": _dt(68 + rnd.uniform(-2, 2)),
                    "status": st,
                    "seg": "hot",
                }
            )
            pos += 1

    for j in range(5, 45):
        cid = CUSTOMER_ID_START + j
        st = "refunded" if pos in hot_refund_positions else "paid"
        templates.append(
            {"cid": cid, "when": _dt(18 + rnd.uniform(0, 72)), "status": st, "seg": "hot"}
        )
        pos += 1

    assert pos == 90

    # Keep the “cheap SKU whale” off the VIP cohort so their LTV stays in the high band.
    whale_cheap = CUSTOMER_ID_START + 35
    for i in range(12):
        when = _dt(rnd.uniform(0.5, 6.5)) if i < 6 else _dt(12 + rnd.uniform(0, 78))
        templates.append(
            {"cid": whale_cheap, "when": when, "status": "paid", "seg": "cheap"}
        )

    for w in range(5):
        cid = CUSTOMER_ID_START + w
        for _ in range(10):
            templates.append(
                {
                    "cid": cid,
                    "when": _dt(125 + rnd.uniform(0, 14)),
                    "status": "paid",
                    "seg": "old",
                }
            )

    churn_counts = [10, 10, 10, 9, 9]
    for idx, j in enumerate(range(45, 50)):
        cid = CUSTOMER_ID_START + j
        for _ in range(churn_counts[idx]):
            templates.append(
                {
                    "cid": cid,
                    "when": _dt(112 + rnd.uniform(0, 22)),
                    "status": "paid",
                    "seg": "old",
                }
            )

    assert len(templates) == 200, len(templates)

    def push_order(cid: int, when: datetime, status: str, specs: list[tuple[dict, int, float]]) -> None:
        nonlocal oid, liid
        this_oid = oid
        order_total = round(sum(qty * unit for _, qty, unit in specs), 2)
        order_rows.append(
            {
                "store_id": store_id,
                "id": this_oid,
                "customer_id": cid,
                "email": None,
                "total_price": order_total,
                "subtotal_price": order_total,
                "total_discounts": 0.0,
                "financial_status": status,
                "fulfillment_status": "fulfilled",
                "created_at": when,
                "updated_at": when,
            }
        )
        for vrow, qty, unit in specs:
            item_rows.append(
                {
                    "store_id": store_id,
                    "id": liid,
                    "order_id": this_oid,
                    "product_id": vrow["product_id"],
                    "variant_id": vrow["variant_id"],
                    "title": vrow["product_title"],
                    "quantity": qty,
                    "price": round(float(unit), 2),
                    "total_discount": 0.0,
                    "vendor": vrow.get("vendor"),
                }
            )
            liid += 1
        oid = this_oid + 1

    for t in templates:
        seg = t["seg"]
        cid = int(t["cid"])
        is_vip = CUSTOMER_ID_START <= cid < CUSTOMER_ID_START + VIP_CUSTOMER_COUNT
        if seg == "hot":
            total = _random_order_total_vip(rnd) if is_vip else _random_order_total(rnd)
            n = _n_line_items(rnd)
            specs = _line_specs_hot(hot_row, total, n, rnd)
            push_order(t["cid"], t["when"], t["status"], specs)
        elif seg == "cheap":
            specs = _line_specs_cheap_led(cheap_row, pool, rnd)
            push_order(t["cid"], t["when"], t["status"], specs)
        else:
            total = _random_order_total_vip(rnd) if is_vip else _random_order_total(rnd)
            n = _n_line_items(rnd)
            specs = _line_specs_pool_only(pool, total, n, rnd)
            push_order(t["cid"], t["when"], t["status"], specs)

    aov = sum(float(o["total_price"]) for o in order_rows) / max(len(order_rows), 1)
    logger.info("Seed AOV check: mean order total = $%.2f across %s orders.", aov, len(order_rows))

    o_sql = """
        INSERT INTO orders (store_id, id, customer_id, email, total_price, subtotal_price, total_discounts,
            financial_status, fulfillment_status, created_at, updated_at)
        VALUES (%(store_id)s, %(id)s, %(customer_id)s, %(email)s, %(total_price)s, %(subtotal_price)s, %(total_discounts)s,
            %(financial_status)s, %(fulfillment_status)s, %(created_at)s, %(updated_at)s);
    """
    i_sql = """
        INSERT INTO order_items (store_id, id, order_id, product_id, variant_id, title, quantity, price, total_discount, vendor)
        VALUES (%(store_id)s, %(id)s, %(order_id)s, %(product_id)s, %(variant_id)s, %(title)s, %(quantity)s, %(price)s, %(total_discount)s, %(vendor)s);
    """
    with conn.cursor() as cur:
        execute_batch(cur, o_sql, order_rows)
        execute_batch(cur, i_sql, item_rows)
    conn.commit()
    logger.info("Inserted %s orders and %s order_items.", len(order_rows), len(item_rows))

    seed_abandoned(conn, store_id)
    refresh_customer_aggregates(conn, store_id)
    upsert_dead_inventory(conn, store_id, dead_pids, cat_rows)
    logger.info("Dead inventory upserted for product_ids=%s", sorted(dead_pids))


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed realistic test data for a store (dev only).")
    parser.add_argument("--replace", action="store_true", help="Delete existing store analytics rows first.")
    parser.add_argument("--store-id", type=int, default=None)
    args = parser.parse_args()

    if not args.replace:
        raise SystemExit("Refusing to run without --replace (safety).")

    conn = _connect()
    try:
        ensure_abandoned_checkouts_table(conn)
        store_id = resolve_store_id(conn, args.store_id)
        clear_store_analytics(conn, store_id)
        seed_customers(conn, store_id)
        run_seed(conn, store_id)
        logger.info("Done. store_id=%s", store_id)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
