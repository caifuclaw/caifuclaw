import base64
import re
from datetime import datetime, timezone
from typing import Any

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
    normalize_currency,
    normalize_fulfillment_type,
    normalize_money,
    product_payload,
    response_data,
)


DMSMATRIX_CATALOG_MAIN_IMAGE_KEYS = (
    "main_image_url",
    "mainImageUrl",
    "MainImageUrl",
    "MainImageURL",
    "main_image",
    "mainImage",
    "MainImage",
    "image_url",
    "imageUrl",
    "ImageUrl",
    "ImageURL",
    "ProductImageUrl",
    "ProductImageURL",
    "ItemImageUrl",
    "ItemImageURL",
    "PictureUrl",
    "PictureURL",
    "PhotoUrl",
    "PhotoURL",
    "thumbnail_url",
    "thumbnailUrl",
    "ThumbnailUrl",
    "cover_url",
    "coverUrl",
)
DMSMATRIX_CATALOG_IMAGE_LIST_KEYS = (
    "images",
    "Images",
    "image_urls",
    "imageUrls",
    "ImageUrls",
    "pictures",
    "Pictures",
    "photos",
    "Photos",
    "media",
    "Media",
    "gallery_image_urls",
    "galleryImageUrls",
)
DMSMATRIX_CATALOG_IMAGE_VALUE_KEYS = (
    "url",
    "Url",
    "URL",
    "src",
    "Src",
    "source",
    "Source",
    "href",
    "Href",
    "link",
    "Link",
    "original",
    "Original",
    "large",
    "Large",
)
DMSMATRIX_CATALOG_IMAGE_CONTAINER_KEYS = ("product", "item", "listing", "payload", "raw_payload")


def _dmsmatrix_image_url_from_value(value: Any, depth: int = 0) -> str:
    if value in (None, "") or depth > 3:
        return ""
    if isinstance(value, str):
        for part in re.split(r"[\s,;|]+", value.strip()):
            normalized = part.lower()
            if normalized.startswith(("http://", "https://", "//", "/api/")):
                return part
        return ""
    if isinstance(value, (list, tuple, set)):
        for item in value:
            image_url = _dmsmatrix_image_url_from_value(item, depth + 1)
            if image_url:
                return image_url
        return ""
    if isinstance(value, dict):
        for key in DMSMATRIX_CATALOG_IMAGE_VALUE_KEYS:
            image_url = _dmsmatrix_image_url_from_value(value.get(key), depth + 1)
            if image_url:
                return image_url
        return ""
    return ""


def _dmsmatrix_catalog_main_image_url(row: dict) -> str:
    for key in DMSMATRIX_CATALOG_MAIN_IMAGE_KEYS:
        image_url = _dmsmatrix_image_url_from_value(deep_get(row, key))
        if image_url:
            return image_url
    for key in DMSMATRIX_CATALOG_IMAGE_LIST_KEYS:
        image_url = _dmsmatrix_image_url_from_value(deep_get(row, key))
        if image_url:
            return image_url
    for key in DMSMATRIX_CATALOG_IMAGE_CONTAINER_KEYS:
        nested = row.get(key)
        if isinstance(nested, dict):
            image_url = _dmsmatrix_catalog_main_image_url(nested)
            if image_url:
                return image_url
    return ""


class DMSMatrixConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    """DMSMatrix adapter with configurable endpoint overrides."""

    platform = "dmsmatrix"
    DEFAULT_ORDERS_PATH = "/Order/getOrders"
    DEFAULT_ORDERS_METHOD = "POST"
    DEFAULT_PAGE_SIZE = 50

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.api_key = str(first_value(self.credentials.get("api_key"), self.credentials.get("access_token")) or "")
        self.client_name = str(self.credentials.get("client_name") or "")
        self.client_id = str(self.credentials.get("client_id") or "")
        self.client_secret = str(self.credentials.get("client_secret") or "")
        self.channel_code = str(self.credentials.get("channel_code") or "")
        self.account_id = str(first_value(self.settings.get("account_id"), self.credentials.get("account_id"), self.credentials.get("seller_id")) or "")
        self.base_url = str(self.settings.get("base_url") or "https://api.dmsmatrix.net/apis").rstrip("/")

    def _credential_header_names(self) -> dict[str, str]:
        configured = self.settings.get("credential_headers") if isinstance(self.settings.get("credential_headers"), dict) else {}
        return {
            "client_name": str(configured.get("client_name") or self.settings.get("client_name_header") or "Client-Name"),
            "client_id": str(configured.get("client_id") or self.settings.get("client_id_header") or "Client-Id"),
            "client_secret": str(configured.get("client_secret") or self.settings.get("client_secret_header") or "Client-Secret"),
            "channel_code": str(configured.get("channel_code") or self.settings.get("channel_code_header") or "Channel-Code"),
        }

    def _headers(self) -> dict:
        headers = dict(self.settings.get("headers") or {})
        headers.setdefault("Accept", "application/json")
        headers.setdefault("Content-Type", "application/json")
        if self.api_key:
            auth_scheme = str(self.settings.get("auth_scheme") or "Bearer").strip()
            if auth_scheme.lower() in {"none", "raw"}:
                headers.setdefault("Authorization", self.api_key)
            else:
                headers.setdefault("Authorization", f"{auth_scheme} {self.api_key}")
        api_key_header = str(self.settings.get("api_key_header") or "").strip()
        if api_key_header and self.api_key:
            headers.setdefault(api_key_header, self.api_key)
        credential_headers = self._credential_header_names()
        for key, value in (
            ("client_name", self.client_name),
            ("client_id", self.client_id),
            ("client_secret", self.client_secret),
            ("channel_code", self.channel_code),
        ):
            header_name = credential_headers.get(key, "").strip()
            if header_name and value:
                headers.setdefault(header_name, value)
        tenant_header = str(self.settings.get("tenant_header") or "").strip()
        if tenant_header and self.account_id:
            headers.setdefault(tenant_header, self.account_id)
        return headers

    def _url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"

    async def _get(self, path: str, params: dict | None = None, *, binary: bool = False) -> dict | bytes:
        return await self._request("GET", self._url(path), headers=self._headers(), params=params, binary=binary)

    async def _post(self, path: str, payload: dict | None = None, *, binary: bool = False) -> dict | bytes:
        return await self._request("POST", self._url(path), headers=self._headers(), json_body=payload or {}, binary=binary)

    @staticmethod
    def _path_values(order: NormalizedOrder | dict, shipment: ShipmentResult | None = None) -> dict[str, Any]:
        if isinstance(order, NormalizedOrder):
            raw = order.raw_payload or {}
            values: dict[str, Any] = {
                "order_id": order.platform_order_id,
                "platform_order_id": order.platform_order_id,
                "order_no": order.platform_order_no,
                "platform_order_no": order.platform_order_no,
                "posting_number": order.posting_number,
            }
        else:
            raw = order
            values = {}
        values.update(
            {
                "shipment_id": first_value(
                    shipment.platform_shipment_id if shipment else None,
                    raw.get("shipment_id"),
                    raw.get("shipmentId"),
                    raw.get("package_id"),
                    raw.get("packageId"),
                    raw.get("label_id"),
                    raw.get("labelId"),
                ),
                "tracking_number": first_value(
                    shipment.tracking_number if shipment else None,
                    raw.get("tracking_number"),
                    raw.get("trackingNumber"),
                    raw.get("shipment_tracking_number"),
                ),
            }
        )
        return values

    @staticmethod
    def _format_path(path: str, values: dict[str, Any]) -> str:
        class Missing(dict):
            def __missing__(self, key):
                return ""

        return path.format_map(Missing({key: "" if value is None else value for key, value in values.items()}))

    @staticmethod
    def _decode_label_data(value: str) -> bytes | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.startswith("data:") and "," in text:
            text = text.split(",", 1)[1].strip()
        if text.startswith("%PDF"):
            return text.encode("utf-8")
        try:
            return base64.b64decode("".join(text.split()))
        except Exception:
            return None

    @classmethod
    def _label_result_from_payload(cls, payload) -> LabelResult | None:
        body = response_data(payload)
        roots = body if isinstance(body, list) else [body]
        if isinstance(body, dict):
            data = first_value(body.get("Data"), body.get("data"))
            if isinstance(data, list):
                roots = [*roots, *data]
            elif isinstance(data, dict):
                roots = [*roots, data]
        for root in roots:
            if not isinstance(root, dict):
                continue
            for label in cls._label_candidates(root):
                data = first_value(label.get("Data"), label.get("data"), label.get("Content"), label.get("content"))
                content = cls._decode_label_data(data) if isinstance(data, str) else None
                if not content:
                    continue
                label_type = str(first_value(label.get("Type"), label.get("type"), "PDF") or "PDF").lower()
                label_format = str(first_value(label.get("Format"), label.get("format"), "") or "").lower()
                is_pdf = "pdf" in label_type or "pdf" in label_format or content.startswith(b"%PDF")
                return LabelResult(
                    content=content,
                    content_type="application/pdf" if is_pdf else "application/octet-stream",
                    file_extension=".pdf" if is_pdf else "",
                    raw_payload=label,
                )
        return None

    @staticmethod
    def _label_candidates(root: dict):
        for key in ("Label", "label"):
            label = root.get(key)
            if isinstance(label, dict):
                yield label
        for section in ("ShippingInfo", "ReturnInfo", "shipping_info", "return_info"):
            for row in as_list(root.get(section)):
                if not isinstance(row, dict):
                    continue
                for key in ("Label", "label"):
                    label = row.get(key)
                    if isinstance(label, dict):
                        yield label

    @staticmethod
    def _order_rows(payload) -> list[dict]:
        if isinstance(payload, dict):
            rows = extract_items(
                payload,
                "Data",
                "orders",
                "data.orders",
                "data.Data",
                "data.items",
                "data.list",
                "result.orders",
                "result.items",
                "items",
                "list",
            )
            if rows:
                return rows
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    @staticmethod
    def _products(order: dict) -> list[dict]:
        rows = extract_items(
            order,
            "LineItemsInfo",
            "products",
            "items",
            "order_items",
            "orderItems",
            "lines",
            "line_items",
            "lineItems",
            "details",
        )
        products: list[dict] = []
        for row in rows:
            products.append(
                product_payload(
                    row,
                    sku_keys=("sku", "SKU", "ChannelSKU", "ItemCode", "ItemId", "item_sku", "itemSku", "seller_sku", "sellerSku", "product.sku"),
                    name_keys=("name", "title", "ItemDescription", "product_name", "productName", "item_name", "itemName", "product.name"),
                    quantity_keys=("quantity", "qty", "ItemQty", "order_quantity", "orderQuantity", "quantity_ordered", "quantityOrdered"),
                    price_keys=("price", "unit_price", "unitPrice", "ItemUnitCost", "amount", "sale_price", "salePrice", "product.price"),
                    currency_keys=("currency", "currency_code", "CurrencyCode", "currencyCode", "price.currency", "unitPrice.currency"),
                )
            )
        return products

    def _normalize_order(self, order: dict) -> NormalizedOrder | None:
        general = order.get("GeneralInfo") if isinstance(order.get("GeneralInfo"), dict) else {}
        customer = order.get("CustomerInfo") if isinstance(order.get("CustomerInfo"), dict) else {}
        shipping_infos = as_list(order.get("ShippingInfo"))
        shipping_info = next((item for item in shipping_infos if isinstance(item, dict)), {})
        order_id = str(
            first_value(
                order.get("ReferenceOrderId"),
                order.get("order_id"),
                order.get("orderId"),
                order.get("id"),
                order.get("platform_order_id"),
                order.get("external_order_id"),
                order.get("externalOrderId"),
            )
            or ""
        )
        if not order_id:
            return None
        shipment = order.get("shipment") if isinstance(order.get("shipment"), dict) else {}
        package = order.get("package") if isinstance(order.get("package"), dict) else {}
        shipping = order.get("shipping") if isinstance(order.get("shipping"), dict) else {}
        address = first_value(
            customer,
            shipping.get("address") if isinstance(shipping.get("address"), dict) else None,
            shipping.get("receiver_address") if isinstance(shipping.get("receiver_address"), dict) else None,
            order.get("receiver_address") if isinstance(order.get("receiver_address"), dict) else None,
            order.get("shipping_address") if isinstance(order.get("shipping_address"), dict) else None,
            {},
        )
        products = self._products(order)
        tracking_number = str(
            first_value(
                shipping_info.get("TrackingNumber"),
                shipping_info.get("LabelTrackingNumber"),
                shipping_info.get("GroundTrackingNumber"),
                order.get("tracking_number"),
                order.get("trackingNumber"),
                order.get("shipment_tracking_number"),
                shipment.get("tracking_number"),
                shipment.get("TrackingNumber"),
                shipment.get("trackingNumber"),
                package.get("tracking_number"),
                package.get("trackingNumber"),
            )
            or ""
        )
        posting_number = str(
            first_value(
                order.get("ReferenceOrderId"),
                order.get("posting_number"),
                order.get("postingNumber"),
                order.get("shipment_id"),
                order.get("shipmentId"),
                order.get("package_id"),
                order.get("packageId"),
                shipment.get("id"),
                shipment.get("shipment_id"),
                package.get("id"),
                package.get("package_id"),
                order_id,
            )
            or ""
        )
        status = str(first_value(general.get("OrderStatus"), order.get("status"), order.get("order_status"), order.get("orderStatus"), shipment.get("status")) or "")
        raw_payload = {
            **order,
            "id": order_id,
            "order_number": first_value(
                general.get("ChannelOrderId"),
                general.get("CustomerOrderNumber"),
                order.get("order_no"),
                order.get("orderNo"),
                order.get("order_number"),
                order.get("orderNumber"),
                order_id,
            ),
            "site": first_value(general.get("ChannelCode"), order.get("site"), order.get("market"), order.get("channel"), "dmsmatrix"),
            "created_at": first_value(general.get("CreatedDate"), general.get("OrderDate"), order.get("created_at"), order.get("createdAt"), order.get("order_date"), order.get("orderDate")),
            "order_date": first_value(general.get("OrderDate"), order.get("order_date"), order.get("orderDate"), order.get("created_at"), order.get("createdAt")),
            "payment_at": first_value(general.get("OrderDate"), order.get("payment_at"), order.get("paymentAt"), order.get("paid_at"), order.get("paidAt"), order.get("order_date"), order.get("orderDate")),
            "shipping_deadline_at": first_value(order.get("shipping_deadline_at"), order.get("shippingDeadlineAt"), order.get("ship_by_date"), order.get("shipByDate")),
            "buyer_selected_logistics": first_value(
                general.get("ShippingMethod"),
                shipping_info.get("CarrierServiceCode"),
                shipping_info.get("CarrierCode"),
                order.get("logistics_channel"),
                order.get("logisticsChannel"),
                order.get("shipping_method"),
                order.get("shippingMethod"),
                shipping.get("method"),
            ),
            "shipment_tracking_number": tracking_number,
            "tracking_number": tracking_number,
            "country_code": first_value(
                customer.get("CountryCode"),
                order.get("country_code"),
                order.get("countryCode"),
                address.get("country_code") if isinstance(address, dict) else None,
                address.get("countryCode") if isinstance(address, dict) else None,
                address.get("country") if isinstance(address, dict) else None,
            ),
            "buyer_name": first_value(
                customer.get("FullName"),
                order.get("buyer_name"),
                order.get("buyerName"),
                address.get("name") if isinstance(address, dict) else None,
                address.get("recipient_name") if isinstance(address, dict) else None,
            ),
            "order_amount": normalize_money(first_value(general.get("TotalCost"), order.get("order_amount"), order.get("orderAmount"), order.get("total_amount"), order.get("totalAmount"), order.get("amount"))),
            "currency_code": normalize_currency(general.get("CurrencyCode"), order.get("currency_code"), order.get("currencyCode"), order.get("currency"), *(item.get("currency_code") for item in products)),
            "products": products,
            "items": products,
            "fulfillment_type": normalize_fulfillment_type(first_value(order.get("fulfillment_type"), order.get("fulfillmentType"), order.get("delivery_type"), order.get("deliveryType")), "FBS"),
            "shipment_id": first_value(shipment.get("id"), shipment.get("shipment_id"), order.get("shipment_id"), order.get("shipmentId"), posting_number),
            "package_id": first_value(package.get("id"), package.get("package_id"), order.get("package_id"), order.get("packageId")),
            "label_id": first_value(order.get("label_id"), order.get("labelId"), shipment.get("label_id"), package.get("label_id")),
            "label_url": first_value(order.get("label_url"), order.get("labelUrl"), shipment.get("label_url"), package.get("label_url")),
        }
        fulfillment_type = str(raw_payload["fulfillment_type"])
        return NormalizedOrder(
            platform_order_id=order_id,
            platform_order_no=str(raw_payload["order_number"] or order_id),
            posting_number=posting_number,
            platform_status=status,
            fulfillment_type=fulfillment_type,
            is_overseas_warehouse=fulfillment_type.upper() in {"FBO", "FBP", "OVERSEAS", "OVERSEAS_WAREHOUSE"},
            raw_payload=raw_payload,
        )

    async def _fetch_order_detail(self, order_id: str) -> dict:
        path = str(self.settings.get("order_detail_path") or "")
        if not path:
            return {}
        values = {"order_id": order_id, "platform_order_id": order_id}
        data = await self._get(self._format_path(path, values))
        payload = response_data(data)
        if isinstance(payload, dict):
            return first_value(payload.get("order"), payload.get("data"), payload.get("result"), payload) or {}
        return {}

    @staticmethod
    def _list_param(value) -> list:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return [item for item in as_list(value) if item not in (None, "")]

    @staticmethod
    def _dms_datetime(value: datetime) -> str:
        return iso_utc(value)

    @staticmethod
    def _raise_for_dms_errors(payload) -> None:
        if not isinstance(payload, dict):
            return
        errors = payload.get("Errors")
        if not isinstance(errors, list) or not errors:
            return
        messages = []
        for item in errors:
            if not isinstance(item, dict):
                continue
            messages.append(
                " ".join(
                    str(part)
                    for part in (item.get("Code"), item.get("Type"), item.get("Message"))
                    if part not in (None, "")
                )
                )
        raise RuntimeError(f"DMSMatrix API returned errors: {'; '.join(messages) or errors}")

    @staticmethod
    def _catalog_product_rows(payload) -> list[dict]:
        rows = extract_items(
            payload,
            "Data",
            "Products",
            "products",
            "data.products",
            "data.items",
            "items",
            "list",
            "result.products",
            "result.items",
        )
        if rows:
            return rows
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        return []

    def _normalize_catalog_product_row(self, row: dict, *, source: str, message: str = "") -> dict | None:
        sku = str(
            first_value(
                deep_get(row, "sku"),
                deep_get(row, "SKU"),
                deep_get(row, "seller_sku"),
                deep_get(row, "sellerSku"),
                deep_get(row, "ChannelSKU"),
                deep_get(row, "ItemCode"),
                deep_get(row, "ItemId"),
                deep_get(row, "offer_id"),
                deep_get(row, "id"),
            )
            or ""
        ).strip()
        product_id = str(
            first_value(
                deep_get(row, "product_id"),
                deep_get(row, "ProductId"),
                deep_get(row, "ProductID"),
                deep_get(row, "item_id"),
                deep_get(row, "ItemId"),
                deep_get(row, "id"),
                sku,
            )
            or ""
        ).strip()
        if not sku and not product_id:
            return None

        available_stock = first_value(
            deep_get(row, "available_stock"),
            deep_get(row, "availableQuantity"),
            deep_get(row, "available"),
            deep_get(row, "sellable_stock"),
            deep_get(row, "sellableStock"),
            deep_get(row, "free_to_sell_amount"),
            deep_get(row, "free_stock"),
            deep_get(row, "freeStock"),
            deep_get(row, "stock"),
            deep_get(row, "Stock"),
            deep_get(row, "quantity"),
            deep_get(row, "Quantity"),
            0,
        )
        raw_payload = dict(row)
        raw_payload.setdefault("catalog_source", source)
        if message:
            raw_payload.setdefault("catalog_message", message)
        main_image_url = _dmsmatrix_catalog_main_image_url(row)
        normalized = {
            "platform_product_id": product_id or sku,
            "platform_sku": sku or product_id,
            "product_name": str(
                first_value(
                    deep_get(row, "name"),
                    deep_get(row, "Name"),
                    deep_get(row, "title"),
                    deep_get(row, "Title"),
                    deep_get(row, "ItemDescription"),
                    deep_get(row, "product_name"),
                    deep_get(row, "productName"),
                    deep_get(row, "ProductName"),
                )
                or ""
            ),
            "listing_status": str(first_value(deep_get(row, "listing_status"), deep_get(row, "ListingStatus"), deep_get(row, "status"), deep_get(row, "Status")) or ""),
            "warehouse_code": str(
                first_value(
                    deep_get(row, "warehouse_code"),
                    deep_get(row, "warehouseCode"),
                    deep_get(row, "warehouse_id"),
                    deep_get(row, "warehouseId"),
                    deep_get(row, "warehouse"),
                    deep_get(row, "WarehouseCode"),
                    deep_get(row, "WarehouseId"),
                )
                or ""
            ).strip(),
            "warehouse_name": str(first_value(deep_get(row, "warehouse_name"), deep_get(row, "warehouseName"), deep_get(row, "warehouse"), deep_get(row, "WarehouseName")) or "").strip(),
            "fulfillment_type": str(first_value(deep_get(row, "fulfillment_type"), deep_get(row, "fulfillmentType"), deep_get(row, "delivery_type"), deep_get(row, "deliveryType")) or ""),
            "logistics_type": str(first_value(deep_get(row, "logistics_type"), deep_get(row, "logisticsType"), deep_get(row, "shipping_method"), deep_get(row, "shippingMethod")) or ""),
            "available_stock": available_stock,
            "reserved_stock": first_value(
                deep_get(row, "reserved_stock"),
                deep_get(row, "reserved"),
                deep_get(row, "reservedQuantity"),
                deep_get(row, "reservedQty"),
            ),
            "price_amount": normalize_money(
                first_value(
                    deep_get(row, "price"),
                    deep_get(row, "Price"),
                    deep_get(row, "selling_price"),
                    deep_get(row, "sellingPrice"),
                    deep_get(row, "unitPrice"),
                    deep_get(row, "UnitPrice"),
                    deep_get(row, "sale_price"),
                    deep_get(row, "salePrice"),
                )
            ),
            "price_currency": str(
                normalize_currency(
                    deep_get(row, "currency"),
                    deep_get(row, "Currency"),
                    deep_get(row, "currency_code"),
                    deep_get(row, "CurrencyCode"),
                    deep_get(row, "price.currency"),
                    deep_get(row, "unitPrice.currency"),
                )
                or "CNY"
            ).upper(),
            "raw_payload": raw_payload,
        }
        if main_image_url:
            normalized["main_image_url"] = main_image_url
        return normalized

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        path = str(
            first_value(
                self.settings.get("product_catalog_path"),
                self.settings.get("catalog_products_path"),
                self.settings.get("products_path"),
                self.settings.get("inventory_path"),
                self.settings.get("stock_path"),
            )
            or ""
        ).strip()
        if path:
            method = str(first_value(self.settings.get("product_catalog_method"), self.settings.get("catalog_products_method"), "GET") or "GET").upper()
            params = dict(self.settings.get("product_catalog_params") or self.settings.get("catalog_products_params") or {})
            page_param = str(first_value(self.settings.get("product_catalog_page_param"), self.settings.get("catalog_products_page_param"), "Page") or "Page")
            page_size_param = str(
                first_value(self.settings.get("product_catalog_page_size_param"), self.settings.get("catalog_products_page_size_param"), "PerPage") or "PerPage"
            )
            try:
                page_size = int(first_value(self.settings.get("product_catalog_page_size"), self.settings.get("catalog_products_page_size"), self.DEFAULT_PAGE_SIZE) or self.DEFAULT_PAGE_SIZE)
            except (TypeError, ValueError):
                page_size = self.DEFAULT_PAGE_SIZE
            page_size = max(1, min(page_size, 500))
            try:
                max_pages = int(first_value(self.settings.get("product_catalog_max_pages"), self.settings.get("catalog_products_max_pages"), 0) or 0)
            except (TypeError, ValueError):
                max_pages = 0
            if max_pages <= 0:
                max_pages = 200

            rows: list[dict] = []
            page = int(first_value(self.settings.get("product_catalog_start_page"), self.settings.get("catalog_products_start_page"), 1) or 1)
            while True:
                request_params = dict(params)
                request_params.setdefault(page_param, page)
                request_params.setdefault(page_size_param, page_size)
                payload = await (self._post(path, request_params) if method == "POST" else self._get(path, request_params))
                self._raise_for_dms_errors(payload)
                body = response_data(payload)
                page_rows = self._catalog_product_rows(body)
                for row in page_rows:
                    normalized = self._normalize_catalog_product_row(row, source="configured_endpoint")
                    if normalized:
                        rows.append(normalized)
                if not page_rows or page >= max_pages or not self._has_next_page(body, page, len(page_rows), page_size):
                    break
                page += 1
            return rows

        orders = await self.fetch_unprocessed_orders()
        normalized: list[dict] = []
        seen: set[tuple[str, str, str]] = set()
        fallback_message = "DMSMatrix product catalog endpoint not configured; row derived from order line items"
        for order in orders:
            products = order.raw_payload.get("products") if isinstance(order.raw_payload, dict) else []
            products = products if isinstance(products, list) else []
            for product in products:
                if not isinstance(product, dict):
                    continue
                sku = str(first_value(product.get("sku"), product.get("offer_id"), product.get("name")) or "").strip()
                product_id = str(first_value(product.get("offer_id"), product.get("sku"), sku) or "").strip()
                if not sku and not product_id:
                    continue
                identity = (product_id or sku, sku, "")
                if identity in seen:
                    continue
                seen.add(identity)
                fallback_row = {
                    **product,
                    "available_stock": 0,
                    "catalog_source": "orders_fallback",
                    "catalog_message": fallback_message,
                    "source_order_id": order.platform_order_id,
                    "source_order_no": order.platform_order_no,
                    "source_posting_number": order.posting_number,
                }
                normalized_row = self._normalize_catalog_product_row(fallback_row, source="orders_fallback", message=fallback_message)
                if normalized_row:
                    normalized.append(normalized_row)
        return normalized

    def _order_request_params(self, since: datetime | None, page_size: int) -> dict:
        params = dict(self.settings.get("orders_params") or {})
        if since:
            params.setdefault(str(self.settings.get("updated_since_param") or "OrderDateFrom"), self._dms_datetime(since))
            date_to_param = str(self.settings.get("date_to_param") or "OrderDateTo")
            if date_to_param:
                params.setdefault(date_to_param, self._dms_datetime(datetime.now(timezone.utc)))
        status = first_value(self.settings.get("order_statuses"), self.settings.get("order_status"))
        if status:
            params.setdefault(str(self.settings.get("status_param") or "OrderStatuses"), self._list_param(status))
        channel_codes = self._list_param(first_value(self.settings.get("channel_codes"), self.channel_code))
        if channel_codes:
            params.setdefault(str(self.settings.get("channel_codes_param") or "ChannelCodes"), channel_codes)
        if page_size:
            params.setdefault(str(self.settings.get("page_size_param") or "PerPage"), page_size)
        return params

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        path = str(self.settings.get("orders_path") or self.DEFAULT_ORDERS_PATH)
        method = str(self.settings.get("orders_method") or self.DEFAULT_ORDERS_METHOD).upper()
        page_size = min(max(int(self.settings.get("page_size") or self.DEFAULT_PAGE_SIZE), 1), 100)
        params = self._order_request_params(since, page_size)
        orders: list[NormalizedOrder] = []
        fetch_detail = bool(self.settings.get("fetch_order_details", False))
        paginate = bool(self.settings.get("orders_paginate", True))
        page_param = str(self.settings.get("page_param") or "Page")
        page = int(self.settings.get("start_page") or 1)
        max_pages = int(self.settings.get("max_pages") or 0)
        while True:
            request_params = dict(params)
            if paginate:
                request_params.setdefault(page_param, page)
            payload = await (self._post(path, request_params) if method == "POST" else self._get(path, request_params))
            self._raise_for_dms_errors(payload)
            body = response_data(payload)
            rows = self._order_rows(body)
            if not rows:
                break
            for row in rows:
                order_id = str(first_value(row.get("ReferenceOrderId"), row.get("order_id"), row.get("orderId"), row.get("id"), row.get("external_order_id"), row.get("externalOrderId")) or "")
                detail = await self._fetch_order_detail(order_id) if fetch_detail and order_id else row
                normalized = self._normalize_order(detail if isinstance(detail, dict) and detail else row)
                if normalized:
                    orders.append(normalized)
            if not paginate:
                break
            if max_pages and page >= max_pages:
                break
            if not self._has_next_page(body, page, len(rows), page_size):
                break
            page += 1
        return orders

    @staticmethod
    def _has_next_page(payload, page: int, row_count: int, page_size: int) -> bool:
        if not isinstance(payload, dict):
            return False
        explicit = first_value(
            deep_get(payload, "pagination.has_next"),
            deep_get(payload, "pagination.hasNext"),
            deep_get(payload, "page.has_next"),
            deep_get(payload, "page.hasNext"),
            payload.get("has_next"),
            payload.get("hasNext"),
        )
        if isinstance(explicit, bool):
            return explicit
        next_page = first_value(
            deep_get(payload, "pagination.next_page"),
            deep_get(payload, "pagination.nextPage"),
            deep_get(payload, "page.next_page"),
            deep_get(payload, "page.nextPage"),
            payload.get("next_page"),
            payload.get("nextPage"),
        )
        if next_page not in (None, "", 0, "0"):
            return True
        total_pages = first_value(deep_get(payload, "Meta.ResultsPages"), deep_get(payload, "Meta.results_pages"))
        current_page = first_value(deep_get(payload, "Meta.CurrentPage"), deep_get(payload, "Meta.current_page"), page)
        try:
            if total_pages not in (None, "", 0, "0"):
                return int(current_page) < int(total_pages)
        except (TypeError, ValueError):
            pass
        total = first_value(
            deep_get(payload, "Meta.ResultsOrders"),
            deep_get(payload, "Meta.TotalResults"),
            deep_get(payload, "pagination.total"),
            deep_get(payload, "page.total"),
            payload.get("total"),
            payload.get("total_count"),
            payload.get("totalCount"),
        )
        try:
            return bool(page_size and int(total) > page * page_size)
        except (TypeError, ValueError):
            return bool(row_count >= page_size)

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        updates: list[OrderStatusUpdate] = []
        for value in [str(item).strip() for item in posting_numbers if str(item or "").strip()]:
            detail = await self._fetch_order_detail(value)
            if not detail:
                path = str(self.settings.get("order_status_path") or "")
                if not path:
                    continue
                data = await self._get(self._format_path(path, {"order_id": value, "posting_number": value, "shipment_id": value}))
                payload = response_data(data)
                detail = payload if isinstance(payload, dict) else {}
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
        tracking_number = str(first_value(order.raw_payload.get("tracking_number"), order.raw_payload.get("shipment_tracking_number"), order.posting_number) or "")
        carrier = str(first_value(order.raw_payload.get("buyer_selected_logistics"), self.settings.get("carrier_name"), "DMSMatrix") or "")
        if self._dry_run():
            return ShipmentResult(order.posting_number or order.platform_order_id, tracking_number, carrier, "dry_run_created", order.raw_payload)
        path = str(self.settings.get("shipment_create_path") or "")
        if not path:
            return ShipmentResult(order.posting_number or order.platform_order_id, tracking_number, carrier, "existing", order.raw_payload)
        values = self._path_values(order)
        payload = dict(self.settings.get("shipment_payload_template") or {})
        payload.setdefault("order_id", order.platform_order_id)
        payload.setdefault("shipment_id", values.get("shipment_id") or order.posting_number or order.platform_order_id)
        payload.setdefault("tracking_number", tracking_number)
        payload.setdefault("carrier", carrier)
        payload.setdefault("ship_at", datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"))
        data = await self._post(self._format_path(path, values), payload)
        raw = response_data(data)
        if not isinstance(raw, dict):
            raw = {}
        return ShipmentResult(
            platform_shipment_id=str(first_value(raw.get("shipment_id"), raw.get("shipmentId"), raw.get("id"), values.get("shipment_id"), order.posting_number, order.platform_order_id) or ""),
            tracking_number=str(first_value(raw.get("tracking_number"), raw.get("trackingNumber"), tracking_number) or ""),
            carrier=str(first_value(raw.get("carrier"), raw.get("carrier_name"), carrier) or ""),
            status=str(first_value(raw.get("status"), "created") or "created"),
            raw_payload=raw,
        )

    async def register_tracking_number(
        self,
        order: NormalizedOrder,
        tracking_number: str,
        carrier: str = "",
    ) -> ShipmentResult:
        """Send an externally-created tracking number to the DMSMatrix channel."""
        tracking_number = str(tracking_number or "").strip()
        if not tracking_number:
            raise ValueError("DMSMatrix external tracking number is required.")

        reference_order_id = str(first_value(order.platform_order_id, order.posting_number, order.platform_order_no) or "").strip()
        if not reference_order_id:
            raise ValueError("DMSMatrix ReferenceOrderId is required to register external tracking.")

        existing_tracking = str(
            first_value(
                order.raw_payload.get("tracking_number"),
                order.raw_payload.get("shipment_tracking_number"),
                deep_get(order.raw_payload, "ShippingInfo.0.TrackingNumber"),
            )
            or ""
        ).strip()
        if existing_tracking == tracking_number:
            return ShipmentResult(
                platform_shipment_id=reference_order_id,
                tracking_number=tracking_number,
                carrier=carrier,
                status="existing",
                raw_payload={"registration": "existing"},
            )

        payload = [
            {
                "ReferenceOrderId": reference_order_id,
                "ShippingInfo": [{"TrackingNumber": tracking_number}],
            }
        ]
        if self._dry_run():
            return ShipmentResult(
                platform_shipment_id=reference_order_id,
                tracking_number=tracking_number,
                carrier=carrier,
                status="dry_run_registered",
                raw_payload={"registration": "dry_run", "payload": payload},
            )

        path = str(self.settings.get("tracking_registration_path") or "/Order/fulfilOrders")
        data = await self._post(path, payload)
        self._raise_for_dms_errors(data)
        raw = response_data(data)
        return ShipmentResult(
            platform_shipment_id=reference_order_id,
            tracking_number=tracking_number,
            carrier=carrier,
            status="registered",
            raw_payload=raw if isinstance(raw, dict) else {"response": raw},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self._dry_run():
            return self._preview_label("DMSMatrix Label Preview", shipment, order)
        existing_label = self._label_result_from_payload(order.raw_payload or {})
        if existing_label:
            return existing_label
        values = self._path_values(order, shipment)
        path = str(self.settings.get("label_path") or order.raw_payload.get("label_url") or "")
        label_format = str(self.settings.get("label_format") or "6x4_PDF")
        if not path:
            label = await self._fetch_label_from_get_orders(order, label_format)
            if label:
                return label
            order_label_path = str(self.settings.get("label_order_path") or "").strip()
            if not order_label_path:
                raise RuntimeError("DMSMatrix label response did not contain ShippingInfo.Label.Data")
            payload = dict(self.settings.get("label_payload_template") or {})
            payload.setdefault("ReferenceOrderId", order.platform_order_id or order.posting_number or order.platform_order_no)
            label_payload = dict(payload.get("Label") or payload.get("label") or {})
            label_payload.setdefault("Type", "PDF" if "pdf" in label_format.lower() else "IMAGE")
            label_payload.setdefault("Format", label_format)
            payload["Label"] = label_payload
            data = await self._post(order_label_path, payload)
            self._raise_for_dms_errors(data)
            label = self._label_result_from_payload(data)
            if label:
                return label
            raise RuntimeError("DMSMatrix label response did not contain ShippingInfo.Label.Data")
        method = str(self.settings.get("label_method") or "GET").upper()
        payload = dict(self.settings.get("label_payload_template") or {})
        payload.setdefault("order_id", order.platform_order_id)
        payload.setdefault("shipment_id", values.get("shipment_id") or order.posting_number or order.platform_order_id)
        payload.setdefault("tracking_number", values.get("tracking_number") or "")
        payload.setdefault("format", label_format)
        url = self._format_path(path, values)
        data = await (self._post(url, payload) if method == "POST" else self._get(url, payload))
        label = self._label_result_from_payload(data)
        if label:
            return label
        return label_from_platform_response(data, default_content_type="application/pdf" if "pdf" in label_format.lower() else "application/octet-stream")

    async def _fetch_label_from_get_orders(self, order: NormalizedOrder, label_format: str) -> LabelResult | None:
        reference_id = str(first_value(order.platform_order_id, order.posting_number, order.platform_order_no) or "")
        if not reference_id:
            return None
        path = str(self.settings.get("label_get_orders_path") or self.settings.get("orders_path") or self.DEFAULT_ORDERS_PATH)
        method = str(self.settings.get("label_get_orders_method") or self.settings.get("orders_method") or self.DEFAULT_ORDERS_METHOD).upper()
        payload = dict(self.settings.get("label_get_orders_payload_template") or {})
        payload.setdefault("ReferenceOrderIds", [reference_id])
        payload.setdefault("LabelFormat", label_format)
        payload.setdefault("Sections", ["GeneralInfo", "LineItemsInfo", "CustomerInfo", "ShippingInfo", "ReturnInfo"])
        payload.setdefault(str(self.settings.get("page_size_param") or "PerPage"), 50)
        payload.setdefault(str(self.settings.get("page_param") or "Page"), 1)
        data = await (self._post(path, payload) if method == "POST" else self._get(path, payload))
        self._raise_for_dms_errors(data)
        return self._label_result_from_payload(data)

    async def fetch_label_batch(self, orders: list[NormalizedOrder]) -> LabelResult:
        if self._dry_run():
            shipment = ShipmentResult("batch", "", "DMSMatrix", "dry_run")
            return self._preview_label("DMSMatrix Batch Label Preview", shipment, orders[0] if orders else NormalizedOrder("batch", "", {}))
        path = str(self.settings.get("label_batch_path") or "")
        if not path:
            raise NotImplementedError("DMSMatrix batch label download requires label_batch_path")
        label_format = str(self.settings.get("label_format") or "pdf").lower()
        payload = dict(self.settings.get("label_batch_payload_template") or {})
        payload.setdefault(
            "orders",
            [
                {
                    "order_id": order.platform_order_id,
                    "shipment_id": order.raw_payload.get("shipment_id") or order.posting_number or order.platform_order_id,
                    "tracking_number": order.raw_payload.get("tracking_number") or order.raw_payload.get("shipment_tracking_number") or "",
                }
                for order in orders
            ],
        )
        payload.setdefault("format", label_format)
        data = await self._post(path, payload)
        return label_from_platform_response(data, default_content_type="application/pdf" if label_format == "pdf" else "application/octet-stream")
