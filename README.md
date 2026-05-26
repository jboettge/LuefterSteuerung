# RSPro RS510 / TECO L510 – Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

Steuert einen **RSPro RS510-2P7-SH1** (OEM des TECO L510) Frequenzumrichter über Modbus RTU / RS485 direkt aus Home Assistant.

## Unterstützte Geräte

| Gerät | Typ | Hinweis |
|---|---|---|
| RSPro RS510-2P7-SH1 | 1-phasig 230 V, 2,7 kW | getestet |
| TECO L510-Serie | alle Varianten | baugleich, sollte funktionieren |

## Funktionen

- **Lüfter-Entity** mit stufenloser Geschwindigkeit (0–100 %) und drei Voreinstellungen (Niedrig 15 Hz / Mittel 30 Hz / Hoch 50 Hz)
- **Sensoren:** Ausgangsfrequenz, Sollfrequenz, Ausgangsstrom, Ausgangsspannung, Zwischenkreisspannung, Kühlkörpertemperatur, Fehlercode, Status
- Konfigurierbare Min-/Max-Frequenz und Abfrageintervall
- Vollständige UI-Einrichtung über den HA Config-Flow (kein YAML nötig)

## Voraussetzungen

### Hardware

- RS485-Adapter (USB oder HAT), z. B. CH340-basierter USB-RS485-Konverter
- Verkabelung RS510 **CON2** ↔ RS485-Adapter:

  | CON2 | RS485 |
  |---|---|
  | Pin 1 oder 3 (Data+) | A / D+ |
  | Pin 2 oder 6 (Data−) | B / D− |
  | Pin 8 (GND) | GND (optional, empfohlen) |

### Umrichter-Parametrierung (einmalig am Tastenfeld)

| Parameter | Wert | Bedeutung |
|---|---|---|
| P00-02 | 2 | Steuerquelle: Kommunikation |
| P00-05 | 5 | Frequenzquelle: Kommunikation |
| P09-00 | 1 | Slave-Adresse (Standard) |
| P09-01 | 0 | Modbus RTU |
| P09-02 | 2 | 19200 Baud (Standard) |
| P09-03 | 0 | 1 Stoppbit |
| P09-04 | 0 | Keine Parität |

## Installation via HACS

1. HACS öffnen → **Integrationen** → Drei-Punkte-Menü → **Benutzerdefinierte Repositories**
2. URL eingeben: `https://github.com/jboettge/lueftersteuerung`
3. Kategorie: **Integration** → **Hinzufügen**
4. Integration **RS510** in HACS suchen und installieren
5. Home Assistant neu starten

## Manuelle Installation

```
custom_components/rs510/  →  <HA-config>/custom_components/rs510/
```

HA neu starten.

## Einrichtung

1. **Einstellungen → Geräte & Dienste → Integration hinzufügen → RS510**
2. Felder ausfüllen:
   - **Serieller Port**: z. B. `/dev/ttyUSB0` oder `/dev/ttyACM0`
   - **Baudrate**: `19200` (Werkseinstellung)
   - **Slave-Adresse**: `1` (Werkseinstellung P09-00)
   - **Mindestfrequenz**: entspricht 0 % (empfohlen: `0` oder `5`)
   - **Höchstfrequenz**: entspricht 100 % (empfohlen: `50`)
   - **Abfrageintervall**: Sekunden zwischen zwei Status-Lesungen (Standard: `30`)
3. Speichern — der Umrichter wird getestet, danach erscheinen alle Entities.

## Entities

| Entity | Typ | Beschreibung |
|---|---|---|
| `fan.rs510_lüfter` | Fan | Geschwindigkeit, Ein/Aus, Voreinstellungen |
| `sensor.rs510_ausgangsfrequenz` | Sensor | Aktuelle Ausgangsfrequenz in Hz |
| `sensor.rs510_sollfrequenz` | Sensor | Frequenz-Sollwert in Hz *(standardmäßig deaktiviert)* |
| `sensor.rs510_ausgangsstrom` | Sensor | Ausgangsstrom in A |
| `sensor.rs510_ausgangsspannung` | Sensor | Ausgangsspannung in V |
| `sensor.rs510_zwischenkreisspannung` | Sensor | DC-Zwischenkreis in V *(standardmäßig deaktiviert)* |
| `sensor.rs510_kühlkörpertemperatur` | Sensor | Kühlkörpertemperatur in °C *(standardmäßig deaktiviert)* |
| `sensor.rs510_fehler` | Sensor | Fehlercode-Text aus Register 0x2521 |
| `sensor.rs510_status` | Sensor | Betriebszustand (Bereit / Vorwärts / Rückwärts / Fehler) |

## Fehlerbehebung

**Umrichter antwortet nicht beim Einrichten**
- A/B (Data+/Data−) am RS485-Adapter tauschen
- Baudrate und Slave-Adresse am Umrichter mit P09-02 / P09-00 prüfen
- P09-01 = 0 (Modbus RTU, nicht ASCII/BACnet)?
- 120-Ω-Abschlusswiderstand am Bus-Ende vorhanden?

**Motor dreht nicht trotz Befehlen**
- P00-02 = 2 und P00-05 = 5 am Umrichter gesetzt?
- Fehlercode-Sensor prüfen — `Err7 Parameterkonflikt` deutet auf falsch gesetzte Parameter hin.

**Diagnose-Skripte** (ohne HA, auf dem Host ausführen):
```bash
python rs510_scan.py --port /dev/ttyACM0        # Baudrate/Adresse finden
python rs510_test.py --port /dev/ttyACM0 status  # Statusregister lesen
python rs510_test.py --port /dev/ttyACM0 freq=15 # 15 Hz testen
```

## Lizenz

MIT
