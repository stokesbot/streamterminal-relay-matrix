"""Smoke tests for the `host_restore_snapshot.py` CLI.

These tests run the script as a subprocess against a temp data dir so
they never touch the real runtime, /etc, or the user's environment.
"""

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "apps" / "api" / "scripts" / "host_restore_snapshot.py"


def _write_runtime_with_snapshot(workdir: Path) -> tuple[Path, str]:
    runtime_dir = workdir / "runtime"
    snapshot_id = "20260603T120000000000Z"
    snapshot_dir = runtime_dir / "host-snapshots" / snapshot_id
    files_dir = snapshot_dir / "files"
    files_dir.mkdir(parents=True)

    host_root = workdir / "host"
    config_dir = host_root / "etc" / "streamterminal-relay-matrix"
    config_dir.mkdir(parents=True)
    (config_dir / "mediamtx.yml").write_text("logLevel: warn\napi: no\n")

    snapshot_config = files_dir / "etc" / "streamterminal-relay-matrix" / "mediamtx.yml"
    snapshot_config.parent.mkdir(parents=True)
    snapshot_config.write_text("logLevel: info\napi: yes\n")

    manifest = {
        "id": snapshot_id,
        "created_at": "2026-06-03T12:00:00+00:00",
        "trigger": "apply",
        "host_root": str(host_root),
        "source_bundle": None,
        "note": None,
        "files": [
            {
                "path": "etc/streamterminal-relay-matrix/mediamtx.yml",
                "size": snapshot_config.stat().st_size,
                "sha256": "deadbeef" * 8,
            }
        ],
    }
    (snapshot_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    return runtime_dir, snapshot_id


def _run_script(runtime_dir: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "RUNTIME_DIR": str(runtime_dir), "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        check=False,
        capture_output=True,
        text=True,
        env=env,
    )


class HostRestoreSnapshotCliTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workdir = Path(tempfile.mkdtemp(prefix="stm-restore-cli-"))

    def tearDown(self) -> None:
        import shutil
        shutil.rmtree(self.workdir, ignore_errors=True)

    def test_list_command_prints_snapshot_id(self) -> None:
        runtime_dir, snapshot_id = _write_runtime_with_snapshot(self.workdir)
        result = _run_script(runtime_dir, "list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(snapshot_id, result.stdout)
        self.assertIn("trigger=apply", result.stdout)

    def test_show_command_prints_manifest(self) -> None:
        runtime_dir, snapshot_id = _write_runtime_with_snapshot(self.workdir)
        result = _run_script(runtime_dir, "show", snapshot_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["id"], snapshot_id)
        self.assertEqual(payload["files"][0]["path"], "etc/streamterminal-relay-matrix/mediamtx.yml")

    def test_restore_command_writes_files(self) -> None:
        runtime_dir, snapshot_id = _write_runtime_with_snapshot(self.workdir)
        result = _run_script(runtime_dir, "restore", snapshot_id)
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.workdir / "host" / "etc" / "streamterminal-relay-matrix" / "mediamtx.yml"
        self.assertTrue(target.exists(), result.stdout)
        self.assertEqual(target.read_text(), "logLevel: info\napi: yes\n")

    def test_restore_dry_run_does_not_write(self) -> None:
        runtime_dir, snapshot_id = _write_runtime_with_snapshot(self.workdir)
        target = self.workdir / "host" / "etc" / "streamterminal-relay-matrix" / "mediamtx.yml"
        before = target.read_text()
        result = _run_script(runtime_dir, "restore", snapshot_id, "--dry-run")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("DRY-RUN", result.stdout)
        self.assertEqual(target.read_text(), before)

    def test_missing_snapshot_returns_nonzero(self) -> None:
        runtime_dir, _ = _write_runtime_with_snapshot(self.workdir)
        result = _run_script(runtime_dir, "show", "no-such-snapshot")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("snapshot not found", result.stderr)


if __name__ == "__main__":
    unittest.main()
