# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from email.utils import formatdate
from zoneinfo import ZoneInfo

import httpx

from .config_loader import optional


SOURCE_TENCENT_MARKET = "tencent_cloud_market"
QUOTE_CURRENCY = "CNY"
BASE_FETCH_CURRENCY = "USD"
DEFAULT_ENDPOINT = "https://ap-shanghai.cloudmarket-apigw.com/service-p90qcght/exchange/single"
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")


def provider_enabled() -> bool:
    return bool(optional("exchange_rates", "enabled", True))


def _config_value(key: str, default: str = "") -> str:
    env_key = f"TENCENT_EXCHANGE_{key.upper()}"
    return str(os.getenv(env_key) or optional("exchange_rates.tencent_cloud_market", key, default) or default)


def _provider_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None


def _decimal_rate(currency: str, payload: dict) -> Decimal:
    try:
        rate = Decimal(str(payload.get("rate")))
    except (InvalidOperation, TypeError) as exc:
        raise RuntimeError(f"{currency} returned an invalid rate") from exc
    if rate <= 0:
        raise RuntimeError(f"{currency} returned a non-positive rate")
    return rate


class TencentMarketExchangeClient:
    def __init__(self) -> None:
        self.secret_id = _config_value("secret_id")
        self.secret_key = _config_value("secret_key")
        self.endpoint = _config_value("endpoint", DEFAULT_ENDPOINT)
        if not self.secret_id or not self.secret_key:
            raise RuntimeError("Tencent exchange rate API credentials are not configured")

    def _headers(self) -> dict[str, str]:
        x_date = formatdate(timeval=None, localtime=False, usegmt=True)
        signature = base64.b64encode(
            hmac.new(
                self.secret_key.encode("utf-8"),
                f"x-date: {x_date}".encode("utf-8"),
                hashlib.sha1,
            ).digest()
        ).decode("utf-8")
        authorization = json.dumps(
            {"id": self.secret_id, "x-date": x_date, "signature": signature},
            ensure_ascii=True,
            separators=(",", ":"),
        )
        return {"request-id": str(uuid.uuid1()), "Authorization": authorization}

    def fetch_currency(self, currency: str) -> dict:
        currency = currency.strip().upper()
        if not currency or currency == QUOTE_CURRENCY:
            raise ValueError("currency must be non-empty and different from CNY")
        with httpx.Client(timeout=30) as client:
            response = client.get(self.endpoint, params={"currency": currency}, headers=self._headers())
        if response.status_code >= 300:
            raise RuntimeError(f"exchange rate provider HTTP {response.status_code}: {response.text[:300]}")
        try:
            payload = response.json()
        except ValueError as exc:
            raise RuntimeError("exchange rate provider returned invalid JSON") from exc
        if str(payload.get("status")) != "0" or not isinstance(payload.get("result"), dict):
            raise RuntimeError(str(payload.get("msg") or "exchange rate provider returned an error"))
        return payload["result"]


def _single_currency_payload(currency: str, result: dict, target_date: date) -> dict:
    rates = result.get("list")
    if not isinstance(rates, dict) or QUOTE_CURRENCY not in rates:
        raise RuntimeError(f"{currency} response does not contain a CNY quote")
    cny = rates.get(QUOTE_CURRENCY) or {}
    updated_at = _provider_datetime(cny.get("updatetime"))
    return {
        "rate_date": (updated_at.date() if updated_at else target_date).isoformat(),
        "base_currency": currency,
        "quote_currency": QUOTE_CURRENCY,
        "rate": str(_decimal_rate(currency, cny)),
        "source": SOURCE_TENCENT_MARKET,
        "source_currency_name": str(result.get("name") or currency),
        "quote_currency_name": str(cny.get("name") or "CNY"),
        "provider_updated_at": updated_at.isoformat() if updated_at else None,
    }


def _all_currency_payloads(result: dict, target_date: date) -> list[dict]:
    base_currency = str(result.get("currency") or "").strip().upper()
    rates = result.get("list")
    if not base_currency or not isinstance(rates, dict) or QUOTE_CURRENCY not in rates:
        raise RuntimeError("exchange rate provider returned an incomplete quote table")
    cny = rates.get(QUOTE_CURRENCY) or {}
    base_to_cny = _decimal_rate(QUOTE_CURRENCY, cny)
    base_name = str(result.get("name") or base_currency)
    cny_name = str(cny.get("name") or QUOTE_CURRENCY)
    rows: list[dict] = []
    for currency, payload in {base_currency: cny, **rates}.items():
        currency_code = str(currency or "").strip().upper()
        if not currency_code or currency_code == QUOTE_CURRENCY:
            continue
        quote = payload or {}
        rate = base_to_cny if currency_code == base_currency else base_to_cny / _decimal_rate(currency_code, quote)
        updated_at = _provider_datetime(quote.get("updatetime") or cny.get("updatetime"))
        rows.append(
            {
                "rate_date": (updated_at.date() if updated_at else target_date).isoformat(),
                "base_currency": currency_code,
                "quote_currency": QUOTE_CURRENCY,
                "rate": str(rate),
                "source": SOURCE_TENCENT_MARKET,
                "source_currency_name": base_name if currency_code == base_currency else str(quote.get("name") or currency_code),
                "quote_currency_name": cny_name,
                "provider_updated_at": updated_at.isoformat() if updated_at else None,
            }
        )
    return rows


def fetch_exchange_rates(currencies: list[str] | None, target_date: date) -> tuple[list[dict], list[dict]]:
    if not provider_enabled():
        return [], []
    client = TencentMarketExchangeClient()
    selected = list(dict.fromkeys(str(item).strip().upper() for item in currencies or [] if str(item).strip().upper() != QUOTE_CURRENCY))
    if not selected:
        base_currency = str(optional("exchange_rates", "base_fetch_currency", BASE_FETCH_CURRENCY) or BASE_FETCH_CURRENCY).upper()
        return _all_currency_payloads(client.fetch_currency(base_currency), target_date), []
    success: list[dict] = []
    failed: list[dict] = []
    for currency in selected:
        try:
            success.append(_single_currency_payload(currency, client.fetch_currency(currency), target_date))
        except Exception as exc:
            failed.append({"currency": currency, "error": str(exc)})
    return success, failed
