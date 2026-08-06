# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

import httpx
import pytest

from common.wecom_robot import WeComRobotClient, WeComRobotError, WeComRobotSettings


WEBHOOK_URL = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test-key"


def make_client(handler):
    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    settings = WeComRobotSettings(webhook_url=WEBHOOK_URL, max_retries=0)
    return WeComRobotClient(settings, http_client=http_client)


def test_send_text_posts_expected_payload():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = make_client(handler)

    response = client.send_text("hello", mentioned_list=["wangqing"], mentioned_mobile_list=["13800000000"])

    assert response["errcode"] == 0
    assert len(requests) == 1
    assert str(requests[0].url) == WEBHOOK_URL
    assert json.loads(requests[0].content) == {
        "msgtype": "text",
        "text": {
            "content": "hello",
            "mentioned_list": ["wangqing"],
            "mentioned_mobile_list": ["13800000000"],
        },
    }


def test_send_text_can_skip_default_mentions():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    settings = WeComRobotSettings(
        webhook_url=WEBHOOK_URL,
        max_retries=0,
        default_mentioned_list=("default-user",),
        default_mentioned_mobile_list=("13800000000",),
    )
    client = WeComRobotClient(settings, http_client=http_client)

    client.send_text("@", mentioned_mobile_list=["13800000000"], use_default_mentions=False)

    assert json.loads(requests[0].content) == {
        "msgtype": "text",
        "text": {
            "content": "@",
            "mentioned_mobile_list": ["13800000000"],
        },
    }


def test_send_image_posts_base64_and_md5(tmp_path: Path):
    image_bytes = b"\x89PNG\r\n\x1a\nfake image"
    image_path = tmp_path / "notice.png"
    image_path.write_bytes(image_bytes)
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = make_client(handler)

    client.send_image(image_path)

    payload = json.loads(requests[0].content)
    assert payload == {
        "msgtype": "image",
        "image": {
            "base64": base64.b64encode(image_bytes).decode("ascii"),
            "md5": hashlib.md5(image_bytes).hexdigest(),
        },
    }


def test_send_excel_uploads_file_then_sends_media_id(tmp_path: Path):
    excel_path = tmp_path / "report.xlsx"
    excel_path.write_bytes(b"fake xlsx payload")
    urls = []

    def handler(request: httpx.Request) -> httpx.Response:
        urls.append(str(request.url))
        if request.url.path.endswith("/upload_media"):
            assert request.url.params["key"] == "test-key"
            assert request.url.params["type"] == "file"
            assert "multipart/form-data" in request.headers["content-type"]
            assert b'report.xlsx' in request.content
            return httpx.Response(200, json={"errcode": 0, "errmsg": "ok", "media_id": "media-1"})
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    client = make_client(handler)

    client.send_excel(excel_path)

    assert urls == [
        "https://qyapi.weixin.qq.com/cgi-bin/webhook/upload_media?key=test-key&type=file",
        WEBHOOK_URL,
    ]


def test_api_error_raises():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errcode": 93000, "errmsg": "invalid webhook"})

    client = make_client(handler)

    with pytest.raises(WeComRobotError, match="93000"):
        client.send_text("hello")


def test_rate_limit_waits_before_sending_more_messages():
    current_time = 100.0
    sleeps = []
    requests = []

    def monotonic() -> float:
        return current_time

    def sleeper(seconds: float) -> None:
        nonlocal current_time
        sleeps.append(seconds)
        current_time += seconds

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"errcode": 0, "errmsg": "ok"})

    transport = httpx.MockTransport(handler)
    http_client = httpx.Client(transport=transport)
    settings = WeComRobotSettings(webhook_url=WEBHOOK_URL, max_retries=0, rate_limit_per_minute=1)
    client = WeComRobotClient(settings, http_client=http_client, monotonic=monotonic, sleeper=sleeper)

    client.send_text("first")
    client.send_text("second")

    assert len(requests) == 2
    assert sleeps == [60.0]
