from __future__ import annotations

import hashlib
import hmac
import os
from urllib.parse import parse_qsl

from starlette.requests import Request

from config.logging_config import get_logger

logger = get_logger(__name__)

# Not part of Shopify OAuth; injected by Vercel rewrites (e.g. /oauth/:path* → /api/index).
_HMAC_EXCLUDED_KEYS = frozenset({"hmac", "signature", "path"})


def shopify_client_secret() -> str:
    return (os.getenv("SHOPIFY_API_SECRET") or "").strip()


def _secret_prefix(value: str | None) -> str:
    trimmed = (value or "").strip()
    return trimmed[:4] if trimmed else "<empty>"


def _oauth_message_from_pairs(pairs: list[tuple[str, str]]) -> tuple[str, str]:
    hmac_received = ""
    filtered: list[tuple[str, str]] = []
    for key, value in pairs:
        if key in _HMAC_EXCLUDED_KEYS:
            if key == "hmac":
                hmac_received = (value or "").strip()
            continue
        filtered.append((key, value))

    filtered.sort(key=lambda kv: (kv[0], kv[1]))
    message = "&".join(f"{k}={v}" for k, v in filtered)
    return message, hmac_received


def _digest(secret: str, message: str) -> str:
    return hmac.new(secret.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()


def _pairs_from_raw_query(raw_query: str, *, keep_encoding: bool) -> list[tuple[str, str]]:
    if not raw_query:
        return []
    if keep_encoding:
        pairs: list[tuple[str, str]] = []
        for part in raw_query.split("&"):
            if not part:
                continue
            key, sep, value = part.partition("=")
            if not sep:
                pairs.append((key, ""))
            else:
                pairs.append((key, value))
        return pairs
    return parse_qsl(raw_query, keep_blank_values=True, strict_parsing=False)


def _pairs_from_request(request: Request) -> list[tuple[str, str]]:
    return list(request.query_params.multi_items())


def _raw_query_from_request(request: Request) -> str:
    raw = request.scope.get("query_string", b"")
    if isinstance(raw, bytes):
        raw_query = raw.decode("utf-8", errors="replace")
    else:
        raw_query = str(raw or "")
    if not raw_query and request.url.query:
        raw_query = str(request.url.query)
    return raw_query


def verify_oauth_callback_hmac(request: Request, *, secret: str | None = None) -> bool:
    """
    Verify Shopify OAuth redirect HMAC (authorization code grant callback).
    Shopify signs all query params except hmac/signature.
    """
    client_secret = (secret or shopify_client_secret()).strip()
    if not client_secret:
        logger.error("OAuth HMAC verification failed: SHOPIFY_API_SECRET is not set")
        return False

    raw_query = _raw_query_from_request(request)
    attempts: list[tuple[str, list[tuple[str, str]]]] = [
        ("raw_decoded", _pairs_from_raw_query(raw_query, keep_encoding=False)),
        ("query_params", _pairs_from_request(request)),
        ("raw_encoded", _pairs_from_raw_query(raw_query, keep_encoding=True)),
    ]

    for label, pairs in attempts:
        message, hmac_received = _oauth_message_from_pairs(pairs)
        if not hmac_received or not message:
            continue
        computed = _digest(client_secret, message)
        if hmac.compare_digest(computed, hmac_received):
            logger.info("OAuth HMAC verified via %s", label)
            return True

    # Log once for debugging (no secrets / full codes in logs).
    _, last_hmac = _oauth_message_from_pairs(attempts[0][1] if attempts else [])
    last_message = _oauth_message_from_pairs(attempts[0][1])[0] if attempts else ""
    computed = _digest(client_secret, last_message) if last_message else ""
    logger.warning(
        "OAuth HMAC mismatch: secret_prefix=%s received_prefix=%s computed_prefix=%s param_keys=%s",
        _secret_prefix(client_secret),
        (last_hmac or "")[:8],
        computed[:8],
        sorted({k for k, _ in attempts[0][1]} if attempts else []),
    )
    return False
