from __future__ import annotations

import os
import secrets
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, status

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10
    import tomli as tomllib


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


@lru_cache
def _internal_service_token() -> str:
    configured_path = os.getenv("CAIFUCLAW_AI_CONFIG_FILE") or os.getenv("CAIFUCLAW_ERP_CONFIG_FILE")
    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = _project_root() / path
    else:
        path = _project_root() / "caifuclaw_business_app" / "config.toml"
    if not path.exists():
        raise RuntimeError(f"Config file not found: {path}")
    with path.open("rb") as file:
        config: dict[str, Any] = tomllib.load(file)
    return str(config.get("security", {}).get("internal_service_token") or "").strip()


def require_internal_service_token(
    x_internal_service_token: str | None = Header(default=None, alias="X-Internal-Service-Token"),
) -> bool:
    expected = _internal_service_token()
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
