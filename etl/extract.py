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
    """
    Standalone Customers REST/GraphQL is not used. Customer rows are built from order
    payloads (including GraphQL `orders { customer { ... } }`) so dev stores work
    without Protected Customer Data approval on the Customer object.
    """
    _ = shop_domain, access_token
    logger.info(
        "Skipping standalone customers API; customers will be derived from orders for %s.",
        shop_domain,
    )
    return []


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
                "Orders REST API denied for %s (HTTP 403). Checking GraphQL access to the Order object...",
                shop_domain,
            )
            if not _orders_root_accessible_via_graphql(shop_domain=shop_domain, access_token=access_token):
                logger.warning(
                    "GraphQL `orders` is not available (e.g. Order protected data / app not approved). "
                    "Order sync skipped. For local testing use: python scripts/seed_test_data.py --replace"
                )
                return []
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


def deduplicate_customers_from_orders(orders: list[dict]) -> list[dict]:
    """
    Build one customer record per Shopify customer id from embedded order.customer dicts.
    Merges duplicates seen across multiple orders (max orders_count / total_spent, first non-empty names).
    """
    by_id: dict[int, dict] = {}
    for o in orders or []:
        c = o.get("customer")
        if not c or c.get("id") is None:
            continue
        try:
            cid = int(c["id"])
        except (TypeError, ValueError):
            continue
        entry = {
            "id": cid,
            "email": c.get("email"),
            "first_name": c.get("first_name"),
            "last_name": c.get("last_name"),
            "orders_count": int(c.get("orders_count") or 0),
            "total_spent": float(c.get("total_spent") or 0),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        }
        if cid not in by_id:
            by_id[cid] = entry
            continue
        ex = by_id[cid]
        for field in ("email", "first_name", "last_name"):
            if not ex.get(field) and entry.get(field):
                ex[field] = entry[field]
        ex["orders_count"] = max(ex["orders_count"], entry["orders_count"])
        ex["total_spent"] = max(ex["total_spent"], entry["total_spent"])
        if entry.get("created_at") and (not ex.get("created_at") or entry["created_at"] < ex["created_at"]):
            ex["created_at"] = entry["created_at"]
        if entry.get("updated_at") and (not ex.get("updated_at") or entry["updated_at"] > ex["updated_at"]):
            ex["updated_at"] = entry["updated_at"]
    out = list(by_id.values())
    logger.info("Deduplicated customers from orders: %s unique customers.", len(out))
    return out


def _parse_gid_int(gid: str | None) -> int | None:
    value = (gid or "").strip()
    if not value:
        return None
    tail = value.rsplit("/", 1)[-1]
    if tail.isdigit():
        return int(tail)
    return None


def _orders_root_accessible_via_graphql(*, shop_domain: str, access_token: str) -> bool:
    """
    Return True if Admin API GraphQL exposes the Order type (minimal fields).
    When Shopify returns ACCESS_DENIED on `orders`, broad order sync is impossible
    without Partner / protected-data approval — callers should skip pagination.
    """
    url = f"https://{shop_domain}/admin/api/{constants.SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    query = """
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
    try:
        response = requests.post(url, headers=headers, json={"query": query}, timeout=30)
        response.raise_for_status()
    except requests.RequestException as exc:
        logger.warning("Minimal orders GraphQL probe request failed for %s: %s", shop_domain, exc)
        return False
    payload = response.json() or {}
    errors = payload.get("errors") or []
    if any("ACCESS_DENIED" in str(err) for err in errors):
        logger.warning(
            "Minimal orders GraphQL probe: ACCESS_DENIED on Order object for %s (read_orders is not sufficient).",
            shop_domain,
        )
        return False
    if errors:
        logger.warning("Minimal orders GraphQL probe returned errors for %s: %s", shop_domain, errors)
        return False
    return True


def _normalize_financial_status(raw: str | None) -> str | None:
    if not raw:
        return None
    key = str(raw).strip().upper()
    mapping = {
        "PAID": "paid",
        "PENDING": "pending",
        "AUTHORIZED": "authorized",
        "PARTIALLY_PAID": "partially_paid",
        "PARTIALLY_REFUNDED": "partially_refunded",
        "REFUNDED": "refunded",
        "VOIDED": "voided",
        "EXPIRED": "expired",
    }
    return mapping.get(key, str(raw).strip().lower())


def _normalize_fulfillment_status(raw: str | None) -> str | None:
    if not raw:
        return None
    return str(raw).strip().lower()


def _fetch_orders_graphql(*, shop_domain: str, access_token: str) -> list[dict]:
    """
    GraphQL orders with nested customer (allowed on many dev installs without Customer PCD),
    line items, and refunds. Replaces REST when orders.json returns 403.
    """
    url = f"https://{shop_domain}/admin/api/{constants.SHOPIFY_API_VERSION}/graphql.json"
    headers = {
        "X-Shopify-Access-Token": access_token,
        "Content-Type": "application/json",
    }
    query = """
    query OrdersPage($cursor: String) {
      orders(first: 250, after: $cursor, sortKey: CREATED_AT, reverse: true) {
        pageInfo { hasNextPage endCursor }
        edges {
          node {
            id
            legacyResourceId
            createdAt
            updatedAt
            displayFinancialStatus
            displayFulfillmentStatus
            customer {
              id
              legacyResourceId
              email
              firstName
              lastName
              numberOfOrders
              amountSpent { amount }
            }
            totalPriceSet { shopMoney { amount } }
            currentSubtotalPriceSet { shopMoney { amount } }
            currentTotalDiscountsSet { shopMoney { amount } }
            lineItems(first: 100) {
              edges {
                node {
                  id
                  quantity
                  discountedUnitPriceSet { shopMoney { amount } }
                  variant {
                    id
                    legacyResourceId
                    sku
                    product { id legacyResourceId title }
                  }
                }
              }
            }
            refunds {
              id
              createdAt
              refundLineItems(first: 50) {
                edges {
                  node {
                    quantity
                    lineItem { id }
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
            else:
                try:
                    order_id = int(order_id)
                except (TypeError, ValueError):
                    order_id = _parse_gid_int(node.get("id"))

            refund_qty_by_line: dict[int, int] = {}
            for ref in node.get("refunds") or []:
                for rli_edge in ((ref.get("refundLineItems") or {}).get("edges") or []):
                    rli = (rli_edge or {}).get("node") or {}
                    li_ref = rli.get("lineItem") or {}
                    li_id = _parse_gid_int(li_ref.get("id"))
                    if li_id is None:
                        continue
                    refund_qty_by_line[li_id] = refund_qty_by_line.get(li_id, 0) + int(rli.get("quantity") or 0)

            cust_raw = node.get("customer")
            customer_dict = None
            order_email = None
            if cust_raw:
                cid = cust_raw.get("legacyResourceId") or _parse_gid_int(cust_raw.get("id"))
                if cid:
                    amt = ((cust_raw.get("amountSpent") or {}).get("amount")) or 0
                    order_email = cust_raw.get("email")
                    customer_dict = {
                        "id": int(cid),
                        "email": cust_raw.get("email"),
                        "first_name": cust_raw.get("firstName"),
                        "last_name": cust_raw.get("lastName"),
                        "orders_count": int(cust_raw.get("numberOfOrders") or 0),
                        "total_spent": float(amt),
                        "created_at": None,
                        "updated_at": None,
                    }

            line_items = []
            for li_edge in ((node.get("lineItems") or {}).get("edges") or []):
                li = (li_edge or {}).get("node") or {}
                variant = li.get("variant") or {}
                product = variant.get("product") or {}
                li_id = _parse_gid_int(li.get("id"))
                if li_id is None:
                    continue
                unit_price = (
                    ((li.get("discountedUnitPriceSet") or {}).get("shopMoney") or {}).get("amount")
                ) or 0
                quantity = int(li.get("quantity") or 0)
                refunded = refund_qty_by_line.get(li_id, 0)
                net_qty = quantity - refunded
                if net_qty <= 0:
                    continue
                title = product.get("title")
                line_items.append(
                    {
                        "id": li_id,
                        "product_id": product.get("legacyResourceId") or _parse_gid_int(product.get("id")),
                        "variant_id": variant.get("legacyResourceId") or _parse_gid_int(variant.get("id")),
                        "title": title,
                        "quantity": net_qty,
                        "price": float(unit_price),
                        "total_discount": 0,
                        "vendor": None,
                    }
                )

            gross = ((node.get("totalPriceSet") or {}).get("shopMoney") or {}).get("amount")
            cur_total = ((node.get("currentTotalPriceSet") or {}).get("shopMoney") or {}).get("amount")
            total_price = gross or cur_total or 0
            results.append(
                {
                    "id": order_id,
                    "customer": customer_dict,
                    "email": order_email,
                    "total_price": total_price,
                    "subtotal_price": (((node.get("currentSubtotalPriceSet") or {}).get("shopMoney")) or {}).get(
                        "amount"
                    )
                    or 0,
                    "total_discounts": (((node.get("currentTotalDiscountsSet") or {}).get("shopMoney")) or {}).get(
                        "amount"
                    )
                    or 0,
                    "financial_status": _normalize_financial_status(node.get("displayFinancialStatus")),
                    "fulfillment_status": _normalize_fulfillment_status(node.get("displayFulfillmentStatus")),
                    "created_at": node.get("createdAt"),
                    "updated_at": node.get("updatedAt"),
                    "line_items": line_items,
                }
            )

        page_info = orders_block.get("pageInfo") or {}
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info.get("endCursor")

    logger.info("Orders fetched via GraphQL fallback for %s: %s", shop_domain, len(results))
    return [order for order in results if order.get("id")]


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