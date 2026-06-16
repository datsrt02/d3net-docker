from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext
try:
    # PyModbus >= 3.10
    from pymodbus.datastore import ModbusDeviceContext as _ModbusContext
except ImportError:  # pragma: no cover - PyModbus < 3.10
    from pymodbus.datastore import ModbusSlaveContext as _ModbusContext
from pymodbus.server import StartAsyncTcpServer

_LOGGER = logging.getLogger(__name__)
WriteCallback = Callable[[int, list[int]], Awaitable[None]]


class CallbackDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address: int, values: list[int], callback: WriteCallback | None = None):
        super().__init__(address, values)
        self.callback = callback
        self.silent = False

    def setValues(self, address, values):  # pymodbus calls this synchronously
        if isinstance(values, int):
            values = [values]
        super().setValues(address, values)
        if self.callback and not self.silent:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self.callback(address, list(values)))
            except RuntimeError:
                _LOGGER.warning("No running event loop for Modbus write callback")

    def set_values_silent(self, address: int, values: list[int]) -> None:
        self.silent = True
        try:
            super().setValues(address, values)
        finally:
            self.silent = False


def _make_device_context(**blocks):
    """Create PyModbus device/slave context across 3.x API variants."""
    try:
        return _ModbusContext(**blocks, zero_mode=True)
    except TypeError:
        # PyModbus >= 3.8 removed zero_mode from the legacy datastore API.
        return _ModbusContext(**blocks)


def _make_server_context(device_context):
    """Create PyModbus server context across 3.x API variants."""
    for kwargs in (
        {"device_default": device_context, "single": True},  # newer 3.x
        {"devices": device_context, "single": True},         # 3.10 API change note
        {"slaves": device_context, "single": True},          # older 3.x
    ):
        try:
            return ModbusServerContext(**kwargs)
        except TypeError:
            continue
    raise RuntimeError("Unsupported pymodbus ModbusServerContext API")


class VirtualModbusServer:
    def __init__(self, host: str, port: int, write_callback: WriteCallback):
        self.host = host
        self.port = port
        self.input_block = CallbackDataBlock(0, [0] * 10000)
        self.holding_block = CallbackDataBlock(0, [0] * 10000, callback=write_callback)
        self.store = _make_device_context(
            di=ModbusSequentialDataBlock(0, [0] * 100),
            co=ModbusSequentialDataBlock(0, [0] * 100),
            ir=self.input_block,
            hr=self.holding_block,
        )
        self.context = _make_server_context(self.store)

    def set_input_registers(self, address: int, values: list[int]) -> None:
        self.input_block.set_values_silent(address, [v & 0xFFFF for v in values])

    def set_holding_registers(self, address: int, values: list[int]) -> None:
        self.holding_block.set_values_silent(address, [v & 0xFFFF for v in values])

    def get_holding_registers(self, address: int, count: int) -> list[int]:
        return self.holding_block.getValues(address, count)

    async def run(self) -> None:
        _LOGGER.info("Starting virtual Modbus TCP server on %s:%s", self.host, self.port)
        await StartAsyncTcpServer(context=self.context, address=(self.host, self.port))
