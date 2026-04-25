from urllib.parse import parse_qsl, urlparse
import hashlib
import hmac
import os
from pathlib import Path
import sys

from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import onboarding.app as onboarding
from db.queries import (
    create_referral_code,
    deactivate_referral_code,
    get_referral_code_details,
    get_store_by_domain,
)


class _FakeTokenResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        return self._payload


def _shopify_hmac(secret: str, params: dict[str, str]) -> str:
    msg = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).hexdigest()


def main() -> None:
    code = "LIVE2026"
    partner = "Creator Live Test"
    shop = "live-ref-test.myshopify.com"
    recipient = "lekbiramine09@gmail.com"

    try:
        create_referral_code(code=code, partner_name=partner, discount_percent=20)
    except Exception:
        # Code likely already exists; continue.
        pass

    onboarding.fetch_access_scopes = lambda *_args, **_kwargs: [
        "read_products",
        "read_orders",
        "read_customers",
        "read_inventory",
    ]
    onboarding.requests.post = lambda *args, **kwargs: _FakeTokenResponse(
        {
            "access_token": os.getenv("SHOPIFY_ACCESS_TOKEN", "token_x"),
            "scope": "read_products,read_orders,read_customers,read_inventory",
        }
    )

    client = TestClient(onboarding.app)

    def run_flow(*, flow_shop: str, email: str | None, ref: str | None):
        params = {"shop": flow_shop}
        if email is not None:
            params["email"] = email
        if ref is not None:
            params["ref"] = ref
        install_resp = client.get("/install", params=params, follow_redirects=False)
        if install_resp.status_code not in (302, 307):
            raise RuntimeError(f"/install failed: {install_resp.status_code} {install_resp.text}")
        state = dict(parse_qsl(urlparse(install_resp.headers["location"]).query)).get("state", "")
        callback_params = {
            "shop": flow_shop,
            "code": "fake_oauth_code",
            "state": state,
        }
        callback_params["hmac"] = _shopify_hmac(onboarding.SHOPIFY_API_SECRET, callback_params)
        callback_resp = client.get("/oauth/callback", params=callback_params, follow_redirects=False)
        return install_resp, callback_resp, callback_params

    # Happy path with referral code.
    _, callback_resp, _ = run_flow(flow_shop=shop, email=recipient, ref=code)
    if callback_resp.status_code not in (302, 307):
        raise RuntimeError(f"/oauth/callback failed: {callback_resp.status_code} {callback_resp.text}")

    store = get_store_by_domain(shop) or {}
    details = get_referral_code_details(code) or {}
    linked = [row.get("shop_domain") for row in details.get("stores", [])]

    if store.get("referral_code_used") != code:
        raise RuntimeError(f"Store referral_code_used mismatch: {store.get('referral_code_used')}")
    if shop not in linked:
        raise RuntimeError(f"Store not linked under referral code. linked={linked}")

    # Without ref (regression check)
    no_ref_shop = "live-noref-test.myshopify.com"
    _, no_ref_callback, _ = run_flow(flow_shop=no_ref_shop, email=recipient, ref=None)
    if no_ref_callback.status_code not in (302, 307):
        raise RuntimeError(f"No-ref callback failed: {no_ref_callback.status_code} {no_ref_callback.text}")
    no_ref_store = get_store_by_domain(no_ref_shop) or {}
    if no_ref_store.get("referral_code_id"):
        raise RuntimeError("No-ref flow incorrectly attached a referral code.")

    # Invalid referral code should not crash or attach.
    invalid_shop = "live-invalid-ref.myshopify.com"
    _, invalid_callback, _ = run_flow(flow_shop=invalid_shop, email=recipient, ref="NOTREAL")
    if invalid_callback.status_code not in (302, 307):
        raise RuntimeError(f"Invalid-ref callback failed: {invalid_callback.status_code} {invalid_callback.text}")
    invalid_store = get_store_by_domain(invalid_shop) or {}
    if invalid_store.get("referral_code_id"):
        raise RuntimeError("Invalid ref incorrectly attached a referral code.")

    # Inactive referral code should not attach.
    inactive_code = "INACTIVE26"
    try:
        create_referral_code(code=inactive_code, partner_name="Inactive Creator", discount_percent=20)
    except Exception:
        pass
    deactivate_referral_code(inactive_code)
    inactive_shop = "live-inactive-ref.myshopify.com"
    _, inactive_callback, _ = run_flow(flow_shop=inactive_shop, email=recipient, ref=inactive_code)
    if inactive_callback.status_code not in (302, 307):
        raise RuntimeError(f"Inactive-ref callback failed: {inactive_callback.status_code} {inactive_callback.text}")
    inactive_store = get_store_by_domain(inactive_shop) or {}
    if inactive_store.get("referral_code_id"):
        raise RuntimeError("Inactive ref incorrectly attached a referral code.")

    # Missing email should still onboard.
    missing_email_shop = "live-no-email.myshopify.com"
    _, missing_email_callback, _ = run_flow(flow_shop=missing_email_shop, email=None, ref=code)
    if missing_email_callback.status_code not in (302, 307):
        raise RuntimeError(
            f"Missing-email callback failed: {missing_email_callback.status_code} {missing_email_callback.text}"
        )

    # Reused OAuth state should be rejected on second callback.
    _, reused_first_callback, reused_callback_params = run_flow(
        flow_shop="live-reused-state.myshopify.com",
        email=recipient,
        ref=code,
    )
    if reused_first_callback.status_code not in (302, 307):
        raise RuntimeError("Initial callback failed for reused-state check.")
    reused_second = client.get("/oauth/callback", params=reused_callback_params, follow_redirects=False)
    if reused_second.status_code != 400:
        raise RuntimeError(f"Reused state was not rejected. Status={reused_second.status_code}")

    # Expired OAuth state should be rejected.
    expired_payload = "live-expired-state.myshopify.com|nonce|1"
    expired_sig = hmac.new(
        onboarding.SHOPIFY_API_SECRET.encode("utf-8"),
        expired_payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    expired_state = f"{expired_payload}|{expired_sig}"
    expired_params = {
        "shop": "live-expired-state.myshopify.com",
        "code": "fake_oauth_code",
        "state": expired_state,
    }
    expired_params["hmac"] = _shopify_hmac(onboarding.SHOPIFY_API_SECRET, expired_params)
    expired_resp = client.get("/oauth/callback", params=expired_params, follow_redirects=False)
    if expired_resp.status_code != 400:
        raise RuntimeError(f"Expired state was not rejected. Status={expired_resp.status_code}")

    print("Referral onboarding live check passed.")
    print(f"Store: {shop}")
    print(f"Referral code: {code}")
    print(f"Stores linked to code: {details.get('store_count')}")


if __name__ == "__main__":
    main()
