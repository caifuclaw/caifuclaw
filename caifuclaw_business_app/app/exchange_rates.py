from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .database import SessionLocal
from .exchange_rate_provider import fetch_exchange_rates
from .models import ExchangeRate, ExchangeRateCurrencySetting


SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def _parse_date(value: str | date | None) -> date | None:
    if isinstance(value, date):
        return value
    if not value:
        return None
    return date.fromisoformat(str(value))


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed.replace(microsecond=0)


def _rate_from_payload(payload: dict) -> Decimal:
    try:
        rate = Decimal(str(payload.get("rate")))
    except (InvalidOperation, TypeError) as exc:
        raise ValueError("汇率无效") from exc
    if rate <= 0:
        raise ValueError("汇率必须大于 0")
    return rate


def _provider_rate_date(source_updated_at: datetime | None, fallback: date) -> date:
    return source_updated_at.date() if source_updated_at else fallback


def _payload_rate_date(payload: dict) -> tuple[date | None, datetime | None]:
    payload_date = _parse_date(payload.get("rate_date"))
    source_updated_at = _parse_datetime(payload.get("provider_updated_at") or payload.get("updated_at"))
    if payload_date and source_updated_at:
        return _provider_rate_date(source_updated_at, payload_date), source_updated_at
    return payload_date, source_updated_at


def _delete_stale_exchange_rates(db: Session, rate_date: date, currencies: set[str]) -> int:
    stmt = select(ExchangeRate).where(ExchangeRate.rate_date == rate_date)
    if currencies:
        stmt = stmt.where(ExchangeRate.currency_code.in_(currencies))
    rows = db.scalars(stmt).all()
    deleted = 0
    for row in rows:
        if row.source_updated_at and row.source_updated_at.date() != row.rate_date:
            db.delete(row)
            deleted += 1
    if deleted:
        db.flush()
    return deleted


def upsert_exchange_rate(db: Session, payload: dict, synced_at: datetime | None = None) -> ExchangeRate:
    rate_date, source_updated_at = _payload_rate_date(payload)
    currency_code = str(payload.get("base_currency") or payload.get("currency_code") or "").strip().upper()
    if not rate_date:
        raise ValueError("汇率日期无效")
    if not currency_code:
        raise ValueError("货币代码不能为空")

    now = synced_at or datetime.utcnow()
    row = db.scalar(
        select(ExchangeRate).where(
            ExchangeRate.rate_date == rate_date,
            ExchangeRate.currency_code == currency_code,
        )
    )
    if not row:
        row = ExchangeRate(rate_date=rate_date, currency_code=currency_code)

    row.currency_name = str(payload.get("source_currency_name") or payload.get("currency_name") or currency_code)
    row.rate = _rate_from_payload(payload)
    row.source_updated_at = source_updated_at
    row.synced_at = now
    row.updated_at = now
    db.add(row)
    return row


def configured_exchange_rate_currencies(db: Session) -> list[str]:
    rows = db.scalars(
        select(ExchangeRateCurrencySetting)
        .where(ExchangeRateCurrencySetting.enabled == True)
        .order_by(ExchangeRateCurrencySetting.currency_code.asc())
    ).all()
    return [row.currency_code for row in rows if row.currency_code]


def _target_sync_dates(rate_date: str | date | None) -> list[date]:
    parsed_date = _parse_date(rate_date)
    if parsed_date:
        return [parsed_date]
    today = datetime.now(SHANGHAI_TZ).date()
    return [today, today - timedelta(days=1)]


async def sync_exchange_rates_from_provider(rate_date: str | date | None = None, replace_existing: bool = False) -> dict:
    db = SessionLocal()
    selected_currencies = configured_exchange_rate_currencies(db)
    db.close()
    dates = _target_sync_dates(rate_date)

    db = SessionLocal()
    synced = 0
    skipped = 0
    failed = 0
    removed_stale = 0
    try:
        selected_set = set(selected_currencies)
        for item_date in dates:
            payloads, provider_failures = await asyncio.to_thread(
                fetch_exchange_rates,
                selected_currencies or None,
                item_date,
            )
            failed += len(provider_failures)
            if selected_set:
                payloads = [
                    payload for payload in payloads
                    if str(payload.get("base_currency") or payload.get("currency_code") or "").strip().upper() in selected_set
                ]
            removed_stale += _delete_stale_exchange_rates(db, item_date, selected_set)
            if not payloads:
                skipped += 1
                db.commit()
                continue
            now = datetime.utcnow()
            if replace_existing:
                db.execute(delete(ExchangeRate).where(ExchangeRate.rate_date == item_date))
            for payload in payloads:
                try:
                    upsert_exchange_rate(db, payload, synced_at=now)
                    synced += 1
                except Exception:
                    failed += 1
            db.commit()
        return {
            "synced": synced,
            "skipped": skipped,
            "failed": failed,
            "message": (
                f"{'清空后同步完成' if replace_existing else '同步完成'}："
                f"成功 {synced} 条，跳过 {skipped} 次，失败 {failed} 条"
                f"{f'，清理 {removed_stale} 条异常日期' if removed_stale else ''}"
            ),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def sync_exchange_rates_from_provider_sync(rate_date: str | date | None = None, replace_existing: bool = False) -> dict:
    return asyncio.run(sync_exchange_rates_from_provider(rate_date, replace_existing=replace_existing))
