from __future__ import annotations

import json
import os
from pathlib import Path
from pydantic import BaseModel, Field

CONFIG_FILE = Path(os.getenv("CONFIG_FILE", "/config/config.json"))


class AppConfig(BaseModel):
    name: str = "Daikin D3net"
    upstream_host: str = "192.168.1.100"
    upstream_port: int = 502
    upstream_slave: int = 1
    upstream_protocol: str = Field(default="tcp", pattern="^(tcp|rtu_over_tcp)$")
    poll_interval: float = 10.0
    virtual_modbus_host: str = "0.0.0.0"
    virtual_modbus_port: int = 1502


def load_config() -> AppConfig:
    if CONFIG_FILE.exists():
        return AppConfig(**json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
    cfg = AppConfig()
    save_config(cfg)
    return cfg


def save_config(cfg: AppConfig) -> None:
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(cfg.model_dump_json(indent=2), encoding="utf-8")
