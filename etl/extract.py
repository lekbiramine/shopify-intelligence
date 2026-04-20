from etl.utils import paginated_get
from config.logging_config import get_logger
import requests

logger = get_logger(__name__)


def fetch_products(*, shop_domain: str, access_token: str) -> list:
    logger.info("Fetching products from Shopify...")
    return paginated_get(
        endpoint="products.json",
        key="products",
        params={"status": "active"},
        shop_domain=shop_domain,
        access_token=access_token,
    )


def fetch_customers(*, shop_domain: str, access_token: str) -> list:
    logger.info("Fetching customers from Shopify...")
    try:
        return paginated_get(
            endpoint="customers.json",
            key="customers",
            shop_domain=shop_domain,
            access_token=access_token,
        )
    except requests.HTTPError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 403:
            logger.warning(
                "Customers API denied for %s (HTTP 403). Continuing without customer records.",
                shop_domain,
            )
            return []
        raise


def fetch_orders(*, shop_domain: str, access_token: str) -> list:
    logger.info("Fetching orders from Shopify...")
    try:
        return paginated_get(
            endpoint="orders.json",
            key="orders",
            params={"status": "any"},
            shop_domain=shop_domain,
            access_token=access_token,
        )
    except requests.HTTPError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 403:
            logger.warning(
                "Orders REST API denied for %s (HTTP 403). Falling back to GraphQL orders query.",
                shop_domain,
            )
            return _fetch_orders_graphql(shop_domain=shop_domain, access_token=access_token)
        raise


def fetch_inventory_levels(inventory_item_ids: list, *, shop_domain: str, access_token: str) -> list:
    """
    Shopify requires inventory_item_ids to fetch inventory levels.
    Accepts a list of inventory_item_ids and fetches in batches of 50 (Shopify limit).
    """
    logger.info("Fetching inventory levels from Shopify...")
    all_levels = []
    batch_size = 50

    for i in range(0, len(inventory_item_ids), batch_size):
        batch = inventory_item_ids[i: i + batch_size]
        ids_str = ",".join(str(id) for id in batch)
        levels = paginated_get(
            endpoint="inventory_levels.json",
            key="inventory_levels",
            params={"inventory_item_ids": ids_str},
            shop_domain=shop_domain,
            access_token=access_token,
        )
        all_levels.extend(levels)
        logger.debug(f"Fetched inventory batch {i // batch_size + 1}")

    logger.info(f"Total inventory levels fetched: {len(all_levels)}")
    return all_levels


def _parse_gid_int(gid: str | None) -> int | None:
    value = (gid or "").strip()
    if not value:
        return None
    tail = value.rsplit("/", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return None


def _fetch_orders_graphql(*, shop_domain: str, access_token: str) -> list[dict]:
    """
    REST orders/customers can be blocked by protected customer data restrictions.
    This GraphQL fallback only requests non-protected order fields.
    """
    url = f"https://{shop_domain}/admin/api/2026-04/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    query = """
    query OrdersPage($cursor: String) {
      orders(first: 100, after: $cursor, sortKey: CREATED_AT, reverse: true) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            legacyResourceId
            createdAt
            updatedAt
            displayFinancialStatus
            displayFulfillmentStatus
            currentSubtotalPriceSet { shopMoney { amount } }
            currentTotalPriceSet { shopMoney { amount } }
            currentTotalDiscountsSet { shopMoney { amount } }
            lineItems(first: 100) {
              edges {
                node {
                  id
                  title
                  quantity
                  discountedUnitPriceSet { shopMoney { amount } }
                  variant {
                    id
                    legacyResourceId
                    product { legacyResourceId }
                  }
                }
              }
            }
          }
        }
      }
    }
    """

    results: list[dict] = []
    cursor = None
    while True:
        response = requests.post(
            url,
            headers=headers,
            json={"query": query, "variables": {"cursor": cursor}},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json() or {}
        if payload.get("errors"):
            raise RuntimeError(f"Shopify GraphQL orders query failed: {payload['errors']}")
        orders_block = (((payload.get("data") or {}).get("orders")) or {})
        edges = orders_block.get("edges") or []
        for edge in edges:
            node = (edge or {}).get("node") or {}
            order_id = node.get("legacyResourceId")
            if order_id is None:
                order_id = _parse_gid_int(node.get("id"))
            line_items = []
            for li_edge in ((node.get("lineItems") or {}).get("edges") or []):
                li = (li_edge or {}).get("node") or {}
                variant = li.get("variant") or {}
                unit_price = ((((li.get("discountedUnitPriceSet") or {}).get("shopMoney")) or {}).get("amount")) or 0
                quantity = int(li.get("quantity") or 0)
                line_items.append(
                    {
                        "id": _parse_gid_int(li.get("id")),
                        "product_id": variant.get("product", {}).get("legacyResourceId"),
                        "variant_id": variant.get("legacyResourceId") or _parse_gid_int(variant.get("id")),
                        "title": li.get("title"),
                        "quantity": quantity,
                        "price": float(unit_price),
                        "total_discount": 0,
                        "vendor": None,
                    }
                )

            results.append(
                {
                    "id": order_id,
                    "customer": None,
                    "email": None,
                    "total_price": (((node.get("currentTotalPriceSet") or {}).get("shopMoney")) or {}).get("amount") or 0,
                    "subtotal_price": (((node.get("currentSubtotalPriceSet") or {}).get("shopMoney")) or {}).get("amount") or 0,
                    "total_discounts": (((node.get("currentTotalDiscountsSet") or {}).get("shopMoney")) or {}).get("amount") or 0,
                    "financial_status": node.get("displayFinancialStatus"),
                    "fulfillment_status": node.get("displayFulfillmentStatus"),
                    "created_at": node.get("createdAt"),
                    "updated_at": node.get("updatedAt"),
                    "line_items": [li for li in line_items if li.get("id")],
                }
            )

        page_info = orders_block.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info("Fetched %s orders via GraphQL fallback.", len(results))
    return [order for order in results if order.get("id")]