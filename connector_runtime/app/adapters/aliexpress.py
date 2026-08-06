# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from datetime import datetime

from .alibaba_common import AlibabaTopConnector
from .base import LabelResult, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    as_list,
    deep_get,
    extract_items,
    first_value,
    label_from_platform_response,
    product_payload,
    response_data,
)


class AliExpressConnector(AlibabaTopConnector):
    platform = "aliexpress"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        super().__init__(credentials, settings)
        if not self.base_url:
            self.base_url = "https://api-sg.aliexpress.com/sync"

    @staticmethod
    def _order_items(order: dict) -> list[dict]:
        return extract_items(order, "child_order_list", "child_order_list.child_order", "order_items", "items", "products")

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("order_id"), order.get("id"), order.get("orderId")) or "")
        if not order_id:
            return None
        logistics = first_value(order.get("logistics"), order.get("logistics_info"), order.get("shipment"), {})
        logistics = logistics if isinstance(logistics, dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("sku_code", "product_sku", "seller_sku", "sku", "product_id"),
                name_keys=("product_name", "productName", "name", "product_title"),
                quantity_keys=("product_count", "quantity", "qty", "product_quantity"),
                price_keys=("product_price.amount", "product_price", "price.amount", "price"),
                currency_keys=("product_price.currency", "price.currency", "currency_code", "currency"),
            )
            for item in self._order_items(order)
        ]
        tracking = first_value(
            order.get("logistics_no"),
            order.get("tracking_no"),
            order.get("tracking_number"),
            logistics.get("logistics_no"),
            logistics.get("tracking_no"),
            logistics.get("tracking_number"),
        )
        raw_payload = {
            **order,
            "id": order_id,
            "site": first_value(self.settings.get("region"), order.get("country"), "aliexpress"),
            "created_at": first_value(order.get("gmt_create"), order.get("create_time")),
            "order_date": first_value(order.get("gmt_pay_time"), order.get("pay_time"), order.get("gmt_create")),
            "payment_at": first_value(order.get("gmt_pay_time"), order.get("pay_time")),
            "shipping_deadline_at": first_value(order.get("send_goods_time"), order.get("shipment_deadline"), order.get("delivery_deadline")),
            "buyer_selected_logistics": first_value(order.get("logistics_service_name"), order.get("logistics_service"), logistics.get("service_name"), logistics.get("service_code")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": first_value(order.get("country_code"), deep_get(order, "receipt_address.country_code"), deep_get(order, "buyer_info.country_code")),
            "order_amount": first_value(deep_get(order, "order_amount.amount"), order.get("order_amount"), order.get("total_amount")),
            "currency_code": first_value(deep_get(order, "order_amount.currency"), order.get("currency_code"), order.get("currency"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("fulfillment_type"), "FBS"),
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=order_id,
            posting_number=str(first_value(tracking, order.get("logistics_no"), order_id)),
            platform_status=str(first_value(order.get("order_status"), order.get("status")) or ""),
            fulfillment_type=str(raw_payload["fulfillment_type"]),
            is_overseas_warehouse=False,
            raw_payload=raw_payload,
        )

    async def _fetch_detail(self, order_id: str) -> dict:
        method = str(self.settings.get("order_detail_method") or "aliexpress.trade.redefining.findorderbyid")
        id_key = str(self.settings.get("order_detail_id_key") or "order_id")
        data = await self._top_post(method, {id_key: order_id})
        payload = response_data(data)
        if isinstance(payload, dict):
            return payload.get("order") if isinstance(payload.get("order"), dict) else payload
        return {}

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        method = str(self.settings.get("order_list_method") or "aliexpress.trade.redefining.findorderlistsimplequery")
        statuses = list(self.settings.get("pull_order_statuses") or ["PLACE_ORDER_SUCCESS", "WAIT_SELLER_SEND_GOODS"])
        page_size = int(self.settings.get("page_size") or 50)
        max_pages = int(self.settings.get("max_pages") or 20)
        orders: list[NormalizedOrder] = []
        for status in statuses:
            for page in range(1, max_pages + 1):
                params = {
                    "order_status": status,
                    "page_size": page_size,
                    "current_page": page,
                    **self._timestamp_filter(since, "gmt_create_start", "gmt_create_end"),
                }
                data = await self._top_post(method, params)
                payload = response_data(data)
                rows = extract_items(payload if isinstance(payload, dict) else {}, "order_list", "orders", "result.orders")
                if not rows:
                    break
                for row in rows:
                    detail = await self._fetch_detail(str(first_value(row.get("order_id"), row.get("id")) or "")) if bool(self.settings.get("fetch_order_details", True)) else row
                    normalized = self._normalize_order({**row, **detail})
                    if normalized:
                        orders.append(normalized)
                if len(rows) < page_size:
                    break
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_detail(order_id)
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
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, str(order.raw_payload.get("tracking_number") or order.posting_number or order.platform_order_id), "AliExpress", "dry_run_created", order.raw_payload)
        method = str(self.settings.get("shipment_method") or "aliexpress.logistics.redefining.sellershipmentfortop")
        payload = {
            "out_ref": order.platform_order_id,
            "send_type": self.settings.get("send_type", "all"),
            "logistics_no": first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), ""),
            "service_name": self.settings.get("service_name", ""),
            **dict(self.settings.get("shipment_payload_template") or {}),
        }
        data = await self._top_post(method, payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("logistics_no"), payload.get("logistics_no"), order.platform_order_id)),
            tracking_number=str(first_value(raw.get("logistics_no"), payload.get("logistics_no"), order.platform_order_id)),
            carrier=str(first_value(raw.get("service_name"), payload.get("service_name"), "AliExpress")),
            status=str(first_value(raw.get("result"), raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("AliExpress Label Preview", shipment, order)
        method = str(self.settings.get("label_method") or "aliexpress.logistics.redefining.getprintinfo")
        params = {
            "order_id": order.platform_order_id,
            "logistics_no": first_value(shipment.tracking_number, order.raw_payload.get("tracking_number"), order.posting_number),
            **dict(self.settings.get("label_payload_template") or {}),
        }
        data = await self._top_post(method, params, binary=bool(self.settings.get("label_binary_response", False)))
        return label_from_platform_response(data)
