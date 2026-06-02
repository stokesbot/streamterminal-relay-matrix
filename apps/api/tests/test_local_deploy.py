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

FAKE_TOOL = """#!/usr/bin/env bash
echo fake-$0
exit 0
"""


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


class LocalDeployApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.base = Path(self.tempdir.name)
        self.fakebin = self.base / "fakebin"
        self.fakebin.mkdir(parents=True, exist_ok=True)
        self.state_path = self.base / "systemctl-state.json"
        self._write_executable(self.fakebin / "sudo", FAKE_SUDO)
        self._write_executable(self.fakebin / "systemctl", FAKE_SYSTEMCTL)
        self._write_executable(self.fakebin / "mediamtx", FAKE_TOOL)
        self._write_executable(self.fakebin / "stream-failover-relay", FAKE_TOOL)

        self.original_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.fakebin}:{self.original_path}"
        os.environ["FAKE_SYSTEMCTL_STATE"] = str(self.state_path)

        data_dir = self.base / "data"
        host_root = self.base / "host"
        self.host_root = host_root
        self.store = ConfigStore(str(data_dir))
        self.runtime = TestRuntimeAdapter(data_dir / "runtime", host_root)
        self.config = RelayConfig.model_validate(DEFAULT_CONFIG.model_dump(mode="json"))
        self.store.save(self.config)

        relay_env_path = self.host_root / "etc/streamterminal-relay-matrix/streamterminal-relay.env"
        relay_env_path.parent.mkdir(parents=True, exist_ok=True)
        os.environ["FAKE_RELAY_ENV"] = str(relay_env_path)

        main_module.store = self.store
        main_module.runtime = self.runtime
        self.client = TestClient(app)

    def tearDown(self) -> None:
        main_module.store = original_store
        main_module.runtime = original_runtime
        os.environ["PATH"] = self.original_path
        os.environ.pop("FAKE_SYSTEMCTL_STATE", None)
        os.environ.pop("FAKE_RELAY_ENV", None)
        self.tempdir.cleanup()

    def _write_executable(self, path: Path, content: str) -> None:
        path.write_text(content)
        path.chmod(0o755)

    def _write_valid_live_env(self) -> Path:
        env_path = Path(os.environ["FAKE_RELAY_ENV"])
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

    def test_preflight_apply_and_rollback(self) -> None:
        self._write_valid_live_env()

        preflight = self.client.get("/api/deploy/preflight", params={"profile_id": "local-system"})
        self.assertEqual(preflight.status_code, 200)
        preflight_payload = preflight.json()
        self.assertTrue(preflight_payload["summary"]["ok"])
        env_check = next(item for item in preflight_payload["checks"] if item["name"] == "Live relay env readiness")
        self.assertEqual(env_check["status"], "pass")

        first_apply = self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "apply"},
        )
        self.assertEqual(first_apply.status_code, 200)
        first_apply_payload = first_apply.json()
        self.assertTrue(first_apply_payload["ok"])
        self.assertEqual(first_apply_payload["mode"], "apply")
        self.assertTrue(first_apply_payload["host_touched"])

        live_config_path = self.base / "host/etc/streamterminal-relay-matrix/mediamtx.yml"
        self.assertTrue(live_config_path.exists())
        first_contents = live_config_path.read_text()
        self.assertIn("rtmpAddress: :1935", first_contents)
        self.assertIn("paths:", first_contents)
        self.assertIn("  live/main:", first_contents)
        self.assertIn("  live/backup:", first_contents)

        updated_config = RelayConfig.model_validate(DEFAULT_CONFIG.model_dump(mode="json"))
        updated_config.channel_name = "Rollback target"
        updated_config.primary_input.url = "rtmp://localhost:1935/live/changed-main"
        updated_config.output.url = "rtmp://localhost:1935/live/changed-output"
        save_response = self.client.put("/api/config/draft", json=updated_config.model_dump(mode="json"))
        self.assertEqual(save_response.status_code, 200)

        second_apply = self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "apply"},
        )
        self.assertEqual(second_apply.status_code, 200)
        self.assertTrue(second_apply.json()["ok"])
        second_contents = live_config_path.read_text()
        self.assertIn("changed-main", second_contents)

        rollback = self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "rollback"},
        )
        self.assertEqual(rollback.status_code, 200)
        rollback_payload = rollback.json()
        self.assertTrue(rollback_payload["ok"])
        self.assertEqual(rollback_payload["mode"], "rollback")
        self.assertTrue(rollback_payload["host_touched"])

        rolled_back_contents = live_config_path.read_text()
        self.assertEqual(rolled_back_contents, first_contents)

        current_config = self.client.get("/api/config")
        self.assertEqual(current_config.status_code, 200)
        self.assertEqual(current_config.json()["channel_name"], self.config.channel_name)

    def test_apply_blocks_unready_relay_env(self) -> None:
        preflight = self.client.get("/api/deploy/preflight", params={"profile_id": "local-system"})
        self.assertEqual(preflight.status_code, 200)
        preflight_payload = preflight.json()
        self.assertFalse(preflight_payload["summary"]["ok"])
        env_check = next(item for item in preflight_payload["checks"] if item["name"] == "Live relay env readiness")
        self.assertEqual(env_check["status"], "fail")

        apply_response = self.client.post(
            "/api/deploy/execute",
            json={"profile_id": "local-system", "execute": True, "action": "apply"},
        )
        self.assertEqual(apply_response.status_code, 200)
        payload = apply_response.json()
        self.assertFalse(payload["ok"])
        relay_env_step = next(item for item in payload["steps"] if item["label"] == "Verify live relay env")
        self.assertEqual(relay_env_step["status"], "failed")
        relay_state_step = next(item for item in payload["steps"] if item["label"] == "Verify stream-failover-relay state")
        self.assertEqual(relay_state_step["status"], "executed")
        self.assertIn("UnitFileState=disabled", relay_state_step["detail"])


if __name__ == "__main__":
    unittest.main()
