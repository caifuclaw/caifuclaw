"""Rotate local demo security values without printing secrets.

This utility is intentionally for a developer workstation. It preserves
existing encrypted credentials by making the current derived Fernet key
explicit before rotating the JWT signing key, and stores the new local admin
password in an ignored output file.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import secrets
import sys
from pathlib import Path

import psycopg
from passlib.context import CryptContext


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "caifuclaw_business_app" / "config.toml"
DEFAULT_CREDENTIAL_OUTPUT = ROOT / "outputs" / "local-admin-credentials.txt"
PWD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _config_path(value: str | None) -> Path:
    path = Path(value) if value else DEFAULT_CONFIG
    return path if path.is_absolute() else ROOT / path


def _replace_toml_value(source: str, section: str, key: str, value: str) -> str:
    lines = source.splitlines(keepends=True)
    current_section = ""
    replacement = json.dumps(value, ensure_ascii=False)
    found = False
    section_start: int | None = None
    section_end: int | None = None
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            current_section = stripped[1:-1]
            if current_section == section:
                section_start = index
            elif section_start is not None and section_end is None:
                section_end = index
        elif current_section == section and stripped.startswith(f"{key} ="):
            newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
            lines[index] = f"{key} = {replacement}{newline}"
            found = True
            break
    if not found:
        if section_start is None:
            raise RuntimeError(f"Missing [{section}] section in configuration")
        insert_at = section_end if section_end is not None else len(lines)
        newline = "\r\n" if lines[section_start].endswith("\r\n") else "\n"
        lines.insert(insert_at, f"{key} = {replacement}{newline}")
    return "".join(lines)


def _derived_fernet_key(sync_secret: str) -> str:
    digest = hashlib.sha256(sync_secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--credentials-output", default=str(DEFAULT_CREDENTIAL_OUTPUT))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    config_path = _config_path(args.config)
    if not config_path.exists():
        raise RuntimeError(f"Config file not found: {config_path}")

    import tomllib

    source = config_path.read_text(encoding="utf-8")
    config = tomllib.loads(source)
    postgres = config["postgres"]
    admin = config["sync_admin"]
    old_sync_secret = str(config["security"]["sync_secret_key"])
    new_sync_secret = secrets.token_urlsafe(48)
    new_internal_token = secrets.token_urlsafe(48)
    new_admin_password = secrets.token_urlsafe(18)
    explicit_fernet_key = str(config["security"].get("fernet_key") or "") or _derived_fernet_key(old_sync_secret)

    updated = source
    updated = _replace_toml_value(updated, "security", "sync_secret_key", new_sync_secret)
    updated = _replace_toml_value(updated, "security", "fernet_key", explicit_fernet_key)
    updated = _replace_toml_value(updated, "security", "internal_service_token", new_internal_token)
    updated = _replace_toml_value(updated, "sync_admin", "password", new_admin_password)

    if args.dry_run:
        print(f"Would rotate {config_path}")
        return 0

    admin_username = str(admin["username"])
    with psycopg.connect(
        host=str(postgres["host"]),
        port=int(postgres["port"]),
        user=str(postgres["user"]),
        password=str(postgres["password"]),
        dbname=str(config["databases"]["sync"]),
    ) as connection:
        connection.execute(
            "UPDATE local_users SET password_hash = %s, updated_at = CURRENT_TIMESTAMP WHERE username = %s",
            (PWD_CONTEXT.hash(new_admin_password), admin_username),
        )
        connection.commit()

    config_path.write_text(updated, encoding="utf-8", newline="\n")
    credential_output = _config_path(args.credentials_output)
    credential_output.parent.mkdir(parents=True, exist_ok=True)
    credential_output.write_text(
        "# Generated locally; do not commit or share.\n"
        f"username={admin_username}\n"
        f"password={new_admin_password}\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Rotated local security configuration: {config_path}")
    print(f"Wrote the new local admin credentials to: {credential_output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Rotation failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
