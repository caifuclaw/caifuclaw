from collections.abc import Callable
from dataclasses import dataclass
import secrets
from typing import Any

from fastapi import Depends, Header, HTTPException, Query, Request, status
from jwt.exceptions import PyJWTError as JWTError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import LocalUser
from ..security import AUTH_COOKIE_NAME, decode_scheduled_task_run_pdf_download_token, decode_user_token
from ..settings import get_settings


@dataclass(frozen=True)
class AccessDependencies:
    current_user: Callable
    current_user_from_scheduled_task_run_pdf_download_token: Callable
    require_admin: Callable


def create_access_dependencies(
    *,
    ensure_request_menu_access: Callable[[Request, LocalUser, Session], None],
    is_admin_user: Callable[[LocalUser, Session], bool],
) -> AccessDependencies:
    def current_user(request: Request, db: Session = Depends(get_db)) -> LocalUser:
        auth = request.headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip() if auth.startswith("Bearer ") else ""
        token = token or request.cookies.get(AUTH_COOKIE_NAME, "").strip()
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing authentication token")
        try:
            username = decode_user_token(token)
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
        user = db.scalar(select(LocalUser).where(LocalUser.username == username))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if not user.enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
        ensure_request_menu_access(request, user, db)
        return user

    def current_user_by_username(username: str, request: Request, db: Session) -> LocalUser:
        user = db.scalar(select(LocalUser).where(LocalUser.username == username))
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
        if not user.enabled:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User disabled")
        ensure_request_menu_access(request, user, db)
        return user

    def current_user_from_scheduled_task_run_pdf_download_token(
        request: Request,
        run_id: int,
        download_token: str = Query(alias="token"),
        db: Session = Depends(get_db),
    ) -> LocalUser:
        try:
            username, token_run_id = decode_scheduled_task_run_pdf_download_token(download_token)
        except JWTError as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid download token") from exc
        if token_run_id != run_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Download token does not match this run",
            )
        return current_user_by_username(username, request, db)

    def require_admin(
        user: LocalUser = Depends(current_user),
        db: Session = Depends(get_db),
    ) -> LocalUser:
        if not is_admin_user(user, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admin permission required",
            )
        return user

    return AccessDependencies(
        current_user=current_user,
        current_user_from_scheduled_task_run_pdf_download_token=(
            current_user_from_scheduled_task_run_pdf_download_token
        ),
        require_admin=require_admin,
    )


def create_internal_service_dependency(
    settings_provider: Callable[[], Any] = get_settings,
) -> Callable[..., bool]:
    """Create a dependency for service-to-service calls that carry a shared token."""

    def require_internal_service_token(
        x_internal_service_token: str | None = Header(
            default=None,
            alias="X-Internal-Service-Token",
        ),
    ) -> bool:
        expected = str(getattr(settings_provider(), "internal_service_token", "") or "").strip()
        if not expected:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Internal service authentication is not configured",
            )
        if not x_internal_service_token or not secrets.compare_digest(x_internal_service_token, expected):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid internal service token",
            )
        return True

    return require_internal_service_token
