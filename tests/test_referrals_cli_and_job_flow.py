import sys
from datetime import datetime, timezone

import pytest


@pytest.fixture
def baseline_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "test")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "test")


def test_referrals_cli_commands(baseline_env, monkeypatch, capsys):
    import scripts.referrals as cli

    codes: dict[str, dict] = {}
    installs: dict[str, list[str]] = {}

    def fake_create_referral_code(code: str, partner_name: str, discount_percent: float = 20.0):
        row = {
            "id": len(codes) + 1,
            "code": code,
            "partner_name": partner_name,
            "discount_percent": discount_percent,
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
        }
        codes[code] = row
        installs.setdefault(code, [])
        return row

    def fake_list_referral_codes_with_stats():
        rows = []
        for code, row in codes.items():
            rows.append(
                {
                    **row,
                    "store_count": len(installs.get(code, [])),
                }
            )
        return rows

    def fake_get_referral_code_details(code: str):
        if code not in codes:
            return None
        stores = [{"shop_domain": s, "installed_at": datetime.now(timezone.utc)} for s in installs.get(code, [])]
        return {
            **codes[code],
            "stores": stores,
            "store_count": len(stores),
        }

    def fake_deactivate_referral_code(code: str):
        if code not in codes:
            return False
        codes[code]["is_active"] = False
        return True

    monkeypatch.setattr(cli, "create_referral_code", fake_create_referral_code)
    monkeypatch.setattr(cli, "list_referral_codes_with_stats", fake_list_referral_codes_with_stats)
    monkeypatch.setattr(cli, "get_referral_code_details", fake_get_referral_code_details)
    monkeypatch.setattr(cli, "deactivate_referral_code", fake_deactivate_referral_code)

    monkeypatch.setattr(sys, "argv", ["referrals.py", "create", "--partner", "Creator One", "--code", "CREATOR20"])
    cli.main()
    out = capsys.readouterr().out
    assert "Created code CREATOR20" in out

    installs["CREATOR20"].extend(["store-a.myshopify.com", "store-b.myshopify.com"])

    monkeypatch.setattr(sys, "argv", ["referrals.py", "list"])
    cli.main()
    out = capsys.readouterr().out
    assert "CREATOR20" in out
    assert "stores=2" in out

    monkeypatch.setattr(sys, "argv", ["referrals.py", "show", "--code", "CREATOR20"])
    cli.main()
    out = capsys.readouterr().out
    assert "stores=2" in out
    assert "store-a.myshopify.com" in out

    monkeypatch.setattr(sys, "argv", ["referrals.py", "deactivate", "--code", "CREATOR20"])
    cli.main()
    out = capsys.readouterr().out
    assert "Deactivated referral code: CREATOR20" in out


def test_run_store_job_referral_fields_do_not_break_flow(baseline_env, monkeypatch):
    import scripts.run_store_job as run_store_job

    calls = {
        "etl": 0,
        "report": 0,
        "complete": 0,
    }

    monkeypatch.setattr(run_store_job, "load_client_env", lambda env_file: "")
    monkeypatch.setattr(run_store_job, "env_value", lambda *args: "")
    monkeypatch.setattr(run_store_job, "normalize_shop_domain", lambda s: s)
    monkeypatch.setattr(
        run_store_job,
        "get_store_by_domain",
        lambda shop: {
            "id": 1,
            "shop_domain": shop,
            "access_token": "token_x",
            "refresh_token": None,
            "access_token_expires_at": None,
            "contact_email": "owner@example.com",
            "referral_code_used": "CREATOR20",
            "referral_code_id": 11,
        },
    )
    monkeypatch.setattr(run_store_job, "create_job_run", lambda **kwargs: 99)

    def fake_etl(**kwargs):
        calls["etl"] += 1

    def fake_report(**kwargs):
        calls["report"] += 1

    def fake_complete(*args, **kwargs):
        calls["complete"] += 1
        assert kwargs["status"] == "success"

    monkeypatch.setattr(run_store_job, "run_etl_for_store", fake_etl)
    monkeypatch.setattr(run_store_job, "run_reporting_for_store", fake_report)
    monkeypatch.setattr(run_store_job, "complete_job_run", fake_complete)

    monkeypatch.setattr(sys, "argv", ["run_store_job.py", "--shop-domain", "store-a.myshopify.com"])
    run_store_job.main()

    assert calls["etl"] == 1
    assert calls["report"] == 1
    assert calls["complete"] == 1
