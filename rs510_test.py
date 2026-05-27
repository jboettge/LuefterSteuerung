#!/usr/bin/env python3
from __future__ import annotations

"""Standalone Modbus RTU test script for the RSPro RS510 inverter.

RS510 Communication defaults (from manual):
  19200 baud, 8N1, Modbus RTU, slave address 1

Prerequisites — set on the RS510 keypad BEFORE running this script:
  P00-02 = 2   (Run source = Communication)
  P00-05 = 5   (Frequency source = Communication)

RS485 connector (CON2):
  Pin 1,3 = Data+   Pin 2,6 = Data-   Pin 7 = +5V   Pin 8 = GND

Usage:
    python rs510_test.py --port /dev/ttyACM0 status
    python rs510_test.py --port /dev/ttyACM0 freq=30.0
    python rs510_test.py --port /dev/ttyACM0 run
    python rs510_test.py --port /dev/ttyACM0 stop
    python rs510_test.py --port /dev/ttyACM0 reset
    python rs510_test.py --port /dev/ttyACM0 param=0008  (read P00-08)
"""

import argparse
import asyncio
import sys

import pymodbus
from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException

# pymodbus 2.x uses unit=, pymodbus 3.x uses slave=
_PMVER = tuple(int(x) for x in pymodbus.__version__.split(".")[:2])
_SLAVE_KEY = "slave" if _PMVER >= (3, 0) else "unit"

def _sk(slave_id: int) -> dict:
    """Return the correct slave/unit kwarg for the installed pymodbus version."""
    return {_SLAVE_KEY: slave_id}

# --- Register addresses (L510 manual, Appendix 3) ---
# 0x2501: Operation Signal (bit0=Run, bit1=Reverse, bit3=Reset)
# 0x2502: Frequency Command (0.01 Hz)
# 0x2520–0x2532: Monitoring block (status, fault, freq, voltage, current, temp)
REG_CONTROL_CMD   = 0x2501  # Operation Signal
REG_FREQ_SETPOINT = 0x2502  # Frequency Command (0.01 Hz)
REG_STATUS_WORD   = 0x2520  # Monitoring: status bits
REG_MONITOR_START = 0x2520
REG_MONITOR_COUNT = 19      # 0x2520–0x2532

CMD_STOP        = 0x0000  # all bits clear
CMD_RUN_FORWARD = 0x0001  # bit0=Run, bit1=0 (forward)
CMD_RUN_REVERSE = 0x0003  # bit0=Run, bit1=1 (reverse)
CMD_RESET_FAULT = 0x0008  # bit3=Reset (follow with CMD_STOP)

# Status word bits (0x2520)
STATUS_RUNNING = 0x0001  # bit 0
STATUS_REVERSE = 0x0002  # bit 1
STATUS_READY   = 0x0004  # bit 2
STATUS_FAULT   = 0x0008  # bit 3
STATUS_ALARM   = 0x0010  # bit 4 (data error)

FAULT_CODES = {
    0:  "Kein Fehler",
    1:  "OH    Übertemperatur",
    2:  "OC    Überstrom (gestoppt)",
    3:  "LV    Unterspannung",
    4:  "OV    Überspannung",
    6:  "bb    Externer Basisblock",
    7:  "CtEr  CPU-Fehler",
    8:  "PdEr  PID-Rückmeldung verloren",
    9:  "EPr   EEPROM-Fehler",
    11: "OL3   Drehmomenten-Überlast",
    12: "OL2   Umrichter Überlast",
    13: "OL1   Motor Überlast",
    14: "EFO   Externer Kommunikationsfehler",
    15: "E.S.  Externer Stopp",
    16: "LOC   Parameter gesperrt",
    18: "OC-C  Überstrom Konstantbetrieb",
    19: "OC-A  Überstrom Beschleunigung",
    20: "OC-d  Überstrom Verzögerung",
    21: "OC-S  Überstrom Start",
    23: "LV-C  Unterspannung im Betrieb",
    24: "OV-C  Überspannung Verzögerung",
    25: "OH-C  Übertemperatur im Betrieb",
    33: "Err6  Kommunikationsfehler",
    34: "Err7  Parameterkonflikt",
    40: "OVSP  Motor Überdrehzahl",
    41: "PF    Eingangsphase fehlt",
    44: "OH4   Motor Übertemperatur",
    46: "CL    Strombegrenzung",
}


async def connect(port: str, baud: int) -> AsyncModbusSerialClient:
    client = AsyncModbusSerialClient(
        port=port, baudrate=baud, bytesize=8, parity="N", stopbits=1, timeout=2,
    )
    ok = await client.connect()
    if not ok:
        print(f"FEHLER: Konnte {port} nicht öffnen.")
        sys.exit(1)
    print(f"Verbunden: {port} @ {baud} baud")
    return client


async def read_status(client: AsyncModbusSerialClient, slave: int) -> None:
    """Read monitoring registers 0x2520–0x2532 (L510 Appendix 3 layout)."""
    try:
        result = await client.read_holding_registers(
            address=REG_MONITOR_START, count=REG_MONITOR_COUNT, **_sk(slave),
        )
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")
        print("\nFallback: versuche Parameter-Register direkt zu lesen ...")
        await read_param_status(client, slave)
        return

    if result.isError():
        print(f"Lesefehler: {result}")
        print("\nFallback: versuche Parameter-Register direkt zu lesen ...")
        await read_param_status(client, slave)
        return

    r = result.registers
    # L510 Appendix 3 monitoring layout (offsets from 0x2520):
    # [0]=status, [1]=fault, [2]=DIO, [3]=setfreq, [4]=outfreq,
    # [5]=outvolt, [6]=dcvolt, [7]=outcurrent, [9]=outpower,
    # [17]=heatsinktemp, [18]=current%
    sw    = r[0]
    fault = r[1]
    print("─" * 52)
    print(f"  Status-Word (0x2520): 0x{sw:04X}")
    print(f"  Läuft:                {'Ja' if sw & STATUS_RUNNING else 'Nein'}")
    print(f"  Richtung:             {'Rückwärts' if sw & STATUS_REVERSE else 'Vorwärts'}")
    print(f"  Bereit:               {'Ja' if sw & STATUS_READY else 'Nein'}")
    print(f"  Fehler aktiv:         {'Ja' if sw & STATUS_FAULT else 'Nein'}")
    print(f"  Warnung:              {'Ja' if sw & STATUS_ALARM else 'Nein'}")
    print(f"  Fehlercode (0x2521):  {fault} – {FAULT_CODES.get(fault, 'unbekannt')}")
    print(f"  Sollfrequenz:         {r[3] / 100.0:.2f} Hz   (0x2523)")
    print(f"  Ausgangsfrequenz:     {r[4] / 100.0:.2f} Hz   (0x2524)")
    print(f"  Ausgangsspannung:     {r[5] / 10.0:.1f} V     (0x2525)")
    print(f"  Zwischenkreis-U:      {r[6]:.0f} V            (0x2526)")
    print(f"  Ausgangsstrom:        {r[7] / 10.0:.1f} A     (0x2527)")
    print(f"  Kühlkörpertemp.:      {r[17] / 10.0:.1f} °C  (0x2531)")
    print(f"  Strom-Verhältnis:     {r[18]} %               (0x2532)")
    print("─" * 52)
    print(f"\n  Rohdaten 0x2520–0x2532:")
    for i, v in enumerate(r):
        print(f"    0x{REG_MONITOR_START + i:04X} = {v:6d}  (0x{v:04X})")
    print("─" * 52)


async def read_param_status(client: AsyncModbusSerialClient, slave: int) -> None:
    """Fallback: read individual parameter registers."""
    params = [
        (0x0008, "P00-08 Frequenz-Sollwert", 100.0, "Hz"),
        (0x000C, "P00-12 Max-Frequenz", 100.0, "Hz"),
        (0x000D, "P00-13 Min-Frequenz", 100.0, "Hz"),
        (0x0002, "P00-02 Steuerquelle", 1, ""),
        (0x0005, "P00-05 Frequenzquelle", 1, ""),
        (0x0900, "P09-00 Slave-Adresse", 1, ""),
        (0x0902, "P09-02 Baudrate-Code", 1, ""),
    ]
    print("─" * 52)
    for addr, desc, div, unit in params:
        try:
            result = await client.read_holding_registers(
                address=addr, count=1, **_sk(slave),
            )
            if result.isError():
                print(f"  {desc:30s}  Fehler")
            else:
                val = result.registers[0]
                if div != 1:
                    print(f"  {desc:30s}  {val / div:.2f} {unit}")
                else:
                    print(f"  {desc:30s}  {val} {unit}")
        except Exception as exc:
            print(f"  {desc:30s}  {exc}")
    print("─" * 52)


async def write_cmd(client: AsyncModbusSerialClient, slave: int, cmd: int, label: str) -> None:
    try:
        result = await client.write_register(address=REG_CONTROL_CMD, value=cmd, **_sk(slave))
        if result.isError():
            print(f"Schreibfehler ({label}): {result}")
        else:
            print(f"OK: {label} (0x{cmd:04X}) gesendet an Register 0x{REG_CONTROL_CMD:04X}")
    except ModbusException as exc:
        print(f"Modbus-Fehler ({label}): {exc}")


async def set_frequency(client: AsyncModbusSerialClient, slave: int, freq_hz: float) -> None:
    """Write frequency to 0x2502 and send run-forward command to 0x2501."""
    value = int(round(freq_hz * 100))
    try:
        result = await client.write_register(address=REG_FREQ_SETPOINT, value=value, **_sk(slave))
        if result.isError():
            print(f"Schreibfehler Frequenz (0x{REG_FREQ_SETPOINT:04X}): {result}")
            return
        print(f"OK: Frequenz {freq_hz:.2f} Hz gesetzt (0x2502 = {value})")
        result2 = await client.write_register(
            address=REG_CONTROL_CMD, value=CMD_RUN_FORWARD, **_sk(slave)
        )
        if result2.isError():
            print(f"Schreibfehler Run-Befehl (0x{REG_CONTROL_CMD:04X}): {result2}")
        else:
            print(f"OK: Run-Befehl gesendet (0x2501 = {CMD_RUN_FORWARD})")
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")


async def read_input_registers(client: AsyncModbusSerialClient, slave: int, start_hex: str, count: int) -> None:
    """FC 04: read input registers (separate address space from holding registers)."""
    addr = int(start_hex, 16)
    try:
        result = await client.read_input_registers(address=addr, count=count, **_sk(slave))
        if result.isError():
            print(f"FC04 Lesefehler ab 0x{addr:04X}: {result}")
        else:
            print(f"FC04 Input-Register ab 0x{addr:04X}:")
            print("─" * 52)
            for i, v in enumerate(result.registers):
                print(f"  0x{addr + i:04X} = {v:6d}  (0x{v:04X})")
            print("─" * 52)
    except ModbusException as exc:
        print(f"Modbus-Fehler FC04: {exc}")


async def write_coil(client: AsyncModbusSerialClient, slave: int, addr_hex: str, on: bool) -> None:
    """FC 05: write single coil (discrete output)."""
    addr = int(addr_hex, 16)
    try:
        result = await client.write_coil(address=addr, value=on, **_sk(slave))
        if result.isError():
            print(f"FC05 Schreibfehler Coil 0x{addr:04X}: {result}")
        else:
            print(f"OK: FC05 Coil 0x{addr:04X} = {'EIN' if on else 'AUS'}")
    except ModbusException as exc:
        print(f"Modbus-Fehler FC05: {exc}")


async def read_param(client: AsyncModbusSerialClient, slave: int, addr_hex: str) -> None:
    addr = int(addr_hex, 16)
    try:
        result = await client.read_holding_registers(address=addr, count=1, **_sk(slave))
        if result.isError():
            print(f"Lesefehler Register 0x{addr:04X}: {result}")
        else:
            val = result.registers[0]
            print(f"Register 0x{addr:04X} = {val} (0x{val:04X})")
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")


async def run_heartbeat(
    client: AsyncModbusSerialClient, slave: int, freq_hz: float, interval: float = 1.0,
) -> None:
    """Keep connection open and refresh 0x2502 (freq) + 0x2501 (run) every interval seconds.

    Use this when P09-06>0 causes the VFD to stop on communication timeout.
    Press Ctrl+C to stop (sends stop command before exiting).
    """
    freq_value = int(round(freq_hz * 100))
    print(f"Heartbeat-Modus: {freq_hz:.2f} Hz, Refresh alle {interval:.1f} s — Ctrl+C zum Stoppen")
    try:
        iteration = 0
        while True:
            r1 = await client.write_register(address=REG_FREQ_SETPOINT, value=freq_value, **_sk(slave))
            r2 = await client.write_register(address=REG_CONTROL_CMD, value=CMD_RUN_FORWARD, **_sk(slave))
            ok = not r1.isError() and not r2.isError()
            if iteration % 5 == 0:
                status = "✓" if ok else "✗"
                print(f"  [{iteration:4d}] {status} 0x2502={freq_value} 0x2501={CMD_RUN_FORWARD}")
            iteration += 1
            await asyncio.sleep(interval)
    except KeyboardInterrupt:
        print("\nStoppe Motor ...")
        await client.write_register(address=REG_CONTROL_CMD, value=CMD_STOP, **_sk(slave))
        print("Stopp-Befehl gesendet.")


async def write_param(client: AsyncModbusSerialClient, slave: int, addr_hex: str, value: int) -> None:
    addr = int(addr_hex, 16)
    try:
        result = await client.write_register(address=addr, value=value, **_sk(slave))
        if result.isError():
            print(f"Schreibfehler Register 0x{addr:04X}: {result}")
        else:
            print(f"OK: Register 0x{addr:04X} = {value} (0x{value:04X}) geschrieben")
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")


async def write_param_fc16(client: AsyncModbusSerialClient, slave: int, addr_hex: str, value: int) -> None:
    """Write a single register using FC 16 (write_registers) instead of FC 06.

    Some VFDs reject FC 06 for the control register block but accept FC 16.
    """
    addr = int(addr_hex, 16)
    try:
        result = await client.write_registers(address=addr, values=[value], **_sk(slave))
        if result.isError():
            print(f"Schreibfehler FC16 Register 0x{addr:04X}: {result}")
        else:
            print(f"OK: FC16 Register 0x{addr:04X} = {value} (0x{value:04X}) geschrieben")
    except ModbusException as exc:
        print(f"Modbus-Fehler FC16: {exc}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="RSPro RS510 Modbus RTU Testskript")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serieller Port")
    parser.add_argument("--baud", type=int, default=19200, help="Baudrate (Default: 19200)")
    parser.add_argument("--slave", type=int, default=1, help="Modbus Slave-Adresse (1–32)")
    parser.add_argument(
        "action", nargs="?", default="status",
        help="status | run | run_rev | stop | emergency | reset | freq=<Hz> | param=<hex> | write=<hex>,<val>",
    )
    args = parser.parse_args()

    client = await connect(args.port, args.baud)
    try:
        action = args.action.lower()
        if action == "status":
            await read_status(client, args.slave)
        elif action == "run":
            await write_cmd(client, args.slave, CMD_RUN_FORWARD, "Vorwärts starten")
        elif action == "run_rev":
            await write_cmd(client, args.slave, CMD_RUN_REVERSE, "Rückwärts starten")
        elif action == "stop":
            await write_cmd(client, args.slave, CMD_STOP, "Stopp")
        elif action == "emergency":
            await write_cmd(client, args.slave, CMD_STOP, "Not-Stopp")
        elif action == "reset":
            await write_cmd(client, args.slave, CMD_RESET_FAULT, "Fehler zurücksetzen (Reset)")
            await write_cmd(client, args.slave, CMD_STOP, "Stopp nach Reset")
        elif action.startswith("freq="):
            freq = float(action.split("=", 1)[1])
            await set_frequency(client, args.slave, freq)
        elif action.startswith("loop="):
            # Keep connection open and refresh freq+run every second (Heartbeat)
            freq = float(action.split("=", 1)[1])
            await run_heartbeat(client, args.slave, freq)
        elif action.startswith("param="):
            addr_hex = action.split("=", 1)[1]
            await read_param(client, args.slave, addr_hex)
        elif action.startswith("write="):
            parts = action.split("=", 1)[1].split(",", 1)
            if len(parts) != 2:
                print("Syntax: write=<hex-addr>,<int-wert>  z.B. write=3000,18")
                sys.exit(1)
            addr_hex, raw_val = parts
            val = int(raw_val, 0)  # supports 0x... or decimal
            await write_param(client, args.slave, addr_hex, val)
        elif action.startswith("write16="):
            # FC 16 (write multiple registers) – some VFDs reject FC 06 for control blocks
            parts = action.split("=", 1)[1].split(",", 1)
            if len(parts) != 2:
                print("Syntax: write16=<hex-addr>,<int-wert>  z.B. write16=3000,18")
                sys.exit(1)
            addr_hex, raw_val = parts
            val = int(raw_val, 0)
            await write_param_fc16(client, args.slave, addr_hex, val)
        elif action.startswith("scan="):
            parts = action.split("=", 1)[1].split(",", 1)
            if len(parts) != 2:
                print("Syntax: scan=<hex-start>,<count>  z.B. scan=3000,32")
                sys.exit(1)
            start_addr = int(parts[0], 16)
            count = int(parts[1], 0)
            print(f"FC03 Lese {count} Register ab 0x{start_addr:04X} ...")
            print("─" * 52)
            try:
                result = await client.read_holding_registers(
                    address=start_addr, count=count, slave=args.slave,
                )
                if result.isError():
                    print(f"Fehler: {result}")
                else:
                    for i, v in enumerate(result.registers):
                        print(f"  0x{start_addr + i:04X} = {v:6d}  (0x{v:04X})")
            except ModbusException as exc:
                print(f"Modbus-Fehler: {exc}")
            print("─" * 52)
        elif action.startswith("fc04="):
            # FC 04 read input registers
            parts = action.split("=", 1)[1].split(",", 1)
            if len(parts) != 2:
                print("Syntax: fc04=<hex-start>,<count>  z.B. fc04=0000,16")
                sys.exit(1)
            await read_input_registers(client, args.slave, parts[0], int(parts[1], 0))
        elif action.startswith("coil="):
            # FC 05 write coil
            parts = action.split("=", 1)[1].split(",", 1)
            if len(parts) != 2:
                print("Syntax: coil=<hex-addr>,<0|1>  z.B. coil=0000,1")
                sys.exit(1)
            await write_coil(client, args.slave, parts[0], parts[1].strip() != "0")
        else:
            print(f"Unbekannte Aktion: {args.action}")
            print("Aktionen: status | run | run_rev | stop | emergency | reset | freq=<Hz>")
            print("          param=<hex> | write=<hex>,<val> | write16=<hex>,<val>")
            print("          scan=<hex>,<count> | fc04=<hex>,<count> | coil=<hex>,<0|1>")
            sys.exit(1)
    finally:
        client.close()
        print("Verbindung getrennt.")


if __name__ == "__main__":
    asyncio.run(main())
