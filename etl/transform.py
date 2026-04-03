from config.logging_config import get_logger

logger = get_logger(__name__)


def transform_products(raw_products: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Transforms raw Shopify products into clean products and variants records.
    Returns a tuple of (products, variants).
    """
    if not raw_products:
        logger.warning("No products to transform.")
        return [], []

    logger.info("Transforming products...")
    products = []
    variants = []

    for p in raw_products:
        products.append({
            "id": p["id"],
            "title": p.get("title"),
            "vendor": p.get("vendor"),
            "product_type": p.get("product_type"),
            "status": p.get("status"),
            "created_at": p.get("created_at"),
            "updated_at": p.get("updated_at"),
        })

        for v in p.get("variants", []):
            variants.append({
                "id": v["id"],
                "product_id": p["id"],
                "title": v.get("title"),
                "sku": v.get("sku"),
                "price": float(v.get("price", 0)),
                "inventory_quantity": v.get("inventory_quantity", 0),
                "updated_at": v.get("updated_at"),
            })

    logger.info(f"Transformed {len(products)} products and {len(variants)} variants.")
    return products, variants


def transform_customers(raw_customers: list[dict]) -> list[dict]:
    if not raw_customers:
        logger.warning("No customers to transform.")
        return []

    logger.info("Transforming customers...")
    customers = []

    for c in raw_customers:
        customers.append({
            "id": c["id"],
            "email": c.get("email"),
            "first_name": c.get("first_name"),
            "last_name": c.get("last_name"),
            "orders_count": c.get("orders_count", 0),
            "total_spent": float(c.get("total_spent", 0)),
            "created_at": c.get("created_at"),
            "updated_at": c.get("updated_at"),
        })

    logger.info(f"Transformed {len(customers)} customers.")
    return customers


def transform_orders(raw_orders: list[dict]) -> tuple[list[dict], list[dict]]:
    """
    Transforms raw Shopify orders into clean orders and order_items records.
    Returns a tuple of (orders, order_items).
    """
    if not raw_orders:
        logger.warning("No orders to transform.")
        return [], []

    logger.info("Transforming orders...")
    orders = []
    order_items = []

    for o in raw_orders:
        orders.append({
            "id": o["id"],
            "customer_id": o.get("customer", {}).get("id") if o.get("customer") else None,
            "email": o.get("email"),
            "total_price": float(o.get("total_price", 0)),
            "subtotal_price": float(o.get("subtotal_price", 0)),
            "total_discounts": float(o.get("total_discounts", 0)),
            "financial_status": o.get("financial_status"),
            "fulfillment_status": o.get("fulfillment_status"),
            "created_at": o.get("created_at"),
            "updated_at": o.get("updated_at"),
        })

        for item in o.get("line_items", []):
            order_items.append({
                "id": item["id"],
                "order_id": o["id"],
                "product_id": item.get("product_id"),
                "variant_id": item.get("variant_id"),
                "title": item.get("title"),
                "quantity": item.get("quantity", 0),
                "price": float(item.get("price", 0)),
                "total_discount": float(item.get("total_discount", 0)),
                "vendor": item.get("vendor"),
            })

    logger.info(f"Transformed {len(orders)} orders and {len(order_items)} order items.")
    return orders, order_items


def transform_inventory(raw_inventory: list[dict]) -> list[dict]:
    if not raw_inventory:
        logger.warning("No inventory to transform.")
        return []

    logger.info("Transforming inventory levels...")
    inventory = []

    for i in raw_inventory:
        inventory.append({
            "variant_id": i.get("variant_id"),
            "inventory_item_id": i.get("inventory_item_id"),
            "location_id": i.get("location_id"),
            "available": i.get("available", 0),
        })

    logger.info(f"Transformed {len(inventory)} inventory records.")
    return inventory