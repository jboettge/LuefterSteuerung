#!/usr/bin/env python3
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

# --- Register addresses (Delta VFD platform) ---
REG_CONTROL_CMD   = 0x2000
REG_FREQ_SETPOINT = 0x2001
REG_STATUS_WORD   = 0x2100

# Confirmed by LinuxCNC vfdb_vfd.c and Delta VFD documentation
CMD_STOP          = 0x0001  # Bit 0
CMD_RUN_FORWARD   = 0x0012  # Bit 1 (RUN) + Bit 4 (FWD)
CMD_RUN_REVERSE   = 0x0022  # Bit 1 (RUN) + Bit 5 (REV)
CMD_RESET_FAULT   = 0x2000  # Bit 13
CMD_EMERGENCY     = 0x1000  # Bit 12

# Status word bits
STATUS_READY   = 0x0001
STATUS_RUNNING = 0x0002
STATUS_REVERSE = 0x0004
STATUS_FAULT   = 0x0008
STATUS_ALARM   = 0x0010

# Parameter addresses
PARAM_COMM_FREQ = 0x0008  # P00-08: communication frequency (0.01 Hz)

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
    value = int(round(freq_hz * 100))
    # Try dedicated register first, fall back to P00-08
    try:
        result = await client.write_register(address=REG_FREQ_SETPOINT, value=value, slave=slave)
        if result.isError():
            print(f"Register 0x2001 nicht verfügbar, nutze P00-08 (0x0008) ...")
            result = await client.write_register(address=PARAM_COMM_FREQ, value=value, slave=slave)
            if result.isError():
                print(f"Schreibfehler: {result}")
                return
            print(f"OK: Frequenz {freq_hz:.2f} Hz via P00-08 gesetzt (Wert: {value})")
        else:
            print(f"OK: Frequenz {freq_hz:.2f} Hz via 0x2001 gesetzt (Wert: {value})")
    except ModbusException as exc:
        print(f"Modbus-Fehler: {exc}")


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


async def main() -> None:
    parser = argparse.ArgumentParser(description="RSPro RS510 Modbus RTU Testskript")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serieller Port")
    parser.add_argument("--baud", type=int, default=19200, help="Baudrate (Default: 19200)")
    parser.add_argument("--slave", type=int, default=1, help="Modbus Slave-Adresse (1–32)")
    parser.add_argument(
        "action", nargs="?", default="status",
        help="status | run | run_rev | stop | emergency | reset | freq=<Hz> | param=<hex>",
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
            await write_cmd(client, args.slave, CMD_EMERGENCY, "Not-Stopp")
        elif action == "reset":
            await write_cmd(client, args.slave, CMD_RESET_FAULT, "Fehler zurücksetzen")
        elif action.startswith("freq="):
            freq = float(action.split("=", 1)[1])
            await set_frequency(client, args.slave, freq)
        elif action.startswith("param="):
            addr_hex = action.split("=", 1)[1]
            await read_param(client, args.slave, addr_hex)
        else:
            print(f"Unbekannte Aktion: {args.action}")
            print("Aktionen: status | run | run_rev | stop | emergency | reset | freq=<Hz> | param=<hex>")
            sys.exit(1)
    finally:
        client.close()
        print("Verbindung getrennt.")


if __name__ == "__main__":
    asyncio.run(main())
