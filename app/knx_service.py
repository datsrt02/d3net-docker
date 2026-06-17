from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class KnxConfig(BaseModel):
    gateway_name: str = "KNX Main Gateway"
    gateway_ip: str = "192.168.1.10"
    gateway_port: int = Field(default=3671, ge=1, le=65535)
    physical_address: str = "1.1.10"
    protocol: str = Field(default="TunnelUDP", pattern="^(TunnelUDP|TunnelTCP|Multicast)$")


class KnxMapping(BaseModel):
    indoor: str = "1-00"
    power_ga: str = "1/4/70"
    mode_ga: str = "1/4/71"
    setpoint_ga: str = "1/4/72"
    temp_ga: str = "1/4/73"
    fan_ga: str = "1/4/74"


class MonitorRequest(BaseModel):
    enabled: bool


class KnxRuntime:
    """Lightweight KNX gateway placeholder/runtime for UI configuration and bus monitor.

    This module deliberately keeps the web app installable without a KNX stack dependency.
    It stores KNX gateway settings, exposes connection state, and provides a monitor log
    buffer. Real KNXnet/IP telegram subscription can be attached later behind the same API.
    """

    def __init__(self) -> None:
        self.config = KnxConfig()
        self.connected = False
        self.monitor_enabled = False
        self.last_error: str | None = None
        self.logs: deque[dict[str, Any]] = deque(maxlen=500)
        self.mappings: list[KnxMapping] = []
        self._demo_task: asyncio.Task | None = None

    def set_config(self, config: KnxConfig) -> None:
        self.config = config
        self.add_log("local", config.physical_address, "-", "GatewayConfig", "", f"Saved {config.gateway_name} {config.gateway_ip}:{config.gateway_port}")

    async def connect(self, config: KnxConfig | None = None) -> None:
        if config is not None:
            self.config = config
        # Placeholder connection: validates config and marks connected.
        # The API and UI are ready for real KNXnet/IP integration in a next step.
        self.connected = True
        self.last_error = None
        self.add_log("local", self.config.physical_address, "-", "Connect", "", f"Connected to {self.config.gateway_ip}:{self.config.gateway_port} via {self.config.protocol}")
        if self.monitor_enabled:
            self._ensure_demo_task()

    async def disconnect(self) -> None:
        self.connected = False
        self.add_log("local", self.config.physical_address, "-", "Disconnect", "", "Disconnected")
        if self._demo_task:
            self._demo_task.cancel()
            try:
                await self._demo_task
            except asyncio.CancelledError:
                pass
            self._demo_task = None

    def status_json(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "monitor_enabled": self.monitor_enabled,
            "last_error": self.last_error,
            "config": self.config.model_dump(),
            "log_count": len(self.logs),
        }

    def add_log(self, service: str, source: str, destination: str, telegram_type: str, dpt: str, value: Any) -> None:
        self.logs.appendleft({
            "time": datetime.now().strftime("%d-%b-%y %I:%M:%S.%f %p")[:-3],
            "service": service,
            "flags": "",
            "prio": "Low",
            "source_address": source,
            "source_name": "",
            "destination_address": destination,
            "destination_route": "6" if destination != "-" else "",
            "type": telegram_type,
            "dpt": dpt,
            "value": value,
        })

    def logs_json(self, limit: int = 100, ga_filter: str | None = None) -> list[dict[str, Any]]:
        rows = list(self.logs)[: max(1, min(limit, 500))]
        if ga_filter:
            if ga_filter.endswith("*"):
                prefix = ga_filter[:-1]
                rows = [r for r in rows if str(r.get("destination_address", "")).startswith(prefix)]
            else:
                rows = [r for r in rows if r.get("destination_address") == ga_filter]
        return rows

    def clear_logs(self) -> None:
        self.logs.clear()

    def set_monitor(self, enabled: bool) -> None:
        self.monitor_enabled = enabled
        self.add_log("local", self.config.physical_address, "-", "Monitor", "", "ON" if enabled else "OFF")
        if enabled and self.connected:
            self._ensure_demo_task()
        elif not enabled and self._demo_task:
            self._demo_task.cancel()
            self._demo_task = None

    def _ensure_demo_task(self) -> None:
        if self._demo_task is None or self._demo_task.done():
            self._demo_task = asyncio.create_task(self._demo_telegram_loop())

    async def _demo_telegram_loop(self) -> None:
        samples = [
            ("from bus", "1.1.10", "1/4/70", "GroupValueWrite", "1.001", "1"),
            ("from bus", "1.1.10", "1/4/74", "GroupValueWrite", "5.001", "57.36"),
            ("from bus", "1.1.10", "1/4/81", "GroupValueWrite", "9.001", "27.88"),
            ("from bus", "1.1.10", "1/4/84", "GroupValueWrite", "5.001", "61.72"),
        ]
        i = 0
        while self.connected and self.monitor_enabled:
            s = samples[i % len(samples)]
            self.add_log(*s)
            i += 1
            await asyncio.sleep(2.5)


    def publish_group_value(self, destination: str, value: Any, dpt: str, source: str | None = None, force: bool = False, label: str = "D3netLink") -> bool:
        """Publish/log a D3net value to a KNX group address.

        The current implementation records the telegram in the KNX monitor log and
        de-duplicates unchanged values. A real KNXnet/IP write can later be added
        here without changing the D3net mapping API.
        """
        destination = (destination or "").strip()
        if not destination:
            return False
        cache_key = f"{destination}|{dpt}"
        if not hasattr(self, "_last_published"):
            self._last_published = {}
        if not force and self._last_published.get(cache_key) == value:
            return False
        self._last_published[cache_key] = value
        self.add_log("D3net -> KNX", source or self.config.physical_address, destination, "GroupValueWrite", dpt, value)
        return True

    def save_mapping(self, mapping: KnxMapping) -> None:
        self.mappings = [m for m in self.mappings if m.indoor != mapping.indoor]
        self.mappings.append(mapping)
        self.add_log("local", self.config.physical_address, "-", "Mapping", "", f"Saved mapping for {mapping.indoor}")

    def mappings_json(self) -> list[dict[str, Any]]:
        return [m.model_dump() for m in self.mappings]
