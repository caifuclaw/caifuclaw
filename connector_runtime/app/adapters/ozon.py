import asyncio
from datetime import datetime, timedelta, timezone
from time import perf_counter

import httpx

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult


class OzonApiError(RuntimeError):
    def __init__(self, status_code: int, url: str, body: str) -> None:
        message = f"Ozon API HTTP {status_code} for {url}: {body}"
        super().__init__(message)
        self.status_code = status_code
        self.url = url
        self.body = body


def _ozon_timestamp(value: datetime) -> str:
    """Return an RFC3339 UTC timestamp accepted by Ozon protobuf APIs."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


class OzonConnector(MarketplaceConnector):
    platform = "ozon"
    TRAFFIC_RETRY_ATTEMPTS = 5
    TRAFFIC_RETRY_MAX_DELAY_SECONDS = 10

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.client_id = str(credentials["client_id"])
        self.api_key = credentials["api_key"]
        self.settings = settings or {}
        self.base_url = self.settings["base_url"]
        # account_id used for logging context; falls back to client_id when not supplied
        self.account_id = str(self.settings.get("account_id") or self.client_id)

    @property
    def headers(self) -> dict:
        return {
            "Client-Id": self.client_id,
            "Api-Key": self.api_key,
            "Content-Type": "application/json",
        }

    async def _post(self, path: str, payload: dict) -> dict | bytes:
        # Lazy import to avoid circular dependencies with models/database.
        from ..api_logger import log_api_call

        url = f"{self.base_url}{path}"
        started = perf_counter()
        try:
            async with httpx.AsyncClient(timeout=60) as client:
                response = await client.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "")
                if "application/pdf" in content_type or response.content.startswith(b"%PDF"):
                    log_api_call(
                        platform=self.platform,
                        account_id=self.account_id,
                        method="POST",
                        url=url,
                        request_body=payload,
                        response_status=response.status_code,
                        response_body={"_binary": True, "content_length": len(response.content)},
                        duration_ms=int((perf_counter() - started) * 1000),
                    )
                    return response.content
                body = response.json()
                log_api_call(
                    platform=self.platform,
                    account_id=self.account_id,
                    method="POST",
                    url=url,
                    request_body=payload,
                    response_status=response.status_code,
                    response_body=body,
                    duration_ms=int((perf_counter() - started) * 1000),
                )
                return body
        except httpx.HTTPStatusError as exc:
            err_text = exc.response.text if exc.response is not None else str(exc)
            status_code = exc.response.status_code if exc.response is not None else 0
            log_api_call(
                platform=self.platform,
                account_id=self.account_id,
                method="POST",
                url=url,
                request_body=payload,
                response_status=status_code or None,
                response_body=None,
                error_message=err_text[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise OzonApiError(status_code, url, err_text[:4000]) from exc
        except Exception as exc:
            log_api_call(
                platform=self.platform,
                account_id=self.account_id,
                method="POST",
                url=url,
                request_body=payload,
                response_status=None,
                response_body=None,
                error_message=str(exc)[:4000],
                duration_ms=int((perf_counter() - started) * 1000),
            )
            raise

    @staticmethod
    def _is_retryable_traffic_error(exc: Exception) -> bool:
        if isinstance(exc, httpx.TransportError):
            return True
        return isinstance(exc, OzonApiError) and (
            exc.status_code in {408, 425, 429} or exc.status_code >= 500
        )

    async def _traffic_post(self, path: str, payload: dict) -> dict | bytes:
        attempts = max(1, int(self.settings.get("traffic_retry_attempts", self.TRAFFIC_RETRY_ATTEMPTS)))
        max_delay = max(
            1,
            int(self.settings.get("traffic_retry_max_delay_seconds", self.TRAFFIC_RETRY_MAX_DELAY_SECONDS)),
        )
        for attempt in range(attempts):
            try:
                return await self._post(path, payload)
            except (OzonApiError, httpx.TransportError) as exc:
                if not self._is_retryable_traffic_error(exc) or attempt + 1 >= attempts:
                    raise
                await asyncio.sleep(min(2**attempt, max_delay))
        raise RuntimeError("Ozon traffic request retry loop exited unexpectedly")

    async def _fetch_negative_reviews(
        self,
        start: datetime,
        end: datetime,
    ) -> dict[tuple[str, str], int] | None:
        counts: dict[tuple[str, str], int] = {}
        last_id = ""
        start_date = start.date().isoformat()
        end_date = end.date().isoformat()
        for _ in range(200):
            payload: dict[str, object] = {"limit": 100, "sort_dir": "DESC"}
            if last_id:
                payload["last_id"] = last_id
            try:
                response = await self._post("/v1/review/list", payload)
            except (OzonApiError, httpx.HTTPError):
                return None
            if not isinstance(response, dict):
                return None
            reviews = response.get("reviews") if isinstance(response.get("reviews"), list) else []
            oldest_date = ""
            for review in reviews:
                if not isinstance(review, dict):
                    continue
                published_at = str(review.get("published_at") or "")[:10]
                if not published_at:
                    continue
                oldest_date = min(oldest_date or published_at, published_at)
                if published_at < start_date or published_at > end_date:
                    continue
                try:
                    rating = int(review.get("rating") or 0)
                except (TypeError, ValueError):
                    continue
                if 0 < rating <= 2:
                    sku = str(review.get("sku") or "").strip()
                    if sku:
                        key = (published_at, sku)
                        counts[key] = counts.get(key, 0) + 1
            if not reviews or (oldest_date and oldest_date < start_date):
                break
            if not response.get("has_next"):
                break
            next_id = str(response.get("last_id") or "").strip()
            if not next_id or next_id == last_id:
                break
            last_id = next_id
            await asyncio.sleep(0.2)
        return counts

    async def fetch_traffic(self, start: datetime, end: datetime) -> list[dict]:
        metric_names = [
            "hits_view_search",
            "hits_view_pdp",
            "hits_tocart_search",
            "hits_tocart_pdp",
            "ordered_units",
            "revenue",
        ]
        limit = 1000
        offset = 0
        rows: list[dict] = []
        while True:
            payload = {
                "date_from": start.date().isoformat(),
                "date_to": end.date().isoformat(),
                "metrics": metric_names,
                "dimension": ["day", "sku"],
                "filters": [],
                "sort": [{"key": "hits_view_search", "order": "DESC"}],
                "limit": limit,
                "offset": offset,
            }
            response = await self._traffic_post("/v1/analytics/data", payload)
            if not isinstance(response, dict):
                raise RuntimeError("Ozon analytics returned an unexpected response")
            result = response.get("result") if isinstance(response, dict) else {}
            data = result.get("data") if isinstance(result, dict) else []
            page = data if isinstance(data, list) else []
            for item in page:
                dimensions = item.get("dimensions") if isinstance(item, dict) else []
                metrics = item.get("metrics") if isinstance(item, dict) else []
                if not isinstance(dimensions, list) or len(dimensions) < 2 or not isinstance(metrics, list):
                    continue
                day = str((dimensions[0] or {}).get("id") or (dimensions[0] or {}).get("name") or "")[:10]
                sku_dimension = dimensions[1] if isinstance(dimensions[1], dict) else {}
                if not day:
                    continue
                values = list(metrics) + [0] * max(0, len(metric_names) - len(metrics))
                rows.append(
                    {
                        "source": "organic",
                        "grain": "daily",
                        "stat_date": day,
                        "period_start": day,
                        "period_end": day,
                        "region": "",
                        "entity_type": "sku",
                        "entity_id": str(sku_dimension.get("id") or ""),
                        "sku": str(sku_dimension.get("id") or ""),
                        "product_name": str(sku_dimension.get("name") or ""),
                        "impressions": int(values[0] or 0),
                        "clicks": int(values[1] or 0),
                        "add_to_cart": int(values[2] or 0) + int(values[3] or 0),
                        "orders": int(values[4] or 0),
                        "units_sold": int(values[4] or 0),
                        "revenue": float(values[5] or 0),
                        "currency": "RUB",
                        "raw_data": {"dimensions": dimensions},
                    }
                )
            if len(page) < limit:
                break
            offset += limit
            await asyncio.sleep(1.1)
            if offset >= 200_000:
                raise RuntimeError("Ozon analytics pagination exceeded the safety limit")

        negative_reviews = await self._fetch_negative_reviews(start, end)
        for row in rows:
            raw_data = row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}
            day = str(row.get("stat_date") or "")[:10]
            ozon_sku = str(row.get("entity_id") or "")
            row["negative_reviews"] = (
                negative_reviews.get((day, ozon_sku), 0)
                if negative_reviews is not None
                else None
            )
            row["raw_data"] = {
                **raw_data,
                "negative_reviews_source": "ozon_reviews" if negative_reviews is not None else "unavailable",
            }

        product_metadata = await self.fetch_product_metadata_by_sku(
            [str(row.get("entity_id") or "") for row in rows]
        )
        for row in rows:
            ozon_sku = str(row.get("entity_id") or "")
            metadata = product_metadata.get(ozon_sku, {})
            offer_id = str(metadata.get("offer_id") or "")
            row["sku"] = offer_id
            row["raw_data"] = {
                **(row.get("raw_data") if isinstance(row.get("raw_data"), dict) else {}),
                "ozon_sku": ozon_sku,
                "offer_id": offer_id,
                "platform_category_id": str(metadata.get("platform_category_id") or ""),
                "platform_category_name": "",
                "platform_category_path": "",
                "description_category_id": str(metadata.get("description_category_id") or ""),
                "type_id": str(metadata.get("type_id") or ""),
            }
        return rows

    async def fetch_offer_ids_by_sku(self, skus: list[str]) -> dict[str, str]:
        metadata = await self.fetch_product_metadata_by_sku(skus)
        return {
            sku: str(item.get("offer_id") or "")
            for sku, item in metadata.items()
            if str(item.get("offer_id") or "")
        }

    async def fetch_product_metadata_by_sku(self, skus: list[str]) -> dict[str, dict]:
        normalized_skus = list(
            dict.fromkeys(str(sku or "").strip() for sku in skus if str(sku or "").strip())
        )
        result: dict[str, dict] = {}
        for index in range(0, len(normalized_skus), 1000):
            batch = normalized_skus[index : index + 1000]
            response = await self._traffic_post(
                "/v3/product/info/list",
                {"offer_id": [], "product_id": [], "sku": batch},
            )
            if not isinstance(response, dict):
                raise RuntimeError("Ozon product info returned an unexpected response")
            items = response.get("items")
            for item in items if isinstance(items, list) else []:
                if not isinstance(item, dict):
                    continue
                ozon_sku = str(item.get("sku") or "").strip()
                if not ozon_sku:
                    continue
                description_category_id = str(item.get("description_category_id") or "").strip()
                type_id = str(item.get("type_id") or "").strip()
                platform_category_id = (
                    f"{description_category_id}:{type_id}"
                    if description_category_id and type_id
                    else description_category_id or (f"type:{type_id}" if type_id else "")
                )
                result[ozon_sku] = {
                    "offer_id": str(item.get("offer_id") or "").strip(),
                    "description_category_id": description_category_id,
                    "type_id": type_id,
                    "platform_category_id": platform_category_id,
                }
        return result

    @staticmethod
    def _detect_fulfillment_type(posting: dict) -> str:
        """基于响应字段识别履约类型。
        优先级：
        1. delivery_schema == 'fbo' -> FBO（当前 FBS 接口不会返回，预留判断）
        2. tpl_provider 包含 'FBP' -> FBP
        3. 其他 -> FBS
        """
        ds = str(posting.get("delivery_schema") or "").lower()
        if ds == "fbo":
            return "FBO"
        dm = posting.get("delivery_method") or {}
        ad = posting.get("analytics_data") or {}
        tpl = str(dm.get("tpl_provider") or ad.get("tpl_provider") or "")
        if "fbp" in tpl.lower():
            return "FBP"
        return "FBS"

    async def get_products_by_offer_ids(self, offer_ids: list[str]) -> dict:
        normalized_offer_ids = list(
            dict.fromkeys(str(offer_id or "").strip() for offer_id in offer_ids if str(offer_id or "").strip())
        )
        if not normalized_offer_ids:
            return {"items": []}
        data = await self._post(
            "/v3/product/info/list",
            {"offer_id": normalized_offer_ids[:1000], "product_id": [], "sku": []},
        )
        return data if isinstance(data, dict) else {"items": []}

    @staticmethod
    def _catalog_items(payload: dict | bytes) -> list[dict]:
        if not isinstance(payload, dict):
            return []
        for key in ("items", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
            if isinstance(value, dict) and isinstance(value.get("items"), list):
                return [item for item in value["items"] if isinstance(item, dict)]
        return []

    @staticmethod
    def _catalog_price(item: dict) -> str:
        price = item.get("price")
        if isinstance(price, dict):
            for key in ("price", "marketing_price", "auto_action_min_price", "recommended_price"):
                if price.get(key) not in (None, ""):
                    return str(price[key])
        for key in ("price", "marketing_price", "premium_price", "min_ozon_price"):
            if item.get(key) not in (None, ""):
                return str(item[key])
        return ""

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        """Return one normalized Ozon listing row per seller warehouse stock."""
        listing_rows: list[dict] = []
        last_id = ""
        for _ in range(200):
            payload = {
                "filter": {"offer_id": [], "product_id": [], "visibility": "ALL"},
                "last_id": last_id,
                "limit": 1000,
            }
            response = await self._post("/v3/product/list", payload)
            page = self._catalog_items(response)
            listing_rows.extend(page)
            next_last_id = str(response.get("last_id") or "") if isinstance(response, dict) else ""
            if not page or not next_last_id or next_last_id == last_id:
                break
            last_id = next_last_id
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("Ozon product catalog pagination exceeded the safety limit")

        offer_ids = list(dict.fromkeys(str(row.get("offer_id") or "").strip() for row in listing_rows if row.get("offer_id")))
        info_by_offer: dict[str, dict] = {}
        for index in range(0, len(offer_ids), 1000):
            response = await self._post(
                "/v3/product/info/list",
                {"offer_id": offer_ids[index : index + 1000], "product_id": [], "sku": []},
            )
            for row in self._catalog_items(response):
                offer_id = str(row.get("offer_id") or "").strip()
                if offer_id:
                    info_by_offer[offer_id] = row

        price_by_product: dict[str, dict] = {}
        cursor = ""
        for _ in range(200):
            response = await self._post(
                "/v5/product/info/prices",
                {
                    "filter": {"offer_id": [], "product_id": [], "visibility": "ALL"},
                    "cursor": cursor,
                    "limit": 1000,
                },
            )
            page = self._catalog_items(response)
            for row in page:
                key = str(row.get("product_id") or row.get("id") or "").strip()
                if key:
                    price_by_product[key] = row
            next_cursor = str(response.get("cursor") or "") if isinstance(response, dict) else ""
            if not page or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(0.1)

        stocks_by_product: dict[str, list[dict]] = {}
        cursor = ""
        for _ in range(200):
            response = await self._post(
                "/v4/product/info/stocks",
                {
                    "filter": {"offer_id": [], "product_id": [], "visibility": "ALL"},
                    "cursor": cursor,
                    "limit": 1000,
                },
            )
            page = self._catalog_items(response)
            for row in page:
                key = str(row.get("product_id") or "").strip()
                if key:
                    stocks_by_product[key] = row.get("stocks") if isinstance(row.get("stocks"), list) else []
            next_cursor = str(response.get("cursor") or "") if isinstance(response, dict) else ""
            if not page or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
            await asyncio.sleep(0.1)

        normalized: list[dict] = []
        for listing in listing_rows:
            offer_id = str(listing.get("offer_id") or "").strip()
            info = info_by_offer.get(offer_id, {})
            product_id = str(info.get("id") or info.get("product_id") or listing.get("product_id") or "").strip()
            if not product_id and not offer_id:
                continue
            price_data = price_by_product.get(product_id, {})
            price = self._catalog_price(price_data)
            status = str(info.get("status") or listing.get("status") or "")
            base = {
                "platform_product_id": product_id,
                "platform_sku": offer_id or str(info.get("sku") or ""),
                "product_name": str(info.get("name") or listing.get("name") or ""),
                "listing_status": status,
                "fulfillment_type": str(info.get("fbo_sku") and "FBO" or "FBS"),
                "logistics_type": str(info.get("delivery_schema") or ""),
                "price_amount": price,
                "price_currency": str(price_data.get("currency_code") or "RUB"),
                "raw_payload": {"listing": listing, "info": info, "price": price_data},
            }
            stocks = stocks_by_product.get(product_id, [])
            if not stocks:
                normalized.append({**base, "warehouse_code": "", "warehouse_name": "", "available_stock": 0})
                continue
            for stock in stocks:
                if not isinstance(stock, dict):
                    continue
                sellable_stock = stock.get("free_to_sell_amount")
                if sellable_stock is None:
                    sellable_stock = stock.get("present", 0)
                normalized.append(
                    {
                        **base,
                        "warehouse_code": str(stock.get("warehouse_id") or stock.get("warehouse_name") or ""),
                        "warehouse_name": str(stock.get("warehouse_name") or ""),
                        "available_stock": sellable_stock,
                        "reserved_stock": stock.get("reserved_amount"),
                        "raw_payload": {**base["raw_payload"], "stock": stock},
                    }
                )
        return normalized

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        # Use /v4/posting/fbs/list (cursor 分页，响应含 delivery_schema)
        # 覆盖所有状态，用 since/to 时间窗口定位 posting 变更时间。
        now = datetime.now(timezone.utc)
        
        # 增量同步：如果提供了 since 时间，使用该时间；否则使用配置的 lookback_days
        if since:
            # 增量模式：从上次同步时间开始，但为了避免边界问题，往前回溯 1 小时
            since_time = since - timedelta(hours=1)
        else:
            # 首次同步：使用配置的 lookback_days
            lookback_days = int(self.settings.get("lookback_days", 30))
            since_time = now - timedelta(days=lookback_days)

        # 店铺级配置：fbo_fbp_download_mode ∈ {'none','to_unshipped','to_completed'}
        download_mode = str(self.settings.get("fbo_fbp_download_mode") or "none").lower()

        orders: list[NormalizedOrder] = []
        cursor: str | None = None
        page_size = 100

        while True:
            payload = {
                "dir": "ASC",
                "filter": {
                    "since": _ozon_timestamp(since_time),
                    "to": _ozon_timestamp(now),
                },
                "limit": page_size,
                "with": {"analytics_data": True, "barcodes": False, "financial_data": True},
            }
            if cursor:
                payload["cursor"] = cursor

            data = await self._post("/v4/posting/fbs/list", payload)
            if not isinstance(data, dict):
                break
            # v4 响应结构：postings 直接在顶层，也兼容旧版 result.postings
            postings = data.get("postings") or data.get("result", {}).get("postings", []) or []
            if not postings:
                break

            for posting in postings:
                order_id = posting.get("order_id")
                order_number = posting.get("order_number")
                posting_number = posting.get("posting_number")
                if not posting_number or order_id is None:
                    continue
                ftype = self._detect_fulfillment_type(posting)
                # 根据配置过滤 FBO/FBP：当 download_mode='none' 时跳过这两类
                if ftype in ("FBO", "FBP") and download_mode == "none":
                    continue
                platform_status = str(posting.get("status") or "")
                # 过滤：cancelled 且客户 ID 为空且无 cancellation 详情的订单（视为测试单/风控单）
                # 注：Ozon 对客户主动取消的真实作废单会把 customer 置 null，
                # 但会保留 cancellation.cancel_reason / cancellation_initiator，
                # 因此加上 cancellation 详情判断能区分真实作废单与测试单。
                if platform_status.lower() in ("cancelled", "cancelled_by_seller"):
                    customer = posting.get("customer") or posting.get("buyer") or posting.get("user") or {}
                    buyer_id = (
                        customer.get("id")
                        or customer.get("customer_id")
                        or posting.get("customer_id")
                        or posting.get("buyer_id")
                    )
                    if not buyer_id:
                        cancellation = posting.get("cancellation") or {}
                        has_cancellation_detail = bool(
                            cancellation.get("cancel_reason")
                            or cancellation.get("cancellation_initiator")
                            or cancellation.get("cancel_reason_id")
                        )
                        if not has_cancellation_detail:
                            continue
                orders.append(
                    NormalizedOrder(
                        platform_order_id=str(order_id),
                        platform_order_no=str(order_number or ""),
                        posting_number=str(posting_number),
                        platform_status=platform_status,
                        raw_payload=posting,
                        fulfillment_type=ftype,
                        is_overseas_warehouse=ftype in {"FBO", "FBP"},
                    )
                )
            cursor = data.get("cursor")
            has_next = bool(data.get("has_next", False))
            if not has_next or not cursor:
                break
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        """Batch query order statuses via /v3/posting/fbs/list using since/to time window.
        If posting_numbers is provided, we use /v3/posting/fbs/get for each;
        otherwise fall back to listing recent orders by time range."""
        results: list[OrderStatusUpdate] = []
        if not posting_numbers:
            return results

        # Strategy: batch via /v3/posting/fbs/list with time window covering recent N days
        now = datetime.now(timezone.utc)
        lookback_days = int(self.settings.get("status_sync_lookback_days", 30))
        since = now - timedelta(days=lookback_days)
        offset = 0
        page_size = 100
        target_set = set(posting_numbers)
        found = set()

        while True:
            payload = {
                "dir": "DESC",
                "filter": {
                    "since": _ozon_timestamp(since),
                    "to": _ozon_timestamp(now),
                },
                "limit": page_size,
                "offset": offset,
                "with": {"analytics_data": False, "barcodes": False, "financial_data": False},
            }
            data = await self._post("/v3/posting/fbs/list", payload)
            postings = data.get("result", {}).get("postings", []) if isinstance(data, dict) else []
            for posting in postings:
                pn = posting.get("posting_number") or ""
                if pn in target_set:
                    shipping = posting.get("shipping") if isinstance(posting.get("shipping"), dict) else {}
                    shipment = posting.get("shipment") if isinstance(posting.get("shipment"), dict) else {}
                    tracking_number = str(
                        posting.get("tracking_number")
                        or posting.get("trackingNumber")
                        or shipping.get("tracking_number")
                        or shipping.get("trackingNumber")
                        or shipment.get("tracking_number")
                        or shipment.get("trackingNumber")
                        or ""
                    )
                    results.append(OrderStatusUpdate(
                        posting_number=pn,
                        platform_order_id=str(posting.get("order_id", "")),
                        platform_status=str(posting.get("status") or ""),
                        platform_order_no=str(posting.get("order_number") or ""),
                        shipment_tracking_number=tracking_number,
                        raw_payload=posting,
                    ))
                    found.add(pn)
            if len(postings) < page_size:
                break
            # If all targets found, stop early
            if found >= target_set:
                break
            offset += page_size

        return results

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        posting_number = order.posting_number or order.raw_payload.get("posting_number") or order.platform_order_id
        if self.settings.get("dry_run_fulfillment", False):
            raw = order.raw_payload
            return ShipmentResult(
                platform_shipment_id=str(posting_number),
                tracking_number=str(raw.get("tracking_number") or posting_number),
                carrier=str(raw.get("delivery_method", {}).get("name") or "Ozon"),
                status="dry_run_created",
                raw_payload=raw,
            )

        products = []
        for product in order.raw_payload.get("products", []):
            products.append({"product_id": product.get("sku"), "quantity": product.get("quantity", 1)})
        payload = {"packages": [{"products": products}], "posting_number": posting_number}
        data = await self._post("/v4/posting/fbs/ship", payload)
        return ShipmentResult(
            platform_shipment_id=str(posting_number),
            tracking_number=str(data.get("tracking_number") or data.get("trackingNumber") or ""),
            carrier="Ozon",
            status="created",
            raw_payload=data if isinstance(data, dict) else {},
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        posting_number = order.posting_number or order.raw_payload.get("posting_number") or order.platform_order_id
        if self.settings.get("dry_run_fulfillment", False):
            from reportlab.lib.pagesizes import A6
            from reportlab.pdfgen import canvas
            from io import BytesIO

            buffer = BytesIO()
            pdf = canvas.Canvas(buffer, pagesize=A6)
            pdf.setFont("Helvetica-Bold", 14)
            pdf.drawString(24, 370, "Ozon FBS Label Preview")
            pdf.setFont("Helvetica", 10)
            pdf.drawString(24, 340, f"Posting: {posting_number}")
            pdf.drawString(24, 322, f"Tracking: {shipment.tracking_number}")
            pdf.drawString(24, 304, "Dry-run label. Not for shipping.")
            pdf.showPage()
            pdf.save()
            return LabelResult(content=buffer.getvalue())

        payload = {"posting_number": [posting_number]}
        content = await self._post("/v2/posting/fbs/package-label", payload)
        if not isinstance(content, bytes):
            raise RuntimeError(f"Ozon label endpoint returned JSON instead of PDF: {content}")
        return LabelResult(content=content)

    async def fetch_label_batch(self, orders: list[NormalizedOrder]) -> LabelResult:
        """批量从 Ozon 拉取真实面单 PDF（强制调平台接口，不走 dry-run）。
        Ozon POST /v2/posting/fbs/package-label 支持批量 posting_number，返回合并 PDF。"""
        postings: list[str] = []
        seen: set[str] = set()
        for order in orders:
            pn = order.posting_number or (order.raw_payload or {}).get("posting_number") or order.platform_order_id
            pn = str(pn or "").strip()
            if pn and pn not in seen:
                seen.add(pn)
                postings.append(pn)
        if not postings:
            raise RuntimeError("批量面单拉取失败：没有可用的 posting_number")
        payload = {"posting_number": postings}
        content = await self._post("/v2/posting/fbs/package-label", payload)
        if not isinstance(content, bytes):
            raise RuntimeError(f"Ozon 面单接口返回非 PDF 响应：{content}")
        return LabelResult(content=content)
