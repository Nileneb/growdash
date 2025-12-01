# Firmware Directory

Dieses Verzeichnis enthält die Arduino-Firmware-Dateien für GrowDash.

## Erlaubte Module (Whitelist)

Nur diese Module können vom Agent geflasht werden:

- **main**: `GrowDash_Main.ino` - Hauptfirmware
- **sensor**: `GrowDash_Sensors.ino` - Sensor-Modul
- **actuator**: `GrowDash_Actuators.ino` - Aktuator-Modul

## Verwendung

1. Firmware-Dateien hier ablegen
2. Flash-Befehl über Laravel-API oder Local API senden:

```bash
# Über Local API
curl -X POST http://127.0.0.1:8000/firmware/flash?module_id=main
```

## Sicherheit

- Nur vordefinierte Module können geflasht werden (siehe `agent.py: FirmwareManager.ALLOWED_MODULES`)
- Keine freien C++-Snippets werden ausgeführt
- Jeder Flash wird in `flash_log.json` protokolliert

## Flash-Log

Das Log `flash_log.json` enthält die Flash-Historie:

```json
[
  {
    "timestamp": "2025-12-01T10:30:00Z",
    "module": "main",
    "port": "/dev/ttyACM0",
    "success": true,
    "error": ""
  }
]
```

## Arduino-CLI Setup

Falls noch nicht installiert:

```bash
# Arduino-CLI installieren
curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | sh

# Core installieren
arduino-cli core install arduino:avr

# Board-Info
arduino-cli board list
```
