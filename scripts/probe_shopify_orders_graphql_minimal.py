"""
Probe whether Admin GraphQL exposes the Order type with read_orders (minimal query).

Usage (from repo root, with .env loaded):
  python scripts/probe_shopify_orders_graphql_minimal.py

Exits 0 if the query returns without ACCESS_DENIED on `orders`, non-zero otherwise.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import requests

from config import constants, settings
from config.logging_config import setup_logging, get_logger

setup_logging()
logger = get_logger(__name__)

MINIMAL_QUERY = """
query MinimalOrdersProbe {
  orders(first: 1) {
    edges {
      node {
        id
        createdAt
      }
    }
  }
}
"""


def main() -> int:
    settings.validate_shopify_pipeline_env()
    shop = (settings.SHOPIFY_STORE_URL or "").strip()
    token = (settings.SHOPIFY_ACCESS_TOKEN or "").strip()
    if not shop or not token:
        logger.error("SHOPIFY_STORE_URL and SHOPIFY_ACCESS_TOKEN are required.")
        return 2

    url = f"https://{shop}/admin/api/{constants.SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": token,
        "Content-Type": "application/json",
    }
    resp = requests.post(url, headers=headers, json={"query": MINIMAL_QUERY}, timeout=30)
    print(f"HTTP {resp.status_code}")
    try:
        payload = resp.json()
    except Exception:
        print(resp.text[:2000])
        return 1
    print(json.dumps(payload, indent=2)[:8000])

    errors = payload.get("errors") or []
    if any("ACCESS_DENIED" in str(e) for e in errors):
        logger.error("Order object: ACCESS_DENIED — read_orders alone is not enough for this app/install.")
        return 1
    if errors:
        logger.error("GraphQL returned errors (see JSON above).")
        return 1
    if not resp.ok:
        return 1
    logger.info("Minimal `orders` query succeeded (Order type is readable).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
