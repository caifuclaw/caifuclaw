from __future__ import annotations

import argparse
from pathlib import Path

try:
    from .upgrade_database import (
        business_config_path,
        create_database,
        database_exists,
        database_has_user_tables,
        drop_database,
        load_manifest,
        load_toml,
        require_config_value,
        run_postgres_sql,
        verify_postgres_row_counts,
    )
except ImportError:
    from upgrade_database import (  # type: ignore[no-redef]
        business_config_path,
        create_database,
        database_exists,
        database_has_user_tables,
        drop_database,
        load_manifest,
        load_toml,
        require_config_value,
        run_postgres_sql,
        verify_postgres_row_counts,
    )


DEFAULT_FIXTURE_DIR = Path("deploy/database/demo_fixture")
REQUIRED_FIXTURE_FILES = ("postgres_schema.sql", "postgres_seed.sql", "manifest.json")


def fixture_row_counts(fixture_dir: Path) -> dict[str, int]:
    manifest = load_manifest(fixture_dir)
    return {
        str(table): int(count)
        for table, count in manifest.get("postgres_row_counts", {}).items()
    }


def validate_fixture(fixture_dir: Path) -> None:
    missing = [name for name in REQUIRED_FIXTURE_FILES if not (fixture_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"Demo fixture is incomplete: missing {', '.join(missing)} in {fixture_dir}")


def install_demo_database(
    project_root: Path,
    fixture_dir: Path,
    database_name: str | None,
    replace: bool,
    skip_existing: bool,
    verify: bool,
) -> None:
    validate_fixture(fixture_dir)
    config = load_toml(business_config_path(project_root))
    target_database = database_name or str(require_config_value(config, "databases", "sync"))

    if replace and database_exists(config, target_database):
        drop_database(config, target_database)

    create_database(config, target_database)
    if database_has_user_tables(config, target_database):
        if skip_existing:
            print(f"Skip demo install because database already has tables: {target_database}")
            return
        raise RuntimeError(
            f"Target PostgreSQL database already has tables: {target_database}. "
            "Use --replace to rebuild it, or --skip-existing to leave it unchanged."
        )

    print(f"Restoring demo schema into PostgreSQL database: {target_database}")
    run_postgres_sql(config, target_database, fixture_dir / "postgres_schema.sql")
    print(f"Restoring demo data into PostgreSQL database: {target_database}")
    run_postgres_sql(config, target_database, fixture_dir / "postgres_seed.sql")
    if verify:
        verify_postgres_row_counts(config, target_database, fixture_row_counts(fixture_dir))
    print(f"Demo database install complete: {target_database}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Install the bundled CaifuClaw AI demo PostgreSQL database.")
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Project root directory. Defaults to the repository root.",
    )
    parser.add_argument(
        "--fixture-dir",
        type=Path,
        default=DEFAULT_FIXTURE_DIR,
        help="Directory containing the bundled demo SQL files.",
    )
    parser.add_argument(
        "--database",
        help="Optional PostgreSQL database name override for this install.",
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="Drop and recreate the target PostgreSQL database before installing the demo.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Leave a populated target database unchanged.",
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip row count verification after import.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.replace and args.skip_existing:
        raise RuntimeError("Use either --replace or --skip-existing, not both.")

    project_root = args.project_root.resolve()
    fixture_dir = args.fixture_dir
    if not fixture_dir.is_absolute():
        fixture_dir = project_root / fixture_dir
    install_demo_database(
        project_root,
        fixture_dir,
        args.database,
        args.replace,
        args.skip_existing,
        not args.no_verify,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
