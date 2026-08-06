# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime, timezone

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    deep_get,
    first_value,
    iso_utc,
    label_from_platform_response,
    product_payload,
    response_data,
)


class EbayConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "ebay"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.access_token = str(self.credentials.get("access_token") or "")
        self.refresh_token = str(self.credentials.get("refresh_token") or "")
        self.client_id = str(self.credentials.get("client_id") or "")
        self.client_secret = str(self.credentials.get("client_secret") or "")
        self.seller_id = str(self.credentials.get("seller_id") or self.settings.get("account_id") or "")
        self.base_url = str(self.settings.get("base_url") or "https://api.ebay.com").rstrip("/")
        self.marketplace_id = str(self.settings.get("marketplace_id") or "EBAY_US")
        self.account_id = str(self.settings.get("account_id") or self.seller_id or self.credentials.get("username") or "")

    @property
    def headers(self) -> dict:
        if not self.access_token:
            raise ValueError("eBay access_token is required")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
            "X-EBAY-C-MARKETPLACE-ID": self.marketplace_id,
        }

    async def _get(self, path: str, params: dict | None = None, *, binary: bool = False):
        return await self._request("GET", f"{self.base_url}{path}", headers=self.headers, params=params, binary=binary)

    async def _post(self, path: str, payload: dict):
        return await self._request("POST", f"{self.base_url}{path}", headers=self.headers, json_body=payload)

    @staticmethod
    def _line_items(order: dict) -> list[dict]:
        return [item for item in as_list(order.get("lineItems") or order.get("line_items") or order.get("items")) if isinstance(item, dict)]

    @staticmethod
    def _shipping_step(order: dict) -> dict:
        instructions = as_list(order.get("fulfillmentStartInstructions"))
        for instruction in instructions:
            if isinstance(instruction, dict) and isinstance(instruction.get("shippingStep"), dict):
                return instruction["shippingStep"]
        return {}

    @staticmethod
    def _first_tracking(order: dict) -> dict:
        fulfillments = as_list(order.get("fulfillments") or order.get("shippingFulfillments") or order.get("shipping_fulfillments"))
        for fulfillment in fulfillments:
            if isinstance(fulfillment, dict):
                return fulfillment
        return {}

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("orderId"), order.get("order_id"), order.get("id")) or "")
        if not order_id:
            return None
        shipping_step = self._shipping_step(order)
        ship_to = shipping_step.get("shipTo") if isinstance(shipping_step.get("shipTo"), dict) else {}
        address = ship_to.get("contactAddress") if isinstance(ship_to.get("contactAddress"), dict) else {}
        tracking = self._first_tracking(order)
        products = [
            product_payload(
                item,
                sku_keys=("sku", "sellerSku", "lineItemId", "legacyItemId"),
                name_keys=("title", "name"),
                quantity_keys=("quantity", "quantityPurchased"),
                price_keys=("lineItemCost.value", "lineItemCost", "price.value", "price"),
                currency_keys=("lineItemCost.currency", "price.currency", "currency"),
            )
            | {"line_item_id": first_value(item.get("lineItemId"), item.get("line_item_id"), item.get("id"))}
            for item in self._line_items(order)
        ]
        status = str(
            first_value(
                order.get("orderFulfillmentStatus"),
                order.get("orderPaymentStatus"),
                order.get("cancelStatus", {}).get("cancelState") if isinstance(order.get("cancelStatus"), dict) else None,
                order.get("status"),
            )
            or ""
        )
        raw_payload = {
            **order,
            "id": order_id,
            "order_number": first_value(order.get("legacyOrderId"), order.get("salesRecordReference"), order_id),
            "site": self.marketplace_id,
            "created_at": order.get("creationDate"),
            "order_date": first_value(deep_get(order, "paymentSummary.payments.0.paymentDate"), order.get("creationDate")),
            "payment_at": deep_get(order, "paymentSummary.payments.0.paymentDate"),
            "shipping_deadline_at": first_value(*(deep_get(item, "lineItemFulfillmentInstructions.shipByDate") for item in self._line_items(order))),
            "buyer_selected_logistics": first_value(shipping_step.get("shippingServiceCode"), shipping_step.get("shippingCarrierCode")),
            "shipment_tracking_number": first_value(tracking.get("shipmentTrackingNumber"), tracking.get("trackingNumber")),
            "tracking_number": first_value(tracking.get("shipmentTrackingNumber"), tracking.get("trackingNumber")),
            "country_code": address.get("countryCode"),
            "buyer_name": first_value(ship_to.get("fullName"), deep_get(order, "buyer.username")),
            "order_amount": first_value(deep_get(order, "pricingSummary.total.value"), deep_get(order, "paymentSummary.totalDueSeller.value")),
            "currency_code": first_value(deep_get(order, "pricingSummary.total.currency"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("fulfillment_type"), "FBS"),
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("legacyOrderId"), order.get("salesRecordReference"), order_id)),
            posting_number=order_id,
            platform_status=status,
            fulfillment_type=str(raw_payload["fulfillment_type"]),
            is_overseas_warehouse=False,
            raw_payload=raw_payload,
        )

    async def _fetch_order(self, order_id: str) -> dict:
        path = str(self.settings.get("order_detail_path") or "/sell/fulfillment/v1/order/{order_id}").format(order_id=order_id)
        data = await self._get(path)
        payload = response_data(data)
        return payload if isinstance(payload, dict) else {}

    async def _fetch_fulfillments(self, order_id: str) -> list[dict]:
        if not bool(self.settings.get("fetch_shipping_fulfillments", True)):
            return []
        path = str(self.settings.get("shipping_fulfillments_path") or "/sell/fulfillment/v1/order/{order_id}/shipping_fulfillment").format(order_id=order_id)
        try:
            data = await self._get(path)
        except Exception:
            return []
        payload = response_data(data)
        if isinstance(payload, dict):
            return [item for item in as_list(first_value(payload.get("fulfillments"), payload.get("shippingFulfillments"))) if isinstance(item, dict)]
        return []

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = str(self.settings.get("orders_path") or "/sell/fulfillment/v1/order")
        limit = int(self.settings.get("limit") or self.settings.get("page_size") or 100)
        pull_filter = str(self.settings.get("pull_filter") or "orderfulfillmentstatus:{NOT_STARTED|IN_PROGRESS}")
        if since:
            created_from = iso_utc(since)
            pull_filter = f"{pull_filter},creationdate:[{created_from}..]"
        offset = 0
        orders: list[NormalizedOrder] = []
        while True:
            data = await self._get(path, {"filter": pull_filter, "limit": limit, "offset": offset})
            payload = response_data(data)
            rows = [item for item in as_list(payload.get("orders") if isinstance(payload, dict) else []) if isinstance(item, dict)]
            for row in rows:
                order_id = str(first_value(row.get("orderId"), row.get("id")) or "")
                detail = await self._fetch_order(order_id) if bool(self.settings.get("fetch_order_details", False)) and order_id else row
                fulfillments = await self._fetch_fulfillments(order_id) if order_id else []
                if fulfillments:
                    detail["fulfillments"] = fulfillments
                normalized = self._normalize_order(detail)
                if normalized:
                    orders.append(normalized)
            total = int(first_value(payload.get("total") if isinstance(payload, dict) else None, len(rows)) or 0)
            if len(rows) < limit or offset + len(rows) >= total:
                break
            offset += limit
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_order(order_id)
            fulfillments = await self._fetch_fulfillments(order_id)
            if fulfillments:
                detail["fulfillments"] = fulfillments
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
        carrier = str(first_value(self.settings.get("shipping_carrier_code"), self.settings.get("carrier_code"), order.raw_payload.get("buyer_selected_logistics"), "OTHER"))
        if self._dry_run():
            return ShipmentResult(order.platform_order_id, tracking_number, carrier, "dry_run_created", order.raw_payload)
        path = str(self.settings.get("create_shipping_fulfillment_path") or "/sell/fulfillment/v1/order/{order_id}/shipping_fulfillment").format(order_id=order.platform_order_id)
        line_items = [
            {"lineItemId": item.get("line_item_id"), "quantity": int(item.get("quantity") or 1)}
            for item in as_list(order.raw_payload.get("products") or order.raw_payload.get("items"))
            if isinstance(item, dict) and item.get("line_item_id")
        ]
        payload = dict(self.settings.get("shipping_fulfillment_payload_template") or {})
        payload.setdefault("lineItems", line_items)
        payload.setdefault("shippedDate", datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        payload.setdefault("shippingCarrierCode", carrier)
        payload.setdefault("trackingNumber", tracking_number)
        data = await self._post(path, payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("fulfillmentId"), raw.get("shippingFulfillmentId"), order.platform_order_id)),
            tracking_number=str(first_value(raw.get("shipmentTrackingNumber"), raw.get("trackingNumber"), tracking_number)),
            carrier=str(first_value(raw.get("shippingCarrierCode"), carrier)),
            status=str(first_value(raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("eBay Label Preview", shipment, order)
        if str(self.settings.get("label_mode") or "unsupported").lower() == "unsupported":
            raise NotImplementedError("eBay Sell Fulfillment API does not provide marketplace label download by default")
        path = str(self.settings.get("label_path") or "")
        if not path:
            raise ValueError("eBay label_path is required when label_mode is not unsupported")
        data = await self._get(path.format(shipment_id=shipment.platform_shipment_id, order_id=order.platform_order_id), binary=True)
        return label_from_platform_response(data)
