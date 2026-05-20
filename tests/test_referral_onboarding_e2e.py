import hashlib
import hmac
from urllib.parse import parse_qsl, urlencode, urlparse

import pytest
from fastapi.testclient import TestClient


def _shopify_hmac(secret: str, params: dict[str, str]) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


@pytest.fixture
def onboarding_env(monkeypatch):
    monkeypatch.setenv("DB_HOST", "localhost")
    monkeypatch.setenv("DB_NAME", "test")
    monkeypatch.setenv("DB_USER", "test")
    monkeypatch.setenv("DB_PASSWORD", "test")
    monkeypatch.setenv("SHOPIFY_API_KEY", "key")
    monkeypatch.setenv("SHOPIFY_API_SECRET", "secret")
    monkeypatch.setenv("SHOPIFY_APP_BASE_URL", "https://app.example.com")
    monkeypatch.setenv("SHOPIFY_SCOPES", "read_products,read_orders,read_customers,read_inventory")

    # Import after env values are set (db/settings validate at import time).
    import onboarding.app as onboarding

    onboarding.SHOPIFY_APP_BASE_URL = "https://app.example.com"
    onboarding.SHOPIFY_SCOPES = "read_products,read_orders,read_customers,read_inventory"
    return onboarding


def _install_then_callback(client: TestClient, onboarding, *, shop: str, email: str | None, ref: str | None):
    params = {"shop": shop}
    if email is not None:
        params["email"] = email
    if ref is not None:
        params["ref"] = ref
    install_response = client.get("/install", params=params, follow_redirects=False)
    assert install_response.status_code in (302, 307)

    redirect = install_response.headers["location"]
    state = dict(parse_qsl(urlparse(redirect).query))["state"]

    callback_params = {
        "shop": shop,
        "code": "oauth_code_123",
        "state": state,
    }
    callback_params["hmac"] = _shopify_hmac("secret", callback_params)
    callback_response = client.get("/oauth/callback", params=callback_params, follow_redirects=False)
    return install_response, callback_response


def test_onboarding_referral_e2e_and_edge_cases(monkeypatch, onboarding_env):
    onboarding = onboarding_env

    class FakeResponse:
        def __init__(self, payload, status_code=200):
            self._payload = payload
            self.status_code = status_code

        def raise_for_status(self):
            if self.status_code >= 400:
                raise RuntimeError("http error")

        def json(self):
            return self._payload

    state_store: dict[str, dict] = {}
    stores: dict[str, dict] = {}
    referrals = {
        "CREATOR20": {
            "id": 11,
            "code": "CREATOR20",
            "partner_name": "Creator A",
            "discount_percent": 20,
            "is_active": True,
        },
        "OFFLINE20": {
            "id": 22,
            "code": "OFFLINE20",
            "partner_name": "Inactive",
            "discount_percent": 20,
            "is_active": False,
        },
    }
    store_referrals: dict[str, dict] = {}

    def fake_create_oauth_state(state_hash: str, shop_domain: str, ttl_seconds: int = 600) -> None:
        state_store[state_hash] = {"shop": shop_domain, "consumed": False}

    def fake_consume_oauth_state(state_hash: str, shop_domain: str) -> bool:
        item = state_store.get(state_hash)
        if not item:
            return False
        if item["shop"] != shop_domain or item["consumed"]:
            return False
        item["consumed"] = True
        return True

    def fake_set_store_referral_code(shop_domain: str, referral_code: str | None) -> None:
        stores.setdefault(shop_domain, {"shop_domain": shop_domain})
        stores[shop_domain]["referral_code_used"] = referral_code

    def fake_upsert_store_contact_email(shop_domain: str, contact_email: str) -> None:
        stores.setdefault(shop_domain, {"shop_domain": shop_domain})
        stores[shop_domain]["contact_email"] = contact_email

    def fake_get_store_by_domain(shop_domain: str):
        return stores.get(shop_domain)

    def fake_get_active_referral_code_by_code(code: str):
        referral = referrals.get(code)
        if referral and referral["is_active"]:
            return referral
        return None

    def fake_upsert_store_connection(
        *,
        shop_domain: str,
        access_token: str,
        refresh_token=None,
        access_token_expires_at=None,
        scope=None,
        contact_email=None,
        referral_code_used=None,
        referral_code_id=None,
        api_key=None,
    ):
        stores.setdefault(shop_domain, {"shop_domain": shop_domain})
        stores[shop_domain].update(
            {
                "id": stores[shop_domain].get("id", len(stores) + 1),
                "access_token": access_token,
                "refresh_token": refresh_token,
                "access_token_expires_at": access_token_expires_at,
                "scope": scope,
                "contact_email": contact_email or stores[shop_domain].get("contact_email"),
                "referral_code_used": referral_code_used or stores[shop_domain].get("referral_code_used"),
                "referral_code_id": referral_code_id,
                "api_key": api_key,
            }
        )

    def fake_attach_store_referral(shop_domain: str, referral_code_id: int, referral_code: str) -> bool:
        store_referrals[shop_domain] = {
            "referral_code_id": referral_code_id,
            "referral_code_used": referral_code,
        }
        return True

    import db.queries as db_queries

    monkeypatch.setattr(db_queries, "create_oauth_state", fake_create_oauth_state)
    monkeypatch.setattr(db_queries, "consume_oauth_state", fake_consume_oauth_state)
    monkeypatch.setattr(db_queries, "set_store_referral_code", fake_set_store_referral_code)
    monkeypatch.setattr(db_queries, "upsert_store_contact_email", fake_upsert_store_contact_email)
    monkeypatch.setattr(db_queries, "get_store_by_domain", fake_get_store_by_domain)
    monkeypatch.setattr(db_queries, "get_active_referral_code_by_code", fake_get_active_referral_code_by_code)
    monkeypatch.setattr(db_queries, "upsert_store_connection", fake_upsert_store_connection)
    monkeypatch.setattr(db_queries, "attach_store_referral", fake_attach_store_referral)
    monkeypatch.setattr(onboarding, "fetch_access_scopes", lambda shop, token: ["read_products", "read_orders", "read_customers", "read_inventory"])
    monkeypatch.setattr(onboarding, "validate_read_only_scopes", lambda scopes: (True, "ok"))
    monkeypatch.setattr(onboarding.requests, "post", lambda *args, **kwargs: FakeResponse({"access_token": "token_x", "scope": "read_products,read_orders,read_customers,read_inventory"}))

    client = TestClient(onboarding.app)

    # Happy path with referral code.
    _, callback_response = _install_then_callback(
        client,
        onboarding,
        shop="shop-a.myshopify.com",
        email="owner@shop-a.com",
        ref="CREATOR20",
    )
    assert callback_response.status_code in (302, 307)
    assert stores["shop-a.myshopify.com"]["referral_code_used"] == "CREATOR20"
    assert stores["shop-a.myshopify.com"].get("api_key") == "key"
    assert store_referrals["shop-a.myshopify.com"]["referral_code_id"] == 11

    # Without ref parameter should still complete.
    _, callback_response_no_ref = _install_then_callback(
        client,
        onboarding,
        shop="shop-b.myshopify.com",
        email="owner@shop-b.com",
        ref=None,
    )
    assert callback_response_no_ref.status_code in (302, 307)
    assert "shop-b.myshopify.com" not in store_referrals

    # Missing email should not crash onboarding.
    _, callback_response_no_email = _install_then_callback(
        client,
        onboarding,
        shop="shop-c.myshopify.com",
        email=None,
        ref="CREATOR20",
    )
    assert callback_response_no_email.status_code in (302, 307)

    # Invalid referral code should not crash and should not attach.
    _, callback_invalid_ref = _install_then_callback(
        client,
        onboarding,
        shop="shop-d.myshopify.com",
        email="owner@shop-d.com",
        ref="DOESNOTEXIST",
    )
    assert callback_invalid_ref.status_code in (302, 307)
    assert "shop-d.myshopify.com" not in store_referrals

    # Inactive referral code should not attach.
    _, callback_inactive_ref = _install_then_callback(
        client,
        onboarding,
        shop="shop-e.myshopify.com",
        email="owner@shop-e.com",
        ref="OFFLINE20",
    )
    assert callback_inactive_ref.status_code in (302, 307)
    assert "shop-e.myshopify.com" not in store_referrals

    # Reused state must be rejected.
    install_response = client.get(
        "/install",
        params={"shop": "shop-f.myshopify.com", "email": "owner@shop-f.com", "ref": "CREATOR20"},
        follow_redirects=False,
    )
    state = dict(parse_qsl(urlparse(install_response.headers["location"]).query))["state"]
    callback_params = {"shop": "shop-f.myshopify.com", "code": "oauth_code_123", "state": state}
    callback_params["hmac"] = _shopify_hmac("secret", callback_params)
    first = client.get("/oauth/callback", params=callback_params, follow_redirects=False)
    second = client.get("/oauth/callback", params=callback_params, follow_redirects=False)
    assert first.status_code in (302, 307)
    assert second.status_code == 400
    assert "Invalid or expired state" in second.text

    # Expired state must be rejected (signed timestamp in the past).
    old_payload = "shop-g.myshopify.com|nonce|1|1"
    old_sig = hmac.new("secret".encode("utf-8"), old_payload.encode("utf-8"), hashlib.sha256).hexdigest()
    expired_state = f"{old_payload}|{old_sig}"
    expired_params = {"shop": "shop-g.myshopify.com", "code": "oauth_code_123", "state": expired_state}
    expired_params["hmac"] = _shopify_hmac("secret", expired_params)
    expired = client.get("/oauth/callback", params=expired_params)
    assert expired.status_code == 400
    assert "Invalid or expired state" in expired.text
