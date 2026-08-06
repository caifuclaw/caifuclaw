from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LocalUser, Order, OrderOperationLog


SYSTEM_OPERATOR = "系统任务"
ORDER_LOG_HISTORY_SOURCE = "history"
ORDER_LOG_MANUAL_SOURCE = "manual"
ORDER_LOG_SYSTEM_SOURCE = "system"
MAX_ORDER_LOG_EXTRA_BYTES = 4096


def safe_exception_message(exc: BaseException) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


def order_log_changes(
    before: dict[str, str] | None,
    after: dict[str, str] | None,
    labels: dict[str, str],
) -> list[dict[str, str]]:
    before = before or {}
    after = after or {}
    return [
        {
            "field": key,
            "label": label,
            "before": str(before.get(key, "-") or "-"),
            "after": str(after.get(key, "-") or "-"),
        }
        for key, label in labels.items()
        if before.get(key, "-") != after.get(key, "-")
    ]


def compact_order_log_extra(extra: dict | None) -> dict:
    payload = extra or {}
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    if len(encoded) <= MAX_ORDER_LOG_EXTRA_BYTES:
        return payload

    compact: dict = {
        "payload_truncated": True,
        "payload_bytes": len(encoded),
    }
    for key, value in payload.items():
        if isinstance(value, (bool, int, float)) or value is None:
            compact[key] = value
        elif isinstance(value, str) and len(value.encode("utf-8")) <= 512:
            compact[key] = value
        elif key == "changes" and isinstance(value, list):
            compact[key] = value[:20]

    compact_encoded = json.dumps(compact, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    if len(compact_encoded) > MAX_ORDER_LOG_EXTRA_BYTES:
        compact.pop("changes", None)
    return compact


def _system_event_key(order_id: int, operation_type: str, description: str) -> str:
    digest = hashlib.sha256(description.strip().encode("utf-8")).hexdigest()[:24]
    return f"system:{order_id}:{operation_type}:{digest}"[:180]


def operator_name(user: LocalUser | None) -> str:
    if not user:
        return SYSTEM_OPERATOR
    return (user.display_name or user.username or SYSTEM_OPERATOR).strip() or SYSTEM_OPERATOR


def add_order_operation_log(
    db: Session,
    *,
    order_id: int,
    operation_type: str,
    operation_attribute: str,
    description: str,
    operator: str,
    source: str = ORDER_LOG_MANUAL_SOURCE,
    operated_at: datetime | None = None,
    event_key: str = "",
    extra: dict | None = None,
) -> OrderOperationLog | None:
    if not hasattr(db, "add"):
        return None
    if source == ORDER_LOG_SYSTEM_SOURCE and not event_key:
        event_key = _system_event_key(order_id, operation_type, description)
    if event_key and hasattr(db, "scalar"):
        exists = db.scalar(select(OrderOperationLog.id).where(OrderOperationLog.event_key == event_key).limit(1))
        if exists:
            return None
    row = OrderOperationLog(
        order_id=order_id,
        operation_type=operation_type,
        operation_attribute=operation_attribute,
        description=description,
        operator=operator,
        source=source,
        event_key=event_key,
        extra=compact_order_log_extra(extra),
        operated_at=operated_at or datetime.utcnow(),
    )
    db.add(row)
    return row


def add_order_operation_logs(
    db: Session,
    orders: Iterable[Order],
    *,
    operation_type: str,
    operation_attribute: str,
    description: str | Callable[[Order], str],
    operator: str,
    source: str = ORDER_LOG_MANUAL_SOURCE,
    operated_at: datetime | None = None,
    event_key: str | Callable[[Order], str] = "",
    extra: dict | Callable[[Order], dict] | None = None,
) -> None:
    for order in orders:
        add_order_operation_log(
            db,
            order_id=order.id,
            operation_type=operation_type,
            operation_attribute=operation_attribute,
            description=description(order) if callable(description) else description,
            operator=operator,
            source=source,
            operated_at=operated_at,
            event_key=event_key(order) if callable(event_key) else event_key,
            extra=extra(order) if callable(extra) else extra,
        )
