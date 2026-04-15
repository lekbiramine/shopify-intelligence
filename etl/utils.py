import time
import requests
from config import settings, constants
from config.logging_config import get_logger

logger = get_logger(__name__)


def get_shopify_headers(access_token: str | None = None) -> dict:
    return {
        "X-Shopify-Access-Token": access_token or settings.SHOPIFY_ACCESS_TOKEN,
        "Content-Type": "application/json",
    }


def build_shopify_url(endpoint: str, shop_domain: str | None = None) -> str:
    domain = shop_domain or settings.SHOPIFY_STORE_URL
    return f"https://{domain}/admin/api/{constants.SHOPIFY_API_VERSION}/{endpoint}"


def paginated_get(endpoint: str, key: str, params: dict = None, *, shop_domain: str | None = None, access_token: str | None = None) -> list:
    """
    Fetches all pages from a Shopify endpoint using Link header pagination.
    
    :param endpoint: Shopify API endpoint e.g. 'orders.json'
    :param key: JSON key to extract from response e.g. 'orders'
    :param params: optional query parameters
    :return: flat list of all records across all pages
    """
    url = build_shopify_url(endpoint, shop_domain=shop_domain)
    headers = get_shopify_headers(access_token=access_token)
    results = []

    if params is None:
        params = {}
    params["limit"] = constants.SHOPIFY_MAX_RESULTS_PER_PAGE
    while url:
        try:
            response = requests.get(url, headers=headers, params=params)
            response.raise_for_status()
            data = response.json()
            page_results = data.get(key, [])
            results.extend(page_results)
            logger.debug(f"Fetched {len(page_results)} records from {url}")

            # Extract next page URL from Link header
            link_header = response.headers.get("Link", "")
            url = extract_next_url(link_header)

            # Clear params after first request — next URL already contains them
            params = {}

            # Respect Shopify rate limit
            time.sleep(0.5)

        except requests.exceptions.RequestException as e:
            logger.error(f"Shopify API request failed: {e}")
            raise

    logger.info(f"Total records fetched from '{key}': {len(results)}")
    return results


def extract_next_url(link_header: str) -> str | None:
    """
    Parses Shopify Link header to extract the next page URL.
    Example: <https://store.myshopify.com/admin/api/.../orders.json?page_info=xyz>; rel="next"
    """
    if not link_header:
        return None

    for part in link_header.split(","):
        if 'rel="next"' in part:
            url = part.strip().split(";")[0].strip()
            return url.strip("<>")

    return None