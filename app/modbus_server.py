from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable

from pymodbus.datastore import ModbusSequentialDataBlock, ModbusServerContext, ModbusSlaveContext
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


class VirtualModbusServer:
    def __init__(self, host: str, port: int, write_callback: WriteCallback):
        self.host = host
        self.port = port
        self.input_block = CallbackDataBlock(0, [0] * 10000)
        self.holding_block = CallbackDataBlock(0, [0] * 10000, callback=write_callback)
        self.store = ModbusSlaveContext(
            di=ModbusSequentialDataBlock(0, [0] * 100),
            co=ModbusSequentialDataBlock(0, [0] * 100),
            ir=self.input_block,
            hr=self.holding_block,
            zero_mode=True,
        )
        self.context = ModbusServerContext(slaves=self.store, single=True)

    def set_input_registers(self, address: int, values: list[int]) -> None:
        self.input_block.set_values_silent(address, [v & 0xFFFF for v in values])

    def set_holding_registers(self, address: int, values: list[int]) -> None:
        self.holding_block.set_values_silent(address, [v & 0xFFFF for v in values])

    def get_holding_registers(self, address: int, count: int) -> list[int]:
        return self.holding_block.getValues(address, count)

    async def run(self) -> None:
        _LOGGER.info("Starting virtual Modbus TCP server on %s:%s", self.host, self.port)
        await StartAsyncTcpServer(context=self.context, address=(self.host, self.port))
