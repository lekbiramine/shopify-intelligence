from etl.utils import paginated_get
from config.logging_config import get_logger
from config import constants
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
        customers = paginated_get(
            endpoint="customers.json",
            key="customers",
            shop_domain=shop_domain,
            access_token=access_token,
        )
        logger.info("Customers fetched via REST for %s: %s", shop_domain, len(customers))
        return customers
    except requests.HTTPError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 403:
            logger.warning(
                "Customers REST API denied for %s (HTTP 403). Falling back to GraphQL customers query.",
                shop_domain,
            )
            try:
                return _fetch_customers_graphql(shop_domain=shop_domain, access_token=access_token)
            except Exception as fallback_exc:
                logger.warning(
                    "Customers GraphQL fallback failed for %s: %s. Returning empty customer dataset.",
                    shop_domain,
                    fallback_exc,
                )
                return []
        raise


def fetch_orders(*, shop_domain: str, access_token: str) -> list:
    logger.info("Fetching orders from Shopify...")
    try:
        orders = paginated_get(
            endpoint="orders.json",
            key="orders",
            params={"status": "any"},
            shop_domain=shop_domain,
            access_token=access_token,
        )
        logger.info("Orders fetched via REST for %s: %s", shop_domain, len(orders))
        return orders
    except requests.HTTPError as exc:
        status_code = getattr(exc.response, "status_code", None)
        if status_code == 403:
            logger.warning(
                "Orders REST API denied for %s (HTTP 403). Falling back to GraphQL orders query.",
                shop_domain,
            )
            try:
                return _fetch_orders_graphql(shop_domain=shop_domain, access_token=access_token)
            except Exception as fallback_exc:
                logger.warning(
                    "Orders GraphQL fallback failed for %s: %s. Returning empty orders dataset.",
                    shop_domain,
                    fallback_exc,
                )
                return []
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
    url = f"https://{shop_domain}/admin/api/{constants.SHOPIFY_API_VERSION}/graphql.json"
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
        payload = _post_graphql(
            url=url,
            headers=headers,
            query=query,
            variables={"cursor": cursor},
            operation_name="orders",
            shop_domain=shop_domain,
        )
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

    logger.info("Orders fetched via GraphQL fallback for %s: %s", shop_domain, len(results))
    return [order for order in results if order.get("id")]


def _fetch_customers_graphql(*, shop_domain: str, access_token: str) -> list[dict]:
    """
    GraphQL fallback when customers REST endpoint is denied.
    """
    url = f"https://{shop_domain}/admin/api/{constants.SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    query = """
    query CustomersPage($cursor: String) {
      customers(first: 100, after: $cursor, sortKey: CREATED_AT, reverse: true) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            legacyResourceId
            email
            firstName
            lastName
            numberOfOrders
            amountSpent { amount }
            createdAt
            updatedAt
          }
        }
      }
    }
    """
    results: list[dict] = []
    cursor = None
    while True:
        payload = _post_graphql(
            url=url,
            headers=headers,
            query=query,
            variables={"cursor": cursor},
            operation_name="customers",
            shop_domain=shop_domain,
        )
        customers_block = (((payload.get("data") or {}).get("customers")) or {})
        edges = customers_block.get("edges") or []
        for edge in edges:
            node = (edge or {}).get("node") or {}
            customer_id = node.get("legacyResourceId") or _parse_gid_int(node.get("id"))
            if not customer_id:
                continue
            amount_spent = ((node.get("amountSpent") or {}).get("amount")) or 0
            results.append(
                {
                    "id": customer_id,
                    "email": node.get("email"),
                    "first_name": node.get("firstName"),
                    "last_name": node.get("lastName"),
                    "orders_count": int(node.get("numberOfOrders") or 0),
                    "total_spent": float(amount_spent),
                    "created_at": node.get("createdAt"),
                    "updated_at": node.get("updatedAt"),
                }
            )
        page_info = customers_block.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")
    logger.info("Customers fetched via GraphQL fallback for %s: %s", shop_domain, len(results))
    return results


def _post_graphql(
    *,
    url: str,
    headers: dict,
    query: str,
    variables: dict,
    operation_name: str,
    shop_domain: str,
) -> dict:
    response = requests.post(
        url,
        headers=headers,
        json={"query": query, "variables": variables},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json() or {}
    errors = payload.get("errors") or []
    if errors:
        logger.warning(
            "Shopify GraphQL %s query returned errors for %s: %s",
            operation_name,
            shop_domain,
            errors,
        )
        # ACCESS_DENIED usually indicates Protected Customer Data access is not approved.
        if any("ACCESS_DENIED" in str(err) for err in errors):
            raise RuntimeError(
                f"GraphQL {operation_name} ACCESS_DENIED for {shop_domain}. "
                "Check Shopify Protected Customer Data approval in Partner Dashboard."
            )
        raise RuntimeError(f"Shopify GraphQL {operation_name} query failed: {errors}")
    return payload