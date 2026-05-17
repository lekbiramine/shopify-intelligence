import hashlib
import html
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote_plus, urlencode

import requests
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from config import settings
from config.logging_config import get_logger
from modal_jobs.pipeline import spawn_store_pipeline_job
from utils.shopify_auth import (
    fetch_access_scopes,
    normalize_shop_domain,
    validate_read_only_scopes,
)
from utils.shopify_oauth_hmac import shopify_client_secret, verify_oauth_callback_hmac

logger = get_logger(__name__)
load_dotenv(override=False)

SHOPIFY_API_KEY = os.getenv("SHOPIFY_API_KEY", "")
SHOPIFY_API_SECRET = os.getenv("SHOPIFY_API_SECRET", "")


def _secret_prefix(value: str | None) -> str:
    trimmed = (value or "").strip()
    return trimmed[:4] if trimmed else "<empty>"


logger.info(
    "SHOPIFY_API_SECRET prefix at app load: os.getenv=%s module=%s",
    _secret_prefix(os.getenv("SHOPIFY_API_SECRET", "")),
    _secret_prefix(SHOPIFY_API_SECRET),
)

SHOPIFY_APP_BASE_URL = os.getenv("SHOPIFY_APP_BASE_URL", "")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
SECRET_KEY = os.getenv("SECRET_KEY", "")

app = FastAPI(title="Shopify Private Install Onboarding")
_cors_origins = list(
    dict.fromkeys(
        origin.rstrip("/")
        for origin in (FRONTEND_URL, "http://localhost:5173")
        if origin and origin.strip()
    )
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)
SHOP_COOKIE_NAME = "perspicor_shop"
SHOP_COOKIE_MAX_AGE = 2_592_000
SHOPIFY_SCOPES = settings.SHOPIFY_SCOPES
REQUIRED_SHOPIFY_SCOPES = {
    "read_orders",
    "read_customers",
    "read_products",
    "read_inventory",
}


def _parse_scope_csv(scope_csv: str) -> list[str]:
    return sorted({s.strip() for s in (scope_csv or "").split(",") if s.strip()})


def _shop_cookie_serializer() -> URLSafeTimedSerializer:
    secret = (SECRET_KEY or "").strip()
    if not secret:
        raise RuntimeError("SECRET_KEY is not set")
    return URLSafeTimedSerializer(secret, salt="perspicor-shop")


def _sign_shop_cookie(shop_domain: str) -> str:
    return _shop_cookie_serializer().dumps(shop_domain)


def _unsign_shop_cookie(signed_value: str) -> str:
    return _shop_cookie_serializer().loads(signed_value, max_age=SHOP_COOKIE_MAX_AGE)


def _attach_shop_cookie(response: RedirectResponse, shop_domain: str) -> None:
    """Best-effort session cookie for /api/auth/me (optional; shop is also in the redirect URL)."""
    if not (SECRET_KEY or "").strip():
        logger.warning("SECRET_KEY is not set; skipping shop session cookie for %s", shop_domain)
        return
    try:
        response.set_cookie(
            key=SHOP_COOKIE_NAME,
            value=_sign_shop_cookie(shop_domain),
            httponly=True,
            secure=True,
            samesite="none",
            max_age=SHOP_COOKIE_MAX_AGE,
        )
    except Exception:
        logger.exception("Failed to set shop session cookie for %s", shop_domain)


def _post_install_redirect_response(shop_domain: str) -> RedirectResponse:
    # Success page does not require cross-site cookies (avoids 500s and api↔frontend cookie issues).
    redirect_url = f"{FRONTEND_URL.rstrip('/')}/success?{urlencode({'shop': shop_domain})}"
    response = RedirectResponse(url=redirect_url, status_code=302)
    _attach_shop_cookie(response, shop_domain)
    return response


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
    configured_scopes = set(_parse_scope_csv(SHOPIFY_SCOPES))
    missing_required_scopes = sorted(REQUIRED_SHOPIFY_SCOPES - configured_scopes)
    if missing_required_scopes:
        raise HTTPException(
            status_code=500,
            detail=(
                "SHOPIFY_SCOPES is missing required scopes: "
                f"{missing_required_scopes}. Configured: {sorted(configured_scopes)}"
            ),
        )


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


def _state_hash(state: str) -> str:
    return hashlib.sha256((state or "").encode("utf-8")).hexdigest()


def _canonicalize_state(state: str) -> str:
    """
    Normalize callback state to avoid hash/signature mismatches caused by
    double-encoding or accidental surrounding whitespace.
    """
    value = (state or "").strip()
    # Unquote repeatedly (bounded) to handle callbacks that pass an already
    # decoded state or a still-encoded payload.
    for _ in range(2):
        decoded = unquote_plus(value)
        if decoded == value:
            break
        value = decoded
    return value


def _validate_state(state: str, expected_shop: str) -> bool:
    from db.queries import consume_oauth_state

    canonical_state = _canonicalize_state(state)
    parts = canonical_state.split("|")
    if len(parts) != 4:
        return False
    shop, nonce, issued_at, signature = parts
    if not nonce:
        return False
    try:
        state_shop = normalize_shop_domain(shop)
        expected_shop_normalized = normalize_shop_domain(expected_shop)
    except ValueError:
        return False
    if state_shop.casefold() != expected_shop_normalized.casefold():
        return False
    payload = f"{shop}|{nonce}|{issued_at}"
    expected_sig = hmac.new(
        SHOPIFY_API_SECRET.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_sig):
        return False
    try:
        if int(time.time()) - int(issued_at) > 600:
            return False
    except ValueError:
        return False
    return consume_oauth_state(_state_hash(canonical_state), expected_shop_normalized)


def _normalize_referral_code(ref: str | None) -> str | None:
    value = (ref or "").strip().upper()
    return value or None


def _frontend_hash_route(route: str) -> str:
    """
    Build a frontend hash-route URL so static hosting without rewrite rules
    can still resolve deep links like /success.
    """
    normalized_route = "/" + (route or "").strip().lstrip("/")
    return f"{FRONTEND_URL.rstrip('/')}/#{normalized_route}"


@app.get("/")
async def root(shop: str | None = None):
    if shop:
        return RedirectResponse(
            url=f"https://perspicor.com/dashboard?shop={shop}",
            status_code=302,
        )
    return RedirectResponse(url="https://perspicor.com", status_code=302)


@app.get("/app")
@app.get("/app/{path:path}")
async def app_redirect(path: str = "", shop: str | None = None):
    if shop:
        return RedirectResponse(
            url=f"https://perspicor.com/dashboard?shop={shop}",
            status_code=302,
        )
    return RedirectResponse(url="https://perspicor.com", status_code=302)


@app.get("/install")
@app.get("/oauth/install")
def install(
    shop: str = Query(..., description="Store domain"),
    email: str | None = Query(default=None, description="Optional report recipient"),
    ref: str | None = Query(default=None, description="Optional referral code"),
) -> RedirectResponse:
    from db.queries import set_store_referral_code, upsert_store_contact_email

    try:
        _ensure_oauth_env()
        try:
            shop_domain = normalize_shop_domain(shop)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        recipient = (email or "").strip()
        referral_code = _normalize_referral_code(ref)
        if recipient:
            upsert_store_contact_email(shop_domain, recipient)
        if referral_code:
            # Store pending referral code before OAuth callback.
            set_store_referral_code(shop_domain, referral_code)

        state = _build_state(shop_domain)
        from db.queries import create_oauth_state

        create_oauth_state(_state_hash(state), shop_domain, ttl_seconds=600)
        redirect_uri = f"{SHOPIFY_APP_BASE_URL.rstrip('/')}/oauth/callback"
        query = urlencode(
            [
                ("client_id", SHOPIFY_API_KEY),
                ("scope", SHOPIFY_SCOPES),
                ("redirect_uri", redirect_uri),
                ("state", state),
                ("grant_options[]", "per-user"),
            ]
        )
        auth_url = f"https://{shop_domain}/admin/oauth/authorize?{query}"
        logger.info(
            "Shopify install URL scopes for %s: %s (grant_options[]=per-user)",
            shop_domain,
            SHOPIFY_SCOPES,
        )
        return RedirectResponse(url=auth_url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("OAuth install failed for shop=%s", shop)
        raise HTTPException(status_code=500, detail="Install failed. Please try again.") from exc


@app.get("/oauth/callback")
def oauth_callback(
    request: Request,
    shop: str = Query(...),
    code: str = Query(...),
    state: str = Query(...),
    email: str | None = Query(default=None),
) -> PlainTextResponse:
    from db.queries import (
        attach_store_referral,
        get_active_referral_code_by_code,
        get_store_by_domain,
        upsert_store_connection,
        upsert_store_contact_email,
    )

    try:
        _ensure_oauth_env()
        shop_domain = normalize_shop_domain(shop)

        if not verify_oauth_callback_hmac(request, secret=shopify_client_secret() or SHOPIFY_API_SECRET):
            return PlainTextResponse(
                "Invalid Shopify HMAC. In Vercel (api.perspicor.com), set SHOPIFY_API_SECRET to the "
                "Client secret from Shopify Dev Dashboard → your app → API credentials "
                "(must pair with SHOPIFY_API_KEY).",
                status_code=400,
            )
        if not _validate_state(state, shop_domain):
            return PlainTextResponse("Invalid or expired state.", status_code=400)

        token_url = f"https://{shop_domain}/admin/oauth/access_token"
        api_secret = shopify_client_secret() or SHOPIFY_API_SECRET
        payload = {
            "client_id": SHOPIFY_API_KEY,
            "client_secret": api_secret,
            "code": code,
            "expiring": "1",
        }
        try:
            response = requests.post(token_url, data=payload, timeout=30)
            response.raise_for_status()
            token_data = response.json() or {}
        except requests.RequestException as exc:
            logger.exception("Token exchange HTTP failed for %s", shop_domain)
            return PlainTextResponse("Token exchange failed.", status_code=502)

        access_token = (token_data.get("access_token") or "").strip()
        if not access_token:
            logger.error("Token exchange response missing access_token for %s", shop_domain)
            return PlainTextResponse("Token exchange failed: missing access token.", status_code=400)
        refresh_token = (token_data.get("refresh_token") or "").strip() or None
        access_token_expires_at = None
        expires_in = token_data.get("expires_in")
        if expires_in is not None:
            try:
                access_token_expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
            except (TypeError, ValueError):
                logger.warning("Unexpected expires_in value from Shopify for %s: %r", shop_domain, expires_in)

        token_scope_csv = (token_data.get("scope") or "").strip()
        logger.info(
            "Shopify token response scopes for %s: %s",
            shop_domain,
            token_scope_csv or "<empty>",
        )
        if token_scope_csv:
            scopes = _parse_scope_csv(token_scope_csv)
            missing_from_token = sorted(REQUIRED_SHOPIFY_SCOPES - set(scopes))
            if missing_from_token:
                logger.warning(
                    "Token response missing required scopes for %s: missing=%s required=%s granted=%s",
                    shop_domain,
                    missing_from_token,
                    sorted(REQUIRED_SHOPIFY_SCOPES),
                    scopes,
                )
            logger.info("Using scopes returned by token exchange for %s", shop_domain)
        else:
            scopes = []

        try:
            if not scopes:
                scopes = fetch_access_scopes(shop_domain, access_token)
        except requests.HTTPError as exc:
            status_code = getattr(exc.response, "status_code", "unknown")
            logger.exception(
                "Token accepted but Shopify API call was rejected for %s (HTTP %s)",
                shop_domain,
                status_code,
            )
            return PlainTextResponse(
                f"Token issued, but Shopify API access was denied (HTTP {status_code}). "
                "Check app Admin API scopes and store permissions.",
                status_code=400,
            )
        except requests.RequestException:
            logger.exception("Token accepted but scope fetch request failed for %s", shop_domain)
            return PlainTextResponse("Token issued, but scope verification failed.", status_code=502)
        except Exception as exc:
            logger.exception("Token accepted but scope verification failed for %s", shop_domain)
            return PlainTextResponse(f"Scope verification failed: {exc}", status_code=400)

        scopes_ok, scopes_detail = validate_read_only_scopes(scopes)
        if not scopes_ok:
            return PlainTextResponse(f"Scope validation failed: {scopes_detail}", status_code=400)

        existing_referral_code = None
        try:
            existing_store = get_store_by_domain(shop_domain)
            existing_referral_code = _normalize_referral_code((existing_store or {}).get("referral_code_used"))
        except Exception:
            logger.warning("Could not read pending referral code for %s", shop_domain)

        referral_code_id = None
        referral_code_used = None
        if existing_referral_code:
            referral = get_active_referral_code_by_code(existing_referral_code)
            if referral:
                referral_code_id = int(referral["id"])
                referral_code_used = referral["code"]

        upsert_store_connection(
            shop_domain=shop_domain,
            access_token=access_token,
            refresh_token=refresh_token,
            access_token_expires_at=access_token_expires_at,
            scope=",".join(scopes),
            contact_email=None,
            referral_code_used=referral_code_used,
            referral_code_id=referral_code_id,
        )

        recipient = (email or "").strip()
        if recipient:
            upsert_store_contact_email(shop_domain, recipient)

        if referral_code_id and referral_code_used:
            attach_store_referral(shop_domain, referral_code_id, referral_code_used)

        try:
            spawn_store_pipeline_job(shop_domain)
            logger.info("Triggered Modal pipeline job after install for %s", shop_domain)
        except Exception:
            # Do not block successful OAuth completion if the background trigger fails.
            logger.exception("Failed to trigger Modal pipeline job after install for %s", shop_domain)

        logger.info("Private app install completed for %s", shop_domain)
        return _post_install_redirect_response(shop_domain)

    except ValueError as exc:
        return PlainTextResponse(str(exc), status_code=400)
    except HTTPException as exc:
        return PlainTextResponse(str(exc.detail), status_code=exc.status_code)
    except Exception:
        logger.exception("OAuth callback failed")
        return PlainTextResponse("Internal server error.", status_code=500)


@app.get("/api/auth/me")
def auth_me(request: Request):
    from db.queries import get_store_by_domain

    signed_shop = request.cookies.get(SHOP_COOKIE_NAME)
    if not signed_shop:
        return JSONResponse({"authenticated": False}, status_code=401)

    try:
        shop_domain = normalize_shop_domain(_unsign_shop_cookie(signed_shop))
    except (BadSignature, SignatureExpired, ValueError, RuntimeError):
        return JSONResponse({"authenticated": False}, status_code=401)

    try:
        store = get_store_by_domain(shop_domain)
    except Exception:
        logger.exception("auth_me store lookup failed for %s", shop_domain)
        return JSONResponse({"authenticated": False}, status_code=401)

    if not store or not store.get("is_active"):
        return JSONResponse({"authenticated": False}, status_code=401)

    return {"shop": shop_domain, "authenticated": True}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/cron/run-pipeline")
def run_pipeline_cron(authorization: str | None = Header(default=None)) -> dict:
    try:
        settings.validate_cron_env()
    except EnvironmentError as exc:
        logger.error("Cron trigger rejected: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    expected_secret = (settings.CRON_SECRET or "").strip()

    expected_auth = f"Bearer {expected_secret}"
    if (authorization or "").strip() != expected_auth:
        logger.warning("Cron trigger rejected: invalid Authorization header")
        raise HTTPException(status_code=401, detail="Unauthorized")

    from db.queries import list_connected_stores_for_cron
    stores = list_connected_stores_for_cron()
    logger.info("Cron pipeline started for %s stores", len(stores))

    attempted = 0
    spawned = 0
    failed = 0
    for store in stores:
        store_id = int(store["id"])
        shop_domain = str(store.get("shop_domain") or "").strip()
        attempted += 1
        try:
            logger.info(
                "Cron pipeline store started",
                extra={"store_id": store_id, "shop_domain": shop_domain},
            )
            job = spawn_store_pipeline_job(shop_domain)
            logger.info(
                "Cron pipeline store queued in Modal",
                extra={
                    "store_id": store_id,
                    "shop_domain": shop_domain,
                    "modal_job_id": getattr(job, "object_id", None),
                },
            )
            spawned += 1
        except Exception:
            failed += 1
            logger.exception(
                "Cron pipeline store queueing failed",
                extra={"store_id": store_id, "shop_domain": shop_domain},
            )

    logger.info(
        "Cron pipeline queueing finished: total=%s attempted=%s spawned=%s failed=%s",
        len(stores),
        attempted,
        spawned,
        failed,
    )
    return {
        "status": "ok",
        "total": len(stores),
        "attempted": attempted,
        "spawned": spawned,
        "failed": failed,
    }


@app.get("/unsubscribe")
def unsubscribe(
    email: str = Query(..., description="Recipient email to unsubscribe"),
    action: str = Query(default="unsubscribe", description="unsubscribe or subscribe"),
) -> HTMLResponse:
    from db.queries import disable_report_schedule_by_email, enable_report_schedule_by_email

    recipient = (email or "").strip()
    if not recipient:
        return HTMLResponse("<h1>Invalid unsubscribe link.</h1>", status_code=400)
    normalized_action = (action or "unsubscribe").strip().lower()
    if normalized_action == "subscribe":
        changed = enable_report_schedule_by_email(recipient)
        title = "You're subscribed again."
        subtitle = (
            "Daily Perspicor reports are active again for this address."
            if changed > 0
            else "This address is already subscribed."
        )
        cta_href = ""
        cta_text = ""
    else:
        changed = disable_report_schedule_by_email(recipient)
        title = "You're unsubscribed."
        subtitle = (
            "You will no longer receive daily Perspicor reports at this address."
            if changed > 0
            else "This address is already unsubscribed."
        )
        cta_href = f"/unsubscribe?{urlencode({'email': recipient, 'action': 'subscribe'})}"
        cta_text = "Subscribe again"

    safe_title = html.escape(title)
    safe_subtitle = html.escape(subtitle)
    safe_recipient = html.escape(recipient)
    safe_cta_href = html.escape(cta_href, quote=True)
    safe_cta_text = html.escape(cta_text)
    cta_html = (
        f'<div><a class="cta" href="{safe_cta_href}">{safe_cta_text}</a></div>'
        if safe_cta_href and safe_cta_text
        else ""
    )

    brand_html = f"""
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Perspicor Email Preferences</title>
    <style>
      * {{ box-sizing: border-box; }}
      body {{
        margin: 0;
        font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
        background: #08080f;
        color: #fff;
      }}
      .shell {{
        min-height: 100vh;
        max-width: 760px;
        margin: 0 auto;
        padding: 24px 20px 40px;
      }}
      .brand {{
        color: #fff;
        letter-spacing: 0.22em;
        font-weight: 800;
        font-size: 18px;
        text-transform: uppercase;
      }}
      .card {{
        margin-top: 72px;
        background: #12121e;
        border: 1px solid #1e1e35;
        border-radius: 12px;
        padding: 28px;
        box-shadow: 0 24px 48px rgba(0, 0, 0, 0.45);
      }}
      h1 {{
        margin: 0;
        font-size: 32px;
        line-height: 1.15;
      }}
      p {{
        margin: 14px 0 0;
        color: #8888aa;
        line-height: 1.65;
        max-width: 56ch;
      }}
      .pill {{
        display: inline-block;
        margin-top: 20px;
        color: #7b88ff;
        background: #0d0d2b;
        border: 1px solid #5c6bff;
        border-radius: 999px;
        padding: 6px 12px;
        font-size: 12px;
        letter-spacing: 0.05em;
      }}
      .cta {{
        display: inline-block;
        margin-top: 22px;
        background: #5c6bff;
        color: #fff;
        font-weight: 700;
        text-decoration: none;
        border-radius: 8px;
        padding: 12px 16px;
      }}
      .legal {{
        margin-top: 18px;
        font-size: 12px;
        color: #555570;
      }}
    </style>
  </head>
  <body>
    <main class="shell">
      <div class="brand">Perspicor</div>
      <section class="card">
        <h1>{safe_title}</h1>
        <p>{safe_subtitle}</p>
        <div class="pill">{safe_recipient}</div>
        {cta_html}
        <p class="legal">You can change this anytime from your next report email.</p>
      </section>
    </main>
  </body>
</html>
"""
    return HTMLResponse(brand_html, status_code=200)
