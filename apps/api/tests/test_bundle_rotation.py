"""Tests for bundle rotation and inventory.

Rotation prunes the oldest deploy bundles and staging directories once
the per-bucket retention threshold is exceeded. The tests in this file
exercise the prune logic with a hand-rolled directory tree so they
don't depend on a full apply cycle.
"""

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from app.runtime import RuntimeAdapter


def _write_bundle(bundle_dir: Path, *, profile_id: str = "local-system", mtime: float) -> None:
    bundle_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "deploy-manifest.json").write_text(
        json.dumps(
            {
                "profile_id": profile_id,
                "generated_at": "2026-01-01T00:00:00+00:00",
                "mode": "apply",
                "host_touched": True,
                "success": True,
                "config": {},
                "files": [],
            }
        )
    )
    # Force a deterministic mtime so the test is not at the mercy of fs mtime granularity.
    os.utime(bundle_dir, (mtime, mtime))


def _write_staging_dir(staging_dir: Path, mtime: float) -> None:
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "payload.txt").write_text("x" * 1024)
    os.utime(staging_dir, (mtime, mtime))


def _bundle_ts(index: int) -> str:
    """Return a sortable, second-precise timestamp for the test bundle name.

    The runtime uses `%Y%m%dT%H%M%S%fZ` (microsecond precision, 6 digits).
    """
    return f"20260601T120{index:02d}000000Z"


class BundleRotationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(tempfile.mkdtemp(prefix="stm-rotation-"))
        self.runtime_dir = self.workdir / "runtime"
        self.runtime_dir.mkdir()
        self.adapter = RuntimeAdapter(self.runtime_dir)

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.workdir, ignore_errors=True)

    def test_prune_keeps_only_recent_apply_bundles(self) -> None:
        now = time.time()
        # 12 bundles, mtimes spaced 60s apart, oldest first.
        for i in range(12):
            bundle = self.adapter.bundle_root / f"{_bundle_ts(i)}-local-system"
            _write_bundle(bundle, mtime=now - (12 - i) * 60)

        result = self.adapter.prune_bundles(keep_apply=5, keep_stage=0)
        removed = [Path(item["path"]).name for item in result["removed_bundles"]]
        self.assertEqual(len(removed), 7, removed)

        remaining = sorted(p.name for p in self.adapter.bundle_root.iterdir())
        self.assertEqual(len(remaining), 5, remaining)

    def test_prune_always_keeps_at_least_one_bundle(self) -> None:
        now = time.time()
        for i in range(3):
            _write_bundle(self.adapter.bundle_root / f"{_bundle_ts(i)}-local-system", mtime=now + i)

        # keep_apply=0 still keeps the most recent bundle; older ones are removed.
        result = self.adapter.prune_bundles(keep_apply=0, keep_stage=0)
        remaining = list(self.adapter.bundle_root.iterdir())
        self.assertEqual(len(remaining), 1, [p.name for p in remaining])
        self.assertEqual(len(result["removed_bundles"]), 2)

    def test_single_bundle_survives_zero_keep(self) -> None:
        now = time.time()
        _write_bundle(self.adapter.bundle_root / f"{_bundle_ts(0)}-local-system", mtime=now)

        result = self.adapter.prune_bundles(keep_apply=0, keep_stage=0)
        self.assertEqual(len(result["removed_bundles"]), 0)
        self.assertEqual(len(list(self.adapter.bundle_root.iterdir())), 1)

    def test_prune_keeps_recent_staging_directories(self) -> None:
        now = time.time()
        # 8 staging directories, oldest first.
        for i in range(8):
            _write_staging_dir(self.adapter.install_root / f"staging-{i}", mtime=now - (8 - i) * 60)

        result = self.adapter.prune_bundles(keep_apply=0, keep_stage=3)
        removed = [Path(item["path"]).name for item in result["removed_staging"]]
        self.assertEqual(len(removed), 5, removed)

        remaining = sorted(p.name for p in self.adapter.install_root.iterdir())
        self.assertEqual(len(remaining), 3, remaining)

    def test_prune_dry_run_does_not_delete(self) -> None:
        now = time.time()
        for i in range(6):
            _write_bundle(self.adapter.bundle_root / f"{_bundle_ts(i)}-local-system", mtime=now + i)

        result = self.adapter.prune_bundles(keep_apply=2, keep_stage=0, dry_run=True)
        # We *should* report what would be removed, but the dirs still exist.
        self.assertEqual(len(result["removed_bundles"]), 4)
        remaining = list(self.adapter.bundle_root.iterdir())
        self.assertEqual(len(remaining), 6)

    def test_list_bundles_returns_sorted_inventory(self) -> None:
        now = time.time()
        for i in range(3):
            bundle = self.adapter.bundle_root / f"{_bundle_ts(i)}-local-system"
            _write_bundle(bundle, mtime=now + i)

        inventory = self.adapter.list_bundles()
        # Newest first (sorted by mtime descending).
        names = [item["name"] for item in inventory]
        self.assertEqual(len(names), 3)
        self.assertEqual(names[0], f"{_bundle_ts(2)}-local-system")
        # Each entry has the fields the deploy page needs.
        first = inventory[0]
        for key in ("name", "path", "size_bytes", "file_count", "modified_at", "mtime"):
            self.assertIn(key, first, first)

    def test_default_keep_counts_come_from_env(self) -> None:
        os.environ["STM_BUNDLE_KEEP_APPLY"] = "7"
        os.environ["STM_BUNDLE_KEEP_STAGE"] = "2"
        try:
            self.assertEqual(self.adapter._default_keep_apply(), 7)
            self.assertEqual(self.adapter._default_keep_stage(), 2)
        finally:
            os.environ.pop("STM_BUNDLE_KEEP_APPLY", None)
            os.environ.pop("STM_BUNDLE_KEEP_STAGE", None)


if __name__ == "__main__":
    unittest.main()
