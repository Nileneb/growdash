# GrowDash Hardware Agent

**Simple Hardware Bridge: Laravel ↔ Arduino**

## Was macht der Agent?

- 🔌 **Serial-Kommunikation** mit Arduino
- 🛠️ **Arduino-CLI** Wrapper (compile/upload)
- 📡 **HTTP-Client** zu Laravel (commands/telemetry/heartbeat)
- 🔍 **Port-Scanner** für verfügbare Serial-Devices

## Setup

1. **Install Dependencies:**
```bash
pip install -r requirements.txt
```

2. **Configure `.env`:**
```bash
LARAVEL_BASE_URL=https://grow.linn.games
DEVICE_PUBLIC_ID=your-device-id
DEVICE_TOKEN=your-token
SERIAL_PORT=/dev/ttyACM0
BAUD_RATE=9600
ARDUINO_CLI_PATH=/usr/local/bin/arduino-cli
```

3. **Run Agent:**
```bash
python agent.py
```

## Commands

Agent führt Commands aus Laravel aus:

- `serial_command` - Direkt ans Arduino
- `arduino_compile` - Code kompilieren
- `arduino_upload` - Code kompilieren + uploaden
- `scan_ports` - Verfügbare Serial-Ports scannen

## Local API (Debug)

```bash
python local_api.py
```

Endpoints:
- `GET /ports` - Serial-Ports scannen
- `GET /status` - Agent-Status
- `GET /config` - Aktuelle Config

## Architecture

```
Laravel Backend
    ↕ HTTP (commands/telemetry/heartbeat)
Hardware Agent (agent.py)
    ↕ Serial
Arduino/Microcontroller
```

**Simple. Clean. No bullshit.**

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
- ✅ **Multi-Device Support** - Automatisches Scannen und Verwalten mehrerer USB-Devices
- ✅ **Port-Scanner API** - Dynamische Port-Erkennung für Frontend-Integration

## 🔌 Multi-Device Modus

Der Agent kann **mehrere Arduino-Devices gleichzeitig** verwalten:

```bash
# Multi-Device-Modus aktivieren in .env
MULTI_DEVICE_MODE=true
USB_SCAN_INTERVAL=12000  # Scan alle 12000s (3.33h)

# Agent im Multi-Device-Modus starten
./grow_start.sh
```

### Funktionsweise

1. **Automatischer USB-Scan**
   - Beim Start: Sofortiger Scan aller verfügbaren USB-Ports
   - Periodisch: Alle 12000 Sekunden (konfigurierbar)
   
2. **Device-Erkennung**
   - Erkennt Arduino/USB-Serial-Devices automatisch
   - Jedes Device erhält eindeutige ID: `growdash-{vendor_id}-{product_id}-{port}`
   
3. **Separate Device-Instanzen**
   - Für jeden erkannten Port wird ein eigener Thread gestartet
   - Jedes Device hat separate SerialProtocol, LaravelClient, HardwareAgent
   
4. **Hot-Plug Support**
   - Neue Devices: Werden automatisch erkannt und gestartet
   - Getrennte Devices: Thread wird sauber beendet, Device aus Laravel abgemeldet

📖 **Detaillierte Dokumentation:** [docs/MULTI_DEVICE.md](docs/MULTI_DEVICE.md)

## 🔧 Systemanforderungen

- **OS:** Linux (Raspberry Pi OS, Ubuntu, etc.)
- **Python:** 3.10+
- **Hardware:** Arduino (Uno/Mega/Nano) oder ESP32 via Serial/USB
- **Backend:** Laravel-API mit Agent-Endpoints (siehe `docs/LARAVEL_IMPLEMENTATION.md`)

## 📁 Projektstruktur

```
growdash/
├── agent.py                    # Haupt-Agent (Serial, Telemetrie, Commands)
├── usb_device_manager.py       # Multi-Device USB-Scanner
├── bootstrap.py                # Onboarding-Wizard (standalone)
├── pairing.py                  # Pairing-Flow-Implementierung
├── local_api.py                # Debug-API (optional, localhost)
├── setup.sh                    # Ersteinrichtung (venv + Onboarding)
├── grow_start.sh               # Agent-Starter (Production)
├── requirements.txt            # Python-Dependencies
├── .env.example                # Konfigurationsvorlage
├── docs/                       # Detaillierte Dokumentation
│   ├── MULTI_DEVICE.md         # Multi-Device Support
│   ├── LARAVEL_IMPLEMENTATION.md
│   ├── AGENT_API_UPDATE.md
│   ├── ONBOARDING_MODES.md
│   └── ...
├── scripts/                    # Utility-Scripts
│   ├── test_multi_device.sh    # Test Multi-Device-Scanner
│   ├── test_heartbeat.sh
│   ├── install_arduino_cli.sh
│   └── install.sh
└── firmware/                   # Arduino-Firmware (.ino Dateien)
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

# Multi-Device Support
MULTI_DEVICE_MODE=false     # true = Multi-Device, false = Single-Device
USB_SCAN_INTERVAL=12000     # USB-Scan alle 12000s (nur bei MULTI_DEVICE_MODE=true)

# Arduino-CLI (für Firmware-Updates)
ARDUINO_CLI_PATH=/usr/local/bin/arduino-cli
FIRMWARE_DIR=./firmware

# Debug (optional)
LOCAL_API_ENABLED=false
LOCAL_API_HOST=127.0.0.1
LOCAL_API_PORT=8000
```

## 🎯 Onboarding Modi

### 1. PAIRING (Empfohlen)

Agent zeigt Pairing-Code an, User gibt Code im Laravel-Frontend ein:

```bash
ONBOARDING_MODE=PAIRING
./setup.sh
# → Zeigt 6-stelligen Code an
# → In Laravel-Frontend eingeben
```

### 2. DIRECT_LOGIN

Agent meldet sich mit User-Credentials an:

```bash
ONBOARDING_MODE=DIRECT_LOGIN
./setup.sh
# → Email und Passwort eingeben
```

### 3. PRECONFIGURED

Credentials sind bereits in `.env` vorhanden (z.B. vorkonfigurierte SD-Card):

```bash
ONBOARDING_MODE=PRECONFIGURED
DEVICE_PUBLIC_ID=growdash-001
DEVICE_TOKEN=xxx
```

📖 **Details:** [docs/ONBOARDING_MODES.md](docs/ONBOARDING_MODES.md)

## 📡 API Endpoints

Agent kommuniziert mit Laravel-Backend:

| Endpoint | Methode | Beschreibung |
|----------|---------|--------------|
| `/commands/pending` | GET | Holt ausstehende Commands |
| `/commands/{id}/result` | POST | Meldet Command-Ergebnis |
| `/telemetry` | POST | Sendet Sensor-Daten |
| `/heartbeat` | POST | Meldet "online" Status |
| `/capabilities` | POST | Sendet Board/Sensor-Info |
| `/logs` | POST | Sendet Log-Batch |

📖 **Details:** [docs/LARAVEL_ENDPOINTS.md](docs/LARAVEL_ENDPOINTS.md)

## 🎮 Serial Commands

Agent sendet Commands an Arduino und wartet auf Response:

| Command | Arduino-Antwort | Beschreibung |
|---------|-----------------|--------------|
| `status` | `dist_cm=20.3 liters=33.53 Tab=OFF...` | Kompletter Status |
| `TDS` | `TDS=660 TempC=22.50 ADC=351 V=1.714` | TDS-Sensor |
| `Spray 120000` | (Timeout nach 5s) | Sprühe 120s |
| `Fill 60000` | (Timeout nach 5s) | Fülle 60s |

**Wichtig:** Actuator-Commands (Spray, Fill) laufen länger als 5s → Timeout ist normal.

## 🛠️ Development

### Setup

```bash
# 1. Repo klonen
git clone https://github.com/Nileneb/growdash.git
cd growdash

# 2. Virtual Environment
python3 -m venv venv
source venv/bin/activate

# 3. Dependencies
pip install -r requirements.txt

# 4. .env kopieren
cp .env.example .env
# → LARAVEL_BASE_URL, DEVICE_PUBLIC_ID, DEVICE_TOKEN anpassen
```

### Lokale API (Debug)

```bash
# Local API starten (Port 8000)
python3 local_api.py

# Agent mit Local API testen
# .env:
LOCAL_API_ENABLED=true
LARAVEL_BASE_URL=http://127.0.0.1:8000

# Agent starten
python3 agent.py
```

### Tests

```bash
# Heartbeat testen
./scripts/test_heartbeat.sh

# Multi-Device testen
./scripts/test_multi_device.sh

# Serial-Verbindung testen
python3 -c "import serial; s=serial.Serial('/dev/ttyACM0', 9600); print(s.read(100))"
```

## 🐛 Troubleshooting

### 1. Serial-Port Permission Denied

```bash
# User zu dialout-Gruppe hinzufügen
sudo usermod -a -G dialout $USER

# Neuanmeldung erforderlich
logout
```

### 2. Laravel-Backend 404

```bash
# Backend nicht vollständig eingerichtet
# → Siehe docs/LARAVEL_IMPLEMENTATION.md
# → Routes /api/growdash/agent/* müssen existieren
```

### 3. Device-Auth 401

```bash
# Token ungültig oder Device gelöscht
# → Credentials zurücksetzen:
rm .env
./setup.sh  # Neu pairen
```

### 4. Arduino nicht erkannt

```bash
# USB-Verbindung prüfen
lsusb

# Serial-Ports prüfen
ls -l /dev/tty*

# Permissions prüfen
groups $USER  # sollte "dialout" enthalten
```

### 5. Multi-Device: Keine Devices erkannt

```bash
# pyserial prüfen
pip list | grep pyserial

# USB-Scanner testen
./scripts/test_multi_device.sh

# Manuelle Prüfung
python3 -c "from usb_device_manager import USBScanner; print(USBScanner.scan_ports())"
```

## 📚 Dokumentation

- **[MULTI_DEVICE.md](docs/MULTI_DEVICE.md)** - Multi-Device Support (USB-Scanner, Hot-Plug)
- **[LARAVEL_IMPLEMENTATION.md](docs/LARAVEL_IMPLEMENTATION.md)** - Laravel Backend-Integration
- **[AGENT_API_UPDATE.md](docs/AGENT_API_UPDATE.md)** - API Alignment mit Agent Integration Guide
- **[ONBOARDING_MODES.md](docs/ONBOARDING_MODES.md)** - Pairing, Direct-Login, Pre-configured
- **[PAIRING_FLOW.md](docs/PAIRING_FLOW.md)** - Detaillierter Pairing-Ablauf
- **[LARAVEL_ENDPOINTS.md](docs/LARAVEL_ENDPOINTS.md)** - Alle API-Endpoints
- **[QUICKSTART.md](docs/QUICKSTART.md)** - Schnelleinstieg
- **[SETUP.md](docs/SETUP.md)** - Detaillierte Setup-Anleitung

## 🤝 Contributing

Contributions sind willkommen! Bitte:

1. Fork das Repository
2. Erstelle Feature Branch (`git checkout -b feature/AmazingFeature`)
3. Commit Changes (`git commit -m 'Add AmazingFeature'`)
4. Push zum Branch (`git push origin feature/AmazingFeature`)
5. Öffne Pull Request

## 📝 License

Dieses Projekt ist unter der MIT-Lizenz lizenziert.

## 👨‍💻 Author

**Nileneb**

- GitHub: [@Nileneb](https://github.com/Nileneb)
- Projekt: [GrowDash](https://github.com/Nileneb/growdash)

---

**Status:** ✅ Production-Ready  
**Letzte Aktualisierung:** 2. Dezember 2025  
**Version:** 2.0.0 (Multi-Device Support)
