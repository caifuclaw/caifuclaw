# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

import json
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.main import bsi_logistics_callback
from app.models import OAuthAuthorizationSession
from app.oauth_authorization import build_authorize_url, callback_html
from app.settings import get_settings


def _request(payload: dict) -> Request:
    body = json.dumps(payload).encode("utf-8")
    received = False

    async def receive():
        nonlocal received
        if received:
            return {"type": "http.disconnect"}
        received = True
        return {"type": "http.request", "body": body, "more_body": False}

    return Request({"type": "http", "method": "POST", "path": "/", "headers": []}, receive)


def test_allegro_authorize_url_uses_direct_oauth_structure():
    row = OAuthAuthorizationSession(
        platform_account_id=1,
        platform="allegro",
        account_id="shop-1",
        state="state-1",
        client_id="client-1",
        redirect_uri="https://auth.example.test/api/allegro/callback",
        authorize_url="https://allegro.pl/auth/oauth/authorize",
        token_url="https://allegro.pl/auth/oauth/token",
        refresh_url="https://allegro.pl/auth/oauth/token",
        expires_at=datetime.utcnow() + timedelta(minutes=30),
    )

    authorize_url = build_authorize_url(row)
    parsed = urlparse(authorize_url)
    assert parsed.scheme == "https"
    assert parsed.netloc == "allegro.pl"
    assert parsed.path == "/auth/oauth/authorize"
    assert parse_qs(parsed.query) == {
        "response_type": ["code"],
        "client_id": ["client-1"],
        "redirect_uri": ["https://auth.example.test/api/allegro/callback"],
    }


def test_callback_page_posts_code_and_state_to_business_window():
    page = callback_html("mercadolibre", code="code-1", state="state-1")

    assert '"type": "caifuclaw-oauth-callback"' in page
    assert '"platform": "mercadolibre"' in page
    assert '"code": "code-1"' in page
    assert '"state": "state-1"' in page
    assert "window.opener.postMessage" in page


@pytest.mark.asyncio
async def test_bsi_callback_acknowledges_order_numbers_without_persistence():
    response = await bsi_logistics_callback(
        get_settings().bsi_callback_token,
        _request({"orderNumbers": "PLE-1, PLE-2,PLE-1"}),
    )

    assert response == {
        "status": 1,
        "msg": "",
        "notFound": [],
        "success": ["PLE-1", "PLE-2"],
        "fail": [],
    }


@pytest.mark.asyncio
async def test_bsi_callback_rejects_unknown_token():
    with pytest.raises(HTTPException) as exc_info:
        await bsi_logistics_callback("wrong", _request({}))

    assert exc_info.value.status_code == 404
