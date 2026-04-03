# Inventory thresholds
LOW_STOCK_THRESHOLD = 10          # units — flag product if below this
CRITICAL_STOCK_THRESHOLD = 5      # units — urgent alert
DAYS_OF_STOCK_WARNING = 7         # days — flag if stock runs out within this

# Customer thresholds
CHURN_DAYS_THRESHOLD = 90         # days — customer considered churned
HIGH_VALUE_ORDER_COUNT = 3        # orders — customer considered loyal

# Revenue thresholds
HIGH_RETURN_RATE_THRESHOLD = 0.20  # 20% — flag product if return rate exceeds this
MIN_PROFIT_MARGIN = 0.15           # 15% — flag product if margin drops below this

# API settings
SHOPIFY_API_VERSION = "2026-04"
SHOPIFY_MAX_RESULTS_PER_PAGE = 250  # Shopify max per request

# Email settings
EMAIL_SUBJECT = "Daily Store Intelligence Report"
EMAIL_MAX_RETRIES = 3

# Pipeline settings
PIPELINE_RETRY_ATTEMPTS = 3
PIPELINE_RETRY_DELAY = 5          # seconds