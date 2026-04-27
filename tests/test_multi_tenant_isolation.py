import pytest
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db.connection import _assert_tenant_scoped_query
from db import queries
from reporting.pdf_report_v2 import create_report_pdf
from scheduler.run_pipeline import _assert_store_report_delivery_scope


def test_query_missing_store_id_fails():
    with pytest.raises(RuntimeError):
        _assert_tenant_scoped_query("SELECT * FROM orders WHERE financial_status = 'paid';")


def test_global_task_lookup_blocked():
    with pytest.raises(RuntimeError):
        queries.get_task_by_id(1)


def test_report_path_and_recipient_must_match_store(monkeypatch):
    monkeypatch.setattr("scheduler.run_pipeline.get_store_contact_email_by_id", lambda store_id: "owner@example.com")

    with pytest.raises(RuntimeError):
        _assert_store_report_delivery_scope(
            store_id=7,
            report_path="reports/8/store-intelligence-store-8-20260427-000000.pdf",
            recipient_email="owner@example.com",
        )

    with pytest.raises(RuntimeError):
        _assert_store_report_delivery_scope(
            store_id=7,
            report_path="reports/7/store-intelligence-store-7-20260427-000000.pdf",
            recipient_email="other@example.com",
        )


def test_report_pdf_is_store_scoped(tmp_path):
    output = create_report_pdf(
        summary={"insights": [], "inventory": {}, "customers": {}, "revenue": {}},
        output_dir=str(tmp_path / "reports" / "21"),
        task_sections={},
        store_id=21,
    )
    assert "/21/" in output.replace("\\", "/")
    assert "store-21" in output
