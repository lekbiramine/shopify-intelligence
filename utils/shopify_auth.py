from datetime import datetime, timedelta, timezone

import requests

from config import constants

READ_ONLY_SCOPES = {
    "read_products",
    "read_orders",
    "read_inventory",
    "read_customers",
}


def normalize_shop_domain(shop_domain: str) -> str:
    value = (shop_domain or "").strip().lower()
    value = value.replace("https://", "").replace("http://", "").strip("/")
    if not value.endswith(".myshopify.com"):
        raise ValueError("Use a valid *.myshopify.com domain")
    return value


def _shopify_url(shop_domain: str, endpoint: str) -> str:
    return f"https://{shop_domain}/admin/api/{constants.SHOPIFY_API_VERSION}/{endpoint}"


def _shopify_oauth_url(shop_domain: str, endpoint: str) -> str:
    return f"https://{shop_domain}/admin/oauth/{endpoint}"


def validate_access_token(shop_domain: str, access_token: str) -> tuple[bool, str]:
    """
    Validate token by calling shop metadata endpoint.
    Returns (is_valid, detail_message).
    """
    headers = {
        "X-Shopify-Access-Token": (access_token or "").strip(),
        "Content-Type": "application/json",
    }
    response = requests.get(_shopify_url(shop_domain, "shop.json"), headers=headers, timeout=20)
    if response.status_code == 401:
        return False, "Unauthorized token for this store."
    if response.status_code >= 400:
        return False, f"Shopify token validation failed: HTTP {response.status_code}"
    return True, "Token is valid."


def fetch_shop_display_name(shop_domain: str, access_token: str) -> str | None:
    """
    Fetches the merchant-facing store name from Shopify's shop metadata.
    """
    headers = {
        "X-Shopify-Access-Token": (access_token or "").strip(),
        "Content-Type": "application/json",
    }
    resp = requests.get(_shopify_url(shop_domain, "shop.json"), headers=headers, timeout=20)
    if resp.status_code >= 400:
        return None
    payload = resp.json() or {}
    shop = payload.get("shop") or {}
    name = str(shop.get("name") or "").strip()
    return name or None


def fetch_access_scopes(shop_domain: str, access_token: str) -> list[str]:
    """
    Returns granted scopes for the token.
    """
    headers = {
        "X-Shopify-Access-Token": (access_token or "").strip(),
        "Content-Type": "application/json",
    }

    # Preferred endpoint for installed app scopes.
    response = requests.get(_shopify_oauth_url(shop_domain, "access_scopes.json"), headers=headers, timeout=20)
    if response.status_code < 400:
        payload = response.json() or {}
        scopes = payload.get("access_scopes") or []
        parsed = sorted({(s.get("handle") or "").strip() for s in scopes if s.get("handle")})
        if parsed:
            return parsed

    # Fallback for tokens/stores where the OAuth endpoint isn't available.
    graphql_response = requests.post(
        _shopify_url(shop_domain, "graphql.json"),
        headers=headers,
        json={
            "query": """
            query {
              currentAppInstallation {
                accessScopes {
                  handle
                }
              }
            }
            """
        },
        timeout=20,
    )
    if graphql_response.status_code < 400:
        payload = graphql_response.json() or {}
        scopes = (
            (((payload.get("data") or {}).get("currentAppInstallation") or {}).get("accessScopes"))
            or []
        )
        parsed = sorted({(s.get("handle") or "").strip() for s in scopes if s.get("handle")})
        if parsed:
            return parsed

    # Final fallback: parse access scopes header from shop.json response.
    shop_response = requests.get(_shopify_url(shop_domain, "shop.json"), headers=headers, timeout=20)
    shop_response.raise_for_status()
    header_value = (shop_response.headers.get("X-Shopify-Access-Scopes") or "").strip()
    if header_value:
        return sorted({scope.strip() for scope in header_value.split(",") if scope.strip()})

    raise RuntimeError("Unable to read Shopify access scopes for this token.")


def validate_read_only_scopes(granted_scopes: list[str]) -> tuple[bool, str]:
    granted = set(granted_scopes or [])
    missing = READ_ONLY_SCOPES - granted
    write_scopes = sorted(scope for scope in granted if scope.startswith(("write_", "unauthenticated_write_")))

    if missing:
        return False, f"Missing required read scopes: {sorted(missing)}"
    if write_scopes:
        return False, f"Write scopes are not allowed: {write_scopes}"
    return True, "Scopes are read-only and valid."


def _oauth_access_token_url(shop_domain: str) -> str:
    return f"https://{shop_domain}/admin/oauth/access_token"


def refresh_access_token(
    shop_domain: str,
    refresh_token: str,
    *,
    client_id: str,
    client_secret: str,
) -> dict:
    """
    Refreshes an expiring Shopify access token.
    Returns dict with keys: access_token, refresh_token (optional), access_token_expires_at (optional).
    """
    api_key = (client_id or "").strip()
    api_secret = (client_secret or "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("Missing client_id/client_secret for token refresh.")
    if not (refresh_token or "").strip():
        raise RuntimeError("Missing refresh token for this store.")

    response = requests.post(
        _oauth_access_token_url(shop_domain),
        data={
            "client_id": api_key,
            "client_secret": api_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token.strip(),
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json() or {}
    next_access_token = (payload.get("access_token") or "").strip()
    if not next_access_token:
        raise RuntimeError("Shopify refresh response missing access_token.")

    expires_at = None
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            expires_at = None

    return {
        "access_token": next_access_token,
        "refresh_token": (payload.get("refresh_token") or "").strip() or None,
        "access_token_expires_at": expires_at,
    }


def migrate_non_expiring_offline_token(
    shop_domain: str,
    access_token: str,
    *,
    client_id: str,
    client_secret: str,
) -> dict:
    """
    One-time migration: exchange legacy non-expiring offline token for expiring offline token.
    """
    api_key = (client_id or "").strip()
    api_secret = (client_secret or "").strip()
    if not api_key or not api_secret:
        raise RuntimeError("Missing client_id/client_secret for token migration.")
    if not (access_token or "").strip():
        raise RuntimeError("Missing access token for migration.")

    response = requests.post(
        _oauth_access_token_url(shop_domain),
        data={
            "client_id": api_key,
            "client_secret": api_secret,
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subject_token": access_token.strip(),
            "subject_token_type": "urn:shopify:params:oauth:token-type:offline-access-token",
            "requested_token_type": "urn:shopify:params:oauth:token-type:offline-access-token",
            "expiring": "1",
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json() or {}
    next_access_token = (payload.get("access_token") or "").strip()
    if not next_access_token:
        raise RuntimeError("Shopify migration response missing access_token.")

    expires_at = None
    expires_in = payload.get("expires_in")
    if expires_in is not None:
        try:
            expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            expires_at = None

    return {
        "access_token": next_access_token,
        "refresh_token": (payload.get("refresh_token") or "").strip() or None,
        "access_token_expires_at": expires_at,
    }
