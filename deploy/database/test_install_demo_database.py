# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from deploy.database.install_demo_database import fixture_row_counts, validate_fixture


class InstallDemoDatabaseTests(unittest.TestCase):
    def test_fixture_row_counts_reads_demo_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            (fixture_dir / "manifest.json").write_text(
                json.dumps({"postgres_row_counts": {"orders": 20, "products": 100}}),
                encoding="utf-8",
            )

            self.assertEqual(fixture_row_counts(fixture_dir), {"orders": 20, "products": 100})

    def test_validate_fixture_reports_missing_required_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            with self.assertRaisesRegex(RuntimeError, "postgres_schema.sql"):
                validate_fixture(fixture_dir)

    def test_validate_fixture_accepts_complete_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture_dir = Path(directory)
            for name in ("postgres_schema.sql", "postgres_seed.sql", "manifest.json"):
                (fixture_dir / name).write_text("", encoding="utf-8")

            validate_fixture(fixture_dir)


if __name__ == "__main__":
    unittest.main()
