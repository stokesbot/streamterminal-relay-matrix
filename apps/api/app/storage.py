import json
from datetime import UTC, datetime
from pathlib import Path

from .schemas import ConfigRevision, RelayConfig

DEFAULT_CONFIG = RelayConfig(
    channel_name="IBM VS Failover",
    mediamtx_enabled=True,
    relay_enabled=True,
    auto_restart=True,
    primary_input={
        "label": "Primary",
        "protocol": "rtmp",
        "url": "rtmp://localhost:1935/live/main",
        "mode": "pull",
        "enabled": True,
    },
    backup_input={
        "label": "Backup",
        "protocol": "rtmp",
        "url": "rtmp://localhost:1935/live/backup",
        "mode": "pull",
        "enabled": True,
    },
    output={
        "label": "IBM VS",
        "protocol": "rtmp",
        "url": "rtmp://example.invalid/live/output",
        "mode": "push",
        "enabled": True,
    },
)


class ConfigStore:
    def __init__(self, data_dir: str) -> None:
        self.base_dir = Path(data_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.config_path = self.base_dir / "draft-config.json"
        self.revisions_path = self.base_dir / "revisions.json"
        self.runtime_dir = self.base_dir / "runtime"
        self.runtime_dir.mkdir(parents=True, exist_ok=True)

    def load(self) -> RelayConfig:
        if not self.config_path.exists():
            self.save(DEFAULT_CONFIG)
            return DEFAULT_CONFIG

        payload = json.loads(self.config_path.read_text())
        return RelayConfig.model_validate(payload)

    def save(self, config: RelayConfig) -> RelayConfig:
        self.config_path.write_text(
            json.dumps(config.model_dump(mode="json"), indent=2) + "\n"
        )
        return config

    def list_revisions(self) -> list[ConfigRevision]:
        if not self.revisions_path.exists():
            return []

        payload = json.loads(self.revisions_path.read_text())
        return [ConfigRevision.model_validate(item) for item in payload]

    def latest_revision(self) -> ConfigRevision | None:
        revisions = self.list_revisions()
        return revisions[-1] if revisions else None

    def create_revision(self, config: RelayConfig, status: str, note: str) -> ConfigRevision:
        revisions = self.list_revisions()
        version = revisions[-1].version + 1 if revisions else 1
        revision = ConfigRevision(
            version=version,
            status=status,
            payload=config,
            created_at=datetime.now(UTC).isoformat(),
            note=note,
        )
        revisions.append(revision)
        self.revisions_path.write_text(
            json.dumps([item.model_dump(mode="json") for item in revisions], indent=2) + "\n"
        )
        return revision

    def mark_rollback(self, config: RelayConfig, note: str) -> ConfigRevision:
        return self.create_revision(config, status="rolled_back", note=note)
