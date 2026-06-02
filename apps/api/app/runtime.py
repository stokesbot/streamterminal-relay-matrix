from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .schemas import (
    DeployExecuteResponse,
    DeploymentAuditFile,
    DeploymentAuditResponse,
    DeploymentAuditSummary,
    DeploymentCommand,
    DeploymentExecutionStep,
    DeploymentPlanResponse,
    DeploymentPlannedFile,
    DeploymentPreflightCheck,
    DeploymentPreflightResponse,
    DeploymentPreflightSummary,
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
    REQUIRED_ENV_KEYS = (
        "STM_PRIMARY_INPUT_URL",
        "STM_BACKUP_INPUT_URL",
        "STM_OUTPUT_URL",
    )

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
        listen_address = self._rtmp_listen_address(config)

        return (
            "logLevel: info\n"
            "rtmp: yes\n"
            f"rtmpAddress: {listen_address}\n"
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
                "# Copy to streamterminal-relay.env and replace placeholder values before local activation.",
                "# Keep the real env file out of git and set chmod 600 on the host.",
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
                "Create the live env file locally from the example file.",
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

    def local_profile(self) -> DeploymentProfile:
        host_root = os.environ.get("STM_TEST_HOST_ROOT")
        if host_root:
            config_dir = f"{host_root}/etc/streamterminal-relay-matrix"
            bin_dir = f"{host_root}/usr/local/bin"
            systemd_dir = f"{host_root}/etc/systemd/system"
        else:
            config_dir = "/etc/streamterminal-relay-matrix"
            bin_dir = "/usr/local/bin"
            systemd_dir = "/etc/systemd/system"
        return DeploymentProfile(
            id="local-system",
            label="Local Linux host",
            description="Install and operate the relay stack on the same machine where the control plane runs.",
            run_on="local",
            target_host="localhost",
            target_user="current-user",
            path_roots={
                "config_dir": config_dir,
                "bin_dir": bin_dir,
                "systemd_dir": systemd_dir,
            },
            notes=[
                "This workflow is local-only: no SSH, rsync, or remote VPS copy steps are generated.",
                "Use systemd on the same machine to run MediaMTX and the relay after install.",
            ],
            secret_placeholders=[
                "Create streamterminal-relay.env from the example file locally and keep it outside git.",
            ],
            source="builtin",
            editable=False,
        )

    def preview_artifacts(
        self,
        config: RelayConfig,
        *,
        config_dir: str | None = None,
        bin_dir: str | None = None,
        root: Path | None = None,
    ) -> list[GeneratedArtifact]:
        root = root or self.runtime_dir
        config_dir = config_dir or "/etc/streamterminal-relay-matrix"
        bin_dir = bin_dir or "/usr/local/bin"

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
                content=self.mediamtx_service(config, "/etc/streamterminal-relay-matrix"),
            ),
            GeneratedArtifact(
                name="stream-failover-relay.service",
                path=str(self.install_root / "etc/systemd/system/stream-failover-relay.service"),
                content=self.relay_service(config, "/etc/streamterminal-relay-matrix", "/usr/local/bin"),
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
        return [self.local_profile()]

    def deployment_profile(self, profile_id: str) -> DeploymentProfile:
        profile = self.local_profile()
        if profile.id != profile_id:
            raise ValueError(f"Unknown deployment profile: {profile_id}")
        return profile

    def deployment_plan(
        self,
        config: RelayConfig,
        profile_id: str,
        latest_revision: Any | None = None,
    ) -> DeploymentPlanResponse:
        profile = self.deployment_profile(profile_id)
        staged = self.install_artifacts(config)
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

        files: list[DeploymentPlannedFile] = []
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

        return DeploymentPlanResponse(
            profile=profile,
            staged_root=str(self.install_root),
            generated_at=datetime.now(UTC).isoformat(),
            latest_revision=latest_revision,
            files=files,
            commands=self._deployment_commands(profile, files, config),
            secret_templates=[self.relay_secret_template(config, config_dir)],
            warnings=self._deployment_warnings(config),
        )

    def deployment_preflight(
        self,
        config: RelayConfig,
        profile_id: str,
        latest_revision: Any | None = None,
    ) -> DeploymentPreflightResponse:
        profile = self.deployment_profile(profile_id)
        checks: list[DeploymentPreflightCheck] = []

        sudo_available = shutil.which("sudo") is not None
        sudo_probe = self._run_command(["sudo", "-n", "true"]) if sudo_available else {"ok": False, "stderr": "sudo not found"}
        checks.append(
            DeploymentPreflightCheck(
                name="Non-interactive sudo",
                status="pass" if sudo_probe.get("ok") else "fail",
                detail="The API can escalate locally without prompting." if sudo_probe.get("ok") else "Local apply needs passwordless sudo (sudo -n true).",
                command="sudo -n true",
            )
        )

        systemctl_path = shutil.which("systemctl")
        if not systemctl_path:
            checks.append(
                DeploymentPreflightCheck(
                    name="systemd available",
                    status="fail",
                    detail="systemctl is not available on this host.",
                    command="systemctl --version",
                )
            )
        else:
            system_running = self._run_command([systemctl_path, "is-system-running"])
            state = (system_running.get("stdout") or system_running.get("stderr") or "").strip() or "unknown"
            status = "pass" if system_running.get("ok") else ("warn" if state in {"degraded", "starting"} else "fail")
            checks.append(
                DeploymentPreflightCheck(
                    name="systemd runtime state",
                    status=status,
                    detail=f"systemd reports '{state}'.",
                    command="systemctl is-system-running",
                )
            )

        for name, enabled, binary in [
            ("MediaMTX binary", config.mediamtx_enabled, "mediamtx"),
            ("stream-failover-relay binary", config.relay_enabled, "stream-failover-relay"),
        ]:
            resolved = shutil.which(binary)
            if resolved:
                checks.append(
                    DeploymentPreflightCheck(
                        name=name,
                        status="pass",
                        detail=f"Resolved to {resolved}.",
                        command=f"command -v {binary}",
                    )
                )
            else:
                checks.append(
                    DeploymentPreflightCheck(
                        name=name,
                        status="fail" if enabled else "warn",
                        detail=(
                            f"{binary} is required for the currently enabled service."
                            if enabled
                            else f"{binary} is not installed, but the related service is disabled in the draft."
                        ),
                        command=f"command -v {binary}",
                    )
                )

        for key, target in profile.path_roots.items():
            exists = Path(target).exists()
            writable = Path(target).exists() and Path(target).is_dir() and os.access(target, os.W_OK)
            if writable:
                status = "pass"
                detail = f"{target} already exists and is writable by the current process."
            elif sudo_probe.get("ok"):
                status = "pass"
                detail = f"{target} will be created or managed locally via sudo."
            else:
                status = "fail"
                detail = f"{target} needs elevated local write access."
            checks.append(
                DeploymentPreflightCheck(
                    name=f"Host path: {key}",
                    status=status,
                    detail=detail,
                    command=f"test -d {target}",
                )
            )

        previous_bundle = self._previous_applied_bundle(profile.id)
        checks.append(
            DeploymentPreflightCheck(
                name="Rollback source available",
                status="pass" if previous_bundle else "warn",
                detail=(
                    f"Previous applied bundle available at {previous_bundle}."
                    if previous_bundle
                    else "No earlier applied local bundle exists yet; the first true apply will not have a rollback target."
                ),
            )
        )

        env_live = Path(profile.path_roots["config_dir"]) / "streamterminal-relay.env"
        env_report = self._inspect_live_env_file(env_live)
        env_status = "pass"
        if not env_report["exists"]:
            env_status = "fail" if config.relay_enabled else "pass"
            env_detail = (
                f"{env_live} does not exist yet. A true apply can seed it from the example file, but automatic relay activation will fail until you add real local values."
                if config.relay_enabled
                else f"{env_live} does not exist yet, but relay service is disabled in the draft."
            )
        elif env_report["error"]:
            env_status = "fail" if config.relay_enabled else "warn"
            env_detail = f"{env_live} exists but could not be read for validation: {env_report['error']}"
        elif env_report["missing_keys"]:
            env_status = "fail" if config.relay_enabled else "warn"
            env_detail = f"{env_live} is missing required keys: {', '.join(env_report['missing_keys'])}."
        elif env_report["placeholder_keys"]:
            env_status = "fail" if config.relay_enabled else "warn"
            env_detail = f"{env_live} still contains placeholder values for: {', '.join(env_report['placeholder_keys'])}."
        else:
            env_detail = f"{env_live} contains the required relay variables and no placeholder markers were detected."
        checks.append(
            DeploymentPreflightCheck(
                name="Live relay env readiness",
                status=env_status,
                detail=env_detail,
                command=f"test -f {env_live}",
            )
        )

        pass_count = sum(1 for check in checks if check.status == "pass")
        warn_count = sum(1 for check in checks if check.status == "warn")
        fail_count = sum(1 for check in checks if check.status == "fail")
        return DeploymentPreflightResponse(
            profile=profile,
            generated_at=datetime.now(UTC).isoformat(),
            latest_revision=latest_revision,
            summary=DeploymentPreflightSummary(
                ok=fail_count == 0,
                pass_count=pass_count,
                warn_count=warn_count,
                fail_count=fail_count,
            ),
            checks=checks,
            warnings=self._deployment_warnings(config),
        )

    def deployment_audit(
        self,
        config: RelayConfig,
        profile_id: str,
        latest_revision: Any | None = None,
    ) -> DeploymentAuditResponse:
        plan = self.deployment_plan(config, profile_id, latest_revision)
        previous_bundle = self._latest_bundle_dir(plan.profile.id)
        previous_manifest = self._load_bundle_manifest(previous_bundle)
        previous_map = {
            item["target_path"]: item.get("sha256")
            for item in previous_manifest.get("files", [])
        }

        audit_files: list[DeploymentAuditFile] = []
        changed = 0
        unchanged = 0
        new_files = 0
        for file in plan.files:
            sha256 = self._file_sha256(Path(file.source_path))
            previous_sha = previous_map.get(file.target_path)
            if previous_sha is None:
                status = "new"
                new_files += 1
            elif previous_sha != sha256:
                status = "changed"
                changed += 1
            else:
                status = "unchanged"
                unchanged += 1
            audit_files.append(
                DeploymentAuditFile(
                    name=file.name,
                    target_path=file.target_path,
                    bytes=file.bytes,
                    sha256=sha256,
                    previous_sha256=previous_sha,
                    changed=status != "unchanged",
                    status=status,
                )
            )

        return DeploymentAuditResponse(
            profile=plan.profile,
            generated_at=datetime.now(UTC).isoformat(),
            latest_revision=latest_revision,
            compared_bundle=str(previous_bundle) if previous_bundle else None,
            summary=DeploymentAuditSummary(
                total_files=len(audit_files),
                changed_files=changed,
                unchanged_files=unchanged,
                new_files=new_files,
            ),
            files=audit_files,
        )

    def execute_deployment_bundle(
        self,
        config: RelayConfig,
        profile_id: str,
        execute: bool,
        latest_revision: Any | None = None,
        action: str | None = None,
    ) -> DeployExecuteResponse:
        selected_action = self._resolve_deployment_action(action=action, execute=execute)
        plan = self.deployment_plan(config, profile_id, latest_revision)
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
        bundle_dir = self.bundle_root / f"{timestamp}-{plan.profile.id}"

        if selected_action == "preview":
            return DeployExecuteResponse(
                ok=True,
                executed=False,
                mode="preview",
                profile=plan.profile,
                bundle_root=str(bundle_dir),
                host_touched=False,
                files_created=[],
                steps=[
                    DeploymentExecutionStep(
                        label="Preview true local apply",
                        status="preview",
                        detail=f"Would write host files and manage local services from bundle {bundle_dir}.",
                    ),
                    DeploymentExecutionStep(
                        label="Review env handling",
                        status="preview",
                        detail="Would preserve an existing live env file and only seed it from the example when missing.",
                    ),
                ],
                warnings=plan.warnings,
                next_actions=self._next_actions("preview", ok=True),
            )

        if selected_action == "rollback":
            source_bundle = self._previous_applied_bundle(plan.profile.id)
            if not source_bundle:
                raise ValueError("No previous applied local bundle is available for rollback.")
            source_manifest = self._load_bundle_manifest(source_bundle)
            source_config = RelayConfig.model_validate(source_manifest.get("config") or config.model_dump(mode="json"))
            plan = self.deployment_plan(source_config, profile_id, latest_revision)
            bundle_dir.mkdir(parents=True, exist_ok=True)
            files_created, bundle_steps, manifest_files = self._copy_bundle_rootfs(plan, bundle_dir, source_bundle)
            host_steps, ok = self._apply_bundle_to_host(plan, bundle_dir, source_config)
            files_created.extend(self._write_bundle_metadata(
                plan=plan,
                bundle_dir=bundle_dir,
                files=manifest_files,
                mode="rollback",
                config_snapshot=source_config,
                source_bundle=source_bundle,
                host_touched=True,
                success=ok,
            ))
            return DeployExecuteResponse(
                ok=ok,
                executed=True,
                mode="rollback",
                profile=plan.profile,
                bundle_root=str(bundle_dir),
                host_touched=True,
                files_created=files_created,
                steps=bundle_steps + host_steps,
                warnings=plan.warnings,
                next_actions=self._next_actions("rollback", ok=ok),
            )

        bundle_dir.mkdir(parents=True, exist_ok=True)
        files_created, bundle_steps, manifest_files = self._write_bundle_rootfs(plan, bundle_dir)
        files_created.extend(self._write_bundle_metadata(
            plan=plan,
            bundle_dir=bundle_dir,
            files=manifest_files,
            mode=selected_action,
            config_snapshot=config,
            host_touched=selected_action == "apply",
            success=selected_action != "apply",
        ))

        if selected_action == "bundle":
            return DeployExecuteResponse(
                ok=True,
                executed=True,
                mode="bundle",
                profile=plan.profile,
                bundle_root=str(bundle_dir),
                host_touched=False,
                files_created=files_created,
                steps=bundle_steps,
                warnings=plan.warnings,
                next_actions=self._next_actions("bundle", ok=True),
            )

        host_steps, ok = self._apply_bundle_to_host(plan, bundle_dir, config)
        self._update_bundle_manifest(bundle_dir, host_touched=True, success=ok)
        return DeployExecuteResponse(
            ok=ok,
            executed=True,
            mode="apply",
            profile=plan.profile,
            bundle_root=str(bundle_dir),
            host_touched=True,
            files_created=files_created,
            steps=bundle_steps + host_steps,
            warnings=plan.warnings,
            next_actions=self._next_actions("apply", ok=ok),
        )

    def host_snapshot(self) -> dict[str, Any]:
        tools = {
            "mediamtx": ["mediamtx", "--version"],
            "stream-failover-relay": ["stream-failover-relay", "--help"],
            "ffmpeg": ["ffmpeg", "-version"],
            "ffprobe": ["ffprobe", "-version"],
            "journalctl": ["journalctl", "--version"],
            "systemctl": ["systemctl", "--version"],
            "sudo": ["sudo", "--version"],
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

    def _resolve_deployment_action(self, action: str | None, execute: bool) -> str:
        if action:
            return action
        return "bundle" if execute else "preview"

    def _write_bundle_rootfs(
        self,
        plan: DeploymentPlanResponse,
        bundle_dir: Path,
    ) -> tuple[list[str], list[DeploymentExecutionStep], list[dict[str, Any]]]:
        rootfs_dir = bundle_dir / "rootfs"
        rootfs_dir.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        steps: list[DeploymentExecutionStep] = []
        manifest_files: list[dict[str, Any]] = []
        for file in plan.files:
            target = rootfs_dir / file.target_path.lstrip("/")
            target.parent.mkdir(parents=True, exist_ok=True)
            source = Path(file.source_path)
            target.write_text(source.read_text())
            if target.suffix == ".sh":
                target.chmod(0o755)
            files_created.append(str(target))
            manifest_files.append(
                {
                    "name": file.name,
                    "source_path": file.source_path,
                    "bundle_path": str(target),
                    "target_path": file.target_path,
                    "bytes": file.bytes,
                    "sha256": self._file_sha256(target),
                }
            )
            steps.append(
                DeploymentExecutionStep(
                    label=f"Bundle {file.name}",
                    status="created",
                    detail=f"Created {target}",
                )
            )
        return files_created, steps, manifest_files

    def _copy_bundle_rootfs(
        self,
        plan: DeploymentPlanResponse,
        bundle_dir: Path,
        source_bundle: Path,
    ) -> tuple[list[str], list[DeploymentExecutionStep], list[dict[str, Any]]]:
        rootfs_dir = bundle_dir / "rootfs"
        rootfs_dir.mkdir(parents=True, exist_ok=True)
        files_created: list[str] = []
        steps: list[DeploymentExecutionStep] = []
        manifest_files: list[dict[str, Any]] = []
        for file in plan.files:
            source = source_bundle / "rootfs" / file.target_path.lstrip("/")
            target = rootfs_dir / file.target_path.lstrip("/")
            if not source.exists():
                raise ValueError(f"Rollback bundle is missing {source}")
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(source.read_text())
            if target.suffix == ".sh":
                target.chmod(0o755)
            files_created.append(str(target))
            manifest_files.append(
                {
                    "name": file.name,
                    "source_path": str(source),
                    "bundle_path": str(target),
                    "target_path": file.target_path,
                    "bytes": target.stat().st_size,
                    "sha256": self._file_sha256(target),
                }
            )
            steps.append(
                DeploymentExecutionStep(
                    label=f"Seed rollback bundle {file.name}",
                    status="created",
                    detail=f"Copied {source} to {target}",
                )
            )
        return files_created, steps, manifest_files

    def _write_bundle_metadata(
        self,
        plan: DeploymentPlanResponse,
        bundle_dir: Path,
        files: list[dict[str, Any]],
        mode: str,
        config_snapshot: RelayConfig,
        *,
        source_bundle: Path | None = None,
        host_touched: bool = False,
        success: bool = True,
    ) -> list[str]:
        files_created: list[str] = []
        commands_script = bundle_dir / "commands-preview.sh"
        commands_script.write_text(self._commands_preview_script(plan))
        commands_script.chmod(0o755)
        files_created.append(str(commands_script))

        secret_report = bundle_dir / "secret-template-report.json"
        secret_report.write_text(json.dumps([item.model_dump(mode="json") for item in plan.secret_templates], indent=2))
        files_created.append(str(secret_report))

        manifest = self._bundle_manifest_path(bundle_dir)
        manifest.write_text(
            json.dumps(
                {
                    "profile_id": plan.profile.id,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "mode": mode,
                    "host_touched": host_touched,
                    "success": success,
                    "source_bundle": str(source_bundle) if source_bundle else None,
                    "config": config_snapshot.model_dump(mode="json"),
                    "files": files,
                },
                indent=2,
            )
        )
        files_created.append(str(manifest))

        bundle_readme = bundle_dir / "README.txt"
        bundle_readme.write_text(self._bundle_readme(plan))
        files_created.append(str(bundle_readme))
        return files_created

    def _update_bundle_manifest(self, bundle_dir: Path, *, host_touched: bool, success: bool) -> None:
        manifest = self._bundle_manifest_path(bundle_dir)
        payload = json.loads(manifest.read_text())
        payload["host_touched"] = host_touched
        payload["success"] = success
        manifest.write_text(json.dumps(payload, indent=2))

    def _apply_bundle_to_host(
        self,
        plan: DeploymentPlanResponse,
        bundle_dir: Path,
        config: RelayConfig,
    ) -> tuple[list[DeploymentExecutionStep], bool]:
        profile = plan.profile
        rootfs_dir = bundle_dir / "rootfs"
        systemctl = shutil.which("systemctl") or "systemctl"
        steps: list[DeploymentExecutionStep] = []
        ok = True

        mkdir_command = ["sudo", "-n", "mkdir", "-p", profile.path_roots["config_dir"], profile.path_roots["bin_dir"], profile.path_roots["systemd_dir"]]
        result = self._run_command(mkdir_command)
        steps.append(self._command_step("Create local target directories", mkdir_command, result))
        ok = ok and result.get("ok", False)

        for file in plan.files:
            source = rootfs_dir / file.target_path.lstrip("/")
            mode = "0755" if file.name.endswith(".sh") else "0644"
            command = ["sudo", "-n", "install", "-m", mode, str(source), file.target_path]
            result = self._run_command(command)
            steps.append(self._command_step(f"Install {file.name}", command, result))
            ok = ok and result.get("ok", False)

        env_example = profile.path_roots["config_dir"] + "/streamterminal-relay.env.example"
        env_live = profile.path_roots["config_dir"] + "/streamterminal-relay.env"
        env_check = self._run_command(["sudo", "-n", "test", "-f", env_live])
        if env_check.get("ok"):
            steps.append(
                DeploymentExecutionStep(
                    label="Preserve live env file",
                    status="skipped",
                    detail=f"Left existing {env_live} untouched.",
                )
            )
        else:
            copy_result = self._run_command(["sudo", "-n", "cp", env_example, env_live])
            steps.append(self._command_step("Seed live env file from example", ["sudo", "-n", "cp", env_example, env_live], copy_result))
            ok = ok and copy_result.get("ok", False)
            chmod_result = self._run_command(["sudo", "-n", "chmod", "600", env_live])
            steps.append(self._command_step("Lock down live env file permissions", ["sudo", "-n", "chmod", "600", env_live], chmod_result))
            ok = ok and chmod_result.get("ok", False)

        env_report = self._inspect_live_env_file(Path(env_live))
        relay_env_ready = env_report["exists"] and env_report["readable"] and not env_report["missing_keys"] and not env_report["placeholder_keys"]
        if relay_env_ready:
            steps.append(
                DeploymentExecutionStep(
                    label="Verify live relay env",
                    status="executed",
                    detail=f"{env_live} contains the required relay variables with non-placeholder values.",
                )
            )
        else:
            problems: list[str] = []
            if not env_report["exists"]:
                problems.append("file missing")
            if env_report["error"]:
                problems.append(f"read failed: {env_report['error']}")
            if env_report["missing_keys"]:
                problems.append(f"missing keys: {', '.join(env_report['missing_keys'])}")
            if env_report["placeholder_keys"]:
                problems.append(f"placeholder values: {', '.join(env_report['placeholder_keys'])}")
            steps.append(
                DeploymentExecutionStep(
                    label="Verify live relay env",
                    status="failed",
                    detail=f"{env_live} is not ready for automatic relay start ({'; '.join(problems)}). Edit the live env file locally, then restart stream-failover-relay.service.",
                )
            )
            ok = False

        daemon_reload = ["sudo", "-n", systemctl, "daemon-reload"]
        daemon_result = self._run_command(daemon_reload)
        steps.append(self._command_step("Reload systemd", daemon_reload, daemon_result))
        ok = ok and daemon_result.get("ok", False)

        for service_name, unit_name, enabled in [
            ("mediamtx", self.SERVICE_UNIT_MAP["mediamtx"], config.mediamtx_enabled),
            ("stream-failover-relay", self.SERVICE_UNIT_MAP["stream-failover-relay"], config.relay_enabled and relay_env_ready),
        ]:
            command = ["sudo", "-n", systemctl, "enable", "--now", unit_name] if enabled else ["sudo", "-n", systemctl, "disable", "--now", unit_name]
            result = self._run_command(command)
            steps.append(self._command_step(("Enable and start" if enabled else "Disable and stop") + f" {service_name}", command, result))
            ok = ok and result.get("ok", False)

            show_command = [systemctl, "show", unit_name, "--property=ActiveState,UnitFileState,SubState,ExecMainStatus,NRestarts", "--no-pager"]
            show_result = self._run_command(show_command)
            state = self._parse_systemctl_show(show_result.get("stdout", ""))
            service_ok = False
            if enabled:
                service_ok = state.get("ActiveState") == "active" and state.get("SubState") == "running"
            else:
                service_ok = state.get("ActiveState") in {"inactive", "failed", "unknown", None} and state.get("UnitFileState") != "enabled"
            detail = (
                f"ActiveState={state.get('ActiveState', 'unknown')}, "
                f"SubState={state.get('SubState', 'unknown')}, "
                f"UnitFileState={state.get('UnitFileState', 'unknown')}, "
                f"ExecMainStatus={state.get('ExecMainStatus', 'unknown')}, "
                f"NRestarts={state.get('NRestarts', 'unknown')}"
            )
            steps.append(
                DeploymentExecutionStep(
                    label=f"Verify {service_name} state",
                    status="executed" if service_ok else "failed",
                    detail=detail,
                )
            )
            ok = ok and service_ok and show_result.get("ok", False)

        if config.mediamtx_enabled:
            listen_check = self._verify_listen_port(self.DEFAULT_RTMP_LISTEN_PORT)
            if listen_check["ok"]:
                listeners_text = ", ".join(listen_check["listeners"]) or "(none reported)"
                listen_detail = f"mediamtx is listening on :{listen_check['port']} ({listeners_text})."
            else:
                listen_detail = (
                    f"mediamtx is not listening on :{listen_check['port']} after apply. "
                    "Check the mediamtx.service journal for bind failures or port conflicts."
                )
            steps.append(
                DeploymentExecutionStep(
                    label="Verify mediamtx network listener",
                    status="executed" if listen_check["ok"] else "failed",
                    detail=listen_detail,
                )
            )
            ok = ok and listen_check["ok"]

        return steps, ok

    def _command_step(self, label: str, command: list[str], result: dict[str, Any]) -> DeploymentExecutionStep:
        output = (result.get("stdout") or result.get("stderr") or "").strip()
        if output:
            output = " | ".join(output.splitlines()[:3])
        detail = f"$ {' '.join(command)}"
        if output:
            detail += f" -> {output}"
        return DeploymentExecutionStep(
            label=label,
            status="executed" if result.get("ok") else "failed",
            detail=detail,
        )

    @staticmethod
    def _parse_systemctl_show(output: str) -> dict[str, str]:
        parsed: dict[str, str] = {}
        for line in output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                parsed[key] = value
        return parsed

    DEFAULT_RTMP_LISTEN_PORT = 1935

    def _verify_listen_port(self, port: int) -> dict[str, Any]:
        """Return a dict describing whether `port` is listening on the local host.

        Tries `ss` first, then `netstat`, then a direct `socket.connect_ex` probe.
        Each listener is reported with the full `Local Address:Port` so the operator
        can tell IPv4 from IPv6, wildcard from specific, etc.
        """
        listeners: list[str] = []
        probe_command: list[str] | None = None
        probe_stdout = ""
        ss_path = shutil.which("ss")
        if ss_path:
            probe_command = [ss_path, "-ltn"]
            result = self._run_command(probe_command)
            probe_stdout = result.get("stdout", "")
            if result.get("ok"):
                listeners.extend(self._parse_listen_lines(probe_stdout, port=port, format_hint="ss"))
        if not listeners and shutil.which("netstat"):
            netstat_path = shutil.which("netstat") or "netstat"
            probe_command = [netstat_path, "-ltn"]
            result = self._run_command(probe_command)
            probe_stdout = result.get("stdout", "")
            if result.get("ok"):
                listeners.extend(self._parse_listen_lines(probe_stdout, port=port, format_hint="netstat"))
        if not listeners and probe_command is None:
            # No ss / netstat; fall back to a direct TCP probe. This only tells us
            # "something is listening" or "nothing is listening" without IPv4/IPv6 detail.
            try:
                import socket

                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                    sock.settimeout(1.0)
                    if sock.connect_ex(("127.0.0.1", port)) == 0:
                        listeners.append(f"127.0.0.1:{port}")
            except OSError:
                pass
        return {
            "port": port,
            "ok": bool(listeners),
            "listeners": listeners,
            "probe_command": probe_command,
        }

    @staticmethod
    def _parse_listen_lines(output: str, *, port: int, format_hint: str) -> list[str]:
        """Pull `Local Address:Port` lines for a given port from `ss -ltn` or `netstat -ltn`.

        Matches the well-known shapes:
            ss:      `LISTEN 0 4096 0.0.0.0:1935 0.0.0.0:*`
                     `LISTEN 0 4096 *:1935 *:*`
                     `LISTEN 0 4096 [::]:1935 [::]:*`
            netstat: `tcp 0 0 0.0.0.0:1935 0.0.0.0:* LISTEN`
                     `tcp6 0 0 [::]:1935 [::]:* LISTEN`

        The local-address column is the 4th whitespace-separated token in both
        `ss -ltn` and `netstat -ltn` output. We only consider that column to
        avoid picking up peer addresses that also contain a port.
        """
        if not output:
            return []
        matched: list[str] = []
        for raw in output.splitlines():
            line = raw.strip()
            if not line:
                continue
            if line.startswith(("State", "Proto", "Active", "Recv-Q", "Local", "Address")):
                continue
            tokens = line.split()
            if len(tokens) < 4:
                continue
            local_token = tokens[3]
            # Strip the wildcard v4-mapped form that `netstat` sometimes prints.
            if local_token.endswith(f":{port}"):
                matched.append(local_token)
        return matched

    def _inspect_live_env_file(self, path: Path) -> dict[str, Any]:
        report: dict[str, Any] = {
            "exists": path.exists(),
            "readable": False,
            "missing_keys": [],
            "placeholder_keys": [],
            "error": None,
        }
        if not path.exists():
            return report

        try:
            payload = path.read_text()
        except PermissionError:
            result = self._run_command(["sudo", "-n", "cat", str(path)])
            if not result.get("ok"):
                report["error"] = result.get("stderr") or result.get("stdout") or "permission denied"
                return report
            payload = result.get("stdout", "")
        except OSError as exc:
            report["error"] = str(exc)
            return report

        report["readable"] = True
        values: dict[str, str] = {}
        for line in payload.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key.strip()] = value.strip().strip("\"'")

        report["missing_keys"] = [key for key in self.REQUIRED_ENV_KEYS if not values.get(key)]
        report["placeholder_keys"] = [
            key
            for key in self.REQUIRED_ENV_KEYS
            if self._looks_placeholder_value(values.get(key, ""))
        ]
        return report

    @staticmethod
    def _looks_placeholder_value(value: str) -> bool:
        normalized = value.strip()
        if not normalized:
            return True
        return bool(re.search(r"(^REPLACE_WITH_|placeholder|example\.invalid)", normalized, re.IGNORECASE))

    def _applied_bundle_dirs(self, profile_id: str) -> list[Path]:
        applied: list[Path] = []
        for bundle_dir in sorted(self.bundle_root.glob(f"*-{profile_id}")):
            manifest = self._load_bundle_manifest(bundle_dir)
            if manifest.get("mode") in {"apply", "rollback"} and manifest.get("host_touched") and manifest.get("success"):
                applied.append(bundle_dir)
        return applied

    def _previous_applied_bundle(self, profile_id: str) -> Path | None:
        bundles = self._applied_bundle_dirs(profile_id)
        if len(bundles) < 2:
            return None
        return bundles[-2]

    @staticmethod
    def _bundle_manifest_path(bundle_dir: Path) -> Path:
        return bundle_dir / "deploy-manifest.json"

    def _deployment_commands(self, profile: DeploymentProfile, files: list[DeploymentPlannedFile], config: RelayConfig) -> list[DeploymentCommand]:
        config_dir = profile.path_roots["config_dir"]
        env_example = f"{config_dir}/streamterminal-relay.env.example"
        env_live = f"{config_dir}/streamterminal-relay.env"
        mkdirs = " ".join(self._shell_escape(profile.path_roots[key]) for key in ["config_dir", "bin_dir", "systemd_dir"])
        commands: list[DeploymentCommand] = [
            DeploymentCommand(
                phase="prepare",
                label="Create local target directories",
                run_on="local",
                command=f"sudo mkdir -p {mkdirs}",
            )
        ]
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
                    label="Seed live env file only when missing",
                    run_on="local",
                    command=f"if [ ! -f {self._shell_escape(env_live)} ]; then sudo cp {self._shell_escape(env_example)} {self._shell_escape(env_live)} && sudo chmod 600 {self._shell_escape(env_live)}; fi",
                ),
                DeploymentCommand(
                    phase="activate",
                    label="Reload systemd",
                    run_on="local",
                    command="sudo systemctl daemon-reload",
                ),
                DeploymentCommand(
                    phase="activate",
                    label=("Enable and start mediamtx" if config.mediamtx_enabled else "Disable and stop mediamtx"),
                    run_on="local",
                    command=("sudo systemctl enable --now mediamtx.service" if config.mediamtx_enabled else "sudo systemctl disable --now mediamtx.service"),
                ),
                DeploymentCommand(
                    phase="activate",
                    label=("Enable and start stream-failover-relay" if config.relay_enabled else "Disable and stop stream-failover-relay"),
                    run_on="local",
                    command=("sudo systemctl enable --now stream-failover-relay.service" if config.relay_enabled else "sudo systemctl disable --now stream-failover-relay.service"),
                ),
                DeploymentCommand(
                    phase="verify",
                    label="Check local service state",
                    run_on="local",
                    command="systemctl show mediamtx.service stream-failover-relay.service --property=ActiveState,UnitFileState,SubState --no-pager",
                ),
            ]
        )
        return commands

    def _deployment_warnings(self, config: RelayConfig) -> list[str]:
        warnings: list[str] = []
        if self._looks_sensitive_url(config.output.url):
            warnings.append("Output URL appears sensitive; keep the live output destination only in the on-host env file.")
        if config.primary_input.protocol != config.backup_input.protocol:
            warnings.append("Mixed primary/backup protocols remain a failover risk and may need additional normalization.")
        if not config.auto_restart:
            warnings.append("Auto-restart is disabled in the draft; review whether local systemd restart behavior should remain enabled.")
        return warnings

    def _commands_preview_script(self, plan: DeploymentPlanResponse) -> str:
        lines = ["#!/usr/bin/env bash", "set -euo pipefail", "", "# Local install preview only. Review each command before running with sudo on this host."]
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
                "This bundle is local-only. It does NOT connect to any remote host.",
                "Review commands-preview.sh before running anything manually with sudo on this machine.",
                "",
                "Secret/env handling:",
                f"- Example file: {secret.example_path}",
                f"- Live file:    {secret.live_path}",
                "- Copy the example to the live path locally and replace placeholders there.",
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

    def _next_actions(self, mode: str, ok: bool) -> list[str]:
        if mode == "preview":
            return [
                "Run local preflight before attempting a true host apply.",
                "Inspect the planned bundle location and generated file map.",
                "Review env handling so real stream URLs stay only in the on-host env file.",
            ]
        if mode == "bundle":
            return [
                "Inspect the generated bundle under apps/api/data/runtime/deploy-bundles/.",
                "Use it for audit/review or as a manual fallback package for this same host.",
                "Run local preflight before switching from bundle generation to true apply.",
            ]
        if mode == "apply":
            if ok:
                return [
                    "Inspect /etc/streamterminal-relay-matrix and /etc/systemd/system on this host.",
                    "Verify the live env file contains real local secrets and stream URLs.",
                    "Review service logs from the diagnostics page if you need post-apply validation.",
                ]
            return [
                "Read the failed execution steps to see which local sudo or systemd command broke.",
                "Run local preflight and confirm required binaries are installed on this machine.",
                "Use local rollback after fixing prerequisites if the current host state needs to be reverted.",
            ]
        return [
            "Confirm the restored host files match the previous known-good local bundle.",
            "Check service state and logs on this machine after rollback.",
            "Re-run audit/preflight before attempting another true apply.",
        ]

    def _latest_bundle_dir(self, profile_id: str) -> Path | None:
        candidates = sorted(self.bundle_root.glob(f"*-{profile_id}"))
        return candidates[-1] if candidates else None

    def _load_bundle_manifest(self, bundle_dir: Path | None) -> dict[str, Any]:
        if bundle_dir is None:
            return {}
        manifest = bundle_dir / "deploy-manifest.json"
        if not manifest.exists():
            return {}
        return json.loads(manifest.read_text())

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
            completed = subprocess.run(
                [systemctl, "show", unit_name, "--property=LoadState,ActiveState,SubState,UnitFileState", "--no-pager"],
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
    def _file_sha256(path: Path) -> str:
        return hashlib.sha256(path.read_bytes()).hexdigest()

    @staticmethod
    def _shell_escape(value: str) -> str:
        return "'" + value.replace("'", "'\\''") + "'"

    @staticmethod
    def _systemd_escape(value: str) -> str:
        return '"' + value.replace('"', '\\"') + '"'

    @staticmethod
    def _path_name(endpoint: Any, fallback: str) -> str:
        parsed = urlparse(endpoint.url)
        path = parsed.path.strip("/")
        return path or fallback

    @staticmethod
    def _rtmp_listen_address(config: RelayConfig) -> str:
        parsed = urlparse(config.primary_input.url)
        port = parsed.port
        if parsed.scheme == "rtmp" and port is None:
            port = 1935
        return f":{port}" if port else ":1935"

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
