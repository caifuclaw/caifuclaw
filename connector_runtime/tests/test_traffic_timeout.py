import asyncio

import httpx
import pytest

import app.api.routes.connectors as connectors_module
from app.schemas import TrafficRequest


@pytest.mark.asyncio
async def test_traffic_endpoint_cancels_connector_and_returns_timeout(monkeypatch):
    cancelled = asyncio.Event()

    class SlowConnector:
        async def fetch_traffic(self, _start, _end):
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

    monkeypatch.setattr(connectors_module, "_connector", lambda *_args: SlowConnector())
    monkeypatch.setattr(connectors_module, "_traffic_sync_timeout_seconds", lambda *_args: 0.01)

    response = await connectors_module.fetch_traffic(
        "ozon",
        TrafficRequest(start="2026-07-22T00:00:00", end="2026-07-28T23:59:59"),
    )

    assert cancelled.is_set()
    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "TRAFFIC_SYNC_TIMEOUT"
    assert response.error.retryable is True


def test_traffic_timeout_defaults_are_platform_specific():
    payload = TrafficRequest(start="2026-07-22T00:00:00", end="2026-07-28T23:59:59")

    assert connectors_module._traffic_sync_timeout_seconds("allegro", payload) == 5 * 60
    assert connectors_module._traffic_sync_timeout_seconds("joomlogistics", payload) == 15 * 60
    assert connectors_module._traffic_sync_timeout_seconds("ozon", payload) == 30 * 60
    assert connectors_module._traffic_sync_timeout_seconds("wildberries", payload) == 30 * 60
    assert connectors_module._traffic_sync_timeout_seconds("mercadolibre", payload) == 130 * 60


def test_transport_disconnect_is_reported_as_retryable_platform_error():
    response = connectors_module._failure(
        "ozon",
        httpx.RemoteProtocolError("Server disconnected without sending a response."),
    )

    assert response.ok is False
    assert response.error is not None
    assert response.error.code == "TEMPORARY_PLATFORM_ERROR"
    assert response.error.retryable is True
