from typing import Any, Literal

from pydantic import BaseModel, Field

Protocol = Literal["rtmp", "srt", "rtsp", "udp", "file"]
ConnectionMode = Literal["pull", "push", "listener", "caller"]
IssueLevel = Literal["info", "warning", "error"]
ServiceName = Literal["mediamtx", "stream-failover-relay"]
ServiceAction = Literal["start", "stop", "restart", "reload", "status", "daemon-reload"]
DeploymentProfileId = Literal["local-dev", "staging-vm", "production-vm"]
DeploymentRunOn = Literal["local", "remote"]
DeploymentPhase = Literal["prepare", "copy", "activate", "verify"]


class StreamEndpoint(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    protocol: Protocol = "rtmp"
    url: str = Field(min_length=1)
    mode: ConnectionMode = "pull"
    enabled: bool = True


class RelayConfig(BaseModel):
    channel_name: str = Field(default="default", min_length=1, max_length=128)
    mediamtx_enabled: bool = True
    relay_enabled: bool = True
    auto_restart: bool = True
    primary_input: StreamEndpoint
    backup_input: StreamEndpoint
    output: StreamEndpoint


class ValidationIssue(BaseModel):
    level: IssueLevel
    message: str


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = Field(default_factory=list)


class ServiceStatus(BaseModel):
    name: str
    status: Literal["running", "stopped", "unknown"]
    detail: str


class RuntimeStatus(BaseModel):
    active_source: Literal["primary", "backup", "unknown"] = "unknown"
    primary_state: Literal["healthy", "down", "unknown"] = "unknown"
    backup_state: Literal["healthy", "down", "unknown"] = "unknown"
    output_state: Literal["connected", "disconnected", "unknown"] = "unknown"
    services: list[ServiceStatus]
    recent_events: list[str] = Field(default_factory=list)


class ConfigRevision(BaseModel):
    version: int
    status: Literal["draft", "applied", "rolled_back"]
    payload: RelayConfig
    created_at: str
    note: str


class ApplyResult(BaseModel):
    ok: bool
    version: int
    note: str
    artifacts: list[str] = Field(default_factory=list)


class GeneratedArtifact(BaseModel):
    name: str
    path: str
    content: str


class InstallResult(BaseModel):
    ok: bool
    installed_to: str
    artifacts: list[str] = Field(default_factory=list)


class ServiceActionRequest(BaseModel):
    action: ServiceAction
    execute: bool = False


class ServiceActionResult(BaseModel):
    ok: bool
    executed: bool
    service: ServiceName
    unit: str
    action: ServiceAction
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    exit_code: int = 0


class ServiceLogsResponse(BaseModel):
    service: ServiceName
    unit: str
    available: bool
    detail: str
    command: list[str] | None = None
    exit_code: int | None = None
    lines: list[str] = Field(default_factory=list)


class DeploymentProfile(BaseModel):
    id: DeploymentProfileId
    label: str
    description: str
    run_on: DeploymentRunOn
    target_host: str
    target_user: str
    path_roots: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    secret_placeholders: list[str] = Field(default_factory=list)


class DeploymentCommand(BaseModel):
    phase: DeploymentPhase
    label: str
    run_on: DeploymentRunOn
    command: str


class DeploymentPlannedFile(BaseModel):
    name: str
    source_path: str
    target_path: str
    bytes: int
    exists_in_stage: bool
    preview: str


class DeploymentPlanResponse(BaseModel):
    profile: DeploymentProfile
    staged_root: str
    generated_at: str
    latest_revision: ConfigRevision | None = None
    files: list[DeploymentPlannedFile] = Field(default_factory=list)
    commands: list[DeploymentCommand] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class DiagnosticsResponse(BaseModel):
    draft_config: RelayConfig
    latest_revision: ConfigRevision | None = None
    generated_artifacts: list[GeneratedArtifact] = Field(default_factory=list)
    environment: dict[str, Any] = Field(default_factory=dict)
