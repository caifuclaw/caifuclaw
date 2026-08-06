#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from passlib.context import CryptContext
from psycopg import sql
from sqlalchemy import MetaData, Table, create_engine, select

try:
    from .backup_postgres import resolve_pg_command
    from .export_database import (
        business_config_path,
        load_toml,
        postgres_connect_kwargs,
        postgres_literal,
        postgres_url,
    )
except ImportError:
    from backup_postgres import resolve_pg_command  # type: ignore[no-redef]
    from export_database import (  # type: ignore[no-redef]
        business_config_path,
        load_toml,
        postgres_connect_kwargs,
        postgres_literal,
        postgres_url,
    )


PROJECT_ROOT = Path(__file__).resolve().parents[2]
TEST_ADMIN_USERNAME = "testadmin"
TEST_ADMIN_PASSWORD = "TestPass123!"
PASSWORD_CONTEXT = CryptContext(schemes=["bcrypt"], deprecated="auto")
CONFIG_SECRET_VALUE = "CHANGE_ME"

REFERENCE_TABLES = [
    "roles",
    "role_menu_permissions",
    "platform_settings",
    "dashboard_platform_settings",
    "exchange_rate_currency_settings",
    "exchange_rates",
    "shipping_deadline_settings",
]


def normalize_postgres_schema_for_driver(content: str) -> str:
    """Remove psql-only dump guards before restoring through psycopg."""
    normalized = re.sub(r"(?m)^\\(?:restrict|unrestrict)\b[^\r\n]*(?:\r?\n)?", "", content)
    normalized = re.sub(r"(?m)^SET transaction_timeout = 0;\r?\n", "", normalized)
    return normalized.rstrip() + "\n"


@dataclass
class FixtureContext:
    generated_at: datetime
    user_id: int
    role_id: int
    password_hash: str
    account_aliases: dict[tuple[str, str], str] = field(default_factory=dict)
    fallback_accounts: dict[str, str] = field(default_factory=dict)
    sku_aliases: dict[str, str] = field(default_factory=dict)

    def account_alias(self, platform: Any, account_id: Any) -> str:
        normalized_platform = str(platform or "test")
        existing = self.account_aliases.get((normalized_platform, str(account_id or "")))
        return existing or self.fallback_accounts.get(normalized_platform, f"test-{normalized_platform}-fixture")

    def sku_alias(self, sku: Any, row_id: Any) -> str:
        existing = self.sku_aliases.get(str(sku or ""))
        return existing or f"TEST-ORDER-SKU-{row_id}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a sanitized CaifuClaw AI test database fixture.")
    parser.add_argument("--project-root", type=Path, default=PROJECT_ROOT, help="Project root directory.")
    parser.add_argument("--output-dir", type=Path, required=True, help="Empty directory for the generated fixture.")
    parser.add_argument("--orders-limit", type=int, default=20, help="Number of recent order records to include.")
    parser.add_argument("--products-limit", type=int, default=100, help="Number of recent product records to include.")
    parser.add_argument("--pg-dump", default=os.getenv("PG_DUMP_BIN", "pg_dump"), help="pg_dump executable path.")
    return parser.parse_args()


def require_empty_output_dir(path: Path) -> None:
    if path.exists():
        if not path.is_dir():
            raise RuntimeError(f"Output path is not a directory: {path}")
        if any(path.iterdir()):
            raise RuntimeError(f"Output directory must be empty: {path}")
    else:
        path.mkdir(parents=True, mode=0o700)
    os.chmod(path, 0o700)


def pg_table(metadata: MetaData, name: str) -> Table:
    table = metadata.tables.get(name) or metadata.tables.get(f"public.{name}")
    if table is None:
        raise RuntimeError(f"PostgreSQL table not found: {name}")
    return table


def fetch_rows(
    connection: Any,
    table: Table,
    *,
    ids: set[int] | None = None,
    column: str = "id",
    limit: int | None = None,
    order_by: str = "id",
    descending: bool = False,
) -> list[dict[str, Any]]:
    statement = select(*table.columns)
    if ids is not None:
        if not ids:
            return []
        statement = statement.where(table.c[column].in_(sorted(ids)))
    if order_by in table.c:
        primary_order = table.c[order_by].desc() if descending else table.c[order_by]
        id_order = table.c.id.desc() if descending else table.c.id
        statement = statement.order_by(primary_order, id_order)
    elif "id" in table.c:
        statement = statement.order_by(table.c.id)
    if limit is not None:
        statement = statement.limit(limit)
    return [dict(row) for row in connection.execute(statement).mappings().all()]


def write_insert(file: Any, raw_connection: Any, table: Table, row: dict[str, Any]) -> None:
    columns = [column for column in table.columns if column.name in row]
    if not columns:
        return
    table_name = sql.SQL(".").join([sql.Identifier("public"), sql.Identifier(table.name)]).as_string(raw_connection)
    column_names = ", ".join(sql.Identifier(column.name).as_string(raw_connection) for column in columns)
    values = ", ".join(postgres_literal(raw_connection, row[column.name], column.type) for column in columns)
    file.write(f"INSERT INTO {table_name} ({column_names}) VALUES ({values});\n")


def sanitize_reference_row(table_name: str, row: dict[str, Any], context: FixtureContext) -> dict[str, Any]:
    return dict(row)


def sanitize_row(table_name: str, row: dict[str, Any], context: FixtureContext) -> dict[str, Any]:
    result = sanitize_reference_row(table_name, row, context)
    row_id = result.get("id", 0)
    if table_name == "platform_accounts":
        alias = context.account_alias(result.get("platform"), row.get("account_id"))
        result.update(
            {
                "account_id": alias,
                "display_name": f"Test {result.get('platform', 'Platform')} Shop {row_id}",
                "enabled": False,
                "auth_type": "test",
                "credential_type": "test",
                "encrypted_credentials": None,
                "settings": {},
                "status": "disabled",
                "session_expires_at": None,
                "last_sync_at": None,
                "last_sync_status": "",
                "credentials_version": "",
                "authorization_status": "unauthorized",
                "token_valid": None,
                "token_message": None,
                "last_authorized_at": None,
                "authorization_expires_at": None,
                "created_by": TEST_ADMIN_USERNAME,
            }
        )
    elif table_name == "products":
        result.update(
            {
                "product_code": f"TEST-PRODUCT-{row_id}",
                "internal_name": f"Test Product {row_id}",
                "english_name": f"Test Product {row_id}",
                "cost": 10,
                "weight": 0.5,
                "safety_stock": 10,
                "buyer_user_id": context.user_id,
                "gross_weight": 0.5,
                "package_length": 10,
                "package_width": 10,
                "package_height": 10,
                "ean": f"TEST-EAN-{row_id}",
                "description": "Sanitized test product.",
                "main_image_url": "",
            }
        )
    elif table_name == "product_inventory":
        result.update({"product_name": f"Test Product {result.get('product_id')}", "stock_qty": 100, "last_count_qty": 100, "remark": "", "updated_by": TEST_ADMIN_USERNAME})
    elif table_name == "product_shop_mappings":
        result["shop_sku"] = context.sku_alias(row.get("shop_sku"), row_id)
    elif table_name == "platform_product_catalog_items":
        result.update(
            {
                "platform_product_id": f"TEST-PLATFORM-PRODUCT-{row_id}",
                "platform_sku": f"TEST-CATALOG-SKU-{row_id}",
                "product_name": f"Test Product {result.get('product_id')}",
                "warehouse_code": "TEST-WH",
                "warehouse_name": "Test Warehouse",
                "raw_payload": {},
            }
        )
    elif table_name == "orders":
        platform = result.get("platform", "test")
        account = context.account_alias(platform, row.get("account_id"))
        result.update(
            {
                "tenant_id": "test-tenant",
                "account_id": account,
                "shop_id": account,
                "shop_name": f"Test {platform} Shop",
                "platform_order_id": f"TEST-ORDER-{row_id}",
                "platform_order_no": f"TEST-ORDER-NO-{row_id}",
                "posting_number": f"TEST-POSTING-{row_id}",
                "buyer_id": f"TEST-BUYER-{row_id}",
                "buyer_name": "Test Buyer",
                "buyer_selected_logistics": "Test Logistics",
                "shipment_tracking_number": f"TEST-TRACK-{row_id}",
                "internal_order_no": f"TEST-INTERNAL-{row_id}",
                "raw_payload": {},
                "last_api_payload": {},
                "error_message": "",
                "logistics_match_rule_name": "Test Rule",
                "logistics_match_reason": "Sanitized fixture",
                "bsi_order_no": "",
            }
        )
    elif table_name == "order_items":
        result.update(
            {
                "sku": context.sku_alias(row.get("sku"), row_id),
                "platform_product_name": f"Test Item {row_id}",
                "unit_price": "10.00",
                "raw_payload": {},
            }
        )
    elif table_name == "shipments":
        result.update({"platform_shipment_id": f"TEST-SHIPMENT-{row_id}", "tracking_number": f"TEST-TRACK-{row_id}", "carrier": "Test Carrier"})
    elif table_name == "order_operation_logs":
        result.update({"description": "Sanitized test operation", "operator": TEST_ADMIN_USERNAME, "event_key": f"test-event-{row_id}", "extra": {}})
    elif table_name == "order_risk_handlings":
        result.update({"handled_by": TEST_ADMIN_USERNAME, "note": "Sanitized test risk note"})
    elif table_name == "outbound_scan_records":
        result.update(
            {
                "tracking_number": f"TEST-SCAN-{row_id}",
                "raw_input": f"TEST-SCAN-{row_id}",
                "shop_name": "Test Shop",
                "platform_order_no": f"TEST-ORDER-NO-{result.get('order_id')}",
                "posting_number": f"TEST-POSTING-{result.get('order_id')}",
                "message": "Sanitized test scan",
                "scanned_by": TEST_ADMIN_USERNAME,
            }
        )
    elif table_name == "purchase_orders":
        result.update({"purchase_no": f"TEST-PO-{row_id}", "created_by": TEST_ADMIN_USERNAME, "remark": "Sanitized test purchase order"})
    elif table_name == "purchase_order_items":
        result.update(
            {
                "product_name": f"Test Product {result.get('product_id') or row_id}",
                "buyer_user_id": context.user_id,
                "buyer": TEST_ADMIN_USERNAME,
                "purchase_channel": "Test Supplier",
                "remark": "Sanitized test purchase item",
                "total_cost_record": 10,
                "purchase_cost": 10,
            }
        )
    elif table_name == "purchase_order_sources":
        result["product_name"] = f"Test Product {result.get('product_id') or row_id}"
    elif table_name == "logistics_match_rules":
        result.update({"name": f"Test Logistics Rule {row_id}", "shop_names": [], "remark": "Sanitized test rule", "created_by": TEST_ADMIN_USERNAME})
    return result


def build_account_context(account_rows: list[dict[str, Any]], context: FixtureContext) -> None:
    for row in account_rows:
        platform = str(row.get("platform") or "test")
        alias = f"test-{platform}-{row['id']}"
        context.account_aliases[(platform, str(row.get("account_id") or ""))] = alias
        context.fallback_accounts.setdefault(platform, alias)


def build_sku_context(mapping_rows: list[dict[str, Any]], context: FixtureContext) -> None:
    for row in mapping_rows:
        context.sku_aliases.setdefault(str(row.get("shop_sku") or ""), f"TEST-SKU-{row['id']}")


def write_postgres_schema(config: dict[str, Any], output_path: Path, pg_dump: str) -> None:
    command = [
        resolve_pg_command(pg_dump, "pg_dump"),
        "--host",
        str(config["postgres"]["host"]),
        "--port",
        str(config["postgres"]["port"]),
        "--username",
        str(config["postgres"]["user"]),
        "--dbname",
        str(config["databases"]["sync"]),
        "--schema-only",
        "--no-owner",
        "--no-acl",
        "--file",
        str(output_path),
    ]
    env = os.environ.copy()
    env["PGPASSWORD"] = str(config["postgres"]["password"])
    result = subprocess.run(command, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"pg_dump schema export failed: {result.stdout.strip()}")
    output_path.write_text(
        normalize_postgres_schema_for_driver(output_path.read_text(encoding="utf-8")),
        encoding="utf-8",
        newline="\n",
    )


def write_postgres_create_database(output_path: Path) -> None:
    output_path.write_text(
        "-- Create the test database before importing postgres_schema.sql.\n"
        "CREATE DATABASE caifuclaw_ai_test WITH ENCODING 'UTF8';\n",
        encoding="utf-8",
    )


def selected_postgres_rows(connection: Any, metadata: MetaData, orders_limit: int, products_limit: int) -> dict[str, list[dict[str, Any]]]:
    rows: dict[str, list[dict[str, Any]]] = {}
    for table_name in REFERENCE_TABLES:
        rows[table_name] = fetch_rows(connection, pg_table(metadata, table_name))

    rows["platform_accounts"] = fetch_rows(connection, pg_table(metadata, "platform_accounts"))

    latest_orders = fetch_rows(connection, pg_table(metadata, "orders"), limit=orders_limit, order_by="created_at", descending=True)
    purchase_orders = fetch_rows(connection, pg_table(metadata, "purchase_orders"), limit=1, order_by="created_at", descending=True)
    purchase_order_ids = {int(row["id"]) for row in purchase_orders}
    purchase_items = fetch_rows(connection, pg_table(metadata, "purchase_order_items"), ids=purchase_order_ids, column="purchase_order_id")
    purchase_sources = fetch_rows(connection, pg_table(metadata, "purchase_order_sources"), ids=purchase_order_ids, column="purchase_order_id")

    order_ids = {int(row["id"]) for row in latest_orders}
    order_ids.update(int(row["order_id"]) for row in purchase_sources if row.get("order_id") is not None)
    rows["orders"] = fetch_rows(connection, pg_table(metadata, "orders"), ids=order_ids)

    requested_item_ids = {int(row["order_item_id"]) for row in purchase_sources if row.get("order_item_id") is not None}
    order_items = fetch_rows(connection, pg_table(metadata, "order_items"), ids=order_ids, column="order_id")
    order_items.extend(fetch_rows(connection, pg_table(metadata, "order_items"), ids=requested_item_ids))
    rows["order_items"] = list({int(row["id"]): row for row in order_items}.values())

    product_ids = {int(row["product_id"]) for row in purchase_items if row.get("product_id") is not None}
    product_ids.update(int(row["product_id"]) for row in purchase_sources if row.get("product_id") is not None)
    latest_products = fetch_rows(connection, pg_table(metadata, "products"), limit=products_limit, order_by="updated_at", descending=True)
    product_ids.update(int(row["id"]) for row in latest_products)

    all_mappings = fetch_rows(connection, pg_table(metadata, "product_shop_mappings"))
    order_skus = {str(row.get("sku") or "") for row in rows["order_items"]}
    product_ids.update(int(row["product_id"]) for row in all_mappings if str(row.get("shop_sku") or "") in order_skus)
    rows["products"] = fetch_rows(connection, pg_table(metadata, "products"), ids=product_ids)
    rows["product_inventory"] = fetch_rows(connection, pg_table(metadata, "product_inventory"), ids=product_ids, column="product_id")
    rows["product_shop_mappings"] = [row for row in all_mappings if int(row["product_id"]) in product_ids]
    rows["shipments"] = fetch_rows(connection, pg_table(metadata, "shipments"), ids=order_ids, column="order_id")
    rows["order_operation_logs"] = fetch_rows(connection, pg_table(metadata, "order_operation_logs"), ids=order_ids, column="order_id")[:40]
    rows["order_risk_handlings"] = fetch_rows(connection, pg_table(metadata, "order_risk_handlings"), ids=order_ids, column="order_id")
    rows["outbound_scan_records"] = fetch_rows(connection, pg_table(metadata, "outbound_scan_records"), ids=order_ids, column="order_id")[:20]
    rows["purchase_orders"] = purchase_orders
    rows["purchase_order_items"] = purchase_items
    rows["purchase_order_sources"] = purchase_sources

    return rows


def write_postgres_seed(project_root: Path, output_path: Path, orders_limit: int, products_limit: int) -> dict[str, int]:
    config = load_toml(business_config_path(project_root))
    engine = create_engine(postgres_url(config), pool_pre_ping=True)
    metadata = MetaData()
    metadata.reflect(bind=engine, schema="public")
    row_counts: dict[str, int] = {}

    try:
        with psycopg.connect(**postgres_connect_kwargs(config)) as raw_connection, engine.connect() as connection:
            roles = fetch_rows(connection, pg_table(metadata, "roles"))
            if not roles:
                raise RuntimeError("Cannot build fixture without at least one role")
            users = fetch_rows(connection, pg_table(metadata, "local_users"), limit=1)
            if not users:
                raise RuntimeError("Cannot build fixture without at least one local user")
            context = FixtureContext(
                generated_at=datetime.now().astimezone(),
                user_id=int(users[0]["id"]),
                role_id=int(roles[0]["id"]),
                password_hash=PASSWORD_CONTEXT.hash(TEST_ADMIN_PASSWORD),
            )
            selected_rows = selected_postgres_rows(connection, metadata, orders_limit, products_limit)
            build_account_context(selected_rows["platform_accounts"], context)
            build_sku_context(selected_rows["product_shop_mappings"], context)

            order = [
                *REFERENCE_TABLES,
                "platform_accounts",
                "products",
                "product_inventory",
                "product_shop_mappings",
                "orders",
                "order_items",
                "shipments",
                "order_operation_logs",
                "order_risk_handlings",
                "outbound_scan_records",
                "purchase_orders",
                "purchase_order_items",
                "purchase_order_sources",
            ]

            with output_path.open("w", encoding="utf-8", newline="\n") as file:
                file.write("-- Sanitized CaifuClaw AI test fixture. Import after postgres_schema.sql.\n")
                file.write("-- No production credentials, tokens, buyer names, buyer IDs, addresses, request logs, or raw API payloads are included.\n")
                file.write("SET client_encoding = 'UTF8';\n")
                file.write("SET standard_conforming_strings = on;\n")
                file.write("BEGIN;\n\n")

                user_inserted = False
                for table_name in order:
                    table_rows = selected_rows.get(table_name, [])
                    if not table_rows:
                        continue
                    table = pg_table(metadata, table_name)
                    file.write(f"-- Data for {table_name}: {len(table_rows)} rows\n")
                    for row in table_rows:
                        write_insert(file, raw_connection, table, sanitize_row(table_name, row, context))
                    file.write("\n")
                    row_counts[table_name] = len(table_rows)
                    if table_name == "roles" and not user_inserted:
                        user_row = dict(users[0])
                        user_row.update(
                            {
                                "username": TEST_ADMIN_USERNAME,
                                "password_hash": context.password_hash,
                                "display_name": "Test Administrator",
                                "wecom_mobile": "",
                                "role_id": context.role_id,
                                "role_code": roles[0].get("code", "admin"),
                                "enabled": True,
                                "created_at": context.generated_at.replace(tzinfo=None),
                                "updated_at": context.generated_at.replace(tzinfo=None),
                            }
                        )
                        file.write("-- Test login user\n")
                        write_insert(file, raw_connection, pg_table(metadata, "local_users"), user_row)
                        row_counts["local_users"] = 1

                        user_roles = fetch_rows(connection, pg_table(metadata, "user_roles"), limit=1)
                        if user_roles:
                            relation = dict(user_roles[0])
                            relation.update(
                                {
                                    "user_id": context.user_id,
                                    "role_id": context.role_id,
                                    "created_at": context.generated_at.replace(tzinfo=None),
                                }
                            )
                            write_insert(file, raw_connection, pg_table(metadata, "user_roles"), relation)
                            row_counts["user_roles"] = 1
                        file.write("\n")
                        user_inserted = True

                file.write("\n-- Reset sequences after explicit id inserts.\n")
                for table_name in sorted(row_counts):
                    table = pg_table(metadata, table_name)
                    if "id" not in table.c:
                        continue
                    qualified_name = sql.SQL(".").join([sql.Identifier("public"), sql.Identifier(table.name)]).as_string(raw_connection)
                    table_identifier = qualified_name
                    id_identifier = sql.Identifier("id").as_string(raw_connection)
                    file.write(
                        "SELECT setval(pg_get_serial_sequence("
                        f"'{qualified_name}', 'id'), "
                        f"COALESCE((SELECT MAX({id_identifier}) FROM {table_identifier}), 1), true);\n"
                    )
                file.write("COMMIT;\n")
    finally:
        engine.dispose()
    return row_counts


def is_sensitive_config_key(key: str) -> bool:
    normalized = key.lower()
    return normalized in {"password", "secret", "token", "api_key", "private_key"} or normalized.endswith(
        ("_password", "_secret", "_secret_key", "_token", "_api_key", "_private_key")
    )


def sanitize_config_template(content: str) -> str:
    pattern = re.compile(
        r"(?P<prefix>\b(?P<key>[A-Za-z_][A-Za-z0-9_-]*)\s*=\s*)"
        r"(?P<value>\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*'|[^,}\]\s]+)"
    )

    def replace(match: re.Match[str]) -> str:
        if is_sensitive_config_key(match.group("key")):
            return f'{match.group("prefix")}"{CONFIG_SECRET_VALUE}"'
        return match.group(0)

    return pattern.sub(replace, content)


def copy_config_templates(project_root: Path, output_dir: Path) -> None:
    templates = {
        project_root / "caifuclaw_business_app" / "config.template.toml": output_dir / "config_templates" / "caifuclaw_business_app.config.toml.example",
    }
    for source, destination in templates.items():
        if not source.is_file():
            raise FileNotFoundError(f"Config template not found: {source}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(sanitize_config_template(source.read_text(encoding="utf-8")), encoding="utf-8")


def write_readme(output_dir: Path) -> None:
    (output_dir / "README.md").write_text(
        "# CaifuClaw AI Test Database Fixture\n\n"
        "This fixture contains the current PostgreSQL schema plus a small, sanitized data set. "
        "It has no production credentials, tokens, buyer identities, addresses, request logs, audit logs, or raw API payloads.\n\n"
        "## Quick Install\n\n"
        "1. Copy `config_templates/caifuclaw_business_app.config.toml.example` to `caifuclaw_business_app/config.toml`.\n"
        "2. Set the PostgreSQL connection values in that file.\n"
        "3. From the repository root, run `.\\deploy\\database\\install_demo_database.cmd`.\n\n"
        "The installer creates the configured database, imports `postgres_schema.sql` and `postgres_seed.sql`, then verifies row counts. "
        "Use `-Replace` only when intentionally replacing an existing database.\n\n"
        "## Manual PostgreSQL Install\n\n"
        "1. Create a fresh database with `00_create_caifuclaw_ai_test.sql`.\n"
        "2. Import `postgres_schema.sql`.\n"
        "3. Import `postgres_seed.sql`.\n\n"
        "## Test Login\n\n"
        f"- Username: `{TEST_ADMIN_USERNAME}`\n"
        f"- Password: `{TEST_ADMIN_PASSWORD}`\n"
        "Copy the files in `config_templates/` for the new environment and replace all placeholder secrets, URLs, and database connection values. "
        "Keep platform accounts disabled until test credentials are configured.\n",
        encoding="utf-8",
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_manifest(output_dir: Path, postgres_counts: dict[str, int]) -> None:
    files = [path for path in sorted(output_dir.rglob("*")) if path.is_file() and path.name != "manifest.json"]
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "purpose": "sanitized test environment fixture",
        "test_login": {"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        "postgres_row_counts": postgres_counts,
        "files": [
            {"path": path.relative_to(output_dir).as_posix(), "size_bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in files
        ],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    args = parse_args()
    if args.orders_limit <= 0 or args.products_limit <= 0:
        raise RuntimeError("orders-limit and products-limit must be positive")
    project_root = args.project_root.resolve()
    output_dir = args.output_dir.expanduser().resolve()
    require_empty_output_dir(output_dir)

    business_config = load_toml(business_config_path(project_root))
    write_postgres_create_database(output_dir / "00_create_caifuclaw_ai_test.sql")
    write_postgres_schema(business_config, output_dir / "postgres_schema.sql", args.pg_dump)
    postgres_counts = write_postgres_seed(project_root, output_dir / "postgres_seed.sql", args.orders_limit, args.products_limit)

    copy_config_templates(project_root, output_dir)
    write_readme(output_dir)
    write_manifest(output_dir, postgres_counts)
    print(f"Wrote sanitized test fixture: {output_dir}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        print(f"Test fixture export failed: {exc}", file=sys.stderr)
        sys.exit(1)
