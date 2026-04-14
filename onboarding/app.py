import hashlib
import hmac
import os
import secrets
import time
from collections.abc import Sequence
from pathlib import Path
from urllib.parse import parse_qsl, quote, urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from config.logging_config import get_logger
from db.queries import get_store_by_domain, update_store_contact_email, upsert_store_connection
from reporting.email_sender import send_email
from reporting.pdf_report import create_report_pdf
from reporting.templates import get_email_subject
from analytics.summary import build_summary

logger = get_logger(__name__)

app = FastAPI(title="Shopify Store Onboarding")
SESSION_SECRET = os.getenv("ONBOARDING_SESSION_SECRET") or secrets.token_hex(32)
app.add_middleware(SessionMiddleware, secret_key=SESSION_SECRET, same_site="lax", https_only=False)
STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Load .env for local dev so OAuth vars resolve
load_dotenv()

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET", "")
SHOPIFY_APP_BASE_URL = os.getenv("SHOPIFY_APP_BASE_URL", "")
SHOPIFY_SCOPES = os.getenv("SHOPIFY_SCOPES", "read_products,read_customers,read_orders,read_inventory")
SHOPIFY_API_VERSION = os.getenv("SHOPIFY_API_VERSION", "2025-01")


def _ensure_oauth_env() -> None:
    missing = [
        key
        for key, value in {
            "SHOPIFY_API_KEY": SHOPIFY_API_KEY,
            "SHOPIFY_API_SECRET": SHOPIFY_API_SECRET,
            "SHOPIFY_APP_BASE_URL": SHOPIFY_APP_BASE_URL,
        }.items()
        if not value
    ]
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing OAuth env vars: {missing}")


def _normalize_shop_domain(shop: str) -> str:
    value = (shop or "").strip().lower()
    value = value.replace("https://", "").replace("http://", "").strip("/")
    if not value.endswith(".myshopify.com"):
        raise HTTPException(status_code=400, detail="Use a valid *.myshopify.com domain")
    return value


def _build_state(shop_domain: str) -> str:
    nonce = secrets.token_hex(8)
    issued_at = str(int(time.time()))
    payload = f"{shop_domain}|{nonce}|{issued_at}"
    signature = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}|{signature}"


def _validate_state(state: str, expected_shop: str) -> bool:
    parts = (state or "").split("|")
    if len(parts) != 4:
        return False
    shop, nonce, issued_at, signature = parts
    if not nonce or shop != expected_shop:
        return False
    payload = f"{shop}|{nonce}|{issued_at}"
    expected_sig = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return False
    # 10 minute max state age
    try:
        return int(time.time()) - int(issued_at) <= 600
    except ValueError:
        return False


def _verify_shopify_hmac(params: dict[str, str]) -> bool:
    """
    Shopify signs the full query string (all params) excluding `hmac` and `signature`.
    If we only include a subset (e.g. shop/code/state) verification will fail.
    """
    hmac_received = (params.get("hmac") or "").strip()
    if not hmac_received:
        return False

    filtered = {k: v for k, v in params.items() if k not in {"hmac", "signature"}}
    message = "&".join(f"{k}={filtered[k]}" for k in sorted(filtered))
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, hmac_received)


def _verify_shopify_hmac_items(items: Sequence[tuple[str, str]]) -> bool:
    """
    Verify Shopify HMAC from query-param items (supports duplicate keys).

    Shopify computes HMAC over all parameters except `hmac` and `signature`,
    sorted by key and encoded as a query string.
    """
    hmac_received = ""
    filtered: list[tuple[str, str]] = []
    for k, v in items:
        if k == "hmac":
            hmac_received = (v or "").strip()
            continue
        if k == "signature":
            continue
        filtered.append((k, v))

    if not hmac_received:
        return False

    filtered.sort(key=lambda kv: kv[0])
    message = urlencode(filtered, doseq=True, quote_via=quote)
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, hmac_received)


def _verify_shopify_hmac_from_raw_query(raw_query: str) -> bool:
    """
    Verify Shopify HMAC from the *raw* query string.

    This avoids mismatches from decoding + re-encoding parameters (e.g. %7C vs |),
    and matches common reference implementations that start from the raw query.
    """
    # parse_qsl supports duplicate keys and handles percent-decoding
    pairs = parse_qsl(raw_query, keep_blank_values=True, strict_parsing=False)

    hmac_received = ""
    filtered: list[tuple[str, str]] = []
    for k, v in pairs:
        if k == "hmac":
            hmac_received = (v or "").strip()
            continue
        if k == "signature":
            continue
        filtered.append((k, v))

    if not hmac_received:
        return False

    # Shopify's reference implementations typically build the HMAC message from the
    # *decoded* key/value pairs, joined as `k=v` and sorted by key.
    # Re-encoding here (e.g. %7C vs |) can cause mismatches across frameworks.
    filtered.sort(key=lambda kv: (kv[0], kv[1]))
    message = "&".join(f"{k}={v}" for k, v in filtered)
    digest = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(digest, hmac_received)


def _connect_page_html(message: str = "", message_kind: str = "success") -> str:
    message_html = ""
    if message:
        css = "ok" if message_kind == "success" else "err"
        message_html = f'<div class="notice {css}"><span class="dot"></span><div>{message}</div></div>'
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Connect Your Shopify Store</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <div class="shell">
      <header class="topbar">
        <div class="brand">
          <div class="mark" aria-hidden="true"></div>
          <div>
            <h1>Shopify Store Intelligence</h1>
            <p class="subtitle">Connect your store and email reports on demand</p>
          </div>
        </div>
      </header>
      <main class="card">
        <div class="grid">
          <section class="panel">
            <h2 class="title">Connect your store</h2>
            <p class="lead">Enter your store domain and the email address where you want to receive PDF reports.</p>
            <form action="/connect" method="post" autocomplete="on">
              <div class="field">
                <label for="shop">Shopify domain</label>
                <input id="shop" name="shop" type="text" placeholder="your-store.myshopify.com" inputmode="url" required />
                <div class="muted">We only accept <strong>*.myshopify.com</strong> domains.</div>
              </div>
              <div class="field">
                <label for="email">Email for reports</label>
                <input id="email" name="email" type="email" placeholder="owner@yourstore.com" autocomplete="email" required />
                <div class="muted">We’ll send reports to this address.</div>
              </div>
              <div class="actions">
                <button class="btn btn-primary" type="submit">Connect with Shopify</button>
              </div>
              {message_html}
            </form>
          </section>
          <aside class="panel">
            <div class="helpbox">
              <h3>What happens next</h3>
              <ul>
                <li>You’ll authorize access in Shopify (read-only scopes).</li>
                <li>We save your store connection securely in Postgres.</li>
                <li>You can send a PDF report anytime from the connected page.</li>
              </ul>
            </div>
          </aside>
        </div>
      </main>
    </div>
  </body>
</html>"""


def _connected_page_html(
    shop_domain: str,
    email: str,
    banner: str = "",
    banner_kind: str = "success",
    *,
    ask_for_email: bool = False,
) -> str:
    banner_html = ""
    if banner:
        css = "ok" if banner_kind == "success" else "err"
        banner_html = f'<div class="notice {css}"><span class="dot"></span><div>{banner}</div></div>'
    safe_shop = shop_domain or "your-store.myshopify.com"
    safe_email = email or ""
    email_field_html = ""
    if ask_for_email:
        email_field_html = f"""
        <div class="field">
          <label for="email">Email for reports</label>
          <input id="email" name="email" type="email" placeholder="owner@yourstore.com" value="{safe_email}" required />
          <div class="muted">We’ll save this for next time.</div>
        </div>
        """
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Store Connected</title>
    <link rel="stylesheet" href="/static/styles.css" />
  </head>
  <body>
    <div class="shell">
      <header class="topbar">
        <div class="brand">
          <div class="mark" aria-hidden="true"></div>
          <div>
            <h1>Shopify Store Intelligence</h1>
            <p class="subtitle">Store connected</p>
          </div>
        </div>
      </header>
      <main class="card">
        <div class="grid">
          <section class="panel">
            <h2 class="title">Store connected</h2>
            <p class="lead">Send a fresh PDF report to your email.</p>
            {banner_html}
            <div class="kv">
              <div class="row"><span class="k">Store</span><span class="v">{safe_shop}</span></div>
              <div class="row"><span class="k">Recipient</span><span class="v">{safe_email or "Not set"}</span></div>
            </div>
            <form action="/send-report" method="post" class="actions">
              <input type="hidden" name="shop" value="{safe_shop}" />
              {email_field_html}
              <button class="btn btn-primary" type="submit">Send email report now</button>
              <a class="btn btn-secondary" href="/">Connect another store</a>
            </form>
          </section>
          <aside class="panel">
            <div class="helpbox">
              <h3>Notes</h3>
              <ul>
                <li>If you don’t receive the email, check spam/junk.</li>
                <li>SMTP settings are read from <code>.env</code>.</li>
              </ul>
            </div>
          </aside>
        </div>
      </main>
    </div>
  </body>
</html>"""


@app.get("/", response_class=HTMLResponse)
def home() -> str:
    return _connect_page_html()


@app.get("/connect")
def connect_get(shop: str = Query(..., description="Store domain")) -> RedirectResponse:
    return _start_oauth(shop)


@app.post("/connect")
def connect_post(request: Request, shop: str = Form(...), email: str = Form(...)) -> RedirectResponse:
    request.session["contact_email"] = (email or "").strip()
    request.session["shop_domain"] = _normalize_shop_domain(shop)
    return _start_oauth(shop)


def _start_oauth(shop: str) -> RedirectResponse:
    _ensure_oauth_env()
    shop_domain = _normalize_shop_domain(shop)
    state = _build_state(shop_domain)
    redirect_uri = f"{SHOPIFY_APP_BASE_URL.rstrip('/')}/oauth/callback"
    query = urlencode(
        {
            "client_id": SHOPIFY_API_KEY,
            "scope": SHOPIFY_SCOPES,
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    auth_url = f"https://{shop_domain}/admin/oauth/authorize?{query}"
    return RedirectResponse(url=auth_url)


@app.get("/oauth/callback", response_class=HTMLResponse)
def oauth_callback(
    request: Request,
    shop: str = Query(...),
    code: str = Query(...),
    state: str = Query(...),
) -> str:
    """
    Important: Shopify will surface any 5xx here as a generic "Internal Server Error".
    For a smoother onboarding experience (and to avoid intermittent 5xx during reloads),
    we return an HTML page with the error message instead of raising unhandled exceptions.
    """
    try:
        _ensure_oauth_env()
        shop_domain = _normalize_shop_domain(shop)

        # Verify HMAC using *all* received query params (excluding `hmac` / `signature`)
        raw_query = request.scope.get("query_string", b"").decode("utf-8", errors="replace")
        if not _verify_shopify_hmac_from_raw_query(raw_query):
            logger.warning("Invalid Shopify HMAC for query: %s", raw_query)
            return _connect_page_html(message="Error: Invalid Shopify HMAC. Please retry Connect.", message_kind="error")
        if not _validate_state(state, shop_domain):
            return _connect_page_html(message="Error: Invalid or expired state. Please retry Connect.", message_kind="error")

        token_url = f"https://{shop_domain}/admin/oauth/access_token"
        payload = {
            "client_id": SHOPIFY_API_KEY,
            "client_secret": SHOPIFY_API_SECRET,
            "code": code,
        }
        response = requests.post(token_url, json=payload, timeout=30)
        response.raise_for_status()
        token_data = response.json()

        access_token = token_data.get("access_token")
        scope = token_data.get("scope")
        if not access_token:
            return _connect_page_html(message="Error: Shopify token exchange failed. Please retry Connect.", message_kind="error")

        contact_email = (request.session.get("contact_email") or "").strip() or None
        upsert_store_connection(
            shop_domain=shop_domain,
            access_token=access_token,
            scope=scope,
            contact_email=contact_email,
        )

        logger.info(f"Store connected via OAuth: {shop_domain}")
        request.session["shop_domain"] = shop_domain
        return RedirectResponse(url="/connected", status_code=303)
    except requests.RequestException as exc:
        logger.exception("Shopify token exchange failed")
        return _connect_page_html(message=f"Error: Token exchange failed. ({exc})", message_kind="error")
    except Exception as exc:
        logger.exception("Unhandled error in oauth_callback")
        return _connect_page_html(message=f"Error: {exc}", message_kind="error")


@app.get("/connected", response_class=HTMLResponse)
def connected(request: Request) -> str:
    shop_domain = (request.session.get("shop_domain") or "").strip()
    contact_email = (request.session.get("contact_email") or "").strip()
    if not shop_domain:
        return _connect_page_html(message="Please connect your store first.", message_kind="error")
    if not contact_email:
        # fallback from DB if session missing
        store = get_store_by_domain(shop_domain)
        contact_email = (store or {}).get("contact_email") or ""
    return _connected_page_html(shop_domain=shop_domain, email=contact_email, ask_for_email=not bool(contact_email))


@app.post("/send-report", response_class=HTMLResponse)
def send_report(request: Request, shop: str = Form(...), email: str | None = Form(default=None)) -> str:
    shop_domain = _normalize_shop_domain(shop)
    store = get_store_by_domain(shop_domain) or {}
    to_addr = (email or "").strip()
    if not to_addr:
        to_addr = (store.get("contact_email") or request.session.get("contact_email") or "").strip()
    if not to_addr:
        return _connected_page_html(
            shop_domain,
            "",
            banner="Missing email address for reports.",
            banner_kind="error",
            ask_for_email=True,
        )

    # Persist email for future use
    try:
        update_store_contact_email(shop_domain, to_addr)
        request.session["contact_email"] = to_addr
        request.session["shop_domain"] = shop_domain
    except Exception:
        logger.exception("Failed to persist contact email")

    summary = build_summary()
    pdf_path = create_report_pdf(summary)
    subject = get_email_subject()
    body = (
        "Your Store Intelligence report is attached as a PDF.\n\n"
        f"Store: {shop_domain}\n"
        f"Attachment: {pdf_path}"
    )
    send_email(subject, body, attachment_path=pdf_path, recipient=to_addr)
    return _connected_page_html(shop_domain, to_addr, banner="Email sent successfully.", banner_kind="success")
