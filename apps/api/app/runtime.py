from __future__ import annotations

import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .schemas import (
    DeployExecuteResponse,
    DeploymentCommand,
    DeploymentExecutionStep,
    DeploymentPlanResponse,
    DeploymentPlannedFile,
    DeploymentProfile,
    DeploymentSecretTemplate,
    GeneratedArtifact,
    RelayConfig,
)


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
        self.bundle_root = self.runtime_dir / "deploy-bundles"
        self.bundle_root.mkdir(parents=True, exist_ok=True)

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

    def relay_command(self, _: RelayConfig) -> str:
        return "\n".join(
            [
                "set -euo pipefail",
                'ENV_FILE="${STM_ENV_FILE:-/etc/streamterminal-relay-matrix/streamterminal-relay.env}"',
                'if [ -f "$ENV_FILE" ]; then',
                "  set -a",
                '  # shellcheck disable=SC1090',
                '  . "$ENV_FILE"',
                "  set +a",
                "fi",
                ': "${STM_PRIMARY_INPUT_URL:?Missing STM_PRIMARY_INPUT_URL}"',
                ': "${STM_BACKUP_INPUT_URL:?Missing STM_BACKUP_INPUT_URL}"',
                ': "${STM_OUTPUT_URL:?Missing STM_OUTPUT_URL}"',
                'RELAY_BIN="${STM_RELAY_BINARY:-stream-failover-relay}"',
                'exec "$RELAY_BIN" "$STM_PRIMARY_INPUT_URL" "$STM_BACKUP_INPUT_URL" "$STM_OUTPUT_URL" --log-level "${STM_RELAY_LOG_LEVEL:-info}"',
            ]
        ) + "\n"

    def relay_env_example(self, config: RelayConfig) -> str:
        return "\n".join(
            [
                "# Copy to streamterminal-relay.env and replace placeholder values before live deployment.",
                "# Keep the real env file out of git and set chmod 600 on the target host.",
                f"STM_CHANNEL_NAME={self._shell_escape(config.channel_name)}",
                "STM_PRIMARY_INPUT_URL='REPLACE_WITH_PRIMARY_INPUT_URL'",
                "STM_BACKUP_INPUT_URL='REPLACE_WITH_BACKUP_INPUT_URL'",
                "STM_OUTPUT_URL='REPLACE_WITH_OUTPUT_URL'",
                "STM_RELAY_LOG_LEVEL='info'",
                "",
            ]
        )

    def relay_secret_template(self, config: RelayConfig, config_dir: str) -> DeploymentSecretTemplate:
        return DeploymentSecretTemplate(
            name="streamterminal-relay.env",
            example_path=f"{config_dir}/streamterminal-relay.env.example",
            live_path=f"{config_dir}/streamterminal-relay.env",
            example_content=self.relay_env_example(config),
            masked_current_values={
                "STM_PRIMARY_INPUT_URL": self._mask_url(config.primary_input.url),
                "STM_BACKUP_INPUT_URL": self._mask_url(config.backup_input.url),
                "STM_OUTPUT_URL": self._mask_url(config.output.url),
            },
            notes=[
                "Generate the live env file on the target host from the example file.",
                "Inject real URLs and stream keys outside the repository and outside committed artifacts.",
                "Set file permissions to 600 and load it via systemd EnvironmentFile.",
            ],
        )

    def mediamtx_service(self, config: RelayConfig, config_dir: str) -> str:
        mediamtx_binary = shutil.which("mediamtx") or "/usr/local/bin/mediamtx"
        config_path = f"{config_dir}/mediamtx.yml"

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

    def relay_service(self, config: RelayConfig, config_dir: str, bin_dir: str) -> str:
        relay_binary = shutil.which("stream-failover-relay") or "/usr/local/bin/stream-failover-relay"
        command_path = f"{bin_dir}/relay-command.sh"
        env_path = f"{config_dir}/streamterminal-relay.env"

        return (
            "[Unit]\n"
            "Description=StreamTerminal Relay Matrix Failover Relay\n"
            "After=network-online.target\n"
            "Wants=network-online.target\n\n"
            "[Service]\n"
            "Type=simple\n"
            f"EnvironmentFile=-{env_path}\n"
            f"ExecStart={command_path}\n"
            "Restart=always\n"
            "RestartSec=2\n"
            f"Environment=STM_RELAY_BINARY={relay_binary}\n"
            f"Environment=STM_ENV_FILE={env_path}\n"
            f"Environment=STM_CHANNEL_NAME={self._systemd_escape(config.channel_name)}\n\n"
            "[Install]\n"
            "WantedBy=multi-user.target\n"
        )

    def preview_artifacts(self, config: RelayConfig, *, config_dir: str | None = None, bin_dir: str | None = None, systemd_dir: str | None = None, root: Path | None = None) -> list[GeneratedArtifact]:
        root = root or self.runtime_dir
        config_dir = config_dir or "/etc/streamterminal-relay-matrix"
        bin_dir = bin_dir or "/usr/local/bin"
        systemd_dir = systemd_dir or "/etc/systemd/system"

        return [
            GeneratedArtifact(
                name="mediamtx.yml",
                path=str(root / "mediamtx.yml"),
                content=self.mediamtx_config(config),
            ),
            GeneratedArtifact(
                name="relay-command.sh",
                path=str(root / "relay-command.sh"),
                content="#!/usr/bin/env bash\n" + self.relay_command(config),
            ),
            GeneratedArtifact(
                name="streamterminal-relay.env.example",
                path=str(root / "streamterminal-relay.env.example"),
                content=self.relay_env_example(config),
            ),
            GeneratedArtifact(
                name="mediamtx.service",
                path=str(root / "mediamtx.service"),
                content=self.mediamtx_service(config, config_dir),
            ),
            GeneratedArtifact(
                name="stream-failover-relay.service",
                path=str(root / "stream-failover-relay.service"),
                content=self.relay_service(config, config_dir, bin_dir),
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

        config_dir = "/etc/streamterminal-relay-matrix"
        bin_dir = "/usr/local/bin"
        systemd_dir = "/etc/systemd/system"

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
                name="streamterminal-relay.env.example",
                path=str(self.install_root / "etc/streamterminal-relay-matrix/streamterminal-relay.env.example"),
                content=self.relay_env_example(config),
            ),
            GeneratedArtifact(
                name="mediamtx.service",
                path=str(self.install_root / "etc/systemd/system/mediamtx.service"),
                content=self.mediamtx_service(config, config_dir),
            ),
            GeneratedArtifact(
                name="stream-failover-relay.service",
                path=str(self.install_root / "etc/systemd/system/stream-failover-relay.service"),
                content=self.relay_service(config, config_dir, bin_dir),
            ),
        ]

        for artifact in installed:
            path = Path(artifact.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(artifact.content)
            if path.suffix == ".sh":
                path.chmod(0o755)

        return installed

    def deployment_profiles(self) -> list[DeploymentProfile]:
        return [
            DeploymentProfile(
                id="local-dev",
                label="Local development host",
                description="Generate a safe local deploy bundle without touching privileged system paths.",
                run_on="local",
                target_host="localhost",
                target_user="current-user",
                path_roots={
                    "config_dir": "/etc/streamterminal-relay-matrix",
                    "bin_dir": "/usr/local/bin",
                    "systemd_dir": "/etc/systemd/system",
                },
                notes=[
                    "Bundle generation is safe: it writes only under apps/api/data/runtime/deploy-bundles/.",
                    "Review generated files before any manual privileged install.",
                ],
                secret_placeholders=[
                    "Create streamterminal-relay.env from the example file on the host and keep it outside git.",
                ],
            ),
            DeploymentProfile(
                id="staging-vm",
                label="Staging VM",
                description="Generate a remote deployment bundle with rsync/ssh command previews for a staging relay host.",
                run_on="remote",
                target_host="relay-staging.example.internal",
                target_user="relayops",
                path_roots={
                    "config_dir": "/etc/streamterminal-relay-matrix",
                    "bin_dir": "/usr/local/bin",
                    "systemd_dir": "/etc/systemd/system",
                },
                notes=[
                    "Use a non-production relay VM first.",
                    "Validate SSH access, sudo policy, and installed binaries before activation.",
                ],
                secret_placeholders=[
                    "Inject real output endpoints via remote env/secrets, not by committing them into repo defaults.",
                ],
            ),
            DeploymentProfile(
                id="production-vm",
                label="Production VM",
                description="Generate a controlled production deployment bundle with restart and verification command previews.",
                run_on="remote",
                target_host="relay-prod.example.internal",
                target_user="relayops",
                path_roots={
                    "config_dir": "/etc/streamterminal-relay-matrix",
                    "bin_dir": "/usr/local/bin",
                    "systemd_dir": "/etc/systemd/system",
                },
                notes=[
                    "Schedule around live traffic and encoder availability.",
                    "Prepare rollback instructions and verify env-file secrets on-host immediately before activation.",
                ],
                secret_placeholders=[
                    "Do not store production stream keys in repo-tracked files or chat transcripts.",
                ],
            ),
        ]

    def deployment_profile(self, profile_id: str) -> DeploymentProfile:
        for profile in self.deployment_profiles():
            if profile.id == profile_id:
                return profile
        raise ValueError(f"Unknown deployment profile: {profile_id}")

    def deployment_plan(self, config: RelayConfig, profile_id: str, latest_revision: Any | None = None) -> DeploymentPlanResponse:
        profile = self.deployment_profile(profile_id)
        staged = self.install_artifacts(config)
        files: list[DeploymentPlannedFile] = []
        config_dir = profile.path_roots["config_dir"]
        bin_dir = profile.path_roots["bin_dir"]
        systemd_dir = profile.path_roots["systemd_dir"]

        mapping = {
            "mediamtx.yml": f"{config_dir}/mediamtx.yml",
            "relay-command.sh": f"{bin_dir}/relay-command.sh",
            "streamterminal-relay.env.example": f"{config_dir}/streamterminal-relay.env.example",
            "mediamtx.service": f"{systemd_dir}/mediamtx.service",
            "stream-failover-relay.service": f"{systemd_dir}/stream-failover-relay.service",
        }

        for artifact in staged:
            source_path = Path(artifact.path)
            files.append(
                DeploymentPlannedFile(
                    name=artifact.name,
                    source_path=str(source_path),
                    target_path=mapping[artifact.name],
                    bytes=source_path.stat().st_size if source_path.exists() else len(artifact.content.encode()),
                    exists_in_stage=source_path.exists(),
                    preview="\n".join(artifact.content.splitlines()[:12]),
                )
            )

        commands = self._deployment_commands(profile, files, config_dir)
        warnings = self._deployment_warnings(config, profile)
        secret_templates = [self.relay_secret_template(config, config_dir)]

        return DeploymentPlanResponse(
            profile=profile,
            staged_root=str(self.install_root),
            generated_at=datetime.now(UTC).isoformat(),
            latest_revision=latest_revision,
            files=files,
            commands=commands,
            secret_templates=secret_templates,
            warnings=warnings,
        )

    def execute_deployment_bundle(self, config: RelayConfig, profile_id: str, execute: bool, latest_revision: Any | None = None) -> DeployExecuteResponse:
        plan = self.deployment_plan(config, profile_id, latest_revision)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        bundle_dir = self.bundle_root / f"{timestamp}-{profile_id}"

        if not execute:
            preview_steps = [
                DeploymentExecutionStep(
                    label="Preview deploy bundle",
                    status="preview",
                    detail=f"Would create bundle under {bundle_dir} without touching any target host.",
                ),
                DeploymentExecutionStep(
                    label="Review env template",
                    status="preview",
                    detail="Would include a placeholder-only env example and masked current values report.",
                ),
            ]
            return DeployExecuteResponse(
                ok=True,
                executed=False,
                mode="preview",
                profile=plan.profile,
                bundle_root=str(bundle_dir),
                remote_touched=False,
                files_created=[],
                steps=preview_steps,
                warnings=plan.warnings,
                next_actions=self._next_actions(plan.profile),
            )

        bundle_dir.mkdir(parents=True, exist_ok=True)
        rootfs_dir = bundle_dir / "rootfs"
        rootfs_dir.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        steps: list[DeploymentExecutionStep] = []

        for file in plan.files:
            target = rootfs_dir / file.target_path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = Path(file.source_path)
            target.write_text(source.read_text())
            if target.suffix == ".sh":
                target.chmod(0o755)
            files_created.append(str(target))
            steps.append(
                DeploymentExecutionStep(
                    label=f"Bundle {file.name}",
                    status="created",
                    detail=f"Created {target}",
                )
            )

        commands_script = bundle_dir / "commands-preview.sh"
        commands_script.write_text(self._commands_preview_script(plan))
        commands_script.chmod(0o755)
        files_created.append(str(commands_script))
        steps.append(
            DeploymentExecutionStep(
                label="Write command preview script",
                status="created",
                detail=f"Created {commands_script}",
            )
        )

        secret_report = bundle_dir / "secret-template-report.json"
        secret_report.write_text(json.dumps([item.model_dump(mode="json") for item in plan.secret_templates], indent=2))
        files_created.append(str(secret_report))
        steps.append(
            DeploymentExecutionStep(
                label="Write secret template report",
                status="created",
                detail=f"Created {secret_report}",
            )
        )

        bundle_readme = bundle_dir / "README.txt"
        bundle_readme.write_text(self._bundle_readme(plan))
        files_created.append(str(bundle_readme))
        steps.append(
            DeploymentExecutionStep(
                label="Write bundle README",
                status="created",
                detail=f"Created {bundle_readme}",
            )
        )

        return DeployExecuteResponse(
            ok=True,
            executed=True,
            mode="bundle",
            profile=plan.profile,
            bundle_root=str(bundle_dir),
            remote_touched=False,
            files_created=files_created,
            steps=steps,
            warnings=plan.warnings,
            next_actions=self._next_actions(plan.profile),
        )

    def host_snapshot(self) -> dict[str, Any]:
        tools = {
            "mediamtx": ["mediamtx", "--version"],
            "stream-failover-relay": ["stream-failover-relay", "--help"],
            "ffmpeg": ["ffmpeg", "-version"],
            "ffprobe": ["ffprobe", "-version"],
            "journalctl": ["journalctl", "--version"],
            "systemctl": ["systemctl", "--version"],
            "rsync": ["rsync", "--version"],
            "ssh": ["ssh", "-V"],
        }

        return {
            "runtime_dir": str(self.runtime_dir),
            "install_root": str(self.install_root),
            "bundle_root": str(self.bundle_root),
            "tools": {name: self._probe_command(command) for name, command in tools.items()},
            "systemd_units": self.systemd_unit_snapshot(),
        }

    def systemd_unit_snapshot(self) -> dict[str, Any]:
        return {unit: self._probe_systemd_unit(unit) for unit in self.SERVICE_UNIT_MAP.values()}

    def service_action(self, service_name: str, action: str, execute: bool = False) -> dict[str, Any]:
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

    def _deployment_commands(self, profile: DeploymentProfile, files: list[DeploymentPlannedFile], config_dir: str) -> list[DeploymentCommand]:
        commands: list[DeploymentCommand] = []
        env_example = f"{config_dir}/streamterminal-relay.env.example"
        env_live = f"{config_dir}/streamterminal-relay.env"

        if profile.run_on == "local":
            mkdirs = " ".join(self._shell_escape(profile.path_roots[key]) for key in ["config_dir", "bin_dir", "systemd_dir"])
            commands.append(
                DeploymentCommand(
                    phase="prepare",
                    label="Create target directories",
                    run_on="local",
                    command=f"sudo mkdir -p {mkdirs}",
                )
            )
            for file in files:
                mode = "0755" if file.name.endswith(".sh") else "0644"
                commands.append(
                    DeploymentCommand(
                        phase="copy",
                        label=f"Install {file.name}",
                        run_on="local",
                        command=f"sudo install -m {mode} {self._shell_escape(file.source_path)} {self._shell_escape(file.target_path)}",
                    )
                )
            commands.extend(
                [
                    DeploymentCommand(
                        phase="copy",
                        label="Create live env file from example",
                        run_on="local",
                        command=f"sudo cp {self._shell_escape(env_example)} {self._shell_escape(env_live)} && sudo chmod 600 {self._shell_escape(env_live)}",
                    ),
                    DeploymentCommand(
                        phase="activate",
                        label="Reload systemd",
                        run_on="local",
                        command="sudo systemctl daemon-reload",
                    ),
                    DeploymentCommand(
                        phase="activate",
                        label="Restart services",
                        run_on="local",
                        command="sudo systemctl restart mediamtx.service stream-failover-relay.service",
                    ),
                    DeploymentCommand(
                        phase="verify",
                        label="Check service state",
                        run_on="local",
                        command="sudo systemctl status mediamtx.service stream-failover-relay.service --no-pager",
                    ),
                ]
            )
            return commands

        target = f"{profile.target_user}@{profile.target_host}"
        commands.append(
            DeploymentCommand(
                phase="prepare",
                label="Create target directories over SSH",
                run_on="remote",
                command="ssh " + self._shell_escape(target) + " " + self._shell_escape("sudo mkdir -p " + profile.path_roots["config_dir"] + " " + profile.path_roots["bin_dir"] + " " + profile.path_roots["systemd_dir"]),
            )
        )
        for file in files:
            commands.append(
                DeploymentCommand(
                    phase="copy",
                    label=f"Copy {file.name}",
                    run_on="remote",
                    command="rsync -av " + self._shell_escape(file.source_path) + " " + self._shell_escape(f"{target}:{file.target_path}"),
                )
            )
        commands.extend(
            [
                DeploymentCommand(
                    phase="copy",
                    label="Create remote env file from example",
                    run_on="remote",
                    command="ssh " + self._shell_escape(target) + " " + self._shell_escape(f"sudo cp {env_example} {env_live} && sudo chmod 600 {env_live}"),
                ),
                DeploymentCommand(
                    phase="activate",
                    label="Reload systemd on remote host",
                    run_on="remote",
                    command="ssh " + self._shell_escape(target) + " " + self._shell_escape("sudo systemctl daemon-reload"),
                ),
                DeploymentCommand(
                    phase="activate",
                    label="Restart remote services",
                    run_on="remote",
                    command="ssh " + self._shell_escape(target) + " " + self._shell_escape("sudo systemctl restart mediamtx.service stream-failover-relay.service"),
                ),
                DeploymentCommand(
                    phase="verify",
                    label="Verify remote service state",
                    run_on="remote",
                    command="ssh " + self._shell_escape(target) + " " + self._shell_escape("sudo systemctl status mediamtx.service stream-failover-relay.service --no-pager"),
                ),
            ]
        )
        return commands

    def _deployment_warnings(self, config: RelayConfig, profile: DeploymentProfile) -> list[str]:
        warnings: list[str] = []
        if self._looks_sensitive_url(config.output.url):
            warnings.append("Output URL appears sensitive; keep the live output destination only in the on-host env file.")
        if profile.id != "local-dev":
            warnings.append("Remote deployment execution is still bundle-only in this prototype; review and run the generated commands manually.")
        if config.primary_input.protocol != config.backup_input.protocol:
            warnings.append("Mixed primary/backup protocols remain a failover risk and may need additional normalization.")
        if not config.auto_restart:
            warnings.append("Auto-restart is disabled in the draft; review whether production should rely on systemd restart behavior.")
        return warnings

    def _commands_preview_script(self, plan: DeploymentPlanResponse) -> str:
        lines = ["#!/usr/bin/env bash", "set -euo pipefail", "", "# Preview only. Review each command before running on a real host."]
        current_phase = None
        for command in plan.commands:
            if command.phase != current_phase:
                lines.extend(["", f"# {command.phase.upper()}"])
                current_phase = command.phase
            lines.append(command.command)
        lines.append("")
        return "\n".join(lines)

    def _bundle_readme(self, plan: DeploymentPlanResponse) -> str:
        secret = plan.secret_templates[0]
        warning_lines = [f"- {warning}" for warning in plan.warnings] or ["- none"]
        return "\n".join(
            [
                f"Profile: {plan.profile.label}",
                f"Target: {plan.profile.target_user}@{plan.profile.target_host}",
                "",
                "This bundle is safe to generate: it does NOT connect to or modify any target host.",
                "Review commands-preview.sh before running anything manually.",
                "",
                "Secret/env handling:",
                f"- Example file: {secret.example_path}",
                f"- Live file:    {secret.live_path}",
                "- Copy the example to the live path on the target host and replace placeholders there.",
                "- Keep the live file out of git and set chmod 600.",
                "",
                "Masked current values:",
                *[f"- {key}: {value}" for key, value in secret.masked_current_values.items()],
                "",
                "Warnings:",
                *warning_lines,
                "",
            ]
        )

    def _next_actions(self, profile: DeploymentProfile) -> list[str]:
        if profile.run_on == "local":
            return [
                "Inspect the generated bundle under apps/api/data/runtime/deploy-bundles/.",
                "Copy streamterminal-relay.env.example to a real on-host env file and replace placeholders.",
                "Run only the reviewed commands you trust with sudo on the actual host.",
            ]
        return [
            "Inspect the generated bundle and commands-preview.sh locally first.",
            "Provision the live env file with real secrets on the remote host outside git.",
            "Run the reviewed rsync/ssh commands manually once SSH access and rollback steps are confirmed.",
        ]

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
        result: dict[str, Any] = {"binary": binary, "path": resolved, "available": bool(resolved)}

        if not resolved:
            return result

        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False)
            output = completed.stdout or completed.stderr
            result["exit_code"] = completed.returncode
            result["preview"] = "\n".join(output.splitlines()[:3])
        except Exception as exc:  # pragma: no cover
            result["error"] = str(exc)

        return result

    def _probe_systemd_unit(self, unit_name: str) -> dict[str, Any]:
        systemctl = shutil.which("systemctl")
        result: dict[str, Any] = {"unit": unit_name, "available": bool(systemctl)}

        if not systemctl:
            return result

        try:
            completed = subprocess.run([systemctl, "show", unit_name, "--property=LoadState,ActiveState,SubState,UnitFileState", "--no-pager"], capture_output=True, text=True, timeout=5, check=False)
            result["exit_code"] = completed.returncode
            parsed: dict[str, str] = {}
            for line in (completed.stdout or completed.stderr).splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    parsed[key] = value
            result["state"] = parsed
        except Exception as exc:  # pragma: no cover
            result["error"] = str(exc)

        return result

    def _run_command(self, command: list[str]) -> dict[str, Any]:
        try:
            completed = subprocess.run(command, capture_output=True, text=True, timeout=10, check=False)
            return {
                "ok": completed.returncode == 0,
                "executed": True,
                "exit_code": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        except Exception as exc:  # pragma: no cover
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

    @staticmethod
    def _looks_sensitive_url(url: str) -> bool:
        return "@" in url or "key=" in url.lower() or "token=" in url.lower()

    @staticmethod
    def _mask_url(url: str) -> str:
        if "://" not in url:
            return "***masked***"
        scheme, rest = url.split("://", 1)
        path = ""
        if "/" in rest:
            _, path = rest.split("/", 1)
            path = "/" + path
        return f"{scheme}://***masked***{path[:24]}"
