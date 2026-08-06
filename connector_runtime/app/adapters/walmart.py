# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import base64
from datetime import datetime, timezone
from uuid import uuid4

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    deep_get,
    extract_items,
    first_value,
    iso_utc,
    label_from_platform_response,
    product_payload,
    response_data,
)


class WalmartConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "walmart"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.client_id = str(self.credentials.get("client_id") or "")
        self.client_secret = str(self.credentials.get("client_secret") or "")
        self.access_token = str(self.credentials.get("access_token") or "")
        self.seller_id = str(self.credentials.get("seller_id") or self.settings.get("account_id") or "")
        self.base_url = str(self.settings.get("base_url") or "https://marketplace.walmartapis.com").rstrip("/")
        self.market = str(self.settings.get("market") or "us")
        self.account_id = str(self.settings.get("account_id") or self.seller_id)

    async def _ensure_access_token(self) -> str:
        if self.access_token:
            return self.access_token
        if not (self.client_id and self.client_secret):
            raise ValueError("Walmart client_id/client_secret or access_token is required")
        token_url = str(self.settings.get("token_url") or f"{self.base_url}{self.settings.get('token_path') or '/v3/token'}")
        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode("utf-8")).decode("ascii")
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "WM_QOS.CORRELATION_ID": str(uuid4()),
            "WM_SVC.NAME": str(self.settings.get("service_name") or "Walmart Marketplace"),
            "WM_MARKET": self.market,
        }
        data = await self._request("POST", token_url, headers=headers, data={"grant_type": "client_credentials"}, timeout=30)
        payload = response_data(data)
        if not isinstance(payload, dict) or not payload.get("access_token"):
            raise RuntimeError(f"Walmart token response did not include access_token: {data}")
        self.access_token = str(payload["access_token"])
        return self.access_token

    async def _headers(self) -> dict:
        token = await self._ensure_access_token()
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "WM_SEC.ACCESS_TOKEN": token,
            "WM_QOS.CORRELATION_ID": str(uuid4()),
            "WM_SVC.NAME": str(self.settings.get("service_name") or "Walmart Marketplace"),
            "WM_MARKET": self.market,
        }
        channel_type = self.settings.get("consumer_channel_type")
        if channel_type:
            headers["WM_CONSUMER.CHANNEL.TYPE"] = str(channel_type)
        return headers

    async def _get(self, path: str, params: dict | None = None, *, binary: bool = False):
        return await self._request("GET", f"{self.base_url}{path}", headers=await self._headers(), params=params, binary=binary)

    async def _post(self, path: str, payload: dict | None = None):
        return await self._request("POST", f"{self.base_url}{path}", headers=await self._headers(), json_body=payload or {})

    @staticmethod
    def _order_lines(order: dict) -> list[dict]:
        return extract_items(order, "orderLines.orderLine", "order_lines", "lines", "items")

    @staticmethod
    def _first_status(line: dict) -> dict:
        statuses = deep_get(line, "orderLineStatuses.orderLineStatus")
        rows = as_list(statuses)
        return rows[0] if rows and isinstance(rows[0], dict) else {}

    @staticmethod
    def _line_charge(line: dict) -> dict:
        charges = deep_get(line, "charges.charge")
        rows = as_list(charges)
        for row in rows:
            if isinstance(row, dict) and row.get("chargeAmount"):
                amount = row.get("chargeAmount")
                return amount if isinstance(amount, dict) else row
        return {}

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("purchaseOrderId"), order.get("purchase_order_id"), order.get("id")) or "")
        if not order_id:
            return None
        shipping = order.get("shippingInfo") if isinstance(order.get("shippingInfo"), dict) else {}
        address = shipping.get("postalAddress") if isinstance(shipping.get("postalAddress"), dict) else {}
        lines = self._order_lines(order)
        first_line = lines[0] if lines else {}
        first_status = self._first_status(first_line) if first_line else {}
        tracking = deep_get(first_status, "trackingInfo.trackingNumber")
        products = []
        for line in lines:
            item = line.get("item") if isinstance(line.get("item"), dict) else line
            charge = self._line_charge(line)
            products.append(
                product_payload(
                    {**line, **({"item": item} if isinstance(item, dict) else {}), "chargeAmount": charge},
                    sku_keys=("item.sku", "sku", "item.productId"),
                    name_keys=("item.productName", "productName", "name", "title"),
                    quantity_keys=("orderLineQuantity.amount", "quantity", "qty"),
                    price_keys=("chargeAmount.amount", "charges.charge.0.chargeAmount.amount", "price"),
                    currency_keys=("chargeAmount.currency", "charges.charge.0.chargeAmount.currency", "currency"),
                )
                | {"line_number": first_value(line.get("lineNumber"), line.get("orderLineNumber"), line.get("line_number"))}
            )
        status = str(first_value(first_status.get("status"), order.get("status")) or "")
        raw_payload = {
            **order,
            "id": order_id,
            "order_number": first_value(order.get("customerOrderId"), order_id),
            "site": self.market,
            "created_at": order.get("orderDate"),
            "order_date": order.get("orderDate"),
            "payment_at": order.get("orderDate"),
            "shipping_deadline_at": first_value(shipping.get("estimatedShipDate"), shipping.get("estimatedDeliveryDate")),
            "buyer_selected_logistics": first_value(shipping.get("methodCode"), shipping.get("carrierMethodName")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": address.get("country"),
            "buyer_name": address.get("name"),
            "order_amount": first_value(*(item.get("price") for item in products)),
            "currency_code": first_value(*(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("fulfillment_type"), "FBS"),
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("customerOrderId"), order_id)),
            posting_number=order_id,
            platform_status=status,
            fulfillment_type=str(raw_payload["fulfillment_type"]),
            is_overseas_warehouse=False,
            raw_payload=raw_payload,
        )

    @staticmethod
    def _order_rows(payload) -> list[dict]:
        if isinstance(payload, dict):
            rows = extract_items(payload, "list.elements.order", "elements.order", "orders", "order")
            if rows:
                return rows
        return []

    async def _fetch_order(self, purchase_order_id: str) -> dict:
        path = str(self.settings.get("order_detail_path") or "/v3/orders/{purchase_order_id}").format(purchase_order_id=purchase_order_id, order_id=purchase_order_id)
        data = await self._get(path)
        payload = response_data(data)
        if isinstance(payload, dict):
            order = first_value(payload.get("order"), payload.get("purchaseOrder"), payload)
            return order if isinstance(order, dict) else payload
        return {}

    async def _acknowledge_order(self, purchase_order_id: str) -> None:
        path = str(self.settings.get("acknowledge_path") or "/v3/orders/{purchase_order_id}/acknowledge").format(purchase_order_id=purchase_order_id, order_id=purchase_order_id)
        await self._post(path, {})

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        released_only = bool(self.settings.get("released_only", True))
        path = str(self.settings.get("released_orders_path" if released_only else "orders_path") or ("/v3/orders/released" if released_only else "/v3/orders"))
        params = dict(self.settings.get("orders_params") or {})
        if since:
            params.setdefault(str(self.settings.get("created_start_param") or "createdStartDate"), iso_utc(since))
        statuses = self.settings.get("pull_statuses")
        if statuses and not released_only:
            params.setdefault("status", ",".join(str(item) for item in as_list(statuses)))
        data = await self._get(path, params)
        payload = response_data(data)
        orders: list[NormalizedOrder] = []
        for row in self._order_rows(payload):
            order_id = str(first_value(row.get("purchaseOrderId"), row.get("id")) or "")
            detail = await self._fetch_order(order_id) if bool(self.settings.get("fetch_order_details", False)) and order_id else row
            if released_only and bool(self.settings.get("auto_acknowledge_released_orders", False)) and order_id:
                await self._acknowledge_order(order_id)
            normalized = self._normalize_order(detail)
            if normalized:
                orders.append(normalized)
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_order(order_id)
            normalized = self._normalize_order(detail)
            if not normalized:
                continue
            updates.append(
                OrderStatusUpdate(
                    posting_number=normalized.posting_number,
                    platform_order_id=normalized.platform_order_id,
                    platform_order_no=normalized.platform_order_no,
                    platform_status=normalized.platform_status,
                    shipment_tracking_number=str(normalized.raw_payload.get("shipment_tracking_number") or ""),
                    raw_payload=normalized.raw_payload,
                )
            )
        return updates

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        tracking_number = str(first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), self.settings.get("tracking_number"), order.platform_order_id) or "")
        carrier = str(first_value(self.settings.get("carrier_name"), self.settings.get("carrier_code"), order.raw_payload.get("buyer_selected_logistics"), "Other"))
        method_code = str(first_value(self.settings.get("method_code"), "Standard"))
        if self._dry_run():
            return ShipmentResult(order.platform_order_id, tracking_number, carrier, "dry_run_created", order.raw_payload)
        path = str(self.settings.get("ship_order_path") or "/v3/orders/{purchase_order_id}/shipping").format(purchase_order_id=order.platform_order_id, order_id=order.platform_order_id)
        ship_date = str(first_value(self.settings.get("ship_date_time"), datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")))
        line_rows = []
        for item in as_list(order.raw_payload.get("products") or order.raw_payload.get("items")):
            if not isinstance(item, dict):
                continue
            line_number = first_value(item.get("line_number"), item.get("lineNumber"), item.get("orderLineNumber"))
            if not line_number:
                continue
            quantity = item.get("quantity") or 1
            line_rows.append(
                {
                    "lineNumber": line_number,
                    "orderLineStatuses": {
                        "orderLineStatus": [
                            {
                                "status": "Shipped",
                                "statusQuantity": {"unitOfMeasurement": "EACH", "amount": str(quantity)},
                                "trackingInfo": {
                                    "shipDateTime": ship_date,
                                    "carrierName": {"carrier": carrier},
                                    "methodCode": method_code,
                                    "trackingNumber": tracking_number,
                                    **({"trackingURL": self.settings.get("tracking_url")} if self.settings.get("tracking_url") else {}),
                                },
                            }
                        ]
                    },
                }
            )
        payload = dict(self.settings.get("ship_order_payload_template") or {})
        payload.setdefault("orderShipment", {"orderLines": {"orderLine": line_rows}})
        data = await self._post(path, payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("purchaseOrderId"), order.platform_order_id)),
            tracking_number=str(first_value(deep_get(raw, "orderShipment.orderLines.orderLine.0.orderLineStatuses.orderLineStatus.0.trackingInfo.trackingNumber"), tracking_number)),
            carrier=carrier,
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Walmart Label Preview", shipment, order)
        if str(self.settings.get("label_mode") or "unsupported").lower() in {"unsupported", "ship_with_walmart_optional"} and not self.settings.get("label_path"):
            raise NotImplementedError("Walmart label download requires Ship with Walmart or a configured label_path")
        path = str(self.settings.get("label_path") or "")
        if not path:
            raise ValueError("Walmart label_path is required")
        data = await self._get(path.format(shipment_id=shipment.platform_shipment_id, order_id=order.platform_order_id), binary=True)
        return label_from_platform_response(data)
