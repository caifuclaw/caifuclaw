# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import base64
import json
from datetime import datetime

import pytest
import respx
from httpx import Response

from app.adapters.allegro import AllegroConnector
from app.adapters.base import NormalizedOrder, ShipmentResult
from app.adapters.joom import JoomLogisticsConnector
from app.adapters.mercado import MercadoGlobalConnector
from app.adapters.wildberries import WildberriesConnector


def _normalized_order_item_payloads(raw_payload: dict, fallback_currency: str = "") -> list[dict]:
    products = raw_payload.get("products") or []
    result = []
    for item in products:
        price = item.get("price") if isinstance(item.get("price"), dict) else {}
        result.append(
            {
                "sku": item.get("sku") or "",
                "platform_product_name": item.get("name") or "",
                "quantity": item.get("quantity") or 1,
                "unit_price": price.get("amount") if price else item.get("price"),
                "currency": price.get("currency") or item.get("currency") or fallback_currency,
                "raw_payload": item,
            }
        )
    return result


def test_normalized_order_items_keep_platform_product_name():
    payload = {
        "products": [
            {
                "sku": "SKU-1",
                "name": "Platform Item Name",
                "quantity": 2,
                "price": {"amount": "12.34", "currency": "USD"},
            }
        ]
    }

    items = _normalized_order_item_payloads(payload, "USD")

    assert items[0]["sku"] == "SKU-1"
    assert items[0]["platform_product_name"] == "Platform Item Name"


@pytest.mark.asyncio
@respx.mock
async def test_mercado_fetch_platform_products_requests_and_keeps_pictures():
    respx.get("https://api.mercadolibre.com/users/1/items/search").mock(
        return_value=Response(200, json={"results": ["MLM-1"], "scroll_id": ""})
    )
    details_route = respx.get("https://api.mercadolibre.com/items").mock(
        return_value=Response(
            200,
            json=[
                {
                    "code": 200,
                    "body": {
                        "id": "MLM-1",
                        "title": "Mercado Product",
                        "status": "active",
                        "seller_custom_field": "SKU-ML-1",
                        "price": 12.34,
                        "currency_id": "USD",
                        "available_quantity": 4,
                        "pictures": [{"id": "PIC-1", "url": "https://cdn.example.test/ml-main.jpg"}],
                        "variations": [],
                    },
                }
            ],
        ),
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "1"},
        {"base_url": "https://api.mercadolibre.com", "mercado_site": "MLM"},
    )

    rows = await connector.fetch_platform_products()

    assert details_route.called
    assert "pictures" in details_route.calls[0].request.url.params["attributes"]
    assert rows[0]["raw_payload"]["item"]["pictures"][0]["url"] == "https://cdn.example.test/ml-main.jpg"


def test_mercado_new_local_sites_use_local_api_mode():
    for site_id in ("MLA", "MEC", "MPE", "MLU"):
        connector = MercadoGlobalConnector(
            {"access_token": "token"},
            {"base_url": "https://api.mercadolibre.com", "mercado_site": site_id},
        )

        assert connector.api_mode == "local"
        assert connector._order_search_path() == "/orders/search"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_fetch_platform_products_uses_active_offers():
    route = respx.get("https://api.allegro.pl/sale/offers").mock(
        return_value=Response(
            200,
            json={
                "offers": [
                    {
                        "id": "offer-1",
                        "name": "Allegro Item",
                        "external": {"id": "SKU-ALLEGRO-1"},
                        "publication": {
                            "status": "ACTIVE",
                            "marketplaces": {"base": {"id": "allegro-pl", "name": "Allegro PL"}},
                        },
                        "sellingMode": {"price": {"amount": "19.99", "currency": "PLN"}},
                        "stock": {"available": 7, "sold": 1, "unit": "pcs"},
                    }
                ],
                "totalCount": 1,
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"base_url": "https://api.allegro.pl"},
    )

    rows = await connector.fetch_platform_products()

    assert route.called
    assert route.calls.last.request.url.params["publication.status"] == "ACTIVE"
    assert route.calls.last.request.url.params["limit"] == "1000"
    assert rows[0]["platform_product_id"] == "offer-1"
    assert rows[0]["platform_sku"] == "SKU-ALLEGRO-1"
    assert rows[0]["product_name"] == "Allegro Item"
    assert rows[0]["listing_status"] == "ACTIVE"
    assert rows[0]["available_stock"] == 7
    assert rows[0]["price_amount"] == "19.99"
    assert rows[0]["price_currency"] == "PLN"
    assert rows[0]["raw_payload"]["marketplace_id"] == "allegro-pl"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_fetch_orders_and_preview_label():
    shipments_route = respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(200, json={"shipments": [{"id": "shipment-1", "waybill": "WAYBILL-1", "carrierId": "DPD"}]})
    )
    route = respx.get("https://api.allegro.pl/order/checkout-forms").mock(
        return_value=Response(
            200,
            json={
                "checkoutForms": [
                    {
                        "id": "cf-1",
                        "fulfillment": {"status": "READY_FOR_PROCESSING"},
                        "buyer": {"id": "buyer-1", "login": "buyer"},
                        "summary": {"totalToPay": {"amount": "10.00", "currency": "PLN"}},
                        "lineItems": [{"offer": {"id": "sku-1", "name": "Item"}, "quantity": 1, "price": {"amount": "10.00", "currency": "PLN"}}],
                    }
                ]
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": True, "base_url": "https://api.allegro.pl"},
    )
    orders = await connector.fetch_unprocessed_orders()
    request = route.calls.last.request
    assert request.url.params["status"] == "READY_FOR_PROCESSING"
    assert "fulfillment.status" not in request.url.params
    assert orders[0].platform_order_id == "cf-1"
    assert orders[0].raw_payload["shipment_tracking_number"] == "WAYBILL-1"
    assert orders[0].raw_payload["shipping"]["tracking_number"] == "WAYBILL-1"
    assert shipments_route.called
    assert orders[0].is_overseas_warehouse is False
    label = await connector.fetch_label(ShipmentResult("cf-1", "cf-1"), orders[0])
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_allegro_create_order_shipment_before_label():
    route = respx.post("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(
            201,
            json={
                "id": "shipment-1",
                "waybill": "",
                "carrierId": "0c0ffe5b-1d12-41b2-9176-f9906416c8ff",
                "lineItems": [{"id": "line-1"}],
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {
            "dry_run_fulfillment": False,
            "base_url": "https://api.allegro.pl",
            "allegro_carrier_id": "0c0ffe5b-1d12-41b2-9176-f9906416c8ff",
        },
    )
    order = NormalizedOrder(
        "cf-1",
        "READY_FOR_PROCESSING",
        {"lineItems": [{"id": "line-1"}, {"id": "line-2"}]},
        posting_number="cf-1",
    )

    shipment = await connector.create_platform_shipment(order)

    request = route.calls.last.request
    assert request.headers["accept"] == "application/vnd.allegro.public.v1+json"
    assert json.loads(request.content) == {
        "carrierId": "0c0ffe5b-1d12-41b2-9176-f9906416c8ff",
        "waybill": "",
        "lineItems": [{"id": "line-1"}, {"id": "line-2"}],
    }
    assert shipment.platform_shipment_id == "shipment-1"
    assert shipment.tracking_number == ""
    assert shipment.carrier == "0c0ffe5b-1d12-41b2-9176-f9906416c8ff"
    assert shipment.raw_payload["id"] == "shipment-1"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_registers_external_wanbang_tracking_idempotently():
    lookup = respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(200, json={"shipments": []})
    )
    create = respx.post("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(
            201,
            json={
                "id": "shipment-wanbang-1",
                "waybill": "WB-TRACK-1",
                "carrierId": "OTHER",
                "carrierName": "WanbExpress",
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://api.allegro.pl"},
    )
    order = NormalizedOrder(
        "cf-1",
        "READY_FOR_PROCESSING",
        {"lineItems": [{"id": "line-1"}]},
        posting_number="cf-1",
    )

    shipment = await connector.register_tracking_number(order, "WB-TRACK-1", "WanbExpress")

    assert lookup.called
    assert json.loads(create.calls.last.request.content) == {
        "carrierId": "OTHER",
        "carrierName": "WanbExpress",
        "waybill": "WB-TRACK-1",
        "lineItems": [{"id": "line-1"}],
    }
    assert shipment.platform_shipment_id == "shipment-wanbang-1"
    assert shipment.status == "registered"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_external_tracking_does_not_duplicate_existing_waybill():
    lookup = respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(
            200,
            json={"shipments": [{"id": "shipment-wanbang-1", "waybill": "WB-TRACK-1", "carrierName": "WanbExpress"}]},
        )
    )
    create = respx.post("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(201, json={"id": "should-not-be-created"})
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://api.allegro.pl"},
    )
    order = NormalizedOrder("cf-1", "READY_FOR_PROCESSING", {}, posting_number="cf-1")

    shipment = await connector.register_tracking_number(order, "WB-TRACK-1", "WanbExpress")

    assert lookup.called
    assert not create.called
    assert shipment.platform_shipment_id == "shipment-wanbang-1"
    assert shipment.status == "existing"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_label_request_accepts_binary_response():
    route = respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments/shipment-1/label").mock(
        return_value=Response(200, content=b"%PDF-allegro-label")
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://api.allegro.pl"},
    )
    order = NormalizedOrder("cf-1", "SENT", {}, posting_number="cf-1")

    label = await connector.fetch_label(ShipmentResult("shipment-1", "WAYBILL-1"), order)

    request = route.calls.last.request
    assert request.headers["accept"] == "application/pdf"
    assert label.content == b"%PDF-allegro-label"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_label_not_found_falls_back_to_wza_label_endpoint():
    order_label_route = respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments/shipment-1/label").mock(
        return_value=Response(404, json={"errors": [{"userMessage": "Feature unavailable. Contact the application author."}]})
    )
    wza_route = respx.post("https://api.allegro.pl/shipment-management/label").mock(
        return_value=Response(200, content=b"%PDF-wza-label")
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://api.allegro.pl"},
    )
    order = NormalizedOrder("cf-1", "SENT", {}, posting_number="cf-1")

    label = await connector.fetch_label(ShipmentResult("shipment-1", "WAYBILL-1"), order)

    request = wza_route.calls.last.request
    assert order_label_route.called
    assert request.headers["accept"] == "application/octet-stream, application/pdf, */*"
    assert json.loads(request.content.decode()) == {"shipmentIds": ["shipment-1"]}
    assert label.content == b"%PDF-wza-label"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_label_empty_response_reports_no_label():
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments/shipment-1/label").mock(return_value=Response(404))
    respx.post("https://api.allegro.pl/shipment-management/label").mock(return_value=Response(204))
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://api.allegro.pl"},
    )
    order = NormalizedOrder("cf-1", "SENT", {}, posting_number="cf-1")

    with pytest.raises(RuntimeError, match="没有可下载标签"):
        await connector.fetch_label(ShipmentResult("shipment-1", "WAYBILL-1"), order)


@pytest.mark.asyncio
@respx.mock
async def test_allegro_label_not_acceptable_reports_unavailable_label():
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments/shipment-1/label").mock(return_value=Response(404))
    respx.post("https://api.allegro.pl/shipment-management/label").mock(return_value=Response(406))
    connector = AllegroConnector(
        {"access_token": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://api.allegro.pl"},
    )
    order = NormalizedOrder("cf-1", "SENT", {}, posting_number="cf-1")

    with pytest.raises(RuntimeError, match="406 Not Acceptable"):
        await connector.fetch_label(ShipmentResult("shipment-1", "WAYBILL-1"), order)


@pytest.mark.asyncio
@respx.mock
async def test_allegro_fulfillment_status_uses_fulfillment_filter():
    route = respx.get("https://api.allegro.pl/order/checkout-forms").mock(
        return_value=Response(200, json={"checkoutForms": []})
    )
    respx.get("https://api.allegro.pl/order/events").mock(return_value=Response(200, json={"events": []}))
    connector = AllegroConnector(
        {"access_token": "token"},
        {
            "base_url": "https://api.allegro.pl",
            "allegro_fulfillment_status": "PROCESSING",
        },
    )

    await connector.fetch_unprocessed_orders()

    request = route.calls.last.request
    assert request.url.params["status"] == "READY_FOR_PROCESSING"
    assert request.url.params["fulfillment.status"] == "PROCESSING"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_search_orders_by_date_range_pages_results():
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(200, json={"shipments": [{"id": "shipment-1", "waybill": "WAYBILL-1"}]})
    )
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-2/shipments").mock(
        return_value=Response(200, json={"shipments": []})
    )
    first_page = respx.get("https://api.allegro.pl/order/checkout-forms").mock(
        side_effect=[
            Response(
                200,
                json={
                    "count": 1,
                    "totalCount": 2,
                    "checkoutForms": [
                        {
                            "id": "cf-1",
                            "status": "READY_FOR_PROCESSING",
                            "lineItems": [{"offer": {"id": "sku-1", "name": "Item 1"}, "boughtAt": "2026-01-02T00:00:00Z"}],
                        }
                    ],
                },
            ),
            Response(
                200,
                json={
                    "count": 1,
                    "totalCount": 2,
                    "checkoutForms": [
                        {
                            "id": "cf-2",
                            "status": "SENT",
                            "lineItems": [{"offer": {"id": "sku-2", "name": "Item 2"}, "boughtAt": "2026-01-03T00:00:00Z"}],
                        }
                    ],
                },
            ),
        ]
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"base_url": "https://api.allegro.pl"},
    )

    orders = await connector.fetch_orders_by_date_range(datetime(2026, 1, 1), datetime(2026, 12, 31), limit=1)

    assert [order.platform_order_id for order in orders] == ["cf-1", "cf-2"]
    assert orders[0].raw_payload["shipment_tracking_number"] == "WAYBILL-1"
    first_request = first_page.calls[0].request
    second_request = first_page.calls[1].request
    assert first_request.url.params["lineItems.boughtAt.gte"] == "2026-01-01T00:00:00Z"
    assert first_request.url.params["lineItems.boughtAt.lte"] == "2026-12-31T00:00:00Z"
    assert first_request.url.params["limit"] == "1"
    assert first_request.url.params["offset"] == "0"
    assert "status" not in first_request.url.params
    assert second_request.url.params["offset"] == "1"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_can_skip_platform_package_orders():
    shipment_route = respx.get("https://api.allegro.pl/order/checkout-forms/seller-package/shipments").mock(
        return_value=Response(200, json={"shipments": []})
    )
    respx.get("https://api.allegro.pl/order/checkout-forms").mock(
        return_value=Response(
            200,
            json={
                "checkoutForms": [
                    {
                        "id": "platform-package",
                        "fulfillment": {"status": "READY_FOR_PROCESSING", "provider": {"name": "Allegro Fulfillment"}},
                    },
                    {"id": "seller-package", "fulfillment": {"status": "READY_FOR_PROCESSING"}},
                ]
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {
            "dry_run_fulfillment": True,
            "base_url": "https://api.allegro.pl",
            "download_platform_package_orders": False,
        },
    )
    orders = await connector.fetch_unprocessed_orders()
    assert [order.platform_order_id for order in orders] == ["seller-package"]
    assert shipment_route.called


@pytest.mark.asyncio
@respx.mock
async def test_allegro_platform_package_orders_are_marked_overseas_when_downloaded():
    respx.get("https://api.allegro.pl/order/checkout-forms/platform-package/shipments").mock(
        return_value=Response(200, json={"shipments": []})
    )
    respx.get("https://api.allegro.pl/order/checkout-forms").mock(
        return_value=Response(
            200,
            json={
                "checkoutForms": [
                    {
                        "id": "platform-package",
                        "fulfillment": {"status": "READY_FOR_PROCESSING", "provider": {"name": "Allegro Fulfillment"}},
                    }
                ]
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {
            "dry_run_fulfillment": True,
            "base_url": "https://api.allegro.pl",
            "download_platform_package_orders": True,
        },
    )
    orders = await connector.fetch_unprocessed_orders()
    assert [order.platform_order_id for order in orders] == ["platform-package"]
    assert orders[0].fulfillment_type == "ALLEGRO_FULFILLMENT"
    assert orders[0].is_overseas_warehouse is True


@pytest.mark.asyncio
@respx.mock
async def test_allegro_status_updates_return_tracking_number():
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-1").mock(
        return_value=Response(
            200,
            json={
                "id": "cf-1",
                "fulfillment": {"status": "SENT"},
                "delivery": {"trackingNumber": "ALLEGRO-TRACK-1", "method": {"name": "Courier"}},
            },
        )
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"base_url": "https://api.allegro.pl"},
    )

    updates = await connector.fetch_order_status_updates(["cf-1"])

    assert updates[0].posting_number == "cf-1"
    assert updates[0].platform_status == "SENT"
    assert updates[0].shipment_tracking_number == "ALLEGRO-TRACK-1"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_status_updates_fetch_waybill_when_order_has_no_tracking_number():
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-1").mock(
        return_value=Response(
            200,
            json={
                "id": "cf-1",
                "fulfillment": {"status": "SENT"},
                "delivery": {"method": {"name": "Courier"}},
            },
        )
    )
    respx.get("https://api.allegro.pl/order/checkout-forms/cf-1/shipments").mock(
        return_value=Response(200, json={"shipments": [{"id": "shipment-1", "waybill": "WAYBILL-1", "carrierId": "DPD"}]})
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"base_url": "https://api.allegro.pl"},
    )

    updates = await connector.fetch_order_status_updates(["cf-1"])

    assert updates[0].shipment_tracking_number == "WAYBILL-1"
    assert updates[0].raw_payload["shipments"][0]["waybill"] == "WAYBILL-1"


@pytest.mark.asyncio
@respx.mock
async def test_allegro_status_updates_normalize_compact_uuid_lookup():
    compact_id = "6142a780ffbf11f0b753159bf9d0ca3f"
    checkout_form_id = "6142a780-ffbf-11f0-b753-159bf9d0ca3f"
    detail_route = respx.get(f"https://api.allegro.pl/order/checkout-forms/{checkout_form_id}").mock(
        return_value=Response(
            200,
            json={
                "id": checkout_form_id,
                "fulfillment": {"status": "SENT"},
                "delivery": {"method": {"name": "Courier"}},
            },
        )
    )
    shipment_route = respx.get(f"https://api.allegro.pl/order/checkout-forms/{checkout_form_id}/shipments").mock(
        return_value=Response(200, json={"shipments": [{"id": "shipment-1", "waybill": "WAYBILL-1"}]})
    )
    connector = AllegroConnector(
        {"access_token": "token"},
        {"base_url": "https://api.allegro.pl"},
    )

    updates = await connector.fetch_order_status_updates([compact_id])

    assert detail_route.called
    assert shipment_route.called
    assert updates[0].posting_number == compact_id
    assert updates[0].platform_order_id == checkout_form_id
    assert updates[0].shipment_tracking_number == "WAYBILL-1"


@pytest.mark.asyncio
@respx.mock
async def test_mercado_fetch_orders_and_preview_label():
    respx.get("https://api.mercadolibre.com/orders/search").mock(
        return_value=Response(
            200,
            json={"results": [{"id": 1001, "status": "paid", "shipping": {"id": 9001, "status": "ready_to_ship"}}], "paging": {"total": 1, "limit": 50, "offset": 0}},
        )
    )
    respx.get("https://api.mercadolibre.com/orders/1001").mock(
        return_value=Response(
            200,
            json={
                "id": 1001,
                "status": "paid",
                "currency_id": "USD",
                "total_amount": 12.5,
                "buyer": {"id": 1, "nickname": "buyer"},
                "shipping": {"id": 9001, "status": "ready_to_ship"},
                "order_items": [{"item": {"id": "sku-1", "title": "Item"}, "quantity": 1, "unit_price": 12.5}],
            },
        )
    )
    respx.get("https://api.mercadolibre.com/shipments/9001").mock(
        return_value=Response(200, json={"id": 9001, "status": "ready_to_ship", "tracking_number": "TRK-1"})
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "seller-1"},
        {"dry_run_fulfillment": True, "base_url": "https://api.mercadolibre.com"},
    )
    orders = await connector.fetch_unprocessed_orders()
    assert orders[0].platform_order_id == "1001"
    shipment = await connector.create_platform_shipment(orders[0])
    assert shipment.platform_shipment_id == "9001"
    label = await connector.fetch_label(shipment, orders[0])
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_mercado_status_updates_return_shipment_tracking():
    respx.get("https://api.mercadolibre.com/shipments/9001").mock(
        return_value=Response(200, json={"id": 9001, "status": "ready_to_ship", "tracking_number": "TRK-9001", "order_id": 1001})
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "seller-1"},
        {"base_url": "https://api.mercadolibre.com"},
    )

    updates = await connector.fetch_order_status_updates(["9001"])

    assert updates[0].posting_number == "9001"
    assert updates[0].platform_order_id == "1001"
    assert updates[0].platform_status == "ready_to_ship"
    assert updates[0].shipment_tracking_number == "TRK-9001"


@pytest.mark.asyncio
@respx.mock
async def test_mercado_settings_control_status_and_full_orders():
    route = respx.get("https://api.mercadolibre.com/orders/search").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {"id": 1001, "status": "paid", "shipping": {"id": 9001, "status": "ready_to_ship", "logistic_type": "fulfillment"}},
                    {"id": 1002, "status": "paid", "shipping": {"id": 9002, "status": "ready_to_ship", "logistic_type": "cross_docking"}},
                ],
                "paging": {"total": 2, "limit": 50, "offset": 0},
            },
        )
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "seller-1"},
        {
            "dry_run_fulfillment": True,
            "base_url": "https://api.mercadolibre.com",
            "download_full_orders": False,
            "mercado_order_pull_status": "after_shipped",
            "fetch_order_details": False,
            "fetch_shipment_details": False,
        },
    )
    orders = await connector.fetch_unprocessed_orders()
    assert route.calls.last.request.url.params["order.status"] == "confirmed"
    assert [order.platform_order_id for order in orders] == ["1002"]


@pytest.mark.asyncio
@respx.mock
async def test_mercado_full_orders_are_marked_overseas_when_downloaded():
    respx.get("https://api.mercadolibre.com/orders/search").mock(
        return_value=Response(
            200,
            json={
                "results": [
                    {"id": 1001, "status": "paid", "shipping": {"id": 9001, "status": "ready_to_ship", "logistic_type": "fulfillment"}},
                ],
                "paging": {"total": 1, "limit": 50, "offset": 0},
            },
        )
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "seller-1"},
        {
            "dry_run_fulfillment": True,
            "base_url": "https://api.mercadolibre.com",
            "download_full_orders": True,
            "fetch_order_details": False,
            "fetch_shipment_details": False,
        },
    )
    orders = await connector.fetch_unprocessed_orders()
    assert [order.platform_order_id for order in orders] == ["1001"]
    assert orders[0].fulfillment_type == "FULFILLMENT"
    assert orders[0].is_overseas_warehouse is True


@pytest.mark.asyncio
@respx.mock
async def test_mercado_cbt_uses_marketplace_endpoints_and_label():
    search_route = respx.get("https://api.mercadolibre.com/marketplace/orders/search").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": 2001, "status": "paid", "shipping": {"id": 9901, "status": "ready_to_ship"}}],
                "paging": {"total": 1, "limit": 50, "offset": 0},
            },
        )
    )
    respx.get("https://api.mercadolibre.com/marketplace/orders/pack/2001").mock(
        return_value=Response(
            200,
            json={"id": 2001, "buyer": {"id": 2, "nickname": "cbt-buyer"}, "shipment": {"id": 9901}, "orders": [{"id": 3001}]},
        )
    )
    respx.get("https://api.mercadolibre.com/marketplace/orders/3001").mock(
        return_value=Response(
            200,
            json={
                "id": 3001,
                "pack_id": 2001,
                "status": "paid",
                "currency_id": "USD",
                "total_amount": 19.99,
                "buyer": {"id": 2, "nickname": "cbt-buyer"},
                "shipping": {"id": 9901, "status": "ready_to_ship"},
                "order_items": [{"item": {"id": "sku-cbt", "title": "CBT Item"}, "quantity": 1, "unit_price": 19.99}],
            },
        )
    )
    respx.get("https://api.mercadolibre.com/marketplace/shipments/9901").mock(
        return_value=Response(200, json={"id": 9901, "status": "ready_to_ship", "tracking_number": "CBT-TRK-1"})
    )
    label_route = respx.get("https://api.mercadolibre.com/marketplace/shipments/9901/labels").mock(
        return_value=Response(200, content=b"%PDF-cbt-label", headers={"content-type": "application/pdf"})
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "seller-1"},
        {
            "dry_run_fulfillment": False,
            "base_url": "https://api.mercadolibre.com",
            "mercado_store_type": "semi_managed",
            "mercado_site": "CBT",
        },
    )
    orders = await connector.fetch_unprocessed_orders()
    assert search_route.calls.last.request.url.params["seller_id"] == "seller-1"
    assert search_route.calls.last.request.url.params["status"] == "paid"
    assert orders[0].raw_payload["mercado_api_mode"] == "cbt"
    shipment = await connector.create_platform_shipment(orders[0])
    label = await connector.fetch_label(shipment, orders[0])
    assert label_route.called
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_mercado_cbt_package_detail_maps_nested_order_fields():
    respx.get("https://api.mercadolibre.com/marketplace/orders/search").mock(
        return_value=Response(
            200,
            json={
                "results": [{"id": "DEMO-ORDER-0003", "shipping": {"id": None}, "shipment": {"id": "DEMO-TRACKING-0003"}}],
                "paging": {"total": 1, "limit": 50, "offset": 0},
            },
        )
    )
    respx.get("https://api.mercadolibre.com/marketplace/orders/pack/DEMO-ORDER-0003").mock(
        return_value=Response(
            200,
            json={
                "id": "DEMO-ORDER-0003",
                "site": "CBT",
                "buyer": {"id": 473186644},
                "shipment": {"id": "DEMO-TRACKING-0003", "status": "ready_to_ship"},
                "orders": [{"id": 2000000000000002}],
            },
        )
    )
    respx.get("https://api.mercadolibre.com/marketplace/orders/2000000000000002").mock(
        return_value=Response(
            200,
            json={
                "id": 2000000000000002,
                "status": "paid",
                "currency_id": "USD",
                "total_amount": 15.5,
                "order_items": [
                    {
                        "item": {"id": "MLA0000000001", "title": "Nested CBT Item", "seller_custom_field": "SKU-CBT-1"},
                        "quantity": 2,
                        "unit_price": 7.75,
                    }
                ],
            },
        )
    )
    respx.get("https://api.mercadolibre.com/marketplace/shipments/DEMO-TRACKING-0003").mock(
        return_value=Response(200, json={"id": "DEMO-TRACKING-0003", "status": "ready_to_ship", "tracking_number": "DEMO-TRACKING-0037"})
    )
    connector = MercadoGlobalConnector(
        {"access_token": "token", "seller_id": "seller-1"},
        {
            "base_url": "https://api.mercadolibre.com",
            "mercado_store_type": "cbt",
            "mercado_site": "CBT",
        },
    )

    orders = await connector.fetch_unprocessed_orders()

    assert len(orders) == 1
    order = orders[0]
    assert order.platform_order_id == "DEMO-ORDER-0003"
    assert order.posting_number == "DEMO-TRACKING-0003"
    assert order.platform_status == "ready_to_ship"
    assert order.raw_payload["order_amount"] == 15.5
    assert order.raw_payload["currency_code"] == "USD"
    assert order.raw_payload["products"][0]["sku"] == "SKU-CBT-1"
    assert order.raw_payload["products"][0]["name"] == "Nested CBT Item"
    assert order.raw_payload["products"][0]["quantity"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_joom_fetch_orders_and_preview_label():
    respx.get("https://api-merchant.joom.com/api/v3/orders/unfulfilled").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "items": [
                        {
                            "id": "joom-1",
                            "status": "approved",
                            "customerId": "customer-1",
                            "marketplace": "JOOM",
                            "currency": "USD",
                            "quantity": 2,
                            "orderTimestamp": "2026-05-21T03:50:00Z",
                            "approvedTimestamp": "2026-05-21T05:50:15Z",
                            "updateTimestamp": "2026-05-21T05:50:18Z",
                            "daysToFulfill": 1,
                            "hoursToFulfill": 2,
                            "shippingAddress": {"country": "RU"},
                            "shippingOption": {"tierName": "Standard Shipping"},
                            "trackingNumber": "DEMO-TRACKING-0004",
                            "priceInfo": {"orderPrice": "76", "unitPrice": "38"},
                            "product": {
                                "id": "product-1",
                                "sku": "DEMO-SKU-0046",
                                "name": "Joom Product",
                                "variant": {"id": "variant-1", "sku": "DEMO-SKU-0028"},
                            },
                        }
                    ]
                }
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {"dry_run_fulfillment": True, "base_url": "https://api-merchant.joom.com/api/v3"},
    )
    orders = await connector.fetch_unprocessed_orders()
    order = orders[0]
    assert order.platform_order_id == "joom-1"
    assert order.platform_order_no == "joom-1"
    assert order.raw_payload["customer_id"] == "customer-1"
    assert order.raw_payload["country_code"] == "RU"
    assert order.raw_payload["order_amount"] == "76"
    assert order.raw_payload["currency_code"] == "USD"
    assert order.raw_payload["payment_at"] == "2026-05-21T05:50:15Z"
    assert order.raw_payload["shipping_deadline_at"] == "2026-05-22T07:50:15Z"
    assert order.raw_payload["platform_handover_deadline"] == "2026-05-22T07:50:15Z"
    assert order.raw_payload["shipment_tracking_number"] == "DEMO-TRACKING-0004"
    assert order.raw_payload["tracking_number"] == "DEMO-TRACKING-0004"
    assert order.raw_payload["buyer_selected_logistics"] == "Standard Shipping"
    assert order.raw_payload["products"][0]["sku"] == "DEMO-SKU-0028"
    assert order.raw_payload["products"][0]["name"] == "Joom Product"
    assert order.raw_payload["products"][0]["quantity"] == 2
    assert order.raw_payload["products"][0]["price"] == "38"
    shipment = await connector.create_platform_shipment(orders[0])
    label = await connector.fetch_label(shipment, orders[0])
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_joom_online_shipping_uses_fulfill_online_endpoint_and_label_query():
    fulfill = respx.post("https://api-merchant.joom.com/api/v3/orders/fulfillOnline").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "shipperName": "Joom Logistics",
                    "shippingOrderNumber": "SHIP-1",
                    "trackingNumber": "TRACK-1",
                }
            },
        )
    )
    label_route = respx.get("https://api-merchant.joom.com/api/v3/orders/shippingLabel", params={"id": "26VE349M"}).mock(
        return_value=Response(200, content=b"%PDF real label")
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api-merchant.joom.com/api/v3",
            "dry_run_fulfillment": False,
            "joom_shipping_provider": "Joom Logistics",
            "joom_pickup": False,
        },
    )
    order = NormalizedOrder("26VE349M", "approved", {"id": "26VE349M"}, platform_order_no="DEMO-ORDER-0030")

    shipment = await connector.create_platform_shipment(order)
    label = await connector.fetch_label(shipment, order)

    assert fulfill.called
    assert fulfill.calls[0].request.url.path == "/api/v3/orders/fulfillOnline"
    assert json.loads(fulfill.calls[0].request.content) == {
        "ids": ["26VE349M"],
        "provider": "Joom Logistics",
        "pickup": False,
    }
    assert shipment.platform_shipment_id == "SHIP-1"
    assert shipment.tracking_number == "TRACK-1"
    assert shipment.carrier == "Joom Logistics"
    assert shipment.status == "fulfilledOnline"
    assert label_route.called
    assert label.content == b"%PDF real label"


@pytest.mark.asyncio
@respx.mock
async def test_joom_status_updates_return_tracking_number():
    respx.get("https://api-merchant.joom.com/api/v3/orders", params={"id": "joom-1"}).mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "id": "joom-1",
                    "status": "fulfilledOnline",
                    "shipment": {
                        "trackingNumber": "JOOM-TRACK-1",
                        "fulfilledTimestamp": "2026-05-28T05:00:00Z",
                    },
                }
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {"base_url": "https://api-merchant.joom.com/api/v3"},
    )

    updates = await connector.fetch_order_status_updates(["joom-1"])

    assert updates[0].posting_number == "joom-1"
    assert updates[0].platform_status == "fulfilledOnline"
    assert updates[0].shipment_tracking_number == "JOOM-TRACK-1"
    assert updates[0].handover_at == "2026-05-28T05:00:00Z"


@pytest.mark.asyncio
@respx.mock
async def test_joom_daily_sync_keeps_unfulfilled_endpoint_even_when_full_download_enabled():
    route = respx.get("https://api-merchant.joom.com/api/v3/orders/unfulfilled").mock(
        return_value=Response(200, json={"data": {"items": []}})
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api-merchant.joom.com/api/v3",
            "download_full_orders": True,
            "joom_full_sync_updated_from": "2026-04-01T00:00:00Z",
        },
    )

    await connector.fetch_unprocessed_orders(datetime(2026, 5, 1, 2, 3, 4))

    assert route.called
    assert route.calls[0].request.url.params["status"] == "approved"
    assert "updatedFrom" not in route.calls[0].request.url.params


@pytest.mark.asyncio
@respx.mock
async def test_joom_downloads_full_orders_with_paging():
    first = respx.get(
        "https://api-merchant.joom.com/api/v3/orders/multi",
        params={"updatedFrom": "2026-04-01T00:00:00Z", "limit": "500"},
    ).mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "items": [
                        {"id": "joom-shipped", "status": "shipped", "orderTimestamp": "2026-04-02T00:00:00Z"},
                    ]
                },
                "paging": {
                    "next": "https://api-merchant.joom.com/api/v3/orders/multi?after=page-2&limit=500"
                },
            },
        )
    )
    second = respx.get("https://api-merchant.joom.com/api/v3/orders/multi", params={"after": "page-2", "limit": "500"}).mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "items": [
                        {"id": "joom-refunded", "status": "refunded", "orderTimestamp": "2026-04-03T00:00:00Z"},
                    ]
                }
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api-merchant.joom.com/api/v3",
            "full_refresh": True,
            "joom_full_sync_updated_from": "2026-04-01T00:00:00Z",
        },
    )

    orders = await connector.fetch_unprocessed_orders()

    assert [order.platform_order_id for order in orders] == ["joom-shipped", "joom-refunded"]
    assert [order.platform_status for order in orders] == ["shipped", "refunded"]
    assert first.calls[0].request.url.params["updatedFrom"] == "2026-04-01T00:00:00Z"
    assert first.calls[0].request.url.params["limit"] == "500"
    assert second.called


@pytest.mark.asyncio
@respx.mock
async def test_joom_full_orders_incremental_uses_since():
    route = respx.get("https://api-merchant.joom.com/api/v3/orders/multi").mock(
        return_value=Response(200, json={"data": {"items": []}})
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api-merchant.joom.com/api/v3",
            "full_refresh": True,
            "joom_full_sync_updated_from": "2026-04-01T00:00:00Z",
        },
    )

    await connector.fetch_unprocessed_orders(datetime(2026, 5, 1, 2, 3, 4))

    assert route.calls[0].request.url.params["updatedFrom"] == "2026-05-01T02:03:04Z"


@pytest.mark.asyncio
@respx.mock
async def test_joom_full_orders_can_filter_by_order_created_time():
    respx.get("https://api-merchant.joom.com/api/v3/orders/multi").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "items": [
                        {"id": "joom-old", "status": "shipped", "orderTimestamp": "2026-03-31T23:59:59Z"},
                        {"id": "joom-new", "status": "shipped", "orderTimestamp": "2026-04-01T00:00:00Z"},
                    ]
                }
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api-merchant.joom.com/api/v3",
            "full_refresh": True,
            "joom_full_sync_updated_from": "2026-04-01T00:00:00Z",
            "joom_full_sync_created_from": "2026-04-01T00:00:00Z",
        },
    )

    orders = await connector.fetch_unprocessed_orders()

    assert [order.platform_order_id for order in orders] == ["joom-new"]


@pytest.mark.asyncio
@respx.mock
async def test_joom_skips_overseas_warehouse_orders_by_default():
    respx.get("https://api-merchant.joom.com/api/v3/orders/unfulfilled").mock(
        return_value=Response(
            200,
            json={
                "data": {"items": [
                    {"id": "joom-fbj", "status": "approved", "fulfillmentType": "FBJ"},
                    {
                        "id": "joom-nested-warehouse",
                        "status": "shipped",
                        "shippingOption": {
                            "warehouseName": "Joom Logistics CN Warehouse",
                            "warehouseType": "fulfillment",
                        },
                    },
                    {"id": "joom-seller", "status": "approved", "fulfillmentType": "seller"},
                    {
                        "id": "joom-default-fulfilled-online",
                        "status": "fulfilledOnline",
                        "shippingOption": {
                            "warehouseName": "Default warehouse",
                            "warehouseType": "default",
                        },
                    },
                    {
                        "id": "joom-physical-overseas",
                        "status": "approved",
                        "shippingOption": {
                            "warehouseName": "BSI-PL",
                            "warehouseType": "physical",
                        },
                    },
                ]}
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {"dry_run_fulfillment": True, "base_url": "https://api-merchant.joom.com/api/v3"},
    )
    orders = await connector.fetch_unprocessed_orders()
    assert [order.platform_order_id for order in orders] == ["joom-seller", "joom-default-fulfilled-online"]


@pytest.mark.asyncio
@respx.mock
async def test_joom_can_download_overseas_warehouse_orders():
    respx.get("https://api-merchant.joom.com/api/v3/orders/unfulfilled").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "items": [
                        {"id": "joom-fbj", "status": "approved", "fulfillmentType": "FBJ"},
                        {
                            "id": "joom-nested-warehouse",
                            "status": "shipped",
                            "shippingOption": {
                                "warehouseName": "Joom Logistics CN Warehouse",
                                "warehouseType": "fulfillment",
                            },
                        },
                        {
                            "id": "joom-physical-overseas",
                            "status": "approved",
                            "shippingOption": {
                                "warehouseName": "BSI-PL",
                                "warehouseType": "physical",
                            },
                        },
                    ]
                }
            },
        )
    )
    connector = JoomLogisticsConnector(
        {"api_key": "token"},
        {
            "dry_run_fulfillment": True,
            "base_url": "https://api-merchant.joom.com/api/v3",
            "download_overseas_warehouse_orders": True,
        },
    )
    orders = await connector.fetch_unprocessed_orders()
    assert [order.platform_order_id for order in orders] == ["joom-fbj", "joom-nested-warehouse", "joom-physical-overseas"]
    assert [order.is_overseas_warehouse for order in orders] == [True, True, True]
    assert [order.fulfillment_type for order in orders] == ["FBJ", "FBJ", "PHYSICAL"]


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_fetch_orders_and_preview_label():
    respx.get("https://marketplace-api.wildberries.ru/api/v3/orders").mock(
        return_value=Response(
            200,
            json={
                "orders": [
                    {
                        "id": 12345,
                        "rid": "rid-1",
                        "orderUid": "uid-1",
                        "article": "ART-1",
                        "skus": ["BAR-1"],
                        "createdAt": "2026-05-16T01:02:03Z",
                        "convertedFinalPrice": 1234,
                        "convertedCurrencyCode": 643,
                        "currencyCode": 643,
                        "deliveryType": "fbs",
                        "supplyId": "WB-GI-1",
                    },
                    {
                        "id": 54321,
                        "rid": "rid-cn",
                        "orderUid": "uid-cn",
                        "article": "ART-CN",
                        "skus": ["BAR-CN"],
                        "createdAt": "2026-05-16T01:02:04Z",
                        "convertedPrice": 71434,
                        "convertedCurrencyCode": 156,
                        "currencyCode": 643,
                        "country_code": "RU",
                        "crossBorderType": 1,
                        "deliveryType": "fbs",
                        "offices": ["\u041f\u0435\u043a\u0438\u043d"],
                        "officeId": 23071,
                    },
                    {"id": 99999, "article": "META-1", "deliveryType": "fbs", "requiredMeta": {"uin": True}},
                    {"id": 88888, "article": "DBS-1", "deliveryType": "dbs"},
                ]
            },
        )
    )
    respx.get("https://marketplace-api.wildberries.ru/api/v3/orders/new").mock(
        return_value=Response(200, json={"orders": []})
    )
    respx.get("https://marketplace-api.wildberries.ru/api/v3/supplies/WB-GI-1").mock(
        return_value=Response(200, json={"id": "WB-GI-1", "scanDt": "2026-05-16T06:07:08Z"})
    )
    respx.post("https://marketplace-api.wildberries.ru/api/v3/orders/status").mock(
        return_value=Response(200, json={"orders": [{"id": 12345, "supplierStatus": "confirm"}]})
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"dry_run_fulfillment": True, "base_url": "https://marketplace-api.wildberries.ru"},
    )
    orders = await connector.fetch_unprocessed_orders()
    assert [order.platform_order_id for order in orders] == ["12345", "54321", "88888"]
    seller_order = orders[0]
    china_cross_border_order = orders[1]
    overseas_order = orders[2]
    assert seller_order.platform_order_no == "12345"
    assert seller_order.posting_number == "12345"
    assert seller_order.platform_status == "confirm"
    assert seller_order.fulfillment_type == "FBS"
    assert seller_order.is_overseas_warehouse is False
    assert seller_order.raw_payload["products"][0]["offer_id"] == "ART-1"
    assert seller_order.raw_payload["order_amount"] == "12.34"
    assert seller_order.raw_payload["products"][0]["price"] == "12.34"
    assert seller_order.raw_payload["created_at"] == "2026-05-16T01:02:03Z"
    assert overseas_order.fulfillment_type == "DBS"
    assert overseas_order.is_overseas_warehouse is True
    assert overseas_order.raw_payload["is_overseas_warehouse"] is True
    assert orders[0].raw_payload["supply_id"] == "WB-GI-1"
    assert "tracking_number" not in orders[0].raw_payload
    assert "buyer_id" not in orders[0].raw_payload
    assert "customer_id" not in orders[0].raw_payload
    assert orders[0].raw_payload["country_code"] == "RU"
    assert china_cross_border_order.raw_payload["country_code"] == "CN"
    assert china_cross_border_order.raw_payload["currency_code"] == "CNY"
    assert orders[0].raw_payload["shipment_date"] == "2026-05-16T06:07:08Z"
    shipment = await connector.create_platform_shipment(orders[0])
    label = await connector.fetch_label(shipment, orders[0])
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_fetch_platform_products_retries_price_rate_limit(monkeypatch):
    content_route = respx.post("https://content-api.wildberries.ru/content/v2/get/cards/list").mock(
        return_value=Response(
            200,
            json={
                "cards": [
                    {
                        "nmID": 123,
                        "vendorCode": "SKU-1",
                        "title": "Test Product",
                    }
                ],
                "cursor": {"nmID": 0},
            },
        )
    )
    price_route = respx.get("https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter").mock(
        side_effect=[
            Response(429, headers={"Retry-After": "3"}, json={"message": "too many requests"}),
            Response(
                200,
                json={
                    "data": {
                        "listGoods": [
                            {
                                "nmID": 123,
                                "sizes": [{"discountedPrice": 12300, "price": 15000}],
                                "currencyIsoCode4217": "RUB",
                            }
                        ]
                    }
                },
            ),
            Response(200, json={"data": {"listGoods": []}}),
        ]
    )
    stock_route = respx.get("https://statistics-api.wildberries.ru/api/v1/supplier/stocks").mock(
        return_value=Response(
            200,
            json=[
                {
                    "supplierArticle": "SKU-1",
                    "warehouseName": "Main",
                    "quantity": 5,
                    "inWayToClient": 1,
                }
            ],
        )
    )
    sleep_delays = []

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr("app.adapters.wildberries.asyncio.sleep", fake_sleep)
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"base_url": "https://marketplace-api.wildberries.ru"},
    )

    rows = await connector.fetch_platform_products()

    assert content_route.called
    assert price_route.call_count == 3
    assert stock_route.called
    assert sleep_delays == [3.0, 0.65]
    assert rows[0]["platform_product_id"] == "123"
    assert rows[0]["platform_sku"] == "SKU-1"
    assert rows[0]["price_amount"] == 12300
    assert rows[0]["available_stock"] == 5
    assert rows[0]["reserved_stock"] == 1


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_fetch_platform_products_keeps_partial_data_when_price_api_stays_rate_limited(monkeypatch):
    respx.post("https://content-api.wildberries.ru/content/v2/get/cards/list").mock(
        return_value=Response(
            200,
            json={
                "cards": [
                    {
                        "nmID": 123,
                        "vendorCode": "SKU-1",
                        "title": "Test Product",
                    }
                ],
                "cursor": {"nmID": 0},
            },
        )
    )
    price_route = respx.get("https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter").mock(
        side_effect=[Response(429, json={"message": "too many requests"}) for _ in range(5)]
    )
    respx.get("https://statistics-api.wildberries.ru/api/v1/supplier/stocks").mock(
        return_value=Response(
            200,
            json=[
                {
                    "supplierArticle": "SKU-1",
                    "warehouseName": "Main",
                    "quantity": 5,
                }
            ],
        )
    )
    sleep_delays = []

    async def fake_sleep(delay):
        sleep_delays.append(delay)

    monkeypatch.setattr("app.adapters.wildberries.asyncio.sleep", fake_sleep)
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"base_url": "https://marketplace-api.wildberries.ru"},
    )

    rows = await connector.fetch_platform_products()

    assert price_route.call_count == 5
    assert sleep_delays[:4] == [1, 2, 4, 8]
    assert rows[0]["platform_product_id"] == "123"
    assert rows[0]["platform_sku"] == "SKU-1"
    assert rows[0]["price_amount"] is None
    assert rows[0]["available_stock"] == 5


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_fetch_platform_products_keeps_rows_when_stock_api_fails():
    respx.post("https://content-api.wildberries.ru/content/v2/get/cards/list").mock(
        return_value=Response(
            200,
            json={
                "cards": [
                    {
                        "nmID": 123,
                        "vendorCode": "SKU-1",
                        "title": "Test Product",
                    }
                ],
                "cursor": {"nmID": 0},
            },
        )
    )
    respx.get("https://discounts-prices-api.wildberries.ru/api/v2/list/goods/filter").mock(
        return_value=Response(200, json={"data": {"listGoods": []}})
    )
    stock_route = respx.get("https://statistics-api.wildberries.ru/api/v1/supplier/stocks").mock(
        return_value=Response(404, json={"message": "not found"})
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"base_url": "https://marketplace-api.wildberries.ru"},
    )

    rows = await connector.fetch_platform_products()

    assert stock_route.called
    assert rows[0]["platform_product_id"] == "123"
    assert rows[0]["available_stock"] == 0
    assert rows[0]["raw_payload"]["stock_fetch_error"] == "Wildberries stock API returned HTTP 404"


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_real_supply_label_and_status():
    add_route = respx.patch("https://marketplace-api.wildberries.ru/api/marketplace/v3/supplies/supply-1/orders").mock(
        return_value=Response(204)
    )
    sticker_png = (
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
    )
    sticker_route = respx.post("https://marketplace-api.wildberries.ru/api/v3/orders/stickers").mock(
        return_value=Response(
            200,
            json={
                "stickers": [
                    {
                        "id": 12345,
                        "barcode": "*DMcSAMpW",
                        "partA": "5487945",
                        "partB": "3386",
                        "file": sticker_png,
                    }
                ]
            },
        )
    )
    status_route = respx.post("https://marketplace-api.wildberries.ru/api/v3/orders/status").mock(
        return_value=Response(200, json={"orders": [{"id": 12345, "supplierStatus": "confirm", "supplyId": "supply-1"}]})
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {
            "dry_run_fulfillment": False,
            "base_url": "https://marketplace-api.wildberries.ru",
            "supply_id": "supply-1",
        },
    )
    order = NormalizedOrder("12345", "new", {"article": "ART-1"}, platform_order_no="uid-1", posting_number="12345")
    shipment = await connector.create_platform_shipment(order)
    assert add_route.called
    assert add_route.calls.last.request.read().decode() == '{"orders":[12345]}'
    assert shipment.tracking_number == ""
    assert shipment.raw_payload["supply_id"] == "supply-1"

    label = await connector.fetch_label(shipment, order)
    assert sticker_route.called
    assert sticker_route.calls.last.request.url.params["type"] == "png"
    assert sticker_route.calls.last.request.url.params["width"] == "58"
    assert sticker_route.calls.last.request.url.params["height"] == "40"
    assert label.content.startswith(b"%PDF")
    assert "shipment_tracking_number" not in label.raw_payload
    assert label.raw_payload["wildberries_sticker_barcode"] == "*DMcSAMpW"
    assert label.raw_payload["stickers"][0]["barcode"] == "*DMcSAMpW"

    updates = await connector.fetch_order_status_updates(["12345"])
    assert status_route.called
    assert updates[0].posting_number == "12345"
    assert updates[0].platform_status == "confirm"
    assert updates[0].shipment_tracking_number == ""
    assert updates[0].raw_payload["supply_id"] == "supply-1"


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_cross_border_label_uses_pdf_endpoint():
    label_pdf = base64.b64encode(b"%PDF-1.4\ncross-border label\n%%EOF").decode("ascii")
    cross_border_route = respx.post("https://marketplace-api.wildberries.ru/api/v3/orders/stickers/cross-border").mock(
        return_value=Response(
            200,
            json={
                "stickers": [
                    {
                        "id": 900000002,
                        "status": "ready",
                        "file": label_pdf,
                        "barcode": "*DMcSAMpW",
                        "trackingNumber": "WBCNRUCLBCF0600WLE",
                    }
                ]
            },
        )
    )
    regular_sticker_route = respx.post("https://marketplace-api.wildberries.ru/api/v3/orders/stickers").mock(
        return_value=Response(500, json={"error": "regular sticker endpoint should not be used"})
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {
            "dry_run_fulfillment": False,
            "base_url": "https://marketplace-api.wildberries.ru",
        },
    )
    order = NormalizedOrder(
        "900000002",
        "complete",
        {"article": "ART-1", "country_code": "CN", "site": "wildberries"},
        platform_order_no="900000002",
        posting_number="900000002",
    )

    label = await connector.fetch_label(ShipmentResult("900000002", "WBCNRUCLBCF0600WLE"), order)

    assert cross_border_route.called
    assert cross_border_route.calls.last.request.read().decode() == '{"orders":[900000002]}'
    assert not regular_sticker_route.called
    assert label.content == b"%PDF-1.4\ncross-border label\n%%EOF"
    assert label.raw_payload["cross_border"] is True
    assert label.raw_payload["shipment_tracking_number"] == "WBCNRUCLBCF0600WLE"


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_cross_border_label_uses_parcel_id_as_tracking():
    label_pdf = base64.b64encode(b"%PDF-1.4\ncross-border label\n%%EOF").decode("ascii")
    cross_border_route = respx.post("https://marketplace-api.wildberries.ru/api/v3/orders/stickers/cross-border").mock(
        return_value=Response(
            200,
            json={
                "stickers": [
                    {
                        "id": 900000003,
                        "status": "ready",
                        "file": label_pdf,
                        "barcode": "*DObv4SBB",
                        "parcelId": "WBCRNUCLBCF2100P3W",
                    }
                ]
            },
        )
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {
            "dry_run_fulfillment": False,
            "base_url": "https://marketplace-api.wildberries.ru",
        },
    )
    order = NormalizedOrder(
        "900000003",
        "complete",
        {"article": "ART-1", "country_code": "CN", "site": "wildberries", "crossBorderType": 1},
        platform_order_no="900000003",
        posting_number="900000003",
    )

    label = await connector.fetch_label(ShipmentResult("900000003", ""), order)

    assert cross_border_route.called
    assert label.raw_payload["shipment_tracking_number"] == "WBCRNUCLBCF2100P3W"
    assert label.raw_payload["waybillNumber"] == "WBCRNUCLBCF2100P3W"
    assert label.raw_payload["stickers"][0]["parcelId"] == "WBCRNUCLBCF2100P3W"


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_real_uses_configured_supply_id():
    add_route = respx.patch("https://marketplace-api.wildberries.ru/api/marketplace/v3/supplies/WB-GI-1/orders").mock(
        return_value=Response(204)
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://marketplace-api.wildberries.ru", "supply_id": "WB-GI-1"},
    )
    order = NormalizedOrder(
        "12345",
        "new",
        {"article": "ART-1"},
        platform_order_no="uid-1",
        posting_number="12345",
    )

    shipment = await connector.create_platform_shipment(order)

    assert add_route.called
    assert shipment.tracking_number == ""
    assert shipment.raw_payload["supply_id"] == "WB-GI-1"


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_real_skips_submit_when_order_already_has_supply():
    add_route = respx.patch("https://marketplace-api.wildberries.ru/api/marketplace/v3/supplies/WB-GI-1/orders").mock(
        return_value=Response(409, json={"error": "order already in supply"})
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://marketplace-api.wildberries.ru"},
    )
    order = NormalizedOrder(
        "900000003",
        "complete",
        {"article": "ART-1", "supplyId": "WB-GI-1", "supply": {"id": "WB-GI-1", "done": True}},
        platform_order_no="900000003",
        posting_number="900000003",
    )

    shipment = await connector.create_platform_shipment(order)

    assert not add_route.called
    assert shipment.platform_shipment_id == "900000003"
    assert shipment.raw_payload["supply_id"] == "WB-GI-1"
    assert shipment.raw_payload["response"]["skipped_submit"] is True


@pytest.mark.asyncio
@respx.mock
async def test_wildberries_real_creates_supply_when_missing():
    create_route = respx.post("https://marketplace-api.wildberries.ru/api/v3/supplies").mock(
        return_value=Response(200, json={"id": "auto-supply-1"})
    )
    add_route = respx.patch("https://marketplace-api.wildberries.ru/api/marketplace/v3/supplies/auto-supply-1/orders").mock(
        return_value=Response(204)
    )
    connector = WildberriesConnector(
        {"api_key": "token"},
        {"dry_run_fulfillment": False, "base_url": "https://marketplace-api.wildberries.ru"},
    )
    order = NormalizedOrder("12345", "new", {"article": "ART-1"}, platform_order_no="uid-1", posting_number="12345")

    shipment = await connector.create_platform_shipment(order)

    assert create_route.called
    assert add_route.called
    assert shipment.tracking_number == ""
    assert shipment.raw_payload["supply_id"] == "auto-supply-1"
