from unittest.mock import patch
import requests

from etl.extract import (
    deduplicate_customers_from_orders,
    fetch_products,
    fetch_customers,
    fetch_orders,
    _fetch_orders_graphql,
)
from etl.transform import (
    transform_products,
    transform_customers,
    transform_orders,
    transform_inventory,
)


# ─── Extract Tests ───────────────────────────────────────────────────────────

def test_fetch_products_returns_list():
    with patch("etl.extract.paginated_get", return_value=[{"id": 1, "title": "Test"}]):
        result = fetch_products(shop_domain="test-shop.myshopify.com", access_token="token")
        assert isinstance(result, list)
        assert len(result) == 1


def test_fetch_customers_returns_empty_list():
    result = fetch_customers(shop_domain="test-shop.myshopify.com", access_token="token")
    assert result == []


def test_deduplicate_customers_from_orders():
    raw_orders = [
        {
            "id": 1,
            "customer": {
                "id": 10,
                "email": "a@b.com",
                "first_name": "A",
                "last_name": "B",
                "orders_count": 2,
                "total_spent": 50.0,
            },
        },
        {
            "id": 2,
            "customer": {
                "id": 10,
                "email": "a@b.com",
                "first_name": "A",
                "last_name": "B",
                "orders_count": 3,
                "total_spent": 80.0,
            },
        },
    ]
    out = deduplicate_customers_from_orders(raw_orders)
    assert len(out) == 1
    assert out[0]["id"] == 10
    assert out[0]["orders_count"] == 3
    assert out[0]["total_spent"] == 80.0


def test_fetch_orders_returns_list():
    with patch("etl.extract.paginated_get", return_value=[{"id": 1, "total_price": "99.99"}]):
        result = fetch_orders(shop_domain="test-shop.myshopify.com", access_token="token")
        assert isinstance(result, list)


def test_fetch_orders_graphql_parses_customer_line_items_and_refunds():
    gql_page = {
        "data": {
            "orders": {
                "pageInfo": {"hasNextPage": False, "endCursor": None},
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/Order/9001",
                            "legacyResourceId": "9001",
                            "createdAt": "2024-06-01T00:00:00Z",
                            "updatedAt": "2024-06-01T00:00:00Z",
                            "displayFinancialStatus": "PAID",
                            "displayFulfillmentStatus": "FULFILLED",
                            "customer": {
                                "id": "gid://shopify/Customer/7001",
                                "legacyResourceId": "7001",
                                "email": "buyer@example.com",
                                "firstName": "Bo",
                                "lastName": "UGHT",
                                "numberOfOrders": 5,
                                "amountSpent": {"amount": "199.50"},
                            },
                            "totalPriceSet": {"shopMoney": {"amount": "49.99"}},
                            "currentSubtotalPriceSet": {"shopMoney": {"amount": "49.99"}},
                            "currentTotalDiscountsSet": {"shopMoney": {"amount": "0"}},
                            "lineItems": {
                                "edges": [
                                    {
                                        "node": {
                                            "id": "gid://shopify/LineItem/8001",
                                            "quantity": 3,
                                            "discountedUnitPriceSet": {"shopMoney": {"amount": "10.00"}},
                                            "variant": {
                                                "id": "gid://shopify/ProductVariant/5001",
                                                "legacyResourceId": "5001",
                                                "sku": "SKU-A",
                                                "product": {
                                                    "id": "gid://shopify/Product/4001",
                                                    "legacyResourceId": "4001",
                                                    "title": "Widget",
                                                },
                                            },
                                        }
                                    }
                                ]
                            },
                            "refunds": [
                                {
                                    "id": "gid://shopify/Refund/1",
                                    "createdAt": "2024-06-02T00:00:00Z",
                                    "refundLineItems": {
                                        "edges": [
                                            {
                                                "node": {
                                                    "quantity": 1,
                                                    "lineItem": {"id": "gid://shopify/LineItem/8001"},
                                                }
                                            }
                                        ]
                                    },
                                }
                            ],
                        }
                    }
                ],
            }
        }
    }

    with patch("etl.extract._post_graphql", return_value=gql_page):
        orders = _fetch_orders_graphql(shop_domain="test-shop.myshopify.com", access_token="t")
    assert len(orders) == 1
    o = orders[0]
    assert o["id"] == 9001
    assert o["customer"]["id"] == 7001
    assert o["customer"]["email"] == "buyer@example.com"
    assert o["financial_status"] == "paid"
    assert len(o["line_items"]) == 1
    assert o["line_items"][0]["quantity"] == 2
    assert o["line_items"][0]["title"] == "Widget"
    customers = deduplicate_customers_from_orders(orders)
    assert len(customers) == 1
    assert customers[0]["id"] == 7001


def test_fetch_orders_falls_back_to_graphql_on_403():
    http_error = requests.HTTPError(response=type("Resp", (), {"status_code": 403})())
    with (
        patch("etl.extract.paginated_get", side_effect=http_error),
        patch("etl.extract._orders_root_accessible_via_graphql", return_value=True),
        patch(
            "etl.extract._fetch_orders_graphql",
            return_value=[{"id": 1, "total_price": "99.99"}],
        ),
    ):
        result = fetch_orders(shop_domain="test-shop.myshopify.com", access_token="token")
        assert isinstance(result, list)
        assert len(result) == 1


def test_fetch_orders_returns_empty_when_graphql_order_root_denied():
    http_error = requests.HTTPError(response=type("Resp", (), {"status_code": 403})())
    with (
        patch("etl.extract.paginated_get", side_effect=http_error),
        patch("etl.extract._orders_root_accessible_via_graphql", return_value=False),
    ):
        result = fetch_orders(shop_domain="test-shop.myshopify.com", access_token="token")
        assert result == []


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