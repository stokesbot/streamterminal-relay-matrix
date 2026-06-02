"""Smoke loop and systemd unit hardening tests.

These tests use a sandboxed `sudo`/`systemctl` PATH and a temp
host root so they never mutate the real /etc, /usr/local/bin, or
systemd. The relay service probe uses the fake systemctl state to
verify "running" / "active" semantics.
"""

import json
import os
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

if args[0] in {'enable', 'disable'}:
    action = args[0]
    units = [arg for arg in args[1:] if not arg.startswith('-')]
    for unit in units:
        ensure(unit)
        if action == 'enable':
            if unit == 'stream-failover-relay.service' and not relay_env_ready():
                state[unit].update({'ActiveState': 'activating', 'SubState': 'auto-restart', 'UnitFileState': 'enabled', 'ExecMainStatus': '1', 'NRestarts': '2'})
            else:
                state[unit].update({'ActiveState': 'active', 'SubState': 'running', 'UnitFileState': 'enabled', 'ExecMainStatus': '0', 'NRestarts': '0'})
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


class SmokeLoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.fakebin = self.base / "fakebin"
        self.fakebin.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base / "systemctl-state.json"
        self.ss_lines_path = self.base / "ss-lines.txt"
        self.ss_lines_path.write_text("\n".join(FAKE_SS_LINES) + "\n")
        self._write_executable(self.fakebin / "sudo", FAKE_SUDO)
        self._write_executable(self.fakebin / "systemctl", FAKE_SYSTEMCTL)
        self._write_executable(self.fakebin / "ss", FAKE_SS)
        self._write_executable(self.fakebin / "netstat", FAKE_NETSTAT)

        self.original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.fakebin}:{self.original_path}"
        os.environ["FAKE_SYSTEMCTL_STATE"] = str(self.state_path)
        os.environ["FAKE_SS_LINES"] = str(self.ss_lines_path)
        os.environ["STM_SMOKE_PROBE_OVERRIDE"] = json.dumps(
            {
                # Probe results for the network-reachability checks.
                # The smoke endpoint should treat these as overrides so the test is
                # fully hermetic and never opens a real socket to the upstream RTMP.
                "primary": {"ok": True, "detail": "tcp://localhost:1935 reachable"},
                "backup": {"ok": True, "detail": "tcp://localhost:1935 reachable"},
                "output": {"ok": False, "detail": "tcp://example.invalid:1935 connection refused"},
            }
        )

        data_dir = self.base / "data"
        host_root = self.base / "host"
        self.host_root = host_root
        self.store = ConfigStore(str(data_dir))
        self.runtime = TestRuntimeAdapter(data_dir / "runtime", host_root)
        self.config = RelayConfig.model_validate(DEFAULT_CONFIG.model_dump(mode="json"))
        # Set output to a host that we can fake a refusal for.
        self.config.output.url = "rtmp://example.invalid:1935/live/output"
        self.store.save(self.config)

        relay_env_path = self.host_root / "etc/streamterminal-relay-matrix/streamterminal-relay.env"
        relay_env_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["FAKE_RELAY_ENV"] = str(relay_env_path)
        relay_env_path.write_text(
            "\n".join(
                [
                    "STM_PRIMARY_INPUT_URL=rtmp://localhost:1935/live/main",
                    "STM_BACKUP_INPUT_URL=rtmp://localhost:1935/live/backup",
                    "STM_OUTPUT_URL=rtmp://example.invalid:1935/live/output",
                    "",
                ]
            )
        )

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

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content)
        path.chmod(0o755)

    def _seed_unit_state(self, *, mediamtx: str, relay: str) -> None:
        state = {
            "mediamtx.service": {
                "ActiveState": mediamtx,
                "SubState": "running" if mediamtx == "active" else "dead",
                "UnitFileState": "enabled" if mediamtx == "active" else "disabled",
                "ExecMainStatus": "0" if mediamtx == "active" else "1",
                "NRestarts": "0",
            },
            "stream-failover-relay.service": {
                "ActiveState": relay,
                "SubState": "running" if relay == "active" else "dead",
                "UnitFileState": "enabled" if relay == "active" else "disabled",
                "ExecMainStatus": "0" if relay == "active" else "1",
                "NRestarts": "0",
            },
        }
        self.state_path.write_text(json.dumps(state))

    def test_smoke_endpoint_reports_full_status(self) -> None:
        self._seed_unit_state(mediamtx="active", relay="active")

        response = self.client.get("/api/runtime/smoke")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("checks", payload)
        self.assertIn("summary", payload)
        self.assertIn("generated_at", payload)
        names = {check["name"] for check in payload["checks"]}
        self.assertIn("mediamtx service", names)
        self.assertIn("mediamtx rtmp listener", names)
        self.assertIn("stream-failover-relay service", names)
        self.assertIn("primary input reachable", names)
        self.assertIn("backup input reachable", names)
        self.assertIn("output destination reachable", names)

        status_by_name = {check["name"]: check["status"] for check in payload["checks"]}
        self.assertEqual(status_by_name["mediamtx service"], "pass")
        self.assertEqual(status_by_name["mediamtx rtmp listener"], "pass")
        self.assertEqual(status_by_name["stream-failover-relay service"], "pass")
        self.assertEqual(status_by_name["primary input reachable"], "pass")
        self.assertEqual(status_by_name["backup input reachable"], "pass")
        self.assertEqual(status_by_name["output destination reachable"], "fail")

        self.assertEqual(payload["summary"]["fail_count"], 1)
        self.assertFalse(payload["ok"])

    def test_smoke_endpoint_fails_when_mediamtx_not_listening(self) -> None:
        self._seed_unit_state(mediamtx="active", relay="active")
        self.ss_lines_path.write_text(
            "State      Recv-Q Send-Q    Local Address:Port    Peer Address:Port\n"
            "LISTEN     0      4096          0.0.0.0:8080         0.0.0.0:*\n"
        )

        response = self.client.get("/api/runtime/smoke")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        status_by_name = {check["name"]: check["status"] for check in payload["checks"]}
        self.assertEqual(status_by_name["mediamtx rtmp listener"], "fail")
        self.assertFalse(payload["ok"])

    def test_smoke_endpoint_fails_when_relay_crash_looping(self) -> None:
        self._seed_unit_state(mediamtx="active", relay="failed")
        # Force NRestarts=4 to look like a crash loop.
        state = json.loads(self.state_path.read_text())
        state["stream-failover-relay.service"].update(
            {
                "ActiveState": "activating",
                "SubState": "auto-restart",
                "ExecMainStatus": "1",
                "NRestarts": "4",
            }
        )
        self.state_path.write_text(json.dumps(state))

        response = self.client.get("/api/runtime/smoke")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        status_by_name = {check["name"]: check["status"] for check in payload["checks"]}
        self.assertEqual(status_by_name["stream-failover-relay service"], "fail")
        self.assertFalse(payload["ok"])

    def test_mediamtx_service_template_is_hardened(self) -> None:
        mediamtx_unit = self.runtime.mediamtx_service(self.config, "/etc/streamterminal-relay-matrix")
        for directive in [
            "Restart=always",
            "RestartSec=",
            "WatchdogSec=60",
            "LimitNOFILE=65536",
            "After=network-online.target",
            "Wants=network-online.target",
            "StandardOutput=journal",
            "StandardError=journal",
        ]:
            self.assertIn(directive, mediamtx_unit, f"missing mediamtx directive: {directive}")

    def test_relay_service_template_is_hardened(self) -> None:
        relay_unit = self.runtime.relay_service(
            self.config, "/etc/streamterminal-relay-matrix", "/usr/local/bin"
        )
        for directive in [
            "Restart=always",
            "RestartSec=",
            "LimitNOFILE=65536",
            "MemoryMax=512M",
            "After=network-online.target",
            "Wants=network-online.target",
            "StandardOutput=journal",
            "StandardError=journal",
        ]:
            self.assertIn(directive, relay_unit, f"missing relay directive: {directive}")


if __name__ == "__main__":
    unittest.main()
