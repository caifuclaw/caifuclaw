from datetime import datetime, timedelta, timezone

import jwt
from jwt.exceptions import PyJWTError as JWTError
from passlib.context import CryptContext

from .settings import get_settings


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
AUTH_COOKIE_NAME = "caifuclaw_session"
AUTH_SESSION_SECONDS = 12 * 60 * 60


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, hashed: str) -> bool:
    return pwd_context.verify(password, hashed)


def create_user_token(username: str) -> str:
    settings = get_settings()
    payload = {
        "sub": username,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=AUTH_SESSION_SECONDS),
    }
    return jwt.encode(payload, settings.sync_secret_key, algorithm="HS256")


def decode_user_token(token: str) -> str:
    settings = get_settings()
    payload = jwt.decode(token, settings.sync_secret_key, algorithms=["HS256"])
    username = payload.get("sub")
    if not username:
        raise JWTError("missing subject")
    return username


SCHEDULED_TASK_RUN_PDF_DOWNLOAD_SCOPE = "scheduled_task_run_pdf_download"
FILE_BROWSER_SESSION_SCOPE = "filebrowser_session"


def create_scheduled_task_run_pdf_download_token(
    username: str,
    run_id: int,
    expires_seconds: int = 300,
) -> str:
    settings = get_settings()
    payload = {
        "sub": username,
        "scope": SCHEDULED_TASK_RUN_PDF_DOWNLOAD_SCOPE,
        "run_id": int(run_id),
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_seconds),
    }
    return jwt.encode(payload, settings.sync_secret_key, algorithm="HS256")


def decode_scheduled_task_run_pdf_download_token(token: str) -> tuple[str, int]:
    settings = get_settings()
    payload = jwt.decode(token, settings.sync_secret_key, algorithms=["HS256"])
    if payload.get("scope") != SCHEDULED_TASK_RUN_PDF_DOWNLOAD_SCOPE:
        raise JWTError("invalid scope")
    username = payload.get("sub")
    if not username:
        raise JWTError("missing subject")
    try:
        run_id = int(payload.get("run_id"))
    except (TypeError, ValueError) as exc:
        raise JWTError("invalid run id") from exc
    return username, run_id


def create_filebrowser_session_token(username: str, expires_seconds: int = 7200) -> str:
    settings = get_settings()
    payload = {
        "sub": username,
        "scope": FILE_BROWSER_SESSION_SCOPE,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_seconds),
    }
    return jwt.encode(payload, settings.sync_secret_key, algorithm="HS256")


def decode_filebrowser_session_token(token: str) -> str:
    settings = get_settings()
    payload = jwt.decode(token, settings.sync_secret_key, algorithms=["HS256"])
    if payload.get("scope") != FILE_BROWSER_SESSION_SCOPE:
        raise JWTError("invalid scope")
    username = payload.get("sub")
    if not username:
        raise JWTError("missing subject")
    return username
