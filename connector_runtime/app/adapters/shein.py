import base64
import hashlib
import hmac
import random
import string
from datetime import datetime, timedelta, timezone

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .marketplace_common import (
    DryRunFulfillmentMixin,
    LoggedHttpMixin,
    as_list,
    deep_get,
    first_value,
    label_from_platform_response,
    product_payload,
    response_data,
)


class SheinConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = "shein"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.open_key_id = str(
            first_value(
                self.credentials.get("open_key_id"),
                self.credentials.get("openKeyId"),
                self.credentials.get("open_key"),
                self.credentials.get("app_id"),
            )
            or ""
        )
        self.secret_key = str(
            first_value(
                self.credentials.get("secret_key"),
                self.credentials.get("secretKey"),
                self.credentials.get("app_secret"),
                self.credentials.get("client_secret"),
            )
            or ""
        )
        self.seller_id = str(first_value(self.credentials.get("seller_id"), self.settings.get("account_id")) or "")
        self.base_url = str(self.settings.get("base_url") or "https://openapi.sheincorp.com").rstrip("/")
        self.account_id = str(self.settings.get("account_id") or self.seller_id or self.open_key_id)

    @staticmethod
    def _random_key(length: int = 5) -> str:
        return "".join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

    def _signature(self, path: str, timestamp_ms: str, random_key: str) -> str:
        if not (self.open_key_id and self.secret_key):
            raise ValueError("SHEIN open_key_id and secret_key are required")
        value = f"{self.open_key_id}&{timestamp_ms}&{path}"
        key = f"{self.secret_key}{random_key}"
        digest_hex = hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()
        return random_key + base64.b64encode(digest_hex.encode("utf-8")).decode("ascii")

    def _headers(self, path: str) -> dict:
        timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1000))
        random_key = str(self.settings.get("signature_random_key") or self._random_key())
        return {
            "Content-Type": "application/json",
            "language": str(self.settings.get("language") or "en"),
            "x-lt-openKeyId": self.open_key_id,
            "x-lt-timestamp": timestamp,
            "x-lt-signature": self._signature(path, timestamp, random_key),
        }

    async def _post(self, path: str, payload: dict | None = None, *, binary: bool = False):
        return await self._request(
            "POST",
            f"{self.base_url}{path}",
            headers=self._headers(path),
            json_body=payload or {},
            binary=binary,
            timeout=90,
        )

    def _payload(self, data) -> dict:
        payload = response_data(data)
        if isinstance(payload, dict):
            info = payload.get("info")
            if isinstance(info, dict):
                return info
            return payload
        return {}

    @staticmethod
    def _items(order: dict) -> list[dict]:
        rows: list[dict] = []
        for key in (
            "goodsList",
            "goods_list",
            "productList",
            "product_list",
            "itemList",
            "item_list",
            "orderGoodsList",
            "order_goods_list",
            "skuList",
            "sku_list",
            "products",
            "items",
        ):
            rows.extend(item for item in as_list(order.get(key)) if isinstance(item, dict))
        return rows

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        order_id = str(
            first_value(
                order.get("orderNo"),
                order.get("order_no"),
                order.get("orderNumber"),
                order.get("order_number"),
                order.get("order_id"),
                order.get("id"),
            )
            or ""
        )
        if not order_id:
            return None
        package = first_value(order.get("packageInfo"), order.get("package"), order.get("shipment"), {})
        package = package if isinstance(package, dict) else {}
        shipping = first_value(order.get("shipping"), order.get("shippingInfo"), order.get("receiver"), {})
        shipping = shipping if isinstance(shipping, dict) else {}
        products = [
            product_payload(
                item,
                sku_keys=("sellerSku", "seller_sku", "supplierSku", "skuCode", "sku_code", "sku", "goodsSn", "goods_sn"),
                name_keys=("goodsName", "goods_name", "productName", "product_name", "name", "title"),
                quantity_keys=("quantity", "qty", "goodsQuantity", "goods_quantity", "productCount", "product_count"),
                price_keys=("price.amount", "price", "salePrice", "sale_price", "paidPrice", "paid_price"),
                currency_keys=("price.currency", "currency", "currencyCode", "currency_code"),
            )
            for item in self._items(order)
        ]
        tracking = first_value(
            order.get("trackingNumber"),
            order.get("tracking_number"),
            order.get("waybillNumber"),
            order.get("waybill_number"),
            package.get("trackingNumber"),
            package.get("tracking_number"),
            package.get("waybillNumber"),
            package.get("waybill_number"),
        )
        package_id = str(
            first_value(
                package.get("packageNo"),
                package.get("package_no"),
                package.get("packageId"),
                package.get("package_id"),
                order.get("packageNo"),
                order.get("package_no"),
                order.get("shipmentNo"),
                order.get("shipment_no"),
                tracking,
                order_id,
            )
            or ""
        )
        status = str(
            first_value(
                order.get("orderStatus"),
                order.get("order_status"),
                order.get("status"),
                package.get("status"),
            )
            or ""
        )
        fulfillment_type = str(first_value(order.get("fulfillmentType"), order.get("fulfillment_type"), order.get("businessMode"), "FBS"))
        raw_payload = {
            **order,
            "id": order_id,
            "order_number": first_value(order.get("orderNo"), order.get("order_number"), order_id),
            "package_id": package_id,
            "site": first_value(self.settings.get("region"), order.get("site"), order.get("siteName"), "shein"),
            "created_at": first_value(order.get("createdAt"), order.get("createTime"), order.get("created_time"), order.get("orderTime")),
            "order_date": first_value(order.get("paidAt"), order.get("payTime"), order.get("orderTime"), order.get("createdAt")),
            "payment_at": first_value(order.get("paidAt"), order.get("payTime"), order.get("paymentTime")),
            "shipping_deadline_at": first_value(order.get("latestShipTime"), order.get("shipByTime"), order.get("deliveryDeadline"), package.get("latestShipTime")),
            "buyer_selected_logistics": first_value(order.get("logisticsService"), order.get("shippingService"), package.get("logisticsService")),
            "shipment_tracking_number": tracking,
            "tracking_number": tracking,
            "country_code": first_value(shipping.get("countryCode"), shipping.get("country_code"), order.get("countryCode"), order.get("country_code")),
            "buyer_name": first_value(shipping.get("name"), shipping.get("receiverName"), shipping.get("receiver_name")),
            "order_amount": first_value(deep_get(order, "orderAmount.amount"), order.get("orderAmount"), order.get("totalAmount")),
            "currency_code": first_value(deep_get(order, "orderAmount.currency"), order.get("currency"), order.get("currencyCode"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": fulfillment_type,
        }
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(first_value(order.get("orderNo"), order.get("order_number"), order_id)),
            posting_number=package_id,
            platform_status=status,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type.upper() in {"FULL", "FULL_MANAGED", "SEMI_MANAGED", "SHEIN_FULFILLMENT", "FBS_SHEIN"},
            raw_payload=raw_payload,
        )

    async def _fetch_order_detail(self, order_id: str) -> dict:
        path = str(self.settings.get("order_detail_path") or "/open-api/order/purchase-order-info")
        payload = dict(self.settings.get("order_detail_payload_template") or {})
        payload.setdefault(str(self.settings.get("order_id_field") or "orderNo"), order_id)
        data = await self._post(path, payload)
        result = self._payload(data)
        detail = first_value(result.get("data"), result.get("order"), result.get("orderInfo"), result)
        return detail if isinstance(detail, dict) else result

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = str(self.settings.get("order_list_path") or "/open-api/order/order-list")
        statuses = self.settings.get("pull_statuses") or self.settings.get("pull_order_statuses") or ["WAITING_SHIPMENT", "PENDING_SHIPMENT", "TO_BE_SHIPPED"]
        page = int(self.settings.get("page") or 1)
        page_size = int(self.settings.get("page_size") or 50)
        max_pages = int(self.settings.get("max_pages") or 20)
        since = since or (datetime.now(timezone.utc) - timedelta(days=int(self.settings.get("lookback_days") or 7)))
        orders: list[NormalizedOrder] = []
        for status in as_list(statuses):
            current_page = page
            for _ in range(max_pages):
                payload = dict(self.settings.get("order_list_payload_template") or {})
                payload.setdefault(str(self.settings.get("status_field") or "orderStatus"), status)
                payload.setdefault(str(self.settings.get("page_field") or "page"), current_page)
                payload.setdefault(str(self.settings.get("page_size_field") or "pageSize"), page_size)
                payload.setdefault(str(self.settings.get("start_time_field") or "startTime"), since.replace(microsecond=0).isoformat())
                payload.setdefault(str(self.settings.get("end_time_field") or "endTime"), datetime.now(timezone.utc).replace(microsecond=0).isoformat())
                data = await self._post(path, payload)
                result = self._payload(data)
                rows = []
                for key in ("data", "list", "orderList", "order_list", "orders", "items"):
                    rows.extend(item for item in as_list(result.get(key)) if isinstance(item, dict))
                if not rows:
                    break
                for row in rows:
                    order_id = str(first_value(row.get("orderNo"), row.get("order_no"), row.get("order_id"), row.get("id")) or "")
                    detail = await self._fetch_order_detail(order_id) if bool(self.settings.get("fetch_order_details", False)) and order_id else row
                    normalized = self._normalize_order({**row, **detail})
                    if normalized:
                        orders.append(normalized)
                if len(rows) < page_size:
                    break
                current_page += 1
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for order_id in [str(value).strip() for value in posting_numbers if str(value or "").strip()]:
            detail = await self._fetch_order_detail(order_id)
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
        carrier = str(first_value(self.settings.get("carrier_code"), self.settings.get("carrier_name"), order.raw_payload.get("buyer_selected_logistics"), "Seller Shipping"))
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, tracking_number, carrier, "dry_run_created", order.raw_payload)
        path = str(self.settings.get("ship_path") or "/open-api/order/import-batch-multiple-express")
        payload = dict(self.settings.get("ship_payload_template") or {})
        shipment = {
            str(self.settings.get("ship_order_id_field") or "orderNo"): order.platform_order_id,
            str(self.settings.get("ship_package_id_field") or "packageNo"): order.posting_number or order.platform_order_id,
            str(self.settings.get("tracking_number_field") or "trackingNumber"): tracking_number,
            str(self.settings.get("carrier_field") or "expressCode"): carrier,
        }
        payload.setdefault(str(self.settings.get("ship_list_field") or "orderList"), [shipment])
        data = await self._post(path, payload)
        raw = self._payload(data)
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("packageNo"), raw.get("package_id"), order.posting_number, order.platform_order_id)),
            tracking_number=str(first_value(raw.get("trackingNumber"), raw.get("tracking_number"), tracking_number)),
            carrier=str(first_value(raw.get("expressCode"), raw.get("carrier"), carrier)),
            status=str(first_value(raw.get("status"), raw.get("msg"), "created")),
            raw_payload=raw,
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("SHEIN Label Preview", shipment, order)
        if str(self.settings.get("label_mode") or "requires_shein_fulfill_confirmation").lower() in {"unsupported", "requires_shein_fulfill_confirmation"} and not self.settings.get("label_path"):
            raise NotImplementedError("SHEIN label download requires a confirmed label_path for the store fulfillment mode")
        path = str(self.settings.get("label_path") or "")
        if not path:
            raise ValueError("SHEIN label_path is required")
        payload = dict(self.settings.get("label_payload_template") or {})
        payload.setdefault(str(self.settings.get("order_id_field") or "orderNo"), order.platform_order_id)
        payload.setdefault(str(self.settings.get("package_id_field") or "packageNo"), shipment.platform_shipment_id or order.posting_number)
        data = await self._post(path, payload, binary=bool(self.settings.get("label_binary_response", False)))
        return label_from_platform_response(data)
