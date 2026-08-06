from __future__ import annotations

import ipaddress
import mimetypes
import os
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

from .config_loader import optional as config_optional
from .openclaw_browser_relay import download_url_via_openclaw_browser_relay


IMAGE_MIME_TO_SUFFIX = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/bmp": ".bmp",
    "image/x-ms-bmp": ".bmp",
}
IMAGE_SIGNATURES: tuple[tuple[bytes, str], ...] = (
    (b"\xff\xd8\xff", "image/jpeg"),
    (b"\x89PNG\r\n\x1a\n", "image/png"),
    (b"RIFF", "image/webp"),
    (b"BM", "image/bmp"),
)
NETWORK_IMAGE_MAX_BYTES = 10 * 1024 * 1024
NETWORK_IMAGE_TIMEOUT_SECONDS = 20
BROWSER_RELAY_FALLBACK_HOST_SUFFIXES = ("entertainmentearth.com",)


class ImageStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class OssConfig:
    access_key_id: str
    access_key_secret: str
    bucket_name: str
    endpoint: str
    public_domain: str = ""
    public_base_url: str = ""


def split_image_urls(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [url for item in value for url in split_image_urls(item)]
    text = str(value or "").strip()
    if not text:
        return []
    for separator in ("\r", "\n", ";", ",", "，"):
        text = text.replace(separator, "\n")
    return [part.strip() for part in text.split("\n") if part.strip()]


def _config_value(*keys: str) -> str:
    for key in keys:
        value = config_optional("oss", key, None)
        if value not in (None, ""):
            return str(value).strip()
    return ""


def load_oss_config() -> OssConfig:
    config = OssConfig(
        access_key_id=_config_value("access_key_id", "accessKeyId") or os.getenv("OSS_ACCESS_KEY_ID", "").strip(),
        access_key_secret=_config_value("access_key_secret", "accessKeySecret") or os.getenv("OSS_ACCESS_KEY_SECRET", "").strip(),
        bucket_name=_config_value("bucket_name", "bucket") or os.getenv("OSS_BUCKET_NAME", "").strip(),
        endpoint=_config_value("endpoint") or os.getenv("OSS_ENDPOINT", "").strip(),
        public_domain=_config_value("public_domain", "custom_domain") or os.getenv("OSS_PUBLIC_DOMAIN", "").strip(),
        public_base_url=_config_value("public_base_url") or os.getenv("OSS_PUBLIC_BASE_URL", "").strip(),
    )
    if not all((config.access_key_id, config.access_key_secret, config.bucket_name, config.endpoint)):
        raise ImageStorageError("OSS configuration is incomplete")
    return config


def public_oss_url(config: OssConfig, object_key: str) -> str:
    endpoint = config.endpoint.replace("https://", "").replace("http://", "").rstrip("/")
    if config.public_base_url:
        return f"{config.public_base_url.rstrip('/')}/{object_key}"
    if config.public_domain:
        domain = config.public_domain.replace("https://", "").replace("http://", "").rstrip("/")
        return f"https://{domain}/{object_key}"
    return f"https://{config.bucket_name}.{endpoint}/{object_key}"


def upload_file_to_oss(file_path: Path, *, object_key: str | None = None) -> tuple[str, str]:
    config = load_oss_config()
    key = object_key or file_path.name
    try:
        import oss2
    except ImportError as exc:
        raise ImageStorageError("The oss2 dependency is unavailable") from exc
    auth = oss2.Auth(config.access_key_id, config.access_key_secret)
    bucket = oss2.Bucket(auth, config.endpoint, config.bucket_name)
    content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    result = bucket.put_object_from_file(
        key,
        str(file_path),
        headers={"Content-Type": content_type, "Content-Disposition": "inline"},
    )
    if getattr(result, "status", None) != 200:
        raise ImageStorageError(f"OSS upload failed: {getattr(result, 'status', '')}")
    return key, public_oss_url(config, key)


def _normalized_public_url(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    return parsed._replace(fragment="").geturl() if parsed.scheme else text


def _url_is_safe_to_fetch(value: str) -> bool:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    host = parsed.hostname.strip().lower()
    if host in {"localhost", "localhost.localdomain"}:
        return False
    try:
        ipaddress.ip_address(host)
        hosts = [host]
    except ValueError:
        try:
            hosts = [info[4][0] for info in socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)]
        except socket.gaierror:
            return False
    for address in hosts:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved or ip.is_unspecified:
            return False
    return True


def _image_mime_from_bytes(content: bytes, header_mime: str = "") -> str:
    for signature, mime_type in IMAGE_SIGNATURES:
        if not content.startswith(signature):
            continue
        if mime_type == "image/webp" and content[8:12] != b"WEBP":
            continue
        return mime_type
    lower_header = header_mime.split(";", 1)[0].strip().lower()
    if lower_header == "image/webp" and content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return lower_header
    return ""


def _should_use_browser_relay_fallback(url: str, status_code: int) -> bool:
    if status_code != 403:
        return False
    host = (urlparse(url).hostname or "").strip().lower().rstrip(".")
    return any(host == suffix or host.endswith(f".{suffix}") for suffix in BROWSER_RELAY_FALLBACK_HOST_SUFFIXES)


def download_network_image(url: str) -> tuple[bytes, str, str]:
    normalized_url = _normalized_public_url(url)
    if not _url_is_safe_to_fetch(normalized_url):
        raise ImageStorageError("The image URL is invalid or points to a private network")
    try:
        with httpx.Client(
            timeout=httpx.Timeout(NETWORK_IMAGE_TIMEOUT_SECONDS, connect=5),
            follow_redirects=False,
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=0),
        ) as client:
            current_url = normalized_url
            response: httpx.Response | None = None
            for _ in range(5):
                response = client.get(current_url, headers={"User-Agent": "CaifuClawImageImporter/1.0"})
                if response.status_code not in {301, 302, 303, 307, 308}:
                    break
                location = response.headers.get("location", "").strip()
                if not location:
                    break
                current_url = _normalized_public_url(urljoin(current_url, location))
                if not _url_is_safe_to_fetch(current_url):
                    raise ImageStorageError("The image redirect points to a private network")
            if response is None:
                raise ImageStorageError("Image download failed")
    except httpx.HTTPError as exc:
        raise ImageStorageError(f"Image download failed: {exc}") from exc

    final_url = _normalized_public_url(str(response.url))
    if _should_use_browser_relay_fallback(final_url or normalized_url, response.status_code):
        try:
            relay = download_url_via_openclaw_browser_relay(
                final_url or normalized_url,
                allowed_host_suffixes=BROWSER_RELAY_FALLBACK_HOST_SUFFIXES,
                timeout_seconds=NETWORK_IMAGE_TIMEOUT_SECONDS,
            )
        except Exception:
            relay = None
        if relay is not None:
            response = httpx.Response(
                relay.status_code,
                content=relay.content,
                headers={"content-type": relay.content_type},
                request=httpx.Request("GET", relay.final_url),
            )
            final_url = _normalized_public_url(relay.final_url)
    if response.status_code >= 400:
        raise ImageStorageError(f"Image download failed: HTTP {response.status_code}")
    if final_url and not _url_is_safe_to_fetch(final_url):
        raise ImageStorageError("The image redirect points to a private network")
    content = response.content
    if not content:
        raise ImageStorageError("The image file is empty")
    if len(content) > NETWORK_IMAGE_MAX_BYTES:
        raise ImageStorageError("The image file exceeds 10 MB")
    mime_type = _image_mime_from_bytes(content, response.headers.get("content-type", ""))
    if not mime_type:
        raise ImageStorageError("The image format is invalid")
    return content, mime_type, final_url or normalized_url
