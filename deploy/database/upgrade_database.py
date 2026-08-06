from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import psycopg
from psycopg import sql

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 fallback if tomli is installed.
    import tomli as tomllib  # type: ignore[no-redef]


DEFAULT_SQL_DIR = Path("deploy/database/sql")
POSTGRES_SQL_FILE = "caifuclaw_business_app.postgres.sql"
MANIFEST_FILE = "manifest.json"


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text(encoding="utf-8-sig"))


def load_manifest(sql_dir: Path) -> dict[str, Any]:
    manifest_path = sql_dir / MANIFEST_FILE
    if not manifest_path.exists():
        return {"entries": []}
    return json.loads(manifest_path.read_text(encoding="utf-8-sig"))


def manifest_row_counts(sql_dir: Path, entry_name: str) -> dict[str, int]:
    manifest = load_manifest(sql_dir)
    for entry in manifest.get("entries", []):
        if entry.get("name") == entry_name:
            return {str(table): int(count) for table, count in entry.get("row_counts", {}).items()}
    return {}


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


def postgres_connect_kwargs(
    config: dict[str, Any],
    *,
    database: str | None = None,
    autocommit: bool = False,
) -> dict[str, Any]:
    return {
        "host": require_config_value(config, "postgres", "host"),
        "port": int(require_config_value(config, "postgres", "port")),
        "user": require_config_value(config, "postgres", "user"),
        "password": require_config_value(config, "postgres", "password"),
        "dbname": database or require_config_value(config, "databases", "sync"),
        "autocommit": autocommit,
    }


def quote_identifier(name: str) -> sql.Identifier:
    return sql.Identifier(name)


def database_exists(config: dict[str, Any], database_name: str) -> bool:
    maintenance_db = str(require_config_value(config, "postgres", "maintenance_database"))
    with psycopg.connect(**postgres_connect_kwargs(config, database=maintenance_db, autocommit=True)) as conn:
        return conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)).fetchone() is not None


def create_database(config: dict[str, Any], database_name: str) -> None:
    maintenance_db = str(require_config_value(config, "postgres", "maintenance_database"))
    with psycopg.connect(**postgres_connect_kwargs(config, database=maintenance_db, autocommit=True)) as conn:
        exists = conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (database_name,)).fetchone()
        if exists:
            print(f"PostgreSQL database exists: {database_name}")
            return
        conn.execute(sql.SQL("CREATE DATABASE {} WITH ENCODING 'UTF8'").format(quote_identifier(database_name)))
        print(f"Created PostgreSQL database: {database_name}")


def drop_database(config: dict[str, Any], database_name: str) -> None:
    maintenance_db = str(require_config_value(config, "postgres", "maintenance_database"))
    with psycopg.connect(**postgres_connect_kwargs(config, database=maintenance_db, autocommit=True)) as conn:
        conn.execute(
            """
            SELECT pg_terminate_backend(pid)
            FROM pg_stat_activity
            WHERE datname = %s AND pid <> pg_backend_pid()
            """,
            (database_name,),
        )
        conn.execute(sql.SQL("DROP DATABASE IF EXISTS {}").format(quote_identifier(database_name)))
        print(f"Dropped PostgreSQL database: {database_name}")


def database_has_user_tables(config: dict[str, Any], database_name: str) -> bool:
    with psycopg.connect(**postgres_connect_kwargs(config, database=database_name)) as conn:
        count = conn.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'public'
              AND table_type = 'BASE TABLE'
            """
        ).fetchone()[0]
        return int(count) > 0


def run_postgres_sql(config: dict[str, Any], database_name: str, sql_path: Path) -> None:
    sql_text = sql_path.read_text(encoding="utf-8")
    with psycopg.connect(**postgres_connect_kwargs(config, database=database_name, autocommit=True)) as conn:
        statements = split_postgres_sql(sql_text)
        total = len(statements)
        for index, statement in enumerate(statements, 1):
            conn.execute(statement)
            if index % 100 == 0 or index == total:
                print(f"  PostgreSQL statements: {index}/{total}")


def verify_postgres_row_counts(config: dict[str, Any], database_name: str, expected_counts: dict[str, int]) -> None:
    if not expected_counts:
        print("PostgreSQL row count verification skipped: manifest has no counts.")
        return
    mismatches: list[tuple[str, int, int]] = []
    with psycopg.connect(**postgres_connect_kwargs(config, database=database_name)) as conn:
        for table_name, expected_count in sorted(expected_counts.items()):
            actual_count = conn.execute(
                sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(table_name))
            ).fetchone()[0]
            if int(actual_count) != expected_count:
                mismatches.append((table_name, expected_count, int(actual_count)))
    if mismatches:
        formatted = ", ".join(
            f"{table}: expected {expected}, got {actual}"
            for table, expected, actual in mismatches[:10]
        )
        raise RuntimeError(f"PostgreSQL row count verification failed: {formatted}")
    print(f"PostgreSQL row count verification passed: {len(expected_counts)} tables")


def split_postgres_sql(sql_text: str) -> list[str]:
    statements: list[str] = []
    current: list[str] = []
    in_single_quote = False
    in_double_quote = False
    in_line_comment = False
    in_block_comment = False
    dollar_quote_tag: str | None = None
    index = 0

    while index < len(sql_text):
        char = sql_text[index]
        next_char = sql_text[index + 1] if index + 1 < len(sql_text) else ""

        if in_line_comment:
            current.append(char)
            if char == "\n":
                in_line_comment = False
            index += 1
            continue

        if in_block_comment:
            current.append(char)
            if char == "*" and next_char == "/":
                current.append(next_char)
                in_block_comment = False
                index += 2
            else:
                index += 1
            continue

        if dollar_quote_tag is not None:
            if sql_text.startswith(dollar_quote_tag, index):
                current.append(dollar_quote_tag)
                index += len(dollar_quote_tag)
                dollar_quote_tag = None
            else:
                current.append(char)
                index += 1
            continue

        if in_single_quote:
            current.append(char)
            if char == "'":
                if next_char == "'":
                    current.append(next_char)
                    index += 2
                    continue
                in_single_quote = False
            index += 1
            continue

        if in_double_quote:
            current.append(char)
            if char == '"':
                if next_char == '"':
                    current.append(next_char)
                    index += 2
                    continue
                in_double_quote = False
            index += 1
            continue

        if char == "-" and next_char == "-":
            current.append(char)
            current.append(next_char)
            in_line_comment = True
            index += 2
            continue

        if char == "/" and next_char == "*":
            current.append(char)
            current.append(next_char)
            in_block_comment = True
            index += 2
            continue

        if char == "'":
            current.append(char)
            in_single_quote = True
            index += 1
            continue

        if char == '"':
            current.append(char)
            in_double_quote = True
            index += 1
            continue

        if char == "$":
            match = re.match(r"\$[A-Za-z_][A-Za-z0-9_]*\$|\$\$", sql_text[index:])
            if match:
                dollar_quote_tag = match.group(0)
                current.append(dollar_quote_tag)
                index += len(dollar_quote_tag)
                continue

        if char == ";":
            statement = "".join(current).strip()
            if statement:
                statements.append(statement)
            current = []
            index += 1
            continue

        current.append(char)
        index += 1

    tail = "".join(current).strip()
    if tail:
        statements.append(tail)
    return statements


def upgrade_postgres(project_root: Path, sql_dir: Path, replace: bool, skip_existing: bool, verify: bool) -> None:
    config = load_toml(business_config_path(project_root))
    database_name = str(require_config_value(config, "databases", "sync"))
    sql_path = sql_dir / POSTGRES_SQL_FILE
    if not sql_path.exists():
        raise RuntimeError(f"Missing SQL file: {sql_path}")

    if replace and database_exists(config, database_name):
        drop_database(config, database_name)

    create_database(config, database_name)
    if database_has_user_tables(config, database_name):
        if skip_existing:
            print(f"Skip PostgreSQL restore because database already has tables: {database_name}")
            return
        raise RuntimeError(
            f"Target PostgreSQL database already has tables: {database_name}. "
            "Use --replace to rebuild it, or --skip-existing to leave it unchanged."
        )

    print(f"Restoring PostgreSQL database from {sql_path}")
    run_postgres_sql(config, database_name, sql_path)
    if verify:
        verify_postgres_row_counts(config, database_name, manifest_row_counts(sql_dir, "caifuclaw_business_app"))
    print(f"PostgreSQL restore complete: {database_name}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create or rebuild CaifuClaw AI databases from exported SQL.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Project root directory. Defaults to the repository root.",
    )
    parser.add_argument(
        "--sql-dir",
        type=Path,
        default=DEFAULT_SQL_DIR,
        help="Directory containing exported SQL files.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and recreate the PostgreSQL database before restore.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip a target database when it already contains user tables.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip row count verification after restore.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    sql_dir = args.sql_dir
    if not sql_dir.is_absolute():
        sql_dir = project_root / sql_dir

    if args.replace and args.skip_existing:
        raise RuntimeError("Use either --replace or --skip-existing, not both.")

    upgrade_postgres(project_root, sql_dir, args.replace, args.skip_existing, not args.no_verify)

    print("Database upgrade finished.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
