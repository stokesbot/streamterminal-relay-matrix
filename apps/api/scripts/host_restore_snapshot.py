"""Restore a host snapshot captured by an earlier apply.

Usage:

    uv run python scripts/host_restore_snapshot.py list
    uv run python scripts/host_restore_snapshot.py show <snapshot_id>
    uv run python scripts/host_restore_snapshot.py restore <snapshot_id> [--dry-run]

This script is meant for off-band recovery (e.g. when the API itself
is unhealthy but the operator has shell access). It talks directly to
the runtime data directory and never opens a network connection.

Reads `RUNTIME_DIR` from the environment to find the on-disk
snapshots. Defaults to `apps/api/data/runtime`.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _resolve_runtime_dir() -> Path:
    return Path(os.environ.get("RUNTIME_DIR", "apps/api/data/runtime"))


def _list(runtime_dir: Path) -> int:
    snapshot_root = runtime_dir / "host-snapshots"
    if not snapshot_root.exists():
        print("(no snapshots found)", file=sys.stderr)
        return 0
    found = 0
    for manifest_path in sorted(snapshot_root.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text())
        files = manifest.get("files", [])
        total_bytes = sum(int(f.get("size", 0)) for f in files)
        print(
            f"{manifest.get('id')}  trigger={manifest.get('trigger')}  "
            f"created_at={manifest.get('created_at')}  "
            f"files={len(files)}  total_bytes={total_bytes}  "
            f"host_root={manifest.get('host_root')}"
        )
        found += 1
    if found == 0:
        print("(no snapshots found)", file=sys.stderr)
    return 0


def _show(runtime_dir: Path, snapshot_id: str) -> int:
    manifest_path = runtime_dir / "host-snapshots" / snapshot_id / "manifest.json"
    if not manifest_path.exists():
        print(f"snapshot not found: {snapshot_id}", file=sys.stderr)
        return 1
    print(json.dumps(json.loads(manifest_path.read_text()), indent=2))
    return 0


def _restore(runtime_dir: Path, snapshot_id: str, dry_run: bool) -> int:
    manifest_path = runtime_dir / "host-snapshots" / snapshot_id / "manifest.json"
    if not manifest_path.exists():
        print(f"snapshot not found: {snapshot_id}", file=sys.stderr)
        return 1
    manifest = json.loads(manifest_path.read_text())
    files = manifest.get("files", [])
    host_root = manifest.get("host_root")
    if not host_root:
        print(f"snapshot {snapshot_id} is missing host_root", file=sys.stderr)
        return 1
    snapshot_files_dir = runtime_dir / "host-snapshots" / snapshot_id / "files"
    print(f"Restoring {len(files)} files from snapshot {snapshot_id} onto {host_root} ...")
    for entry in files:
        rel = entry["path"]
        source = snapshot_files_dir / rel
        target = Path(host_root) / rel
        mode = "0755" if rel.endswith(".sh") else "0644"
        if not source.exists():
            print(f"  SKIP {rel}: snapshot file is missing")
            continue
        if dry_run:
            print(f"  DRY-RUN {rel}  src={source}  dst={target}  mode={mode}")
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source.read_bytes())
        target.chmod(int(mode, 8))
        print(f"  WROTE {rel}  size={entry.get('size')}  sha256={entry.get('sha256')[:12]}...")
    print("done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="List, show, or restore a StreamTerminal relay host snapshot."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="list all known host snapshots")
    show_p = sub.add_parser("show", help="print the manifest of a snapshot")
    show_p.add_argument("snapshot_id")
    restore_p = sub.add_parser("restore", help="restore a snapshot onto the host")
    restore_p.add_argument("snapshot_id")
    restore_p.add_argument(
        "--dry-run",
        action="store_true",
        help="print the planned restores without writing anything",
    )
    args = parser.parse_args(argv)

    runtime_dir = _resolve_runtime_dir()
    if not runtime_dir.exists():
        print(f"runtime dir does not exist: {runtime_dir}", file=sys.stderr)
        return 1

    if args.command == "list":
        return _list(runtime_dir)
    if args.command == "show":
        return _show(runtime_dir, args.snapshot_id)
    if args.command == "restore":
        return _restore(runtime_dir, args.snapshot_id, args.dry_run)
    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
