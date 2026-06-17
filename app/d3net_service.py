from __future__ import annotations

import asyncio
import logging
from typing import Any

from pymodbus.client import AsyncModbusTcpClient
try:
    from pymodbus.framer import FramerType as ModbusFramer
except Exception:  # pragma: no cover
    ModbusFramer = None

from .config import AppConfig
from .d3net.const import D3netFanDirection, D3netFanSpeed, D3netOperationMode
from .d3net.encoding import SystemStatus, UnitCapability, UnitError, UnitHolding, UnitStatus
from .d3net.gateway import D3netGateway, D3netUnit
from .modbus_server import VirtualModbusServer
from .register_map import (
    HOLDING_UNIT_BASE, HOLDING_UNIT_STEP,
    INPUT_CAP_BASE, INPUT_CAP_STEP,
    INPUT_ERROR_BASE, INPUT_ERROR_STEP,
    INPUT_STATUS_BASE, INPUT_STATUS_STEP,
    INPUT_SYSTEM_BASE,
    index_to_unit_id, unit_id_to_index,
)

_LOGGER = logging.getLogger(__name__)


class D3netRuntime:
    def __init__(self) -> None:
        self.config: AppConfig | None = None
        self.gateway: D3netGateway | None = None
        self.modbus: VirtualModbusServer | None = None
        self.poll_task: asyncio.Task | None = None
        self.connected = False
        self.last_error: str | None = None
        self._lock = asyncio.Lock()

    async def start(self, config: AppConfig) -> None:
        async with self._lock:
            await self.stop()
            self.config = config
            if config.upstream_protocol == "rtu_over_tcp" and ModbusFramer:
                client = AsyncModbusTcpClient(
                    host=config.upstream_host,
                    port=config.upstream_port,
                    timeout=10,
                    framer=ModbusFramer.RTU,
                )
            else:
                client = AsyncModbusTcpClient(
                    host=config.upstream_host,
                    port=config.upstream_port,
                    timeout=10,
                )
            # Daikin DIII Modbus uses zero-based register addresses.
            # Slave/device id must be 1..247; using a register number here can trigger
            # PyModbus error: "0 <= address < 65535".
            if not (1 <= int(config.upstream_slave) <= 247):
                raise ValueError("Slave ID phải nằm trong khoảng 1..247, không nhập địa chỉ thanh ghi như 30001/42001 vào ô này")
            if not (1 <= int(config.upstream_port) <= 65535):
                raise ValueError("Gateway Port phải nằm trong khoảng 1..65535, thường là 502")
            if not (1 <= int(config.virtual_modbus_port) <= 65535):
                raise ValueError("Virtual Modbus Port phải nằm trong khoảng 1..65535, ví dụ 1502")
            self.gateway = D3netGateway(client, config.upstream_slave)
            self.modbus = VirtualModbusServer(
                config.virtual_modbus_host,
                config.virtual_modbus_port,
                self.apply_holding_write,
            )
            asyncio.create_task(self.modbus.run())
            await self.gateway.async_setup()
            if not self.gateway.units:
                await self.rediscover_units_from_system()
            self.connected = True
            self.last_error = None
            await self.sync_all_to_virtual_modbus()
            self.poll_task = asyncio.create_task(self.poll_loop())

    async def stop(self) -> None:
        if self.poll_task:
            self.poll_task.cancel()
            try:
                await self.poll_task
            except asyncio.CancelledError:
                pass
            self.poll_task = None
        if self.gateway:
            try:
                await self.gateway.async_close()
            except Exception:
                pass
        self.gateway = None
        self.connected = False

    async def poll_loop(self) -> None:
        assert self.config is not None
        while True:
            try:
                await self.poll_once()
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                _LOGGER.exception("D3net polling failed")
            await asyncio.sleep(self.config.poll_interval)

    async def poll_once(self) -> None:
        if not self.gateway:
            return
        # Auto discovery must run on every poll. The Daikin interface can discover
        # a new indoor after the web app has already started; 30002-30005 are the
        # source of truth for the connected DIII addresses.
        await self.rediscover_units_from_system()
        for unit in self.gateway.units or []:
            await unit.async_update_status()
        self.connected = True
        self.last_error = None
        await self.sync_all_to_virtual_modbus()

    async def sync_all_to_virtual_modbus(self) -> None:
        if not self.gateway or not self.modbus:
            return
        units: list[D3netUnit] = self.gateway.units or []
        system_regs = [0] * 9
        system_regs[0] = 0x0001  # bit 0 = Ready
        for unit in units:
            group = unit.index // 16
            bit = unit.index % 16
            system_regs[1 + group] |= 1 << bit
        self.modbus.set_input_registers(INPUT_SYSTEM_BASE, system_regs)

        for unit in units:
            self.modbus.set_input_registers(
                INPUT_CAP_BASE + unit.index * INPUT_CAP_STEP,
                unit.capabilities._registers,
            )
            self.modbus.set_input_registers(
                INPUT_STATUS_BASE + unit.index * INPUT_STATUS_STEP,
                unit.status._registers,
            )
            # Keep holding registers copied from current status, as Daikin recommends before control.
            holding = UnitHolding([0, 0, 0])
            holding.sync(unit.status, D3netUnit.SYNC_PROPERTIES)
            self.modbus.set_holding_registers(
                HOLDING_UNIT_BASE + unit.index * HOLDING_UNIT_STEP,
                holding.registers,
            )
            try:
                err = await self.gateway.async_read(UnitError, unit.index)
                self.modbus.set_input_registers(
                    INPUT_ERROR_BASE + unit.index * INPUT_ERROR_STEP,
                    err._registers,
                )
            except Exception:
                # Error registers are non-critical for climate control.
                pass


    async def rediscover_units_from_system(self) -> None:
        """Populate gateway.units from 30002-30005 even if the original setup path failed to render them.

        This is the robust discovery path used by the web UI: 30002-30005 are the
        source of truth for connected DIII group addresses, and 30006-30009 are
        used to exclude communication-error units.
        """
        if not self.gateway:
            return
        system = await self.gateway.async_read(SystemStatus, 0)
        discovered: list[D3netUnit] = []
        for index, connected in enumerate(system.units_connected):
            if not connected or system.units_error[index]:
                continue
            cap = await self.gateway.async_read(UnitCapability, index)
            st = await self.gateway.async_read(UnitStatus, index)
            discovered.append(D3netUnit(self.gateway, index, cap, st))
        self.gateway._units = discovered
        self.connected = True
        self.last_error = None

    async def units_json_async(self) -> list[dict[str, Any]]:
        """Return units for the web UI, always refreshing discovery from 30002-30009.

        This makes the web Auto Refresh show newly connected indoor units without
        requiring the user to press Scan / Connect again.
        """
        if not self.gateway:
            return []
        await self.rediscover_units_from_system()
        return self.units_json()

    def get_unit_by_id(self, unit_id: str) -> D3netUnit:
        if not self.gateway:
            raise RuntimeError("Gateway not started")
        index = unit_id_to_index(unit_id)
        for unit in self.gateway.units or []:
            if unit.index == index:
                return unit
        raise KeyError(f"Unit {unit_id} not discovered")

    async def apply_holding_write(self, address: int, values: list[int]) -> None:
        if not self.gateway:
            return
        if address < HOLDING_UNIT_BASE:
            return
        index = (address - HOLDING_UNIT_BASE) // HOLDING_UNIT_STEP
        offset = (address - HOLDING_UNIT_BASE) % HOLDING_UNIT_STEP
        if offset not in (0, 1, 2):
            return
        unit_id = index_to_unit_id(index)
        try:
            unit = self.get_unit_by_id(unit_id)
        except Exception:
            return

        regs = self.modbus.get_holding_registers(HOLDING_UNIT_BASE + index * HOLDING_UNIT_STEP, HOLDING_UNIT_STEP) if self.modbus else [0, 0, 0]
        holding = UnitHolding(regs)
        await unit.async_write_prepare()
        # Copy requested holding values to status object. Commit syncs status -> holding and writes upstream.
        unit.status.power = holding.power
        unit.status.fan_direct = holding.fan_direct
        unit.status.fan_speed = holding.fan_speed
        unit.status.operating_mode = holding.operating_mode
        unit.status.temp_setpoint = holding.temp_setpoint
        if holding.filter_reset:
            unit.filter_reset()
        await unit.async_write_commit()
        await asyncio.sleep(0.2)
        await unit.async_update_status()
        await self.sync_all_to_virtual_modbus()


    async def debug_system_registers(self) -> dict[str, Any]:
        if not self.gateway:
            raise RuntimeError("Gateway not started")
        decoder = await self.gateway.async_read(SystemStatus, 0)
        regs = list(decoder._registers)
        connected = []
        errors = []
        for i, ok in enumerate(decoder.units_connected):
            if ok:
                connected.append(index_to_unit_id(i))
        for i, err in enumerate(decoder.units_error):
            if err:
                errors.append(index_to_unit_id(i))
        return {
            "raw_30001_30009": regs,
            "ready_30001_bit0": decoder.initialised,
            "other_diii_device_30001_bit1": decoder.other_device_exists,
            "connected_units_from_30002_30005": connected,
            "error_units_from_30006_30009": errors,
        }

    async def debug_unit_registers(self, unit_id: str) -> dict[str, Any]:
        if not self.gateway:
            raise RuntimeError("Gateway not started")
        index = unit_id_to_index(unit_id)
        cap = await self.gateway.async_read(UnitCapability, index)
        st = await self.gateway.async_read(UnitStatus, index)
        err = await self.gateway.async_read(UnitError, index)
        return {
            "unit_id": unit_id,
            "index": index,
            "capability_address_zero_based": UnitCapability.ADDRESS + index * UnitCapability.COUNT,
            "status_address_zero_based": UnitStatus.ADDRESS + index * UnitStatus.COUNT,
            "error_address_zero_based": UnitError.ADDRESS + index * UnitError.COUNT,
            "raw_310xx_capability": list(cap._registers),
            "raw_320xx_status": list(st._registers),
            "raw_336xx_error": list(err._registers),
        }

    def status_json(self) -> dict[str, Any]:
        return {
            "running": self.gateway is not None,
            "connected": self.connected,
            "last_error": self.last_error,
            "unit_count": len(self.gateway.units or []) if self.gateway else 0,
        }

    def _safe(self, fn, default=None):
        try:
            return fn()
        except Exception as exc:
            _LOGGER.warning("Decode warning: %s", exc)
            return default

    def units_json(self) -> list[dict[str, Any]]:
        if not self.gateway:
            return []
        result = []
        for unit in self.gateway.units or []:
            st = unit.status
            cap = unit.capabilities
            mode = self._safe(lambda: st.operating_mode)
            running = self._safe(lambda: st.operating_current)
            fan_speed = self._safe(lambda: st.fan_speed)
            fan_direct = self._safe(lambda: st.fan_direct)
            result.append({
                "id": unit.unit_id,
                "index": unit.index,
                "power": self._safe(lambda: st.power, False),
                "mode": mode.name if mode else "UNKNOWN",
                "mode_value": mode.value if mode else None,
                "running": running.name if running else "UNKNOWN",
                "fan": self._safe(lambda: st.fan, False),
                "fan_speed": fan_speed.name if fan_speed else "UNKNOWN",
                "fan_direction": fan_direct.name if fan_direct else "UNKNOWN",
                "setpoint": self._safe(lambda: st.temp_setpoint),
                "current_temperature": self._safe(lambda: st.temp_current),
                "filter_warning": self._safe(lambda: st.filter_warning, False),
                "capabilities": {
                    "fan": self._safe(lambda: cap.fan_mode_capable, False),
                    "cool": self._safe(lambda: cap.cool_mode_capable, False),
                    "heat": self._safe(lambda: cap.heat_mode_capable, False),
                    "auto": self._safe(lambda: cap.auto_mode_capable, False),
                    "dry": self._safe(lambda: cap.dry_mode_capable, False),
                    "fan_speed": self._safe(lambda: cap.fan_speed_capable, False),
                    "fan_direction": self._safe(lambda: cap.fan_direct_capable, False),
                    "cool_min": self._safe(lambda: cap.cool_setpoint_lowerlimit),
                    "cool_max": self._safe(lambda: cap.cool_setpoint_upperlimit),
                    "heat_min": self._safe(lambda: cap.heat_setpoint_lowerlimit),
                    "heat_max": self._safe(lambda: cap.heat_setpoint_upperlimit),
                },
                "raw": {
                    "capability": list(getattr(cap, "_registers", [])),
                    "status": list(getattr(st, "_registers", [])),
                }
            })
        return result

    async def set_power(self, unit_id: str, power: bool) -> None:
        unit = self.get_unit_by_id(unit_id)
        await unit.async_write_prepare()
        unit.status.power = power
        await unit.async_write_commit()
        await unit.async_update_status()
        await self.sync_all_to_virtual_modbus()

    async def set_mode(self, unit_id: str, mode: str) -> None:
        unit = self.get_unit_by_id(unit_id)
        await unit.async_write_prepare()
        unit.status.operating_mode = D3netOperationMode[mode.upper()]
        unit.status.power = True
        await unit.async_write_commit()
        await unit.async_update_status()
        await self.sync_all_to_virtual_modbus()

    async def set_setpoint(self, unit_id: str, value: float) -> None:
        unit = self.get_unit_by_id(unit_id)
        await unit.async_write_prepare()
        unit.status.temp_setpoint = value
        await unit.async_write_commit()
        await unit.async_update_status()
        await self.sync_all_to_virtual_modbus()

    async def set_fan_speed(self, unit_id: str, speed: str) -> None:
        unit = self.get_unit_by_id(unit_id)
        await unit.async_write_prepare()
        unit.status.fan_speed = D3netFanSpeed[speed]
        await unit.async_write_commit()
        await unit.async_update_status()
        await self.sync_all_to_virtual_modbus()

    async def set_fan_direction(self, unit_id: str, direction: str) -> None:
        unit = self.get_unit_by_id(unit_id)
        await unit.async_write_prepare()
        unit.status.fan_direct = D3netFanDirection[direction]
        await unit.async_write_commit()
        await unit.async_update_status()
        await self.sync_all_to_virtual_modbus()
