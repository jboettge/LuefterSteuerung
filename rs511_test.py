#!/usr/bin/env python3
"""Standalone Modbus RTU test script for the RSPro RS511 inverter.

Verwendung:
    python rs511_test.py --port /dev/ttyUSB0 --baud 9600 --slave 1 [--action status|run|stop|freq=25.0|reset]

Beispiele:
    python rs511_test.py --port /dev/ttyUSB0 status
    python rs511_test.py --port /dev/ttyUSB0 freq=30.0
    python rs511_test.py --port /dev/ttyUSB0 run
    python rs511_test.py --port /dev/ttyUSB0 stop
    python rs511_test.py --port /dev/ttyUSB0 reset
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Allow running from the project root without installing
sys.path.insert(0, str(Path(__file__).parent))

from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException

# -----------------------------------------------------------------------
# RS511 register / command constants (kept local to avoid HA imports)
# -----------------------------------------------------------------------
REG_CONTROL_CMD = 0x2000
REG_FREQ_SETPOINT = 0x2001
REG_STATUS_WORD = 0x3000

CMD_RUN_FORWARD = 0x0001
CMD_RUN_REVERSE = 0x0002
CMD_STOP = 0x0003
CMD_EMERGENCY_STOP = 0x0005
CMD_RESET_FAULT = 0x0006

STATUS_BIT_RUNNING = 0x0001
STATUS_BIT_REVERSE = 0x0002
STATUS_BIT_FAULT = 0x0004
STATUS_BIT_READY = 0x0008

FAULT_CODES = {
    0: "Kein Fehler",
    1: "Überstrom Beschleunigung",
    2: "Überstrom Verzögerung",
    3: "Überstrom Konstantbetrieb",
    4: "Überspannung Beschleunigung",
    5: "Überspannung Verzögerung",
    6: "Überspannung Konstantbetrieb",
    7: "Zwischenkreis-Überspannung",
    8: "Steuerungsversorgung Fehler",
    9: "Unterspannung",
    10: "Umrichter Überlast",
    11: "Motor Überlast",
    12: "Eingangsphase fehlt",
    13: "Ausgangsphase fehlt",
    14: "Kühlkörper Überhitzung",
    15: "Externe Störung",
    16: "Kommunikationsfehler",
    17: "Kontaktorfehler",
    18: "Stromerfassungsfehler",
    19: "Motor Überhitzung",
    23: "Kurzschluss Fehler",
}


async def connect(port: str, baud: int) -> AsyncModbusSerialClient:
    client = AsyncModbusSerialClient(
        port=port,
        baudrate=baud,
        bytesize=8,
        parity="N",
        stopbits=1,
        timeout=2,
    )
    ok = await client.connect()
    if not ok:
        print(f"FEHLER: Konnte {port} nicht öffnen.")
        sys.exit(1)
    print(f"Verbunden: {port} @ {baud} baud")
    return client


async def read_status(client: AsyncModbusSerialClient, slave: int) -> None:
    result = await client.read_holding_registers(
        address=REG_STATUS_WORD, count=7, slave=slave
    )
    if result.isError():
        print(f"Lesefehler: {result}")
        return

    r = result.registers
    sw = r[0]
    freq_hz = r[1] / 100.0
    current_a = r[2] / 100.0
    dc_v = r[3] / 10.0
    out_v = r[4] / 10.0
    rpm = r[5]
    fault = r[6]

    running = bool(sw & STATUS_BIT_RUNNING)
    reverse = bool(sw & STATUS_BIT_REVERSE)
    fault_bit = bool(sw & STATUS_BIT_FAULT)
    ready = bool(sw & STATUS_BIT_READY)

    print("─" * 48)
    print(f"  Status-Word:          0x{sw:04X}")
    print(f"  Läuft:                {'Ja' if running else 'Nein'}")
    print(f"  Richtung:             {'Rückwärts' if reverse else 'Vorwärts'}")
    print(f"  Bereit:               {'Ja' if ready else 'Nein'}")
    print(f"  Fehler aktiv:         {'Ja' if fault_bit else 'Nein'}")
    print(f"  Ausgangsfrequenz:     {freq_hz:.2f} Hz")
    print(f"  Ausgangsstrom:        {current_a:.2f} A")
    print(f"  Zwischenkreis-U:      {dc_v:.1f} V")
    print(f"  Ausgangsspannung:     {out_v:.1f} V")
    print(f"  Motordrehzahl:        {rpm} RPM")
    print(f"  Fehlercode:           {fault} – {FAULT_CODES.get(fault, 'unbekannt')}")
    print("─" * 48)


async def write_cmd(client: AsyncModbusSerialClient, slave: int, cmd: int, label: str) -> None:
    result = await client.write_register(address=REG_CONTROL_CMD, value=cmd, slave=slave)
    if result.isError():
        print(f"Schreibfehler ({label}): {result}")
    else:
        print(f"OK: {label} (0x{cmd:04X}) gesendet")


async def set_frequency(client: AsyncModbusSerialClient, slave: int, freq_hz: float) -> None:
    value = int(round(freq_hz * 100))
    result = await client.write_register(address=REG_FREQ_SETPOINT, value=value, slave=slave)
    if result.isError():
        print(f"Schreibfehler (Frequenz-Sollwert): {result}")
    else:
        print(f"OK: Frequenz-Sollwert auf {freq_hz:.2f} Hz gesetzt (Register-Wert: {value})")


async def main() -> None:
    parser = argparse.ArgumentParser(description="RSPro RS511 Modbus RTU Testskript")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serieller Port")
    parser.add_argument("--baud", type=int, default=9600, help="Baudrate")
    parser.add_argument("--slave", type=int, default=1, help="Modbus Slave-Adresse (1–247)")
    parser.add_argument(
        "action",
        nargs="?",
        default="status",
        help="Aktion: status | run | run_rev | stop | emergency | reset | freq=<Hz>",
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
            await write_cmd(client, args.slave, CMD_EMERGENCY_STOP, "Not-Stopp")
        elif action == "reset":
            await write_cmd(client, args.slave, CMD_RESET_FAULT, "Fehler zurücksetzen")
        elif action.startswith("freq="):
            freq_str = action.split("=", 1)[1]
            try:
                freq = float(freq_str)
            except ValueError:
                print(f"Ungültige Frequenz: {freq_str}")
                sys.exit(1)
            await set_frequency(client, args.slave, freq)
        else:
            print(f"Unbekannte Aktion: {args.action}")
            print("Mögliche Aktionen: status | run | run_rev | stop | emergency | reset | freq=<Hz>")
            sys.exit(1)
    finally:
        client.close()
        print("Verbindung getrennt.")


if __name__ == "__main__":
    asyncio.run(main())
