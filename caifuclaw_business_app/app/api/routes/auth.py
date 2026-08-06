# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from collections.abc import Callable
from datetime import datetime
from threading import Lock
from time import monotonic
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...database import get_db
from ...models import LocalUser, Role
from ...security import AUTH_COOKIE_NAME, AUTH_SESSION_SECONDS, create_user_token, hash_password, verify_password
from ...settings import get_settings
from ..contracts.auth import AuthMeResponse, ChangePasswordRequest, LoginRequest, TokenResponse


LOGIN_ATTEMPT_LIMIT = 5
LOGIN_ATTEMPT_WINDOW_SECONDS = 5 * 60
MIN_PASSWORD_LENGTH = 12
_login_attempts: dict[str, list[float]] = {}
_login_attempts_lock = Lock()


def _login_attempt_key(request: Request, username: str) -> str:
    client_host = request.client.host if request.client else "unknown"
    return f"{client_host}:{username.strip().lower()}"


def _check_login_rate_limit(key: str) -> None:
    now = monotonic()
    cutoff = now - LOGIN_ATTEMPT_WINDOW_SECONDS
    with _login_attempts_lock:
        attempts = [attempt for attempt in _login_attempts.get(key, []) if attempt >= cutoff]
        _login_attempts[key] = attempts
        if len(attempts) >= LOGIN_ATTEMPT_LIMIT:
            retry_after = max(1, round(LOGIN_ATTEMPT_WINDOW_SECONDS - (now - attempts[0])))
            raise HTTPException(
                status_code=429,
                detail="Too many login attempts",
                headers={"Retry-After": str(retry_after)},
            )


def _record_login_failure(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.setdefault(key, []).append(monotonic())


def _clear_login_failures(key: str) -> None:
    with _login_attempts_lock:
        _login_attempts.pop(key, None)


def _cookie_secure() -> bool:
    return get_settings().public_base_url.lower().startswith("https://")


def create_auth_router(
    *,
    current_user_dependency: Callable[..., Any],
    roles_for_user: Callable[..., list[Role]],
    menu_codes_for_user: Callable[[LocalUser, Session], list[str]],
    admin_role_code: str,
) -> APIRouter:
    router = APIRouter(tags=["auth"])

    @router.post("/api/auth/login", response_model=TokenResponse)
    @router.post("/api/v1/auth/login", response_model=TokenResponse)
    def login(
        payload: LoginRequest,
        request: Request,
        response: Response,
        db: Session = Depends(get_db),
    ) -> TokenResponse:
        attempt_key = _login_attempt_key(request, payload.username)
        _check_login_rate_limit(attempt_key)
        user = db.scalar(select(LocalUser).where(LocalUser.username == payload.username))
        if not user or not verify_password(payload.password, user.password_hash):
            _record_login_failure(attempt_key)
            raise HTTPException(status_code=401, detail="Invalid username or password")
        if not user.enabled:
            _record_login_failure(attempt_key)
            raise HTTPException(status_code=403, detail="User disabled")
        _clear_login_failures(attempt_key)
        access_token = create_user_token(user.username)
        response.set_cookie(
            key=AUTH_COOKIE_NAME,
            value=access_token,
            max_age=AUTH_SESSION_SECONDS,
            httponly=True,
            secure=_cookie_secure(),
            samesite="lax",
            path="/",
        )
        return TokenResponse(access_token=access_token)

    @router.post("/api/auth/logout")
    @router.post("/api/v1/auth/logout")
    def logout(response: Response) -> dict[str, bool]:
        response.delete_cookie(
            key=AUTH_COOKIE_NAME,
            httponly=True,
            secure=_cookie_secure(),
            samesite="lax",
            path="/",
        )
        return {"ok": True}

    @router.get("/api/v1/auth/me", response_model=AuthMeResponse)
    def auth_me(
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> AuthMeResponse:
        roles = roles_for_user(user, db)
        primary_role = next(
            (role for role in roles if role.code == admin_role_code),
            roles[0] if roles else None,
        )
        return AuthMeResponse(
            id=user.id,
            username=user.username,
            display_name=user.display_name or "",
            role_id=primary_role.id if primary_role else None,
            role_code=primary_role.code if primary_role else "",
            role_name=primary_role.name if primary_role else "",
            role_ids=[role.id for role in roles],
            role_codes=[role.code for role in roles],
            role_names=[role.name for role in roles],
            menus=menu_codes_for_user(user, db),
        )

    @router.post("/api/v1/auth/change-password")
    def change_password(
        payload: ChangePasswordRequest,
        user: LocalUser = Depends(current_user_dependency),
        db: Session = Depends(get_db),
    ) -> dict:
        if not verify_password(payload.old_password, user.password_hash):
            raise HTTPException(status_code=400, detail="当前密码不正确")
        if len(payload.new_password) < MIN_PASSWORD_LENGTH:
            raise HTTPException(status_code=400, detail=f"新密码至少 {MIN_PASSWORD_LENGTH} 位")
        if payload.old_password == payload.new_password:
            raise HTTPException(status_code=400, detail="新密码不能和当前密码相同")
        user.password_hash = hash_password(payload.new_password)
        user.updated_at = datetime.utcnow()
        db.commit()
        return {"ok": True}

    return router
