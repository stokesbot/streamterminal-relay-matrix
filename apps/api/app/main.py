from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .runtime import RuntimeAdapter
from .schemas import (
    ApplyResult,
    DeployExecuteRequest,
    DeployExecuteResponse,
    DeploymentAuditResponse,
    DeploymentPlanResponse,
    DeploymentPreflightResponse,
    DeploymentProfile,
    DiagnosticsResponse,
    HostSnapshotListResponse,
    HostSnapshotRestoreRequest,
    HostSnapshotSummary,
    InstallResult,
    RelayConfig,
    RuntimeStatus,
    ServiceActionRequest,
    ServiceActionResult,
    ServiceLogsResponse,
    ServiceStatus,
    SmokeResponse,
    ValidationIssue,
    ValidationResult,
)
from .storage import ConfigStore

settings = get_settings()
store = ConfigStore(settings.data_dir)
runtime = RuntimeAdapter(store.runtime_dir)


def validate_config(config: RelayConfig) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if config.primary_input.url == config.backup_input.url:
        issues.append(ValidationIssue(level="warning", message="Primary and backup input URLs are identical."))
    if config.output.protocol != "rtmp":
        issues.append(ValidationIssue(level="info", message="Only RTMP output has been validated in the current live test stack."))
    if not config.primary_input.enabled and not config.backup_input.enabled:
        issues.append(ValidationIssue(level="error", message="At least one input must be enabled."))
    if not config.output.enabled:
        issues.append(ValidationIssue(level="error", message="Output must be enabled."))
    if config.primary_input.protocol != config.backup_input.protocol:
        issues.append(ValidationIssue(level="warning", message="Primary and backup protocols differ. Real failover may need extra normalization logic."))
    if not config.output.url.startswith(("rtmp://", "srt://", "rtsp://", "udp://", "file://")):
        issues.append(ValidationIssue(level="error", message="Output URL must include a supported protocol prefix."))

    return ValidationResult(valid=not any(issue.level == "error" for issue in issues), issues=issues)


@asynccontextmanager
async def lifespan(_: FastAPI):
    store.load()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": settings.app_name}


@app.get("/api/config", response_model=RelayConfig)
def get_config() -> RelayConfig:
    return store.load()


@app.put("/api/config/draft", response_model=RelayConfig)
def put_config(config: RelayConfig) -> RelayConfig:
    return store.save(config)


@app.post("/api/config/validate", response_model=ValidationResult)
def post_validate(config: RelayConfig) -> ValidationResult:
    return validate_config(config)


@app.post("/api/config/apply", response_model=ApplyResult)
def apply_config() -> ApplyResult:
    config = store.load()
    validation = validate_config(config)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.model_dump(mode="json"))

    artifacts = runtime.write_runtime_artifacts(config)
    revision = store.create_revision(config, status="applied", note="Generated local runtime artifacts for the current draft.")
    return ApplyResult(ok=True, version=revision.version, note=revision.note, artifacts=[artifact.path for artifact in artifacts])


@app.post("/api/config/rollback", response_model=ApplyResult)
def rollback_config() -> ApplyResult:
    revisions = store.list_revisions()
    if len(revisions) < 2:
        raise HTTPException(status_code=400, detail="No previous applied revision available.")

    previous = revisions[-2]
    store.save(previous.payload)
    artifacts = runtime.write_runtime_artifacts(previous.payload)
    rollback_revision = store.mark_rollback(previous.payload, note=f"Rolled back to revision {previous.version}.")
    return ApplyResult(ok=True, version=rollback_revision.version, note=rollback_revision.note, artifacts=[artifact.path for artifact in artifacts])


@app.post("/api/runtime/install", response_model=InstallResult)
def install_runtime() -> InstallResult:
    config = store.load()
    validation = validate_config(config)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.model_dump(mode="json"))

    installed = runtime.install_artifacts(config)
    return InstallResult(ok=True, installed_to=str(runtime.install_root), artifacts=[artifact.path for artifact in installed])


@app.get("/api/deploy/profiles", response_model=list[DeploymentProfile])
def deploy_profiles() -> list[DeploymentProfile]:
    return runtime.deployment_profiles()


@app.get("/api/deploy/plan", response_model=DeploymentPlanResponse)
def deploy_plan(profile_id: str = Query(default="local-system")) -> DeploymentPlanResponse:
    config = store.load()
    validation = validate_config(config)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.model_dump(mode="json"))

    try:
        return runtime.deployment_plan(config, profile_id=profile_id, latest_revision=store.latest_revision())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/deploy/preflight", response_model=DeploymentPreflightResponse)
def deploy_preflight(profile_id: str = Query(default="local-system")) -> DeploymentPreflightResponse:
    config = store.load()
    validation = validate_config(config)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.model_dump(mode="json"))

    try:
        return runtime.deployment_preflight(config, profile_id=profile_id, latest_revision=store.latest_revision())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/deploy/audit", response_model=DeploymentAuditResponse)
def deploy_audit(profile_id: str = Query(default="local-system")) -> DeploymentAuditResponse:
    config = store.load()
    validation = validate_config(config)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.model_dump(mode="json"))

    try:
        return runtime.deployment_audit(config, profile_id=profile_id, latest_revision=store.latest_revision())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/deploy/host-snapshots", response_model=HostSnapshotListResponse)
def deploy_host_snapshots() -> HostSnapshotListResponse:
    """List all pre-apply host snapshots the runtime adapter has captured.

    Each snapshot lives under `<runtime_dir>/host-snapshots/<id>/` with a
    `manifest.json` and a `files/` mirror of the on-host relay files that
    were about to be overwritten.
    """
    snapshots = [HostSnapshotSummary.model_validate(item) for item in runtime.list_host_snapshots()]
    return HostSnapshotListResponse(
        generated_at=datetime.now(UTC).isoformat(),
        snapshots=snapshots,
    )


@app.post("/api/deploy/restore-snapshot")
def deploy_restore_snapshot(request: HostSnapshotRestoreRequest) -> dict[str, Any]:
    """Restore a captured host snapshot onto the local host.

    Always uses `sudo -n install` so the operation is auditable and never
    silently touches files outside the snapshot's recorded host_root.
    Dry-run mode (execute=False) returns the planned commands without
    running them.
    """
    if not request.execute:
        # Read-only preview: emit the plan and a list of the files that
        # would be restored, but do not touch the host.
        try:
            manifest = runtime._read_snapshot_manifest(request.snapshot_id)
        except (FileNotFoundError, ValueError) as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {
            "ok": True,
            "executed": False,
            "snapshot_id": request.snapshot_id,
            "host_root": manifest.get("host_root"),
            "files": manifest.get("files", []),
        }
    try:
        result = runtime.restore_host_snapshot(request.snapshot_id)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "executed": True,
        "snapshot_id": result["snapshot_id"],
        "host_root": result["host_root"],
        "restored": result["restored"],
    }


@app.post("/api/deploy/execute", response_model=DeployExecuteResponse)
def deploy_execute(request: DeployExecuteRequest) -> DeployExecuteResponse:
    config = store.load()
    validation = validate_config(config)
    if not validation.valid:
        raise HTTPException(status_code=400, detail=validation.model_dump(mode="json"))

    try:
        response = runtime.execute_deployment_bundle(
            config,
            profile_id=request.profile_id,
            execute=request.execute,
            latest_revision=store.latest_revision(),
            action=request.action,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    resolved_action = request.action or ("bundle" if request.execute else "preview")
    if response.ok and response.host_touched and resolved_action == "apply":
        store.create_revision(config, status="applied", note=f"Applied local deployment bundle on host via profile {request.profile_id}.")
    elif response.ok and response.host_touched and resolved_action == "rollback":
        manifest = runtime._load_bundle_manifest(Path(response.bundle_root))
        restored_config = RelayConfig.model_validate(manifest.get("config") or config.model_dump(mode="json"))
        store.save(restored_config)
        store.mark_rollback(restored_config, note=f"Rolled back local host deployment via profile {request.profile_id}.")
    return response


@app.get("/api/runtime/status", response_model=RuntimeStatus)
def runtime_status() -> RuntimeStatus:
    config = store.load()
    latest_revision = store.latest_revision()
    host = runtime.host_snapshot()
    mediamtx_tool = host["tools"]["mediamtx"]
    relay_tool = host["tools"]["stream-failover-relay"]
    status_detail = f"Draft applied in revision {latest_revision.version}" if latest_revision else "No applied revision yet"

    return RuntimeStatus(
        active_source="primary",
        primary_state="healthy" if config.primary_input.enabled else "down",
        backup_state="healthy" if config.backup_input.enabled else "down",
        output_state="connected" if config.output.enabled else "disconnected",
        services=[
            ServiceStatus(
                name="mediamtx",
                status="running" if config.mediamtx_enabled and mediamtx_tool.get("available") else "stopped",
                detail=f"{status_detail}; binary at {mediamtx_tool.get('path')}" if mediamtx_tool.get("available") else f"{status_detail}; mediamtx binary not found on host",
            ),
            ServiceStatus(
                name="stream-failover-relay",
                status="running" if config.relay_enabled and relay_tool.get("available") else "stopped",
                detail=f"Relay binary at {relay_tool.get('path')}" if relay_tool.get("available") else "Relay binary not found on host",
            ),
        ],
        recent_events=[
            "Prototype scaffold online",
            "Draft/apply/rollback path now generates runtime artifacts locally",
            "Host diagnostics now probe local runtime binaries and command availability",
            "Runtime install staging and service-control APIs are now available",
            "Deployment workflow is now local-host only",
            "Safe local bundle execution writes env-template-aware bundles without touching other machines",
            "Deployment audit compares file checksums against the latest local bundle",
        ],
    )


@app.get("/api/runtime/smoke", response_model=SmokeResponse)
def runtime_smoke() -> SmokeResponse:
    """Run a one-shot health probe of the local relay stack.

    Probes systemd state for both services, the mediamtx RTMP listener, and
    TCP reachability of the primary/backup inputs and the output destination.
    Returns a structured report suitable for the dashboard and CI.
    """
    config = store.load()
    payload = runtime.runtime_smoke(config)
    return SmokeResponse.model_validate(payload)


@app.post("/api/services/{service_name}/action", response_model=ServiceActionResult)
def service_action(service_name: str, request: ServiceActionRequest) -> ServiceActionResult:
    try:
        result = runtime.service_action(service_name, request.action, execute=request.execute)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ServiceActionResult.model_validate(result)


@app.get("/api/services/{service_name}/logs", response_model=ServiceLogsResponse)
def service_logs(service_name: str, lines: int = Query(default=50, ge=1, le=500)) -> ServiceLogsResponse:
    try:
        result = runtime.service_logs(service_name, lines=lines)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return ServiceLogsResponse.model_validate(result)


@app.get("/api/diagnostics", response_model=DiagnosticsResponse)
def diagnostics() -> DiagnosticsResponse:
    config = store.load()
    return DiagnosticsResponse(
        draft_config=config,
        latest_revision=store.latest_revision(),
        generated_artifacts=runtime.preview_artifacts(config),
        environment={
            "data_dir": settings.data_dir,
            "allowed_origins": settings.allowed_origins,
            "api_host": settings.api_host,
            "api_port": settings.api_port,
            "host": runtime.host_snapshot(),
        },
    )
