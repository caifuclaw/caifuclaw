from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10
    import tomli as tomllib


def _project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@lru_cache
def load_config() -> dict[str, Any]:
    configured_path = os.getenv("CAIFUCLAW_AI_CONFIG_FILE") or os.getenv("CAIFUCLAW_ERP_CONFIG_FILE")
    if configured_path:
        path = Path(configured_path)
        if not path.is_absolute():
            path = _project_root().parent / path
    else:
        path = _project_root() / "config.toml"
    if not path.exists():
        template = _project_root() / "config.template.toml"
        raise RuntimeError(f"Config file not found: {path}. Create it from {template} and adjust it.")
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
