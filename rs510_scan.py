#!/usr/bin/env python3
from __future__ import annotations

"""Diagnose-/Scan-Tool für die RS510 Modbus-Verbindung.

RS510 Communication defaults:
  19200 baud, 8N1, Modbus RTU, slave address 1 (P09-00 to P09-05)

RS485 Stecker (CON2):
  Pin 1,3 = Data+   Pin 2,6 = Data-   Pin 7 = +5V   Pin 8 = GND

Verwendung:
    python rs510_scan.py --port /dev/ttyACM0
    python rs510_scan.py --port /dev/ttyACM0 --quick
    python rs510_scan.py --port /dev/ttyACM0 --probe 1
"""

import argparse
import asyncio
import sys

from pymodbus.client import AsyncModbusSerialClient

# RS510 supports: 4800, 9600, 19200 (default), 38400
BAUDRATES_FULL = [19200, 9600, 38400, 4800]
BAUDRATES_QUICK = [19200, 9600, 38400]
PARITIES = [("N", 1), ("E", 1), ("O", 1), ("N", 2)]
SLAVE_RANGE = range(1, 33)  # RS510 supports 1-32

# Registers to try when probing
PROBE_REGISTERS = [
    # Dedicated monitoring registers (Delta VFD platform)
    (0x2100, "Status Word (0x2100)"),
    (0x2101, "Sollfrequenz (0x2101)"),
    (0x2102, "Ausgangsfrequenz (0x2102)"),
    # Parameter registers (guaranteed to exist)
    (0x0000, "P00-00 Steuermodus"),
    (0x0002, "P00-02 Steuerquelle"),
    (0x0005, "P00-05 Frequenzquelle"),
    (0x0008, "P00-08 Kommunikationsfrequenz"),
    (0x000C, "P00-12 Max-Frequenz"),
    (0x0900, "P09-00 Slave-Adresse"),
    (0x0902, "P09-02 Baudrate-Code"),
    # Alternative monitoring register ranges
    (0x2000, "Steuerregister (0x2000)"),
    (0x2001, "Frequenz-Sollwert (0x2001)"),
    (0x3000, "Alt. Status (0x3000)"),
]


async def try_read(
    port: str, baud: int, parity: str, stopbits: int, slave: int,
    address: int = 0x0000, timeout: float = 0.3,
) -> int | None:
    """Try reading a single register. Returns the value on success, None on failure."""
    client = AsyncModbusSerialClient(
        port=port, baudrate=baud, bytesize=8, parity=parity,
        stopbits=stopbits, timeout=timeout, retries=0,
    )
    try:
        if not await client.connect():
            return None
        result = await client.read_holding_registers(
            address=address, count=1, slave=slave,
        )
        if result is None or result.isError():
            return None
        return result.registers[0]
    except Exception:
        return None
    finally:
        client.close()


async def scan(port: str, quick: bool) -> None:
    bauds = BAUDRATES_QUICK if quick else BAUDRATES_FULL
    print(f"Scanne {port} ...")
    print(f"  Baudrates: {bauds}")
    print(f"  Parities:  N/E/O + Stop 1/2")
    print(f"  Slaves:    1–32")
    print()
    print(f"{'Baud':>7}  {'Par':>3}  {'Stop':>4}  {'Slave':>5}  Ergebnis")
    print("─" * 52)

    found_any = False
    # Try P00-00 (register 0x0000) which always exists
    for baud in bauds:
        for parity, stopbits in PARITIES:
            for slave in SLAVE_RANGE:
                val = await try_read(port, baud, parity, stopbits, slave, address=0x0000)
                if val is not None:
                    found_any = True
                    print(
                        f"{baud:>7}  {parity:>3}  {stopbits:>4}  {slave:>5}  "
                        f"\033[32m✓ Antwort! P00-00={val}\033[0m"
                    )
        print(f"  ── {baud} baud durchsucht ──")

    print()
    if found_any:
        print("Funktionierende Kombination(en) gefunden – siehe oben.")
        print("Nutze: python rs510_test.py --port ... --baud ... --slave ... status")
    else:
        print("Keine Antwort bei keiner Kombination.")
        print()
        print("Prüfen:")
        print("  1. A/B (Data+/Data-) am RS485-Adapter vertauschen")
        print("  2. RS510 CON2: Pin 1,3 = Data+ / Pin 2,6 = Data-")
        print("  3. P09-01 = 0 (Modbus RTU) am Umrichter prüfen")
        print("  4. 120 Ω Terminierung am Bus-Ende?")
        print("  5. RS485-Adapter funktionsfähig? (LED-Blinken prüfen)")


async def probe(port: str, slave: int, baud: int) -> None:
    print(f"Probe Register bei Slave {slave} @ {baud} baud ...\n")
    print(f"{'Adresse':>8}  {'Beschreibung':45s}  Ergebnis")
    print("─" * 75)
    for addr, desc in PROBE_REGISTERS:
        val = await try_read(port, baud, "N", 1, slave, address=addr, timeout=0.5)
        if val is not None:
            print(f"  0x{addr:04X}  {desc:45s}  \033[32m✓ = {val} (0x{val:04X})\033[0m")
        else:
            print(f"  0x{addr:04X}  {desc:45s}  \033[31m✗\033[0m")
    print()
    print("Hinweis: Falls nur Parameter-Register (0x0000-0x0D08) antworten,")
    print("aber 0x2000/0x2100 nicht, nutzt der RS510 ggf. nur Parameter-Zugriff.")


async def main() -> None:
    parser = argparse.ArgumentParser(description="RS510 Modbus-Bus-Scanner")
    parser.add_argument("--port", default="/dev/ttyACM0", help="Serieller Port")
    parser.add_argument("--quick", action="store_true", help="Nur 19200/9600/38400 testen")
    parser.add_argument("--probe", type=int, metavar="SLAVE", help="Register-Probe bei bekanntem Slave")
    parser.add_argument("--baud", type=int, default=19200, help="Baudrate (Default: 19200)")
    args = parser.parse_args()

    if args.probe is not None:
        await probe(args.port, args.probe, args.baud)
    else:
        await scan(args.port, args.quick)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(130)
