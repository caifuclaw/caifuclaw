# Company: 深圳智柠网络科技有限公司
# Author: mohsen liang

from __future__ import annotations

import os
import shutil
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from deploy.database.backup_all import (
    cleanup_old_snapshots,
    cleanup_stale_incomplete_snapshots,
    copy_directory,
    write_file_inventory,
)


class BackupAllTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.log_file = self.root / "backup.log"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @unittest.skipUnless(shutil.which("rsync"), "rsync is required")
    def test_rsync_snapshot_hard_links_unchanged_files(self) -> None:
        source = self.root / "source"
        source.mkdir()
        (source / "unchanged.txt").write_text("same", encoding="utf-8")
        changed_source = source / "changed.txt"
        changed_source.write_text("first", encoding="utf-8")

        first = self.root / "first"
        copy_directory(source, first, None, "rsync", self.log_file)
        original_stat = changed_source.stat()
        changed_source.write_text("other", encoding="utf-8")
        os.utime(changed_source, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

        second = self.root / "second"
        copy_directory(source, second, first, "rsync", self.log_file)

        self.assertEqual(os.stat(first / "unchanged.txt").st_ino, os.stat(second / "unchanged.txt").st_ino)
        self.assertNotEqual(os.stat(first / "changed.txt").st_ino, os.stat(second / "changed.txt").st_ino)
        self.assertEqual((second / "changed.txt").read_text(encoding="utf-8"), "other")

    def test_retention_only_removes_old_completed_snapshots(self) -> None:
        backup_dir = self.root / "backups"
        backup_dir.mkdir()
        old_snapshot = backup_dir / "caifuclaw_ai_20260701_010000"
        recent_snapshot = backup_dir / "caifuclaw_ai_20260725_010000"
        incomplete_snapshot = backup_dir / "caifuclaw_ai_20260601_010000"
        unrelated = backup_dir / "manual_files"
        for path in (old_snapshot, recent_snapshot, incomplete_snapshot, unrelated):
            path.mkdir()
        (old_snapshot / "COMPLETE").write_text("ok", encoding="ascii")
        (recent_snapshot / "COMPLETE").write_text("ok", encoding="ascii")

        cleanup_old_snapshots(
            backup_dir,
            14,
            self.log_file,
            current_time=datetime(2026, 7, 31, 12, 0, 0),
        )

        self.assertFalse(old_snapshot.exists())
        self.assertTrue(recent_snapshot.exists())
        self.assertTrue(incomplete_snapshot.exists())
        self.assertTrue(unrelated.exists())

    def test_stale_incomplete_snapshot_cleanup_is_strictly_scoped(self) -> None:
        backup_dir = self.root / "backups"
        backup_dir.mkdir()
        old_incomplete = backup_dir / ".caifuclaw_ai_20260701_010000.incomplete"
        recent_incomplete = backup_dir / ".caifuclaw_ai_20260731_010000.incomplete"
        unrelated = backup_dir / ".other.incomplete"
        for path in (old_incomplete, recent_incomplete, unrelated):
            path.mkdir()

        cleanup_stale_incomplete_snapshots(
            backup_dir,
            self.log_file,
            current_time=datetime(2026, 7, 31, 12, 0, 0),
        )

        self.assertFalse(old_incomplete.exists())
        self.assertTrue(recent_incomplete.exists())
        self.assertTrue(unrelated.exists())

    def test_inventory_hash_covers_inventory_file(self) -> None:
        snapshot = self.root / "snapshot"
        snapshot.mkdir()
        (snapshot / "example.txt").write_text("content", encoding="utf-8")

        inventory = write_file_inventory(snapshot)

        self.assertEqual(inventory["path"], "file_inventory.json")
        self.assertEqual(inventory["file_count"], 1)
        self.assertEqual(len(inventory["sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
