# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime, timedelta

from app.sync_engine import _effective_order_sync_since


def test_mercado_incremental_sync_uses_default_lookback_window():
    last_sync_at = datetime(2026, 6, 26, 16, 8, 2)

    assert _effective_order_sync_since("mercadolibre", last_sync_at, {}) == last_sync_at - timedelta(minutes=30)


def test_mercado_incremental_sync_allows_account_lookback_override():
    last_sync_at = datetime(2026, 6, 26, 16, 8, 2)

    assert _effective_order_sync_since(
        "mercadolibre",
        last_sync_at,
        {"mercado_incremental_lookback_seconds": 120},
    ) == last_sync_at - timedelta(seconds=120)
    assert _effective_order_sync_since(
        "mercadolibre",
        last_sync_at,
        {"mercado_incremental_lookback_seconds": 0},
    ) == last_sync_at


def test_mercado_explicit_sync_since_is_not_shifted_again():
    since = datetime(2026, 6, 26, 16, 4, 0)
    last_sync_at = datetime(2026, 6, 26, 17, 17, 59)

    assert _effective_order_sync_since(
        "mercadolibre",
        last_sync_at,
        {},
        since_override=since,
    ) == since


def test_non_mercado_incremental_sync_keeps_existing_cursor():
    last_sync_at = datetime(2026, 6, 26, 16, 8, 2)

    assert _effective_order_sync_since("ozon", last_sync_at, {}) == last_sync_at
