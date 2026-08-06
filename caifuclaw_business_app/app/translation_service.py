# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import hashlib
import os
import re
from functools import lru_cache
from pathlib import Path
from uuid import uuid4

import httpx

from .config_loader import optional as config_optional


BAIDU_TRANSLATE_ENDPOINT = "https://fanyi-api.baidu.com/api/trans/vip/translate"
BAIDU_TRANSLATE_BATCH_SIZE = 80
BAIDU_TRANSLATE_BATCH_CHARS = 5000
TRANSLATION_ENV_PATHS = tuple(
    path
    for path in (
        os.environ.get("CAIFUCLAW_TRANSLATION_ENV_PATH", "").strip(),
        str(Path.home() / ".config" / "caifuclaw" / ".env"),
    )
    if path
)

BAIDU_LANGUAGE_ALIASES = {
    "es": "spa",
    "es-419": "spa",
    "es_419": "spa",
    "es-mx": "spa",
    "es_mx": "spa",
    "es-es": "spa",
    "es_es": "spa",
    "spanish": "spa",
    "spanish latam": "spa",
    "spanish_latam": "spa",
    "spanish mexico": "spa",
    "spanish_mexico": "spa",
    "pt-br": "pt",
    "pt_br": "pt",
    "pt-pt": "pt",
    "pt_pt": "pt",
    "portuguese brazil": "pt",
    "portuguese_brazil": "pt",
    "en-us": "en",
    "en_us": "en",
    "zh-cn": "zh",
    "zh_cn": "zh",
    "zh-hans": "zh",
    "zh_hans": "zh",
    "zh-tw": "cht",
    "zh_tw": "cht",
    "zh-hant": "cht",
    "zh_hant": "cht",
}


class TranslationUnavailable(RuntimeError):
    pass


def _translation_config_value(section: str, *keys: str) -> str:
    for key in keys:
        env_name = f"{section}_{key}".upper().replace(".", "_")
        value = os.getenv(env_name)
        if value:
            return value.strip()
    for key in keys:
        try:
            value = config_optional(section, key, "")
        except RuntimeError:
            value = ""
        if value:
            return str(value).strip()
    return ""


def _dotenv_value(path: str, *keys: str) -> str:
    try:
        with open(path, encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return ""
    wanted = {key.upper() for key in keys}
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        if key.strip().upper() not in wanted:
            continue
        return value.strip().strip("\"'")
    return ""


def _translation_env_value(*keys: str) -> str:
    for key in keys:
        value = os.getenv(key, "").strip()
        if value:
            return value
    for path in TRANSLATION_ENV_PATHS:
        value = _dotenv_value(path, *keys)
        if value:
            return value
    return ""


def baidu_target_language(value: object) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    key = raw.casefold()
    return BAIDU_LANGUAGE_ALIASES.get(key, key)


def _translation_batches(
    texts: list[str],
    *,
    max_size: int = BAIDU_TRANSLATE_BATCH_SIZE,
    max_chars: int = BAIDU_TRANSLATE_BATCH_CHARS,
) -> list[list[str]]:
    batches: list[list[str]] = []
    current: list[str] = []
    current_chars = 0
    for text in texts:
        text_len = len(text) + 1
        if current and (len(current) >= max_size or current_chars + text_len > max_chars):
            batches.append(current)
            current = []
            current_chars = 0
        current.append(text)
        current_chars += text_len
    if current:
        batches.append(current)
    return batches


class DisabledTranslationClient:
    provider = ""

    def __init__(self, message: str = "Translation provider is not configured"):
        self.message = message

    @property
    def available(self) -> bool:
        return False

    def translate_texts(self, texts: list[str], *, from_lang: str = "auto", to_lang: str = "en") -> dict[str, str]:
        raise TranslationUnavailable(self.message)


class BaiduTranslationClient:
    provider = "baidu"

    def __init__(
        self,
        *,
        appid: str = "",
        secret_key: str = "",
        endpoint: str = BAIDU_TRANSLATE_ENDPOINT,
        timeout: float = 30.0,
        max_retries: int = 0,
        batch_size: int = BAIDU_TRANSLATE_BATCH_SIZE,
        batch_chars: int = BAIDU_TRANSLATE_BATCH_CHARS,
    ):
        self.appid = appid.strip()
        self.secret_key = secret_key.strip()
        self.endpoint = (endpoint or BAIDU_TRANSLATE_ENDPOINT).strip()
        self.timeout = timeout
        self.max_retries = max(0, int(max_retries or 0))
        self.batch_size = max(1, int(batch_size or BAIDU_TRANSLATE_BATCH_SIZE))
        self.batch_chars = max(100, int(batch_chars or BAIDU_TRANSLATE_BATCH_CHARS))

    @classmethod
    def from_config(cls) -> "BaiduTranslationClient":
        appid = (
            _translation_env_value("BAIDU_TRANSLATE_APPID", "BAIDU_FANYI_APPID", "BAIDU_APPID")
            or _translation_config_value("translation.baidu", "appid", "app_id")
        )
        secret_key = (
            _translation_env_value(
                "BAIDU_TRANSLATE_SECRET_KEY",
                "BAIDU_TRANSLATE_KEY",
                "BAIDU_FANYI_SECRET",
                "BAIDU_FANYI_SECRET_KEY",
                "BAIDU_SECRET_KEY",
            )
            or _translation_config_value("translation.baidu", "secret_key", "key", "app_key")
        )
        endpoint = (
            _translation_env_value("BAIDU_TRANSLATE_ENDPOINT")
            or _translation_config_value("translation.baidu", "endpoint")
            or BAIDU_TRANSLATE_ENDPOINT
        )
        return cls(appid=appid, secret_key=secret_key, endpoint=endpoint)

    @property
    def available(self) -> bool:
        return bool(self.appid and self.secret_key)

    def translate_texts(self, texts: list[str], *, from_lang: str = "auto", to_lang: str = "en") -> dict[str, str]:
        if not self.available:
            raise TranslationUnavailable("Baidu Translate credentials are not configured")
        target_language = baidu_target_language(to_lang)
        unique_texts = list(dict.fromkeys(text.strip() for text in texts if text and text.strip()))
        translations: dict[str, str] = {}
        if not unique_texts or not target_language:
            return translations

        parts_by_text: dict[str, list[str]] = {
            text: re.split(r"(\r\n|\r|\n)", text)
            for text in unique_texts
        }
        unique_segments = list(
            dict.fromkeys(
                part.strip()
                for parts in parts_by_text.values()
                for part in parts
                if part not in {"\r\n", "\r", "\n"} and part.strip()
            )
        )

        def request_batch(client: httpx.Client, batch: list[str]) -> list[dict]:
            query = "\n".join(batch)
            attempts = self.max_retries + 1
            last_exc: Exception | None = None
            for _ in range(attempts):
                try:
                    salt = uuid4().hex[:16]
                    sign_source = f"{self.appid}{query}{salt}{self.secret_key}"
                    sign = hashlib.md5(sign_source.encode("utf-8")).hexdigest()
                    response = client.post(
                        self.endpoint,
                        data={
                            "q": query,
                            "from": from_lang,
                            "to": target_language,
                            "appid": self.appid,
                            "salt": salt,
                            "sign": sign,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    break
                except (httpx.HTTPError, ValueError) as exc:
                    last_exc = exc
            else:
                raise RuntimeError(f"Baidu Translate request failed: {last_exc}") from last_exc
            if not isinstance(data, dict):
                raise RuntimeError("Baidu Translate returned an unexpected response")
            if data.get("error_code"):
                raise RuntimeError(f"Baidu Translate error {data.get('error_code')}: {data.get('error_msg') or ''}")
            result_rows = data.get("trans_result")
            if not isinstance(result_rows, list):
                raise RuntimeError("Baidu Translate response is missing trans_result")
            return [row for row in result_rows if isinstance(row, dict)]

        segment_translations: dict[str, str] = {}
        with httpx.Client(timeout=self.timeout) as client:
            for batch in _translation_batches(unique_segments, max_size=self.batch_size, max_chars=self.batch_chars):
                result_rows = request_batch(client, batch)
                if len(batch) > 1 and len(result_rows) != len(batch):
                    result_rows = []
                    for source in batch:
                        single_rows = request_batch(client, [source])
                        result_rows.extend(single_rows[:1])
                for source, result in zip(batch, result_rows):
                    translated = str(result.get("dst") or "").strip()
                    if translated:
                        segment_translations[source] = translated
        for source, parts in parts_by_text.items():
            source_segments = [
                part.strip()
                for part in parts
                if part not in {"\r\n", "\r", "\n"} and part.strip()
            ]
            if any(segment not in segment_translations for segment in source_segments):
                continue
            rebuilt: list[str] = []
            for part in parts:
                if part in {"\r\n", "\r", "\n"} or not part.strip():
                    rebuilt.append(part)
                    continue
                stripped = part.strip()
                leading = part[: len(part) - len(part.lstrip())]
                trailing = part[len(part.rstrip()):]
                rebuilt.append(f"{leading}{segment_translations[stripped]}{trailing}")
            translations[source] = "".join(rebuilt)
        return translations


@lru_cache
def get_baidu_translation_client() -> BaiduTranslationClient:
    return BaiduTranslationClient.from_config()
