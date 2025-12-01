# GrowDash Hardware Agent v2.0

**Vereinfachter Hardware-Agent für GrowDash**

Die gesamte Business-Logik wird von einer externen Laravel-App übernommen. 
Dieser Agent stellt nur noch Hardware-Zugriff zur Verfügung.

## Architektur

```
┌─────────────────┐
│  Laravel App    │  ← Business-Logik, UI, Datenbank
│  (Backend)      │
└────────┬────────┘
         │ HTTP (Device-Token-Auth)
         │
┌────────▼────────┐
│ Hardware Agent  │  ← Dieser Agent
│  (Python)       │
└────────┬────────┘
         │ Serial
         │
┌────────▼────────┐
│   Arduino       │  ← Hardware-Steuerung
│   (Firmware)    │
└─────────────────┘
```

## Features

- **Device-Token-Auth**: Keine User-Logins, nur Device-Identifikation
- **Serial-Protokoll**: Einfache Text-Kommunikation mit Arduino
- **Telemetrie-Batching**: Sensordaten werden gesammelt und an Laravel gesendet
- **Command-Polling**: Befehle von Laravel werden periodisch abgerufen
- **Firmware-Updates**: Sichere Arduino-Firmware-Updates (nur Whitelist)
- **Local Debug API**: Optional für manuelle Tests (nur LAN)

## Installation

### 1. Repository klonen und .env erstellen

```bash
cd growdash
cp .env.example .env
nano .env  # Konfiguration anpassen
```

### 2. Virtuelle Umgebung erstellen

```bash
python -m venv .venv
source .venv/bin/activate
```

### 3. Dependencies installieren

```bash
pip install -r requirements.txt
```

## Konfiguration

Alle Einstellungen werden aus der `.env` Datei geladen:

```env
# Laravel Backend
LARAVEL_BASE_URL=http://192.168.178.12
LARAVEL_API_PATH=/api/growdash

# Device Identifikation
DEVICE_PUBLIC_ID=growdash-device-001
DEVICE_TOKEN=your-secure-device-token-here

# Hardware
SERIAL_PORT=/dev/ttyACM0
BAUD_RATE=9600

# Agent Verhalten
TELEMETRY_INTERVAL=10        # Sekunden zwischen Telemetrie-Uploads
COMMAND_POLL_INTERVAL=5      # Sekunden zwischen Command-Polls

# Local API (optional, nur für Debugging)
LOCAL_API_ENABLED=true
LOCAL_API_HOST=127.0.0.1
LOCAL_API_PORT=8000
```

## Verwendung

### Agent starten

```bash
./grow_start.sh
```

oder manuell:

```bash
source .venv/bin/activate
python agent.py
```

### Local Debug API starten (optional)

```bash
python local_api.py
```

Dann verfügbar unter: http://127.0.0.1:8000/docs

## Laravel API Endpoints

Der Agent kommuniziert mit folgenden Laravel-Endpoints:

### 1. Telemetrie senden (POST)

```
POST /api/growdash/telemetry
Content-Type: application/json
X-Device-ID: growdash-device-001
X-Device-Token: xxx

{
  "device_id": "growdash-device-001",
  "readings": [
    {
      "timestamp": "2025-12-01T10:30:00Z",
      "sensor_id": "water_level",
      "value": 45.5,
      "unit": "percent"
    },
    ...
  ]
}
```

### 2. Befehle abrufen (GET)

```
GET /api/growdash/commands/pending
X-Device-ID: growdash-device-001
X-Device-Token: xxx

Response:
{
  "commands": [
    {
      "id": "cmd-123",
      "type": "spray_on",
      "params": {"duration": 5}
    },
    ...
  ]
}
```

### 3. Befehlsergebnis melden (POST)

```
POST /api/growdash/commands/{command_id}/result
X-Device-ID: growdash-device-001
X-Device-Token: xxx

{
  "success": true,
  "message": "Spray für 5s aktiviert",
  "timestamp": "2025-12-01T10:30:05Z"
}
```

## Unterstützte Befehle

| Befehl | Parameter | Arduino-Befehl | Beschreibung |
|--------|-----------|----------------|--------------|
| `spray_on` | `duration` (optional) | `SprayOn` / `Spray {ms}` | Spray aktivieren |
| `spray_off` | - | `SprayOff` | Spray deaktivieren |
| `fill_start` | `target_liters` | `FillL {liters}` | Füllen starten |
| `fill_stop` | - | `CancelFill` | Füllen stoppen |
| `request_status` | - | `Status` | Status abfragen |
| `request_tds` | - | `TDS` | TDS-Messung anfordern |
| `firmware_update` | `module_id` | - | Firmware flashen |

## Arduino-Protokoll

### Vom Agent zum Arduino (Commands)

```
SprayOn              # Spray einschalten
SprayOff             # Spray ausschalten
Spray 5000           # Spray für 5000ms (5s)
FillL 5.0            # Auf 5 Liter füllen
CancelFill           # Füllen abbrechen
Status               # Status abfragen
TDS                  # TDS-Messung starten
```

### Vom Arduino zum Agent (Telemetrie)

```
WaterLevel: 45       # Wasserstand in %
TDS=320 TempC=22.5   # TDS in ppm, Temperatur in °C
Spray: ON            # Spray-Status
Tab: ON              # Füll-Status
```

## Firmware-Updates

Firmware-Updates werden sicher über eine Whitelist verwaltet:

### Erlaubte Module

- `main`: GrowDash_Main.ino
- `sensor`: GrowDash_Sensors.ino
- `actuator`: GrowDash_Actuators.ino

### Firmware flashen

Über Laravel-API:

```json
{
  "type": "firmware_update",
  "params": {
    "module_id": "main"
  }
}
```

Oder über Local API:

```bash
curl -X POST http://127.0.0.1:8000/firmware/flash?module_id=main
```

### Voraussetzungen

- Arduino-CLI muss installiert sein
- Firmware-Dateien müssen in `./firmware/` liegen
- Nur Dateien aus der Whitelist werden geflasht

## Local Debug API

Wenn `LOCAL_API_ENABLED=true`:

### Endpoints

- `GET /health` - Gesundheitscheck
- `POST /command` - Manuellen Befehl senden
- `GET /telemetry` - Aktuelle Telemetrie
- `GET /status` - Hardware-Status abfragen
- `GET /config` - Agent-Konfiguration
- `POST /firmware/flash` - Firmware flashen
- `GET /firmware/log` - Flash-Log
- `GET /firmware/modules` - Verfügbare Module

### Beispiele

```bash
# Status abfragen
curl http://127.0.0.1:8000/status

# Spray einschalten
curl -X POST http://127.0.0.1:8000/command \
  -H "Content-Type: application/json" \
  -d '{"type": "spray_on", "params": {"duration": 5}}'

# Telemetrie abrufen
curl http://127.0.0.1:8000/telemetry
```

## Entwicklung

### Struktur

```
growdash/
├── agent.py              # Hauptagent
├── local_api.py          # Debug-API (optional)
├── .env                  # Konfiguration (nicht in Git)
├── .env.example          # Konfigurationsvorlage
├── requirements.txt      # Python-Dependencies
├── grow_start.sh         # Startskript
├── firmware/             # Firmware-Dateien
│   ├── GrowDash_Main.ino
│   ├── GrowDash_Sensors.ino
│   └── flash_log.json    # Flash-Historie
└── README.md

ARCHIVIERT (alte Struktur):
├── app.py                # Alte FastAPI-App
├── scripts/              # Alte Module
│   ├── arduino.py
│   ├── camera.py
│   ├── db_handler.py
│   └── ...
└── static/               # Altes Frontend
```

### Logging

Der Agent loggt alle Aktivitäten:

```
2025-12-01 10:30:00 - INFO - Agent gestartet für Device: growdash-device-001
2025-12-01 10:30:00 - INFO - Verbunden mit /dev/ttyACM0 @ 9600 baud
2025-12-01 10:30:10 - INFO - Telemetrie gesendet: 5 Messwerte
2025-12-01 10:30:15 - INFO - Empfangene Befehle: 1
2025-12-01 10:30:15 - INFO - Führe Befehl aus: spray_on
2025-12-01 10:30:15 - INFO - Befehl an Arduino: Spray 5000
```

## Troubleshooting

### Serial-Port nicht gefunden

```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
sudo usermod -a -G dialout $USER  # Berechtigungen
```

### Laravel-Backend nicht erreichbar

```bash
# Verbindung testen
curl http://192.168.178.12/api/growdash/commands/pending \
  -H "X-Device-ID: growdash-device-001" \
  -H "X-Device-Token: xxx"
```

### Agent startet nicht

```bash
# Dependencies prüfen
pip install -r requirements.txt

# .env prüfen
cat .env

# Manuell starten mit Debug-Output
python agent.py
```

## Lizenz

MIT
