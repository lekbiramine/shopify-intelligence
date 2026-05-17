import hashlib
import hmac
from urllib.parse import urlencode

import pytest
from starlette.requests import Request

from utils.shopify_oauth_hmac import verify_oauth_callback_hmac


def _sign(secret: str, params: dict[str, str]) -> str:
    message = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _request_for_query(query: str) -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/oauth/callback",
        "query_string": query.encode("utf-8"),
        "headers": [],
    }
    return Request(scope)


def test_verify_oauth_callback_hmac_accepts_shopify_style_query():
    secret = "shpss_test_secret"
    state = "isaac-998084671.myshopify.com|nonce|1710000000|abcdef0123456789"
    params = {
        "code": "oauth_code_123",
        "shop": "isaac-998084671.myshopify.com",
        "state": state,
        "timestamp": "1710000000",
    }
    digest = _sign(secret, params)
    query = urlencode(params) + f"&hmac={digest}"
    request = _request_for_query(query)
    assert verify_oauth_callback_hmac(request, secret=secret) is True


def test_verify_oauth_callback_hmac_accepts_urlencoded_state():
    secret = "shpss_test_secret"
    state = "isaac-998084671.myshopify.com|nonce|1710000000|abcdef0123456789"
    params = {
        "code": "oauth_code_123",
        "shop": "isaac-998084671.myshopify.com",
        "state": state,
        "timestamp": "1710000000",
    }
    digest = _sign(secret, params)
    query = urlencode(params) + f"&hmac={digest}"
    request = _request_for_query(query)
    assert verify_oauth_callback_hmac(request, secret=secret) is True


def test_verify_oauth_callback_hmac_rejects_wrong_secret():
    params = {
        "code": "oauth_code_123",
        "shop": "isaac-998084671.myshopify.com",
        "state": "x",
        "timestamp": "1",
    }
    digest = _sign("correct", params)
    query = urlencode(params) + f"&hmac={digest}"
    request = _request_for_query(query)
    assert verify_oauth_callback_hmac(request, secret="wrong") is False
