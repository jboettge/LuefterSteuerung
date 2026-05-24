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

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException

# --- Register addresses (confirmed on RS510-2P7-SH1) ---
# P07-00 (0x0700): Run/Stop command  — 0=stop, 1=forward, 2=reverse
# P07-01 (0x0701): Frequency setpoint (0.01 Hz) — e.g. 1500 = 15.00 Hz
# P07-02 (0x0702): Run status readback (1=running forward)
# 0x3000+: read-only status block
# 0x2000/0x2001/0x2100+: do NOT exist on this device
REG_CONTROL_CMD   = 0x0700  # P07-00
REG_FREQ_SETPOINT = 0x0701  # P07-01
REG_STATUS_WORD   = 0x3000

CMD_STOP        = 0x0000
CMD_RUN_FORWARD = 0x0001
CMD_RUN_REVERSE = 0x0002
CMD_RESET_FAULT = 0x0000  # stop is the safest reset action on this device

FAULT_CODES = {
    0:  "Kein Fehler",
    1:  "OC-A  Überstrom Beschleunigung",
    2:  "OC-C  Überstrom Konstantbetrieb",
    3:  "OC-d  Überstrom Verzögerung",
    4:  "OC-S  Überstrom Start",
    5:  "OV-C  Überspannung",
    6:  "OH    Übertemperatur",
    7:  "OL1   Motor Überlast",
    8:  "OL2   Umrichter Überlast",
    9:  "OC    Überstrom Stopp",
    10: "CL    Strombegrenzung",
    11: "PF    Phase fehlt",
    12: "LV-C  Unterspannung",
    13: "OVSP  Überdrehzahl",
    14: "OH4   Motor Überhitzung",
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
    """Read monitoring registers 0x2100–0x210C (Delta VFD-EL layout)."""
    try:
        result = await client.read_holding_registers(
            address=0x2100, count=13, slave=slave,
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
    # Delta VFD-EL layout:
    # [0]=0x2100 fault, [1]=0x2101 status, [2]=0x2102 set freq,
    # [3]=0x2103 out freq, [4]=0x2104 current, [5-7]=reserved/PID,
    # [8]=0x2108 DC bus V, [9]=0x2109 out V, [10]=0x210A temp,
    # [11]=0x210B torque, [12]=0x210C speed
    fault = r[0]
    sw = r[1]
    print("─" * 52)
    print(f"  Fehlercode (0x2100):  {fault} – {FAULT_CODES.get(fault, 'unbekannt')}")
    print(f"  Status-Word (0x2101): 0x{sw:04X}")
    print(f"  Bereit:               {'Ja' if sw & STATUS_READY else 'Nein'}")
    print(f"  Läuft:                {'Ja' if sw & STATUS_RUNNING else 'Nein'}")
    print(f"  Richtung:             {'Rückwärts' if sw & STATUS_REVERSE else 'Vorwärts'}")
    print(f"  Fehler aktiv:         {'Ja' if sw & STATUS_FAULT else 'Nein'}")
    print(f"  Warnung:              {'Ja' if sw & STATUS_ALARM else 'Nein'}")
    print(f"  Sollfrequenz:         {r[2] / 100.0:.2f} Hz   (0x2102)")
    print(f"  Ausgangsfrequenz:     {r[3] / 100.0:.2f} Hz   (0x2103)")
    print(f"  Ausgangsstrom:        {r[4] / 100.0:.2f} A    (0x2104)")
    print(f"  Zwischenkreis-U:      {r[8] / 10.0:.1f} V     (0x2108)")
    print(f"  Ausgangsspannung:     {r[9] / 10.0:.1f} V     (0x2109)")
    print(f"  Kühlkörpertemp.:      {r[10]} °C              (0x210A)")
    print(f"  Drehmoment:           {r[11]} %               (0x210B)")
    print(f"  Motordrehzahl:        {r[12]} RPM             (0x210C)")
    print("─" * 52)
    print(f"\n  Rohdaten 0x2100–0x210C:")
    for i, v in enumerate(r):
        print(f"    0x{0x2100 + i:04X} = {v:5d} (0x{v:04X})")
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
                address=addr, count=1, slave=slave,
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
        result = await client.write_register(address=REG_CONTROL_CMD, value=cmd, slave=slave)
        if result.isError():
            print(f"Schreibfehler ({label}): {result}")
        else:
            print(f"OK: {label} (0x{cmd:04X}) gesendet an Register 0x2000")
    except ModbusException as exc:
        print(f"Modbus-Fehler ({label}): {exc}")


async def set_frequency(client: AsyncModbusSerialClient, slave: int, freq_hz: float) -> None:
    """Write frequency to P07-01 and send run-forward command to P07-00."""
    value = int(round(freq_hz * 100))
    try:
        result = await client.write_register(address=REG_FREQ_SETPOINT, value=value, slave=slave)
        if result.isError():
            print(f"Schreibfehler Frequenz (0x{REG_FREQ_SETPOINT:04X}): {result}")
            return
        print(f"OK: Frequenz {freq_hz:.2f} Hz gesetzt (P07-01 = {value})")
        # Also send run command so motor starts immediately
        result2 = await client.write_register(
            address=REG_CONTROL_CMD, value=CMD_RUN_FORWARD, slave=slave
        )
        if result2.isError():
            print(f"Schreibfehler Run-Befehl (0x{REG_CONTROL_CMD:04X}): {result2}")
        else:
            print(f"OK: Run-Befehl gesendet (P07-00 = {CMD_RUN_FORWARD})")
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")


async def read_input_registers(client: AsyncModbusSerialClient, slave: int, start_hex: str, count: int) -> None:
    """FC 04: read input registers (separate address space from holding registers)."""
    addr = int(start_hex, 16)
    try:
        result = await client.read_input_registers(address=addr, count=count, slave=slave)
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
        result = await client.write_coil(address=addr, value=on, slave=slave)
        if result.isError():
            print(f"FC05 Schreibfehler Coil 0x{addr:04X}: {result}")
        else:
            print(f"OK: FC05 Coil 0x{addr:04X} = {'EIN' if on else 'AUS'}")
    except ModbusException as exc:
        print(f"Modbus-Fehler FC05: {exc}")


async def read_param(client: AsyncModbusSerialClient, slave: int, addr_hex: str) -> None:
    addr = int(addr_hex, 16)
    try:
        result = await client.read_holding_registers(address=addr, count=1, slave=slave)
        if result.isError():
            print(f"Lesefehler Register 0x{addr:04X}: {result}")
        else:
            val = result.registers[0]
            print(f"Register 0x{addr:04X} = {val} (0x{val:04X})")
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")


async def write_param(client: AsyncModbusSerialClient, slave: int, addr_hex: str, value: int) -> None:
    addr = int(addr_hex, 16)
    try:
        result = await client.write_register(address=addr, value=value, slave=slave)
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
        result = await client.write_registers(address=addr, values=[value], slave=slave)
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
            await write_cmd(client, args.slave, CMD_STOP, "Fehler zurücksetzen (Stopp)")
        elif action.startswith("freq="):
            freq = float(action.split("=", 1)[1])
            await set_frequency(client, args.slave, freq)
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
