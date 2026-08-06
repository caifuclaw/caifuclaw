#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.9/3.10
    try:
        import tomli as tomllib
    except ModuleNotFoundError:
        tomllib = None


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_DIR = Path.home() / "caifuclaw_ai_backups" / "postgres"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "postgres_backup"
LOCK_NAME = ".caifuclaw_ai_postgres_backup.lock"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up the configured CaifuClaw AI PostgreSQL database with pg_dump.")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.toml. Defaults to CAIFUCLAW_AI_CONFIG_FILE or project config.toml.")
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help=f"Directory for backup files. Default: {DEFAULT_BACKUP_DIR}")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help=f"Directory for backup logs. Default: {DEFAULT_LOG_DIR}")
    parser.add_argument("--retention-days", type=int, default=14, help="Delete backups older than this many days. Use 0 to disable cleanup.")
    parser.add_argument("--prefix", default="caifuclaw_ai_sync", help="Filename prefix for dump files.")
    parser.add_argument("--pg-dump", default=os.getenv("PG_DUMP_BIN", "pg_dump"), help="pg_dump executable path.")
    parser.add_argument("--pg-restore", default=os.getenv("PG_RESTORE_BIN", "pg_restore"), help="pg_restore executable path.")
    parser.add_argument("--pg-dumpall", default=os.getenv("PG_DUMPALL_BIN", "pg_dumpall"), help="pg_dumpall executable path.")
    parser.add_argument("--include-globals", action="store_true", help="Also back up PostgreSQL global objects with pg_dumpall --globals-only.")
    parser.add_argument("--skip-verify", action="store_true", help="Skip pg_restore --list verification.")
    parser.add_argument("--dry-run", action="store_true", help="Print what would be backed up without running pg_dump.")
    return parser.parse_args()


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def log(message: str, log_file: Path | None = None) -> None:
    line = f"{now_text()} {message}"
    print(line, flush=True)
    if log_file is not None:
        with log_file.open("a", encoding="utf-8", newline="\n") as file:
            file.write(line + "\n")


def resolve_config_path(config_arg: Path | None) -> Path:
    configured_path = os.getenv("CAIFUCLAW_AI_CONFIG_FILE") or os.getenv("CAIFUCLAW_ERP_CONFIG_FILE")
    raw = config_arg or Path(configured_path or "config.toml")
    path = raw if raw.is_absolute() else PROJECT_ROOT / raw
    if path.exists():
        return path

    app_config = PROJECT_ROOT / "caifuclaw_business_app" / "config.toml"
    if config_arg is None and not configured_path and app_config.exists():
        return app_config

    raise FileNotFoundError(f"Config file not found: {path}")


def load_config(path: Path) -> dict[str, Any]:
    with path.open("rb") as file:
        if tomllib is None:
            return load_basic_config(file.read().decode("utf-8"))
        return tomllib.load(file)


def load_basic_config(text: str) -> dict[str, Any]:
    config: dict[str, Any] = {}
    current: dict[str, Any] | None = None
    for raw_line in text.splitlines():
        line = strip_toml_comment(raw_line).strip()
        if not line:
            continue
        if line.startswith("[["):
            current = None
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            current = config.setdefault(section, {})
            continue
        if current is None or "=" not in line:
            continue
        key, raw_value = line.split("=", 1)
        key = key.strip()
        raw_value = raw_value.strip().rstrip(",")
        if raw_value.startswith('"') and raw_value.endswith('"'):
            value: Any = raw_value[1:-1]
        elif raw_value.lower() in {"true", "false"}:
            value = raw_value.lower() == "true"
        else:
            try:
                value = int(raw_value)
            except ValueError:
                value = raw_value
        current[key] = value
    return config


def strip_toml_comment(line: str) -> str:
    in_string = False
    escaped = False
    for index, char in enumerate(line):
        if escaped:
            escaped = False
            continue
        if char == "\\" and in_string:
            escaped = True
            continue
        if char == '"':
            in_string = not in_string
            continue
        if char == "#" and not in_string:
            return line[:index]
    return line


def require(config: dict[str, Any], section: str, key: str) -> Any:
    current: Any = config
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            raise RuntimeError(f"Missing config section: {section}")
        current = current[part]
    if not isinstance(current, dict) or key not in current:
        raise RuntimeError(f"Missing config key: {section}.{key}")
    return current[key]


def absolute_path(path: Path) -> Path:
    return path if path.is_absolute() else PROJECT_ROOT / path


class FileLock:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.fd: int | None = None

    def __enter__(self) -> "FileLock":
        flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
        try:
            self.fd = os.open(self.path, flags, 0o644)
            os.write(self.fd, str(os.getpid()).encode("ascii"))
        except FileExistsError as exc:
            if self._clear_stale_lock():
                self.fd = os.open(self.path, flags, 0o644)
                os.write(self.fd, str(os.getpid()).encode("ascii"))
                return self
            raise RuntimeError(f"Backup is already running or lock exists: {self.path}") from exc
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None
        try:
            self.path.unlink()
        except FileNotFoundError:
            pass

    def _clear_stale_lock(self) -> bool:
        try:
            pid_text = self.path.read_text(encoding="utf-8").strip()
            pid = int(pid_text)
        except Exception:
            return False

        try:
            os.kill(pid, 0)
            return False
        except ProcessLookupError:
            self.path.unlink(missing_ok=True)
            return True
        except PermissionError:
            return False


def command_exists(command: str) -> bool:
    if Path(command).is_absolute() or "/" in command:
        return Path(command).exists()
    return shutil.which(command) is not None


def resolve_pg_command(command: str, executable_name: str) -> str:
    if Path(command).is_absolute() or "/" in command:
        return command
    found = shutil.which(command)
    if found:
        return found

    candidates = [
        Path("/opt/homebrew/opt/postgresql/bin") / executable_name,
        Path("/opt/homebrew/opt/libpq/bin") / executable_name,
        Path("/usr/local/opt/postgresql/bin") / executable_name,
        Path("/usr/local/opt/libpq/bin") / executable_name,
    ]
    for cellar_root in (Path("/opt/homebrew/Cellar"), Path("/usr/local/Cellar")):
        for pattern in ("postgresql*", "libpq*"):
            for package_dir in sorted(cellar_root.glob(pattern), reverse=True):
                for version_dir in sorted(package_dir.iterdir(), reverse=True) if package_dir.is_dir() else []:
                    candidates.append(version_dir / "bin" / executable_name)

    for candidate in candidates:
        if candidate.exists() and os.access(candidate, os.X_OK):
            return str(candidate)
    return command


def redact_command(command: list[str]) -> str:
    return " ".join(command)


def run_command(command: list[str], *, env: dict[str, str], log_file: Path) -> None:
    log(f"Running: {redact_command(command)}", log_file)
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        for line in result.stdout.rstrip().splitlines():
            log(line, log_file)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {command[0]}")


def run_quiet_command(command: list[str], *, env: dict[str, str], log_file: Path) -> None:
    log(f"Running: {redact_command(command)}", log_file)
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        if result.stdout:
            for line in result.stdout.rstrip().splitlines():
                log(line, log_file)
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {command[0]}")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_checksum(path: Path, log_file: Path) -> Path:
    checksum = sha256_file(path)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    with checksum_path.open("w", encoding="utf-8", newline="\n") as file:
        file.write(f"{checksum}  {path.name}\n")
    log(f"Wrote checksum: {checksum_path}", log_file)
    return checksum_path


def cleanup_old_backups(backup_dir: Path, prefix: str, retention_days: int, log_file: Path) -> None:
    if retention_days <= 0:
        log("Retention cleanup disabled", log_file)
        return

    cutoff = datetime.now() - timedelta(days=retention_days)
    deleted = 0
    for path in backup_dir.iterdir():
        if not path.is_file() or not path.name.startswith(prefix + "_"):
            continue
        if path.suffix not in {".dump", ".sha256", ".sql"} and not path.name.endswith(".dump.sha256"):
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime)
        if modified < cutoff:
            path.unlink()
            deleted += 1
            log(f"Deleted old backup artifact: {path}", log_file)
    log(f"Retention cleanup complete, deleted={deleted}, retention_days={retention_days}", log_file)


def build_pg_env(password: str) -> dict[str, str]:
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    return env


def main() -> int:
    args = parse_args()
    backup_dir = absolute_path(args.backup_dir)
    log_dir = absolute_path(args.log_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = log_dir / f"postgres_backup_{timestamp}.log"
    lock_path = backup_dir / LOCK_NAME

    try:
        pg_dump = resolve_pg_command(args.pg_dump, "pg_dump")
        pg_restore = resolve_pg_command(args.pg_restore, "pg_restore")
        pg_dumpall = resolve_pg_command(args.pg_dumpall, "pg_dumpall")

        if not command_exists(pg_dump):
            raise RuntimeError(f"pg_dump not found: {args.pg_dump}")
        if not args.skip_verify and not command_exists(pg_restore):
            raise RuntimeError(f"pg_restore not found: {args.pg_restore}")
        if args.include_globals and not command_exists(pg_dumpall):
            raise RuntimeError(f"pg_dumpall not found: {args.pg_dumpall}")

        config_path = resolve_config_path(args.config)
        config = load_config(config_path)
        host = str(require(config, "postgres", "host"))
        port = str(require(config, "postgres", "port"))
        user = str(require(config, "postgres", "user"))
        password = str(require(config, "postgres", "password"))
        database = str(require(config, "databases", "sync"))

        dump_path = backup_dir / f"{args.prefix}_{timestamp}.dump"
        globals_path = backup_dir / f"{args.prefix}_{timestamp}_globals.sql"

        log(f"PostgreSQL backup starting, config={config_path}, database={database}, backup_dir={backup_dir}", log_file)

        with FileLock(lock_path):
            dump_command = [
                pg_dump,
                "--host",
                host,
                "--port",
                port,
                "--username",
                user,
                "--dbname",
                database,
                "--format",
                "custom",
                "--compress",
                "9",
                "--no-owner",
                "--no-acl",
                "--file",
                str(dump_path),
            ]

            env = build_pg_env(password)
            if args.dry_run:
                log(f"Dry run: would run {redact_command(dump_command)}", log_file)
                if args.include_globals:
                    log(f"Dry run: would write globals backup to {globals_path}", log_file)
                return 0

            run_command(dump_command, env=env, log_file=log_file)
            if not dump_path.exists() or dump_path.stat().st_size == 0:
                raise RuntimeError(f"Dump file was not created or is empty: {dump_path}")
            log(f"Created dump: {dump_path} ({dump_path.stat().st_size} bytes)", log_file)

            if not args.skip_verify:
                run_quiet_command([pg_restore, "--list", str(dump_path)], env=env, log_file=log_file)
                log("Verified dump with pg_restore --list", log_file)

            write_checksum(dump_path, log_file)

            if args.include_globals:
                run_command(
                    [
                        pg_dumpall,
                        "--host",
                        host,
                        "--port",
                        port,
                        "--username",
                        user,
                        "--globals-only",
                        "--file",
                        str(globals_path),
                    ],
                    env=env,
                    log_file=log_file,
                )
                write_checksum(globals_path, log_file)

            cleanup_old_backups(backup_dir, args.prefix, int(args.retention_days), log_file)

        log("PostgreSQL backup finished successfully", log_file)
        return 0
    except Exception as exc:
        log(f"PostgreSQL backup failed: {exc}", log_file)
        return 1


if __name__ == "__main__":
    sys.exit(main())
