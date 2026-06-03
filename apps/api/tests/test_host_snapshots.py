"""Tests for pre-apply host snapshots.

The "snapshot" subsystem captures the on-host relay files BEFORE an apply
or rollback overwrites them, so operators can restore by hand or via
`POST /api/deploy/restore-snapshot` if a future change breaks the stack.

Tests run in a fully sandboxed environment: a fake `sudo`/`systemctl` PATH,
a temp host root, and a fake `ss` for the listener probe.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from app.main import app, store as original_store, runtime as original_runtime
from app import main as main_module
from app.schemas import DeploymentProfile, RelayConfig
from app.storage import ConfigStore, DEFAULT_CONFIG
from app.runtime import RuntimeAdapter


FAKE_SUDO = """#!/usr/bin/env python3
import os
import subprocess
import sys

args = sys.argv[1:]
if args[:1] == ['-n']:
    args = args[1:]
if not args:
    sys.exit(0)
raise SystemExit(subprocess.run(args, env=os.environ.copy()).returncode)
"""

FAKE_SYSTEMCTL = """#!/usr/bin/env python3
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ['FAKE_SYSTEMCTL_STATE'])
state_path.parent.mkdir(parents=True, exist_ok=True)
state = json.loads(state_path.read_text()) if state_path.exists() else {}
args = sys.argv[1:]


def save():
    state_path.write_text(json.dumps(state))


def ensure(unit):
    state.setdefault(unit, {'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'disabled', 'ExecMainStatus': '0', 'NRestarts': '0'})


def relay_env_ready():
    env_path = Path(os.environ['FAKE_RELAY_ENV'])
    if not env_path.exists():
        return False
    payload = env_path.read_text()
    required = ['STM_PRIMARY_INPUT_URL=', 'STM_BACKUP_INPUT_URL=', 'STM_OUTPUT_URL=']
    if not all(item in payload for item in required):
        return False
    return 'REPLACE_WITH_' not in payload and 'example.invalid' not in payload and 'placeholder' not in payload.lower()


if not args:
    raise SystemExit(1)

if args[0] == '--version':
    print('systemd 999 (fake)')
    raise SystemExit(0)

if args[0] == 'is-system-running':
    print('running')
    raise SystemExit(0)

if args[0] == 'daemon-reload':
    print('reloaded')
    raise SystemExit(0)

if args[0] in {'enable', 'disable', 'start', 'stop', 'restart'}:
    action = args[0]
    units = [arg for arg in args[1:] if not arg.startswith('-')]
    for unit in units:
        ensure(unit)
        if action == 'enable':
            if unit == 'stream-failover-relay.service' and not relay_env_ready():
                state[unit].update({'ActiveState': 'activating', 'SubState': 'auto-restart', 'UnitFileState': 'enabled', 'ExecMainStatus': '1', 'NRestarts': '2'})
            else:
                state[unit].update({'ActiveState': 'active', 'SubState': 'running', 'UnitFileState': 'enabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
        elif action in {'start', 'restart'}:
            state[unit].update({'ActiveState': 'active', 'SubState': 'running', 'UnitFileState': 'enabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
        elif action == 'stop':
            state[unit].update({'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'disabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
        else:
            state[unit].update({'ActiveState': 'inactive', 'SubState': 'dead', 'UnitFileState': 'disabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
    save()
    print(action)
    raise SystemExit(0)

if args[0] == 'show':
    units = []
    for arg in args[1:]:
        if arg.startswith('--'):
            continue
        units.append(arg)
    lines = []
    for unit in units:
        ensure(unit)
        for key in ['ActiveState', 'UnitFileState', 'SubState', 'ExecMainStatus', 'NRestarts']:
            lines.append(f'{key}={state[unit][key]}')
    print('\\n'.join(lines))
    raise SystemExit(0)

if args[0] == 'status':
    units = [arg for arg in args[1:] if not arg.startswith('-')]
    for unit in units:
        ensure(unit)
        print(f"{unit} {state[unit]['ActiveState']}")
    raise SystemExit(0)

raise SystemExit(0)
"""

FAKE_SS_LINES = [
    "State      Recv-Q Send-Q    Local Address:Port    Peer Address:Port",
    "LISTEN     0      4096          0.0.0.0:1935         0.0.0.0:*",
    "LISTEN     0      4096                *:1935                *:*",
    "LISTEN     0      4096             [::]:1935              [::]:*",
]

FAKE_SS = (
    "#!/usr/bin/env python3\n"
    "import os\n"
    "import sys\n"
    "\n"
    "lines_path = os.environ.get('FAKE_SS_LINES', '')\n"
    "if not lines_path or not os.path.exists(lines_path):\n"
    "    sys.exit(0)\n"
    "with open(lines_path) as handle:\n"
    "    sys.stdout.write(handle.read())\n"
)

FAKE_NETSTAT = (
    "#!/usr/bin/env python3\n"
    "import os\n"
    "import sys\n"
    "\n"
    "lines_path = os.environ.get('FAKE_SS_LINES', '')\n"
    "if not lines_path or not os.path.exists(lines_path):\n"
    "    sys.exit(0)\n"
    "with open(lines_path) as handle:\n"
    "    sys.stdout.write(handle.read())\n"
)


class TestRuntimeAdapter(RuntimeAdapter):
    def __init__(self, runtime_dir: Path, host_root: Path) -> None:
        super().__init__(runtime_dir)
        self.host_root = host_root

    def local_profile(self) -> DeploymentProfile:
        return DeploymentProfile(
            id="local-system",
            label="Local Linux host",
            description="Install and operate the relay stack on the same machine where the control plane runs.",
            run_on="local",
            target_host="localhost",
            target_user="current-user",
            path_roots={
                "config_dir": str(self.host_root / "etc/streamterminal-relay-matrix"),
                "bin_dir": str(self.host_root / "usr/local/bin"),
                "systemd_dir": str(self.host_root / "etc/systemd/system"),
            },
            notes=["Local-only test profile"],
            secret_placeholders=["Local-only test placeholder"],
            source="builtin",
            editable=False,
        )


def _write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(0o755)


def _seed_relay_env(host_root: Path) -> Path:
    env_path = host_root / "etc/streamterminal-relay-matrix/streamterminal-relay.env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        "\n".join(
            [
                "STM_PRIMARY_INPUT_URL=rtmp://localhost:1935/live/main",
                "STM_BACKUP_INPUT_URL=rtmp://localhost:1935/live/backup",
                "STM_OUTPUT_URL=rtmp://localhost:1935/live/output",
                "",
            ]
        )
    )
    return env_path


class HostSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.fakebin = self.base / "fakebin"
        self.fakebin.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base / "systemctl-state.json"
        self.ss_lines_path = self.base / "ss-lines.txt"
        self.ss_lines_path.write_text("\n".join(FAKE_SS_LINES) + "\n")
        _write_executable(self.fakebin / "sudo", FAKE_SUDO)
        _write_executable(self.fakebin / "systemctl", FAKE_SYSTEMCTL)
        _write_executable(self.fakebin / "ss", FAKE_SS)
        _write_executable(self.fakebin / "netstat", FAKE_NETSTAT)

        self.original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.fakebin}:{self.original_path}"
        os.environ["FAKE_SYSTEMCTL_STATE"] = str(self.state_path)
        os.environ["FAKE_SS_LINES"] = str(self.ss_lines_path)
        os.environ["STM_SMOKE_PROBE_OVERRIDE"] = json.dumps(
            {
                "primary": {"ok": True, "detail": "tcp://localhost:1935 reachable"},
                "backup": {"ok": True, "detail": "tcp://localhost:1935 reachable"},
                "output": {"ok": True, "detail": "tcp://localhost:1935 reachable"},
            }
        )

        data_dir = self.base / "data"
        host_root = self.base / "host"
        self.host_root = host_root
        self.store = ConfigStore(str(data_dir))
        self.runtime = TestRuntimeAdapter(data_dir / "runtime", host_root)
        self.config = RelayConfig.model_validate(DEFAULT_CONFIG.model_dump(mode="json"))
        self.store.save(self.config)
        self.env_path = _seed_relay_env(host_root)
        os.environ["FAKE_RELAY_ENV"] = str(self.env_path)

        main_module.store = self.store
        main_module.runtime = self.runtime
        self.client = TestClient(app)

    def tearDown(self) -> None:
        main_module.store = original_store
        main_module.runtime = original_runtime
        os.environ["PATH"] = self.original_path
        os.environ.pop("FAKE_SYSTEMCTL_STATE", None)
        os.environ.pop("FAKE_RELAY_ENV", None)
        os.environ.pop("FAKE_SS_LINES", None)
        os.environ.pop("STM_SMOKE_PROBE_OVERRIDE", None)
        self.tempdir.cleanup()

    def test_apply_captures_pre_apply_snapshot(self) -> None:
        # Pre-seed a "previous" mediamtx.yml and a live env file on the host,
        # so the snapshot has something to capture.
        (self.host_root / "etc/streamterminal-relay-matrix").mkdir(parents=True, exist_ok=True)
        previous_mediamtx_yml = (
            "# old mediamtx config\n"
            "logLevel: info\n"
            "api: no\n"
        )
        (self.host_root / "etc/streamterminal-relay-matrix/mediamtx.yml").write_text(previous_mediamtx_yml)

        response = self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "apply"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        payload = response.json()
        self.assertTrue(payload["ok"], payload)

        snapshot_step = next(
            (step for step in payload["steps"] if step["label"].startswith("Snapshot host files")),
            None,
        )
        self.assertIsNotNone(snapshot_step, payload["steps"])
        self.assertEqual(snapshot_step["status"], "executed", snapshot_step)
        self.assertIn("snapshot_id=", snapshot_step["detail"])

        snapshot_id = snapshot_step["detail"].split("snapshot_id=", 1)[1].split()[0]
        snapshot_dir = self.runtime.runtime_dir / "host-snapshots" / snapshot_id
        self.assertTrue(snapshot_dir.exists(), f"snapshot dir missing at {snapshot_dir}")

        # Snapshot should contain the previous mediamtx.yml with its original content.
        snap_mediamtx = snapshot_dir / "files" / "etc/streamterminal-relay-matrix/mediamtx.yml"
        self.assertTrue(snap_mediamtx.exists(), f"snapshot file missing at {snap_mediamtx}")
        self.assertEqual(snap_mediamtx.read_text(), previous_mediamtx_yml)

        # Manifest should list this file.
        manifest_path = snapshot_dir / "manifest.json"
        self.assertTrue(manifest_path.exists(), f"manifest missing at {manifest_path}")
        manifest = json.loads(manifest_path.read_text())
        file_paths = {entry["path"] for entry in manifest["files"]}
        self.assertIn("etc/streamterminal-relay-matrix/mediamtx.yml", file_paths)

    def test_list_host_snapshots_endpoint(self) -> None:
        # No snapshots yet.
        empty = self.client.get("/api/deploy/host-snapshots")
        self.assertEqual(empty.status_code, 200)
        self.assertEqual(empty.json()["snapshots"], [])

        # Trigger an apply so a snapshot is created.
        (self.host_root / "etc/streamterminal-relay-matrix").mkdir(parents=True, exist_ok=True)
        (self.host_root / "etc/streamterminal-relay-matrix/mediamtx.yml").write_text("logLevel: warn\n")
        self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "apply"},
        )

        listing = self.client.get("/api/deploy/host-snapshots")
        self.assertEqual(listing.status_code, 200, listing.text)
        listing_payload = listing.json()
        self.assertGreaterEqual(len(listing_payload["snapshots"]), 1)
        latest = listing_payload["snapshots"][-1]
        self.assertEqual(latest["trigger"], "apply")
        self.assertIn("manifest_path", latest)

    def test_restore_snapshot_endpoint_restores_files(self) -> None:
        # Pre-seed a known file.
        (self.host_root / "etc/streamterminal-relay-matrix").mkdir(parents=True, exist_ok=True)
        (self.host_root / "etc/streamterminal-relay-matrix/mediamtx.yml").write_text(
            "logLevel: warn\napi: yes\n"
        )

        apply_response = self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "apply"},
        )
        self.assertEqual(apply_response.status_code, 200, apply_response.text)
        self.assertTrue(apply_response.json()["ok"], apply_response.json())

        # After the apply the on-host mediamtx.yml will have been overwritten with
        # the freshly generated config. The pre-apply snapshot should restore the
        # original content if we ask for it.
        listing = self.client.get("/api/deploy/host-snapshots").json()
        self.assertGreaterEqual(len(listing["snapshots"]), 1)
        snapshot_id = listing["snapshots"][-1]["id"]

        restore = self.client.post(
            "/api/deploy/restore-snapshot",
            json={"snapshot_id": snapshot_id, "execute": True},
        )
        self.assertEqual(restore.status_code, 200, restore.text)
        restore_payload = restore.json()
        self.assertTrue(restore_payload["ok"], restore_payload)

        restored = self.host_root / "etc/streamterminal-relay-matrix/mediamtx.yml"
        self.assertTrue(restored.exists())
        self.assertEqual(
            restored.read_text(),
            "logLevel: warn\napi: yes\n",
        )


if __name__ == "__main__":
    unittest.main()
