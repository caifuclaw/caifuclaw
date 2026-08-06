# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Lock
from time import perf_counter

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config_loader import optional, require
from .credential_manager import get_credential_manager
from .models import PlatformAccount
from .api_logger import log_api_call


OAUTH_PLATFORMS = {"joom_logistics", "joomlogistics", "joom", "allegro", "mercadolibre"}
OAUTH_PLATFORM_KEYS = {"joom_logistics", "allegro", "mercadolibre"}
TOKEN_REFRESH_WINDOW = timedelta(minutes=10)
PLATFORM_TOKEN_REFRESH_WINDOWS = {
    "mercadolibre": timedelta(hours=1),
    "allegro": timedelta(hours=2),
    "joom_logistics": timedelta(days=3),
}
PLATFORM_TOKEN_KEEPALIVE_INTERVALS = {
    "joom_logistics": timedelta(days=7),
}
PLATFORM_REFRESH_TOKEN_LIFETIMES = {
    "mercadolibre": timedelta(days=180),
    "allegro": timedelta(days=90),
}
REFRESH_TOKEN_REFRESH_WINDOW = timedelta(days=14)
TOKEN_REFRESH_LOCK_TIMEOUT = timedelta(minutes=10)
_token_refresh_locks: dict[str, Lock] = {}
_token_refresh_locks_guard = Lock()


def canonical_oauth_platform(platform: str) -> str:
    normalized = (platform or "").lower()
    if normalized in {"joom", "joomlogistics", "joom_logistics"}:
        return "joom_logistics"
    if normalized == "mercadolibre":
        return "mercadolibre"
    return normalized


def _refresh_lock_key(account: PlatformAccount) -> str:
    return f"{canonical_oauth_platform(account.platform)}:{account.account_id}"


def _refresh_lock_for(account: PlatformAccount) -> Lock:
    key = _refresh_lock_key(account)
    with _token_refresh_locks_guard:
        lock = _token_refresh_locks.get(key)
        if lock is None:
            lock = Lock()
            _token_refresh_locks[key] = lock
        return lock


def _platform_endpoint(platform_key: str) -> str:
    return require("platform_endpoints", platform_key)


def _parse_datetime(value: str | datetime | None) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        if value.tzinfo:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        return parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _iso_utc(value: datetime | None) -> str:
    return value.replace(microsecond=0).isoformat() if value else ""


def _expiry_from_payload(
    payload: dict,
    absolute_keys: tuple[str, ...],
    relative_keys: tuple[str, ...],
    now: datetime,
) -> str:
    for key in absolute_keys:
        parsed = _parse_datetime(payload.get(key))
        if parsed:
            return _iso_utc(parsed)
    for key in relative_keys:
        value = payload.get(key)
        if value in (None, ""):
            continue
        try:
            return _iso_utc(now + timedelta(seconds=int(value)))
        except (TypeError, ValueError):
            return ""
    return ""


def _access_token_expires_at(credentials: dict) -> datetime | None:
    return _parse_datetime(credentials.get("access_token_expires_at") or credentials.get("expires_at"))


def _refresh_token_expires_at(credentials: dict) -> datetime | None:
    return _parse_datetime(
        credentials.get("refresh_token_expires_at")
        or credentials.get("refresh_expires_at")
        or credentials.get("refresh_token_expire_at")
    )


def _platform_refresh_window(platform: str | None) -> timedelta:
    if not platform:
        return TOKEN_REFRESH_WINDOW
    return PLATFORM_TOKEN_REFRESH_WINDOWS.get(canonical_oauth_platform(platform), TOKEN_REFRESH_WINDOW)


def _next_token_refresh_at(platform: str, credentials: dict, now: datetime | None = None) -> datetime | None:
    now = now or datetime.utcnow()
    platform_key = canonical_oauth_platform(platform)
    candidates: list[datetime] = []
    access_expires_at = _access_token_expires_at(credentials)
    if access_expires_at:
        candidates.append(access_expires_at - _platform_refresh_window(platform_key))
    refresh_expires_at = _refresh_token_expires_at(credentials)
    if refresh_expires_at:
        candidates.append(refresh_expires_at - REFRESH_TOKEN_REFRESH_WINDOW)
    keepalive = PLATFORM_TOKEN_KEEPALIVE_INTERVALS.get(platform_key)
    if keepalive:
        candidates.append(now + keepalive)
    return min(candidates) if candidates else None


def _token_expired(credentials: dict, platform: str | None = None, window: timedelta | None = None) -> bool:
    expires_at = _access_token_expires_at(credentials)
    if not expires_at:
        return False
    return expires_at <= datetime.utcnow() + (window or _platform_refresh_window(platform))


def _access_token_still_valid(credentials: dict, now: datetime | None = None) -> bool:
    if not credentials.get("access_token"):
        return False
    expires_at = _access_token_expires_at(credentials)
    if not expires_at:
        return True
    return expires_at > (now or datetime.utcnow())


def _token_refresh_due(
    platform: str,
    credentials: dict,
    account: PlatformAccount | None = None,
    now: datetime | None = None,
) -> tuple[bool, str]:
    now = now or datetime.utcnow()
    platform_key = canonical_oauth_platform(platform)
    if platform_key not in OAUTH_PLATFORM_KEYS:
        return False, "not_oauth_platform"
    if not credentials.get("refresh_token"):
        return True, "missing_refresh_token"
    if not credentials.get("access_token"):
        return True, "missing_access_token"
    access_expires_at = _access_token_expires_at(credentials)
    if not access_expires_at:
        return True, "missing_access_token_expires_at"
    if access_expires_at <= now + _platform_refresh_window(platform_key):
        return True, "access_token_expiring"
    refresh_expires_at = _refresh_token_expires_at(credentials)
    if refresh_expires_at and refresh_expires_at <= now + REFRESH_TOKEN_REFRESH_WINDOW:
        return True, "refresh_token_expiring"
    next_refresh_at = _parse_datetime(credentials.get("next_token_refresh_at"))
    if next_refresh_at and next_refresh_at <= now:
        return True, "scheduled_refresh_due"
    keepalive = PLATFORM_TOKEN_KEEPALIVE_INTERVALS.get(platform_key)
    if keepalive:
        last_refresh_at = (
            _parse_datetime(credentials.get("last_token_refresh_at"))
            or _parse_datetime(account.last_authorized_at if account else None)
        )
        if last_refresh_at and last_refresh_at <= now - keepalive:
            return True, "keepalive_due"
    return False, ""


def _oauth_url(platform: str, credentials: dict, settings: dict, key: str, fallback_path: str = "") -> str:
    platform_key = canonical_oauth_platform(platform)
    base_url = str(settings.get("base_url") or _platform_endpoint(platform_key)).rstrip("/")
    default_url = ""
    if platform_key == "allegro" and key in {"token_url", "refresh_url"}:
        default_url = "https://allegro.pl/auth/oauth/token"
    elif platform_key == "mercadolibre" and key in {"token_url", "refresh_url"}:
        default_url = "https://api.mercadolibre.com/oauth/token"
    return (
        credentials.get(key)
        or settings.get(key)
        or optional(f"oauth.{platform_key}", key, "")
        or default_url
        or (f"{base_url}{fallback_path}" if fallback_path else base_url)
    )


def _oauth_client_option(platform: str, credentials: dict, key: str) -> str:
    platform_key = canonical_oauth_platform(platform)
    return str(
        credentials.get(key)
        or optional(f"oauth.{platform_key}", key, "")
        or ""
    )


def _token_payload_from_response(
    platform: str,
    data: dict,
    refresh_url: str,
    token_url: str,
    credentials: dict,
) -> dict:
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    now = datetime.utcnow()
    expires_at = _expiry_from_payload(
        payload,
        ("access_token_expires_at", "expires_at", "expire_at"),
        ("access_token_expires_in", "expires_in"),
        now,
    )
    refresh_token_expires_at = _expiry_from_payload(
        payload,
        ("refresh_token_expires_at", "refresh_expires_at", "refresh_token_expire_at"),
        ("refresh_token_expires_in", "refresh_expires_in"),
        now,
    )
    platform_key = canonical_oauth_platform(platform)
    updated = {
        **credentials,
        "access_token": payload.get("access_token") or payload.get("token") or credentials.get("access_token", ""),
        "refresh_token": payload.get("refresh_token") or credentials.get("refresh_token", ""),
        "token_type": payload.get("token_type") or credentials.get("token_type") or "Bearer",
        "access_token_expires_at": expires_at or credentials.get("access_token_expires_at") or credentials.get("expires_at") or "",
        "expires_at": expires_at or credentials.get("expires_at") or credentials.get("access_token_expires_at") or "",
        "token_url": token_url,
        "refresh_url": refresh_url,
        "last_token_refresh_at": _iso_utc(now),
        "token_refresh_fail_count": 0,
        "token_refresh_last_error": "",
        "token_refresh_last_error_at": "",
    }
    if refresh_token_expires_at:
        updated["refresh_token_expires_at"] = refresh_token_expires_at
    elif payload.get("refresh_token") and platform_key in PLATFORM_REFRESH_TOKEN_LIFETIMES:
        updated["refresh_token_expires_at"] = _iso_utc(now + PLATFORM_REFRESH_TOKEN_LIFETIMES[platform_key])
    elif credentials.get("refresh_token_expires_at"):
        updated["refresh_token_expires_at"] = credentials["refresh_token_expires_at"]
    next_refresh_at = _next_token_refresh_at(platform_key, updated, now)
    if next_refresh_at:
        updated["next_token_refresh_at"] = _iso_utc(next_refresh_at)
    if platform_key == "mercadolibre":
        updated["seller_id"] = str(payload.get("user_id") or payload.get("seller_id") or credentials.get("seller_id") or "")
    return updated


def refresh_access_token(platform: str, credentials: dict, settings: dict | None = None) -> dict:
    settings = settings or {}
    platform_key = canonical_oauth_platform(platform)
    refresh_token = credentials.get("refresh_token")
    client_id = _oauth_client_option(platform_key, credentials, "client_id")
    client_secret = _oauth_client_option(platform_key, credentials, "client_secret") or credentials.get("api_key")
    if not refresh_token or not client_id or not client_secret:
        return credentials

    if platform_key == "joom_logistics":
        token_url = "https://api-merchant.joom.com/api/v2/oauth/access_token"
        refresh_url = "https://api-merchant.joom.com/api/v2/oauth/refresh_token"
    elif platform_key == "mercadolibre":
        token_url = _oauth_url(platform_key, credentials, settings, "token_url", "/oauth/token")
        refresh_url = _oauth_url(platform_key, credentials, settings, "refresh_url", "/oauth/token")
    elif platform_key == "allegro":
        token_url = _oauth_url(platform_key, credentials, settings, "token_url", "")
        refresh_url = _oauth_url(platform_key, credentials, settings, "refresh_url", "")
    else:
        return credentials

    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    auth = None
    if platform_key == "allegro":
        auth = (client_id, client_secret)
    else:
        data["client_id"] = client_id
        data["client_secret"] = client_secret

    started = perf_counter()
    account_id = str(settings.get("account_id") or credentials.get("account_id") or "")
    with httpx.Client(timeout=30) as client:
        try:
            response = client.post(
                refresh_url,
                data=data,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                auth=auth,
            )
            response.raise_for_status()
            payload = response.json()
            log_api_call(
                platform=platform_key,
                account_id=account_id,
                operation="refresh_token",
                method="POST",
                url=refresh_url,
                request_body=data,
                response_status=response.status_code,
                response_body=payload,
                duration_ms=int((perf_counter() - started) * 1000),
            )
            return _token_payload_from_response(platform_key, payload, refresh_url, token_url, credentials)
        except httpx.HTTPStatusError as exc:
            log_api_call(
                platform=platform_key,
                account_id=account_id,
                operation="refresh_token",
                method="POST",
                url=refresh_url,
                request_body=data,
                response_status=exc.response.status_code if exc.response is not None else None,
                error_message=(exc.response.text if exc.response is not None else str(exc))[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise
        except Exception as exc:
            log_api_call(
                platform=platform_key,
                account_id=account_id,
                operation="refresh_token",
                method="POST",
                url=refresh_url,
                request_body=data,
                error_message=str(exc)[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise


def _token_refresh_error_message(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        body = exc.response.text[:1000]
        return f"HTTP {exc.response.status_code}: {body}"
    return str(exc)[:1000]


def _is_reauthorization_error(exc: Exception) -> bool:
    if not isinstance(exc, httpx.HTTPStatusError) or exc.response is None:
        return False
    text = exc.response.text.lower()
    return exc.response.status_code in {400, 401, 403} and any(
        marker in text
        for marker in (
            "invalid_grant",
            "invalid refresh",
            "refresh token expired",
            "refresh_token expired",
            "revoked",
        )
    )


def _record_token_refresh_failure(
    db: Session,
    account: PlatformAccount,
    credentials: dict,
    exc: Exception,
    due_reason: str = "",
) -> dict:
    now = datetime.utcnow()
    updated = {
        **credentials,
        "token_refresh_fail_count": int(credentials.get("token_refresh_fail_count") or 0) + 1,
        "token_refresh_last_error": _token_refresh_error_message(exc),
        "token_refresh_last_error_at": _iso_utc(now),
        "token_refresh_last_due_reason": due_reason,
    }
    account.encrypted_credentials = get_credential_manager().encrypt_credentials(updated)
    account.credentials_version = now.isoformat()
    account.token_valid = _access_token_still_valid(updated, now)
    account.token_message = f"Token refresh failed: {updated['token_refresh_last_error'][:300]}"
    if _is_reauthorization_error(exc):
        account.authorization_status = "failed"
        account.token_valid = False
        account.token_message = "OAuth refresh token invalid or expired; reauthorization required"
    db.add(account)
    db.commit()
    return updated


def _store_refreshed_credentials(db: Session, account: PlatformAccount, credentials: dict) -> None:
    now = datetime.utcnow()
    expires_at = _access_token_expires_at(credentials)
    account.encrypted_credentials = get_credential_manager().encrypt_credentials(credentials)
    account.credentials_version = now.isoformat()
    account.authorization_status = "success"
    account.token_valid = True
    account.token_message = "Token 已自动刷新"
    account.last_authorized_at = now
    if expires_at:
        account.authorization_expires_at = expires_at
        account.session_expires_at = expires_at
    db.add(account)
    db.commit()
    db.refresh(account)


def ensure_access_token(
    db: Session,
    account: PlatformAccount,
    credentials: dict,
    settings: dict | None = None,
    force: bool = False,
) -> dict:
    if canonical_oauth_platform(account.platform) not in OAUTH_PLATFORMS:
        return credentials
    if not force and credentials.get("access_token") and not _token_expired(credentials, account.platform):
        return credentials
    lock = _refresh_lock_for(account)
    with lock:
        if account.encrypted_credentials:
            credentials = get_credential_manager().decrypt_credentials(account.encrypted_credentials)
        if not force and credentials.get("access_token") and not _token_expired(credentials, account.platform):
            return credentials
        try:
            refreshed = refresh_access_token(account.platform, credentials, settings)
        except Exception as exc:
            _record_token_refresh_failure(db, account, credentials, exc, "business_call")
            raise
        if refreshed == credentials:
            return credentials
        _store_refreshed_credentials(db, account, refreshed)
    return refreshed


def maintain_oauth_tokens(db: Session) -> dict:
    now = datetime.utcnow()
    rows = db.scalars(
        select(PlatformAccount)
        .where(PlatformAccount.platform.in_(OAUTH_PLATFORMS))
        .where(PlatformAccount.encrypted_credentials.is_not(None))
        .order_by(PlatformAccount.id)
    ).all()
    stats = {
        "checked": 0,
        "refreshed": 0,
        "skipped": 0,
        "failed": 0,
        "reauthorization_required": 0,
    }
    manager = get_credential_manager()
    for account in rows:
        stats["checked"] += 1
        platform_key = canonical_oauth_platform(account.platform)
        lock = _refresh_lock_for(account)
        acquired = lock.acquire(blocking=False)
        if not acquired:
            stats["skipped"] += 1
            continue
        try:
            db.refresh(account)
            credentials = manager.decrypt_credentials(account.encrypted_credentials)
            due, reason = _token_refresh_due(platform_key, credentials, account, now)
            if not due:
                stats["skipped"] += 1
                continue
            if not credentials.get("refresh_token"):
                account.token_valid = _access_token_still_valid(credentials, now)
                account.token_message = "缺少 refresh_token，需要重新授权"
                account.authorization_status = "failed"
                stats["reauthorization_required"] += 1
                db.add(account)
                db.commit()
                stats["skipped"] += 1
                continue
            marker_at = _parse_datetime(credentials.get("token_refresh_started_at"))
            if marker_at and marker_at > now - TOKEN_REFRESH_LOCK_TIMEOUT:
                stats["skipped"] += 1
                continue
            credentials["token_refresh_started_at"] = _iso_utc(now)
            credentials["token_refresh_due_reason"] = reason
            account.encrypted_credentials = manager.encrypt_credentials(credentials)
            account.credentials_version = now.isoformat()
            db.add(account)
            db.commit()
            try:
                refreshed = refresh_access_token(
                    platform_key,
                    credentials,
                    {**(account.settings or {}), "account_id": account.account_id},
                )
                if refreshed == credentials:
                    current_credentials = {**credentials}
                    current_credentials.pop("token_refresh_started_at", None)
                    current_credentials["token_refresh_fail_count"] = int(
                        current_credentials.get("token_refresh_fail_count") or 0
                    ) + 1
                    current_credentials["token_refresh_last_error"] = "Missing refresh token, client_id, or client_secret"
                    current_credentials["token_refresh_last_error_at"] = _iso_utc(datetime.utcnow())
                    current_credentials["token_refresh_last_due_reason"] = reason
                    account.encrypted_credentials = manager.encrypt_credentials(current_credentials)
                    account.credentials_version = datetime.utcnow().isoformat()
                    account.token_valid = _access_token_still_valid(current_credentials)
                    account.token_message = "Missing refresh token, client_id, or client_secret"
                    if not account.token_valid:
                        account.authorization_status = "failed"
                        stats["reauthorization_required"] += 1
                    db.add(account)
                    db.commit()
                    stats["skipped"] += 1
                    continue
                refreshed.pop("token_refresh_started_at", None)
                refreshed["token_refresh_due_reason"] = reason
                _store_refreshed_credentials(db, account, refreshed)
                stats["refreshed"] += 1
            except Exception as exc:
                db.refresh(account)
                current_credentials = manager.decrypt_credentials(account.encrypted_credentials)
                current_credentials.pop("token_refresh_started_at", None)
                _record_token_refresh_failure(db, account, current_credentials, exc, reason)
                stats["failed"] += 1
                if _is_reauthorization_error(exc):
                    stats["reauthorization_required"] += 1
        finally:
            lock.release()
    return stats
