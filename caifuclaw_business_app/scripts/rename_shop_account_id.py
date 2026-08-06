from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.sql.sqltypes import String, Text

APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))

from app.database import engine  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Rename a shop account ID and all textual database references in one transaction."
    )
    parser.add_argument("platform", help="Canonical platform code, for example allegro.")
    parser.add_argument("old_account_id", help="Current shop account ID.")
    parser.add_argument("new_account_id", help="Replacement shop account ID.")
    parser.add_argument("--apply", action="store_true", help="Write changes. Defaults to a dry run.")
    return parser.parse_args()


def _reference_columns() -> list[tuple[str, str]]:
    database = inspect(engine)
    references: list[tuple[str, str]] = []
    for table_name in database.get_table_names():
        columns = {column["name"]: column["type"] for column in database.get_columns(table_name)}
        if "platform" not in columns:
            continue
        if isinstance(columns.get("account_id"), (String, Text)):
            references.append((table_name, "account_id"))
        if isinstance(columns.get("shop_id"), (String, Text)):
            references.append((table_name, "shop_id"))
    return references


def main() -> int:
    args = parse_args()
    platform = args.platform.strip().lower()
    old_account_id = args.old_account_id.strip()
    new_account_id = args.new_account_id.strip()
    if not platform or not old_account_id or not new_account_id:
        raise SystemExit("platform and account IDs must not be empty")
    if old_account_id == new_account_id:
        raise SystemExit("old and new account IDs must differ")

    references = _reference_columns()
    counts: list[tuple[str, str, int]] = []
    with engine.connect() as conn:
        old_shop_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM platform_accounts "
                "WHERE platform = :platform AND account_id = :account_id"
            ),
            {"platform": platform, "account_id": old_account_id},
        ).scalar_one()
        new_shop_count = conn.execute(
            text(
                "SELECT COUNT(*) FROM platform_accounts "
                "WHERE platform = :platform AND account_id = :account_id"
            ),
            {"platform": platform, "account_id": new_account_id},
        ).scalar_one()
        first_run = old_shop_count == 1 and new_shop_count == 0
        continuation = old_shop_count == 0 and new_shop_count == 1
        if not first_run and not continuation:
            raise SystemExit(
                "expected exactly one source or replacement shop, "
                f"found source={old_shop_count} replacement={new_shop_count}"
            )

        for table_name, column_name in references:
            count = conn.execute(
                text(
                    f'SELECT COUNT(*) FROM "{table_name}" '
                    f'WHERE platform = :platform AND "{column_name}" = :old_account_id'
                ),
                {"platform": platform, "old_account_id": old_account_id},
            ).scalar_one()
            if count:
                counts.append((table_name, column_name, int(count)))

    mode = "apply" if args.apply else "dry-run"
    print(
        f"mode={mode} platform={platform} old={old_account_id} new={new_account_id} "
        f"references={sum(count for _, _, count in counts)}"
    )
    for table_name, column_name, count in counts:
        print(f"{table_name}.{column_name}: {count}")
    if not args.apply:
        return 0

    with engine.begin() as conn:
        for table_name, column_name, _ in counts:
            conn.execute(
                text(
                    f'UPDATE "{table_name}" SET "{column_name}" = :new_account_id '
                    f'WHERE platform = :platform AND "{column_name}" = :old_account_id'
                ),
                {
                    "platform": platform,
                    "old_account_id": old_account_id,
                    "new_account_id": new_account_id,
                },
            )
    print("rename completed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
