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
from analytics.insights import build_insights
from config.logging_config import get_logger

logger = get_logger(__name__)


def build_summary() -> dict:
    """
    Aggregates all analytics and insights into a single summary dict
    passed to the reporting layer.
    """
    logger.info("Building full analytics summary...")

    summary = {
        "insights": build_insights(),
        "inventory": {
            "low_stock": get_low_stock_products(),
            "critical_stock": get_critical_stock_products(),
            "out_of_stock": get_out_of_stock_products(),
        },
        "customers": {
            "churned": get_churned_customers(),
            "loyal": get_loyal_customers(),
            "never_returned": get_never_returned_customers(),
        },
        "revenue": {
            "summary": get_revenue_summary(),
            "by_product": get_revenue_by_product(),
            "high_return_rate": get_high_return_rate_products(),
        },
        "anomalies": {
            "duplicate_orders": get_duplicate_orders(),
            "zero_value_orders": get_orders_with_zero_value(),
            "abnormal_discounts": get_abnormal_discount_orders(),
            "no_sales_products": get_products_with_no_sales(),
        },
    }

    logger.info("Analytics summary built successfully.")
    return summary