"""Async Modbus RTU client for the RSPro RS510 frequency inverter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException

from .const import (
    CMD_EMERGENCY_STOP,
    CMD_RESET_FAULT,
    CMD_RUN_FORWARD,
    CMD_RUN_REVERSE,
    CMD_STOP,
    PARAM_COMM_FREQ_CMD,
    REG_CONTROL_CMD,
    REG_FAULT_CODE,
    REG_FREQ_SETPOINT,
    REG_MONITOR_COUNT,
    REG_STATUS_WORD,
    STATUS_BIT_ALARM,
    STATUS_BIT_FAULT,
    STATUS_BIT_READY,
    STATUS_BIT_REVERSE,
    STATUS_BIT_RUNNING,
)

_LOGGER = logging.getLogger(__name__)

_MAX_FAILURES = 3


@dataclass
class RS510Status:
    """Snapshot of all RS510 monitoring registers."""

    is_running: bool
    is_reverse: bool
    is_ready: bool
    has_fault: bool
    has_alarm: bool
    set_frequency_hz: float       # Hz
    output_frequency_hz: float    # Hz
    output_current_a: float       # A
    dc_voltage_v: float           # V
    output_voltage_v: float       # V
    motor_speed_rpm: int          # RPM
    heatsink_temp_c: int          # °C
    fault_code: int
    status_word: int


class RS510ModbusClient:
    """Async Modbus RTU wrapper for the RS510 inverter (Delta VFD platform).

    Prerequisites (set via keypad on the inverter once):
      P00-02 = 2   Run source = Communication
      P00-05 = 5   Frequency source = Communication

    Communication defaults:
      19200 baud, 8N1, Modbus RTU, slave address 1
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 19200,
        slave_address: int = 1,
        timeout: float = 2.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._slave = slave_address
        self._timeout = timeout
        self._client: AsyncModbusSerialClient | None = None
        self._lock = asyncio.Lock()
        self._consecutive_failures = 0
        self._use_param_freq = False  # fallback: write freq to P00-08 instead of 0x2001

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def async_connect(self) -> bool:
        try:
            self._client = AsyncModbusSerialClient(
                port=self._port,
                baudrate=self._baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=self._timeout,
            )
            connected = await self._client.connect()
            if connected:
                _LOGGER.debug("RS510 connected on %s @ %d baud", self._port, self._baudrate)
                self._consecutive_failures = 0
            else:
                _LOGGER.error("RS510: could not open %s", self._port)
            return connected
        except Exception as exc:
            _LOGGER.error("RS510 connect error: %s", exc)
            return False

    async def async_disconnect(self) -> None:
        if self._client:
            self._client.close()
            self._client = None
            _LOGGER.debug("RS510 disconnected")

    @property
    def available(self) -> bool:
        return (
            self._client is not None
            and self._consecutive_failures < _MAX_FAILURES
        )

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    async def async_read_status(self) -> Optional[RS510Status]:
        """Read monitoring registers 0x2100–0x2108 in a single request."""
        async with self._lock:
            if self._client is None:
                return None
            try:
                result = await self._client.read_holding_registers(
                    address=REG_STATUS_WORD,
                    count=REG_MONITOR_COUNT + 1,  # +1 for fault code at 0x2108
                    slave=self._slave,
                )
                if result.isError():
                    self._on_failure("read monitoring registers error: %s", result)
                    return None

                regs = result.registers
                self._consecutive_failures = 0
                status_word = regs[0]
                return RS510Status(
                    is_running=bool(status_word & STATUS_BIT_RUNNING),
                    is_reverse=bool(status_word & STATUS_BIT_REVERSE),
                    is_ready=bool(status_word & STATUS_BIT_READY),
                    has_fault=bool(status_word & STATUS_BIT_FAULT),
                    has_alarm=bool(status_word & STATUS_BIT_ALARM),
                    set_frequency_hz=regs[1] / 100.0,
                    output_frequency_hz=regs[2] / 100.0,
                    output_current_a=regs[3] / 100.0,
                    dc_voltage_v=regs[4] / 10.0,
                    output_voltage_v=regs[5] / 10.0,
                    motor_speed_rpm=regs[6],
                    heatsink_temp_c=regs[7],
                    fault_code=regs[8] if len(regs) > 8 else 0,
                    status_word=status_word,
                )
            except ModbusException as exc:
                self._on_failure("Modbus exception during read: %s", exc)
                return None
            except Exception as exc:
                self._on_failure("Unexpected error during read: %s", exc)
                return None

    # ------------------------------------------------------------------
    # Control commands
    # ------------------------------------------------------------------

    async def async_run_forward(self) -> bool:
        return await self._write_control(CMD_RUN_FORWARD)

    async def async_run_reverse(self) -> bool:
        return await self._write_control(CMD_RUN_REVERSE)

    async def async_stop(self) -> bool:
        return await self._write_control(CMD_STOP)

    async def async_emergency_stop(self) -> bool:
        return await self._write_control(CMD_EMERGENCY_STOP)

    async def async_reset_fault(self) -> bool:
        return await self._write_control(CMD_RESET_FAULT)

    async def async_set_frequency(self, frequency_hz: float) -> bool:
        """Set the output frequency setpoint in Hz."""
        value = int(round(frequency_hz * 100))
        if self._use_param_freq:
            return await self._write_register(PARAM_COMM_FREQ_CMD, value)
        return await self._write_register(REG_FREQ_SETPOINT, value)

    async def async_read_parameter(self, address: int) -> Optional[int]:
        """Read a single parameter register."""
        async with self._lock:
            if self._client is None:
                return None
            try:
                result = await self._client.read_holding_registers(
                    address=address, count=1, slave=self._slave,
                )
                if result.isError():
                    return None
                return result.registers[0]
            except Exception:
                return None

    async def async_write_parameter(self, address: int, value: int) -> bool:
        """Write a single parameter register."""
        return await self._write_register(address, value)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _write_control(self, command: int) -> bool:
        return await self._write_register(REG_CONTROL_CMD, command)

    async def _write_register(self, address: int, value: int) -> bool:
        async with self._lock:
            if self._client is None:
                return False
            try:
                result = await self._client.write_register(
                    address=address, value=value, slave=self._slave,
                )
                if result.isError():
                    _LOGGER.error(
                        "RS510: write 0x%04X = %d error: %s", address, value, result
                    )
                    return False
                return True
            except ModbusException as exc:
                _LOGGER.error("RS510: Modbus error writing 0x%04X: %s", address, exc)
                return False
            except Exception as exc:
                _LOGGER.error("RS510: error writing 0x%04X: %s", address, exc)
                return False

    def _on_failure(self, msg: str, *args: object) -> None:
        self._consecutive_failures += 1
        _LOGGER.warning(
            "RS510 (%d/%d): " + msg,
            self._consecutive_failures,
            _MAX_FAILURES,
            *args,
        )
