# GrowDash Hardware Agent

Python-Agent für automatisierte Growbox-Steuerung. Läuft auf Raspberry Pi, kommuniziert mit Arduino über Serial und mit Laravel-Backend via HTTPS.

## 🚀 Quick Start

```bash
# 1. Repository klonen
git clone https://github.com/Nileneb/growdash.git
cd growdash

# 2. Setup ausführen (erstellt venv, installiert Dependencies, startet Onboarding)
./setup.sh

# 3. Agent starten
./grow_start.sh
```

## 📋 Features

- ✅ **Device-Token Authentifizierung** - Sichere Kommunikation mit Laravel-Backend
- ✅ **Automatisches Onboarding** - Pairing-Code oder Direct-Login
- ✅ **Serial-Kommunikation** - Direkte Arduino-Steuerung mit Command-Responses
- ✅ **Telemetrie** - Automatisches Senden von Sensor-Daten (Wasserstand, TDS, Temperatur)
- ✅ **Command-Polling** - Empfängt und führt Commands vom Backend aus
- ✅ **Heartbeat** - Hält Device-Status auf "online"
- ✅ **Board Detection** - Automatische Erkennung von Arduino Uno, Mega, ESP32, etc.
- ✅ **Firmware Updates** - Sichere Arduino-Firmware-Updates via arduino-cli
- ✅ **Log Batching** - Sendet Logs periodisch ans Backend

## 🔧 Systemanforderungen

- **OS:** Linux (Raspberry Pi OS, Ubuntu, etc.)
- **Python:** 3.10+
- **Hardware:** Arduino (Uno/Mega/Nano) oder ESP32 via Serial/USB
- **Backend:** Laravel-API mit Agent-Endpoints (siehe `docs/LARAVEL_IMPLEMENTATION.md`)

## 📁 Projektstruktur

```
growdash/
├── agent.py              # Haupt-Agent (Serial, Telemetrie, Commands)
├── bootstrap.py          # Onboarding-Wizard (standalone)
├── pairing.py            # Pairing-Flow-Implementierung
├── local_api.py          # Debug-API (optional, localhost)
├── setup.sh              # Ersteinrichtung (venv + Onboarding)
├── grow_start.sh         # Agent-Starter (Production)
├── requirements.txt      # Python-Dependencies
├── .env.example          # Konfigurationsvorlage
├── docs/                 # Detaillierte Dokumentation
│   ├── LARAVEL_IMPLEMENTATION.md
│   ├── AGENT_API_UPDATE.md
│   ├── ONBOARDING_MODES.md
│   └── ...
├── scripts/              # Utility-Scripts
│   ├── test_heartbeat.sh
│   ├── install_arduino_cli.sh
│   └── install.sh
└── firmware/             # Arduino-Firmware (.ino Dateien)
```

## 🔐 Konfiguration (.env)

```bash
# Laravel Backend
LARAVEL_BASE_URL=https://grow.linn.games
LARAVEL_API_PATH=/api/growdash/agent

# Onboarding Modus
ONBOARDING_MODE=PAIRING  # PAIRING | DIRECT_LOGIN | PRECONFIGURED

# Device Credentials (werden automatisch gesetzt)
DEVICE_PUBLIC_ID=
DEVICE_TOKEN=

# Hardware
SERIAL_PORT=/dev/ttyACM0
BAUD_RATE=9600

# Agent Intervalle
TELEMETRY_INTERVAL=10       # Sekunden
COMMAND_POLL_INTERVAL=5     # Sekunden

# Arduino-CLI (für Firmware-Updates)
ARDUINO_CLI_PATH=/usr/local/bin/arduino-cli
FIRMWARE_DIR=./firmware

# Debug (optional)
LOCAL_API_ENABLED=false
LOCAL_API_HOST=127.0.0.1
LOCAL_API_PORT=8000
```

## 🎯 Onboarding-Modi

### 1. Pairing-Code (Empfohlen)
Agent generiert 6-stelligen Code → Eingabe in Web-UI → Device wird verknüpft.

```bash
./setup.sh  # Wähle Option 1
# Code wird angezeigt, z.B. "XY42Z7"
# Im Browser: https://grow.linn.games/devices/pair → Code eingeben
```

### 2. Direct Login (Advanced)
Login mit Email + Passwort → Device wird automatisch registriert.

```bash
./setup.sh  # Wähle Option 2
# Email: user@example.com
# Passwort: ***
```

### 3. Preconfigured
Manuelle Konfiguration via `.env` (für Experten).

## 📡 Agent-API Endpoints

Der Agent kommuniziert mit folgenden Laravel-Endpoints:

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/heartbeat` | POST | Device-Status auf "online" halten |
| `/telemetry` | POST | Sensor-Daten senden |
| `/commands/pending` | GET | Befehle abrufen |
| `/commands/{id}/result` | POST | Befehlsergebnis melden |
| `/capabilities` | POST | Board-Info senden |
| `/logs` | POST | Log-Batch senden |

Details: `docs/LARAVEL_IMPLEMENTATION.md`

## 🔌 Serial Commands

Der Agent unterstützt **direkte Arduino-Befehle** und wartet auf Antworten:

```json
// Backend sendet:
{
  "type": "serial_command",
  "params": {
    "command": "STATUS"
  }
}

// Agent führt aus:
1. Sendet "STATUS\n" an Arduino
2. Wartet auf Antwort (5s timeout)
3. Arduino antwortet: "WaterLevel: 75, Pump: OFF"
4. Meldet zurück: { "status": "completed", "result_message": "Arduino: WaterLevel: 75, Pump: OFF" }
```

Unterstützte Legacy-Commands:
- `spray_on`, `spray_off`, `fill_start`, `fill_stop`
- `request_status`, `request_tds`
- `firmware_update` (sichere Kapselung)

## 🛠️ Development

### Lokale Debug-API starten
```bash
python local_api.py
# Erreichbar auf http://localhost:8000
# Endpoints: /config, /telemetry, /status, /firmware/flash
```

### Dependencies installieren
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Tests
```bash
# Heartbeat testen
./scripts/test_heartbeat.sh

# Arduino-CLI installieren
./scripts/install_arduino_cli.sh
```

## 🐛 Troubleshooting

### Agent startet nicht
```bash
# Prüfe .env
cat .env | grep DEVICE

# Prüfe Serial-Port
ls -la /dev/ttyACM* /dev/ttyUSB*

# Logs anzeigen
python agent.py  # Siehe stdout
```

### Backend-Verbindung fehlschlägt
```bash
# Prüfe Backend-Erreichbarkeit
curl -I https://grow.linn.games

# Prüfe Credentials
# Bei 401/403: Credentials werden automatisch zurückgesetzt
# Neu pairen mit: ./setup.sh
```

### Commands werden nicht ausgeführt
```bash
# Prüfe Command-Logs
# Agent loggt: "Empfangene Befehle: X"
# Prüfe Serial-Verbindung: "Befehl an Arduino (mit Response): ..."
# Prüfe Arduino-Antwort: "Arduino Antwort: ..."
```

### Capabilities 422 Error
```bash
# Agent loggt jetzt Response-Body
# Prüfe welche Felder Laravel erwartet
# Passe payload in LaravelClient.send_capabilities() an
```

## 📚 Weiterführende Dokumentation

- **Laravel Backend Setup:** `docs/LARAVEL_IMPLEMENTATION.md`
- **Agent-API Details:** `docs/AGENT_API_UPDATE.md`
- **Onboarding-Modi:** `docs/ONBOARDING_MODES.md`
- **Pairing-Flow:** `docs/PAIRING_FLOW.md`
- **Quickstart:** `docs/QUICKSTART.md`

## 🤝 Contributing

Pull Requests willkommen! Bitte erstelle Issues für Bugs oder Feature-Requests.

## 📄 Lizenz

MIT License - siehe LICENSE-Datei

## 👤 Autor

Entwickelt für automatisierte Growbox-Steuerung mit Arduino + Raspberry Pi + Laravel Backend.

---

**Status:** ✅ Production Ready  
**Version:** 1.0.0  
**Letzte Aktualisierung:** 2. Dezember 2025
