# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
import base64
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
from time import perf_counter

import httpx
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .pdf_preview import build_preview_pdf


def _order_id_value(value: str):
    text = str(value or "").strip()
    return int(text) if text.isdigit() else text


def _first_value(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def _currency_code(value) -> str:
    mapping = {643: "RUB", "643": "RUB", 156: "CNY", "156": "CNY", 840: "USD", "840": "USD"}
    return mapping.get(value, "" if value is None else str(value))


def _wildberries_money(value) -> str:
    if value in (None, ""):
        return ""
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        return str(value)
    if "." not in str(value):
        amount = amount / Decimal("100")
    return format(amount.quantize(Decimal("0.01")).normalize(), "f")


def _country_code_from_currency(value) -> str:
    mapping = {
        51: "AM",
        "51": "AM",
        156: "CN",
        "156": "CN",
        398: "KZ",
        "398": "KZ",
        417: "KG",
        "417": "KG",
        643: "RU",
        "643": "RU",
        933: "BY",
        "933": "BY",
        944: "AZ",
        "944": "AZ",
        949: "TR",
        "949": "TR",
    }
    return mapping.get(value, "")


def _looks_like_china_office(value) -> bool:
    text = str(value or "").strip().lower()
    return any(
        marker in text
        for marker in (
            "beijing",
            "china",
            "\u043f\u0435\u043a\u0438\u043d",
            "\u4e2d\u56fd",
            "\u4e2d\u570b",
        )
    )


def _wildberries_country_code(order: dict) -> str:
    supply = order.get("supply") if isinstance(order.get("supply"), dict) else {}
    cross_border_type = str(_first_value(order.get("crossBorderType"), supply.get("crossBorderType")) or "").strip()
    if cross_border_type == "1":
        office_values = [
            order.get("office"),
            order.get("officeName"),
            order.get("office_name"),
            supply.get("destinationOffice"),
            supply.get("destinationOfficeName"),
            *_as_list(order.get("offices")),
        ]
        if any(_looks_like_china_office(value) for value in office_values):
            return "CN"

    explicit = str(_first_value(order.get("countryCode"), order.get("country_code")) or "").strip().upper()
    if len(explicit) == 2 and explicit.isalpha():
        return explicit

    return _country_code_from_currency(order.get("currencyCode")) or _country_code_from_currency(order.get("convertedCurrencyCode"))


def _is_cross_border_order_payload(payload: dict | None) -> bool:
    if not isinstance(payload, dict):
        return False
    country_code = str(payload.get("country_code") or payload.get("countryCode") or "").strip().upper()
    if country_code and country_code != "RU":
        return True
    supply = payload.get("supply") if isinstance(payload.get("supply"), dict) else {}
    cross_border_type = str(_first_value(payload.get("crossBorderType"), supply.get("crossBorderType")) or "").strip()
    if cross_border_type == "1":
        return True
    return False


def _as_list(value) -> list:
    if isinstance(value, list):
        return value
    if value in (None, ""):
        return []
    return [value]


def _has_meta_requirements(order: dict) -> bool:
    return bool(order.get("requiredMeta") or order.get("optionalMeta"))


def _normalize_fulfillment_type(value) -> str:
    text = str(value or "").strip()
    if not text:
        return "FBS"
    return text.upper().replace("-", "_").replace(" ", "_")[:40]


def _is_overseas_warehouse_order(order: dict) -> bool:
    delivery_type = _normalize_fulfillment_type(_first_value(order.get("deliveryType"), order.get("delivery_type"), "FBS"))
    if delivery_type and delivery_type != "FBS":
        return True
    supply = order.get("supply") if isinstance(order.get("supply"), dict) else {}
    values = [
        order.get("fulfillmentType"),
        order.get("fulfillment_type"),
        order.get("warehouseType"),
        order.get("warehouse_type"),
        order.get("warehouseName"),
        order.get("warehouse_name"),
        supply.get("warehouseType"),
        supply.get("warehouse_type"),
        supply.get("warehouseName"),
        supply.get("warehouse_name"),
        supply.get("name"),
    ]
    text = " ".join(str(value) for value in values if value not in (None, "")).lower()
    return any(marker in text for marker in ("overseas", "fulfillment", "fbo", "fbw", "fbp"))


def _utc_timestamp(value: datetime) -> int:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return int(value.timestamp())


def _normalize_order_payload(order: dict) -> dict:
    payload = dict(order)
    article = str(order.get("article") or "").strip()
    supply = order.get("supply") if isinstance(order.get("supply"), dict) else {}
    supply_id = str(_first_value(order.get("supplyId"), supply.get("id")) or "").strip()
    if supply_id:
        payload.setdefault("supply_id", supply_id)
    created_at = _first_value(order.get("createdAt"), order.get("created_at"))
    if created_at:
        payload.setdefault("created_at", created_at)
        payload.setdefault("in_process_at", created_at)
    shipment_date = _first_value(
        order.get("shipmentDate"),
        order.get("deliveryDate"),
        order.get("delivery_date"),
        supply.get("scanDt"),
        supply.get("closedAt"),
    )
    if shipment_date:
        payload.setdefault("shipment_date", shipment_date)
        payload.setdefault("shipping_deadline_at", shipment_date)
    delivery_type = _first_value(order.get("deliveryType"), order.get("delivery_type"), "FBS")
    fulfillment_type = _normalize_fulfillment_type(delivery_type)
    is_overseas_warehouse = _is_overseas_warehouse_order(order)
    payload.setdefault("buyer_selected_logistics", delivery_type)
    payload.setdefault("fulfillment_type", fulfillment_type)
    payload.setdefault("is_overseas_warehouse", is_overseas_warehouse)
    payload.setdefault("site", "wildberries")
    amount = _first_value(
        order.get("convertedFinalPrice"),
        order.get("convertedPrice"),
        order.get("finalPrice"),
        order.get("price"),
    )
    if amount not in (None, ""):
        amount = _wildberries_money(amount)
        payload.setdefault("order_amount", amount)
    currency = _currency_code(_first_value(order.get("convertedCurrencyCode"), order.get("currencyCode")))
    if currency:
        payload.setdefault("currency_code", currency)
    country_code = _wildberries_country_code(order)
    if country_code:
        payload["country_code"] = country_code
    sku_values = _as_list(order.get("skus"))
    product = {
        "offer_id": article,
        "sku": article,
        "article": article,
        "quantity": 1,
        "price": amount,
        "currency_code": currency,
        "nmId": order.get("nmId"),
        "chrtId": order.get("chrtId"),
        "barcode": sku_values[0] if sku_values else "",
        "raw_payload": order,
    }
    payload["products"] = [product]
    payload.setdefault("items", [product])
    return payload


def _supply_id_from_payload(payload: dict) -> str:
    supply = payload.get("supply") if isinstance(payload.get("supply"), dict) else {}
    return str(_first_value(payload.get("supplyId"), payload.get("supply_id"), supply.get("id")) or "").strip()


def _payload_has_supply_assignment(payload: dict) -> bool:
    return bool(_supply_id_from_payload(payload))


def _supply_id_from_response(data: dict) -> str:
    supply = data.get("supply") if isinstance(data.get("supply"), dict) else {}
    nested = data.get("data") if isinstance(data.get("data"), dict) else {}
    return str(
        _first_value(
            data.get("id"),
            data.get("supplyId"),
            data.get("supplyID"),
            supply.get("id"),
            nested.get("id"),
            nested.get("supplyId"),
        )
        or ""
    ).strip()


def _stickers_to_pdf(stickers: list[dict]) -> bytes:
    if not stickers:
        raise RuntimeError("Wildberries sticker response did not contain stickers")
    width = 58 * mm
    height = 40 * mm
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=(width, height))
    rendered = 0
    for sticker in stickers:
        file_content = sticker.get("file")
        if not file_content:
            continue
        image_bytes = base64.b64decode(file_content)
        image = ImageReader(BytesIO(image_bytes))
        pdf.drawImage(image, 0, 0, width=width, height=height, preserveAspectRatio=True, anchor="c")
        pdf.showPage()
        rendered += 1
    if not rendered:
        raise RuntimeError("Wildberries sticker response did not contain printable sticker files")
    pdf.save()
    return output.getvalue()


def _cross_border_sticker_pdf(stickers: list[dict]) -> tuple[bytes, dict]:
    if not stickers:
        raise RuntimeError("Wildberries cross-border sticker response did not contain stickers")
    rows: list[dict] = []
    first_content = b""
    first_barcode = ""
    first_tracking = ""
    for sticker in stickers:
        if not isinstance(sticker, dict):
            continue
        row = {
            key: value
            for key, value in {
                "id": _first_value(sticker.get("id"), sticker.get("orderId"), sticker.get("order_id")),
                "status": sticker.get("status"),
                "barcode": sticker.get("barcode"),
                "trackingNumber": _first_value(
                    sticker.get("trackingNumber"),
                    sticker.get("tracking_number"),
                    sticker.get("trackingNo"),
                    sticker.get("tracking_no"),
                    sticker.get("waybillNumber"),
                    sticker.get("waybill_number"),
                    sticker.get("waybillNo"),
                    sticker.get("waybill_no"),
                    sticker.get("parcelId"),
                    sticker.get("parcelID"),
                    sticker.get("parcel_id"),
                ),
                "parcelId": _first_value(sticker.get("parcelId"), sticker.get("parcelID"), sticker.get("parcel_id")),
            }.items()
            if value not in (None, "")
        }
        if row:
            rows.append(row)
        if row.get("barcode") and not first_barcode:
            first_barcode = str(row["barcode"])
        if row.get("trackingNumber") and not first_tracking:
            first_tracking = str(row["trackingNumber"])
        file_content = sticker.get("file")
        if file_content and not first_content:
            first_content = base64.b64decode(file_content)
    if not first_content:
        statuses = ", ".join(str(row.get("status") or "unknown") for row in rows[:5])
        raise RuntimeError(f"Wildberries cross-border sticker response did not contain PDF file; statuses: {statuses}")
    if not first_content.startswith(b"%PDF"):
        raise RuntimeError("Wildberries cross-border sticker response did not contain PDF content")
    payload: dict = {"stickers": rows, "cross_border": True}
    if first_barcode:
        payload["wildberries_sticker_barcode"] = first_barcode
    if first_tracking:
        payload["shipment_tracking_number"] = first_tracking
        payload["waybillNumber"] = first_tracking
    return first_content, payload


def _sticker_metadata(stickers: list[dict]) -> dict:
    rows: list[dict] = []
    by_order_id: dict[str, dict] = {}
    first_barcode = ""
    for sticker in stickers:
        if not isinstance(sticker, dict):
            continue
        order_id = _first_value(sticker.get("id"), sticker.get("orderId"), sticker.get("order_id"))
        barcode = str(_first_value(sticker.get("barcode"), sticker.get("trackingNumber"), sticker.get("tracking_number")) or "").strip()
        entry = {
            key: value
            for key, value in {
                "id": order_id,
                "barcode": barcode,
                "partA": sticker.get("partA"),
                "partB": sticker.get("partB"),
            }.items()
            if value not in (None, "")
        }
        if not entry:
            continue
        rows.append(entry)
        if order_id not in (None, ""):
            by_order_id[str(order_id)] = entry
        if barcode and not first_barcode:
            first_barcode = barcode
    payload: dict = {"stickers": rows, "stickers_by_order_id": by_order_id}
    if first_barcode:
        payload["wildberries_sticker_barcode"] = first_barcode
    return payload


class WildberriesConnector(MarketplaceConnector):
    platform = "wildberries"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.api_key = credentials.get("api_key", "")
        self.settings = settings or {}
        self.base_url = str(self.settings["base_url"]).rstrip("/")
        self.account_id = str(self.settings.get("account_id") or "wildberries")
        self._auto_supply_id = ""

    @property
    def headers(self) -> dict:
        return {"Authorization": self.api_key, "Content-Type": "application/json"}

    @staticmethod
    def _retry_delay_seconds(response: httpx.Response, attempt: int, max_delay: float = 30.0) -> float:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return max(0.0, min(float(retry_after), max_delay))
            except (TypeError, ValueError):
                pass
        try:
            reset_seconds = float(response.headers.get("x-ratelimit-reset") or 0)
        except (TypeError, ValueError):
            reset_seconds = 0.0
        if reset_seconds > 0:
            return max(0.0, min(reset_seconds + 1, max_delay))
        return min(2**attempt, max_delay)

    async def _catalog_request(
        self,
        client: httpx.AsyncClient,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> httpx.Response:
        response = None
        for attempt in range(5):
            response = await client.request(method, url, headers=self.headers, params=params, json=json)
            if response.status_code not in {429, 500, 502, 503} or attempt == 4:
                return response
            await asyncio.sleep(self._retry_delay_seconds(response, attempt))
        if response is None:
            raise RuntimeError("Wildberries product catalog API returned no response")
        return response

    async def _fetch_negative_feedbacks(
        self,
        client: httpx.AsyncClient,
        start: date,
        end: date,
    ) -> dict[tuple[str, str], int] | None:
        counts: dict[tuple[str, str], int] = {}
        take = 5000
        try:
            max_wait = int(self.settings.get("traffic_review_max_wait_seconds", 600))
        except (TypeError, ValueError):
            max_wait = 600
        for is_answered in (True, False):
            skip = 0
            for _ in range(100):
                response = None
                for attempt in range(3):
                    try:
                        response = await client.get(
                            "https://feedbacks-api.wildberries.ru/api/v1/feedbacks",
                            headers=self.headers,
                            params={
                                "isAnswered": str(is_answered).lower(),
                                "take": take,
                                "skip": skip,
                                "order": "dateDesc",
                            },
                        )
                    except httpx.HTTPError:
                        return None
                    if response.status_code != 429:
                        break
                    if attempt == 2:
                        return None
                    try:
                        reset_seconds = int(response.headers.get("x-ratelimit-reset") or 1)
                    except (TypeError, ValueError):
                        reset_seconds = 1
                    await asyncio.sleep(max(1, min(reset_seconds + 1, max_wait)))
                if response is None or response.status_code >= 400:
                    return None
                try:
                    payload = response.json()
                except ValueError:
                    return None
                data = payload.get("data") if isinstance(payload, dict) else {}
                feedbacks = data.get("feedbacks") if isinstance(data, dict) else []
                feedbacks = feedbacks if isinstance(feedbacks, list) else []
                for feedback in feedbacks:
                    if not isinstance(feedback, dict):
                        continue
                    review_date = str(feedback.get("createdDate") or "")[:10]
                    if not review_date or not (start.isoformat() <= review_date <= end.isoformat()):
                        continue
                    try:
                        valuation = int(feedback.get("productValuation") or 0)
                    except (TypeError, ValueError):
                        continue
                    if valuation <= 0 or valuation > 2:
                        continue
                    product = feedback.get("productDetails") if isinstance(feedback.get("productDetails"), dict) else {}
                    nm_id = str(product.get("nmId") or feedback.get("nmId") or "").strip()
                    if nm_id:
                        key = (nm_id, review_date)
                        counts[key] = counts.get(key, 0) + 1
                if len(feedbacks) < take:
                    break
                skip += take
        return counts

    async def fetch_traffic(self, start: datetime, end: datetime) -> list[dict]:
        period_days = max(1, (end.date() - start.date()).days + 1)
        past_end = start.date() - timedelta(days=1)
        past_start = past_end - timedelta(days=period_days - 1)
        analytics_base_url = str(
            self.settings.get("analytics_base_url") or "https://seller-analytics-api.wildberries.ru"
        ).rstrip("/")
        offset = 0
        limit = 1000
        products: list[dict] = []
        async with httpx.AsyncClient(timeout=90) as client:
            while True:
                body = {
                    "selectedPeriod": {"start": start.date().isoformat(), "end": end.date().isoformat()},
                    "pastPeriod": {"start": past_start.isoformat(), "end": past_end.isoformat()},
                    "nmIds": [],
                    "brandNames": [],
                    "subjectIds": [],
                    "tagIds": [],
                    "skipDeletedNm": True,
                    "orderBy": {"field": "openCard", "mode": "desc"},
                    "limit": limit,
                    "offset": offset,
                }
                response = None
                for attempt in range(4):
                    response = await client.post(
                        f"{analytics_base_url}/api/analytics/v3/sales-funnel/products",
                        headers=self.headers,
                        json=body,
                    )
                    if response.status_code not in {429, 500, 502, 503} or attempt == 3:
                        break
                    await asyncio.sleep(2**attempt)
                if response is None:
                    raise RuntimeError("Wildberries traffic API returned no response")
                if response.status_code == 429:
                    raise RuntimeError("Wildberries traffic API rate limited (HTTP 429); retry later")
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else {}
                page = data.get("products") if isinstance(data, dict) else []
                page = page if isinstance(page, list) else []
                products.extend(item for item in page if isinstance(item, dict))
                if len(page) < limit or not bool(data.get("isNextPage")):
                    break
                offset += limit

            negative_reviews = await self._fetch_negative_feedbacks(client, past_start, end.date())

        def first_number(values: dict, *keys: str):
            for key in keys:
                if values.get(key) is not None:
                    return values.get(key)
            return None

        rows: list[dict] = []
        periods = [
            ("selected", start.date().isoformat(), end.date().isoformat()),
            ("past", past_start.isoformat(), past_end.isoformat()),
        ]
        for item in products:
            product = item.get("product") if isinstance(item.get("product"), dict) else item
            statistic = item.get("statistic") if isinstance(item.get("statistic"), dict) else {}
            nm_id = str(product.get("nmId") or item.get("nmId") or "")
            sku = str(product.get("vendorCode") or item.get("vendorCode") or nm_id)
            platform_category_id = str(product.get("subjectId") or item.get("subjectId") or "")
            platform_category_name = str(product.get("subjectName") or item.get("subjectName") or "")
            for key, period_start, period_end in periods:
                values = statistic.get(key) if isinstance(statistic.get(key), dict) else item.get(key)
                if not isinstance(values, dict):
                    continue
                clicks = first_number(values, "openCardCount", "openCard", "openCount")
                add_to_cart = first_number(values, "addToCartCount", "addToCart", "cartCount")
                orders = first_number(values, "ordersCount", "orders", "orderCount")
                revenue = first_number(values, "ordersSumRub", "ordersSum", "orderSum", "revenue")
                negative_count = None
                if negative_reviews is not None:
                    period_start_date = date.fromisoformat(period_start)
                    period_end_date = date.fromisoformat(period_end)
                    negative_count = sum(
                        negative_reviews.get((nm_id, (period_start_date + timedelta(days=day_offset)).isoformat()), 0)
                        for day_offset in range((period_end_date - period_start_date).days + 1)
                    )
                rows.append(
                    {
                        "source": "organic",
                        "grain": "date_range",
                        "stat_date": period_end,
                        "period_start": period_start,
                        "period_end": period_end,
                        "region": "RU",
                        "entity_type": "sku",
                        "entity_id": nm_id,
                        "sku": sku,
                        "product_name": str(product.get("title") or product.get("name") or ""),
                        "impressions": None,
                        "clicks": int(clicks) if clicks is not None else None,
                        "add_to_cart": int(add_to_cart) if add_to_cart is not None else None,
                        "orders": int(orders) if orders is not None else None,
                        "negative_reviews": negative_count,
                        "revenue": float(revenue) if revenue is not None else None,
                        "currency": "RUB",
                        "raw_data": {
                            "nm_id": nm_id,
                            "negative_reviews_source": "wildberries_feedbacks" if negative_reviews is not None else "unavailable",
                            "negative_reviews_daily": (
                                {
                                    review_day: count
                                    for day_offset in range((period_end_date - period_start_date).days + 1)
                                    for review_day in [(period_start_date + timedelta(days=day_offset)).isoformat()]
                                    for count in [negative_reviews.get((nm_id, review_day), 0)]
                                    if count
                                }
                                if negative_reviews is not None
                                else {}
                            ),
                            "platform_category_id": platform_category_id,
                            "platform_category_name": platform_category_name,
                            "platform_category_path": platform_category_name,
                        },
                    }
                )
        return rows

    def _content_base_url(self) -> str:
        configured = str(self.settings.get("content_base_url") or "").strip()
        if configured:
            return configured.rstrip("/")
        return self.base_url.replace("marketplace-api.wildberries.ru", "content-api.wildberries.ru")

    async def _content_request(self, path: str, *, params: dict | None = None) -> dict:
        from ..api_logger import log_api_call

        url = f"{self._content_base_url()}{path}"
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.get(url, headers=self.headers, params=params)
                response.raise_for_status()
                body = response.json() if response.content else {}
                log_api_call(
                    platform=self.platform,
                    account_id=self.account_id,
                    method="GET",
                    url=url,
                    request_body={"params": params} if params else None,
                    response_status=response.status_code,
                    response_body=body,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                return body if isinstance(body, dict) else {}
        except httpx.HTTPStatusError as exc:
            error_text = exc.response.text if exc.response is not None else str(exc)
            log_api_call(
                platform=self.platform,
                account_id=self.account_id,
                method="GET",
                url=url,
                request_body={"params": params} if params else None,
                response_status=exc.response.status_code if exc.response is not None else None,
                response_body=None,
                error_message=error_text[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise
        except Exception as exc:
            log_api_call(
                platform=self.platform,
                account_id=self.account_id,
                method="GET",
                url=url,
                request_body={"params": params} if params else None,
                response_status=None,
                response_body=None,
                error_message=str(exc)[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        """Return WB cards with price and seller-warehouse sellable stock."""
        cards: list[dict] = []
        cursor: dict[str, object] = {"limit": 100}
        content_url = f"{self._content_base_url()}/content/v2/get/cards/list"
        price_base_url = str(
            self.settings.get("prices_base_url") or "https://discounts-prices-api.wildberries.ru"
        ).rstrip("/")
        stock_base_url = str(
            self.settings.get("statistics_base_url") or "https://statistics-api.wildberries.ru"
        ).rstrip("/")
        async with httpx.AsyncClient(timeout=90) as client:
            for _ in range(1000):
                response = await self._catalog_request(
                    client,
                    "POST",
                    content_url,
                    json={"settings": {"cursor": cursor, "filter": {"withPhoto": -1}}},
                )
                response.raise_for_status()
                payload = response.json()
                page = payload.get("cards") if isinstance(payload, dict) else []
                page = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
                cards.extend(page)
                next_cursor = payload.get("cursor") if isinstance(payload, dict) else {}
                next_nm_id = next_cursor.get("nmID") if isinstance(next_cursor, dict) else None
                if not page or not next_nm_id or int(next_nm_id or 0) == int(cursor.get("nmID") or 0):
                    break
                cursor = {"limit": 100, "nmID": int(next_nm_id)}
                if isinstance(next_cursor, dict) and next_cursor.get("updatedAt"):
                    cursor["updatedAt"] = next_cursor["updatedAt"]
                await asyncio.sleep(0.65)
            else:
                raise RuntimeError("Wildberries product catalog pagination exceeded the safety limit")

            price_by_nm_id: dict[str, dict] = {}
            price_fetch_error = ""
            offset = 0
            for _ in range(1000):
                response = await self._catalog_request(
                    client,
                    "GET",
                    f"{price_base_url}/api/v2/list/goods/filter",
                    params={"limit": 1000, "offset": offset},
                )
                if response.status_code == 429:
                    price_fetch_error = "Wildberries price API rate limited after retries"
                    break
                response.raise_for_status()
                payload = response.json()
                data = payload.get("data") if isinstance(payload, dict) else {}
                page = data.get("listGoods") if isinstance(data, dict) else []
                page = [item for item in page if isinstance(item, dict)] if isinstance(page, list) else []
                for item in page:
                    nm_id = str(item.get("nmID") or "").strip()
                    if nm_id:
                        price_by_nm_id[nm_id] = item
                if not page:
                    break
                offset += 1000
                await asyncio.sleep(0.65)
            else:
                raise RuntimeError("Wildberries price pagination exceeded the safety limit")

            response = await self._catalog_request(
                client,
                "GET",
                f"{stock_base_url}/api/v1/supplier/stocks",
                params={"dateFrom": "2019-01-01T00:00:00"},
            )
            stock_fetch_error = ""
            if response.status_code >= 400:
                stock_fetch_error = f"Wildberries stock API returned HTTP {response.status_code}"
                stock_rows = []
            else:
                stock_payload = response.json()
                stock_rows = stock_payload if isinstance(stock_payload, list) else []

        stocks_by_vendor_code: dict[str, list[dict]] = {}
        for stock in stock_rows:
            if not isinstance(stock, dict):
                continue
            vendor_code = str(stock.get("supplierArticle") or "").strip()
            if vendor_code:
                stocks_by_vendor_code.setdefault(vendor_code, []).append(stock)

        normalized: list[dict] = []
        for card in cards:
            nm_id = str(card.get("nmID") or "").strip()
            vendor_code = str(card.get("vendorCode") or "").strip()
            if not nm_id and not vendor_code:
                continue
            price_info = price_by_nm_id.get(nm_id, {})
            sizes = price_info.get("sizes") if isinstance(price_info.get("sizes"), list) else []
            first_size = next((item for item in sizes if isinstance(item, dict)), {})
            price = first_size.get("discountedPrice") or first_size.get("price") or price_info.get("price")
            raw_payload = {"card": card, "price": price_info}
            if price_fetch_error:
                raw_payload["price_fetch_error"] = price_fetch_error
            if stock_fetch_error:
                raw_payload["stock_fetch_error"] = stock_fetch_error
            base = {
                "platform_product_id": nm_id,
                "platform_sku": vendor_code or nm_id,
                "product_name": str(card.get("title") or ""),
                "listing_status": "active",
                "price_amount": price,
                "price_currency": str(price_info.get("currencyIsoCode4217") or "RUB"),
                "raw_payload": raw_payload,
            }
            stocks = stocks_by_vendor_code.get(vendor_code, [])
            if not stocks:
                normalized.append({**base, "warehouse_code": "", "warehouse_name": "", "available_stock": 0})
                continue
            for stock in stocks:
                normalized.append(
                    {
                        **base,
                        "warehouse_code": str(stock.get("warehouseName") or stock.get("warehouseId") or ""),
                        "warehouse_name": str(stock.get("warehouseName") or ""),
                        "available_stock": stock.get("quantity") or 0,
                        "reserved_stock": stock.get("inWayToClient") or stock.get("inWayFromClient"),
                        "raw_payload": {**base["raw_payload"], "stock": stock},
                    }
                )
        return normalized

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json_body: dict | None = None,
    ) -> dict:
        from ..api_logger import log_api_call

        url = f"{self.base_url}{path}"
        started = perf_counter()
        request_body = json_body if json_body is not None else ({"params": params} if params else None)
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.request(method, url, headers=self.headers, params=params, json=json_body)
                response.raise_for_status()
                body = response.json() if response.content else {}
                log_api_call(
                    platform=self.platform,
                    account_id=self.account_id,
                    method=method.upper(),
                    url=url,
                    request_body=request_body,
                    response_status=response.status_code,
                    response_body=body,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                return body
        except httpx.HTTPStatusError as exc:
            error_text = exc.response.text if exc.response is not None else str(exc)
            log_api_call(
                platform=self.platform,
                account_id=self.account_id,
                method=method.upper(),
                url=url,
                request_body=request_body,
                response_status=exc.response.status_code if exc.response is not None else None,
                response_body=None,
                error_message=error_text[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise
        except Exception as exc:
            log_api_call(
                platform=self.platform,
                account_id=self.account_id,
                method=method.upper(),
                url=url,
                request_body=request_body,
                response_status=None,
                response_body=None,
                error_message=str(exc)[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        lookback_days = int(self.settings.get("lookback_days", 30))
        end_time = datetime.now(timezone.utc)
        start_time = since - timedelta(hours=1) if since else end_time - timedelta(days=lookback_days)
        if start_time.tzinfo is None:
            start_time = start_time.replace(tzinfo=timezone.utc)
        else:
            start_time = start_time.astimezone(timezone.utc)

        source: list[dict] = []
        seen_ids: set[str] = set()
        next_value = 0
        while True:
            data = await self._request(
                "GET",
                "/api/v3/orders",
                params={
                    "limit": 1000,
                    "next": next_value,
                    "dateFrom": _utc_timestamp(start_time),
                    "dateTo": _utc_timestamp(end_time),
                },
            )
            batch = [item for item in data.get("orders") or [] if isinstance(item, dict)]
            for item in batch:
                order_id = item.get("id")
                if order_id in (None, ""):
                    continue
                key = str(order_id)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                source.append(item)
            new_next = int(data.get("next") or 0)
            if not batch or not new_next or new_next == next_value:
                break
            next_value = new_next

        # orders/new is kept as a safety net for very recent orders not yet visible in the dated list.
        new_data = await self._request("GET", "/api/v3/orders/new")
        for item in new_data.get("orders") or []:
            if not isinstance(item, dict):
                continue
            order_id = item.get("id")
            if order_id in (None, ""):
                continue
            key = str(order_id)
            if key not in seen_ids:
                seen_ids.add(key)
                source.append(item)

        status_map: dict[str, str] = {}
        try:
            updates = await self.fetch_order_status_updates([str(item.get("id")) for item in source if item.get("id") not in (None, "")])
            status_map = {update.posting_number: update.platform_status for update in updates}
        except Exception:
            status_map = {}

        supply_details = await self._fetch_supply_details(
            {str(item.get("supplyId") or "").strip() for item in source if isinstance(item, dict)}
        )

        orders: list[NormalizedOrder] = []
        for item in source:
            if not isinstance(item, dict):
                continue
            if _has_meta_requirements(item):
                continue
            order_id = item.get("id")
            if order_id in (None, ""):
                continue
            supply_id = str(item.get("supplyId") or "").strip()
            if supply_id and supply_id in supply_details:
                item = {**item, "supply": supply_details[supply_id]}
            payload = _normalize_order_payload(item)
            fulfillment_type = str(payload.get("fulfillment_type") or "FBS")
            is_overseas_warehouse = bool(payload.get("is_overseas_warehouse"))
            orders.append(
                NormalizedOrder(
                    platform_order_id=str(order_id),
                    platform_order_no=str(order_id),
                    posting_number=str(order_id),
                    platform_status=status_map.get(str(order_id)) or str(_first_value(item.get("supplierStatus"), item.get("status"), "new")),
                    raw_payload=payload,
                    fulfillment_type=fulfillment_type,
                    is_overseas_warehouse=is_overseas_warehouse,
                )
            )
        return orders

    async def _fetch_supply_details(self, supply_ids: set[str]) -> dict[str, dict]:
        details: dict[str, dict] = {}
        for supply_id in sorted(value for value in supply_ids if value):
            try:
                data = await self._request("GET", f"/api/v3/supplies/{supply_id}")
            except Exception:
                continue
            if isinstance(data, dict):
                details[supply_id] = data
        return details

    async def _create_supply(self) -> str:
        if self._auto_supply_id:
            return self._auto_supply_id
        name = str(self.settings.get("auto_supply_name") or "").strip()
        if not name:
            name = f"CaifuClaw AI {self.account_id} {datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        data = await self._request("POST", "/api/v3/supplies", json_body={"name": name})
        supply_id = _supply_id_from_response(data)
        if not supply_id:
            raise RuntimeError("Wildberries create supply failed: response did not contain supply id")
        self._auto_supply_id = supply_id
        return supply_id

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        order_ids = [_order_id_value(value) for value in posting_numbers if str(value or "").strip()]
        if not order_ids:
            return []
        results: list[OrderStatusUpdate] = []
        for offset in range(0, len(order_ids), 100):
            batch = order_ids[offset : offset + 100]
            data = await self._request("POST", "/api/v3/orders/status", json_body={"orders": batch})
            for item in data.get("orders") or []:
                if not isinstance(item, dict):
                    continue
                order_id = _first_value(item.get("id"), item.get("orderId"))
                if order_id in (None, ""):
                    continue
                supplier_status = str(_first_value(item.get("supplierStatus"), item.get("status")) or "")
                supply_id = str(_first_value(item.get("supplyId"), item.get("supply_id"), item.get("supplyID")) or "")
                if supply_id:
                    item = {**item, "supply_id": supply_id}
                results.append(
                    OrderStatusUpdate(
                        posting_number=str(order_id),
                        platform_order_id=str(order_id),
                        platform_order_no=str(order_id),
                        platform_status=supplier_status,
                        shipment_tracking_number="",
                        raw_payload=item,
                    )
                )
        return results

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        if self.settings.get("dry_run_fulfillment", False):
            return ShipmentResult(order.platform_order_id, "", "Wildberries", "dry_run_created", order.raw_payload)
        supply_id = _supply_id_from_payload(order.raw_payload)
        if not supply_id:
            supply_id = str(self.settings.get("supply_id") or "").strip()
        if not supply_id:
            supply_id = await self._create_supply()
        order_id = order.posting_number or order.platform_order_id
        if _payload_has_supply_assignment(order.raw_payload):
            data = {"supply_id": supply_id, "skipped_submit": True}
        else:
            data = await self._request(
                "PATCH",
                f"/api/marketplace/v3/supplies/{supply_id}/orders",
                json_body={"orders": [_order_id_value(order_id)]},
            )
        return ShipmentResult(
            platform_shipment_id=str(order_id),
            tracking_number="",
            carrier="Wildberries",
            status="created",
            raw_payload={"supply_id": supply_id, "response": data},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self.settings.get("dry_run_fulfillment", False):
            return LabelResult(
                content=build_preview_pdf(
                    "Wildberries Label Preview",
                    [f"Order: {order.platform_order_id}", f"Shipment: {shipment.platform_shipment_id}"],
                )
            )
        return await self.fetch_label_batch([order])

    async def fetch_label_batch(self, orders: list[NormalizedOrder]) -> LabelResult:
        if self.settings.get("dry_run_fulfillment", False):
            lines = [f"Order: {order.platform_order_id}" for order in orders[:10]]
            return LabelResult(content=build_preview_pdf("Wildberries Label Preview", lines))
        order_ids = []
        seen = set()
        for order in orders:
            value = order.posting_number or order.platform_order_id
            if value in (None, ""):
                continue
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            order_ids.append(_order_id_value(key))
        if not order_ids:
            raise RuntimeError("Wildberries sticker fetch failed: no order ids")

        if any(_is_cross_border_order_payload(order.raw_payload) for order in orders):
            if not all(_is_cross_border_order_payload(order.raw_payload) for order in orders):
                raise RuntimeError("Wildberries cross-border labels must be fetched separately from domestic stickers")
            stickers: list[dict] = []
            for offset in range(0, len(order_ids), 100):
                batch = order_ids[offset : offset + 100]
                data = await self._request(
                    "POST",
                    "/api/v3/orders/stickers/cross-border",
                    json_body={"orders": batch},
                )
                stickers.extend([item for item in data.get("stickers") or [] if isinstance(item, dict)])
            content, payload = _cross_border_sticker_pdf(stickers)
            return LabelResult(content=content, raw_payload=payload)

        stickers: list[dict] = []
        for offset in range(0, len(order_ids), 100):
            batch = order_ids[offset : offset + 100]
            data = await self._request(
                "POST",
                "/api/v3/orders/stickers",
                params={"type": "png", "width": 58, "height": 40},
                json_body={"orders": batch},
            )
            stickers.extend([item for item in data.get("stickers") or [] if isinstance(item, dict)])
        return LabelResult(content=_stickers_to_pdf(stickers), raw_payload=_sticker_metadata(stickers))
