from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql
from sqlalchemy import MetaData, create_engine, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import URL
from sqlalchemy.schema import CreateTable
from sqlalchemy.sql.sqltypes import JSON, Integer, LargeBinary

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback if tomli is installed.
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_OUTPUT_DIR = Path("deploy/database/sql")


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8-sig"))


def config_value(config: dict[str, Any], section: str, key: str, default: Any = None) -> Any:
    current: Any = config
    for part in section.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    if not isinstance(current, dict):
        return default
    return current.get(key, default)


def require_config_value(config: dict[str, Any], section: str, key: str) -> Any:
    value = config_value(config, section, key)
    if value is None:
        raise RuntimeError(f"Missing config key: {section}.{key}")
    return value


def business_config_path(project_root: Path) -> Path:
    return project_root / "caifuclaw_business_app" / "config.toml"


def postgres_connect_kwargs(config: dict[str, Any], *, database: str | None = None) -> dict[str, Any]:
    return {
        "host": require_config_value(config, "postgres", "host"),
        "port": int(require_config_value(config, "postgres", "port")),
        "user": require_config_value(config, "postgres", "user"),
        "password": require_config_value(config, "postgres", "password"),
        "dbname": database or require_config_value(config, "databases", "sync"),
    }


def postgres_url(config: dict[str, Any]) -> URL:
    return URL.create(
        "postgresql+psycopg",
        username=require_config_value(config, "postgres", "user"),
        password=require_config_value(config, "postgres", "password"),
        host=require_config_value(config, "postgres", "host"),
        port=int(require_config_value(config, "postgres", "port")),
        database=require_config_value(config, "databases", "sync"),
    )


def quote_pg_identifier(conn: psycopg.Connection[Any], *parts: str) -> str:
    return sql.SQL(".").join(sql.Identifier(part) for part in parts).as_string(conn)


def json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def postgres_literal(
    conn: psycopg.Connection[Any],
    value: Any,
    column_type: Any,
) -> str:
    if value is None:
        return "NULL"

    if isinstance(column_type, (JSON, JSONB)):
        json_text = json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=json_default)
        cast = "::jsonb" if isinstance(column_type, JSONB) else "::json"
        return f"{sql.Literal(json_text).as_string(conn)}{cast}"

    if isinstance(column_type, LargeBinary):
        if isinstance(value, memoryview):
            value = value.tobytes()
        if isinstance(value, bytearray):
            value = bytes(value)
        if not isinstance(value, bytes):
            raise TypeError(f"Expected bytes for binary column, got {type(value).__name__}")
        return f"decode('{value.hex()}', 'hex')"

    return sql.Literal(value).as_string(conn)


def compile_ddl(item: Any) -> str:
    return str(item.compile(dialect=postgresql.dialect())).rstrip()


def fetch_postgres_extensions(conn: psycopg.Connection[Any]) -> list[str]:
    rows = conn.execute(
        """
        SELECT extname
        FROM pg_extension
        WHERE extname <> 'plpgsql'
        ORDER BY extname
        """
    ).fetchall()
    return [str(row[0]) for row in rows]


def fetch_postgres_index_definitions(conn: psycopg.Connection[Any]) -> list[tuple[str, str, str]]:
    rows = conn.execute(
        """
        SELECT
            table_class.relname AS table_name,
            index_class.relname AS index_name,
            pg_get_indexdef(index_class.oid) AS index_definition
        FROM pg_index index_info
        JOIN pg_class table_class ON table_class.oid = index_info.indrelid
        JOIN pg_namespace table_namespace ON table_namespace.oid = table_class.relnamespace
        JOIN pg_class index_class ON index_class.oid = index_info.indexrelid
        LEFT JOIN pg_constraint constraint_info ON constraint_info.conindid = index_class.oid
        WHERE table_namespace.nspname = 'public'
          AND table_class.relkind = 'r'
          AND constraint_info.oid IS NULL
        ORDER BY table_class.relname, index_class.relname
        """
    ).fetchall()
    return [(str(row[0]), str(row[1]), str(row[2])) for row in rows]


def export_postgres(project_root: Path, output_dir: Path) -> dict[str, Any]:
    config = load_toml(business_config_path(project_root))
    database_name = str(require_config_value(config, "databases", "sync"))
    output_path = output_dir / "caifuclaw_business_app.postgres.sql"
    create_database_path = output_dir / "00_create_postgres_database.sql"

    engine = create_engine(postgres_url(config), pool_pre_ping=True)
    metadata = MetaData()
    metadata.reflect(bind=engine, schema="public")

    row_counts: dict[str, int] = {}
    generated_at = datetime.now().astimezone().isoformat(timespec="seconds")

    with psycopg.connect(**postgres_connect_kwargs(config)) as raw_conn, engine.connect() as sa_conn:
        with create_database_path.open("w", encoding="utf-8", newline="\n") as file:
            db_name_sql = quote_pg_identifier(raw_conn, database_name)
            file.write("-- Generated by deploy/database/export_database.py\n")
            file.write(f"-- Generated at: {generated_at}\n")
            file.write("-- Run this against the PostgreSQL maintenance database if you need SQL-only database creation.\n")
            file.write("-- The Python upgrade program creates the database automatically.\n\n")
            file.write(f"CREATE DATABASE {db_name_sql} WITH ENCODING 'UTF8';\n")

        with output_path.open("w", encoding="utf-8", newline="\n") as file:
            file.write("-- Generated by deploy/database/export_database.py\n")
            file.write(f"-- Generated at: {generated_at}\n")
            file.write(f"-- Source database: {database_name}\n")
            file.write("-- Contains schema and data for caifuclaw_business_app.\n\n")
            file.write("SET client_encoding = 'UTF8';\n")
            file.write("SET standard_conforming_strings = on;\n")
            file.write("SET check_function_bodies = false;\n\n")

            extensions = fetch_postgres_extensions(raw_conn)
            if extensions:
                file.write("-- Extensions\n")
                for extension in extensions:
                    extension_name = quote_pg_identifier(raw_conn, extension)
                    file.write(f"CREATE EXTENSION IF NOT EXISTS {extension_name};\n")
                file.write("\n")

            for table in metadata.sorted_tables:
                file.write(f"-- Table: {table.name}\n")
                file.write(compile_ddl(CreateTable(table)))
                file.write(";\n\n")

            for table_name, index_name, index_definition in fetch_postgres_index_definitions(raw_conn):
                file.write(f"-- Index: {table_name}.{index_name}\n")
                file.write(index_definition.rstrip())
                file.write(";\n\n")

            file.write("-- Data\n")
            for table in metadata.sorted_tables:
                columns = list(table.columns)
                if not columns:
                    continue
                order_columns = list(table.primary_key.columns)
                stmt = select(*columns)
                if order_columns:
                    stmt = stmt.order_by(*order_columns)
                rows = sa_conn.execute(stmt).mappings().all()
                row_counts[table.name] = len(rows)
                if not rows:
                    continue

                table_name = quote_pg_identifier(raw_conn, "public", table.name)
                column_names = ", ".join(quote_pg_identifier(raw_conn, column.name) for column in columns)
                file.write(f"\n-- Data for table: {table.name} ({len(rows)} rows)\n")
                for row in rows:
                    values = [
                        postgres_literal(raw_conn, row[column.name], column.type)
                        for column in columns
                    ]
                    file.write(f"INSERT INTO {table_name} ({column_names}) VALUES ({', '.join(values)});\n")

            file.write("\n-- Reset PostgreSQL sequences after explicit id inserts.\n")
            for table in metadata.sorted_tables:
                for column in table.primary_key.columns:
                    if not isinstance(column.type, Integer):
                        continue
                    sequence_name = raw_conn.execute(
                        "SELECT pg_get_serial_sequence(%s, %s)",
                        (f"public.{table.name}", column.name),
                    ).fetchone()[0]
                    if not sequence_name:
                        continue
                    table_name = quote_pg_identifier(raw_conn, "public", table.name)
                    column_name = quote_pg_identifier(raw_conn, column.name)
                    sequence_literal = sql.Literal(sequence_name).as_string(raw_conn)
                    file.write(
                        "SELECT setval("
                        f"{sequence_literal}, "
                        f"COALESCE((SELECT MAX({column_name}) FROM {table_name}), 1), "
                        f"EXISTS (SELECT 1 FROM {table_name})"
                        ");\n"
                    )

    engine.dispose()
    return {
        "name": "caifuclaw_business_app",
        "database": database_name,
        "engine": "postgresql",
        "sql_file": str(output_path.relative_to(project_root)),
        "create_database_sql_file": str(create_database_path.relative_to(project_root)),
        "row_counts": row_counts,
    }


def write_manifest(project_root: Path, output_dir: Path, entries: list[dict[str, Any]]) -> None:
    manifest = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "entries": entries,
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Wrote {manifest_path.relative_to(project_root)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export CaifuClaw AI database schema and data as SQL.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Project root directory. Defaults to the repository root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for generated SQL files.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    output_dir = args.output_dir
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Exporting caifuclaw_business_app PostgreSQL database...")
    entry = export_postgres(project_root, output_dir)
    entries = [entry]
    print(f"Wrote {entry['sql_file']}")

    write_manifest(project_root, output_dir, entries)
    return 0


if __name__ == "__main__":
    sys.exit(main())
