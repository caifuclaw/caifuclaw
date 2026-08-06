# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import json
import base64
import re

import pytest
import respx
from httpx import Response

from app.adapters.base import ShipmentResult
from app.adapters.dmsmatrix import DMSMatrixConnector
from app.adapters.ebay import EbayConnector
from app.adapters.shopify import ShopifyConnector
from app.adapters.temu import TemuConnector
from app.adapters.walmart import WalmartConnector
from app.factory import canonical_platform, connector_for


def test_phase2_platforms_registered_in_factory():
    assert canonical_platform("shopify_admin") == "shopify"
    assert canonical_platform("ebay_sell") == "ebay"
    assert canonical_platform("walmart_marketplace") == "walmart"
    assert connector_for("shopify", {"shop_domain": "demo.myshopify.com", "access_token": "token"}, {}).platform == "shopify"
    assert connector_for("ebay", {"access_token": "token"}, {}).platform == "ebay"
    assert connector_for("walmart", {"access_token": "token", "seller_id": "seller"}, {}).platform == "walmart"
    assert connector_for("temu", {"app_key": "app", "app_secret": "secret", "access_token": "token", "mall_id": "mall"}, {"order_list_path": "/orders"}).platform == "temu"
    assert canonical_platform("dms_matrix") == "dmsmatrix"
    assert connector_for("dmsmatrix", {"api_key": "token"}, {}).platform == "dmsmatrix"


@pytest.mark.asyncio
@respx.mock
async def test_shopify_fetch_orders_and_preview_label():
    route = respx.post("https://demo.myshopify.com/admin/api/2026-04/graphql.json").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "orders": {
                        "nodes": [
                            {
                                "id": "gid://shopify/Order/1001",
                                "name": "#1001",
                                "createdAt": "2026-06-01T00:00:00Z",
                                "processedAt": "2026-06-01T00:05:00Z",
                                "displayFulfillmentStatus": "UNFULFILLED",
                                "displayFinancialStatus": "PAID",
                                "totalPriceSet": {"shopMoney": {"amount": "24.50", "currencyCode": "USD"}},
                                "shippingLine": {"title": "Standard", "code": "STD"},
                                "shippingAddress": {"name": "Buyer", "countryCodeV2": "US"},
                                "fulfillments": [],
                                "fulfillmentOrders": {
                                    "nodes": [
                                        {
                                            "id": "gid://shopify/FulfillmentOrder/2001",
                                            "status": "OPEN",
                                            "fulfillBy": "2026-06-03T00:00:00Z",
                                            "deliveryMethod": {"methodType": "SHIPPING", "serviceCode": "STD"},
                                            "lineItems": {
                                                "nodes": [
                                                    {
                                                        "id": "gid://shopify/FulfillmentOrderLineItem/3001",
                                                        "remainingQuantity": 2,
                                                        "lineItem": {
                                                            "id": "gid://shopify/LineItem/4001",
                                                            "sku": "DEMO-SKU-0039",
                                                            "title": "Shopify Item",
                                                            "quantity": 2,
                                                            "currentQuantity": 2,
                                                            "originalUnitPriceSet": {"shopMoney": {"amount": "12.25", "currencyCode": "USD"}},
                                                        },
                                                    }
                                                ]
                                            },
                                        }
                                    ]
                                },
                            }
                        ],
                        "pageInfo": {"hasNextPage": False, "endCursor": None},
                    }
                }
            },
        )
    )
    connector = ShopifyConnector(
        {"shop_domain": "demo.myshopify.com", "access_token": "token"},
        {"dry_run_fulfillment": True},
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("gid://shopify/FulfillmentOrder/2001", "TRK-1"), orders[0])

    assert route.called
    assert orders[0].platform_order_id == "gid://shopify/Order/1001"
    assert orders[0].platform_order_no == "#1001"
    assert orders[0].posting_number == "gid://shopify/FulfillmentOrder/2001"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0039"
    assert orders[0].raw_payload["fulfillment_order_line_items"][0]["id"] == "gid://shopify/FulfillmentOrderLineItem/3001"
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_shopify_create_fulfillment_posts_graphql_mutation():
    route = respx.post("https://demo.myshopify.com/admin/api/2026-04/graphql.json").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "fulfillmentCreate": {
                        "fulfillment": {
                            "id": "gid://shopify/Fulfillment/5001",
                            "status": "SUCCESS",
                            "trackingInfo": [{"number": "TRK-SHOP", "company": "UPS"}],
                        },
                        "userErrors": [],
                    }
                }
            },
        )
    )
    connector = ShopifyConnector(
        {"shop_domain": "demo.myshopify.com", "access_token": "token"},
        {"dry_run_fulfillment": False, "carrier_name": "UPS"},
    )
    order = (await _shopify_order_for_shipment(connector))
    order.raw_payload["tracking_number"] = "TRK-SHOP"

    shipment = await connector.create_platform_shipment(order)
    request_payload = json.loads(route.calls.last.request.content)

    assert shipment.platform_shipment_id == "gid://shopify/Fulfillment/5001"
    assert request_payload["variables"]["fulfillment"]["lineItemsByFulfillmentOrder"][0]["fulfillmentOrderId"] == "gid://shopify/FulfillmentOrder/2001"
    assert request_payload["variables"]["fulfillment"]["trackingInfo"]["number"] == "TRK-SHOP"


async def _shopify_order_for_shipment(connector: ShopifyConnector):
    order = {
        "id": "gid://shopify/Order/1001",
        "name": "#1001",
        "displayFulfillmentStatus": "UNFULFILLED",
        "fulfillmentOrders": {
            "nodes": [
                {
                    "id": "gid://shopify/FulfillmentOrder/2001",
                    "status": "OPEN",
                    "lineItems": {
                        "nodes": [
                            {
                                "id": "gid://shopify/FulfillmentOrderLineItem/3001",
                                "remainingQuantity": 1,
                                "lineItem": {"sku": "DEMO-SKU-0039", "title": "Shopify Item", "quantity": 1},
                            }
                        ]
                    },
                }
            ]
        },
    }
    normalized = connector._normalize_order(order)
    assert normalized is not None
    return normalized


@pytest.mark.asyncio
@respx.mock
async def test_ebay_fetch_orders_and_real_shipment_payload():
    respx.get("https://api.ebay.com/sell/fulfillment/v1/order").mock(
        return_value=Response(
            200,
            json={
                "orders": [
                    {
                        "orderId": "EBAY-1",
                        "legacyOrderId": "12-34567-89012",
                        "orderFulfillmentStatus": "NOT_STARTED",
                        "creationDate": "2026-06-01T00:00:00Z",
                        "paymentSummary": {"payments": [{"paymentDate": "2026-06-01T00:05:00Z"}]},
                        "fulfillmentStartInstructions": [
                            {"shippingStep": {"shippingServiceCode": "USPSPriority", "shipTo": {"fullName": "Buyer", "contactAddress": {"countryCode": "US"}}}}
                        ],
                        "lineItems": [
                            {
                                "lineItemId": "LI-1",
                                "sku": "DEMO-SKU-0040",
                                "title": "eBay Item",
                                "quantity": 1,
                                "lineItemCost": {"value": "18.00", "currency": "USD"},
                                "lineItemFulfillmentInstructions": {"shipByDate": "2026-06-03T00:00:00Z"},
                            }
                        ],
                    }
                ],
                "total": 1,
            },
        )
    )
    fulfillments_route = respx.get("https://api.ebay.com/sell/fulfillment/v1/order/EBAY-1/shipping_fulfillment").mock(
        return_value=Response(200, json={"fulfillments": []})
    )
    ship_route = respx.post("https://api.ebay.com/sell/fulfillment/v1/order/EBAY-1/shipping_fulfillment").mock(
        return_value=Response(200, json={"fulfillmentId": "FUL-1", "trackingNumber": "TRK-EBAY", "shippingCarrierCode": "USPS", "status": "CREATED"})
    )
    connector = EbayConnector(
        {"access_token": "token"},
        {"base_url": "https://api.ebay.com", "dry_run_fulfillment": False, "shipping_carrier_code": "USPS"},
    )

    orders = await connector.fetch_unprocessed_orders()
    orders[0].raw_payload["tracking_number"] = "TRK-EBAY"
    shipment = await connector.create_platform_shipment(orders[0])
    payload = json.loads(ship_route.calls.last.request.content)

    assert fulfillments_route.called
    assert orders[0].platform_order_id == "EBAY-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0040"
    assert payload["lineItems"] == [{"lineItemId": "LI-1", "quantity": 1}]
    assert payload["trackingNumber"] == "TRK-EBAY"
    assert shipment.platform_shipment_id == "FUL-1"


@pytest.mark.asyncio
@respx.mock
async def test_walmart_fetch_released_orders_with_token_and_acknowledge():
    token_route = respx.post("https://marketplace.walmartapis.com/v3/token").mock(
        return_value=Response(200, json={"access_token": "wm-token", "expires_in": 900})
    )
    list_route = respx.get("https://marketplace.walmartapis.com/v3/orders/released").mock(
        return_value=Response(
            200,
            json={
                "list": {
                    "elements": {
                        "order": [
                            {
                                "purchaseOrderId": "WM-PO-1",
                                "customerOrderId": "WM-CUSTOMER-1",
                                "orderDate": "2026-06-01T00:00:00Z",
                                "shippingInfo": {"methodCode": "Standard", "postalAddress": {"name": "Buyer", "country": "US"}},
                                "orderLines": {
                                    "orderLine": [
                                        {
                                            "lineNumber": "1",
                                            "item": {"sku": "DEMO-SKU-0041", "productName": "Walmart Item"},
                                            "orderLineQuantity": {"amount": "2"},
                                            "charges": {"charge": [{"chargeAmount": {"amount": "11.00", "currency": "USD"}}]},
                                            "orderLineStatuses": {"orderLineStatus": [{"status": "Created"}]},
                                        }
                                    ]
                                },
                            }
                        ]
                    }
                }
            },
        )
    )
    ack_route = respx.post("https://marketplace.walmartapis.com/v3/orders/WM-PO-1/acknowledge").mock(
        return_value=Response(200, json={"purchaseOrderId": "WM-PO-1"})
    )
    connector = WalmartConnector(
        {"client_id": "client", "client_secret": "secret", "seller_id": "seller"},
        {"base_url": "https://marketplace.walmartapis.com", "auto_acknowledge_released_orders": True},
    )

    orders = await connector.fetch_unprocessed_orders()

    assert token_route.called
    assert list_route.called
    assert ack_route.called
    assert orders[0].platform_order_id == "WM-PO-1"
    assert orders[0].platform_order_no == "WM-CUSTOMER-1"
    assert orders[0].platform_status == "Created"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0041"


@pytest.mark.asyncio
@respx.mock
async def test_walmart_create_shipping_payload():
    ship_route = respx.post("https://marketplace.walmartapis.com/v3/orders/WM-PO-1/shipping").mock(
        return_value=Response(200, json={"purchaseOrderId": "WM-PO-1", "status": "Shipped"})
    )
    connector = WalmartConnector(
        {"access_token": "wm-token", "seller_id": "seller"},
        {"base_url": "https://marketplace.walmartapis.com", "carrier_name": "UPS", "method_code": "Standard"},
    )
    order = connector._normalize_order(
        {
            "purchaseOrderId": "WM-PO-1",
            "orderLines": {
                "orderLine": [
                    {
                        "lineNumber": "1",
                        "item": {"sku": "DEMO-SKU-0041", "productName": "Walmart Item"},
                        "orderLineQuantity": {"amount": "2"},
                        "charges": {"charge": [{"chargeAmount": {"amount": "11.00", "currency": "USD"}}]},
                        "orderLineStatuses": {"orderLineStatus": [{"status": "Acknowledged"}]},
                    }
                ]
            },
        }
    )
    assert order is not None
    order.raw_payload["tracking_number"] = "TRK-WM"

    shipment = await connector.create_platform_shipment(order)
    payload = json.loads(ship_route.calls.last.request.content)

    assert payload["orderShipment"]["orderLines"]["orderLine"][0]["lineNumber"] == "1"
    assert payload["orderShipment"]["orderLines"]["orderLine"][0]["orderLineStatuses"]["orderLineStatus"][0]["trackingInfo"]["trackingNumber"] == "TRK-WM"
    assert shipment.platform_shipment_id == "WM-PO-1"


@pytest.mark.asyncio
@respx.mock
async def test_temu_uses_configurable_paths_and_preview_label():
    list_route = respx.post("https://openapi-b-us.temu.com/api/order/list").mock(
        return_value=Response(200, json={"data": {"orders": [{"order_id": "TEMU-1"}]}})
    )
    detail_route = respx.post("https://openapi-b-us.temu.com/api/order/detail").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "order": {
                        "order_id": "TEMU-1",
                        "order_sn": "TEMU-NO-1",
                        "status": "awaiting_shipping",
                        "package_id": "TEMU-PKG-1",
                        "shipping": {"country_code": "US"},
                        "items": [{"seller_sku": "DEMO-SKU-0042", "product_name": "Temu Item", "quantity": 1, "paid_price": "8.00", "currency": "USD"}],
                    }
                }
            },
        )
    )
    connector = TemuConnector(
        {"app_key": "app", "app_secret": "secret", "access_token": "token", "mall_id": "mall"},
        {
            "base_url": "https://openapi-b-us.temu.com",
            "dry_run_fulfillment": True,
            "order_list_path": "/api/order/list",
            "order_detail_path": "/api/order/detail",
        },
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("TEMU-PKG-1", "TRK-TEMU"), orders[0])
    list_payload = json.loads(list_route.calls.last.request.content)
    detail_payload = json.loads(detail_route.calls.last.request.content)

    assert list_payload["status"] == ["pending_shipment", "awaiting_shipping"]
    assert detail_payload["order_id"] == "TEMU-1"
    assert orders[0].platform_order_id == "TEMU-1"
    assert orders[0].platform_order_no == "TEMU-NO-1"
    assert orders[0].posting_number == "TEMU-PKG-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0042"
    assert "sign" in list_route.calls.last.request.url.params
    assert label.content.startswith(b"%PDF")


@pytest.mark.asyncio
@respx.mock
async def test_temu_real_shipment_and_label_paths_are_configurable():
    ship_route = respx.post("https://openapi-b-us.temu.com/api/package/ship").mock(
        return_value=Response(200, json={"data": {"package_id": "TEMU-PKG-1", "tracking_number": "DEMO-TRACKING-0035", "carrier": "USPS", "status": "created"}})
    )
    label_route = respx.post("https://openapi-b-us.temu.com/api/package/label").mock(
        return_value=Response(200, content=b"%PDF-temu", headers={"content-type": "application/pdf"})
    )
    connector = TemuConnector(
        {"app_key": "app", "app_secret": "secret", "access_token": "token", "mall_id": "mall"},
        {
            "base_url": "https://openapi-b-us.temu.com",
            "ship_path": "/api/package/ship",
            "label_path": "/api/package/label",
            "carrier_name": "USPS",
        },
    )
    order = connector._normalize_order({"order_id": "TEMU-1", "package_id": "TEMU-PKG-1", "items": [{"seller_sku": "DEMO-SKU-0042"}]})
    assert order is not None
    order.raw_payload["tracking_number"] = "TRK-TEMU"

    shipment = await connector.create_platform_shipment(order)
    label = await connector.fetch_label(shipment, order)

    assert ship_route.called
    assert label_route.called
    assert shipment.platform_shipment_id == "TEMU-PKG-1"
    assert label.content == b"%PDF-temu"


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_platform_products_uses_configured_catalog_endpoint():
    route = respx.get("https://api.dmsmatrix.test/products").mock(
        return_value=Response(
            200,
            json={
                "Data": [
                    {
                        "SKU": "SKU-DMS-1",
                        "ItemDescription": "DMS Catalog Item",
                        "Stock": 5,
                        "Price": "12.34",
                        "CurrencyCode": "USD",
                        "WarehouseCode": "WH-1",
                        "ImageUrl": "https://cdn.example.test/dms/catalog-main.jpg",
                    }
                ]
            },
        )
    )
    connector = DMSMatrixConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api.dmsmatrix.test",
            "product_catalog_path": "/products",
            "product_catalog_method": "GET",
        },
    )

    rows = await connector.fetch_platform_products()

    assert route.called
    assert rows[0]["platform_product_id"] == "SKU-DMS-1"
    assert rows[0]["platform_sku"] == "SKU-DMS-1"
    assert rows[0]["product_name"] == "DMS Catalog Item"
    assert rows[0]["available_stock"] == 5
    assert rows[0]["warehouse_code"] == "WH-1"
    assert rows[0]["price_amount"] == "12.34"
    assert rows[0]["price_currency"] == "USD"
    assert rows[0]["main_image_url"] == "https://cdn.example.test/dms/catalog-main.jpg"
    assert rows[0]["raw_payload"]["catalog_source"] == "configured_endpoint"


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_orders_and_label_download():
    orders_route = respx.get("https://api.dmsmatrix.test/orders").mock(
        return_value=Response(
            200,
            json={
                "data": {
                    "orders": [
                        {
                            "order_id": "DMS-1",
                            "order_no": "DMS-NO-1",
                            "status": "awaiting_shipping",
                            "shipment_id": "SHIP-1",
                            "tracking_number": "DEMO-TRACKING-0036",
                            "order_date": "2026-06-01T00:00:00Z",
                            "shipping": {"address": {"name": "Buyer", "countryCode": "US"}},
                            "items": [
                                {
                                    "sku": "DEMO-SKU-0043",
                                    "name": "DMS Item",
                                    "quantity": 2,
                                    "unitPrice": {"amount": "9.50", "currency": "USD"},
                                }
                            ],
                        }
                    ]
                }
            },
        )
    )
    label_route = respx.get("https://api.dmsmatrix.test/shipments/SHIP-1/label").mock(
        return_value=Response(200, content=b"%PDF-dmsmatrix", headers={"content-type": "application/pdf"})
    )
    connector = DMSMatrixConnector(
        {"api_key": "token"},
        {
            "base_url": "https://api.dmsmatrix.test",
            "orders_path": "/orders",
            "orders_method": "GET",
            "label_path": "/shipments/{shipment_id}/label",
        },
    )

    orders = await connector.fetch_unprocessed_orders()
    label = await connector.fetch_label(ShipmentResult("SHIP-1", "TRK-DMS"), orders[0])

    assert orders_route.called
    assert label_route.called
    assert orders_route.calls.last.request.headers["authorization"] == "Bearer token"
    assert orders[0].platform_order_id == "DMS-1"
    assert orders[0].platform_order_no == "DMS-NO-1"
    assert orders[0].posting_number == "SHIP-1"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0043"
    assert orders[0].raw_payload["shipment_tracking_number"] == "DEMO-TRACKING-0036"
    assert label.content == b"%PDF-dmsmatrix"


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_platform_products_falls_back_to_order_lines():
    orders_route = respx.post("https://api.dmsmatrix.test/Order/getOrders").mock(
        return_value=Response(
            200,
            json={
                "Data": [
                    {
                        "ReferenceOrderId": "1234567890",
                        "GeneralInfo": {
                            "ChannelCode": "GRPUK",
                            "ChannelOrderId": "FRUUGO-1",
                            "OrderStatus": "Shipped",
                            "CreatedDate": "2019-08-01 15:31:15",
                            "OrderDate": "2019-08-01 14:12:13",
                            "ShippingMethod": "Royal Mail",
                            "TotalCost": "12.34",
                            "CurrencyCode": "GBP",
                        },
                        "CustomerInfo": {
                            "FullName": "Buyer",
                            "CountryCode": "GB",
                        },
                        "LineItemsInfo": [
                            {
                                "SKU": "DEMO-SKU-0044",
                                "ItemDescription": "Documented Item",
                                "ItemQty": 2,
                                "ItemUnitCost": "6.17",
                                "CurrencyCode": "GBP",
                                "ProductImageUrl": "https://cdn.example.test/dms/order-line-main.webp",
                            }
                        ],
                        "ShippingInfo": [
                            {
                                "TrackingNumber": "DMS1234567890",
                                "CarrierCode": "RM",
                            }
                        ],
                    }
                ],
                "Errors": [],
                "Meta": {"CurrentPage": 1, "ResultsPages": 1, "ResultsOrders": 1},
            },
        )
    )
    connector = DMSMatrixConnector(
        {"client_name": "demo-client", "client_id": "demo-id", "client_secret": "demo-secret", "channel_code": "GRPUK"},
        {"base_url": "https://api.dmsmatrix.test"},
    )

    rows = await connector.fetch_platform_products()

    assert orders_route.called
    assert rows[0]["platform_product_id"] == "DEMO-SKU-0044"
    assert rows[0]["platform_sku"] == "DEMO-SKU-0044"
    assert rows[0]["available_stock"] == 0
    assert rows[0]["price_currency"] == "GBP"
    assert rows[0]["main_image_url"] == "https://cdn.example.test/dms/order-line-main.webp"
    assert rows[0]["raw_payload"]["catalog_source"] == "orders_fallback"


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_registers_external_tracking_with_fulfil_orders():
    route = respx.post("https://api.dmsmatrix.test/Order/fulfilOrders").mock(return_value=Response(200, content=b""))
    connector = DMSMatrixConnector(
        {"client_name": "demo-client", "client_id": "demo-id", "client_secret": "demo-secret"},
        {"base_url": "https://api.dmsmatrix.test"},
    )
    order = DMSMatrixConnector({}, {})._normalize_order({"ReferenceOrderId": "DMS-REF-1"})
    assert order is not None

    shipment = await connector.register_tracking_number(order, "WB-TRACK-1", "WanbExpress")
    payload = json.loads(route.calls.last.request.content)

    assert payload == [{"ReferenceOrderId": "DMS-REF-1", "ShippingInfo": [{"TrackingNumber": "WB-TRACK-1"}]}]
    assert route.calls.last.request.headers["client-id"] == "demo-id"
    assert shipment.platform_shipment_id == "DMS-REF-1"
    assert shipment.status == "registered"


@pytest.mark.asyncio
async def test_dmsmatrix_external_tracking_skips_matching_existing_waybill():
    connector = DMSMatrixConnector({}, {})
    order = DMSMatrixConnector({}, {})._normalize_order(
        {"ReferenceOrderId": "DMS-REF-1", "ShippingInfo": [{"TrackingNumber": "WB-TRACK-1"}]}
    )
    assert order is not None

    shipment = await connector.register_tracking_number(order, "WB-TRACK-1", "WanbExpress")

    assert shipment.status == "existing"
    assert shipment.platform_shipment_id == "DMS-REF-1"


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_label_defaults_to_get_orders_label_data():
    label_content = b"%PDF-dmsmatrix-from-shipment-by-order-id"
    label_route = respx.post("https://api.dmsmatrix.test/Order/getOrders").mock(
        return_value=Response(
            200,
            json={
                "Data": [
                    {
                        "ReferenceOrderId": "16a3e98a9e5cda",
                        "ShippingInfo": [
                            {
                                "TrackingNumber": "NTK_16a3e98a9e5cda",
                                "Label": {
                                    "Type": "PDF",
                                    "Format": "6x4_PDF",
                                    "Data": base64.b64encode(label_content).decode("ascii"),
                                },
                            }
                        ],
                    }
                ],
                "Errors": [],
            },
        )
    )
    connector = DMSMatrixConnector(
        {"client_name": "demo-client", "client_id": "demo-id", "client_secret": "demo-secret"},
        {"base_url": "https://api.dmsmatrix.test", "label_format": "6x4_PDF"},
    )
    order = DMSMatrixConnector({}, {})._normalize_order(
        {
            "ReferenceOrderId": "16a3e98a9e5cda",
            "GeneralInfo": {"ChannelOrderId": "200000000000000001", "OrderStatus": "Shipped"},
            "ShippingInfo": [{"TrackingNumber": "NTK_16a3e98a9e5cda", "Label": {"Type": "PDF", "Format": "6x4_PDF", "Data": ""}}],
        }
    )
    assert order is not None

    label = await connector.fetch_label(ShipmentResult("16a3e98a9e5cda", "NTK_16a3e98a9e5cda"), order)
    payload = json.loads(label_route.calls.last.request.content)

    assert payload == {
        "ReferenceOrderIds": ["16a3e98a9e5cda"],
        "LabelFormat": "6x4_PDF",
        "Sections": ["GeneralInfo", "LineItemsInfo", "CustomerInfo", "ShippingInfo", "ReturnInfo"],
        "PerPage": 50,
        "Page": 1,
    }
    assert label.content == label_content


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_label_reports_empty_get_orders_label():
    respx.post("https://api.dmsmatrix.test/Order/getOrders").mock(
        return_value=Response(
            200,
            json={
                "Data": [
                    {
                        "ReferenceOrderId": "16a3e98a9e5cda",
                        "ShippingInfo": [
                            {
                                "TrackingNumber": "NTK_16a3e98a9e5cda",
                                "Label": {"Type": "PDF", "Format": "6x4_PDF", "Data": ""},
                            }
                        ],
                    }
                ],
                "Errors": [],
            },
        )
    )
    connector = DMSMatrixConnector(
        {"client_name": "demo-client", "client_id": "demo-id", "client_secret": "demo-secret"},
        {"base_url": "https://api.dmsmatrix.test", "label_format": "6x4_PDF"},
    )
    order = DMSMatrixConnector({}, {})._normalize_order({"ReferenceOrderId": "16a3e98a9e5cda"})
    assert order is not None

    with pytest.raises(RuntimeError, match="ShippingInfo.Label.Data"):
        await connector.fetch_label(ShipmentResult("16a3e98a9e5cda", "NTK_16a3e98a9e5cda"), order)


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_orders_uses_client_credentials_headers():
    orders_route = respx.post("https://api.dmsmatrix.test/Order/getOrders").mock(
        return_value=Response(200, json={"data": {"orders": []}})
    )
    connector = DMSMatrixConnector(
        {
            "client_name": "demo-client",
            "client_id": "demo-id",
            "client_secret": "demo-secret",
            "channel_code": "demo-channel",
        },
        {"base_url": "https://api.dmsmatrix.test"},
    )

    orders = await connector.fetch_unprocessed_orders()
    headers = orders_route.calls.last.request.headers
    payload = json.loads(orders_route.calls.last.request.content)

    assert orders == []
    assert headers["client-name"] == "demo-client"
    assert headers["client-id"] == "demo-id"
    assert headers["client-secret"] == "demo-secret"
    assert headers["channel-code"] == "demo-channel"
    assert payload["ChannelCodes"] == ["demo-channel"]
    assert payload["Page"] == 1
    assert payload["PerPage"] == 50


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_fetch_orders_uses_documented_get_orders_payload():
    orders_route = respx.post("https://api.dmsmatrix.test/Order/getOrders").mock(
        return_value=Response(
            200,
            json={
                "Data": [
                    {
                        "ReferenceOrderId": "1234567890",
                        "GeneralInfo": {
                            "ChannelCode": "GRPUK",
                            "ChannelOrderId": "FRUUGO-1",
                            "OrderStatus": "Shipped",
                            "CreatedDate": "2019-08-01 15:31:15",
                            "OrderDate": "2019-08-01 14:12:13",
                            "ShippingMethod": "Royal Mail",
                            "TotalCost": "12.34",
                            "CurrencyCode": "GBP",
                        },
                        "CustomerInfo": {
                            "FullName": "Buyer",
                            "CountryCode": "GB",
                        },
                        "LineItemsInfo": [
                            {
                                "SKU": "DEMO-SKU-0044",
                                "ItemDescription": "Documented Item",
                                "ItemQty": 2,
                                "ItemUnitCost": "6.17",
                                "CurrencyCode": "GBP",
                            }
                        ],
                        "ShippingInfo": [
                            {
                                "TrackingNumber": "DMS1234567890",
                                "CarrierCode": "RM",
                            }
                        ],
                    }
                ],
                "Errors": [],
                "Meta": {"CurrentPage": 1, "ResultsPages": 1, "ResultsOrders": 1},
            },
        )
    )
    connector = DMSMatrixConnector(
        {"client_name": "demo-client", "client_id": "demo-id", "client_secret": "demo-secret", "channel_code": "GRPUK"},
        {"base_url": "https://api.dmsmatrix.test"},
    )

    orders = await connector.fetch_unprocessed_orders()
    payload = json.loads(orders_route.calls.last.request.content)

    assert payload == {"ChannelCodes": ["GRPUK"], "PerPage": 50, "Page": 1}
    assert orders[0].platform_order_id == "1234567890"
    assert orders[0].platform_order_no == "FRUUGO-1"
    assert orders[0].posting_number == "1234567890"
    assert orders[0].platform_status == "Shipped"
    assert orders[0].raw_payload["created_at"] == "2019-08-01 15:31:15"
    assert orders[0].raw_payload["country_code"] == "GB"
    assert orders[0].raw_payload["buyer_name"] == "Buyer"
    assert orders[0].raw_payload["order_amount"] == "12.34"
    assert orders[0].raw_payload["currency_code"] == "GBP"
    assert orders[0].raw_payload["shipment_tracking_number"] == "DMS1234567890"
    assert orders[0].raw_payload["products"][0]["sku"] == "DEMO-SKU-0044"
    assert orders[0].raw_payload["products"][0]["quantity"] == 2


@pytest.mark.asyncio
@respx.mock
async def test_dmsmatrix_batch_label_path_is_configurable():
    batch_route = respx.post("https://api.dmsmatrix.test/labels/batch").mock(
        return_value=Response(200, content=b"%PDF-dmsmatrix-batch", headers={"content-type": "application/pdf"})
    )
    connector = DMSMatrixConnector(
        {"access_token": "token"},
        {"base_url": "https://api.dmsmatrix.test", "label_batch_path": "/labels/batch"},
    )
    order = connector._normalize_order({"order_id": "DMS-1", "shipment_id": "SHIP-1", "items": [{"sku": "DEMO-SKU-0043"}]})
    assert order is not None

    label = await connector.fetch_label_batch([order])
    payload = json.loads(batch_route.calls.last.request.content)

    assert payload["orders"][0]["order_id"] == "DMS-1"
    assert payload["orders"][0]["shipment_id"] == "SHIP-1"
    assert payload["format"] == "pdf"
    assert label.content == b"%PDF-dmsmatrix-batch"
