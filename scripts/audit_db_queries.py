from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from config import settings
from db import queries
from db.connection import get_cursor


def run() -> None:
    suffix = uuid4().hex[:10]
    now = datetime.now(timezone.utc)
    shop_domain = f"audit-{suffix}.myshopify.com"
    referral_code = f"AUDIT{suffix[:6].upper()}"
    state_hash = uuid4().hex + uuid4().hex

    assert settings.DB_SSLMODE == "require", "DB_SSLMODE must be set to require"
    with get_cursor() as cursor:
        cursor.execute("SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid();")
        ssl_row = cursor.fetchone() or {}
        print(f"pg_stat_ssl.ssl={ssl_row.get('ssl')}")

    queries.upsert_store_contact_email(shop_domain, f"owner+{suffix}@example.com")
    queries.upsert_store_connection(
        shop_domain=shop_domain,
        access_token=f"token-{suffix}",
        refresh_token=f"refresh-{suffix}",
        access_token_expires_at=now + timedelta(days=10),
        scope="read_orders,read_products",
        contact_email=f"owner+{suffix}@example.com",
        display_name=f"Audit Store {suffix}",
    )
    store = queries.get_store_by_domain(shop_domain)
    assert store and store["id"], "Store upsert failed"
    store_id = int(store["id"])

    created_ref = queries.create_referral_code(referral_code, f"Partner {suffix}", 15.0)
    assert created_ref.get("id"), "Referral code creation failed"
    referral_code_id = int(created_ref["id"])
    assert queries.get_active_referral_code_by_code(referral_code), "Referral lookup failed"
    assert queries.attach_store_referral(shop_domain, referral_code_id, referral_code), "Attach referral failed"
    assert queries.get_referral_code_details(referral_code), "Referral detail lookup failed"
    assert isinstance(queries.list_referral_codes_with_stats(), list), "Referral listing failed"

    queries.create_oauth_state(state_hash, shop_domain)
    assert queries.consume_oauth_state(state_hash, shop_domain), "OAuth consume failed"

    queries.update_store_auth_tokens(
        shop_domain,
        access_token=f"token2-{suffix}",
        refresh_token=f"refresh2-{suffix}",
        access_token_expires_at=now + timedelta(days=20),
    )
    queries.set_store_schedule(shop_domain, "09:00", True)
    queries.update_store_timezone(shop_domain, "UTC")
    queries.update_store_contact_email(shop_domain, f"ops+{suffix}@example.com")
    assert queries.claim_report_send_slot(shop_domain) is True, "First report slot claim failed"
    assert queries.claim_report_send_slot(shop_domain) is False, "Second report slot should be throttled"
    assert isinstance(queries.get_active_scheduled_stores(), list), "Scheduled stores query failed"
    assert isinstance(queries.list_manual_reportable_stores(), list), "Manual reportable stores query failed"
    assert isinstance(queries.deactivate_likely_test_stores(), list), "Deactivate test stores query failed"
    queries.set_store_schedule(shop_domain, "09:00", True)

    product_id = 10_000_000 + int(suffix[:4], 16)
    variant_id = 20_000_000 + int(suffix[4:8], 16)
    customer_id = 30_000_000 + int(suffix[:4], 16)
    order_id = 40_000_000 + int(suffix[4:8], 16)
    order_item_id = 50_000_000 + int(suffix[:4], 16)

    queries.upsert_product(
        {
            "store_id": store_id,
            "id": product_id,
            "title": f"Audit Product {suffix}",
            "vendor": "AuditVendor",
            "product_type": "audit",
            "status": "active",
            "created_at": now,
            "updated_at": now,
        }
    )
    queries.upsert_variant(
        {
            "store_id": store_id,
            "id": variant_id,
            "product_id": product_id,
            "title": "Default",
            "sku": f"SKU-{suffix}",
            "price": 19.99,
            "inventory_quantity": 10,
            "updated_at": now,
        }
    )
    queries.upsert_customer(
        {
            "store_id": store_id,
            "id": customer_id,
            "email": f"buyer+{suffix}@example.com",
            "first_name": "Audit",
            "last_name": "Buyer",
            "orders_count": 1,
            "total_spent": 19.99,
            "created_at": now,
            "updated_at": now,
        }
    )
    queries.upsert_order(
        {
            "store_id": store_id,
            "id": order_id,
            "customer_id": customer_id,
            "email": f"buyer+{suffix}@example.com",
            "total_price": 19.99,
            "subtotal_price": 19.99,
            "total_discounts": 0.0,
            "financial_status": "paid",
            "fulfillment_status": "fulfilled",
            "created_at": now,
            "updated_at": now,
        }
    )
    queries.upsert_order_item(
        {
            "store_id": store_id,
            "id": order_item_id,
            "order_id": order_id,
            "product_id": product_id,
            "variant_id": variant_id,
            "title": "Audit Product",
            "quantity": 1,
            "price": 19.99,
            "total_discount": 0.0,
            "vendor": "AuditVendor",
        }
    )
    queries.upsert_inventory(
        {
            "store_id": store_id,
            "variant_id": variant_id,
            "inventory_item_id": variant_id,
            "location_id": 1,
            "available": 10,
        }
    )

    job_run_id = queries.create_job_run(store_id, shop_domain)
    queries.complete_job_run_for_store(
        store_id=store_id,
        job_run_id=job_run_id,
        status="success",
        email_sent=True,
        report_path=f"/tmp/{suffix}.pdf",
        recipient_email=f"ops+{suffix}@example.com",
    )
    assert isinstance(queries.get_recent_job_runs(10), list), "Job runs query failed"

    report = queries.create_report_record(
        store_id=store_id,
        report_path=f"/tmp/{suffix}.pdf",
        recipient_email=f"ops+{suffix}@example.com",
    )
    assert report.get("id"), "Report record creation failed"
    assert queries.get_store_contact_email_by_id(store_id), "Store contact lookup failed"
    queries.update_store_display_name_by_id(store_id=store_id, display_name=f"Audit Display {suffix}")
    assert queries.get_store_display_name_by_id(store_id), "Display name lookup failed"

    task = queries.create_task(
        store_id=store_id,
        task_type="inventory",
        title=f"Audit task {suffix}",
        description="Audit task description",
        status="pending",
        priority="high",
        due_at=now + timedelta(days=2),
        expected_impact=100.0,
        fingerprint=uuid4().hex,
        primary_entity_id=str(product_id),
        metadata_json='{"source":"audit"}',
    )
    assert task and task.get("id"), "Task creation failed"
    task_id = int(task["id"])
    assert queries.get_task_by_fingerprint(store_id, task["fingerprint"]), "Task fingerprint lookup failed"
    assert queries.update_task_metadata(
        task_id=task_id,
        store_id=store_id,
        title=f"Audit task {suffix} updated",
        description="Updated",
        priority="medium",
        expected_impact=120.0,
        due_at=now + timedelta(days=3),
        metadata_json='{"source":"audit","v":2}',
    ), "Task metadata update failed"
    assert queries.update_task_status(
        task_id=task_id,
        store_id=store_id,
        status="in_progress",
    ), "Task status update failed"
    queries.set_task_actual_impact(task_id, 80.0, store_id)
    queries.touch_task_reminder(task_id, store_id)
    assert isinstance(queries.list_tasks_for_store(store_id), list), "Task listing failed"
    assert queries.get_task_by_id_for_store(task_id, store_id), "Task by id query failed"
    assert isinstance(queries.get_tasks_for_report(store_id), list), "Tasks for report query failed"
    assert isinstance(queries.get_due_task_evaluations(store_id), list), "Due task evaluations query failed"
    assert isinstance(queries.get_tasks_needing_reminders(store_id), list), "Task reminders query failed"
    assert isinstance(queries.count_new_customers_in_window(store_id, now - timedelta(days=7), now), int)

    assert queries.disable_report_schedule_by_email(f"ops+{suffix}@example.com") >= 1
    assert queries.enable_report_schedule_by_email(f"ops+{suffix}@example.com") >= 1
    assert queries.deactivate_referral_code(referral_code) is True

    # Soft cleanup for audit data to keep subsequent runs idempotent.
    with get_cursor(commit=True) as cursor:
        cursor.execute("DELETE FROM stores WHERE id = %s;", (store_id,))

    print("DB queries audit passed")


if __name__ == "__main__":
    run()
