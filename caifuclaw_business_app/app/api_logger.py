"""平台 API 请求日志工具。

在 connectors 内部的 HTTP 调用发生后同步写入 api_request_logs 表，
失败时只打印日志不影响主流程。保留 30 天，由 scheduler 每日清理。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import delete

from .database import SessionLocal
from .models import ApiRequestLog

logger = logging.getLogger(__name__)

# 单个字段最大长度（字符数），超过后截断，避免极端大响应写爆数据库
_MAX_BODY_CHARS = 200_000
_SENSITIVE_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "client_secret",
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
}


def _is_sensitive_key(key: str) -> bool:
    normalized = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", key).lower().replace("-", "_")
    return normalized in _SENSITIVE_KEYS or normalized.endswith("_token") or normalized.endswith("_secret")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: ("***" if _is_sensitive_key(str(key)) else _redact(item)) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _redact_url(url: str) -> str:
    try:
        parts = urlsplit(url)
        query = urlencode([(key, "***" if _is_sensitive_key(key) else value) for key, value in parse_qsl(parts.query, keep_blank_values=True)])
        return urlunsplit((parts.scheme, parts.netloc, parts.path, query, parts.fragment))
    except Exception:
        return url


def _infer_operation(method: str, url: str) -> str:
    lowered = url.lower()
    if "oauth" in lowered and "token" in lowered:
        return "oauth_token"
    if "refresh" in lowered and "token" in lowered:
        return "refresh_token"
    if "label" in lowered or "sticker" in lowered:
        return "fetch_label"
    if "shipment" in lowered or "delivery" in lowered:
        return "shipment"
    if "order" in lowered or "posting" in lowered:
        return "sync_orders" if method.upper() == "GET" else "order_api"
    return "platform_api"


def _truncate_jsonb(value: Any) -> Any:
    """JSONB 字段长度保护，过大时返回截断提示对象。"""
    if value is None:
        return None
    try:
        import json

        serialized = json.dumps(value, ensure_ascii=False, default=str)
        if len(serialized) > _MAX_BODY_CHARS:
            return {
                "_truncated": True,
                "original_length": len(serialized),
                "preview": serialized[:4000],
            }
        return value
    except Exception:
        return {"_serialize_error": True, "repr": repr(value)[:4000]}


def log_api_call(
    *,
    platform: str,
    account_id: str,
    method: str,
    url: str,
    operation: str | None = None,
    status: str | None = None,
    request_id: str | None = None,
    request_body: Any = None,
    response_status: int | None = None,
    response_body: Any = None,
    error_message: str | None = None,
    duration_ms: int | None = None,
    extra: dict | None = None,
) -> None:
    """写入一条 API 调用日志（同步写入；失败时仅告警，不抛出）。"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        final_status = status or ("failed" if error_message or (response_status is not None and response_status >= 400) else "success")
        row = ApiRequestLog(
            platform=platform,
            account_id=str(account_id or ""),
            operation=operation or _infer_operation(method, url),
            status=final_status,
            request_id=str(request_id or ""),
            method=method,
            url=_redact_url(url),
            request_body=_truncate_jsonb(_redact(request_body)),
            response_status=response_status,
            response_body=_truncate_jsonb(_redact(response_body)),
            error_message=error_message,
            duration_ms=duration_ms,
            extra=_truncate_jsonb(_redact(extra or {})) or {},
            log_date=now.strftime("%Y-%m-%d"),
            created_at=now,
        )
        db.add(row)
        db.commit()
    except Exception:
        logger.exception("Failed to write api_request_logs")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        db.close()


def purge_old_logs(retention_days: int = 30) -> int:
    """删除超过 retention_days 天的日志。返回删除行数。"""
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    db = SessionLocal()
    try:
        result = db.execute(delete(ApiRequestLog).where(ApiRequestLog.created_at < cutoff))
        db.commit()
        deleted = result.rowcount or 0
        logger.info("Purged %s old api_request_logs rows (cutoff=%s)", deleted, cutoff.isoformat())
        return deleted
    except Exception:
        logger.exception("Failed to purge api_request_logs")
        db.rollback()
        return 0
    finally:
        db.close()
