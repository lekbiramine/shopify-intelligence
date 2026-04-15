from etl.utils import paginated_get
from config.logging_config import get_logger

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
    return paginated_get(
        endpoint="customers.json",
        key="customers",
        shop_domain=shop_domain,
        access_token=access_token,
    )


def fetch_orders(*, shop_domain: str, access_token: str) -> list:
    logger.info("Fetching orders from Shopify...")
    return paginated_get(
        endpoint="orders.json",
        key="orders",
        params={"status": "any"},
        shop_domain=shop_domain,
        access_token=access_token,
    )


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