from __future__ import annotations

import base64
import hashlib
import hmac
import itertools
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from websockets.sync.client import connect


OPENCLAW_RELAY_STATUS_TIMEOUT_SECONDS = 1.5
OPENCLAW_RELAY_HOST = "127.0.0.1"
OPENCLAW_RELAY_PORT = 18792
OPENCLAW_RELAY_TOKEN_CONTEXT = "openclaw-extension-relay-v1"
OPENCLAW_RELAY_AUTH_HEADER = "x-openclaw-relay-token"
DEFAULT_OPENCLAW_CONFIG_PATH = Path.home() / ".openclaw" / "openclaw.json"
DEFAULT_OPENCLAW_RELAY_STATUS_URL = "http://127.0.0.1:18792/extension/status"


class OpenClawBrowserRelayError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserRelayDownload:
    content: bytes
    content_type: str
    final_url: str
    status_code: int


def read_openclaw_gateway_token(config_path: Path | None = None) -> tuple[str, str]:
    path = config_path or DEFAULT_OPENCLAW_CONFIG_PATH
    with path.open("r", encoding="utf-8") as handle:
        cfg = json.load(handle)
    token = ((cfg.get("gateway") or {}).get("auth") or {}).get("token") if isinstance(cfg, dict) else None
    if not isinstance(token, str) or not token.strip():
        raise OpenClawBrowserRelayError("gateway.auth.token missing")
    return token.strip(), str(path)


def derive_openclaw_relay_token(gateway_token: str, port: int = OPENCLAW_RELAY_PORT) -> str:
    message = f"{OPENCLAW_RELAY_TOKEN_CONTEXT}:{port}".encode("utf-8")
    return hmac.new(gateway_token.encode("utf-8"), message, hashlib.sha256).hexdigest()


def _relay_websocket_url() -> str:
    gateway_token, _config_path = read_openclaw_gateway_token()
    relay_token = derive_openclaw_relay_token(gateway_token)
    base_url = f"http://{OPENCLAW_RELAY_HOST}:{OPENCLAW_RELAY_PORT}"
    try:
        response = httpx.get(
            f"{base_url}/json/version",
            headers={OPENCLAW_RELAY_AUTH_HEADER: relay_token, "Accept": "application/json"},
            timeout=OPENCLAW_RELAY_STATUS_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OpenClawBrowserRelayError("browser relay is unavailable") from exc
    websocket_url = str(payload.get("webSocketDebuggerUrl") or "") if isinstance(payload, dict) else ""
    parsed = urlparse(websocket_url)
    if parsed.scheme not in {"ws", "wss"} or parsed.hostname != OPENCLAW_RELAY_HOST or parsed.port != OPENCLAW_RELAY_PORT:
        raise OpenClawBrowserRelayError("browser relay returned an invalid debugger URL")
    return websocket_url


def _host_matches_suffixes(host: str, allowed_host_suffixes: tuple[str, ...]) -> bool:
    normalized = host.strip().lower().rstrip(".")
    return any(normalized == suffix or normalized.endswith(f".{suffix}") for suffix in allowed_host_suffixes)


class _CdpConnection:
    def __init__(self, websocket: Any):
        self.websocket = websocket
        self.command_ids = itertools.count(1)
        self.events: list[dict[str, Any]] = []

    def call(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        *,
        session_id: str = "",
        timeout: float = 20,
    ) -> dict[str, Any]:
        command_id = next(self.command_ids)
        message: dict[str, Any] = {"id": command_id, "method": method}
        if params is not None:
            message["params"] = params
        if session_id:
            message["sessionId"] = session_id
        self.websocket.send(json.dumps(message, separators=(",", ":")))
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise OpenClawBrowserRelayError(f"browser relay command timed out: {method}")
            try:
                response = json.loads(self.websocket.recv(timeout=remaining))
            except (TimeoutError, ValueError) as exc:
                raise OpenClawBrowserRelayError(f"browser relay command failed: {method}") from exc
            if response.get("id") != command_id:
                self.events.append(response)
                continue
            if response.get("error"):
                raise OpenClawBrowserRelayError(f"browser relay command failed: {method}")
            result = response.get("result")
            return result if isinstance(result, dict) else {}

    def next_event(self, *, timeout: float) -> dict[str, Any]:
        if self.events:
            return self.events.pop(0)
        try:
            event = json.loads(self.websocket.recv(timeout=timeout))
        except (TimeoutError, ValueError) as exc:
            raise OpenClawBrowserRelayError("browser relay image download timed out") from exc
        return event if isinstance(event, dict) else {}


def download_url_via_openclaw_browser_relay(
    url: str,
    *,
    allowed_host_suffixes: tuple[str, ...],
    timeout_seconds: float = 20,
) -> BrowserRelayDownload:
    parsed_url = urlparse(url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise OpenClawBrowserRelayError("browser relay image URL is invalid")
    if not _host_matches_suffixes(parsed_url.hostname, allowed_host_suffixes):
        raise OpenClawBrowserRelayError("browser relay image host is not allowed")

    websocket_url = _relay_websocket_url()
    target_id = ""
    try:
        with connect(websocket_url, open_timeout=5, close_timeout=2) as websocket:
            cdp = _CdpConnection(websocket)
            target = cdp.call(
                "Target.createTarget",
                {"url": "about:blank", "background": True},
                timeout=5,
            )
            target_id = str(target.get("targetId") or "")
            if not target_id:
                raise OpenClawBrowserRelayError("browser relay could not create a background tab")
            try:
                attached = cdp.call(
                    "Target.attachToTarget",
                    {"targetId": target_id, "flatten": True},
                    timeout=5,
                )
                session_id = str(attached.get("sessionId") or "")
                if not session_id:
                    raise OpenClawBrowserRelayError("browser relay could not attach to the background tab")
                cdp.call("Network.enable", session_id=session_id, timeout=5)
                cdp.call("Page.enable", session_id=session_id, timeout=5)
                cdp.call("Page.navigate", {"url": url}, session_id=session_id, timeout=timeout_seconds)

                deadline = time.monotonic() + timeout_seconds
                response_by_request: dict[str, dict[str, Any]] = {}
                finished_requests: set[str] = set()
                failed_requests: set[str] = set()
                while time.monotonic() < deadline:
                    event = cdp.next_event(timeout=max(0.1, deadline - time.monotonic()))
                    if event.get("sessionId") != session_id:
                        continue
                    method = event.get("method")
                    params = event.get("params") if isinstance(event.get("params"), dict) else {}
                    request_id = str(params.get("requestId") or "")
                    if method == "Network.responseReceived":
                        response = params.get("response") if isinstance(params.get("response"), dict) else {}
                        response_url = str(response.get("url") or "")
                        response_host = urlparse(response_url).hostname or ""
                        if params.get("type") == "Document" and _host_matches_suffixes(response_host, allowed_host_suffixes):
                            response_by_request[request_id] = response
                    elif method == "Network.loadingFinished" and request_id:
                        finished_requests.add(request_id)
                    elif method == "Network.loadingFailed" and request_id:
                        failed_requests.add(request_id)

                    completed_request_id = next(
                        (request_id for request_id in response_by_request if request_id in finished_requests),
                        "",
                    )
                    if completed_request_id:
                        response = response_by_request[completed_request_id]
                        body_result = cdp.call(
                            "Network.getResponseBody",
                            {"requestId": completed_request_id},
                            session_id=session_id,
                            timeout=5,
                        )
                        body = str(body_result.get("body") or "")
                        content = base64.b64decode(body) if body_result.get("base64Encoded") else body.encode("utf-8")
                        headers = response.get("headers") if isinstance(response.get("headers"), dict) else {}
                        content_type = str(headers.get("content-type") or headers.get("Content-Type") or response.get("mimeType") or "")
                        return BrowserRelayDownload(
                            content=content,
                            content_type=content_type,
                            final_url=str(response.get("url") or url),
                            status_code=int(response.get("status") or 0),
                        )
                    if any(request_id in failed_requests for request_id in response_by_request):
                        raise OpenClawBrowserRelayError("browser relay image request failed")
                raise OpenClawBrowserRelayError("browser relay image download timed out")
            finally:
                if target_id:
                    try:
                        cdp.call("Target.closeTarget", {"targetId": target_id}, timeout=5)
                    except Exception:
                        pass
    except OpenClawBrowserRelayError:
        raise
    except Exception as exc:
        raise OpenClawBrowserRelayError("browser relay image download failed") from exc
