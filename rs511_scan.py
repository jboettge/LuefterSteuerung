#!/usr/bin/env python3
"""Diagnose-/Scan-Tool für die RS511 Modbus-Verbindung.

Ein 'No response received' bedeutet, dass kein Slave auf der Leitung antwortet.
Mögliche Ursachen (nach Häufigkeit):
  1. A/B-Adern (D+/D-) vertauscht
  2. Falsche Slave-Adresse (Default in Werkseinstellung ist nicht immer 1)
  3. Falsche Baudrate (nicht immer 9600)
  4. Falsche Parität / Stopbits (manche Geräte nutzen 8E1 statt 8N1)
  5. Modbus im Umrichter nicht aktiv – Steuer-/Frequenzquelle muss auf
     Kommunikation umgestellt werden
  6. Fehlende 120-Ω-Terminierung am Busende
  7. RS485-USB-Adapter ohne automatische Sende-/Empfangs-Umschaltung

Verwendung:
    python rs511_scan.py --port /dev/ttyACM0
    python rs511_scan.py --port /dev/ttyACM0 --quick     # nur 9600/19200/38400
    python rs511_scan.py --port /dev/ttyACM0 --probe 1   # bei Slave 1 mehrere
                                                          # Register-Adressen testen
"""

import argparse
import asyncio
import sys

from pymodbus.client import AsyncModbusSerialClient

DEFAULT_BAUDRATES_FULL = [9600, 19200, 38400, 57600, 115200, 4800, 2400]
DEFAULT_BAUDRATES_QUICK = [9600, 19200, 38400]
PARITIES = [("N", 1), ("E", 1), ("O", 1), ("N", 2)]
SLAVE_RANGE = range(1, 33)  # 1..32

# Mögliche Status-/Test-Register, die viele VFDs lesbar machen
PROBE_REGISTERS = [
    (0x3000, "RS511 Status-Word (Default-Map)"),
    (0x2100, "Alternative Status-Map (manche Modelle)"),
    (0x1000, "INVT-Goodrive Status-Word"),
    (0x0000, "Parameter P0.00"),
    (0x7000, "Drive-Type/ID (manche Modelle)"),
    (0xF000, "Invertek/Optidrive Status"),
]


async def try_read(
    port: str,
    baud: int,
    parity: str,
    stopbits: int,
    slave: int,
    address: int = 0x3000,
    timeout: float = 0.4,
) -> bool:
    """Versucht, ein einzelnes Holding-Register zu lesen. True bei Antwort."""
    client = AsyncModbusSerialClient(
        port=port,
        baudrate=baud,
        bytesize=8,
        parity=parity,
        stopbits=stopbits,
        timeout=timeout,
        retries=0,
    )
    try:
        if not await client.connect():
            return False
        result = await client.read_holding_registers(
            address=address, count=1, slave=slave
        )
        if result is None:
            return False
        return not result.isError()
    except Exception:
        return False
    finally:
        client.close()


async def scan(port: str, quick: bool) -> None:
    bauds = DEFAULT_BAUDRATES_QUICK if quick else DEFAULT_BAUDRATES_FULL
    print(f"Scanne {port} – das kann einige Minuten dauern …\n")
    print(f"{'Baud':>7}  {'Par':>3}  {'Stop':>4}  {'Slave':>5}  Result")
    print("─" * 48)

    found_any = False
    for baud in bauds:
        for parity, stopbits in PARITIES:
            for slave in SLAVE_RANGE:
                ok = await try_read(port, baud, parity, stopbits, slave)
                if ok:
                    found_any = True
                    print(
                        f"{baud:>7}  {parity:>3}  {stopbits:>4}  {slave:>5}  "
                        f"[32m✓ Antwort von Slave[0m"
                    )
        # Zeilenumbruch zwischen Baudraten
        print(f"  ── {baud} baud durchsucht ──")

    print()
    if found_any:
        print("Mindestens eine funktionierende Kombination gefunden – siehe oben.")
    else:
        print("Keine Antwort bei keiner Kombination.")
        print("Prüfen:")
        print("  • A/B-Verdrahtung (D+/D-) tauschen")
        print("  • Modbus im Umrichter aktiviert? (Steuerquelle = Kommunikation)")
        print("  • 120-Ω-Terminierung an beiden Bus-Enden vorhanden?")
        print("  • RS485-Adapter mit automatischer Sende/Empfangs-Umschaltung?")


async def probe_registers(port: str, slave: int, baud: int) -> None:
    """Bei bekanntem Slave verschiedene Register-Adressen testen."""
    print(f"Probiere Register-Adressen bei Slave {slave} @ {baud} baud …\n")
    print(f"{'Adresse':>8}  Beschreibung")
    print("─" * 60)
    for addr, desc in PROBE_REGISTERS:
        ok = await try_read(port, baud, "N", 1, slave, address=addr, timeout=0.6)
        marker = "[32m✓ lesbar[0m" if ok else "[31m✗[0m"
        print(f"  0x{addr:04X}  {desc:<45} {marker}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="RS511 Modbus-Bus-Scanner")
    parser.add_argument("--port", default="/dev/ttyUSB0", help="Serieller Port")
    parser.add_argument(
        "--quick", action="store_true", help="Nur 9600/19200/38400 baud testen"
    )
    parser.add_argument(
        "--probe",
        type=int,
        metavar="SLAVE",
        help="Bekannte Slave-Adresse: verschiedene Register-Maps testen",
    )
    parser.add_argument(
        "--baud", type=int, default=9600, help="Baudrate für --probe"
    )
    args = parser.parse_args()

    if args.probe is not None:
        await probe_registers(args.port, args.probe, args.baud)
    else:
        await scan(args.port, args.quick)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        sys.exit(130)
