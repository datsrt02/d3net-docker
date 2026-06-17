from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

try:
    from xknx import XKNX
    from xknx.io import ConnectionConfig, ConnectionType
    from xknx.telegram import Telegram
    from xknx.telegram.address import GroupAddress, IndividualAddress
    from xknx.telegram.apci import GroupValueWrite, GroupValueRead, GroupValueResponse
    from xknx.dpt import DPTBinary, DPT2ByteFloat, DPTValue1ByteUnsigned, DPTArray
except Exception:  # pragma: no cover - allows UI to start even if xknx is missing
    XKNX = None
    ConnectionConfig = None
    ConnectionType = None
    Telegram = None
    GroupAddress = None
    IndividualAddress = None
    GroupValueWrite = None
    GroupValueRead = None
    GroupValueResponse = None
    DPTBinary = None
    DPT2ByteFloat = None
    DPTValue1ByteUnsigned = None
    DPTArray = None


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


def _boolish(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "on", "yes"}


class KnxRuntime:
    """KNXnet/IP runtime.

    v16 changes this from a UI-only placeholder into a real KNXnet/IP sender.
    The monitor table still records outgoing telegrams locally, but `publish_group_value()`
    now also sends GroupValueWrite telegrams to the configured KNX/IP gateway when connected.
    """

    def __init__(self) -> None:
        self.config = KnxConfig()
        self.connected = False
        self.monitor_enabled = False
        self.last_error: str | None = None
        self.logs: deque[dict[str, Any]] = deque(maxlen=500)
        self.mappings: list[KnxMapping] = []
        self._xknx: Any | None = None
        self._lock = asyncio.Lock()
        self._last_published: dict[str, Any] = {}

    def set_config(self, config: KnxConfig) -> None:
        self.config = config
        self.add_log("local", config.physical_address, "-", "GatewayConfig", "", f"Saved {config.gateway_name} {config.gateway_ip}:{config.gateway_port}")

    def _connection_type(self):
        if ConnectionType is None:
            return None
        if self.config.protocol == "TunnelTCP":
            return ConnectionType.TUNNELING_TCP
        if self.config.protocol == "Multicast":
            return ConnectionType.ROUTING
        return ConnectionType.TUNNELING

    async def connect(self, config: KnxConfig | None = None) -> None:
        if config is not None:
            self.config = config
        async with self._lock:
            await self._stop_xknx_locked()
            if XKNX is None:
                self.connected = False
                self.last_error = "xknx is not installed in this container"
                self.add_log("local", self.config.physical_address, "-", "ConnectError", "", self.last_error)
                raise RuntimeError(self.last_error)

            try:
                connection_config = ConnectionConfig(
                    connection_type=self._connection_type(),
                    gateway_ip=self.config.gateway_ip if self.config.protocol != "Multicast" else None,
                    gateway_port=self.config.gateway_port,
                    individual_address=self.config.physical_address,
                    multicast_port=self.config.gateway_port,
                    auto_reconnect=True,
                )
                self._xknx = XKNX(
                    connection_config=connection_config,
                    telegram_received_cb=self._telegram_received,
                    daemon_mode=True,
                )
                await self._xknx.start()
                self.connected = True
                self.last_error = None
                self.add_log("local", self.config.physical_address, "-", "Connect", "", f"Connected real KNX/IP {self.config.gateway_ip}:{self.config.gateway_port} via {self.config.protocol}")
            except Exception as exc:
                self._xknx = None
                self.connected = False
                self.last_error = str(exc)
                self.add_log("local", self.config.physical_address, "-", "ConnectError", "", self.last_error)
                raise

    async def disconnect(self) -> None:
        async with self._lock:
            await self._stop_xknx_locked()
            self.connected = False
            self.add_log("local", self.config.physical_address, "-", "Disconnect", "", "Disconnected")

    async def _stop_xknx_locked(self) -> None:
        if self._xknx is not None:
            try:
                await self._xknx.stop()
            except Exception:
                pass
            self._xknx = None

    def status_json(self) -> dict[str, Any]:
        return {
            "connected": self.connected,
            "monitor_enabled": self.monitor_enabled,
            "last_error": self.last_error,
            "real_knx_enabled": self._xknx is not None,
            "xknx_installed": XKNX is not None,
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

    def _telegram_received(self, telegram: Any) -> None:
        if not self.monitor_enabled:
            return
        try:
            source = str(getattr(telegram, "source_address", ""))
            destination = str(getattr(telegram, "destination_address", ""))
            payload = getattr(telegram, "payload", None)
            typ = type(payload).__name__ if payload is not None else "Telegram"
            value = str(payload) if payload is not None else ""
            self.add_log("from bus", source, destination, typ, "", value)
        except Exception:
            pass

    def _payload_for_dpt(self, dpt: str, value: Any):
        dpt = (dpt or "").strip()
        if DPTBinary is None or DPTArray is None:
            raise RuntimeError("xknx DPT classes are not available")
        if dpt.startswith("1."):
            return DPTBinary(1 if _boolish(value) else 0)
        if dpt.startswith("9."):
            return DPT2ByteFloat.to_knx(float(value))
        if dpt.startswith("5.") or dpt.startswith("20."):
            return DPTValue1ByteUnsigned.to_knx(int(round(float(value))))
        # Fallback: send one raw byte for byte-like status values.
        if isinstance(value, (int, float)) or str(value).strip().lstrip("-").isdigit():
            return DPTArray([max(0, min(255, int(round(float(value)))) )])
        raise ValueError(f"Unsupported DPT {dpt} for value {value!r}")

    async def _send_group_value_async(self, destination: str, value: Any, dpt: str) -> bool:
        if not self.connected or self._xknx is None:
            raise RuntimeError("KNX is not connected")
        payload_value = self._payload_for_dpt(dpt, value)
        telegram = Telegram(
            destination_address=GroupAddress(destination),
            payload=GroupValueWrite(payload_value),
            source_address=IndividualAddress(self.config.physical_address),
        )
        await self._xknx.telegrams.put(telegram)
        return True

    def publish_group_value(self, destination: str, value: Any, dpt: str, source: str | None = None, force: bool = False, label: str = "D3netLink") -> bool:
        """Send a D3net value to KNX bus and log it.

        Returns True when a new value was accepted for sending/logging. If the value is unchanged
        and `force` is false, it returns False to avoid flooding the KNX bus.
        """
        destination = (destination or "").strip()
        if not destination:
            return False
        cache_key = f"{destination}|{dpt}"
        if not force and self._last_published.get(cache_key) == value:
            return False
        self._last_published[cache_key] = value

        # Always log the attempted outgoing telegram so the UI remains useful.
        self.add_log("D3net -> KNX", source or self.config.physical_address, destination, "GroupValueWrite", dpt, value)

        # Schedule the actual KNXnet/IP write. This method is intentionally sync because
        # older endpoint code calls it from both sync and async contexts.
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._send_group_value_guarded(destination, value, dpt))
        except RuntimeError:
            # Should not happen under FastAPI, but keep safe.
            pass
        return True

    async def _send_group_value_guarded(self, destination: str, value: Any, dpt: str) -> None:
        try:
            await self._send_group_value_async(destination, value, dpt)
            self.add_log("to bus", self.config.physical_address, destination, "GroupValueWrite", dpt, value)
        except Exception as exc:
            self.last_error = str(exc)
            self.add_log("KNX error", self.config.physical_address, destination, "GroupValueWrite", dpt, self.last_error)

    def save_mapping(self, mapping: KnxMapping) -> None:
        self.mappings = [m for m in self.mappings if m.indoor != mapping.indoor]
        self.mappings.append(mapping)
        self.add_log("local", self.config.physical_address, "-", "Mapping", "", f"Saved mapping for {mapping.indoor}")

    def mappings_json(self) -> list[dict[str, Any]]:
        return [m.model_dump() for m in self.mappings]
