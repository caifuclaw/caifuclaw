#!/usr/bin/env python3
# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

try:
    from .backup_postgres import (
        FileLock,
        cleanup_old_backups,
        command_exists,
        load_config,
        log,
        require,
        resolve_config_path,
        sha256_file,
        write_checksum,
    )
except ImportError:
    from backup_postgres import (  # type: ignore[no-redef]
        FileLock,
        cleanup_old_backups,
        command_exists,
        load_config,
        log,
        require,
        resolve_config_path,
        sha256_file,
        write_checksum,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BACKUP_DIR = Path.home() / "caifuclaw_ai_backups" / "full"
DEFAULT_LEGACY_POSTGRES_BACKUP_DIR = Path.home() / "caifuclaw_erp_backups" / "postgres"
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs" / "backup"
SNAPSHOT_PREFIX = "caifuclaw_ai_"
SNAPSHOT_PATTERN = re.compile(r"^(?:caifuclaw_ai|caifuclaw_erp)_(\d{8}_\d{6})$")
INCOMPLETE_SNAPSHOT_PATTERN = re.compile(r"^\.(?:caifuclaw_ai|caifuclaw_erp)_(\d{8}_\d{6})\.incomplete$")
LOCK_NAME = ".caifuclaw_ai_full_backup.lock"


@dataclass(frozen=True)
class DirectorySource:
    name: str
    source: Path
    destination: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Back up all local CaifuClaw AI databases, files, and runtime configuration.")
    parser.add_argument("--config", type=Path, default=None, help="PostgreSQL config. Defaults to the project config.toml.")
    parser.add_argument(
        "--business-config",
        type=Path,
        default=PROJECT_ROOT / "caifuclaw_business_app" / "config.toml",
        help="Business application config.toml.",
    )
    parser.add_argument("--backup-dir", type=Path, default=DEFAULT_BACKUP_DIR, help=f"Snapshot directory. Default: {DEFAULT_BACKUP_DIR}")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_LOG_DIR, help=f"Log directory. Default: {DEFAULT_LOG_DIR}")
    parser.add_argument("--retention-days", type=int, default=14, help="Delete completed snapshots older than this many days. Use 0 to disable cleanup.")
    parser.add_argument("--rsync", default=os.getenv("RSYNC_BIN", "rsync"), help="rsync executable path.")
    parser.add_argument(
        "--legacy-postgres-backup-dir",
        type=Path,
        default=DEFAULT_LEGACY_POSTGRES_BACKUP_DIR,
        help="Previous PostgreSQL-only backup directory to apply the same retention policy to.",
    )
    parser.add_argument("--skip-postgres-globals", action="store_true", help="Do not back up PostgreSQL roles and other global objects.")
    parser.add_argument("--dry-run", action="store_true", help="Validate and print the planned backup without writing a snapshot.")
    return parser.parse_args()


def resolve_path(path: Path, base: Path) -> Path:
    expanded = path.expanduser()
    if expanded.is_absolute():
        return expanded.resolve()
    return (base / expanded).resolve()


def config_path(path: Path, base: Path) -> Path:
    resolved = resolve_path(path, base)
    if not resolved.is_file():
        raise FileNotFoundError(f"Config file not found: {resolved}")
    return resolved


def configured_path(config: dict[str, Any], section: str, key: str, base: Path) -> Path:
    raw = str(require(config, section, key)).strip()
    if not raw:
        raise RuntimeError(f"Config path is empty: {section}.{key}")
    return resolve_path(Path(raw), base)


def load_directory_sources(business_config_path: Path) -> list[DirectorySource]:
    config = load_config(business_config_path)
    app_root = business_config_path.parent
    return [
        DirectorySource(
            name="labels",
            source=configured_path(config, "storage", "label_storage_root", app_root),
            destination=Path("files/labels"),
        ),
        DirectorySource(
            name="listing",
            source=configured_path(config, "listing", "storage_root", app_root),
            destination=Path("files/listing"),
        ),
        DirectorySource(
            name="caifuclaw_data",
            source=configured_path(config, "order_follow_up_export", "data_root", app_root),
            destination=Path("files/caifuclaw_data"),
        ),
        DirectorySource(
            name="webTemplates",
            source=configured_path(config, "listing", "template_root", app_root),
            destination=Path("files/webTemplates"),
        ),
    ]


def is_within(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def validate_sources(backup_dir: Path, directory_sources: list[DirectorySource]) -> None:
    resolved_backup_dir = backup_dir.resolve()
    for item in directory_sources:
        if not item.source.is_dir():
            raise FileNotFoundError(f"Backup source directory not found: {item.source}")
        resolved_source = item.source.resolve()
        if is_within(resolved_backup_dir, resolved_source) or is_within(resolved_source, resolved_backup_dir):
            raise RuntimeError(f"Backup directory and source directory overlap: {resolved_backup_dir} / {resolved_source}")


def run_logged(command: list[str], log_file: Path) -> None:
    log(f"Running: {' '.join(command)}", log_file)
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.stdout:
        for line in result.stdout.rstrip().splitlines():
            log(line, log_file)
    if result.returncode != 0:
        raise RuntimeError(f"Command failed with exit code {result.returncode}: {command[0]}")


def latest_completed_snapshot(backup_dir: Path) -> Path | None:
    snapshots = [
        path
        for path in backup_dir.iterdir()
        if path.is_dir() and not path.is_symlink() and SNAPSHOT_PATTERN.match(path.name) and (path / "COMPLETE").is_file()
    ]
    return max(snapshots, key=lambda path: SNAPSHOT_PATTERN.match(path.name).group(1)) if snapshots else None


def copy_directory(
    source: Path,
    destination: Path,
    previous_destination: Path | None,
    rsync: str,
    log_file: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    command = [rsync, "-a", "--checksum"]
    if previous_destination is not None and previous_destination.is_dir():
        command.append(f"--link-dest={previous_destination.resolve()}")
    command.extend([str(source) + "/", str(destination) + "/"])
    run_logged(command, log_file)


def backup_postgresql(config: Path, destination: Path, log_dir: Path, include_globals: bool, log_file: Path) -> list[Path]:
    destination.mkdir(parents=True, exist_ok=False)
    command = [
        sys.executable,
        str(PROJECT_ROOT / "deploy" / "database" / "backup_postgres.py"),
        "--config",
        str(config),
        "--backup-dir",
        str(destination),
        "--log-dir",
        str(log_dir),
        "--retention-days",
        "0",
    ]
    if include_globals:
        command.append("--include-globals")
    run_logged(command, log_file)

    dump_files = sorted(destination.glob("*.dump"))
    if len(dump_files) != 1:
        raise RuntimeError(f"Expected one PostgreSQL dump, found {len(dump_files)} in {destination}")
    artifacts = sorted(path for path in destination.iterdir() if path.is_file())
    if not artifacts:
        raise RuntimeError(f"PostgreSQL backup created no artifacts: {destination}")
    return artifacts


def backup_configs(config_paths: list[tuple[Path, Path]], snapshot_dir: Path, log_file: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for source, relative_destination in config_paths:
        destination = snapshot_dir / relative_destination
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        os.chmod(destination, 0o600)
        write_checksum(destination, log_file)
        records.append(
            {
                "source": str(source),
                "backup": relative_destination.as_posix(),
                "size_bytes": destination.stat().st_size,
                "sha256": sha256_file(destination),
            }
        )
    return records


def directory_stats(path: Path) -> dict[str, int]:
    file_count = 0
    symlink_count = 0
    size_bytes = 0
    for item in path.rglob("*"):
        if item.is_symlink():
            symlink_count += 1
        elif item.is_file():
            file_count += 1
            size_bytes += item.stat().st_size
    return {"file_count": file_count, "symlink_count": symlink_count, "size_bytes": size_bytes}


def write_file_inventory(snapshot_dir: Path) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    total_bytes = 0
    for path in sorted(snapshot_dir.rglob("*")):
        relative_path = path.relative_to(snapshot_dir).as_posix()
        if path.is_symlink():
            records.append({"path": relative_path, "type": "symlink", "target": os.readlink(path)})
        elif path.is_file():
            size = path.stat().st_size
            total_bytes += size
            records.append({"path": relative_path, "type": "file", "size_bytes": size, "sha256": sha256_file(path)})

    inventory_path = snapshot_dir / "file_inventory.json"
    inventory_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(inventory_path, 0o600)
    return {
        "path": inventory_path.relative_to(snapshot_dir).as_posix(),
        "file_count": sum(record["type"] == "file" for record in records),
        "size_bytes": total_bytes,
        "sha256": sha256_file(inventory_path),
    }


def write_manifest(snapshot_dir: Path, manifest: dict[str, Any]) -> None:
    manifest_path = snapshot_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.chmod(manifest_path, 0o600)
    checksum = sha256_file(manifest_path)
    complete_path = snapshot_dir / "COMPLETE"
    complete_path.write_text(f"manifest_sha256={checksum}\n", encoding="ascii")
    os.chmod(complete_path, 0o600)


def cleanup_old_snapshots(
    backup_dir: Path,
    retention_days: int,
    log_file: Path,
    *,
    current_time: datetime | None = None,
) -> None:
    if retention_days <= 0:
        log("Full snapshot retention cleanup disabled", log_file)
        return

    cutoff = (current_time or datetime.now()) - timedelta(days=retention_days)
    deleted = 0
    for path in backup_dir.iterdir():
        match = SNAPSHOT_PATTERN.match(path.name)
        if not match or not path.is_dir() or path.is_symlink() or not (path / "COMPLETE").is_file():
            continue
        snapshot_time = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
        if snapshot_time < cutoff:
            shutil.rmtree(path)
            deleted += 1
            log(f"Deleted old full snapshot: {path}", log_file)
    log(f"Full snapshot retention cleanup complete, deleted={deleted}, retention_days={retention_days}", log_file)


def cleanup_stale_incomplete_snapshots(
    backup_dir: Path,
    log_file: Path,
    *,
    current_time: datetime | None = None,
) -> None:
    cutoff = (current_time or datetime.now()) - timedelta(days=1)
    deleted = 0
    for path in backup_dir.iterdir():
        match = INCOMPLETE_SNAPSHOT_PATTERN.match(path.name)
        if not match or not path.is_dir() or path.is_symlink():
            continue
        snapshot_time = datetime.strptime(match.group(1), "%Y%m%d_%H%M%S")
        if snapshot_time < cutoff:
            shutil.rmtree(path)
            deleted += 1
            log(f"Deleted stale incomplete snapshot: {path}", log_file)
    if deleted:
        log(f"Incomplete snapshot cleanup complete, deleted={deleted}", log_file)


def main() -> int:
    args = parse_args()
    started_at = datetime.now().astimezone()
    timestamp = started_at.strftime("%Y%m%d_%H%M%S")

    backup_dir = resolve_path(args.backup_dir, PROJECT_ROOT)
    log_dir = resolve_path(args.log_dir, PROJECT_ROOT)
    legacy_postgres_backup_dir = resolve_path(args.legacy_postgres_backup_dir, PROJECT_ROOT)
    log_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(log_dir, 0o700)
    log_file = log_dir / f"backup_{timestamp}.log"

    temporary_snapshot: Path | None = None
    try:
        postgres_config = resolve_config_path(args.config)
        business_config = config_path(args.business_config, PROJECT_ROOT)
        directory_sources = load_directory_sources(business_config)

        backup_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(backup_dir, 0o700)
        validate_sources(backup_dir, directory_sources)
        if not command_exists(args.rsync):
            raise RuntimeError(f"rsync not found: {args.rsync}")

        previous_snapshot = latest_completed_snapshot(backup_dir)
        final_snapshot = backup_dir / f"{SNAPSHOT_PREFIX}{timestamp}"
        temporary_snapshot = backup_dir / f".{SNAPSHOT_PREFIX}{timestamp}.incomplete"
        if final_snapshot.exists() or temporary_snapshot.exists():
            raise FileExistsError(f"Backup snapshot already exists for timestamp: {timestamp}")

        log(
            f"Full backup starting, snapshot={final_snapshot}, retention_days={args.retention_days}, previous={previous_snapshot}",
            log_file,
        )
        for item in directory_sources:
            log(f"Backup source: {item.name}={item.source}", log_file)

        if args.dry_run:
            log("Dry run finished successfully; no snapshot was written", log_file)
            return 0

        lock_path = backup_dir / LOCK_NAME
        with FileLock(lock_path):
            cleanup_stale_incomplete_snapshots(backup_dir, log_file)
            temporary_snapshot.mkdir(mode=0o700)

            postgres_artifacts = backup_postgresql(
                postgres_config,
                temporary_snapshot / "databases" / "postgresql",
                log_dir,
                not args.skip_postgres_globals,
                log_file,
            )
            directory_records: list[dict[str, Any]] = []
            for item in directory_sources:
                destination = temporary_snapshot / item.destination
                previous_destination = previous_snapshot / item.destination if previous_snapshot else None
                copy_directory(item.source, destination, previous_destination, args.rsync, log_file)
                directory_records.append(
                    {
                        "name": item.name,
                        "source": str(item.source),
                        "backup": item.destination.as_posix(),
                        **directory_stats(destination),
                    }
                )

            config_records = backup_configs(
                [
                    (business_config, Path("config/caifuclaw_ai/config.toml")),
                ],
                temporary_snapshot,
                log_file,
            )

            inventory = write_file_inventory(temporary_snapshot)
            completed_at = datetime.now().astimezone()
            manifest = {
                "format_version": 1,
                "snapshot": final_snapshot.name,
                "status": "complete",
                "started_at": started_at.isoformat(timespec="seconds"),
                "completed_at": completed_at.isoformat(timespec="seconds"),
                "hostname": socket.gethostname(),
                "project_root": str(PROJECT_ROOT),
                "retention_days": int(args.retention_days),
                "postgresql": {
                    "database": str(require(load_config(postgres_config), "databases", "sync")),
                    "artifacts": [path.relative_to(temporary_snapshot).as_posix() for path in postgres_artifacts],
                },
                "directories": directory_records,
                "configs": config_records,
                "inventory": inventory,
            }
            write_manifest(temporary_snapshot, manifest)
            temporary_snapshot.rename(final_snapshot)
            temporary_snapshot = None

            cleanup_old_snapshots(backup_dir, int(args.retention_days), log_file)
            if legacy_postgres_backup_dir.is_dir() and legacy_postgres_backup_dir.resolve() != backup_dir.resolve():
                cleanup_old_backups(
                    legacy_postgres_backup_dir,
                    "caifuclaw_ai_sync",
                    int(args.retention_days),
                    log_file,
                )
                cleanup_old_backups(
                    legacy_postgres_backup_dir,
                    "caifuclaw_erp_sync",
                    int(args.retention_days),
                    log_file,
                )

        log(f"Full backup finished successfully: {final_snapshot}", log_file)
        return 0
    except Exception as exc:
        if temporary_snapshot is not None and temporary_snapshot.is_dir() and not temporary_snapshot.is_symlink():
            shutil.rmtree(temporary_snapshot)
        log(f"Full backup failed: {exc}", log_file)
        return 1


if __name__ == "__main__":
    sys.exit(main())
