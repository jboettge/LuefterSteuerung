"""Async Modbus RTU client for the RSPro RS511 frequency inverter."""

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
    CMD_EMERGENCY_STOP,
    REG_CONTROL_CMD,
    REG_DC_VOLTAGE,
    REG_FAULT_CODE,
    REG_FREQ_SETPOINT,
    REG_MOTOR_SPEED,
    REG_OUT_CURRENT,
    REG_OUT_FREQ,
    REG_OUT_VOLTAGE,
    REG_STATUS_WORD,
    STATUS_BIT_FAULT,
    STATUS_BIT_READY,
    STATUS_BIT_REVERSE,
    STATUS_BIT_RUNNING,
)

_LOGGER = logging.getLogger(__name__)

# Number of consecutive read failures before marking the device unavailable
_MAX_FAILURES = 3


@dataclass
class RS511Status:
    """Snapshot of all RS511 status registers."""

    is_running: bool
    is_reverse: bool
    has_fault: bool
    is_ready: bool
    output_frequency_hz: float   # Hz
    output_current_a: float      # A
    dc_voltage_v: float          # V
    output_voltage_v: float      # V
    motor_speed_rpm: int         # RPM
    fault_code: int
    status_word: int


class RS511ModbusClient:
    """Async Modbus RTU wrapper for the RSPro RS511 inverter.

    Uses pymodbus 3.x AsyncModbusSerialClient internally.
    All public methods are coroutines and safe to call from HA's event loop.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
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

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    async def async_connect(self) -> bool:
        """Open the serial connection. Returns True on success."""
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
                _LOGGER.debug("RS511 connected on %s @ %d baud", self._port, self._baudrate)
                self._consecutive_failures = 0
            else:
                _LOGGER.error("RS511: could not open %s", self._port)
            return connected
        except Exception as exc:
            _LOGGER.error("RS511 connect error: %s", exc)
            return False

    async def async_disconnect(self) -> None:
        """Close the serial connection."""
        if self._client:
            self._client.close()
            self._client = None
            _LOGGER.debug("RS511 disconnected")

    @property
    def available(self) -> bool:
        """True when the device is reachable (no recent consecutive failures)."""
        return (
            self._client is not None
            and self._consecutive_failures < _MAX_FAILURES
        )

    # ------------------------------------------------------------------
    # Status polling
    # ------------------------------------------------------------------

    async def async_read_status(self) -> Optional[RS511Status]:
        """Read all status registers in a single request. Returns None on error."""
        async with self._lock:
            if self._client is None:
                return None
            try:
                # Read 7 consecutive holding registers starting at REG_STATUS_WORD
                result = await self._client.read_holding_registers(
                    address=REG_STATUS_WORD,
                    count=7,
                    slave=self._slave,
                )
                if result.isError():
                    self._on_failure("read_holding_registers returned error: %s", result)
                    return None

                regs = result.registers
                self._consecutive_failures = 0
                status_word = regs[0]
                return RS511Status(
                    is_running=bool(status_word & STATUS_BIT_RUNNING),
                    is_reverse=bool(status_word & STATUS_BIT_REVERSE),
                    has_fault=bool(status_word & STATUS_BIT_FAULT),
                    is_ready=bool(status_word & STATUS_BIT_READY),
                    output_frequency_hz=regs[1] / 100.0,
                    output_current_a=regs[2] / 100.0,
                    dc_voltage_v=regs[3] / 10.0,
                    output_voltage_v=regs[4] / 10.0,
                    motor_speed_rpm=regs[5],
                    fault_code=regs[6],
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
        """Start the inverter in forward direction."""
        return await self._write_control(CMD_RUN_FORWARD)

    async def async_run_reverse(self) -> bool:
        """Start the inverter in reverse direction."""
        return await self._write_control(CMD_RUN_REVERSE)

    async def async_stop(self) -> bool:
        """Stop the inverter (ramp-down deceleration)."""
        return await self._write_control(CMD_STOP)

    async def async_emergency_stop(self) -> bool:
        """Immediately cut output (free-run stop)."""
        return await self._write_control(CMD_EMERGENCY_STOP)

    async def async_reset_fault(self) -> bool:
        """Reset the active fault and return to ready state."""
        return await self._write_control(CMD_RESET_FAULT)

    async def async_set_frequency(self, frequency_hz: float) -> bool:
        """Set the output frequency setpoint in Hz (e.g. 25.0 → 2500 register value)."""
        value = int(round(frequency_hz * 100))
        return await self._write_register(REG_FREQ_SETPOINT, value)

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
                    address=address,
                    value=value,
                    slave=self._slave,
                )
                if result.isError():
                    _LOGGER.error(
                        "RS511: write_register 0x%04X = %d failed: %s",
                        address,
                        value,
                        result,
                    )
                    return False
                return True
            except ModbusException as exc:
                _LOGGER.error("RS511: Modbus exception writing 0x%04X: %s", address, exc)
                return False
            except Exception as exc:
                _LOGGER.error("RS511: unexpected error writing 0x%04X: %s", address, exc)
                return False

    def _on_failure(self, msg: str, *args: object) -> None:
        self._consecutive_failures += 1
        _LOGGER.warning("RS511 (%d/%d): " + msg, self._consecutive_failures, _MAX_FAILURES, *args)
