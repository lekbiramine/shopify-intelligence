from analytics.inventory import (
    get_low_stock_products,
    get_critical_stock_products,
    get_out_of_stock_products,
)
from analytics.customers import (
    get_churned_customers,
    get_loyal_customers,
    get_never_returned_customers,
    get_customer_health_metrics,
)
from analytics.revenue import (
    get_high_return_rate_products,
    get_revenue_by_product,
    get_revenue_summary,
    get_order_volume_trend,
)
from analytics.anomalies import (
    get_duplicate_orders,
    get_orders_with_zero_value,
    get_abnormal_discount_orders,
    get_products_with_no_sales,
)
from analytics.insights import build_insights
from config.logging_config import get_logger

logger = get_logger(__name__)


def build_summary(store_id: int) -> dict:
    """
    Aggregates all analytics and insights into a single summary dict
    passed to the reporting layer.
    """
    logger.info("Building full analytics summary...")

    summary = {
        "insights": build_insights(store_id),
        "inventory": {
            "low_stock": get_low_stock_products(store_id),
            "critical_stock": get_critical_stock_products(store_id),
            "out_of_stock": get_out_of_stock_products(store_id),
        },
        "customers": {
            "churned": get_churned_customers(store_id),
            "loyal": get_loyal_customers(store_id),
            "never_returned": get_never_returned_customers(store_id),
            "health": get_customer_health_metrics(store_id),
        },
        "revenue": {
            "summary": get_revenue_summary(store_id),
            "by_product": get_revenue_by_product(store_id),
            "high_return_rate": get_high_return_rate_products(store_id),
            "trend": get_order_volume_trend(store_id),
        },
        "anomalies": {
            "duplicate_orders": get_duplicate_orders(store_id),
            "zero_value_orders": get_orders_with_zero_value(store_id),
            "abnormal_discounts": get_abnormal_discount_orders(store_id),
            "no_sales_products": get_products_with_no_sales(store_id),
        },
    }

    logger.info("Analytics summary built successfully.")
    return summary