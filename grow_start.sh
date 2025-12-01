#!/bin/bash
# Skript zum Starten des GrowDash Hardware-Agents

# Zum Projektverzeichnis wechseln
cd "$(dirname "$0")"

# Prüfen, ob virtuelle Umgebung vorhanden ist und aktivieren
if [ -d ".venv" ]; then
    source .venv/bin/activate
    echo "Virtuelle Umgebung aktiviert."
else
    echo "Warnung: Keine virtuelle Umgebung gefunden. Verwende System-Python."
fi

# .env Datei prüfen
if [ ! -f ".env" ]; then
    echo "FEHLER: .env Datei nicht gefunden!"
    echo "Bitte .env.example nach .env kopieren und anpassen:"
    echo "  cp .env.example .env"
    exit 1
fi

# Agent starten
echo "Starte GrowDash Hardware-Agent..."
python agent.py