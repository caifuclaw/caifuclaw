# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from .base import LabelResult, MarketplaceConnector, NormalizedOrder, OrderStatusUpdate, ShipmentResult
from .pdf_preview import build_preview_pdf


MERCADO_CBT_SITES = {"CBT", "CBT_MERCADOLIBRE", "GLOBAL", "GLOBAL_SELLING"}
MERCADO_CBT_STORE_TYPES = {"cbt", "cross_border", "crossborder", "global", "global_selling", "semi_managed", "semi-managed", "half_managed"}
MERCADO_LOCAL_SITES = {"MLA", "MLB", "MLC", "MCO", "MEC", "MLM", "MPE", "MLU"}


class MercadoGlobalConnector(MarketplaceConnector):
    platform = "mercadolibre"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.access_token = credentials.get("access_token", "")
        self.seller_id = str(credentials.get("seller_id") or credentials.get("user_id") or "")
        self.settings = settings or {}
        self.base_url = self.settings["base_url"].rstrip("/")
        self.site = str(self.settings.get("mercado_site") or self.settings.get("site") or "").upper()
        self.store_type = str(
            self.settings.get("mercado_store_type")
            or self.settings.get("store_type")
            or credentials.get("mercado_store_type")
            or credentials.get("store_type")
            or ""
        ).lower()
        self.api_mode = self._resolve_api_mode()
        self._traffic_request_lock = asyncio.Lock()
        self._next_traffic_request_at = 0.0

    @property
    def headers(self) -> dict:
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    async def fetch_platform_products(self, since: datetime | None = None) -> list[dict]:
        if not self.seller_id:
            raise ValueError("MercadoLibre seller_id is required for product catalog synchronization")
        item_ids: list[str] = []
        scroll_id = ""
        async with httpx.AsyncClient(timeout=self._request_timeout()) as client:
            for _ in range(200):
                params = {"search_type": "scan", "limit": 100}
                if scroll_id:
                    params["scroll_id"] = scroll_id
                response = await self._traffic_get(client, f"/users/{self.seller_id}/items/search", params=params)
                response.raise_for_status()
                payload = response.json()
                page = payload.get("results") if isinstance(payload, dict) else []
                page = [str(item) for item in page if item] if isinstance(page, list) else []
                item_ids.extend(page)
                next_scroll_id = str(payload.get("scroll_id") or "") if isinstance(payload, dict) else ""
                if not page or not next_scroll_id or next_scroll_id == scroll_id:
                    break
                scroll_id = next_scroll_id
            else:
                raise RuntimeError("MercadoLibre product catalog pagination exceeded the safety limit")

            item_details: list[dict] = []
            for index in range(0, len(item_ids), 20):
                response = await self._traffic_get(
                    client,
                    "/items",
                    params={
                        "ids": ",".join(item_ids[index : index + 20]),
                        "attributes": "id,title,status,seller_custom_field,price,currency_id,available_quantity,pictures,thumbnail,permalink,variations",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                for entry in payload if isinstance(payload, list) else []:
                    body = entry.get("body") if isinstance(entry, dict) else {}
                    if isinstance(body, dict) and body.get("id"):
                        item_details.append(body)

        normalized: list[dict] = []
        for item in item_details:
            parent_id = str(item.get("id") or "").strip()
            variants = item.get("variations") if isinstance(item.get("variations"), list) else []
            variants = [value for value in variants if isinstance(value, dict)]
            if not variants:
                variants = [{}]
            for variation in variants:
                variant_id = str(variation.get("id") or parent_id).strip()
                sku = str(
                    variation.get("seller_custom_field")
                    or variation.get("seller_sku")
                    or item.get("seller_custom_field")
                    or parent_id
                ).strip()
                normalized.append(
                    {
                        "platform_product_id": variant_id,
                        "platform_sku": sku,
                        "product_name": str(item.get("title") or ""),
                        "listing_status": str(item.get("status") or ""),
                        "warehouse_code": "",
                        "warehouse_name": "",
                        "available_stock": variation.get("available_quantity", item.get("available_quantity", 0)),
                        "price_amount": variation.get("price", item.get("price")),
                        "price_currency": str(variation.get("currency_id") or item.get("currency_id") or "USD"),
                        "raw_payload": {"item": item, "variation": variation},
                    }
                )
        return normalized

    async def fetch_traffic(self, start: datetime, end: datetime) -> list[dict]:
        if not self.seller_id:
            raise ValueError("MercadoLibre seller_id is required for traffic analytics")
        timeout = self._request_timeout()
        async with httpx.AsyncClient(timeout=timeout) as client:
            parent_ids: list[str] = []
            scroll_id = ""
            for _ in range(200):
                params = {"search_type": "scan", "status": "active", "limit": 100}
                if scroll_id:
                    params = {"search_type": "scan", "scroll_id": scroll_id, "limit": 100}
                response = await self._traffic_get(
                    client,
                    f"/users/{self.seller_id}/items/search",
                    params=params,
                )
                response.raise_for_status()
                payload = response.json()
                results = payload.get("results") if isinstance(payload, dict) else []
                page = [str(item) for item in results or [] if item]
                parent_ids.extend(page)
                next_scroll = str(payload.get("scroll_id") or "") if isinstance(payload, dict) else ""
                if len(page) < 100 or not next_scroll:
                    break
                scroll_id = next_scroll

            parent_details: dict[str, dict] = {}
            for index in range(0, len(parent_ids), 20):
                batch = parent_ids[index : index + 20]
                try:
                    response = await self._traffic_get(
                        client,
                        "/items",
                        params={
                            "ids": ",".join(batch),
                            "attributes": "id,title,seller_custom_field,site_id,category_id,variations",
                        },
                    )
                    response.raise_for_status()
                    detail_payload = response.json()
                except (RuntimeError, httpx.HTTPError, ValueError):
                    # Product metadata enriches rows but is not required for traffic totals.
                    continue
                for entry in detail_payload if isinstance(detail_payload, list) else []:
                    body = entry.get("body") if isinstance(entry, dict) else {}
                    if not isinstance(body, dict) or not body.get("id"):
                        continue
                    variations = body.get("variations") if isinstance(body.get("variations"), list) else []
                    variation_sku = next(
                        (
                            str(item.get("seller_sku") or item.get("seller_custom_field"))
                            for item in variations
                            if item.get("seller_sku") or item.get("seller_custom_field")
                        ),
                        "",
                    )
                    parent_details[str(body["id"])] = {
                        "sku": str(body.get("seller_sku") or body.get("seller_custom_field") or variation_sku or ""),
                        "title": str(body.get("title") or ""),
                        "category_id": str(body.get("category_id") or ""),
                    }

            semaphore = asyncio.Semaphore(20)

            async def marketplace_items(parent_id: str) -> list[tuple[str, str, str]]:
                async with semaphore:
                    try:
                        response = await self._traffic_get(
                            client,
                            f"/items/{parent_id}/marketplace_items",
                            retry_attempts=4,
                            retry_max_delay_seconds=10,
                        )
                        if response.status_code == 404:
                            return []
                        response.raise_for_status()
                        payload = response.json()
                    except (RuntimeError, httpx.HTTPError, ValueError):
                        # A single unavailable mapping must not discard the whole shop sync.
                        return []
                items = payload.get("marketplace_items") if isinstance(payload, dict) else payload
                mapped: list[tuple[str, str, str]] = []
                for item in items if isinstance(items, list) else []:
                    child_id = str(item.get("item_id") or item.get("id") or "") if isinstance(item, dict) else ""
                    if not child_id:
                        continue
                    site_id = str(item.get("site_id") or child_id[:3]).upper()
                    mapped.append((child_id, parent_id, site_id))
                return mapped

            mapped_pages = await asyncio.gather(*(marketplace_items(parent_id) for parent_id in parent_ids))
            child_map = {
                child_id: {"parent_id": parent_id, "region": site_id}
                for page in mapped_pages
                for child_id, parent_id, site_id in page
            }
            child_ids = list(child_map)
            child_ids_by_region: dict[str, list[str]] = {}
            for child_id, mapping in child_map.items():
                region = str(mapping.get("region") or "UNKNOWN").upper()
                child_ids_by_region.setdefault(region, []).append(child_id)
            period_days = max(1, (end.date() - start.date()).days + 1)

            child_details: dict[str, dict] = {}
            for index in range(0, len(child_ids), 20):
                batch = child_ids[index : index + 20]
                try:
                    response = await self._traffic_get(
                        client,
                        "/items",
                        params={
                            "ids": ",".join(batch),
                            "attributes": "id,title,seller_custom_field,seller_sku,site_id,category_id,variations",
                        },
                    )
                    response.raise_for_status()
                    detail_payload = response.json()
                except (RuntimeError, httpx.HTTPError, ValueError):
                    # Product metadata enriches rows but is not required for traffic totals.
                    continue
                for entry in detail_payload if isinstance(detail_payload, list) else []:
                    body = entry.get("body") if isinstance(entry, dict) else {}
                    if not isinstance(body, dict) or not body.get("id"):
                        continue
                    variations = body.get("variations") if isinstance(body.get("variations"), list) else []
                    variation_sku = next(
                        (
                            str(item.get("seller_sku") or item.get("seller_custom_field"))
                            for item in variations
                            if item.get("seller_sku") or item.get("seller_custom_field")
                        ),
                        "",
                    )
                    child_details[str(body["id"])] = {
                        "sku": str(body.get("seller_sku") or body.get("seller_custom_field") or variation_sku or ""),
                        "title": str(body.get("title") or ""),
                        "category_id": str(body.get("category_id") or ""),
                    }

            category_ids = {
                str(
                    child_details.get(child_id, {}).get("category_id")
                    or parent_details.get(str(mapping["parent_id"]), {}).get("category_id")
                    or ""
                )
                for child_id, mapping in child_map.items()
            }
            category_metadata = await self._traffic_category_metadata(
                client,
                sorted(category_id for category_id in category_ids if category_id),
            )

            review_data: dict[str, dict] = {}

            async def fetch_period_visits(period_end) -> tuple[dict[str, int], dict[str, dict]]:
                visits: dict[str, int] = {}
                visit_request_lock = asyncio.Lock()
                next_visit_request_at = 0.0
                request_interval = max(0.1, float(self.settings.get("traffic_request_interval_seconds", 0.35)))

                async def fetch_visit_batch(batch: list[str]) -> None:
                    nonlocal next_visit_request_at
                    response = None
                    last_error: Exception | None = None
                    for attempt in range(10):
                        try:
                            async with visit_request_lock:
                                loop = asyncio.get_running_loop()
                                wait_seconds = next_visit_request_at - loop.time()
                                if wait_seconds > 0:
                                    await asyncio.sleep(wait_seconds)
                                response = await client.get(
                                    f"{self.base_url}/items/visits/time_window",
                                    headers=self.headers,
                                    params={
                                        "ids": ",".join(batch),
                                        "last": period_days,
                                        "unit": "day",
                                        "ending": period_end.isoformat(),
                                    },
                                )
                                next_visit_request_at = loop.time() + request_interval
                                if response.status_code == 429 or response.status_code >= 500:
                                    retry_after = response.headers.get("Retry-After")
                                    try:
                                        delay = float(retry_after) if retry_after else min(2**attempt, 60)
                                    except (TypeError, ValueError):
                                        delay = min(2**attempt, 60)
                                    next_visit_request_at = max(next_visit_request_at, loop.time() + max(1, delay))
                        except Exception as exc:
                            last_error = exc
                            async with visit_request_lock:
                                loop = asyncio.get_running_loop()
                                next_visit_request_at = max(
                                    next_visit_request_at,
                                    loop.time() + max(1, min(2**attempt, 60)),
                                )
                            if attempt == 9:
                                raise RuntimeError(
                                    "MercadoLibre visits API network request failed after 10 attempts: "
                                    f"{type(exc).__name__}: {exc}"
                                ) from exc
                            continue
                        retryable = response.status_code == 429 or response.status_code >= 500
                        if not retryable or attempt == 9:
                            break
                    if response is None:
                        raise RuntimeError(
                            "MercadoLibre visits API returned no response"
                            + (f": {type(last_error).__name__}: {last_error}" if last_error else "")
                        )
                    if response.status_code in {400, 404, 429} or response.status_code >= 500:
                        if len(batch) == 1:
                            raise RuntimeError(
                                f"MercadoLibre visits API HTTP {response.status_code} for {batch[0]}"
                            )
                        midpoint = len(batch) // 2
                        await fetch_visit_batch(batch[:midpoint])
                        await fetch_visit_batch(batch[midpoint:])
                        return
                    response.raise_for_status()
                    payload = response.json()
                    items = payload if isinstance(payload, list) else payload.get("results", []) if isinstance(payload, dict) else []
                    for item in items:
                        if isinstance(item, dict) and item.get("item_id"):
                            visits[str(item["item_id"])] = int(item.get("total_visits") or 0)

                async def fetch_site_visits(region: str, site_child_ids: list[str]) -> tuple[str, dict]:
                    errors: dict[str, str] = {}

                    async def fetch_item(child_id: str) -> None:
                        try:
                            # MercadoLibre currently accepts only one item ID per time-window request.
                            await fetch_visit_batch([child_id])
                        except Exception as exc:
                            errors[child_id] = f"{type(exc).__name__}: {exc}"[:300]

                    await asyncio.gather(*(fetch_item(child_id) for child_id in site_child_ids))
                    missing_ids = [child_id for child_id in site_child_ids if child_id not in visits]
                    for child_id in missing_ids:
                        errors.setdefault(child_id, "visits API returned no value")
                    return region, {
                        "expected": len(site_child_ids),
                        "received": len(site_child_ids) - len(missing_ids),
                        "missing": len(missing_ids),
                        "error_samples": [errors[child_id] for child_id in missing_ids[:3]],
                    }

                site_results = await asyncio.gather(
                    *(
                        fetch_site_visits(region, site_child_ids)
                        for region, site_child_ids in child_ids_by_region.items()
                    )
                )
                return visits, dict(site_results)

            past_end = start.date() - timedelta(days=1)
            past_start = past_end - timedelta(days=period_days - 1)
            period_values = []
            for period_start, period_end in ((start.date(), end.date()), (past_start, past_end)):
                visits, site_health = await fetch_period_visits(period_end)
                period_values.append((period_start, period_end, visits, site_health))

            if self.settings.get("fetch_traffic_reviews", True) is not False:
                review_child_ids = sorted(child_map)
                review_request_lock = asyncio.Lock()
                next_review_request_at = 0.0
                review_request_interval = max(
                    0.1,
                    float(self.settings.get("traffic_review_request_interval_seconds", 0.5)),
                )

                async def fetch_review_page(child_id: str, offset: int) -> dict | None:
                    nonlocal next_review_request_at
                    for attempt in range(4):
                        try:
                            async with review_request_lock:
                                loop = asyncio.get_running_loop()
                                wait_seconds = next_review_request_at - loop.time()
                                if wait_seconds > 0:
                                    await asyncio.sleep(wait_seconds)
                                response = await client.get(
                                    f"{self.base_url}/reviews/item/{child_id}",
                                    headers=self.headers,
                                    params={"rating": "negative", "limit": 100, "offset": offset},
                                )
                                next_review_request_at = loop.time() + review_request_interval
                                if response.status_code == 429:
                                    retry_after = response.headers.get("Retry-After")
                                    try:
                                        delay = float(retry_after) if retry_after else min(2 ** attempt, 30)
                                    except (TypeError, ValueError):
                                        delay = min(2 ** attempt, 30)
                                    next_review_request_at = max(next_review_request_at, loop.time() + max(1, delay))
                        except Exception:
                            return None
                        if response.status_code == 429 and attempt < 3:
                            continue
                        if response.status_code >= 400:
                            return None
                        try:
                            payload = response.json()
                        except ValueError:
                            return None
                        if not isinstance(payload, dict):
                            return None
                        return payload
                    return None

                async def fetch_review(child_id: str) -> tuple[str, dict | None]:
                    payload = await fetch_review_page(child_id, 0)
                    if payload is None:
                        return child_id, None

                    levels = payload.get("rating_levels") if isinstance(payload.get("rating_levels"), dict) else {}
                    paging = payload.get("paging") if isinstance(payload.get("paging"), dict) else {}
                    reviews = list(payload.get("reviews") if isinstance(payload.get("reviews"), list) else [])
                    total_pageable = int(paging.get("total_pageable") or len(reviews))
                    page_limit = max(1, int(paging.get("limit") or 100))
                    offset = int(paging.get("offset") or 0) + page_limit

                    while len(reviews) < total_pageable:
                        next_payload = await fetch_review_page(child_id, offset)
                        if next_payload is None:
                            return child_id, None
                        next_reviews = (
                            next_payload.get("reviews")
                            if isinstance(next_payload.get("reviews"), list)
                            else []
                        )
                        if not next_reviews:
                            return child_id, None
                        reviews.extend(next_reviews)
                        next_paging = (
                            next_payload.get("paging")
                            if isinstance(next_payload.get("paging"), dict)
                            else {}
                        )
                        next_limit = max(1, int(next_paging.get("limit") or page_limit))
                        next_offset = int(next_paging.get("offset") or offset) + next_limit
                        if next_offset <= offset:
                            return child_id, None
                        offset = next_offset

                    normalized_child_id = child_id.strip().upper()
                    negative_reviews = 0
                    for review in reviews:
                        if not isinstance(review, dict):
                            continue
                        reviewable_object = (
                            review.get("reviewable_object")
                            if isinstance(review.get("reviewable_object"), dict)
                            else {}
                        )
                        review_item_id = str(reviewable_object.get("id") or "").strip().upper()
                        try:
                            review_rate = int(review.get("rate") or 0)
                        except (TypeError, ValueError):
                            continue
                        if review_item_id == normalized_child_id and review_rate in {1, 2}:
                            negative_reviews += 1

                    return child_id, {
                        "negative_reviews": negative_reviews,
                        "catalog_negative_reviews": int(levels.get("one_star") or 0)
                        + int(levels.get("two_star") or 0),
                        "review_total": int(paging.get("total") or 0),
                        "rating_average": payload.get("rating_average"),
                        "negative_reviews_pageable": total_pageable,
                    }

                review_data = {
                    child_id: data
                    for child_id, data in await asyncio.gather(*(fetch_review(child_id) for child_id in review_child_ids))
                    if data is not None
                }

        rows: list[dict] = []
        for period_start, period_end, visits, site_health in period_values:
            for child_id, mapping in child_map.items():
                parent_id = str(mapping["parent_id"])
                region = str(mapping["region"]).upper()
                parent_detail = parent_details.get(parent_id, {})
                child_detail = child_details.get(child_id, {})
                review = review_data.get(child_id, {})
                region_health = site_health.get(
                    region,
                    {"expected": 0, "received": 0, "missing": 0, "error_samples": []},
                )
                platform_category_id = str(
                    child_detail.get("category_id") or parent_detail.get("category_id") or ""
                )
                platform_category = category_metadata.get(platform_category_id, {})
                rows.append(
                    {
                        "source": "organic",
                        "grain": "date_range",
                        "stat_date": period_end.isoformat(),
                        "period_start": period_start.isoformat(),
                        "period_end": period_end.isoformat(),
                        "region": region,
                        "entity_type": "sku",
                        "entity_id": child_id,
                        "sku": str(child_detail.get("sku") or parent_detail.get("sku") or ""),
                        "product_name": str(child_detail.get("title") or parent_detail.get("title") or ""),
                        "impressions": None,
                        "clicks": visits.get(child_id),
                        "add_to_cart": None,
                        "orders": None,
                        "buyers": None,
                        "units_sold": None,
                        "negative_reviews": review.get("negative_reviews"),
                        "revenue": None,
                        "currency": "",
                        "raw_data": {
                            "parent_item_id": parent_id,
                            "local_item_id": child_id,
                            "review_total": review.get("review_total"),
                            "rating_average": review.get("rating_average"),
                            "catalog_negative_reviews": review.get("catalog_negative_reviews"),
                            "negative_reviews_pageable": review.get("negative_reviews_pageable"),
                            "negative_reviews_scope": "local_item" if child_id in review_data else "unavailable",
                            "negative_reviews_source": "mercado_reviews" if child_id in review_data else "unavailable",
                            "platform_category_id": platform_category_id,
                            "platform_category_name": str(platform_category.get("name") or ""),
                            "platform_category_path": str(platform_category.get("path") or ""),
                            "traffic_sync_status": "partial" if region_health["missing"] else "full",
                            "traffic_expected_items": region_health["expected"],
                            "traffic_received_items": region_health["received"],
                            "traffic_missing_items": region_health["missing"],
                            "traffic_error_samples": region_health["error_samples"],
                        },
                    }
                )
        return rows

    @staticmethod
    def _first(*values):
        for value in values:
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _as_list(value) -> list:
        return value if isinstance(value, list) else []

    @staticmethod
    def _first_dict(*values) -> dict:
        for value in values:
            if isinstance(value, dict):
                return value
        return {}

    def _mercado_order_entries(self, item: dict) -> list[dict]:
        entries: list[dict] = []
        for value in (item.get("order_items"), item.get("items"), item.get("products")):
            entries.extend(self._as_list(value))
        for order in self._as_list(item.get("orders")):
            if not isinstance(order, dict):
                continue
            entries.extend(self._as_list(order.get("order_items")))
            entries.extend(self._as_list(order.get("items")))
        if not entries:
            config = item.get("config") if isinstance(item.get("config"), dict) else {}
            entries.extend(self._as_list(config.get("items")))
        return [entry for entry in entries if isinstance(entry, dict)]

    def _entry_item(self, entry: dict) -> dict:
        return self._first_dict(entry.get("item"), entry.get("product"), entry.get("offer"), entry)

    def _entry_sku(self, entry: dict, source_item: dict) -> str | None:
        variation = self._first_dict(entry.get("variation"), source_item.get("variation"))
        return self._first(
            entry.get("seller_sku"),
            entry.get("seller_custom_field"),
            source_item.get("seller_sku"),
            source_item.get("seller_custom_field"),
            variation.get("seller_sku"),
            variation.get("seller_custom_field"),
            entry.get("sku"),
            source_item.get("sku"),
            source_item.get("id"),
            entry.get("item_id"),
            entry.get("id"),
        )

    def _entry_title(self, entry: dict, source_item: dict) -> str | None:
        return self._first(
            source_item.get("title"),
            source_item.get("name"),
            entry.get("title"),
            entry.get("name"),
            entry.get("item_title"),
        )

    def _entry_price(self, entry: dict, source_item: dict):
        price = self._first(
            entry.get("unit_price"),
            entry.get("full_unit_price"),
            entry.get("price"),
            source_item.get("price"),
        )
        if isinstance(price, dict):
            return self._first(price.get("amount"), price.get("value"), price.get("price"))
        return price

    def _entry_currency(self, entry: dict, source_item: dict, order: dict) -> str | None:
        price = entry.get("price")
        price_currency = price.get("currency") if isinstance(price, dict) else None
        return self._first(
            entry.get("currency_id"),
            entry.get("currency_code"),
            entry.get("currency"),
            price_currency,
            source_item.get("currency_id"),
            source_item.get("currency_code"),
            order.get("currency_id"),
            order.get("currency_code"),
        )

    def _order_amount(self, item: dict, products: list[dict]):
        amount = self._first(item.get("paid_amount"), item.get("total_amount"), item.get("order_amount"), item.get("amount"))
        if amount not in (None, ""):
            return amount
        for order in self._as_list(item.get("orders")):
            if not isinstance(order, dict):
                continue
            amount = self._first(order.get("paid_amount"), order.get("total_amount"), order.get("order_amount"), order.get("amount"))
            if amount not in (None, ""):
                return amount
        try:
            total = sum(float(product.get("price") or 0) * int(product.get("quantity") or 1) for product in products)
        except (TypeError, ValueError):
            return None
        return f"{total:.2f}" if total else None

    def _package_shipment(self, item: dict) -> dict:
        shipping = item.get("shipping") if isinstance(item.get("shipping"), dict) else {}
        shipment = item.get("shipment") if isinstance(item.get("shipment"), dict) else {}
        merged = dict(shipment)
        for key, value in shipping.items():
            if value not in (None, "", [], {}):
                merged[key] = value
        return merged

    @staticmethod
    def _iso_utc(value: datetime) -> str:
        if value.tzinfo:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value.replace(microsecond=0).isoformat() + "Z"

    def _resolve_api_mode(self) -> str:
        configured = str(self.settings.get("mercado_api_mode") or self.settings.get("api_mode") or "").lower()
        if configured in {"cbt", "global", "global_selling"}:
            return "cbt"
        if configured in {"local", "site"}:
            return "local"
        if self.store_type in MERCADO_CBT_STORE_TYPES or self.site in MERCADO_CBT_SITES:
            return "cbt"
        if self.store_type == "local" or self.site in MERCADO_LOCAL_SITES:
            return "local"
        return "local"

    def _order_search_path(self) -> str:
        return "/marketplace/orders/search" if self.api_mode == "cbt" else "/orders/search"

    def _order_detail_path(self, order_id: str | int) -> str:
        prefix = "/marketplace/orders" if self.api_mode == "cbt" else "/orders"
        return f"{prefix}/{order_id}"

    def _pack_detail_path(self, pack_id: str | int) -> str:
        return f"/marketplace/orders/pack/{pack_id}"

    def _shipment_detail_path(self, shipment_id: str | int) -> str:
        prefix = "/marketplace/shipments" if self.api_mode == "cbt" else "/shipments"
        return f"{prefix}/{shipment_id}"

    def _order_status_filter(self) -> str:
        pull_status = str(self.settings.get("mercado_order_pull_status") or "paid").lower()
        if pull_status in {"after_shipped", "shipped", "post_shipped"}:
            return "confirmed"
        return pull_status or "paid"

    def _download_full_orders(self) -> bool:
        return bool(self.settings.get("download_full_orders", True))

    def _request_timeout(self) -> httpx.Timeout:
        timeout = float(self.settings.get("request_timeout_seconds", 20))
        detail_timeout = float(self.settings.get("detail_timeout_seconds", min(timeout, 12)))
        return httpx.Timeout(timeout=timeout, connect=min(timeout, 10), read=detail_timeout, write=min(timeout, 10), pool=min(timeout, 10))

    async def _traffic_get(
        self,
        client: httpx.AsyncClient,
        path: str,
        *,
        params: dict | None = None,
        retry_attempts: int | None = None,
        retry_max_delay_seconds: float | None = None,
    ) -> httpx.Response:
        request_interval = max(
            0.0,
            float(self.settings.get("traffic_metadata_request_interval_seconds", 0.35)),
        )
        attempts = max(
            1,
            int(
                retry_attempts
                if retry_attempts is not None
                else self.settings.get("traffic_metadata_retry_attempts", 15)
            ),
        )
        max_delay = max(
            request_interval,
            float(
                retry_max_delay_seconds
                if retry_max_delay_seconds is not None
                else self.settings.get("traffic_metadata_retry_max_delay_seconds", 60)
            ),
        )
        last_error: Exception | None = None

        for attempt in range(attempts):
            response: httpx.Response | None = None
            try:
                async with self._traffic_request_lock:
                    loop = asyncio.get_running_loop()
                    wait_seconds = self._next_traffic_request_at - loop.time()
                    if wait_seconds > 0:
                        await asyncio.sleep(wait_seconds)
                    response = await client.get(
                        f"{self.base_url}{path}",
                        headers=self.headers,
                        params=params,
                    )
                    self._next_traffic_request_at = loop.time() + request_interval
                    if response.status_code == 429 or response.status_code >= 500:
                        retry_after = response.headers.get("Retry-After")
                        try:
                            delay = float(retry_after) if retry_after else min(2**attempt, max_delay)
                        except (TypeError, ValueError):
                            delay = min(2**attempt, max_delay)
                        self._next_traffic_request_at = max(
                            self._next_traffic_request_at,
                            loop.time() + min(max_delay, max(request_interval, delay)),
                        )
            except Exception as exc:
                last_error = exc
                if attempt + 1 >= attempts:
                    break
                async with self._traffic_request_lock:
                    loop = asyncio.get_running_loop()
                    delay = min(2**attempt, max_delay)
                    self._next_traffic_request_at = max(
                        self._next_traffic_request_at,
                        loop.time() + max(request_interval, delay),
                    )
                continue

            if response is None:
                continue
            if (response.status_code == 429 or response.status_code >= 500) and attempt + 1 < attempts:
                continue
            if response.status_code == 429 or response.status_code >= 500:
                detail = self._platform_error_message(response)
                raise RuntimeError(
                    f"MercadoLibre traffic API HTTP {response.status_code} after {attempts} attempts "
                    f"for {path}: {detail}"
                )
            return response

        raise RuntimeError(
            f"MercadoLibre traffic API request failed after {attempts} attempts for {path}: "
            f"{last_error or 'unknown network error'}"
        )

    @staticmethod
    def _platform_error_message(response: httpx.Response) -> str:
        try:
            data = response.json()
        except ValueError:
            data = {}
        message = ""
        if isinstance(data, dict):
            message = str(data.get("message") or data.get("error") or data.get("code") or "").strip()
        return message or response.text[:300]

    @staticmethod
    def _is_full_order(item: dict) -> bool:
        shipping = item.get("shipping") or {}
        logistics_type = str(
            shipping.get("logistic_type")
            or shipping.get("logistics_type")
            or shipping.get("shipping_mode")
            or item.get("logistic_type")
            or ""
        ).lower()
        return logistics_type == "full" or "fulfillment" in logistics_type

    async def _fetch_json_or_empty(self, client: httpx.AsyncClient, path: str) -> dict:
        try:
            response = await client.get(f"{self.base_url}{path}", headers=self.headers)
        except Exception:
            return {}
        if response.status_code >= 400:
            return {}
        try:
            data = response.json()
        except ValueError:
            return {}
        return data if isinstance(data, dict) else {}

    @staticmethod
    def _category_name(item: dict) -> str:
        return str(MercadoGlobalConnector._first(item.get("name"), item.get("title")) or "").strip()

    async def _traffic_category_metadata(
        self,
        client: httpx.AsyncClient,
        category_ids: list[str],
    ) -> dict[str, dict[str, str]]:
        semaphore = asyncio.Semaphore(
            max(1, int(self.settings.get("traffic_category_detail_concurrency", 12)))
        )

        async def fetch_one(category_id: str) -> tuple[str, dict[str, str]]:
            async with semaphore:
                detail = await self._fetch_json_or_empty(client, f"/categories/{category_id}")
            name = self._category_name(detail)
            path_nodes = detail.get("path_from_root") if isinstance(detail.get("path_from_root"), list) else []
            path_names = [
                self._category_name(item)
                for item in path_nodes
                if isinstance(item, dict) and self._category_name(item)
            ]
            return category_id, {
                "name": name,
                "path": " / ".join(path_names) or name,
            }

        return {
            category_id: metadata
            for category_id, metadata in await asyncio.gather(
                *(fetch_one(category_id) for category_id in category_ids)
            )
            if metadata.get("name") or metadata.get("path")
        }

    async def _fetch_order_detail(self, client: httpx.AsyncClient, order_id: str | int) -> dict:
        if self.api_mode == "cbt":
            pack_detail = await self._fetch_json_or_empty(client, self._pack_detail_path(order_id))
            if pack_detail:
                return pack_detail
        return await self._fetch_json_or_empty(client, self._order_detail_path(order_id))

    async def _hydrate_cbt_inner_orders(self, client: httpx.AsyncClient, item: dict) -> dict:
        if self.api_mode != "cbt":
            return item
        orders = self._as_list(item.get("orders"))
        if not orders:
            return item
        hydrated_orders: list[dict] = []
        for order in orders:
            if not isinstance(order, dict):
                continue
            order_id = order.get("id") or order.get("order_id")
            detail = await self._fetch_json_or_empty(client, self._order_detail_path(order_id)) if order_id else {}
            hydrated_orders.append({**order, **detail} if detail else order)
        return {**item, "orders": hydrated_orders}

    async def _hydrate_search_item(self, client: httpx.AsyncClient, item: dict, *, fetch_details: bool, fetch_shipments: bool) -> dict:
        order_id = item.get("id") or item.get("order_id")
        if fetch_details and order_id:
            detail = await self._fetch_order_detail(client, order_id)
            if detail:
                item = {**item, **detail}
            item = await self._hydrate_cbt_inner_orders(client, item)
        shipping = self._package_shipment(item)
        shipping_id = shipping.get("id") or item.get("shipping_id")
        if fetch_shipments and shipping_id:
            shipment = await self._fetch_json_or_empty(client, self._shipment_detail_path(shipping_id))
            if shipment:
                item["shipping"] = {**shipping, **shipment}
                item["shipment"] = {**(item.get("shipment") if isinstance(item.get("shipment"), dict) else {}), **shipment}
        return item

    async def hydrate_order_seeds(self, seeds: list[dict]) -> list[NormalizedOrder]:
        if not seeds:
            return []
        detail_concurrency = max(1, int(self.settings.get("detail_concurrency", 8)))
        semaphore = asyncio.Semaphore(detail_concurrency)
        async with httpx.AsyncClient(timeout=self._request_timeout()) as client:
            async def hydrate(seed: dict) -> dict:
                async with semaphore:
                    return await self._hydrate_search_item(client, dict(seed), fetch_details=True, fetch_shipments=True)

            hydrated_results = await asyncio.gather(*(hydrate(seed) for seed in seeds if isinstance(seed, dict)))
        normalized_orders: list[NormalizedOrder] = []
        for item in hydrated_results:
            normalized = self._normalize_order(item)
            if normalized:
                normalized_orders.append(normalized)
        return normalized_orders

    def _search_params(self, since: datetime | None) -> dict:
        params = {
            "sort": self.settings.get("sort", "date_desc"),
            "limit": int(self.settings.get("limit", 50)),
            "offset": 0,
        }
        if self.seller_id:
            seller_key = str(self.settings.get("mercado_seller_param") or ("seller_id" if self.api_mode == "cbt" else "seller"))
            params[seller_key] = self.seller_id
        if self.api_mode == "local":
            params["order.status"] = self._order_status_filter()
            if self.site:
                params.setdefault("site", self.site)
        else:
            params["status"] = self._order_status_filter()
        if since:
            date_key = str(
                self.settings.get("mercado_date_from_param")
                or ("order.date_created.from" if self.api_mode == "local" else "date_created.from")
            )
            params[date_key] = self._iso_utc(since)
        return params

    def _normalize_order(self, item: dict) -> NormalizedOrder | None:
        order_id = item.get("id") or item.get("order_id")
        if not order_id:
            return None
        shipping = self._package_shipment(item)
        buyer = item.get("buyer") or {}
        address = shipping.get("receiver_address") or shipping.get("destination") or {}
        order_items = self._mercado_order_entries(item)
        products = []
        for entry in order_items:
            source_item = self._entry_item(entry)
            sale_fee = entry.get("sale_fee")
            sku = self._entry_sku(entry, source_item)
            price = self._entry_price(entry, source_item)
            products.append(
                {
                    "offer_id": sku,
                    "sku": sku,
                    "name": self._entry_title(entry, source_item),
                    "quantity": entry.get("quantity") or 1,
                    "price": price,
                    "currency_code": self._entry_currency(entry, source_item, item),
                    "sale_fee": sale_fee,
                    "raw_payload": entry,
                }
            )
        shipment_id = self._first(shipping.get("id"), item.get("shipping_id"), order_id)
        currency_code = self._first(
            item.get("currency_id"),
            item.get("currency_code"),
            *(product.get("currency_code") for product in products),
            *(
                self._first(order.get("currency_id"), order.get("currency_code"), order.get("currency"))
                for order in self._as_list(item.get("orders"))
                if isinstance(order, dict)
            ),
        )
        package_status = self._first(
            shipping.get("status"),
            item.get("status"),
            *((order.get("status") for order in self._as_list(item.get("orders")) if isinstance(order, dict))),
        )
        if not package_status and self.api_mode == "cbt":
            package_status = self._order_status_filter()
        raw_payload = {
            **item,
            "id": str(order_id),
            "site": self._first(item.get("site_id"), item.get("site"), self.site),
            "marketplace": "mercadolibre",
            "mercado_api_mode": self.api_mode,
            "mercado_store_type": self.store_type or ("cbt" if self.api_mode == "cbt" else "local"),
            "created_at": self._first(item.get("date_created"), item.get("date_closed")),
            "order_date": self._first(item.get("date_created"), item.get("date_closed")),
            "buyer": {
                "id": buyer.get("id"),
                "name": self._first(buyer.get("nickname"), buyer.get("first_name"), buyer.get("email")),
                "email": buyer.get("email"),
            },
            "shipping": {
                **shipping,
                "receiver_address": {
                    **address,
                    "country_code": self._first(address.get("country_code"), (address.get("country") or {}).get("id")),
                    "country": self._first((address.get("country") or {}).get("name"), address.get("country_code")),
                    "name": self._first(address.get("receiver_name"), address.get("name"), shipping.get("receiver_name")),
                },
                "tracking_number": self._first(shipping.get("tracking_number"), shipping.get("trackingNumber")),
            },
            "shipment": {
                **(item.get("shipment") if isinstance(item.get("shipment"), dict) else {}),
                "id": shipment_id,
            },
            "status": package_status,
            "order_amount": self._order_amount(item, products),
            "currency_code": currency_code,
            "products": products,
        }
        shipping_status = str(package_status or "")
        fulfillment_type = str(self._first(shipping.get("logistic_type"), shipping.get("mode"), "FBS"))
        normalized_fulfillment_type = fulfillment_type.upper() if fulfillment_type else "FBS"
        is_full_order = self._is_full_order(item)
        raw_payload["fulfillment_type"] = normalized_fulfillment_type
        raw_payload["is_overseas_warehouse"] = is_full_order
        return NormalizedOrder(
            platform_order_id=str(order_id),
            platform_order_no=str(item.get("pack_id") or item.get("order_request_id") or order_id),
            posting_number=str(shipment_id),
            platform_status=shipping_status or str(item.get("status") or ""),
            fulfillment_type=normalized_fulfillment_type,
            is_overseas_warehouse=is_full_order,
            raw_payload=raw_payload,
        )

    async def fetch_unprocessed_orders(self, since: datetime | None = None) -> list[NormalizedOrder]:
        if not self.seller_id:
            raise ValueError("Mercado seller_id is required")
        params = self._search_params(since)
        orders: list[NormalizedOrder] = []
        accepted = set(self.settings.get("accepted_shipping_statuses", ["ready_to_ship", "pending", "handling"]))
        fetch_details = bool(self.settings.get("fetch_order_details", True))
        fetch_shipments = bool(self.settings.get("fetch_shipment_details", True))
        async with httpx.AsyncClient(timeout=self._request_timeout()) as client:
            while True:
                try:
                    response = await client.get(f"{self.base_url}{self._order_search_path()}", headers=self.headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                except (httpx.HTTPError, ValueError):
                    break
                results = data.get("results", [])
                detail_concurrency = max(1, int(self.settings.get("detail_concurrency", 8)))
                semaphore = asyncio.Semaphore(detail_concurrency)

                async def hydrate(item: dict) -> dict:
                    async with semaphore:
                        return await self._hydrate_search_item(client, item, fetch_details=fetch_details, fetch_shipments=fetch_shipments)

                hydrated_results = await asyncio.gather(*(hydrate(item) for item in results if isinstance(item, dict)))
                for item in hydrated_results:
                    if not self._download_full_orders() and self._is_full_order(item):
                        continue
                    shipping_status = str(self._package_shipment(item).get("status") or item.get("status") or "")
                    if accepted and shipping_status and shipping_status not in accepted:
                        continue
                    normalized = self._normalize_order(item)
                    if normalized:
                        orders.append(normalized)
                paging = data.get("paging") or {}
                total = int(paging.get("total") or len(results) or 0)
                limit = int(paging.get("limit") or params["limit"])
                offset = int(paging.get("offset") or params["offset"])
                if not results or offset + limit >= total or len(orders) >= int(self.settings.get("max_orders", 200)):
                    break
                params["offset"] = offset + limit
        return orders

    async def fetch_order_status_updates(self, posting_numbers: list[str]) -> list[OrderStatusUpdate]:
        shipment_ids = [str(value).strip() for value in posting_numbers if str(value or "").strip()]
        if not shipment_ids:
            return []
        results: list[OrderStatusUpdate] = []
        async with httpx.AsyncClient(timeout=self._request_timeout()) as client:
            for shipment_id in shipment_ids:
                shipment = await self._fetch_json_or_empty(client, self._shipment_detail_path(shipment_id))
                if not shipment:
                    continue
                tracking_number = self._first(shipment.get("tracking_number"), shipment.get("trackingNumber"))
                status = str(self._first(shipment.get("status"), shipment.get("substatus")) or "")
                order_id = self._first(shipment.get("order_id"), shipment.get("orderId"), shipment.get("pack_id"), shipment_id)
                raw_payload = {
                    "id": str(order_id),
                    "marketplace": "mercadolibre",
                    "mercado_api_mode": self.api_mode,
                    "mercado_store_type": self.store_type or ("cbt" if self.api_mode == "cbt" else "local"),
                    "status": status,
                    "shipping": {
                        **shipment,
                        "id": shipment_id,
                        "tracking_number": tracking_number,
                    },
                    "shipment": {
                        **shipment,
                        "id": shipment_id,
                    },
                }
                results.append(
                    OrderStatusUpdate(
                        posting_number=shipment_id,
                        platform_order_id=str(order_id),
                        platform_order_no=str(order_id),
                        platform_status=status,
                        shipment_tracking_number=str(tracking_number or ""),
                        raw_payload=raw_payload,
                    )
                )
        return results

    async def create_platform_shipment(self, order: NormalizedOrder) -> ShipmentResult:
        shipping = order.raw_payload.get("shipping") or {}
        shipment_id = str(shipping.get("id") or order.posting_number or order.platform_order_id)
        tracking = str(shipping.get("tracking_number") or shipping.get("trackingNumber") or shipment_id)
        return ShipmentResult(
            platform_shipment_id=shipment_id,
            tracking_number=tracking,
            carrier=str(shipping.get("logistic_type") or shipping.get("mode") or "Mercado Libre"),
            status="platform_ready" if not self.settings.get("dry_run_fulfillment", False) else "dry_run_created",
            raw_payload=shipping,
        )

    async def fetch_label(self, shipment: ShipmentResult, order: NormalizedOrder) -> LabelResult:
        if self.settings.get("dry_run_fulfillment", False):
            return LabelResult(
                content=build_preview_pdf(
                    "Mercado Global Label Preview" if self.api_mode == "cbt" else "Mercado Libre Label Preview",
                    [f"Order: {order.platform_order_id}", f"Shipment: {shipment.platform_shipment_id}"],
                )
            )
        async with httpx.AsyncClient(timeout=60) as client:
            if self.api_mode == "cbt":
                response = await client.get(
                    f"{self.base_url}/marketplace/shipments/{shipment.platform_shipment_id}/labels",
                    headers=self.headers,
                )
            else:
                response = await client.get(
                    f"{self.base_url}/shipment_labels",
                    headers=self.headers,
                    params={"shipment_ids": shipment.platform_shipment_id, "response_type": "pdf", "savePdf": "Y"},
                )
            response.raise_for_status()
            return LabelResult(content=response.content, content_type=response.headers.get("content-type", "application/pdf"))
