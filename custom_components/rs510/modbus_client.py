"""Async Modbus RTU client for the RSPro RS510 frequency inverter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Optional

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException

from .const import (
    CMD_RESET_FAULT,
    CMD_RUN_FORWARD,
    CMD_RUN_REVERSE,
    CMD_STOP,
    REG_CONTROL_CMD,
    REG_FREQ_SETPOINT,
    REG_MONITOR_COUNT,
    REG_MONITOR_START,
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
        self._last_freq_value: int = 1500  # default 15.00 Hz

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
        """Read monitoring registers 0x2520–0x2532 in a single FC03 request.

        L510 manual Appendix 3, Section 4.2 register layout:
          [0]  0x2520 = status word
          [1]  0x2521 = fault code
          [2]  0x2522 = DI/DO status
          [3]  0x2523 = frequency command echo (0.01 Hz)
          [4]  0x2524 = output frequency (0.01 Hz)
          [5]  0x2525 = output voltage (0.1 V)
          [6]  0x2526 = DC bus voltage (1 V)
          [7]  0x2527 = output current (0.1 A)
          [9]  0x2529 = output power (0.1 kW)
          [17] 0x2531 = heatsink temperature (0.1 °C)
          [18] 0x2532 = current ratio (%)
        """
        async with self._lock:
            if self._client is None:
                return None
            try:
                result = await self._client.read_holding_registers(
                    address=REG_MONITOR_START,
                    count=REG_MONITOR_COUNT,
                    slave=self._slave,
                )
                if result.isError():
                    self._on_failure("read monitoring registers error: %s", result)
                    return None

                regs = result.registers
                self._consecutive_failures = 0
                status_word = regs[0]   # 0x2520
                fault_code  = regs[1]   # 0x2521
                return RS510Status(
                    is_running=bool(status_word & STATUS_BIT_RUNNING),
                    is_reverse=bool(status_word & STATUS_BIT_REVERSE),
                    is_ready=bool(status_word & STATUS_BIT_READY),
                    has_fault=bool(status_word & STATUS_BIT_FAULT),
                    has_alarm=bool(status_word & STATUS_BIT_ALARM),
                    set_frequency_hz=regs[3] / 100.0,    # 0x2523
                    output_frequency_hz=regs[4] / 100.0, # 0x2524
                    output_voltage_v=regs[5] / 10.0,     # 0x2525
                    dc_voltage_v=float(regs[6]),          # 0x2526 (1 V resolution)
                    output_current_a=regs[7] / 10.0,     # 0x2527
                    heatsink_temp_c=regs[17] // 10,      # 0x2531 (0.1 °C → °C)
                    motor_speed_rpm=0,
                    fault_code=fault_code,
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
        """Start motor forward. Set frequency first via async_set_frequency."""
        return await self._write_register(REG_CONTROL_CMD, CMD_RUN_FORWARD)

    async def async_run_reverse(self) -> bool:
        """Start motor reverse."""
        return await self._write_register(REG_CONTROL_CMD, CMD_RUN_REVERSE)

    async def async_stop(self) -> bool:
        """Stop motor."""
        return await self._write_register(REG_CONTROL_CMD, CMD_STOP)

    async def async_emergency_stop(self) -> bool:
        return await self.async_stop()

    async def async_reset_fault(self) -> bool:
        ok = await self._write_register(REG_CONTROL_CMD, CMD_RESET_FAULT)
        if ok:
            ok = await self._write_register(REG_CONTROL_CMD, CMD_STOP)
        return ok

    async def async_set_frequency(self, frequency_hz: float) -> bool:
        """Set output frequency (Hz). Also sends run-forward command so motor starts."""
        value = int(round(frequency_hz * 100))
        self._last_freq_value = value
        ok = await self._write_register(REG_FREQ_SETPOINT, value)
        if ok:
            ok = await self._write_register(REG_CONTROL_CMD, CMD_RUN_FORWARD)
        return ok

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
