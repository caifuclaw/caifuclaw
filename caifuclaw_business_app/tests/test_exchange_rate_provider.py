from datetime import date
from decimal import Decimal

from app.exchange_rate_provider import _all_currency_payloads, _single_currency_payload


def test_single_currency_payload_normalizes_cny_quote():
    payload = _single_currency_payload(
        "EUR",
        {
            "name": "欧元",
            "list": {
                "CNY": {
                    "name": "人民币",
                    "rate": "7.76000000",
                    "updatetime": "2026-05-27 10:00:00",
                }
            },
        },
        date(2026, 5, 27),
    )

    assert payload["rate_date"] == "2026-05-27"
    assert payload["base_currency"] == "EUR"
    assert payload["quote_currency"] == "CNY"
    assert Decimal(payload["rate"]) == Decimal("7.76000000")


def test_full_quote_table_converts_cross_rates_to_cny():
    payloads = _all_currency_payloads(
        {
            "currency": "USD",
            "name": "美元",
            "list": {
                "CNY": {"name": "人民币", "rate": "7.2", "updatetime": "2026-05-27 10:00:00"},
                "EUR": {"name": "欧元", "rate": "0.9", "updatetime": "2026-05-27 10:00:00"},
            },
        },
        date(2026, 5, 27),
    )

    by_currency = {row["base_currency"]: row for row in payloads}
    assert Decimal(by_currency["USD"]["rate"]) == Decimal("7.2")
    assert Decimal(by_currency["EUR"]["rate"]) == Decimal("8")
