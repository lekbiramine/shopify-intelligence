from pathlib import Path
import argparse
import sys

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from db.queries import get_store_by_domain
from utils.shopify_auth import fetch_access_scopes, normalize_shop_domain, validate_access_token
from config import constants


def _headers(access_token: str) -> dict:
    return {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }


def _rest_url(shop_domain: str, endpoint: str) -> str:
    return f"https://{shop_domain}/admin/api/{constants.SHOPIFY_API_VERSION}/{endpoint}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose Shopify token/scope/access issues.")
    parser.add_argument("--shop-domain", required=True, help="Store domain, e.g. my-store.myshopify.com")
    return parser.parse_args()


def _print_result(name: str, status: int, detail: str = "") -> None:
    suffix = f" | {detail}" if detail else ""
    print(f"{name}: HTTP {status}{suffix}")


def main() -> None:
    args = parse_args()
    shop_domain = normalize_shop_domain(args.shop_domain)
    store = get_store_by_domain(shop_domain) or {}
    token = (store.get("access_token") or "").strip()
    if not token:
        raise RuntimeError(f"No stored access token for {shop_domain}. Reinstall/onboard first.")

    print(f"Shop: {shop_domain}")
    print(f"Stored scope column: {(store.get('scope') or '').strip() or '<empty>'}")

    token_ok, token_detail = validate_access_token(shop_domain, token)
    print(f"Token valid: {token_ok} ({token_detail})")
    if not token_ok:
        return

    live_scopes = fetch_access_scopes(shop_domain, token)
    print(f"Live token scopes: {','.join(live_scopes)}")
    print(f"Has read_customers: {'read_customers' in set(live_scopes)}")
    print(f"Has read_orders: {'read_orders' in set(live_scopes)}")

    # REST checks
    try:
        r = requests.get(_rest_url(shop_domain, "customers.json"), headers=_headers(token), params={"limit": 1}, timeout=30)
        _print_result("REST customers", r.status_code, r.text[:160].replace("\n", " "))
    except Exception as exc:
        print(f"REST customers: ERROR | {exc}")

    try:
        r = requests.get(_rest_url(shop_domain, "orders.json"), headers=_headers(token), params={"status": "any", "limit": 1}, timeout=30)
        _print_result("REST orders", r.status_code, r.text[:160].replace("\n", " "))
    except Exception as exc:
        print(f"REST orders: ERROR | {exc}")

    graphql_url = _rest_url(shop_domain, "graphql.json")
    customer_query = """
    query {
      customers(first: 1) {
        edges { node { id legacyResourceId email } }
      }
    }
    """
    order_query = """
    query {
      orders(first: 1, sortKey: CREATED_AT, reverse: true) {
        edges { node { id legacyResourceId createdAt } }
      }
    }
    """
    for label, query in (("GraphQL customers", customer_query), ("GraphQL orders", order_query)):
        try:
            r = requests.post(graphql_url, headers=_headers(token), json={"query": query}, timeout=30)
            payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
            detail = str(payload.get("errors") or payload.get("data") or payload)[:200].replace("\n", " ")
            _print_result(label, r.status_code, detail)
        except Exception as exc:
            print(f"{label}: ERROR | {exc}")

    print("")
    print("If customers/orders return ACCESS_DENIED or HTTP 403 while scopes look correct,")
    print("this is usually Shopify Protected Customer Data access (Partner Dashboard approval).")


if __name__ == "__main__":
    main()
