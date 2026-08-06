#!/usr/bin/env python3
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import text

APP_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = APP_ROOT.parent
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import SessionLocal, engine  # noqa: E402


TARGET_TABLE = "public.order_operation_logs"
CONFIRMATION = TARGET_TABLE
DEFAULT_OUTPUT_DIR = Path.home() / "caifuclaw_ai_backups" / "order_operation_logs"
BUSINESS_TABLES = (
    "orders",
    "order_items",
    "shipments",
    "label_files",
    "purchase_orders",
    "purchase_order_items",
    "scheduled_task_runs",
    "scheduled_task_run_steps",
    "scheduled_task_run_orders",
)
REASONS = (
    "global_status_batch",
    "post_sync_batch",
    "pipeline_batch",
    "order_sync_no_change",
    "legacy_generic_update",
    "per_order_refresh_no_change",
    "system_exact_repeat",
)


def cleanup_reason(operation_type: str, source: str, description: str) -> str | None:
    if source != "system":
        return None
    description = description or ""
    if description.startswith("定时同步状态刷新：请求 "):
        return "global_status_batch"
    if description.startswith("订单同步后自动获取物流信息：待处理 "):
        return "post_sync_batch"
    if description.startswith("物流/面单同步完成，候选 "):
        return "pipeline_batch"
    if operation_type == "order_sync" and "核心状态和物流信息无变化" in description:
        return "order_sync_no_change"
    if operation_type == "order_sync" and description == "订单同步更新":
        return "legacy_generic_update"
    if description.startswith("定时同步状态刷新：本订单") and "更新 0 条" in description:
        return "per_order_refresh_no_change"
    return None


CANDIDATE_REASON_SQL = """
CASE
    WHEN source = 'system' AND description LIKE '定时同步状态刷新：请求 %%' THEN 'global_status_batch'
    WHEN source = 'system' AND description LIKE '订单同步后自动获取物流信息：待处理 %%' THEN 'post_sync_batch'
    WHEN source = 'system' AND description LIKE '物流/面单同步完成，候选 %%' THEN 'pipeline_batch'
    WHEN source = 'system' AND operation_type = 'order_sync'
         AND description LIKE '%%核心状态和物流信息无变化%%' THEN 'order_sync_no_change'
    WHEN source = 'system' AND operation_type = 'order_sync'
         AND description = '订单同步更新' THEN 'legacy_generic_update'
    WHEN source = 'system' AND description LIKE '定时同步状态刷新：本订单%%更新 0 条' THEN 'per_order_refresh_no_change'
END
"""


def candidate_cte_sql() -> str:
    return f"""
    base_candidates AS (
        SELECT id, {CANDIDATE_REASON_SQL} AS reason
        FROM {TARGET_TABLE}
        WHERE operated_at <= :cutoff
    ),
    ranked_system_logs AS (
        SELECT
            id,
            row_number() OVER (
                PARTITION BY
                    order_id,
                    operation_type,
                    operation_attribute,
                    description,
                    operator,
                    source,
                    extra
                ORDER BY operated_at DESC, id DESC
            ) AS duplicate_rank
        FROM {TARGET_TABLE}
        WHERE operated_at <= :cutoff
          AND source = 'system'
          AND coalesce(event_key, '') = ''
    ),
    candidates AS (
        SELECT id, reason
        FROM base_candidates
        WHERE reason IS NOT NULL
        UNION ALL
        SELECT ranked.id, 'system_exact_repeat' AS reason
        FROM ranked_system_logs ranked
        WHERE ranked.duplicate_rank > 1
          AND NOT EXISTS (
              SELECT 1
              FROM base_candidates base
              WHERE base.id = ranked.id AND base.reason IS NOT NULL
          )
    )
    """


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Safely clean invalid rows from public.order_operation_logs only.")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--dry-run", action="store_true", help="Create a read-only cleanup manifest.")
    actions.add_argument("--execute", action="store_true", help="Archive and delete rows from a verified manifest.")
    actions.add_argument("--vacuum-full", action="store_true", help="Rewrite only public.order_operation_logs to release disk space.")
    parser.add_argument("--manifest", type=Path, help="Manifest path to create or consume.")
    parser.add_argument("--archive", type=Path, help="Compressed JSONL archive path for execute mode.")
    parser.add_argument("--batch-size", type=int, default=10000, help="Rows per delete transaction (1000-20000).")
    parser.add_argument("--confirm-table", default="", help=f"Must equal {CONFIRMATION!r} for destructive modes.")
    return parser.parse_args()


def json_default(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def table_size(db) -> dict[str, int]:
    row = db.execute(
        text(
            """
            SELECT
                pg_relation_size(CAST(:table_name AS regclass)) AS table_bytes,
                pg_indexes_size(CAST(:table_name AS regclass)) AS index_bytes,
                pg_total_relation_size(CAST(:table_name AS regclass)) AS total_bytes
            """
        ),
        {"table_name": TARGET_TABLE},
    ).mappings().one()
    return {key: int(value or 0) for key, value in row.items()}


def business_fingerprints(db) -> dict[str, dict[str, int | str | None]]:
    fingerprints = {}
    for table in BUSINESS_TABLES:
        exists = db.scalar(text("SELECT to_regclass(:table_name)"), {"table_name": f"public.{table}"})
        if not exists:
            fingerprints[table] = {"exists": 0}
            continue
        row = db.execute(
            text(
                f"""
                SELECT
                    count(*)::bigint AS row_count,
                    min(id)::bigint AS min_id,
                    max(id)::bigint AS max_id,
                    coalesce(sum(id), 0)::numeric::text AS id_sum,
                    md5(coalesce(string_agg(id::text, ',' ORDER BY id), '')) AS id_checksum
                FROM public.{table}
                """
            )
        ).mappings().one()
        fingerprints[table] = dict(row)
    return fingerprints


def candidate_counts(db, cutoff: datetime) -> dict[str, int]:
    rows = db.execute(
        text(
            f"""
            WITH {candidate_cte_sql()}
            SELECT reason, count(*)::bigint AS row_count
            FROM candidates
            GROUP BY reason
            """
        ),
        {"cutoff": cutoff},
    ).all()
    counts = {reason: 0 for reason in REASONS}
    counts.update({str(reason): int(row_count) for reason, row_count in rows})
    counts["total"] = sum(counts[reason] for reason in REASONS)
    return counts


def database_identity(db) -> dict[str, str]:
    row = db.execute(
        text("SELECT current_database() AS database, current_schema() AS schema, inet_server_addr()::text AS server")
    ).mappings().one()
    return {key: str(value or "local") for key, value in row.items()}


def default_manifest_path() -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"cleanup_manifest_{stamp}.json"


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=json_default) + "\n", encoding="utf-8")


def read_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("target_table") != TARGET_TABLE:
        raise RuntimeError("Manifest target table is not public.order_operation_logs")
    return payload


def create_manifest(path: Path) -> dict:
    cutoff = utcnow()
    with SessionLocal() as db:
        manifest = {
            "version": 1,
            "generated_at": utcnow().isoformat(),
            "cutoff": cutoff.isoformat(),
            "target_table": TARGET_TABLE,
            "database": database_identity(db),
            "candidate_counts": candidate_counts(db, cutoff),
            "business_fingerprints": business_fingerprints(db),
            "size_before": table_size(db),
        }
    write_json(path, manifest)
    return manifest


def verify_manifest(db, manifest: dict) -> datetime:
    if database_identity(db) != manifest.get("database"):
        raise RuntimeError("Database identity differs from the cleanup manifest")
    cutoff = datetime.fromisoformat(str(manifest["cutoff"]))
    current_counts = candidate_counts(db, cutoff)
    if current_counts != manifest.get("candidate_counts"):
        raise RuntimeError(f"Candidate counts changed: expected={manifest.get('candidate_counts')} actual={current_counts}")
    current_business = business_fingerprints(db)
    if current_business != manifest.get("business_fingerprints"):
        raise RuntimeError("Business document fingerprints changed after the manifest was created")
    return cutoff


def archive_candidates(path: Path, cutoff: datetime, expected_count: int) -> dict[str, int | str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    row_count = 0
    with SessionLocal() as db, gzip.open(path, "wb", compresslevel=6) as compressed:
        result = db.execute(
            text(
                f"""
                WITH {candidate_cte_sql()}
                SELECT l.*
                FROM {TARGET_TABLE} l
                JOIN candidates candidate ON candidate.id = l.id
                ORDER BY l.id
                """
            ).execution_options(stream_results=True, yield_per=1000),
            {"cutoff": cutoff},
        ).mappings()
        for row in result:
            line = (json.dumps(dict(row), ensure_ascii=False, separators=(",", ":"), default=json_default) + "\n").encode("utf-8")
            compressed.write(line)
            digest.update(line)
            row_count += 1
    if row_count != expected_count:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Archive row count mismatch: expected={expected_count} actual={row_count}")
    if not path.exists() or path.stat().st_size == 0:
        raise RuntimeError("Candidate archive is missing or empty")
    return {
        "path": str(path),
        "rows": row_count,
        "uncompressed_sha256": digest.hexdigest(),
        "compressed_bytes": path.stat().st_size,
    }


def delete_candidates(cutoff: datetime, batch_size: int) -> int:
    deleted_total = 0
    while True:
        with SessionLocal() as db:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
            deleted = db.execute(
                text(
                    f"""
                    DELETE FROM {TARGET_TABLE}
                    WHERE id IN (
                        WITH {candidate_cte_sql()}
                        SELECT id FROM candidates
                        ORDER BY id
                        LIMIT :batch_size
                    )
                    RETURNING id
                    """
                ),
                {"cutoff": cutoff, "batch_size": batch_size},
            ).all()
            db.commit()
        if not deleted:
            break
        deleted_total += len(deleted)
        print(f"deleted={deleted_total}", flush=True)
    return deleted_total


def execute_cleanup(manifest_path: Path, archive_path: Path, batch_size: int) -> dict:
    manifest = read_manifest(manifest_path)
    with SessionLocal() as db:
        cutoff = verify_manifest(db, manifest)
    expected = int(manifest["candidate_counts"]["total"])
    archive = archive_candidates(archive_path, cutoff, expected)
    deleted = delete_candidates(cutoff, batch_size)
    if deleted != expected:
        raise RuntimeError(f"Deleted row count mismatch: expected={expected} actual={deleted}")

    with SessionLocal() as db:
        remaining = candidate_counts(db, cutoff)
        if int(remaining["total"]) != 0:
            raise RuntimeError(f"Cleanup candidates remain after deletion: {remaining}")
        business_after = business_fingerprints(db)
        if business_after != manifest["business_fingerprints"]:
            raise RuntimeError("Business document fingerprints changed during cleanup")
        report = {
            "completed_at": utcnow().isoformat(),
            "target_table": TARGET_TABLE,
            "manifest": str(manifest_path),
            "archive": archive,
            "deleted_rows": deleted,
            "business_fingerprints": business_after,
            "size_after_delete": table_size(db),
        }
    report_path = manifest_path.with_name(manifest_path.stem + "_report.json")
    write_json(report_path, report)
    report["report_path"] = str(report_path)
    return report


def vacuum_log_table() -> dict:
    with SessionLocal() as db:
        business_before = business_fingerprints(db)
        size_before = table_size(db)
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as connection:
        connection.execute(text(f"VACUUM (FULL, ANALYZE) {TARGET_TABLE}"))
    with SessionLocal() as db:
        business_after = business_fingerprints(db)
        if business_after != business_before:
            raise RuntimeError("Business document fingerprints changed during log table compaction")
        return {
            "target_table": TARGET_TABLE,
            "size_before": size_before,
            "size_after": table_size(db),
            "business_fingerprints": business_after,
        }


def main() -> int:
    args = parse_args()
    if args.batch_size < 1000 or args.batch_size > 20000:
        raise SystemExit("--batch-size must be between 1000 and 20000")

    if args.dry_run:
        manifest_path = args.manifest or default_manifest_path()
        manifest = create_manifest(manifest_path)
        print(json.dumps({"manifest": str(manifest_path), **manifest}, ensure_ascii=False, indent=2))
        return 0

    if args.confirm_table != CONFIRMATION:
        raise SystemExit(f"Destructive mode requires --confirm-table {CONFIRMATION}")

    if args.vacuum_full:
        print(json.dumps(vacuum_log_table(), ensure_ascii=False, indent=2, default=json_default))
        return 0

    if not args.manifest:
        raise SystemExit("--execute requires --manifest")
    archive_path = args.archive or args.manifest.with_suffix(".jsonl.gz")
    report = execute_cleanup(args.manifest, archive_path, args.batch_size)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
