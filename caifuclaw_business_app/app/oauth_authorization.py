# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import html
import json
import secrets
from datetime import datetime, timedelta
from time import perf_counter
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .api_logger import log_api_call
from .config_loader import optional
from .models import OAuthAuthorizationSession, PlatformAccount
from .oauth_tokens import _token_payload_from_response, canonical_oauth_platform
from .settings import get_settings


SUPPORTED_OAUTH_PLATFORMS = {"joom_logistics", "allegro", "mercadolibre"}


def _oauth_option(platform: str, key: str, default: str = "") -> str:
    return str(optional(f"oauth.{platform}", key, default) or default)


def _public_callback_url(platform: str) -> str:
    return f"{get_settings().public_base_url}/api/{platform}/callback"


def _mercado_authorize_url(account_settings: dict) -> str:
    store_type = str(account_settings.get("mercado_store_type") or account_settings.get("store_type") or "").lower()
    site = str(account_settings.get("mercado_site") or account_settings.get("site") or "").upper()
    cbt_types = {
        "cbt",
        "cross_border",
        "crossborder",
        "global",
        "global_selling",
        "semi_managed",
        "semi-managed",
        "half_managed",
    }
    if store_type in cbt_types or site in {"CBT", "GLOBAL", "GLOBAL_SELLING"}:
        return _oauth_option(
            "mercadolibre",
            "global_authorize_url",
            "https://global-selling.mercadolibre.com/authorization",
        )
    site_urls = {
        "MLM": "https://auth.mercadolibre.com.mx/authorization",
        "MLC": "https://auth.mercadolibre.cl/authorization",
        "MLB": "https://auth.mercadolivre.com.br/authorization",
        "MCO": "https://auth.mercadolibre.com.co/authorization",
    }
    return _oauth_option(
        "mercadolibre",
        "authorize_url",
        site_urls.get(site, "https://auth.mercadolibre.com.ar/authorization"),
    )


def _oauth_urls(platform: str, account_settings: dict) -> dict[str, str]:
    platform = canonical_oauth_platform(platform)
    overrides = {
        key: str(account_settings.get(f"{platform}_{key}") or "").strip()
        for key in ("redirect_uri", "authorize_url", "token_url", "refresh_url")
    }
    if platform == "joom_logistics":
        defaults = {
            "redirect_uri": _oauth_option("joom_logistics", "redirect_uri", _public_callback_url("joom")),
            "authorize_url": _oauth_option(
                "joom_logistics",
                "authorize_url",
                "https://api-merchant.joom.com/api/v2/oauth/authorize",
            ),
            "token_url": _oauth_option(
                "joom_logistics",
                "token_url",
                "https://api-merchant.joom.com/api/v2/oauth/access_token",
            ),
            "refresh_url": _oauth_option(
                "joom_logistics",
                "refresh_url",
                "https://api-merchant.joom.com/api/v2/oauth/refresh_token",
            ),
        }
    elif platform == "allegro":
        defaults = {
            "redirect_uri": _oauth_option("allegro", "redirect_uri", _public_callback_url("allegro")),
            "authorize_url": _oauth_option(
                "allegro",
                "authorize_url",
                "https://allegro.pl/auth/oauth/authorize",
            ),
            "token_url": _oauth_option("allegro", "token_url", "https://allegro.pl/auth/oauth/token"),
            "refresh_url": _oauth_option("allegro", "refresh_url", "https://allegro.pl/auth/oauth/token"),
        }
    elif platform == "mercadolibre":
        defaults = {
            "redirect_uri": _oauth_option(
                "mercadolibre",
                "redirect_uri",
                _public_callback_url("mercadolibre"),
            ),
            "authorize_url": _mercado_authorize_url(account_settings),
            "token_url": _oauth_option(
                "mercadolibre",
                "token_url",
                "https://api.mercadolibre.com/oauth/token",
            ),
            "refresh_url": _oauth_option(
                "mercadolibre",
                "refresh_url",
                "https://api.mercadolibre.com/oauth/token",
            ),
        }
    else:
        raise ValueError(f"{platform} OAuth is not supported")
    return {key: overrides[key] or value for key, value in defaults.items()}


def create_authorization_session(
    db: Session,
    account: PlatformAccount,
    credentials: dict,
) -> OAuthAuthorizationSession:
    platform = canonical_oauth_platform(account.platform)
    if platform not in SUPPORTED_OAUTH_PLATFORMS:
        raise ValueError(f"{platform} OAuth is not supported")
    client_id = str(credentials.get("client_id") or _oauth_option(platform, "client_id", "")).strip()
    client_secret = str(
        credentials.get("client_secret")
        or credentials.get("api_key")
        or _oauth_option(platform, "client_secret", "")
    ).strip()
    if not client_id or not client_secret:
        raise ValueError("OAuth Client ID and Client Secret are required")
    urls = _oauth_urls(platform, account.settings or {})
    scopes = account.settings.get("oauth_scopes") if isinstance(account.settings, dict) else []
    if isinstance(scopes, str):
        scopes = [item for item in scopes.replace(",", " ").split() if item]
    if not isinstance(scopes, list):
        scopes = []
    now = datetime.utcnow()
    row = OAuthAuthorizationSession(
        platform_account_id=account.id,
        platform=platform,
        account_id=account.account_id,
        state=secrets.token_urlsafe(32),
        client_id=client_id,
        redirect_uri=urls["redirect_uri"],
        authorize_url=urls["authorize_url"],
        token_url=urls["token_url"],
        refresh_url=urls["refresh_url"],
        scopes=scopes,
        status="pending",
        expires_at=now + timedelta(minutes=get_settings().oauth_authorization_session_minutes),
    )
    db.add(row)
    db.flush()
    return row


def build_authorize_url(row: OAuthAuthorizationSession) -> str:
    if row.platform == "joom_logistics":
        params = {"client_id": row.client_id}
    elif row.platform == "allegro":
        params = {
            "response_type": "code",
            "client_id": row.client_id,
            "redirect_uri": row.redirect_uri,
        }
    else:
        params = {
            "client_id": row.client_id,
            "redirect_uri": row.redirect_uri,
            "response_type": "code",
            "state": row.state,
        }
        if row.scopes:
            params["scope"] = " ".join(row.scopes)
    separator = "&" if "?" in row.authorize_url else "?"
    return f"{row.authorize_url}{separator}{urlencode(params, safe=':/')}"


def get_authorization_session(
    db: Session,
    *,
    state: str,
    platform: str,
    account_id: str,
) -> OAuthAuthorizationSession | None:
    row = db.scalar(
        select(OAuthAuthorizationSession).where(
            OAuthAuthorizationSession.state == state,
            OAuthAuthorizationSession.platform == canonical_oauth_platform(platform),
            OAuthAuthorizationSession.account_id == account_id,
        )
    )
    if row and row.status == "pending" and row.expires_at < datetime.utcnow():
        row.status = "expired"
        row.error_message = "authorization session expired"
        row.completed_at = datetime.utcnow()
        db.flush()
    return row


async def exchange_authorization_code(
    row: OAuthAuthorizationSession,
    code: str,
    credentials: dict,
) -> dict:
    client_secret = str(credentials.get("client_secret") or credentials.get("api_key") or "").strip()
    if not client_secret:
        raise RuntimeError("OAuth Client Secret is missing")
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": row.client_id,
        "redirect_uri": row.redirect_uri,
    }
    auth = None
    if row.platform == "allegro":
        auth = (row.client_id, client_secret)
    else:
        data["client_secret"] = client_secret
    started = perf_counter()
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            row.token_url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            auth=auth,
        )
    try:
        response_payload = response.json()
    except ValueError:
        response_payload = {"text": response.text[:500]}
    log_api_call(
        platform=row.platform,
        account_id=row.account_id,
        operation="oauth_exchange",
        method="POST",
        url=row.token_url,
        request_body=data,
        response_status=response.status_code,
        response_body=response_payload,
        duration_ms=int((perf_counter() - started) * 1000),
        error_message=response.text[:500] if response.status_code >= 400 else None,
        extra={"state": row.state},
    )
    if response.status_code >= 400:
        raise RuntimeError(f"token exchange failed: HTTP {response.status_code} {response.text[:500]}")
    token_payload = _token_payload_from_response(
        row.platform,
        response_payload,
        row.refresh_url,
        row.token_url,
        credentials,
    )
    if not token_payload.get("access_token"):
        raise RuntimeError("token exchange failed: access_token is missing")
    return token_payload


def mark_authorization_success(row: OAuthAuthorizationSession) -> None:
    row.status = "success"
    row.error_message = ""
    row.completed_at = datetime.utcnow()


def mark_authorization_failed(row: OAuthAuthorizationSession, error: Exception | str) -> None:
    row.status = "failed"
    row.error_message = str(error)
    row.completed_at = datetime.utcnow()


def callback_html(platform: str, *, code: str = "", state: str = "", error: str = "") -> str:
    payload = json.dumps(
        {
            "type": "caifuclaw-oauth-callback",
            "platform": canonical_oauth_platform(platform),
            "code": code,
            "state": state,
            "error": error,
        },
        ensure_ascii=True,
    )
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    message = "Authorization failed" if error else "Authorization received"
    detail = error or "You can close this window and return to CaifuClaw AI."
    return f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>{message}</title></head>
<body style="font-family:system-ui,sans-serif;padding:32px">
  <h1>{message}</h1>
  <p>{html.escape(detail)}</p>
  <script>
    const payload = {payload};
    if (window.opener) {{
      window.opener.postMessage(payload, "*");
      window.setTimeout(() => window.close(), 500);
    }}
  </script>
</body>
</html>"""
