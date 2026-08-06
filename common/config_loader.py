from __future__ import annotations

import os
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@lru_cache
def load_config() -> dict[str, Any]:
    configured_path = os.getenv("CAIFUCLAW_AI_CONFIG_FILE") or os.getenv("CAIFUCLAW_ERP_CONFIG_FILE")
    path = Path(configured_path or _project_root() / "caifuclaw_business_app" / "config.toml")
    if not path.is_absolute():
        path = _project_root() / path
    if not path.exists():
        example = _project_root() / "caifuclaw_business_app" / "config.template.toml"
        raise RuntimeError(f"Config file not found: {path}. Copy {example} to {path} and adjust it.")
    with path.open("rb") as file:
        return tomllib.load(file)


def require(section: str, key: str) -> Any:
    config = load_config()
    current: Any = config
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            raise RuntimeError(f"Missing config section: {section}")
        current = current[part]
    if key not in current:
        raise RuntimeError(f"Missing config key: {section}.{key}")
    return current[key]


def optional(section: str, key: str, default: Any = None) -> Any:
    config = load_config()
    current: Any = config
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current.get(key, default) if isinstance(current, dict) else default
