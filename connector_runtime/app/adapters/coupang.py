# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import hashlib
import hmac
from datetime import datetime, timedelta, timezone

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    canonical_query,
    deep_get,
    first_value,
    label_from_platform_response,
    product_payload,
    response_data,
)


class CoupangConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "coupang"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.access_key = str(first_value(self.credentials.get("access_key"), self.credentials.get("accessKey")) or "")
        self.secret_key = str(first_value(self.credentials.get("secret_key"), self.credentials.get("secretKey")) or "")
        self.vendor_id = str(first_value(self.credentials.get("vendor_id"), self.credentials.get("vendorId"), self.settings.get("vendor_id"), self.settings.get("account_id")) or "")
        self.base_url = str(self.settings.get("base_url") or "https://api-gateway.coupang.com").rstrip("/")
        self.market = str(self.settings.get("market") or "KR")
        self.account_id = str(self.settings.get("account_id") or self.vendor_id)

    @staticmethod
    def _signed_date() -> str:
        return datetime.now(timezone.utc).strftime("%y%m%dT%H%M%SZ")

    def _authorization(self, method: str, path: str, params: dict | None = None) -> str:
        if not (self.access_key and self.secret_key):
            raise ValueError("Coupang access_key and secret_key are required")
        signed_date = self._signed_date()
        query = canonical_query(params or {})
        message = f"{signed_date}{method.upper()}{path}{query}"
        signature = hmac.new(self.secret_key.encode("utf-8"), message.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"CEA algorithm=HmacSHA256, access-key={self.access_key}, signed-date={signed_date}, signature={signature}"

    async def _request_coupang(self, method: str, path: str, *, params: dict | None = None, payload: dict | list | None = None, binary: bool = False):
        headers = {
            "Authorization": self._authorization(method, path, params),
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json",
        }
        return await self._request(
            method,
            f"{self.base_url}{path}",
            headers=headers,
            params=params,
            json_body=payload if method.upper() in {"POST", "PUT", "PATCH"} else None,
            binary=binary,
            timeout=90,
        )

    def _path(self, key: str, default: str, **values) -> str:
        if not self.vendor_id:
            raise ValueError("Coupang vendor_id is required")
        return str(self.settings.get(key) or default).format(vendor_id=self.vendor_id, vendorId=self.vendor_id, **values)

    @staticmethod
    def _items(order: dict) -> list[dict]:
        rows: list[dict] = []
        for key in ("orderItems", "order_items", "items", "products", "orderSheetItems"):
            rows.extend(item for item in as_list(order.get(key)) if isinstance(item, dict))
        return rows

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(first_value(order.get("orderId"), order.get("order_id"), order.get("id")) or "")
        shipment_box_id = str(first_value(order.get("shipmentBoxId"), order.get("shipment_box_id"), order.get("bundleShipmentId"), order_id) or "")
        if not order_id and not shipment_box_id:
            return None
        receiver = order.get("receiver") if isinstance(order.get("receiver"), dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("sellerProductItemId", "seller_product_item_id", "vendorItemId", "vendor_item_id", "externalVendorSku", "sku", "seller_sku"),
                name_keys=("vendorItemName", "sellerProductName", "sellerProductItemName", "productName", "name"),
                quantity_keys=("shippingCount", "quantity", "qty", "orderCount"),
                price_keys=("salesPrice", "orderPrice", "price", "unitPrice"),
                currency_keys=("currency", "currencyCode", "currency_code"),
            )
            for item in self._items(order)
        ]
        status = str(first_value(order.get("status"), order.get("orderStatus"), order.get("deliveryStatus")) or "")
        tracking = first_value(order.get("invoiceNumber"), order.get("invoice_number"), order.get("trackingNumber"), order.get("tracking_number"))
        raw_payload = {
            **order,
            "id": order_id or shipment_box_id,
            "order_number": first_value(order.get("orderId"), order_id, shipment_box_id),
            "shipment_box_id": shipment_box_id,
            "site": self.market,
            "created_at": first_value(order.get("orderedAt"), order.get("paidAt"), order.get("createdAt")),
            "order_date": first_value(order.get("orderedAt"), order.get("paidAt"), order.get("createdAt")),
            "payment_at": first_value(order.get("paidAt"), order.get("orderedAt")),
            "shipping_deadline_at": first_value(order.get("shipmentDueDate"), order.get("shippingDueDate"), order.get("deliverByDate")),
            "buyer_selected_logistics": first_value(order.get("deliveryCompanyName"), order.get("deliveryCompanyCode"), order.get("shippingType")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": first_value(receiver.get("countryCode"), receiver.get("country_code"), self.market),
            "buyer_name": first_value(receiver.get("name"), receiver.get("receiverName")),
            "order_amount": first_value(order.get("orderAmount"), order.get("totalPrice"), *(item.get("price") for item in products)),
            "currency_code": first_value(order.get("currency"), order.get("currencyCode"), *(item.get("currency_code") for item in products), "KRW"),
            "products": products,
            "items": products,
            "fulfillment_type": first_value(order.get("fulfillmentType"), order.get("shipmentType"), "FBS"),
        }
        return NormalizedOrder(
            platform_order_id=order_id or shipment_box_id,
            platform_order_no=str(first_value(order.get("orderId"), order_id, shipment_box_id)),
            posting_number=shipment_box_id or order_id,
            platform_status=status,
            fulfillment_type=str(raw_payload["fulfillment_type"]),
            is_overseas_warehouse=str(raw_payload["fulfillment_type"]).upper() in {"ROCKET", "CGF", "COUPANG_FULFILLMENT"},
            raw_payload=raw_payload,
        )

    @staticmethod
    def _date_param(value: datetime) -> str:
        if value.tzinfo:
            value = value.astimezone(timezone(timedelta(hours=9)))
        return value.strftime("%Y-%m-%dT%H:%M+09:00")

    async def _fetch_detail(self, posting_number: str, *, by_order_id: bool = False) -> dict:
        if by_order_id:
            path = self._path("order_detail_by_order_id_path", "/v2/providers/openapi/apis/api/v5/vendors/{vendor_id}/{order_id}/ordersheets", order_id=posting_number)
        else:
            path = self._path("order_detail_path", "/v2/providers/openapi/apis/api/v5/vendors/{vendor_id}/ordersheets/{shipment_box_id}", shipment_box_id=posting_number)
        data = await self._request_coupang("GET", path)
        payload = response_data(data)
        detail = payload.get("data") if isinstance(payload, dict) else payload
        if isinstance(detail, list):
            return detail[0] if detail and isinstance(detail[0], dict) else {}
        return detail if isinstance(detail, dict) else {}

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = self._path("orders_path", "/v2/providers/openapi/apis/api/v5/vendors/{vendor_id}/ordersheets")
        statuses = self.settings.get("pull_statuses") or self.settings.get("pull_order_statuses") or ["ACCEPT", "INSTRUCT"]
        now = datetime.now(timezone(timedelta(hours=9)))
        since = since or (now - timedelta(days=int(self.settings.get("lookback_days") or 1)))
        orders: list[NormalizedOrder] = []
        for status in as_list(statuses):
            params = {
                "createdAtFrom": self._date_param(since),
                "createdAtTo": self._date_param(now),
                "status": status,
                "maxPerPage": int(self.settings.get("max_per_page") or self.settings.get("page_size") or 50),
                **dict(self.settings.get("orders_params") or {}),
            }
            if bool(self.settings.get("search_by_minute", True)):
                params.setdefault("searchType", "timeFrame")
            while True:
                data = await self._request_coupang("GET", path, params=params)
                payload = response_data(data)
                rows = [item for item in (payload if isinstance(payload, list) else as_list(payload.get("data") if isinstance(payload, dict) else [])) if isinstance(item, dict)]
                for row in rows:
                    posting = str(first_value(row.get("shipmentBoxId"), row.get("shipment_box_id")) or "")
                    detail = await self._fetch_detail(posting) if bool(self.settings.get("fetch_order_details", False)) and posting else row
                    if status == "ACCEPT" and bool(self.settings.get("auto_acknowledge_orders", False)) and posting:
                        await self._acknowledge([posting])
                    normalized = self._normalize_order({**row, **detail})
                    if normalized:
                        orders.append(normalized)
                next_token = payload.get("nextToken") if isinstance(payload, dict) else ""
                if not next_token:
                    break
                params = {"nextToken": next_token}
        return orders

    async def _acknowledge(self, shipment_box_ids: list[str]) -> None:
        path = self._path("acknowledge_path", "/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/ordersheets/acknowledgement")
        payload = {"vendorId": self.vendor_id, "shipmentBoxIds": [int(item) if str(item).isdigit() else item for item in shipment_box_ids]}
        await self._request_coupang(str(self.settings.get("acknowledge_method") or "PATCH"), path, payload=payload)

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for posting in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_detail(posting)
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
        tracking_number = str(first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), self.settings.get("tracking_number"), order.posting_number) or "")
        carrier = str(first_value(self.settings.get("delivery_company_code"), self.settings.get("carrier_code"), order.raw_payload.get("buyer_selected_logistics"), ""))
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, tracking_number, carrier or "Coupang", "dry_run_created", order.raw_payload)
        path = self._path("invoice_path", "/v2/providers/openapi/apis/api/v4/vendors/{vendor_id}/orders/invoices")
        shipment_box_id = order.posting_number or order.raw_payload.get("shipment_box_id") or order.platform_order_id
        row = {
            "shipmentBoxId": int(shipment_box_id) if str(shipment_box_id).isdigit() else shipment_box_id,
            "invoiceNumber": tracking_number,
        }
        if carrier:
            row["deliveryCompanyCode"] = carrier
        payload = dict(self.settings.get("invoice_payload_template") or {})
        payload.setdefault("vendorId", self.vendor_id)
        payload.setdefault("orderSheetInvoiceApplyDtos", [row])
        data = await self._request_coupang("POST", path, payload=payload)
        raw = response_data(data) if isinstance(data, dict) else {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("shipmentBoxId"), shipment_box_id)),
            tracking_number=str(first_value(raw.get("invoiceNumber"), tracking_number)),
            carrier=str(first_value(raw.get("deliveryCompanyCode"), carrier, "Coupang")),
            status=str(first_value(raw.get("message"), raw.get("status"), "created")),
            raw_payload=raw if isinstance(raw, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("Coupang Label Preview", shipment, order)
        if str(self.settings.get("label_mode") or "unsupported").lower() == "unsupported":
            raise NotImplementedError("Coupang seller shipment label download is not available by default")
        path = str(self.settings.get("label_path") or "")
        if not path:
            raise ValueError("Coupang label_path is required when label_mode is not unsupported")
        data = await self._request_coupang("GET", path.format(vendor_id=self.vendor_id, shipment_id=shipment.platform_shipment_id, order_id=order.platform_order_id), binary=True)
        return label_from_platform_response(data)
