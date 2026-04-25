from unittest.mock import patch
from analytics.inventory import (
    get_low_stock_products,
    get_critical_stock_products,
    get_out_of_stock_products,
)
from analytics.customers import (
    get_churned_customers,
    get_loyal_customers,
    get_never_returned_customers,
)
from analytics.revenue import (
    get_high_return_rate_products,
    get_revenue_by_product,
    get_revenue_summary,
)
from analytics.anomalies import (
    get_duplicate_orders,
    get_orders_with_zero_value,
    get_abnormal_discount_orders,
    get_products_with_no_sales,
)
from analytics.summary import build_summary

STORE_ID = 1


# ─── Inventory Tests ─────────────────────────────────────────────────────────

def test_get_low_stock_products_returns_list():
    with patch("analytics.inventory.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_low_stock_products(STORE_ID)
        assert isinstance(result, list)


def test_get_critical_stock_products_returns_list():
    with patch("analytics.inventory.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_critical_stock_products(STORE_ID)
        assert isinstance(result, list)


def test_get_out_of_stock_products_returns_list():
    with patch("analytics.inventory.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_out_of_stock_products(STORE_ID)
        assert isinstance(result, list)


# ─── Customer Tests ──────────────────────────────────────────────────────────

def test_get_churned_customers_returns_list():
    with patch("analytics.customers.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_churned_customers(STORE_ID)
        assert isinstance(result, list)


def test_get_loyal_customers_returns_list():
    with patch("analytics.customers.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_loyal_customers(STORE_ID)
        assert isinstance(result, list)


def test_get_never_returned_customers_returns_list():
    with patch("analytics.customers.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_never_returned_customers(STORE_ID)
        assert isinstance(result, list)


# ─── Revenue Tests ───────────────────────────────────────────────────────────

def test_get_high_return_rate_products_returns_list():
    with patch("analytics.revenue.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_high_return_rate_products(STORE_ID)
        assert isinstance(result, list)


def test_get_revenue_by_product_returns_list():
    with patch("analytics.revenue.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_revenue_by_product(STORE_ID)
        assert isinstance(result, list)


def test_get_revenue_summary_returns_dict():
    with patch("analytics.revenue.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchone.return_value = {
            "total_orders": 10,
            "unique_customers": 8,
            "gross_revenue": 1000.00,
            "total_discounts": 50.00,
            "net_revenue": 950.00,
            "avg_order_value": 100.00,
        }
        result = get_revenue_summary(STORE_ID)
        assert isinstance(result, dict)
        assert result["total_orders"] == 10


def test_get_revenue_summary_returns_empty_dict_on_none():
    with patch("analytics.revenue.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchone.return_value = None
        result = get_revenue_summary(STORE_ID)
        assert result == {}


# ─── Anomaly Tests ───────────────────────────────────────────────────────────

def test_get_duplicate_orders_returns_list():
    with patch("analytics.anomalies.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_duplicate_orders(STORE_ID)
        assert isinstance(result, list)


def test_get_orders_with_zero_value_returns_list():
    with patch("analytics.anomalies.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_orders_with_zero_value(STORE_ID)
        assert isinstance(result, list)


def test_get_abnormal_discount_orders_returns_list():
    with patch("analytics.anomalies.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_abnormal_discount_orders(STORE_ID)
        assert isinstance(result, list)


def test_get_products_with_no_sales_returns_list():
    with patch("analytics.anomalies.get_cursor") as mock_cursor:
        mock_cursor.return_value.__enter__.return_value.fetchall.return_value = []
        result = get_products_with_no_sales(STORE_ID)
        assert isinstance(result, list)


# ─── Summary Tests ───────────────────────────────────────────────────────────

def test_build_summary_structure():
    with patch("analytics.summary.build_insights", return_value=[]), \
         patch("analytics.summary.get_low_stock_products", return_value=[]), \
         patch("analytics.summary.get_critical_stock_products", return_value=[]), \
         patch("analytics.summary.get_out_of_stock_products", return_value=[]), \
         patch("analytics.summary.get_churned_customers", return_value=[]), \
         patch("analytics.summary.get_loyal_customers", return_value=[]), \
         patch("analytics.summary.get_never_returned_customers", return_value=[]), \
         patch("analytics.summary.get_revenue_summary", return_value={}), \
         patch("analytics.summary.get_revenue_by_product", return_value=[]), \
         patch("analytics.summary.get_high_return_rate_products", return_value=[]), \
         patch("analytics.summary.get_duplicate_orders", return_value=[]), \
         patch("analytics.summary.get_orders_with_zero_value", return_value=[]), \
         patch("analytics.summary.get_abnormal_discount_orders", return_value=[]), \
         patch("analytics.summary.get_products_with_no_sales", return_value=[]):

        result = build_summary(STORE_ID)

        assert "insights" in result
        assert "inventory" in result
        assert "customers" in result
        assert "revenue" in result
        assert "anomalies" in result
        assert "low_stock" in result["inventory"]
        assert "churned" in result["customers"]
        assert "summary" in result["revenue"]
        assert "duplicate_orders" in result["anomalies"]