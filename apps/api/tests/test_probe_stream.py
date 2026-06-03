"""Stream probe tests for probe_stream_state.

Tests RuntimeAdapter.probe_stream_state with fake journalctl data
so they are hermetic and do not depend on real systemd state.
"""
import os
import tempfile
import unittest
from pathlib import Path

from app.schemas import RelayConfig, StreamEndpoint
from app.runtime import RuntimeAdapter


class FakeJournalctlTestCase(unittest.TestCase):
    """Base for tests that inject a fake journalctl binary via PATH."""

    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.fakebin = self.tmp / "bin"
        self.fakebin.mkdir(parents=True, exist_ok=True)
        self.old_path = os.environ.get("PATH", "")
        os.environ["PATH"] = f"{self.fakebin}{os.pathsep}{self.old_path}"
        self.runtime = RuntimeAdapter(self.tmp / "runtime")

    def tearDown(self) -> None:
        os.environ["PATH"] = self.old_path

    def _write_fake_journalctl(self, stdout: str, exit_code: int = 0) -> None:
        # Write fake journalctl that reads data from a temp file
        import tempfile as _tf
        data_file = _tf.NamedTemporaryFile(mode='w', delete=False, suffix='.txt')
        data_file.write(stdout)
        data_file.close()
        self._journal_data_file = data_file.name
        script = (
            "#!/usr/bin/env python3\n"
            "import sys\n"
            f"with open({repr(data_file.name)}, 'r') as f:\n"
            "    print(f.read(), end='')\n"
            f"raise SystemExit({exit_code})\n"
        )
        fake_path = self.fakebin / "journalctl"
        fake_path.write_text(script)
        fake_path.chmod(0o755)
        # Also store for _fake_run_command override
        self.fake_stdout = stdout
        self.fake_exit_code = exit_code
        self.original_run_command = self.runtime._run_command
        self.runtime._run_command = self._fake_run_command

    def _fake_run_command(self, command: list[str]) -> dict:
        return {
            "ok": self.fake_exit_code == 0,
            "stdout": self.fake_stdout,
            "stderr": "",
            "exit_code": self.fake_exit_code,
        }

    def _default_config(self) -> RelayConfig:
        return RelayConfig(
            channel_name="Test",
            mediamtx_enabled=True,
            relay_enabled=True,
            auto_restart=True,
            primary_input=StreamEndpoint(
                label="Primary", protocol="rtmp",
                url="rtmp://localhost:1935/live/main",
                mode="listener", enabled=True,
            ),
            backup_input=StreamEndpoint(
                label="Backup", protocol="rtmp",
                url="rtmp://localhost:1935/live/backup",
                mode="listener", enabled=True,
            ),
            output=StreamEndpoint(
                label="IBM VS", protocol="rtmp",
                url="rtmp://example.invalid/live/output",
                mode="caller", enabled=True,
            ),
        )


class TestProbeStreamStatePrimary(FakeJournalctlTestCase):
    """probe_stream_state when primary is active."""

    PRIMARY_ACTIVE_LOGS = """
inputs: InputWithFallback(InputChain(Input(rtmp://localhost:1935/live/main/):active):current, InputChain(<unable to lock>; factory:rtmp://localhost:1935/live/backup):paused)
input main: {"Unknown":{},"Other":{},"Video":{"Count":2431,"Bytes":36484544},"Audio":{"Count":4594,"Bytes":797624}}
input fallback: {"Unknown":{},"Other":{},"Video":{},"Audio":{}}
output:{"Unknown":{},"Other":{},"Video":{"Count":2431,"Bytes":36484544},"Audio":{"Count":4594,"Bytes":797624}}
"""

    def test_detects_primary_active(self) -> None:
        self._write_fake_journalctl(self.PRIMARY_ACTIVE_LOGS)
        result = self.runtime.probe_stream_state(self._default_config(), lines=10)
        self.assertEqual(result["active_source"], "primary")
        self.assertTrue(result["probe_success"])
        self.assertGreater(result["primary_bytes"], 0)
        self.assertEqual(result["backup_bytes"], 0)


class TestProbeStreamStateBackup(FakeJournalctlTestCase):
    """probe_stream_state when backup is active (primary dead)."""

    BACKUP_ACTIVE_LOGS = """
inputs: InputWithFallback(InputChain(<unable to lock>; factory:rtmp://localhost:1935/live/main), InputChain(Input(rtmp://localhost:1935/live/backup/):active):current)
input main: {"Unknown":{},"Other":{},"Video":{"Count":5023,"Bytes":75567867},"Audio":{"Count":9550,"Bytes":1652968}}
input fallback: {"Unknown":{},"Other":{},"Video":{"Count":16257,"Bytes":192809197},"Audio":{"Count":30625,"Bytes":2142943}}
output:{"Unknown":{},"Other":{},"Video":{"Count":21279,"Bytes":268371496},"Audio":{"Count":39902,"Bytes":3749783}}
"""

    def test_detects_backup_active(self) -> None:
        self._write_fake_journalctl(self.BACKUP_ACTIVE_LOGS)
        result = self.runtime.probe_stream_state(self._default_config(), lines=10)
        self.assertEqual(result["active_source"], "backup")
        self.assertTrue(result["probe_success"])
        self.assertGreater(result["backup_bytes"], 0)
        self.assertGreater(result["output_bytes"], 0)


class TestProbeStreamStateCustomPaths(FakeJournalctlTestCase):
    """probe_stream_state works with custom RTMP paths."""

    CUSTOM_LOGS = """
inputs: InputWithFallback(InputChain(Input(rtmp://localhost:1935/stream_a):active):current, InputChain(<unable to lock>; factory:rtmp://localhost:1935/stream_b):paused)
input main: {"Unknown":{},"Video":{"Count":100,"Bytes":5000000}}
input fallback: {"Unknown":{},"Video":{},"Audio":{}}
output:{"Unknown":{},"Video":{"Count":100,"Bytes":5000000}}
"""

    def test_custom_paths(self) -> None:
        self._write_fake_journalctl(self.CUSTOM_LOGS)
        config = RelayConfig(
            channel_name="Custom",
            mediamtx_enabled=True,
            relay_enabled=True,
            auto_restart=True,
            primary_input=StreamEndpoint(
                label="A", protocol="rtmp",
                url="rtmp://localhost:1935/stream_a",
                mode="listener", enabled=True,
            ),
            backup_input=StreamEndpoint(
                label="B", protocol="rtmp",
                url="rtmp://localhost:1935/stream_b",
                mode="listener", enabled=True,
            ),
            output=StreamEndpoint(
                label="Out", protocol="rtmp",
                url="rtmp://example.invalid/out",
                mode="caller", enabled=True,
            ),
        )
        result = self.runtime.probe_stream_state(config, lines=10)
        self.assertEqual(result["active_source"], "primary")
        self.assertEqual(result["primary_bytes"], 5000000)
        self.assertEqual(result["backup_bytes"], 0)


class TestProbeStreamStateNoJournalctl(FakeJournalctlTestCase):
    """probe_stream_state when journalctl is not available."""

    def test_no_journalctl(self) -> None:
        # Ensure PATH has no journalctl by restricting to fakebin only
        os.environ["PATH"] = str(self.fakebin)
        result = self.runtime.probe_stream_state(self._default_config(), lines=10)
        self.assertEqual(result["active_source"], "unknown")
        self.assertFalse(result["probe_success"])
        self.assertEqual(result["error_hint"], "journalctl not available on host")


if __name__ == "__main__":
    unittest.main()
