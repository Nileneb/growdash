#!/bin/bash
# Skript zum Starten der GrowDash-Anwendung

# Zum Projektverzeichnis wechseln
#cd "$(dirname "$0")"

# Prüfen, ob virtuelle Umgebung vorhanden ist und aktivieren
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "Virtuelle Umgebung aktiviert."
else
    echo "Warnung: Keine virtuelle Umgebung gefunden. Verwende System-Python."
fi

# Umgebungsvariablen setzen (falls nötig)
export SERIAL_PORT=/dev/ttyACM0
export BAUD=9600
# export CAM_WIDTH=640
# export CAM_HEIGHT=360

# Anwendung starten
echo "Starte GrowDash..."
python app.py