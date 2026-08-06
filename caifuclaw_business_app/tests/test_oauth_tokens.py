# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime, timedelta

from app.models import PlatformAccount
from app.oauth_tokens import (
    _next_token_refresh_at,
    _token_payload_from_response,
    _token_refresh_due,
)


def test_token_payload_normalizes_expires_in_and_preserves_refresh_token():
    refreshed = _token_payload_from_response(
        "mercadolibre",
        {
            "access_token": "new-access",
            "expires_in": 3600,
            "token_type": "Bearer",
            "user_id": 123,
        },
        "https://api.mercadolibre.com/oauth/token",
        "https://api.mercadolibre.com/oauth/token",
        {"refresh_token": "old-refresh"},
    )

    assert refreshed["access_token"] == "new-access"
    assert refreshed["refresh_token"] == "old-refresh"
    assert refreshed["access_token_expires_at"]
    assert refreshed["expires_at"] == refreshed["access_token_expires_at"]
    assert refreshed["seller_id"] == "123"
    assert refreshed["token_refresh_fail_count"] == 0
    assert refreshed["next_token_refresh_at"]


def test_token_payload_sets_rotated_refresh_token_expiry_for_mercadolibre():
    refreshed = _token_payload_from_response(
        "mercadolibre",
        {
            "access_token": "new-access",
            "refresh_token": "new-refresh",
            "expires_in": 21600,
        },
        "https://api.mercadolibre.com/oauth/token",
        "https://api.mercadolibre.com/oauth/token",
        {"refresh_token": "old-refresh"},
    )

    refresh_expires_at = datetime.fromisoformat(refreshed["refresh_token_expires_at"])
    last_refresh_at = datetime.fromisoformat(refreshed["last_token_refresh_at"])

    assert refreshed["refresh_token"] == "new-refresh"
    assert refresh_expires_at - last_refresh_at == timedelta(days=180)


def test_token_refresh_due_uses_platform_window():
    now = datetime(2026, 5, 26, 8, 0, 0)
    account = PlatformAccount(platform="mercadolibre", account_id="ml-1")
    credentials = {
        "access_token": "access",
        "refresh_token": "refresh",
        "access_token_expires_at": (now + timedelta(minutes=59)).isoformat(),
    }

    due, reason = _token_refresh_due("mercadolibre", credentials, account, now)

    assert due is True
    assert reason == "access_token_expiring"


def test_allegro_not_due_outside_refresh_window():
    now = datetime(2026, 5, 26, 8, 0, 0)
    account = PlatformAccount(platform="allegro", account_id="a-1")
    credentials = {
        "access_token": "access",
        "refresh_token": "refresh",
        "access_token_expires_at": (now + timedelta(hours=3)).isoformat(),
    }

    due, reason = _token_refresh_due("allegro", credentials, account, now)

    assert due is False
    assert reason == ""


def test_missing_access_expiry_triggers_one_refresh_to_backfill_expiry():
    now = datetime(2026, 5, 26, 8, 0, 0)
    account = PlatformAccount(platform="joom_logistics", account_id="j-1")
    credentials = {"access_token": "access", "refresh_token": "refresh"}

    due, reason = _token_refresh_due("joom_logistics", credentials, account, now)

    assert due is True
    assert reason == "missing_access_token_expires_at"


def test_missing_refresh_token_requires_maintenance_attention():
    now = datetime(2026, 5, 26, 8, 0, 0)
    account = PlatformAccount(platform="mercadolibre", account_id="ml-1")
    credentials = {"access_token": "access"}

    due, reason = _token_refresh_due("mercadolibre", credentials, account, now)

    assert due is True
    assert reason == "missing_refresh_token"


def test_next_token_refresh_chooses_earliest_platform_policy():
    now = datetime(2026, 5, 26, 8, 0, 0)
    credentials = {
        "access_token_expires_at": (now + timedelta(hours=12)).isoformat(),
        "refresh_token_expires_at": (now + timedelta(days=10)).isoformat(),
    }

    assert _next_token_refresh_at("allegro", credentials, now) == now - timedelta(days=4)
