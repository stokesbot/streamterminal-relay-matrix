from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any

from .schemas import GeneratedArtifact, RelayConfig


class RuntimeAdapter:
    SERVICE_UNIT_MAP = {
        "mediamtx": "mediamtx.service",
        "stream-failover-relay": "stream-failover-relay.service",
    }

    def __init__(self, runtime_dir: str | Path) -> None:
        self.runtime_dir = Path(runtime_dir)
        self.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.install_root = self.runtime_dir / "install-root"
        self.install_root.mkdir(parents=True, exist_ok=True)

    def mediamtx_config(self, config: RelayConfig) -> str:
        if not config.mediamtx_enabled:
            return "# MediaMTX disabled in current draft\n"

        primary_path = self._path_name(config.primary_input, "main")
        backup_path = self._path_name(config.backup_input, "backup")

        return (
            "logLevel: info\n"
            "rtmp: yes\n"
            "rtmpAddress: :1935\n"
            "hls: no\n"
            "webrtc: no\n"
            "srt: no\n"
            "api: no\n"
            "paths:\n"
            f"  {primary_path}:\n"
            "    source: publisher\n"
            f"  {backup_path}:\n"
            "    source: publisher\n"
        )

    def relay_command(self, config: RelayConfig) -> str:
        command = [
            "stream-failover-relay",
            config.primary_input.url,
            config.backup_input.url,
            config.output.url,
            "--log-level",
            "info",
        ]
        return " ".join(self._shell_escape(part) for part in command) + "\n"

    def mediamtx_service(self, config: RelayConfig) -> str:
        mediamtx_binary = shutil.which("mediamtx") or "/usr/local/bin/mediamtx"
        config_path = self.install_root / "etc/streamterminal-relay-matrix/mediamtx.yml"

        return (
            "[Unit]\n"
            "Description=StreamTerminal Relay Matrix MediaMTX\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={mediamtx_binary} {config_path}\n"
            "Restart=always\n"
            "RestartSec=2\n"
            f"Environment=STM_CHANNEL_NAME={self._systemd_escape(config.channel_name)}\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

    def relay_service(self, config: RelayConfig) -> str:
        relay_binary = shutil.which("stream-failover-relay") or "/usr/local/bin/stream-failover-relay"
        command_path = self.install_root / "usr/local/bin/relay-command.sh"

        return (
            "[Unit]\n"
            "Description=StreamTerminal Relay Matrix Failover Relay\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"ExecStart={command_path}\n"
            "Restart=always\n"
            "RestartSec=2\n"
            f"Environment=STM_RELAY_BINARY={relay_binary}\n"
            f"Environment=STM_CHANNEL_NAME={self._systemd_escape(config.channel_name)}\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

    def preview_artifacts(self, config: RelayConfig) -> list[GeneratedArtifact]:
        return [
            GeneratedArtifact(
                name="mediamtx.yml",
                path=str(self.runtime_dir / "mediamtx.yml"),
                content=self.mediamtx_config(config),
            ),
            GeneratedArtifact(
                name="relay-command.sh",
                path=str(self.runtime_dir / "relay-command.sh"),
                content="#!/usr/bin/env bash\n" + self.relay_command(config),
            ),
            GeneratedArtifact(
                name="mediamtx.service",
                path=str(self.runtime_dir / "mediamtx.service"),
                content=self.mediamtx_service(config),
            ),
            GeneratedArtifact(
                name="stream-failover-relay.service",
                path=str(self.runtime_dir / "stream-failover-relay.service"),
                content=self.relay_service(config),
            ),
        ]

    def write_runtime_artifacts(self, config: RelayConfig) -> list[GeneratedArtifact]:
        artifacts = self.preview_artifacts(config)

        for artifact in artifacts:
            path = Path(artifact.path)
            path.write_text(artifact.content)
            if path.suffix == ".sh":
                path.chmod(0o755)

        return artifacts

    def install_artifacts(self, config: RelayConfig) -> list[GeneratedArtifact]:
        self.write_runtime_artifacts(config)

        installed = [
            GeneratedArtifact(
                name="mediamtx.yml",
                path=str(self.install_root / "etc/streamterminal-relay-matrix/mediamtx.yml"),
                content=self.mediamtx_config(config),
            ),
            GeneratedArtifact(
                name="relay-command.sh",
                path=str(self.install_root / "usr/local/bin/relay-command.sh"),
                content="#!/usr/bin/env bash\n" + self.relay_command(config),
            ),
            GeneratedArtifact(
                name="mediamtx.service",
                path=str(self.install_root / "etc/systemd/system/mediamtx.service"),
                content=self.mediamtx_service(config),
            ),
            GeneratedArtifact(
                name="stream-failover-relay.service",
                path=str(self.install_root / "etc/systemd/system/stream-failover-relay.service"),
                content=self.relay_service(config),
            ),
        ]

        for artifact in installed:
            path = Path(artifact.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(artifact.content)
            if path.suffix == ".sh":
                path.chmod(0o755)

        return installed

    def host_snapshot(self) -> dict[str, Any]:
        tools = {
            "mediamtx": ["mediamtx", "--version"],
            "stream-failover-relay": ["stream-failover-relay", "--help"],
            "ffmpeg": ["ffmpeg", "-version"],
            "ffprobe": ["ffprobe", "-version"],
            "journalctl": ["journalctl", "--version"],
            "systemctl": ["systemctl", "--version"],
        }

        return {
            "runtime_dir": str(self.runtime_dir),
            "install_root": str(self.install_root),
            "tools": {
                name: self._probe_command(command)
                for name, command in tools.items()
            },
            "systemd_units": self.systemd_unit_snapshot(),
        }

    def systemd_unit_snapshot(self) -> dict[str, Any]:
        return {
            unit: self._probe_systemd_unit(unit)
            for unit in self.SERVICE_UNIT_MAP.values()
        }

    def service_action(
        self,
        service_name: str,
        action: str,
        execute: bool = False,
    ) -> dict[str, Any]:
        unit_name = self._unit_name(service_name)
        command = self._systemctl_command(action, unit_name)

        if not execute:
            return {
                "ok": True,
                "executed": False,
                "service": service_name,
                "unit": unit_name,
                "action": action,
                "command": command,
                "stdout": "",
                "stderr": "",
                "exit_code": 0,
            }

        return {
            "service": service_name,
            "unit": unit_name,
            "action": action,
            "command": command,
            **self._run_command(command),
        }

    def service_logs(self, service_name: str, lines: int = 100) -> dict[str, Any]:
        unit_name = self._unit_name(service_name)
        journalctl = shutil.which("journalctl")
        if not journalctl:
            return {
                "service": service_name,
                "unit": unit_name,
                "available": False,
                "lines": [],
                "detail": "journalctl not available on host",
            }

        command = [journalctl, "-u", unit_name, "-n", str(lines), "--no-pager"]
        result = self._run_command(command)
        output = result.get("stdout") or result.get("stderr") or ""

        return {
            "service": service_name,
            "unit": unit_name,
            "available": True,
            "command": command,
            "exit_code": result.get("exit_code", 1),
            "lines": output.splitlines(),
            "detail": "journalctl query executed",
        }

    def _unit_name(self, service_name: str) -> str:
        try:
            return self.SERVICE_UNIT_MAP[service_name]
        except KeyError as exc:
            raise ValueError(f"Unknown service: {service_name}") from exc

    def _systemctl_command(self, action: str, unit_name: str) -> list[str]:
        systemctl = shutil.which("systemctl") or "systemctl"
        action_map = {
            "start": [systemctl, "start", unit_name],
            "stop": [systemctl, "stop", unit_name],
            "restart": [systemctl, "restart", unit_name],
            "reload": [systemctl, "reload", unit_name],
            "status": [systemctl, "status", unit_name, "--no-pager"],
            "daemon-reload": [systemctl, "daemon-reload"],
        }
        try:
            return action_map[action]
        except KeyError as exc:
            raise ValueError(f"Unsupported action: {action}") from exc

    def _probe_command(self, command: list[str]) -> dict[str, Any]:
        binary = command[0]
        resolved = shutil.which(binary)
        result: dict[str, Any] = {
            "binary": binary,
            "path": resolved,
            "available": bool(resolved),
        }

        if not resolved:
            return result

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            output = completed.stdout or completed.stderr
            result["exit_code"] = completed.returncode
            result["preview"] = "\n".join(output.splitlines()[:3])
        except Exception as exc:  # pragma: no cover - defensive probe path
            result["error"] = str(exc)

        return result

    def _probe_systemd_unit(self, unit_name: str) -> dict[str, Any]:
        systemctl = shutil.which("systemctl")
        result: dict[str, Any] = {
            "unit": unit_name,
            "available": bool(systemctl),
        }

        if not systemctl:
            return result

        try:
            completed = subprocess.run(
                [
                    systemctl,
                    "show",
                    unit_name,
                    "--property=LoadState,ActiveState,SubState,UnitFileState",
                    "--no-pager",
                ],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
            result["exit_code"] = completed.returncode
            parsed: dict[str, str] = {}
            for line in (completed.stdout or completed.stderr).splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    parsed[key] = value
            result["state"] = parsed
        except Exception as exc:  # pragma: no cover - defensive probe path
            result["error"] = str(exc)

        return result

    def _run_command(self, command: list[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            return {
                "ok": completed.returncode == 0,
                "executed": True,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except Exception as exc:  # pragma: no cover - defensive execution path
            return {
                "ok": False,
                "executed": True,
                "exit_code": 1,
                "stdout": "",
                "stderr": str(exc),
            }

    @staticmethod
    def _shell_escape(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"

    @staticmethod
    def _systemd_escape(value: str) -> str:
        return '"' + value.replace('"', '\\"') + '"'

    @staticmethod
    def _path_name(endpoint: Any, fallback: str) -> str:
        tail = endpoint.url.rstrip("/").split("/")[-1]
        return tail or fallback
