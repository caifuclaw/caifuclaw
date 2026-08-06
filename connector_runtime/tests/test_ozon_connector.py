# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime

import pytest
import respx
from httpx import Response

from app.adapters.base import NormalizedOrder, ShipmentResult
from app.adapters.ozon import OzonApiError, OzonConnector


@pytest.mark.asyncio
@respx.mock
async def test_get_products_by_offer_ids_uses_product_info_endpoint():
    route = respx.post("https://api-seller.ozon.ru/v3/product/info/list").mock(
        return_value=Response(
            200,
            json={"items": [{"id": 987654, "offer_id": "SKU-001", "sku": 123456789}]},
        )
    )
    connector = OzonConnector(
        {"client_id": "100001", "api_key": "test"},
        {"base_url": "https://api-seller.ozon.ru"},
    )

    result = await connector.get_products_by_offer_ids(["SKU-001", "SKU-001", ""])

    assert result["items"][0]["id"] == 987654
    assert route.calls.last.request.read().decode() == '{"offer_id":["SKU-001"],"product_id":[],"sku":[]}'


@pytest.mark.asyncio
@respx.mock
async def test_fetch_unprocessed_orders_maps_postings():
    route = respx.post("https://api-seller.ozon.ru/v4/posting/fbs/list").mock(
        return_value=Response(
            200,
            json={
                "postings": [
                    {"order_id": 1, "order_number": "A-1", "posting_number": "DEMO-ORDER-0137", "status": "awaiting_packaging", "products": []},
                    {"order_id": 2, "order_number": "A-2", "posting_number": "DEMO-ORDER-0138", "status": "delivering", "products": []},
                ],
                "has_next": False,
            },
        )
    )
    connector = OzonConnector(
        {"client_id": "100001", "api_key": "test"},
        {"dry_run_fulfillment": True, "base_url": "https://api-seller.ozon.ru"},
    )
    orders = await connector.fetch_unprocessed_orders(since=datetime(2026, 5, 13, 2, 26, 10, 893827))
    assert route.calls.last.request.content
    request_json = route.calls.last.request.read().decode()
    assert '"since":"2026-05-13T01:26:10Z"' in request_json
    assert '"to":"' in request_json and 'Z"' in request_json
    assert len(orders) == 2
    assert orders[0].platform_order_id == "1"
    assert orders[0].platform_status == "awaiting_packaging"
    assert orders[0].is_overseas_warehouse is False
    assert orders[1].is_overseas_warehouse is False


@pytest.mark.asyncio
@respx.mock
async def test_fetch_unprocessed_orders_marks_fbp_as_overseas_when_downloaded():
    respx.post("https://api-seller.ozon.ru/v4/posting/fbs/list").mock(
        return_value=Response(
            200,
            json={
                "postings": [
                    {
                        "order_id": 2,
                        "order_number": "A-2",
                        "posting_number": "DEMO-ORDER-0138",
                        "status": "delivering",
                        "products": [],
                        "analytics_data": {"tpl_provider": "Ozon FBP"},
                    },
                ],
                "has_next": False,
            },
        )
    )
    connector = OzonConnector(
        {"client_id": "100001", "api_key": "test"},
        {
            "dry_run_fulfillment": True,
            "base_url": "https://api-seller.ozon.ru",
            "fbo_fbp_download_mode": "to_unshipped",
        },
    )
    orders = await connector.fetch_unprocessed_orders(since=datetime(2026, 5, 13, 2, 26, 10, 893827))

    assert len(orders) == 1
    assert orders[0].fulfillment_type == "FBP"
    assert orders[0].is_overseas_warehouse is True


@pytest.mark.asyncio
async def test_dry_run_label_is_pdf():
    connector = OzonConnector(
        {"client_id": "100001", "api_key": "test"},
        {"dry_run_fulfillment": True, "base_url": "https://api-seller.ozon.ru"},
    )
    normalized = NormalizedOrder("123-1", "awaiting_packaging", {"posting_number": "DEMO-ORDER-0137"})
    shipment = ShipmentResult(platform_shipment_id="DEMO-ORDER-0137", tracking_number="DEMO-TRACKING-0034")
    label = await connector.fetch_label(shipment, normalized)
    assert label.content.startswith(b"%PDF")
    assert label.content_type == "application/pdf"


@pytest.mark.asyncio
@respx.mock
async def test_label_error_includes_ozon_body():
    respx.post("https://api-seller.ozon.ru/v2/posting/fbs/package-label").mock(
        return_value=Response(400, json={"code": 3, "message": "INVALID_ARGUMENT"})
    )
    connector = OzonConnector(
        {"client_id": "100001", "api_key": "test"},
        {"dry_run_fulfillment": False, "base_url": "https://api-seller.ozon.ru"},
    )
    normalized = NormalizedOrder("123-1", "delivering", {"posting_number": "DEMO-ORDER-0137"})
    shipment = ShipmentResult(platform_shipment_id="DEMO-ORDER-0137", tracking_number="DEMO-TRACKING-0034")

    with pytest.raises(OzonApiError) as exc_info:
        await connector.fetch_label(shipment, normalized)

    assert exc_info.value.status_code == 400
    assert "INVALID_ARGUMENT" in str(exc_info.value)


@pytest.mark.asyncio
@respx.mock
async def test_status_updates_do_not_fallback_to_posting_number_as_tracking():
    respx.post("https://api-seller.ozon.ru/v3/posting/fbs/list").mock(
        return_value=Response(
            200,
            json={
                "result": {
                    "postings": [
                        {
                            "order_id": 30000000001,
                            "order_number": "DEMO-ORDER-0033",
                            "posting_number": "DEMO-ORDER-0033",
                            "status": "awaiting_deliver",
                        }
                    ]
                }
            },
        )
    )
    connector = OzonConnector(
        {"client_id": "100001", "api_key": "test"},
        {"base_url": "https://api-seller.ozon.ru"},
    )

    updates = await connector.fetch_order_status_updates(["DEMO-ORDER-0033"])

    assert updates[0].posting_number == "DEMO-ORDER-0033"
    assert updates[0].platform_status == "awaiting_deliver"
    assert updates[0].shipment_tracking_number == ""

