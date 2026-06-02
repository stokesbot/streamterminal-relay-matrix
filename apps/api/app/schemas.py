from typing import Literal

from pydantic import BaseModel, Field

Protocol = Literal["rtmp", "srt", "rtsp", "udp", "file"]
ConnectionMode = Literal["pull", "push", "listener", "caller"]


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
    level: Literal["info", "warning", "error"]
    message: str


class ValidationResult(BaseModel):
    valid: bool
    issues: list[ValidationIssue] = []


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
    recent_events: list[str] = []
