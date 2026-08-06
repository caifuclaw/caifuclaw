# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

"""Create a runnable demo database without retaining source business data.

The command is dry-run by default. Use ``--apply`` only after the configured
database and retention limits have been verified. Database changes are made in
one transaction; repository-local runtime data is removed after it commits.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlalchemy import Connection, inspect, text

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from caifuclaw_business_app.app.database import engine
from caifuclaw_business_app.app.security import hash_password


DEMO_ADMIN_USERNAME = "admin"
DEMO_ADMIN_PASSWORD = "123456"
DEMO_SYNC_SECRET = "REPLACE_WITH_AT_LEAST_32_RANDOM_CHARACTERS"
DEMO_TIMESTAMP = "2026-01-01 09:00:00"

CLEAR_TABLES = (
    "api_request_logs",
    "label_files",
    "oauth_authorization_sessions",
    "order_follow_up_export_artifacts",
    "order_follow_up_export_items",
    "order_follow_up_export_jobs",
    "outbound_scan_records",
    "purchase_order_edit_locks",
    "scheduled_task_run_orders",
    "scheduled_task_run_steps",
    "scheduled_task_runs",
    "scheduler_heartbeats",
    "sync_audit_logs",
    "sync_job_logs",
    "traffic_sync_runs",
    "user_table_preferences",
)

RUNTIME_DIRECTORIES = (
    "caifuclaw_business_app/data",
    "caifuclaw_business_app/exports",
    "caifuclaw_business_app/outputs",
    "caifuclaw_business_app/logs",
    "connector_runtime/logs",
    "logs",
    "output",
    "outputs",
    ".playwright-cli",
    "tmp_excel_compare",
    "cert",
)

RUNTIME_FILE_PATTERNS = (
    "orders-status-tabs-check*.png",
    "test_label.pdf",
    "caifuclaw_business_app/*.log",
    "caifuclaw_business_app/frontend/*.log",
)

PRESERVED_TEXT_COLUMNS = {
    "action",
    "artifact_type",
    "auth_type",
    "authorization_status",
    "base_date_field",
    "biz_status",
    "calculation_status",
    "carrier_code",
    "code",
    "content_type",
    "credential_type",
    "currency",
    "currency_code",
    "cursor_key",
    "document_type",
    "entity_type",
    "event_type",
    "fulfillment_type",
    "grain",
    "job_type",
    "listing_status",
    "local_status",
    "mapping_status",
    "menu_code",
    "operation_attribute",
    "operation_type",
    "page_orientation",
    "platform",
    "platform_status",
    "price_currency",
    "printer_system",
    "provider",
    "result",
    "source",
    "source_language",
    "status",
    "task_type",
    "trigger_mode",
}

PRESERVED_NUMERIC_COLUMNS = {
    "attempt_count",
    "attempt_no",
    "batch_chars",
    "batch_size",
    "credentials_version",
    "cutover_run_id",
    "interval_seconds",
    "max_attempts",
    "max_retry_count",
    "max_retries",
    "offset_days",
    "pid",
    "priority",
    "rate_limit_per_minute",
    "retry_count",
    "retry_interval_minutes",
    "sort_order",
    "timeout_minutes",
    "timeout_seconds",
}

IDENTIFIER_PARTS = (
    "account",
    "barcode",
    "customer",
    "ean",
    "event_key",
    "fingerprint",
    "internal_order",
    "order_no",
    "owner_id",
    "posting_number",
    "product_code",
    "product_id",
    "purchase_no",
    "record_key",
    "request_id",
    "sha256",
    "shop_id",
    "sku",
    "state",
    "tracking",
    "transaction_id",
    "warehouse_code",
)

NUMERIC_DATA_PARTS = (
    "amount",
    "buyers",
    "clicks",
    "cost",
    "count",
    "fee",
    "height",
    "impressions",
    "length",
    "margin",
    "price",
    "qty",
    "quantity",
    "rate",
    "revenue",
    "reviews",
    "size_bytes",
    "stock",
    "units",
    "weight",
    "width",
)

JSON_ARRAY_COLUMNS = {
    "country_codes",
    "default_mentioned_list",
    "default_mentioned_mobile_list",
    "default_mentioned_user_ids",
    "local_order_ids",
    "scopes",
    "shop_names",
}


@dataclass(frozen=True)
class ColumnInfo:
    name: str
    data_type: str
    nullable: bool
    maximum_length: int | None


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--orders", type=int, default=100, help="Orders to retain (default: 100).")
    parser.add_argument("--products", type=int, default=200, help="Products to retain (default: 200).")
    parser.add_argument(
        "--traffic-metrics",
        type=int,
        default=500,
        help="Traffic metric rows to retain (default: 500).",
    )
    parser.add_argument(
        "--catalog-items",
        type=int,
        default=30,
        help="Platform catalog rows to retain (default: 30).",
    )
    parser.add_argument("--apply", action="store_true", help="Commit database, config, and file changes.")
    parser.add_argument("--keep-files", action="store_true", help="Do not remove local runtime data files.")
    parser.add_argument("--keep-config", action="store_true", help="Do not sanitize the local runtime config.")
    return parser


def _quote_identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _table_names(connection: Connection) -> set[str]:
    return set(inspect(connection).get_table_names(schema="public"))


def _table_columns(connection: Connection, table_name: str) -> list[ColumnInfo]:
    rows = connection.execute(
        text(
            """
            SELECT column_name, data_type, is_nullable, character_maximum_length
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = :table_name
            ORDER BY ordinal_position
            """
        ),
        {"table_name": table_name},
    ).all()
    return [
        ColumnInfo(
            name=row.column_name,
            data_type=row.data_type,
            nullable=row.is_nullable == "YES",
            maximum_length=row.character_maximum_length,
        )
        for row in rows
    ]


def _row_count(connection: Connection, table_name: str) -> int:
    table = _quote_identifier(table_name)
    return int(connection.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def _delete_after_limit(connection: Connection, table_name: str, limit: int) -> int:
    if limit < 1:
        raise ValueError(f"Retention limit for {table_name} must be at least 1")
    table = _quote_identifier(table_name)
    result = connection.execute(
        text(
            f"""
            DELETE FROM {table}
            WHERE id NOT IN (
                SELECT id FROM {table} ORDER BY id ASC LIMIT :limit
            )
            """
        ),
        {"limit": limit},
    )
    return int(result.rowcount or 0)


def _clear_table(connection: Connection, table_name: str, available_tables: set[str]) -> int:
    if table_name not in available_tables:
        return 0
    result = connection.execute(text(f"DELETE FROM {_quote_identifier(table_name)}"))
    return int(result.rowcount or 0)


def _prepare_retention_deletes(
    connection: Connection,
    available_tables: set[str],
    *,
    order_limit: int,
    product_limit: int,
) -> int:
    deleted = 0
    if "orders" in available_tables:
        keep_orders = "SELECT id FROM orders ORDER BY id ASC LIMIT :order_limit"
        if "shipments" in available_tables:
            result = connection.execute(
                text(f"DELETE FROM shipments WHERE order_id NOT IN ({keep_orders})"),
                {"order_limit": order_limit},
            )
            deleted += int(result.rowcount or 0)
        if "purchase_order_sources" in available_tables:
            result = connection.execute(
                text(
                    f"""
                    DELETE FROM purchase_order_sources
                    WHERE order_id IS NOT NULL AND order_id NOT IN ({keep_orders})
                    """
                ),
                {"order_limit": order_limit},
            )
            deleted += int(result.rowcount or 0)

    if "products" in available_tables and "purchase_order_sources" in available_tables:
        keep_products = "SELECT id FROM products ORDER BY id ASC LIMIT :product_limit"
        result = connection.execute(
            text(
                f"""
                UPDATE purchase_order_sources
                SET product_id = NULL
                WHERE product_id IS NOT NULL AND product_id NOT IN ({keep_products})
                """
            ),
            {"product_limit": product_limit},
        )
        deleted += int(result.rowcount or 0)
    return deleted


def _synthetic_text_expression(table_name: str, column: ColumnInfo) -> str | None:
    name = column.name.lower()
    quoted = _quote_identifier(column.name)
    if name in PRESERVED_TEXT_COLUMNS or name == "account_id":
        return None
    if name == "password_hash":
        return None
    if "email" in name:
        value = "'demo+' || id::text || '@example.invalid'"
    elif "mobile" in name or "phone" in name:
        value = "''"
    elif any(part in name for part in ("url", "endpoint", "host", "device_uri")):
        value = "''"
    elif any(part in name for part in ("file_path", "filename", "printer_name", "port_name")):
        value = "''"
    elif any(part in name for part in ("message", "description", "remark", "note", "comment", "reason", "summary", "prompt")):
        value = "'Sanitized demo record'"
    elif name == "username":
        value = "'demo_user_' || id::text"
    elif name in {"display_name", "buyer_name", "product_name", "internal_name", "english_name", "shop_name", "warehouse_name", "account_name", "carrier_name", "name"}:
        value = "'Demo ' || id::text"
    elif any(part in name for part in IDENTIFIER_PARTS):
        value = "'DEMO-' || id::text"
    elif any(part in name for part in ("address", "addressee", "operator", "created_by", "mapped_by", "scanned_by")):
        value = "'Demo ' || id::text"
    else:
        value = "'Sanitized ' || id::text"
    if column.maximum_length:
        value = f"left({value}, {column.maximum_length})"
    return f"CASE WHEN {quoted} IS NULL THEN NULL ELSE {value} END"


def _synthetic_numeric_expression(column: ColumnInfo) -> str | None:
    name = column.name.lower()
    quoted = _quote_identifier(column.name)
    if name == "id" or name.endswith("_id") or name in PRESERVED_NUMERIC_COLUMNS:
        return None
    if not any(part in name for part in NUMERIC_DATA_PARTS):
        return None
    if column.data_type in {"integer", "bigint", "smallint"}:
        value = "((id % 20) + 1)"
    else:
        value = "(((id % 100) + 100)::numeric / 10)"
    return f"CASE WHEN {quoted} IS NULL THEN NULL ELSE {value} END"


def _synthetic_expression(table_name: str, column: ColumnInfo) -> str | None:
    quoted = _quote_identifier(column.name)
    if column.name == "id":
        return None
    if column.data_type in {"character varying", "text", "character"}:
        return _synthetic_text_expression(table_name, column)
    if column.data_type in {"json", "jsonb"}:
        empty = "[]" if column.name in JSON_ARRAY_COLUMNS else "{}"
        return f"CASE WHEN {quoted} IS NULL THEN NULL ELSE '{empty}'::{column.data_type} END"
    if column.data_type == "bytea":
        return "NULL" if column.nullable else "decode('', 'hex')"
    if column.data_type == "date":
        return f"CASE WHEN {quoted} IS NULL THEN NULL ELSE DATE '2026-01-01' + (id % 90)::integer END"
    if column.data_type == "timestamp without time zone":
        return (
            f"CASE WHEN {quoted} IS NULL THEN NULL ELSE "
            f"TIMESTAMP '{DEMO_TIMESTAMP}' + ((id % 90) * INTERVAL '1 day') END"
        )
    if column.data_type in {"integer", "bigint", "smallint", "numeric", "real", "double precision"}:
        return _synthetic_numeric_expression(column)
    return None


def _sanitize_table(connection: Connection, table_name: str) -> int:
    assignments: list[str] = []
    for column in _table_columns(connection, table_name):
        expression = _synthetic_expression(table_name, column)
        if expression is not None:
            assignments.append(f"{_quote_identifier(column.name)} = {expression}")
    if not assignments:
        return 0
    table = _quote_identifier(table_name)
    result = connection.execute(text(f"UPDATE {table} SET {', '.join(assignments)}"))
    return int(result.rowcount or 0)


def _map_account_identifiers(connection: Connection, available_tables: set[str]) -> None:
    if "platform_accounts" not in available_tables:
        return
    dependent_tables = (
        "orders",
        "sync_account_states",
        "sync_cursors",
        "sync_settings",
        "traffic_metrics",
    )
    for table_name in dependent_tables:
        if table_name not in available_tables:
            continue
        columns = {column.name for column in _table_columns(connection, table_name)}
        if not {"platform", "account_id"}.issubset(columns):
            continue
        table = _quote_identifier(table_name)
        connection.execute(
            text(
                f"""
                UPDATE {table} AS child
                SET account_id = 'demo-account-' || account.id::text
                FROM platform_accounts AS account
                WHERE child.platform = account.platform
                  AND child.account_id = account.account_id
                """
            )
        )
        connection.execute(
            text(
                f"""
                UPDATE {table}
                SET account_id = 'demo-account-row-' || id::text
                WHERE account_id IS NOT NULL
                  AND account_id NOT LIKE 'demo-account-%'
                """
            )
        )
    connection.execute(text("UPDATE platform_accounts SET account_id = 'demo-account-' || id::text"))


def _apply_table_overrides(connection: Connection, available_tables: set[str]) -> None:
    if "local_users" in available_tables:
        password_hash = hash_password(DEMO_ADMIN_PASSWORD)
        connection.execute(
            text(
                """
                UPDATE local_users
                SET username = CASE
                        WHEN id = (SELECT min(id) FROM local_users) THEN :admin_username
                        ELSE 'demo_user_' || id::text
                    END,
                    password_hash = :password_hash,
                    display_name = CASE
                        WHEN id = (SELECT min(id) FROM local_users) THEN 'Demo Administrator'
                        ELSE 'Demo User ' || id::text
                    END,
                    wecom_mobile = NULL
                """
            ),
            {"admin_username": DEMO_ADMIN_USERNAME, "password_hash": password_hash},
        )

    statements = {
        "platform_accounts": """
            UPDATE platform_accounts
            SET enabled = false,
                encrypted_credentials = NULL,
                token_valid = false,
                token_message = 'Sanitized; authorization required',
                settings = '{}'::jsonb,
                last_sync_at = NULL,
                last_authorized_at = NULL,
                authorization_expires_at = NULL,
                session_expires_at = NULL
        """,
        "logistics_authorizations": """
            UPDATE logistics_authorizations
            SET enabled = false,
                encrypted_credentials = NULL,
                config_json = '{}'::jsonb,
                settings_json = '{}'::jsonb,
                token_valid = false,
                token_message = 'Sanitized; authorization required',
                last_authorized_at = NULL,
                authorization_expires_at = NULL
        """,
        "sync_settings": "UPDATE sync_settings SET enabled = false, last_run_at = NULL",
        "scheduled_tasks": "UPDATE scheduled_tasks SET enabled = false, settings = '{}'::jsonb",
        "email_smtp_settings": """
            UPDATE email_smtp_settings
            SET enabled = false,
                encrypted_auth_code = NULL,
                notification_recipients = '{}'::jsonb,
                last_test_at = NULL,
                last_test_status = '',
                last_test_message = ''
        """,
        "wecom_robot_settings": """
            UPDATE wecom_robot_settings
            SET encrypted_webhook_url = NULL,
                default_mentioned_user_ids = '[]'::jsonb,
                default_mentioned_list = '[]'::jsonb,
                default_mentioned_mobile_list = '',
                purchase_order_notify_enabled = false
        """,
        "translation_provider_settings": """
            UPDATE translation_provider_settings
            SET enabled = false,
                app_id = '',
                encrypted_secret_key = NULL,
                provider_options_json = '{}',
                last_test_at = NULL,
                last_test_status = '',
                last_test_message = ''
        """,
        "model_endpoints": "UPDATE model_endpoints SET enabled = false, encrypted_api_key = NULL",
        "model_settings": "UPDATE model_settings SET enabled = false, is_default = false",
        "orders": """
            UPDATE orders AS order_row
            SET shop_id = order_row.account_id,
                shop_name = account.display_name
            FROM platform_accounts AS account
            WHERE order_row.platform = account.platform
              AND order_row.account_id = account.account_id
        """,
        "traffic_metrics": """
            UPDATE traffic_metrics AS metric
            SET shop_name = account.display_name
            FROM platform_accounts AS account
            WHERE metric.platform_account_id = account.id
        """,
    }
    for table_name, statement in statements.items():
        if table_name in available_tables:
            connection.execute(text(statement))


def sanitize_database(
    *,
    order_limit: int,
    product_limit: int,
    traffic_limit: int,
    catalog_limit: int,
    apply: bool,
) -> dict[str, Any]:
    limits = {
        "orders": order_limit,
        "products": product_limit,
        "traffic_metrics": traffic_limit,
        "platform_product_catalog_items": catalog_limit,
    }
    if any(limit < 1 for limit in limits.values()):
        raise ValueError("All retention limits must be at least 1")

    with engine.connect() as connection:
        available_tables = _table_names(connection)
        before = {table: _row_count(connection, table) for table in sorted(available_tables)}
        result: dict[str, Any] = {
            "applied": apply,
            "tables": len(available_tables),
            "before_rows": sum(before.values()),
            "planned_clear_rows": sum(before.get(table, 0) for table in CLEAR_TABLES),
            "planned_retention_deletes": sum(
                max(before.get(table, 0) - limit, 0) for table, limit in limits.items()
            ),
        }
        if not apply:
            return result

        connection.rollback()
        transaction = connection.begin()
        try:
            cleared = {
                table: _clear_table(connection, table, available_tables)
                for table in CLEAR_TABLES
            }
            prepared_rows = _prepare_retention_deletes(
                connection,
                available_tables,
                order_limit=order_limit,
                product_limit=product_limit,
            )
            deleted = {
                table: _delete_after_limit(connection, table, limit)
                for table, limit in limits.items()
                if table in available_tables
            }
            _map_account_identifiers(connection, available_tables)
            updated = {
                table: _sanitize_table(connection, table)
                for table in sorted(available_tables)
                if table not in CLEAR_TABLES
            }
            _apply_table_overrides(connection, available_tables)
            transaction.commit()
        except Exception:
            transaction.rollback()
            raise

        after = {table: _row_count(connection, table) for table in sorted(available_tables)}
        result.update(
            {
                "cleared_rows": sum(cleared.values()),
                "prepared_rows": prepared_rows,
                "retention_deletes": sum(deleted.values()),
                "updated_rows": sum(updated.values()),
                "after_rows": sum(after.values()),
            }
        )
        return result


def _sanitize_config_text(
    source: str,
    *,
    template: bool = False,
) -> tuple[str, list[str]]:
    section = ""
    changed: list[str] = []
    output: list[str] = []
    section_pattern = re.compile(r"^\s*\[([^]]+)]\s*(?:#.*)?$")
    value_pattern = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)\s*=.*$")
    replacements = {
        "security.sync_secret_key": f'"{DEMO_SYNC_SECRET}"',
        "security.fernet_key": '""',
        "sync_admin.username": f'"{DEMO_ADMIN_USERNAME}"',
        "sync_admin.password": f'"{DEMO_ADMIN_PASSWORD}"',
        "exchange_rates.enabled": "false",
    }
    if template:
        replacements["postgres.password"] = '"change-me"'
        replacements["sync_admin.password"] = '"REPLACE_WITH_AT_LEAST_12_RANDOM_CHARACTERS"'
    secret_keys = {
        "access_key_id",
        "access_key_secret",
        "api_key",
        "client_id",
        "client_secret",
        "internal_service_token",
        "secret_id",
        "secret_key",
    }

    for line in source.splitlines(keepends=True):
        section_match = section_pattern.match(line.rstrip("\r\n"))
        if section_match:
            section = section_match.group(1)
            output.append(line)
            continue
        value_match = value_pattern.match(line.rstrip("\r\n"))
        if not value_match:
            output.append(line)
            continue
        key = value_match.group(2)
        path = f"{section}.{key}" if section else key
        replacement = replacements.get(path)
        if replacement is None and key in secret_keys and section != "postgres":
            replacement = '""'
        if replacement is None:
            output.append(line)
            continue
        newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
        output.append(f"{value_match.group(1)}{key} = {replacement}{newline}")
        changed.append(path)
    return "".join(output), changed


def sanitize_runtime_config(*, apply: bool) -> dict[str, Any]:
    targets = (
        (ROOT / "caifuclaw_business_app" / "config.toml", False),
        (ROOT / "caifuclaw_business_app" / "config.template.toml", True),
    )
    existing = 0
    changed_keys = 0
    changed_files = 0
    for path, is_template in targets:
        if not path.exists():
            continue
        existing += 1
        source = path.read_text(encoding="utf-8-sig")
        sanitized, changed = _sanitize_config_text(source, template=is_template)
        changed_keys += len(changed)
        if sanitized == source:
            continue
        changed_files += 1
        if apply:
            temporary = path.with_suffix(path.suffix + ".sanitizing")
            temporary.write_text(sanitized, encoding="utf-8", newline="")
            temporary.replace(path)
    return {
        "existing_files": existing,
        "changed_files": changed_files,
        "changed_keys": changed_keys,
        "applied": apply,
    }


def _is_safe_runtime_path(path: Path) -> bool:
    resolved_root = ROOT.resolve()
    resolved = path.resolve()
    return resolved != resolved_root and resolved_root in resolved.parents


def _runtime_files() -> list[Path]:
    files: set[Path] = set()
    for relative in RUNTIME_DIRECTORIES:
        directory = (ROOT / relative).resolve()
        if not directory.exists() or not _is_safe_runtime_path(directory):
            continue
        files.update(path for path in directory.rglob("*") if path.is_file() or path.is_symlink())
    for pattern in RUNTIME_FILE_PATTERNS:
        files.update(path for path in ROOT.glob(pattern) if path.is_file() or path.is_symlink())
    return sorted(files)


def sanitize_runtime_files(*, apply: bool) -> dict[str, Any]:
    files = _runtime_files()
    failures = 0
    if apply:
        for path in files:
            if not _is_safe_runtime_path(path):
                raise RuntimeError(f"Refusing to remove an unsafe path: {path}")
            try:
                path.unlink(missing_ok=True)
            except PermissionError:
                failures += 1
        for relative in RUNTIME_DIRECTORIES:
            directory = (ROOT / relative).resolve()
            if not directory.exists() or not _is_safe_runtime_path(directory):
                continue
            for child in sorted(directory.rglob("*"), reverse=True):
                if child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
        if failures:
            raise RuntimeError(f"Unable to remove {failures} runtime files because they are in use")
    return {"files": len(files), "failures": failures, "applied": apply}


def main() -> int:
    args = _parser().parse_args()
    database_result = sanitize_database(
        order_limit=args.orders,
        product_limit=args.products,
        traffic_limit=args.traffic_metrics,
        catalog_limit=args.catalog_items,
        apply=args.apply,
    )
    config_result = (
        {"skipped": True, "applied": args.apply}
        if args.keep_config
        else sanitize_runtime_config(apply=args.apply)
    )
    file_result = (
        {"skipped": True, "applied": args.apply}
        if args.keep_files
        else sanitize_runtime_files(apply=args.apply)
    )
    print("database: " + ", ".join(f"{key}={value}" for key, value in database_result.items()))
    print("config: " + ", ".join(f"{key}={value}" for key, value in config_result.items()))
    print("files: " + ", ".join(f"{key}={value}" for key, value in file_result.items()))
    if not args.apply:
        print("Dry run only. Re-run with --apply to commit the sanitization.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
