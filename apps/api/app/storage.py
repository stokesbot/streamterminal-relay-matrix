import json
from pathlib import Path

from .schemas import RelayConfig

DEFAULT_CONFIG = RelayConfig(
    channel_name="IBM VS Failover",
    mediamtx_enabled=True,
    relay_enabled=True,
    auto_restart=True,
    primary_input={
        "label": "Primary",
        "protocol": "rtmp",
        "url": "rtmp://109.122.217.246:1936/live/main",
        "mode": "pull",
        "enabled": True,
    },
    backup_input={
        "label": "Backup",
        "protocol": "rtmp",
        "url": "rtmp://109.122.217.246:1936/live/backup",
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
