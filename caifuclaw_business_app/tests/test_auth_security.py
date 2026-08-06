# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.api.dependencies as dependency_module
import app.api.routes.auth as auth_module
from app.api.dependencies import create_access_dependencies
from app.api.routes.auth import LOGIN_ATTEMPT_LIMIT, _login_attempts, create_auth_router
from app.database import get_db
from app.security import AUTH_COOKIE_NAME


class FakeDb:
    def __init__(self, user) -> None:
        self.user = user

    def scalar(self, _statement):
        return self.user


def _auth_app(user) -> FastAPI:
    app = FastAPI()
    app.include_router(
        create_auth_router(
            current_user_dependency=lambda: user,
            roles_for_user=lambda _user, _db: [],
            menu_codes_for_user=lambda _user, _db: [],
            admin_role_code="admin",
        )
    )
    app.dependency_overrides[get_db] = lambda: FakeDb(user)
    return app


def test_login_sets_httponly_session_cookie(monkeypatch) -> None:
    user = SimpleNamespace(username="admin", password_hash="hash", enabled=True)
    monkeypatch.setattr(auth_module, "verify_password", lambda _plain, _hashed: True)
    monkeypatch.setattr(auth_module, "create_user_token", lambda _username: "signed-session-token")
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(public_base_url="https://erp.example.com"),
    )
    _login_attempts.clear()

    response = TestClient(_auth_app(user)).post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "valid-password"},
    )

    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert f"{AUTH_COOKIE_NAME}=signed-session-token" in cookie
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=lax" in cookie


def test_login_rate_limit_blocks_repeated_failures(monkeypatch) -> None:
    user = SimpleNamespace(username="admin", password_hash="hash", enabled=True)
    monkeypatch.setattr(auth_module, "verify_password", lambda _plain, _hashed: False)
    _login_attempts.clear()
    client = TestClient(_auth_app(user))

    responses = [
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        for _ in range(LOGIN_ATTEMPT_LIMIT + 1)
    ]

    assert [response.status_code for response in responses[:-1]] == [401] * LOGIN_ATTEMPT_LIMIT
    assert responses[-1].status_code == 429
    assert int(responses[-1].headers["retry-after"]) > 0


def test_logout_clears_session_cookie(monkeypatch) -> None:
    monkeypatch.setattr(
        auth_module,
        "get_settings",
        lambda: SimpleNamespace(public_base_url="http://127.0.0.1:9999"),
    )

    response = TestClient(_auth_app(None)).post("/api/v1/auth/logout")

    assert response.status_code == 200
    assert f"{AUTH_COOKIE_NAME}=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_current_user_accepts_session_cookie(monkeypatch) -> None:
    user = SimpleNamespace(username="admin", enabled=True)
    fake_db = FakeDb(user)
    monkeypatch.setattr(dependency_module, "decode_user_token", lambda token: "admin" if token == "cookie-token" else "")
    access = create_access_dependencies(
        ensure_request_menu_access=lambda _request, _user, _db: None,
        is_admin_user=lambda _user, _db: True,
    )
    app = FastAPI()

    @app.get("/protected")
    def protected(current_user=Depends(access.current_user)):
        return {"username": current_user.username}

    app.dependency_overrides[get_db] = lambda: fake_db
    client = TestClient(app)
    client.cookies.set(AUTH_COOKIE_NAME, "cookie-token")

    response = client.get("/protected")

    assert response.status_code == 200
    assert response.json() == {"username": "admin"}
