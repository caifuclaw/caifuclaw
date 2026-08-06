# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.exchange_rates as exchange_rate_module
from app.database import Base
from app.exchange_rates import sync_exchange_rates_from_provider
from app.models import ExchangeRate, ExchangeRateCurrencySetting


provider_requests: list[tuple[tuple[str, ...], str]] = []
payloads_by_date: dict[str, list[dict]] = {}


def fake_fetch_exchange_rates(currencies, target_date):
    date_key = target_date.isoformat()
    provider_requests.append((tuple(currencies or []), date_key))
    if date_key in payloads_by_date:
        return payloads_by_date[date_key], []
    return [
        {
            "rate_date": date_key,
            "base_currency": "USD",
            "source_currency_name": "美元",
            "rate": "7.12000000",
            "provider_updated_at": "2026-05-27T10:00:00",
        },
        {
            "rate_date": date_key,
            "base_currency": "EUR",
            "source_currency_name": "欧元",
            "rate": "7.76000000",
            "provider_updated_at": "2026-05-27T10:00:00",
        },
        {
            "rate_date": date_key,
            "base_currency": "AED",
            "source_currency_name": "阿联酋迪拉姆",
            "rate": "1.93000000",
            "provider_updated_at": "2026-05-27T10:00:00",
        },
    ], []


@pytest.fixture()
def exchange_rate_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[ExchangeRate.__table__, ExchangeRateCurrencySetting.__table__],
    )
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    provider_requests.clear()
    payloads_by_date.clear()
    monkeypatch.setattr(exchange_rate_module, "SessionLocal", session_factory)
    monkeypatch.setattr(exchange_rate_module, "fetch_exchange_rates", fake_fetch_exchange_rates)
    monkeypatch.setattr(exchange_rate_module, "SHANGHAI_TZ", None)
    return session_factory


def test_replace_sync_only_clears_target_date_and_keeps_configured_currencies(exchange_rate_session):
    with exchange_rate_session() as db:
        db.add_all(
            [
                ExchangeRate(
                    rate_date=date(2026, 5, 26),
                    currency_code="AED",
                    currency_name="旧币别",
                    rate="1.84000000",
                    synced_at=datetime(2026, 5, 26, 14, 50, 45),
                    updated_at=datetime(2026, 5, 26, 14, 50, 45),
                ),
                ExchangeRateCurrencySetting(currency_code="USD", currency_name="美元", enabled=True),
                ExchangeRateCurrencySetting(currency_code="EUR", currency_name="欧元", enabled=True),
            ]
        )
        db.commit()

    result = asyncio.run(sync_exchange_rates_from_provider(rate_date="2026-05-27", replace_existing=True))

    with exchange_rate_session() as db:
        rates = db.scalars(
            select(ExchangeRate).order_by(ExchangeRate.rate_date.asc(), ExchangeRate.currency_code.asc())
        ).all()

    assert result["synced"] == 2
    assert "清空后同步完成" in result["message"]
    assert [(row.rate_date, row.currency_code) for row in rates] == [
        (date(2026, 5, 26), "AED"),
        (date(2026, 5, 27), "EUR"),
        (date(2026, 5, 27), "USD"),
    ]
    assert provider_requests == [(('EUR', 'USD'), '2026-05-27')]


def test_default_sync_requests_today_and_yesterday(exchange_rate_session, monkeypatch):
    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 29, 9, 0, 0)

    monkeypatch.setattr(exchange_rate_module, "datetime", FixedDateTime)
    payloads_by_date.update(
        {
            "2026-05-29": [
                {
                    "rate_date": "2026-05-29",
                    "base_currency": "USD",
                    "source_currency_name": "美元",
                    "rate": "7.18000000",
                    "provider_updated_at": "2026-05-29T10:00:00",
                }
            ],
            "2026-05-28": [
                {
                    "rate_date": "2026-05-28",
                    "base_currency": "USD",
                    "source_currency_name": "美元",
                    "rate": "7.16000000",
                    "provider_updated_at": "2026-05-28T10:00:00",
                }
            ],
        }
    )
    with exchange_rate_session() as db:
        db.add(ExchangeRateCurrencySetting(currency_code="USD", currency_name="美元", enabled=True))
        db.commit()

    result = asyncio.run(sync_exchange_rates_from_provider())

    with exchange_rate_session() as db:
        rates = db.scalars(select(ExchangeRate).order_by(ExchangeRate.rate_date.asc())).all()

    assert result["synced"] == 2
    assert [(row.rate_date, str(row.rate)) for row in rates] == [
        (date(2026, 5, 28), "7.16000000"),
        (date(2026, 5, 29), "7.18000000"),
    ]
    assert provider_requests == [(('USD',), '2026-05-29'), (('USD',), '2026-05-28')]


def test_sync_uses_provider_update_date_instead_of_requested_future_date(exchange_rate_session):
    payloads_by_date["2026-05-31"] = [
        {
            "rate_date": "2026-05-31",
            "base_currency": "USD",
            "source_currency_name": "美元",
            "rate": "7.18000000",
            "provider_updated_at": "2026-05-30T13:00:00",
        }
    ]
    with exchange_rate_session() as db:
        db.add(ExchangeRateCurrencySetting(currency_code="USD", currency_name="美元", enabled=True))
        db.commit()

    result = asyncio.run(sync_exchange_rates_from_provider(rate_date="2026-05-31", replace_existing=True))

    with exchange_rate_session() as db:
        rates = db.scalars(select(ExchangeRate).order_by(ExchangeRate.rate_date.asc())).all()

    assert result["synced"] == 1
    assert [(row.rate_date, row.currency_code, str(row.rate)) for row in rates] == [
        (date(2026, 5, 30), "USD", "7.18000000")
    ]


def test_sync_removes_stale_local_rate_when_provider_has_no_payload(exchange_rate_session):
    payloads_by_date["2026-05-31"] = []
    with exchange_rate_session() as db:
        db.add_all(
            [
                ExchangeRate(
                    rate_date=date(2026, 5, 31),
                    currency_code="USD",
                    currency_name="美元",
                    rate="7.18000000",
                    source_updated_at=datetime(2026, 5, 30, 13, 0, 0),
                    synced_at=datetime(2026, 5, 31, 3, 30, 1),
                    updated_at=datetime(2026, 5, 31, 3, 30, 1),
                ),
                ExchangeRateCurrencySetting(currency_code="USD", currency_name="美元", enabled=True),
            ]
        )
        db.commit()

    result = asyncio.run(sync_exchange_rates_from_provider(rate_date="2026-05-31"))

    with exchange_rate_session() as db:
        rates = db.scalars(select(ExchangeRate)).all()

    assert result["skipped"] == 1
    assert "清理 1 条异常日期" in result["message"]
    assert rates == []
