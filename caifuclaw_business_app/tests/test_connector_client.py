from datetime import datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.connector_client import ConnectorRuntimeClient, ConnectorRuntimeError
from app.connectors.base import NormalizedOrder


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("runtime_url", "expected_trust_env"),
    [
        ("http://127.0.0.1:8100", False),
        ("http://localhost:8100", False),
        ("https://connectors.example.com", True),
    ],
)
async def test_connector_runtime_proxy_behavior(monkeypatch, runtime_url, expected_trust_env):
    client_options = {}

    class FakeAsyncClient:
        def __init__(self, **kwargs):
            client_options.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, json, headers):
            client_options["request_headers"] = headers
            return httpx.Response(200, json={"ok": True, "data": []})

    monkeypatch.setattr("app.connector_client.httpx.AsyncClient", FakeAsyncClient)
    connector = ConnectorRuntimeClient(
        runtime_url=runtime_url,
        platform="mercadolibre",
        credentials={},
        settings={},
    )

    await connector._post("traffic/fetch", {}, timeout=10)

    assert client_options["trust_env"] is expected_trust_env
    assert client_options["request_headers"] == {}


@pytest.mark.asyncio
async def test_connector_runtime_sends_internal_service_token(monkeypatch):
    captured = {}

    class FakeAsyncClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, json, headers):
            captured.update(url=url, body=json, headers=headers)
            return httpx.Response(200, json={"ok": True, "data": []})

    monkeypatch.setattr("app.connector_client.httpx.AsyncClient", FakeAsyncClient)
    connector = ConnectorRuntimeClient(
        runtime_url="http://127.0.0.1:8100",
        platform="ozon",
        credentials={},
        settings={},
        internal_service_token="service-secret",
    )

    await connector._post("traffic/fetch", {}, timeout=10)

    assert captured["headers"] == {"X-Internal-Service-Token": "service-secret"}


@pytest.mark.asyncio
async def test_fetch_traffic_passes_platform_deadline_to_runtime(monkeypatch):
    captured = {}
    connector = ConnectorRuntimeClient(
        runtime_url="http://127.0.0.1:8100",
        platform="wildberries",
        credentials={},
        settings={},
    )

    async def fake_post(action, payload, *, timeout):
        captured.update(action=action, payload=payload, timeout=timeout)
        return []

    monkeypatch.setattr(connector, "_post", fake_post)

    await connector.fetch_traffic(datetime(2026, 7, 22), datetime(2026, 7, 28))

    assert captured["action"] == "traffic/fetch"
    assert captured["payload"]["timeout_seconds"] == 30 * 60
    assert captured["timeout"] == 31 * 60


@pytest.mark.asyncio
async def test_fetch_traffic_maps_runtime_http_timeout_to_structured_timeout(monkeypatch):
    connector = ConnectorRuntimeClient(
        runtime_url="http://127.0.0.1:8100",
        platform="joom_logistics",
        credentials={},
        settings={"traffic_sync_timeout_seconds": 120},
    )

    async def fake_post(*_args, **_kwargs):
        raise httpx.ReadTimeout("runtime did not respond")

    monkeypatch.setattr(connector, "_post", fake_post)

    with pytest.raises(ConnectorRuntimeError) as caught:
        await connector.fetch_traffic(datetime(2026, 7, 22), datetime(2026, 7, 28))

    assert caught.value.code == "TRAFFIC_SYNC_TIMEOUT"
    assert caught.value.retryable is True
    assert "2 分钟" in str(caught.value)


@pytest.mark.asyncio
async def test_fetch_traffic_retries_runtime_disconnect(monkeypatch):
    connector = ConnectorRuntimeClient(
        runtime_url="http://127.0.0.1:8100",
        platform="ozon",
        credentials={},
        settings={},
    )
    post = AsyncMock(
        side_effect=[
            httpx.RemoteProtocolError("Server disconnected without sending a response."),
            [{"sku": "DEMO-SKU-0005"}],
        ]
    )
    sleep = AsyncMock()
    monkeypatch.setattr(connector, "_post", post)
    monkeypatch.setattr("app.connector_client.asyncio.sleep", sleep)

    rows = await connector.fetch_traffic(datetime(2026, 7, 22), datetime(2026, 7, 28))

    assert rows == [{"sku": "DEMO-SKU-0005"}]
    assert post.await_count == 2
    sleep.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_fetch_traffic_reports_retryable_error_after_runtime_disconnects(monkeypatch):
    connector = ConnectorRuntimeClient(
        runtime_url="http://127.0.0.1:8100",
        platform="ozon",
        credentials={},
        settings={},
    )
    monkeypatch.setattr(
        connector,
        "_post",
        AsyncMock(side_effect=httpx.RemoteProtocolError("Server disconnected without sending a response.")),
    )
    monkeypatch.setattr("app.connector_client.asyncio.sleep", AsyncMock())

    with pytest.raises(ConnectorRuntimeError) as caught:
        await connector.fetch_traffic(datetime(2026, 7, 22), datetime(2026, 7, 28))

    assert caught.value.code == "TEMPORARY_PLATFORM_ERROR"
    assert caught.value.retryable is True
    assert "自动重试 5 次" in str(caught.value)


@pytest.mark.asyncio
async def test_register_tracking_number_uses_runtime_shipment_action(monkeypatch):
    captured = {}
    connector = ConnectorRuntimeClient(
        runtime_url="http://127.0.0.1:8100",
        platform="allegro",
        credentials={},
        settings={},
        account_id="ALG-1",
    )

    async def fake_post(action, payload, *, timeout):
        captured.update(action=action, payload=payload, timeout=timeout)
        return {
            "platform_shipment_id": "shipment-wanbang-1",
            "tracking_number": "WB-TRACK-1",
            "carrier": "WanbExpress",
            "status": "registered",
        }

    monkeypatch.setattr(connector, "_post", fake_post)
    result = await connector.register_tracking_number(
        NormalizedOrder("cf-1", "READY_FOR_PROCESSING", {}),
        "WB-TRACK-1",
        "WanbExpress",
    )

    assert captured == {
        "action": "shipments/register-tracking",
        "payload": {
            "order": {
                "platform_order_id": "cf-1",
                "platform_status": "READY_FOR_PROCESSING",
                "raw_payload": {},
                "platform_order_no": "",
                "posting_number": "",
                "fulfillment_type": "FBS",
                "is_overseas_warehouse": False,
            },
            "tracking_number": "WB-TRACK-1",
            "carrier": "WanbExpress",
        },
        "timeout": 90,
    }
    assert result.status == "registered"
