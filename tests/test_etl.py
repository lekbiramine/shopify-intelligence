from unittest.mock import patch
from etl.extract import fetch_products, fetch_customers, fetch_orders
from etl.transform import (
    transform_products,
    transform_customers,
    transform_orders,
    transform_inventory,
)


# ─── Extract Tests ───────────────────────────────────────────────────────────

def test_fetch_products_returns_list():
    with patch("etl.extract.paginated_get", return_value=[{"id": 1, "title": "Test"}]):
        result = fetch_products()
        assert isinstance(result, list)
        assert len(result) == 1


def test_fetch_customers_returns_list():
    with patch("etl.extract.paginated_get", return_value=[{"id": 1, "email": "a@b.com"}]):
        result = fetch_customers()
        assert isinstance(result, list)


def test_fetch_orders_returns_list():
    with patch("etl.extract.paginated_get", return_value=[{"id": 1, "total_price": "99.99"}]):
        result = fetch_orders()
        assert isinstance(result, list)


# ─── Transform Tests ─────────────────────────────────────────────────────────

def test_transform_products_empty():
    products, variants = transform_products([])
    assert products == []
    assert variants == []


def test_transform_products_basic():
    raw = [{
        "id": 1001,
        "title": "Test Shirt",
        "vendor": "VendorA",
        "product_type": "Apparel",
        "status": "active",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "variants": [{
            "id": 2001,
            "title": "Small",
            "sku": "SHIRT-S",
            "price": "29.99",
            "inventory_quantity": 5,
            "updated_at": "2024-01-01T00:00:00+00:00",
        }]
    }]
    products, variants = transform_products(raw)
    assert len(products) == 1
    assert len(variants) == 1
    assert products[0]["id"] == 1001
    assert variants[0]["price"] == 29.99


def test_transform_customers_empty():
    result = transform_customers([])
    assert result == []


def test_transform_customers_basic():
    raw = [{
        "id": 5001,
        "email": "alice@example.com",
        "first_name": "Alice",
        "last_name": "Smith",
        "orders_count": 3,
        "total_spent": "150.00",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
    }]
    result = transform_customers(raw)
    assert len(result) == 1
    assert result[0]["email"] == "alice@example.com"
    assert result[0]["total_spent"] == 150.00


def test_transform_orders_empty():
    orders, items = transform_orders([])
    assert orders == []
    assert items == []


def test_transform_orders_basic():
    raw = [{
        "id": 6001,
        "customer": {"id": 5001},
        "email": "alice@example.com",
        "total_price": "89.99",
        "subtotal_price": "89.99",
        "total_discounts": "0.00",
        "financial_status": "paid",
        "fulfillment_status": "fulfilled",
        "created_at": "2024-01-01T00:00:00+00:00",
        "updated_at": "2024-01-01T00:00:00+00:00",
        "line_items": [{
            "id": 7001,
            "product_id": 1002,
            "variant_id": 2003,
            "title": "Test Shoes",
            "quantity": 1,
            "price": "89.99",
            "total_discount": "0.00",
            "vendor": "VendorB",
        }]
    }]
    orders, items = transform_orders(raw)
    assert len(orders) == 1
    assert len(items) == 1
    assert orders[0]["financial_status"] == "paid"
    assert items[0]["price"] == 89.99


def test_transform_inventory_empty():
    result = transform_inventory([])
    assert result == []


def test_transform_inventory_basic():
    raw = [{
        "variant_id": 2001,
        "inventory_item_id": 3001,
        "location_id": 4001,
        "available": 5,
    }]
    result = transform_inventory(raw)
    assert len(result) == 1
    assert result[0]["available"] == 5