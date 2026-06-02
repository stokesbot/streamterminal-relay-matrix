from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .schemas import RelayConfig, RuntimeStatus, ServiceStatus, ValidationIssue, ValidationResult
from .storage import ConfigStore

settings = get_settings()
store = ConfigStore(settings.data_dir)


def validate_config(config: RelayConfig) -> ValidationResult:
    issues: list[ValidationIssue] = []

    if config.primary_input.url == config.backup_input.url:
        issues.append(
            ValidationIssue(
                level="warning",
                message="Primary and backup input URLs are identical.",
            )
        )

    if config.output.protocol != "rtmp":
        issues.append(
            ValidationIssue(
                level="info",
                message="Only RTMP output has been validated in the current live test stack.",
            )
        )

    if not config.primary_input.enabled and not config.backup_input.enabled:
        issues.append(
            ValidationIssue(
                level="error",
                message="At least one input must be enabled.",
            )
        )

    if not config.output.enabled:
        issues.append(
            ValidationIssue(
                level="error",
                message="Output must be enabled.",
            )
        )

    return ValidationResult(
        valid=not any(issue.level == "error" for issue in issues),
        issues=issues,
    )


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


@app.get("/api/runtime/status", response_model=RuntimeStatus)
def runtime_status() -> RuntimeStatus:
    config = store.load()

    return RuntimeStatus(
        active_source="primary",
        primary_state="healthy" if config.primary_input.enabled else "down",
        backup_state="healthy" if config.backup_input.enabled else "down",
        output_state="connected" if config.output.enabled else "disconnected",
        services=[
            ServiceStatus(
                name="mediamtx",
                status="running" if config.mediamtx_enabled else "stopped",
                detail="Prototype status stub",
            ),
            ServiceStatus(
                name="stream-failover-relay",
                status="running" if config.relay_enabled else "stopped",
                detail="Prototype status stub",
            ),
        ],
        recent_events=[
            "Initial scaffold online",
            "Runtime integration will replace these mocked events in the next phase",
        ],
    )
