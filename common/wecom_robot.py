# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import base64
import hashlib
import mimetypes
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

import httpx

from .config_loader import optional


MAX_TEXT_BYTES = 2048
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MIN_FILE_BYTES = 5
MAX_FILE_BYTES = 20 * 1024 * 1024
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
EXCEL_SUFFIXES = {".xls", ".xlsx", ".xlsm", ".xlsb"}


class WeComRobotError(RuntimeError):
    pass


@dataclass(frozen=True)
class WeComRobotSettings:
    webhook_url: str
    enabled: bool = True
    timeout_seconds: float = 30
    max_retries: int = 2
    retry_backoff_seconds: float = 1
    rate_limit_per_minute: int = 20
    default_mentioned_list: tuple[str, ...] = ()
    default_mentioned_mobile_list: tuple[str, ...] = ()
    default_prompt: str = ""


def load_wecom_robot_settings(*, webhook_url: str | None = None) -> WeComRobotSettings:
    configured_webhook_url = (
        webhook_url
        or os.getenv("WECOM_ROBOT_WEBHOOK_URL")
        or os.getenv("CAIFUCLAW_AI_WECOM_ROBOT_WEBHOOK_URL")
        or os.getenv("CAIFUCLAW_ERP_WECOM_ROBOT_WEBHOOK_URL")
        or str(_config_optional("wecom_robot", "webhook_url", "") or "")
    ).strip()
    if not configured_webhook_url:
        raise WeComRobotError(
            "Missing WeCom robot webhook URL. Set WECOM_ROBOT_WEBHOOK_URL or [wecom_robot].webhook_url."
        )

    return WeComRobotSettings(
        webhook_url=configured_webhook_url,
        enabled=_as_bool(os.getenv("WECOM_ROBOT_ENABLED"), _config_optional("wecom_robot", "enabled", True)),
        timeout_seconds=_as_float(
            os.getenv("WECOM_ROBOT_TIMEOUT_SECONDS"),
            _config_optional("wecom_robot", "timeout_seconds", 30),
        ),
        max_retries=_as_int(os.getenv("WECOM_ROBOT_MAX_RETRIES"), _config_optional("wecom_robot", "max_retries", 2)),
        retry_backoff_seconds=_as_float(
            os.getenv("WECOM_ROBOT_RETRY_BACKOFF_SECONDS"),
            _config_optional("wecom_robot", "retry_backoff_seconds", 1),
        ),
        rate_limit_per_minute=_as_int(
            os.getenv("WECOM_ROBOT_RATE_LIMIT_PER_MINUTE"),
            _config_optional("wecom_robot", "rate_limit_per_minute", 20),
        ),
        default_mentioned_list=tuple(_as_str_list(_config_optional("wecom_robot", "default_mentioned_list", []))),
        default_mentioned_mobile_list=tuple(
            _as_str_list(_config_optional("wecom_robot", "default_mentioned_mobile_list", []))
        ),
        default_prompt=str(os.getenv("WECOM_ROBOT_DEFAULT_PROMPT") or _config_optional("wecom_robot", "default_prompt", "") or "").strip(),
    )


class WeComRobotClient:
    def __init__(
        self,
        settings: WeComRobotSettings,
        *,
        http_client: httpx.Client | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not settings.enabled:
            raise WeComRobotError("WeCom robot is disabled by configuration.")
        self.settings = settings
        self.webhook_url = settings.webhook_url
        self._client = http_client or httpx.Client()
        self._owns_client = http_client is None
        self._monotonic = monotonic
        self._sleeper = sleeper
        self._sent_message_at: list[float] = []

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> WeComRobotClient:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.close()

    def send_text(
        self,
        content: str,
        *,
        mentioned_list: list[str] | tuple[str, ...] | None = None,
        mentioned_mobile_list: list[str] | tuple[str, ...] | None = None,
        use_default_mentions: bool = True,
    ) -> dict[str, Any]:
        content = str(content)
        if not content:
            raise WeComRobotError("Text content cannot be empty.")
        if len(content.encode("utf-8")) > MAX_TEXT_BYTES:
            raise WeComRobotError(f"Text content exceeds {MAX_TEXT_BYTES} bytes.")

        text: dict[str, Any] = {"content": content}
        merged_mentions = tuple(mentioned_list or ())
        merged_mobile_mentions = tuple(mentioned_mobile_list or ())
        if use_default_mentions:
            merged_mentions = merged_mentions or self.settings.default_mentioned_list
            merged_mobile_mentions = merged_mobile_mentions or self.settings.default_mentioned_mobile_list
        if merged_mentions:
            text["mentioned_list"] = list(merged_mentions)
        if merged_mobile_mentions:
            text["mentioned_mobile_list"] = list(merged_mobile_mentions)
        return self._post_json(self.webhook_url, {"msgtype": "text", "text": text})

    def send_image(self, image_path: str | Path) -> dict[str, Any]:
        path = _validated_path(image_path)
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise WeComRobotError("Image messages only support JPG and PNG files.")
        data = path.read_bytes()
        if len(data) > MAX_IMAGE_BYTES:
            raise WeComRobotError(f"Image file exceeds {MAX_IMAGE_BYTES} bytes.")
        payload = {
            "msgtype": "image",
            "image": {
                "base64": base64.b64encode(data).decode("ascii"),
                "md5": hashlib.md5(data).hexdigest(),
            },
        }
        return self._post_json(self.webhook_url, payload)

    def send_excel(self, excel_path: str | Path) -> dict[str, Any]:
        path = _validated_path(excel_path)
        if path.suffix.lower() not in EXCEL_SUFFIXES:
            raise WeComRobotError("Excel messages require .xls, .xlsx, .xlsm, or .xlsb files.")
        return self.send_file(path)

    def send_file(self, file_path: str | Path) -> dict[str, Any]:
        path = _validated_path(file_path)
        media_id = self.upload_file(path)
        return self._post_json(self.webhook_url, {"msgtype": "file", "file": {"media_id": media_id}})

    def upload_file(self, file_path: str | Path) -> str:
        path = _validated_path(file_path)
        size = path.stat().st_size
        if size <= MIN_FILE_BYTES:
            raise WeComRobotError(f"File must be larger than {MIN_FILE_BYTES} bytes.")
        if size > MAX_FILE_BYTES:
            raise WeComRobotError(f"File exceeds {MAX_FILE_BYTES} bytes.")

        upload_url = _upload_media_url(self.webhook_url)
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        with path.open("rb") as file:
            payload = self._request(
                "POST",
                upload_url,
                files={"media": (path.name, file, content_type)},
            )
        media_id = str(payload.get("media_id") or "").strip()
        if not media_id:
            raise WeComRobotError("WeCom robot upload response did not include media_id.")
        return media_id

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        self._enforce_rate_limit()
        return self._request("POST", url, json=payload, headers={"Content-Type": "application/json"})

    def _request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        attempts = max(0, self.settings.max_retries) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                response = self._client.request(
                    method,
                    url,
                    timeout=self.settings.timeout_seconds,
                    **kwargs,
                )
                if response.status_code >= 500 and attempt < attempts - 1:
                    _sleep_before_retry(self.settings.retry_backoff_seconds, attempt, self._sleeper)
                    continue
                return _parse_wecom_response(response)
            except httpx.RequestError as exc:
                last_error = exc
                if attempt < attempts - 1:
                    _sleep_before_retry(self.settings.retry_backoff_seconds, attempt, self._sleeper)
                    continue
                raise WeComRobotError(f"WeCom robot request failed: {exc.__class__.__name__}") from exc
        raise WeComRobotError("WeCom robot request failed.") from last_error

    def _enforce_rate_limit(self) -> None:
        limit = max(0, self.settings.rate_limit_per_minute)
        if not limit:
            return
        now = self._monotonic()
        window_start = now - 60
        self._sent_message_at = [sent_at for sent_at in self._sent_message_at if sent_at > window_start]
        if len(self._sent_message_at) >= limit:
            wait_seconds = max(0.0, self._sent_message_at[0] + 60 - now)
            if wait_seconds > 0:
                self._sleeper(wait_seconds)
                now = self._monotonic()
                window_start = now - 60
                self._sent_message_at = [sent_at for sent_at in self._sent_message_at if sent_at > window_start]
        self._sent_message_at.append(now)


def _config_optional(section: str, key: str, default: Any = None) -> Any:
    try:
        return optional(section, key, default)
    except RuntimeError:
        return default


def _as_bool(value: Any, default: Any) -> bool:
    raw = default if value is None else value
    if isinstance(raw, bool):
        return raw
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: Any) -> int:
    raw = default if value is None else value
    return int(raw)


def _as_float(value: Any, default: Any) -> float:
    raw = default if value is None else value
    return float(raw)


def _as_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _validated_path(value: str | Path) -> Path:
    path = Path(value)
    if not path.exists():
        raise WeComRobotError(f"File not found: {path}")
    if not path.is_file():
        raise WeComRobotError(f"Path is not a file: {path}")
    return path


def _upload_media_url(webhook_url: str) -> str:
    parsed = urlparse(webhook_url)
    query = parse_qs(parsed.query)
    key = (query.get("key") or [""])[0].strip()
    if not key:
        raise WeComRobotError("WeCom robot webhook URL does not contain a key query parameter.")
    return urlunparse(
        (
            parsed.scheme or "https",
            parsed.netloc or "qyapi.weixin.qq.com",
            "/cgi-bin/webhook/upload_media",
            "",
            urlencode({"key": key, "type": "file"}),
            "",
        )
    )


def _parse_wecom_response(response: httpx.Response) -> dict[str, Any]:
    if response.status_code >= 300:
        raise WeComRobotError(f"WeCom robot HTTP {response.status_code}: {response.text[:300]}")
    try:
        payload = response.json()
    except ValueError as exc:
        raise WeComRobotError("WeCom robot response is not JSON.") from exc
    errcode = payload.get("errcode")
    if errcode not in (0, "0", None):
        errmsg = str(payload.get("errmsg") or "unknown error")
        raise WeComRobotError(f"WeCom robot API error {errcode}: {errmsg}")
    return payload


def _sleep_before_retry(backoff_seconds: float, attempt: int, sleeper: Callable[[float], None]) -> None:
    if backoff_seconds <= 0:
        return
    sleeper(backoff_seconds * (attempt + 1))
