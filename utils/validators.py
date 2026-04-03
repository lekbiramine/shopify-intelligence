from config.logging_config import get_logger

logger = get_logger(__name__)


def validate_product(product: dict) -> bool:
    required_fields = ["id", "title"]
    return _validate_record(product, required_fields, "Product")


def validate_variant(variant: dict) -> bool:
    required_fields = ["id", "product_id", "price"]
    return _validate_record(variant, required_fields, "Variant")


def validate_customer(customer: dict) -> bool:
    required_fields = ["id"]
    return _validate_record(customer, required_fields, "Customer")


def validate_order(order: dict) -> bool:
    required_fields = ["id", "total_price", "financial_status"]
    return _validate_record(order, required_fields, "Order")


def validate_order_item(item: dict) -> bool:
    required_fields = ["id", "order_id", "quantity", "price"]
    return _validate_record(item, required_fields, "OrderItem")


def validate_inventory(inventory: dict) -> bool:
    required_fields = ["variant_id", "inventory_item_id", "location_id"]
    return _validate_record(inventory, required_fields, "Inventory")


def _validate_record(record: dict, required_fields: list[str], label: str) -> bool:
    """
    Checks that all required fields are present and not None.
    Returns True if valid, False otherwise.
    """
    missing = [f for f in required_fields if record.get(f) is None]
    if missing:
        logger.warning(f"Invalid {label} record — missing fields: {missing} | record: {record}")
        return False
    return True