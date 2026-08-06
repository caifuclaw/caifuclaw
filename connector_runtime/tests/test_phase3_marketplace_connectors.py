# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import json

import pytest
import respx
from httpx import Response

from app.adapters.base import ShipmentResult
from app.adapters.coupang import CoupangConnector
from app.adapters.shein import SheinConnector
from app.adapters.wayfair import WayfairConnector
from app.factory import canonical_platform, connector_for


def test_phase3_platforms_registered_in_factory():
    assert canonical_platform("shein_open") == "shein"
    assert canonical_platform("coupang_openapi") == "coupang"
    assert canonical_platform("wayfair_partner") == "wayfair"
    assert connector_for("shein", {"open_key_id": "key", "secret_key": "secret"}, {}).platform == "shein"
    assert connector_for("coupang", {"access_key": "ak", "secret_key": "sk", "vendor_id": "vendor"}, {}).platform == "coupang"
    assert connector_for("wayfair", {"access_token": "token", "supplier_id": "supplier"}, {}).platform == "wayfair"


@pytest.mark.asyncio
@respx.mock
async def test_shein_fetch_orders_and_signed_headers():
    route = respx.post("https://openapi.sheincorp.com/open-api/order/order-list").mock(
        return_value=Response(
            200,
            json={
                "code": "0",
                "info": {
                    "data": [
                        {
                            "orderNo": "SH-1",
                            "orderStatus": "WAITING_SHIPMENT",
                            "packageNo": "SH-PKG-1",
                            "currency": "USD",
                            "shippingInfo": {"countryCode": "US", "receiverName": "Buyer"},
                            "goodsList": [{"sellerSku": "DEMO-SKU-0045", "goodsName": "SHEIN Item", "quantity": 2, "price": "6.50"}],
                        }
                    ]
                },
            },
        )
    )
    connector = SheinConnector(
        {"open_key_id": "open-key", "secret_key": "secret"},
        {"base_url": "https://openapi.sheincorp.com", "dry_run_fulfillment": True, "signature_random_key": "abcde"},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("SH-PKG-1", "TRK-SH"), orders[0])

    headers = route.calls.last.request.headers
    assert headers["x-lt-openkeyid"] == "open-key"
    assert headers["x-lt-signature"].startswith("abcde")
    assert orders[0].platform_order_id == "SH-1"
    assert orders[0].posting_number == "SH-PKG-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0045"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_shein_real_shipment_payload_is_configurable():
    ship_route = respx.post("https://openapi.sheincorp.com/open-api/order/import-batch-multiple-express").mock(
        return_value=Response(200, json={"info": {"packageNo": "SH-PKG-1", "trackingNumber": "TRK-SH", "expressCode": "UPS", "status": "OK"}})
    )
    connector = SheinConnector(
        {"open_key_id": "open-key", "secret_key": "secret"},
        {"base_url": "https://openapi.sheincorp.com", "carrier_code": "UPS", "signature_random_key": "abcde"},
    )
    order = connector._normalize_order({"orderNo": "SH-1", "packageNo": "SH-PKG-1", "goodsList": [{"sellerSku": "DEMO-SKU-0045"}]})
    assert order is not None
    order.raw_payload["tracking_number"] = "TRK-SH"

    shipment = await connector.create_platform_shipment(order)
    payload = json.loads(ship_route.calls.last.request.content)

    assert payload["orderList"][0]["orderNo"] == "SH-1"
    assert payload["orderList"][0]["trackingNumber"] == "TRK-SH"
    assert shipment.platform_shipment_id == "SH-PKG-1"


@pytest.mark.asyncio
@respx.mock
async def test_coupang_fetch_orders_and_cea_authorization():
    route = respx.get("https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v5/vendors/VENDOR/ordersheets").mock(
        return_value=Response(
            200,
            json={
                "code": "SUCCESS",
                "data": [
                    {
                        "orderId": 1001,
                        "shipmentBoxId": 9001,
                        "status": "ACCEPT",
                        "orderedAt": "2026-06-01T00:00:00",
                        "shipmentDueDate": "2026-06-03T00:00:00",
                        "receiver": {"name": "Buyer", "countryCode": "KR"},
                        "orderItems": [{"sellerProductItemId": "SKU-CP", "vendorItemName": "Coupang Item", "shippingCount": 1, "salesPrice": 12000}],
                    }
                ],
            },
        )
    )
    connector = CoupangConnector(
        {"access_key": "access", "secret_key": "secret", "vendor_id": "VENDOR"},
        {"base_url": "https://api-gateway.coupang.com", "dry_run_fulfillment": True, "pull_statuses": ["ACCEPT"]},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("9001", "TRK-CP"), orders[0])

    auth = route.calls.last.request.headers["authorization"]
    assert auth.startswith("CEA algorithm=HmacSHA256")
    assert "access-key=access" in auth
    assert orders[0].platform_order_id == "1001"
    assert orders[0].posting_number == "9001"
    assert orders[0].raw_payload["products"][0]["sku"] == "SKU-CP"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_coupang_create_invoice_payload():
    ship_route = respx.post("https://api-gateway.coupang.com/v2/providers/openapi/apis/api/v4/vendors/VENDOR/orders/invoices").mock(
        return_value=Response(200, json={"code": "SUCCESS", "data": {"shipmentBoxId": 9001, "invoiceNumber": "TRK-CP", "deliveryCompanyCode": "CJGLS"}})
    )
    connector = CoupangConnector(
        {"access_key": "access", "secret_key": "secret", "vendor_id": "VENDOR"},
        {"base_url": "https://api-gateway.coupang.com", "delivery_company_code": "CJGLS"},
    )
    order = connector._normalize_order({"orderId": 1001, "shipmentBoxId": 9001, "orderItems": [{"sellerProductItemId": "SKU-CP"}]})
    assert order is not None
    order.raw_payload["tracking_number"] = "TRK-CP"

    shipment = await connector.create_platform_shipment(order)
    payload = json.loads(ship_route.calls.last.request.content)

    assert payload["vendorId"] == "VENDOR"
    assert payload["orderSheetInvoiceApplyDtos"][0]["shipmentBoxId"] == 9001
    assert payload["orderSheetInvoiceApplyDtos"][0]["invoiceNumber"] == "TRK-CP"
    assert shipment.tracking_number == "TRK-CP"


@pytest.mark.asyncio
@respx.mock
async def test_wayfair_fetch_orders_with_oauth_and_graphql():
    token_route = respx.post("https://sso.auth.wayfair.com/oauth/token").mock(
        return_value=Response(200, json={"access_token": "wf-token", "expires_in": 3600})
    )
    graphql_route = respx.post("https://api.wayfair.com/v1/graphql").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "getDropshipPurchaseOrders": [
                        {
                            "poNumber": "WF-PO-1",
                            "poDate": "2026-06-01T00:00:00Z",
                            "estimatedShipDate": "2026-06-03T00:00:00Z",
                            "customerName": "Buyer",
                            "customerCountry": "US",
                            "shippingInfo": {"shipSpeed": "GROUND", "carrierCode": "FEDEX"},
                            "warehouse": {"id": "WH-1", "name": "Warehouse"},
                            "products": [{"partNumber": "SKU-WF", "name": "Wayfair Item", "quantity": 3, "price": "5.00"}],
                        }
                    ]
                }
            },
        )
    )
    connector = WayfairConnector(
        {"client_id": "client", "client_secret": "secret", "supplier_id": "supplier"},
        {"graphql_url": "https://api.wayfair.com/v1/graphql", "dry_run_fulfillment": True},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("WF-PO-1", "TRK-WF"), orders[0])

    assert token_route.called
    assert graphql_route.called
    assert graphql_route.calls.last.request.headers["authorization"] == "Bearer wf-token"
    assert orders[0].platform_order_id == "WF-PO-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "SKU-WF"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_wayfair_register_shipment_and_fetch_label_url():
    graphql_route = respx.post("https://api.wayfair.com/v1/graphql").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "purchaseOrders": {
                        "register": {
                            "eventDate": "2026-06-01T01:00:00Z",
                            "consolidatedShippingLabel": {"url": "https://labels.wayfair.test/WF-PO-1.pdf"},
                            "shippingLabelInfo": {"carrier": "FEDEX"},
                            "purchaseOrder": {"poNumber": "WF-PO-1", "shippingInfo": {"carrierCode": "FEDEX"}},
                        }
                    }
                }
            },
        )
    )
    label_route = respx.get("https://labels.wayfair.test/WF-PO-1.pdf").mock(
        return_value=Response(200, content=b"%PDF-wayfair", headers={"content-type": "application/pdf"})
    )
    connector = WayfairConnector(
        {"access_token": "wf-token", "supplier_id": "supplier"},
        {"graphql_url": "https://api.wayfair.com/v1/graphql", "warehouse_id": "WH-1"},
    )
    order = connector._normalize_order({"poNumber": "WF-PO-1", "warehouse": {"id": "WH-1"}, "products": [{"partNumber": "SKU-WF"}]})
    assert order is not None

    shipment = await connector.create_platform_shipment(order)
    label = await connector.fetch_label(shipment, order)
    payload = json.loads(graphql_route.calls.last.request.content)

    assert payload["variables"]["params"]["poNumber"] == "WF-PO-1"
    assert shipment.raw_payload["label_url"] == "https://labels.wayfair.test/WF-PO-1.pdf"
    assert label_route.called
    assert label.content == b"%PDF-wayfair"
