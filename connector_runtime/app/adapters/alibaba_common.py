import hashlib
import json
from datetime import datetime

from .base import MarketplaceConnector
from .marketplace_common import DryRunFulfillmentMixin, LoggedHttpMixin, first_value, unix_seconds


class AlibabaTopConnector(LoggedHttpMixin, DryRunFulfillmentMixin, MarketplaceConnector):
    platform = ""
    sign_method = "sha256"

    def __init__(self, credentials: dict, settings: dict | None = None) -> None:
        self.credentials = credentials or {}
        self.settings = settings or {}
        self.app_key = str(self.credentials.get("app_key") or self.credentials.get("client_id") or "")
        self.app_secret = str(self.credentials.get("app_secret") or self.credentials.get("client_secret") or "")
        self.access_token = str(
            first_value(
                self.credentials.get("access_token"),
                self.credentials.get("session"),
                self.credentials.get("session_key"),
            )
            or ""
        )
        self.seller_id = str(self.credentials.get("seller_id") or self.settings.get("account_id") or "")
        self.base_url = str(self.settings.get("base_url") or "").rstrip("/")
        self.account_id = str(self.settings.get("account_id") or self.seller_id)

    @staticmethod
    def _format_time(value: datetime | None = None) -> str:
        value = value or datetime.utcnow()
        if value.tzinfo is not None:
            value = value.replace(tzinfo=None)
        return value.strftime("%Y-%m-%d %H:%M:%S")

    def _sign(self, params: dict) -> str:
        source = self.app_secret + "".join(f"{key}{params[key]}" for key in sorted(params) if key != "sign") + self.app_secret
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest() if self.sign_method == "sha256" else hashlib.md5(source.encode("utf-8")).hexdigest()
        return digest.upper()

    def _common_params(self, method: str, extra: dict | None = None) -> dict:
        params = {
            "app_key": self.app_key,
            "method": method,
            "sign_method": self.sign_method,
            "timestamp": self._format_time(),
            "format": "json",
            "v": str(self.settings.get("api_version") or "2.0"),
        }
        if self.access_token:
            params["session"] = self.access_token
        if extra:
            for key, value in extra.items():
                if value not in (None, ""):
                    params[key] = value
        params["sign"] = self._sign(params)
        return params

    async def _top_post(self, method: str, params: dict | None = None, *, binary: bool = False):
        all_params = self._common_params(method, params)
        return await self._request(
            "POST",
            self.base_url,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"},
            data=all_params,
            binary=binary,
        )

    async def _top_json_param(self, method: str, payload_key: str, payload: dict, extra: dict | None = None):
        params = {payload_key: json.dumps(payload, separators=(",", ":"), ensure_ascii=False), **(extra or {})}
        return await self._top_post(method, params)

    def _timestamp_filter(self, since: datetime | None, from_key: str, to_key: str) -> dict:
        if not since:
            return {}
        return {
            from_key: self._format_time(since),
            to_key: self._format_time(),
        }
