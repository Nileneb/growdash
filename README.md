# GrowDash - Vereinfachte Version

Eine modulare Anwendung, die nur auf Arduino-Steuerung und Webcam-Funktionalität fokussiert ist.

## Struktur

- **app.py** - Hauptanwendung (FastAPI) - stark vereinfacht
- **arduino.py** - Arduino-Kommunikationsmodul
- **camera.py** - Webcam-Modul mit Unterstützung für Video und Audio
- **static/** - Statische Dateien für das vereinfachte Web-Interface
- **captures/** - Verzeichnis für gespeicherte Kamerabilder

## Installation

```bash
# Virtuelle Umgebung erstellen
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# oder
# .venv\Scripts\activate  # Windows

# Für PyAudio werden zusätzliche Abhängigkeiten benötigt
# Ubuntu/Debian:
# sudo apt-get install portaudio19-dev python3-pyaudio

# Abhängigkeiten installieren
pip install -r requirements.txt
```

Für die PyAudio-Installation benötigen Sie möglicherweise zusätzliche Systembibliotheken:
- **Ubuntu/Debian**: `sudo apt-get install portaudio19-dev python3-pyaudio`
- **Windows**: Keine zusätzlichen Schritte erforderlich, pip sollte funktionieren
- **macOS**: `brew install portaudio`

## Konfiguration

Die Anwendung verwendet folgende Umgebungsvariablen:

- `SERIAL_PORT` - Serieller Port für Arduino (z.B. /dev/ttyACM0)
- `BAUD` - Baudrate für serielle Kommunikation (Standard: 9600)
- `CAM_DEVICE` - Kamera-Gerät (z.B. "/dev/video0")
- `CAM_WIDTH` - Kameraauflösung Breite (Standard: 640)
- `CAM_HEIGHT` - Kameraauflösung Höhe (Standard: 360)
- `CAM_FPS` - Kamera-Framerate (Standard: 7)
- `AUDIO_ENABLED` - Audio aktivieren (Standard: "true")
- `AUDIO_RATE` - Audio-Samplerate (Standard: 44100)

## Ausführung

```bash
# Direkt starten
python app.py

# Oder mit uvicorn
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

Die Anwendung ist dann unter http://localhost:8000 erreichbar.

## API-Endpunkte

- `/` - Web-Interface (vereinfacht, nur Arduino und Webcam)
- `/snapshot` - Einzelbild der Kamera
- `/video.mjpg` - MJPEG-Stream der Kamera
- `/audio.wav` - Audio-Stream vom Mikrofon der Webcam
- `/api/command` - POST-Endpunkt zum Senden von Befehlen an den Arduino
- `/api/ports` - Information über verfügbare serielle Ports
- `/ws` - WebSocket für Echtzeit-Kommunikation mit dem Arduino

## Arduino-Befehle

Senden Sie beliebige Befehle über den `/api/command`-Endpunkt oder den WebSocket.
