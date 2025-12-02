# GrowDash Hardware Agent




















































































































































































































































































































































































































**Letzte Aktualisierung:** 2. Dezember 2025**Getestet mit:** Raspberry Pi 4, Python 3.12, Multiple Arduino Uno/Mega  **Status:** ✅ Production-Ready  ---```./grow_start.sh# Agent neu startencp .env.backup .env# .env wiederherstellen```bash### 5. Rollback (falls nötig)```# 🆕 Neues Device erkannt: /dev/ttyACM0 → ...# 🔍 Scanne USB-Ports...# 🔌 GrowDash Multi-Device Manager# Erwartete Ausgabe:tail -f agent.log# Logs prüfen```bash### 4. Verifizieren```./grow_start.sh```bash### 3. Agent neu starten```# DEVICE_PUBLIC_ID/TOKEN werden pro Device generiert# SERIAL_PORT kann bleiben (wird ignoriert)echo "USB_SCAN_INTERVAL=12000" >> .envecho "MULTI_DEVICE_MODE=true" >> .env# Multi-Device aktivieren```bash### 2. .env anpassen```cp .env .env.backup```bash### 1. Backup erstellen## 🔄 Migration von Single zu Multi-Device- **docs/ONBOARDING_MODES.md** - Device-Onboarding- **docs/LARAVEL_IMPLEMENTATION.md** - Backend-Integration- **usb_device_manager.py** - USB-Scanner und Device-Management- **agent.py** - HardwareAgent-Implementierung## 📚 Siehe auch```ALLOWED_PORTS=/dev/ttyACM0,/dev/ttyUSB0# Oder spezifische Ports whitelisten (Custom-Code):USB_SCAN_INTERVAL=36000  # 10h statt 3.33h# USB-Scan-Intervall erhöhen```bash### Zu viele Reconnects```python3 -c "from usb_device_manager import USBScanner; print(USBScanner.scan_ports())"# Test:pip install pyserial# Falls nicht:pip list | grep pyserial# pyserial installiert?```bash### USB-Scan funktioniert nicht```# - Arduino nicht ready (2s delay fehlt)# - Falscher BAUD_RATE# - Keine Serial-Permissions# - Port bereits in Verwendung# Häufige Ursachen:tail -f agent.log | grep "Device-Thread"# Logs prüfen```bash### Device-Thread startet nicht```python3 -c "import serial; s=serial.Serial('/dev/ttyACM0', 9600); print(s.read(100))"# 4. Teste Serial-Port manuellgroups $USER  # sollte "dialout" enthalten# 3. Prüfe Permissionsls -l /dev/tty*# 2. Prüfe Serial-Portslsusb# 1. Prüfe USB-Verbindung```bash### Device wird nicht erkannt## 🐛 Troubleshooting- Empfehlung: Max. 10-20 Devices pro Pi- Viele Devices = viele Threads → RAM/CPU-Verbrauch- Jedes Device = 1 Thread + 4 Sub-Threads (Telemetry, Commands, Heartbeat, Logs)**Beachte:**### 4. Resource-Management- Robuste Error-Handling in Device-Threads- Timeout-Handling in SerialProtocol- Automatische Reconnects via USB-Scan**Lösung:****Problem:** USB-Devices können instabil sein (Resets, Disconnects).### 3. USB-Stabilität```logout# Neuanmeldung erforderlichsudo usermod -a -G dialout $USER# User zu dialout-Gruppe hinzufügen```bashStelle sicher, dass User Serial-Zugriff hat:### 2. Serial-Port Permissions```# Agent verwendet device_id als Lookup-Key# Device-IDs im Voraus in Datenbank anlegen```python**Lösung 3 - Pre-Configuration:**```# Jedes Device erhält eigene ID vom Backend# wenn keine Credentials vorhanden# DeviceInstance ruft automatisch Onboarding auf```python**Lösung 2 - Dynamisches Onboarding (Empfohlen):**```.env.ttyUSB0.env.ttyACM0# Nicht empfohlen - kompliziert bei vielen Devices```bash**Lösung 1 - Separate .env pro Device:****Problem:** Jedes Device braucht eigene Credentials (DEVICE_PUBLIC_ID + DEVICE_TOKEN).### 1. Device-Token Management## ⚠️ Wichtige Hinweise```    return f"{hostname}-{port_name}"    port_name = device_info.port.replace("/dev/", "")    hostname = socket.gethostname()    import socket    # Beispiel: Hostname + Port    """Custom ID-Generator"""def _generate_device_id(device_info):```python### Custom Device-ID Generator```manager.stop()# Stoppen    print(f"  - {device.device_id} ({port})")for port, device in manager.get_active_devices().items():print(f"Aktive Devices: {manager.get_device_count()}")# Statusmanager.start()# Starten)    scan_interval=60    config_template=config,manager = USBDeviceManager(# Manager erstellen (Scan alle 60s für Testing)config = AgentConfig()# Basis-Config ladenfrom agent import AgentConfigfrom usb_device_manager import USBDeviceManager```python### Device-Manager starten```    print(f"Description: {device_info.description}")    print(f"Product ID: {device_info.product_id}")    print(f"Vendor ID: {device_info.vendor_id}")    print(f"Port: {device_info.port}")for device_info in devices:devices = USBScanner.scan_ports()# Scanne alle Portsfrom usb_device_manager import USBScanner```python### USB-Scan durchführen## 🔧 Code-Beispiele```            └── ...        └── Thread → HardwareAgent        ├── device_id: growdash-1a86-7523-ttyUSB0        ├── port: /dev/ttyUSB0    └── DeviceInstance #2    │    │       └── Heartbeat Loop    │       ├── Command Loop    │       ├── Telemetry Loop    │       ├── LaravelClient (device_id=...)    │       ├── SerialProtocol (ttyACM0)    │   └── Thread → HardwareAgent    │   ├── device_id: growdash-2341-0043-ttyACM0    │   ├── port: /dev/ttyACM0    ├── DeviceInstance #1└── DeviceInstances (Dict[port, DeviceInstance])││       └── Getrennte Devices → DeviceInstance.stop()│       ├── Neue Devices → DeviceInstance.start()│   └── _scan_and_update()│   ├── USBScanner.scan_ports()├── Scanner-Thread (alle USB_SCAN_INTERVAL)USBDeviceManager```## 🏗️ Architektur```# ✅ Alle Devices gestoppt# ...# ✅ Device gestoppt: growdash-2341-0043-ttyACM0# Stoppe Device growdash-2341-0043-ttyACM0...# 🛑 Beende Multi-Device Manager...# Strg+C oder SIGTERM```bash### Stoppen```#   - growdash-1a86-7523-ttyUSB0 (/dev/ttyUSB0): ✅ läuft#   - growdash-2341-0043-ttyACM0 (/dev/ttyACM0): ✅ läuft# 📊 Multi-Device Status: 2 aktive Devices# Status-Ausgabe alle 10stail -f agent.log# Logs zeigen alle aktiven Devices```bash### Monitoring```# ...# ✅ Device-Thread gestartet: growdash-2341-0043-ttyACM0# 📱 Device-Instanz erstellt: growdash-2341-0043-ttyACM0 auf /dev/ttyACM0# 🆕 Neues Device erkannt: /dev/ttyACM0 → growdash-2341-0043-ttyACM0# Gefundene Ports: {'/dev/ttyACM0', '/dev/ttyUSB0'}# 🔍 Scanne USB-Ports...# # USB-Scan: beim Start + alle 12000s# ============================================================# 🔌 GrowDash Multi-Device Manager# Ausgabe:./grow_start.sh# 2. Agent startenecho "MULTI_DEVICE_MODE=true" >> .env# 1. Multi-Device-Modus in .env aktivieren```bash### Starten## 🚀 Verwendung```# DEVICE_PUBLIC_ID wird pro Device generiert# SERIAL_PORT wird ignoriert (automatisch erkannt)USB_SCAN_INTERVAL=12000MULTI_DEVICE_MODE=true```bash**Multi-Device:**```DEVICE_TOKEN=xxxDEVICE_PUBLIC_ID=growdash-001SERIAL_PORT=/dev/ttyACM0MULTI_DEVICE_MODE=false```bash**Single-Device (Legacy):**### Single-Device vs Multi-Device```COMMAND_POLL_INTERVAL=5TELEMETRY_INTERVAL=10BAUD_RATE=9600# Basis-Konfiguration (Template für alle Devices)LARAVEL_API_PATH=/api/growdash/agentLARAVEL_BASE_URL=https://grow.linn.games# Laravel Backend (für alle Devices)USB_SCAN_INTERVAL=12000# Default: 12000s (3.33 Stunden)# USB-Scan-Intervall (in Sekunden)MULTI_DEVICE_MODE=true# Multi-Device-Modus aktivieren```bash### .env Einstellungen## 📝 Konfiguration- Optional: Backend-Abmeldung (Heartbeat timeout)- Device wird aus interner Liste entfernt- Thread wird sauber beendet (`device.stop()`)- USB-Scan erkennt fehlendes Device**Getrennte Devices:**- Device meldet sich automatisch beim Backend (Onboarding wenn nötig)- DeviceInstance wird erstellt und Thread gestartet- USB-Scan erkennt neuen Port**Neue Devices:**### 4. Hot-Plug Support- **Unabhängige Loops** (keine Interferenz zwischen Devices)- **Eigener HardwareAgent** für Telemetrie/Commands/Heartbeat- **Eigener LaravelClient** für Backend-Kommunikation- **Eigene SerialProtocol-Instanz** für Arduino-KommunikationJedes Device läuft in einem **eigenen Thread**:### 3. Separate Device-Threads```- growdash-ttyACM0Beispiel:growdash-{port_name}```Falls Vendor/Product-ID nicht verfügbar:```- growdash-10c4-ea60-ttyUSB1  # CP2102 (ESP32)- growdash-1a86-7523-ttyUSB0  # CH340 Serial- growdash-2341-0043-ttyACM0  # Arduino UnoBeispiele:growdash-{vendor_id}-{product_id}-{port_name}```**Device-ID Format:**```)    device_id="growdash-2341-0043-ttyACM0"    config_template=AgentConfig(),  # Basis-Config    port="/dev/ttyACM0",DeviceInstance(```pythonFür jeden erkannten Port wird ein **DeviceInstance-Objekt** erstellt:### 2. Device-Erkennung- **Erkennung:** Filtert nach Arduino/USB-Serial-Devices (Arduino, CH340, FTDI)- **Periodisch:** Alle N Sekunden (konfigurierbar via `USB_SCAN_INTERVAL`)- **Beim Start:** Sofortiger Scan aller verfügbaren PortsDer **USBDeviceManager** scannt automatisch verfügbare USB-Ports:### 1. USB-Scanning## 🎯 FunktionsweiseDer GrowDash Hardware Agent unterstützt die gleichzeitige Verwaltung **mehrerer Arduino-Devices** über USB.Python-Agent für automatisierte Growbox-Steuerung. Läuft auf Raspberry Pi, kommuniziert mit Arduino über Serial und mit Laravel-Backend via HTTPS.

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

### Device-ID Format

```
growdash-2341-0043-ttyACM0  # Arduino Uno auf /dev/ttyACM0
growdash-1a86-7523-ttyUSB0  # CH340 auf /dev/ttyUSB0
growdash-ttyACM1            # Fallback wenn keine Hardware-IDs verfügbar
```

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
