#!/bin/bash
# GrowDash Startskript

# Umgebungsvariablen
export SERIAL_PORT=${SERIAL_PORT:-"/dev/ttyUSB0"}
export BAUD=${BAUD:-"9600"}
export CAM_WIDTH=${CAM_WIDTH:-"640"}
export CAM_HEIGHT=${CAM_HEIGHT:-"360"}
export CAM_FPS=${CAM_FPS:-"7"}
export AUDIO_ENABLED=${AUDIO_ENABLED:-"true"}
export AUDIO_RATE=${AUDIO_RATE:-"44100"}

# Prüfen, ob das Datenverzeichnis existiert
if [ ! -d "data" ]; then
  mkdir -p data
  echo "Datenverzeichnis erstellt."
fi

# Prüfen, ob das Captures-Verzeichnis existiert
if [ ! -d "captures" ]; then
  mkdir -p captures
  echo "Captures-Verzeichnis erstellt."
fi

# Abhängigkeiten prüfen und installieren, falls notwendig
echo "Prüfe Abhängigkeiten..."
pip install -q -r requirements.txt

# Datenbank initialisieren
python -c "from scripts.db_handler import get_db_handler; get_db_handler().log_message('System gestartet', level='info')"

echo "Starte GrowDash mit folgenden Einstellungen:"
echo "  - SERIAL_PORT: $SERIAL_PORT"
echo "  - BAUD:        $BAUD"
echo "  - CAM_WIDTH:   $CAM_WIDTH"
echo "  - CAM_HEIGHT:  $CAM_HEIGHT"
echo "  - CAM_FPS:     $CAM_FPS"
echo "  - AUDIO:       $AUDIO_ENABLED ($AUDIO_RATE Hz)"
echo ""

# Anwendung starten
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
