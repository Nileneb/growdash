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
    echo ""
    echo "FEHLER: .env Datei nicht gefunden!"
    echo "Erstelle .env aus Template..."
    cp .env.example .env
    echo "✅ .env erstellt"
    echo ""
fi

# Prüfen ob Device konfiguriert ist
DEVICE_ID=$(grep "^DEVICE_PUBLIC_ID=" .env | cut -d '=' -f2)
DEVICE_TOKEN=$(grep "^DEVICE_TOKEN=" .env | cut -d '=' -f2)

if [ -z "$DEVICE_ID" ] || [ -z "$DEVICE_TOKEN" ]; then
    echo ""
    echo "============================================================"
    echo "⚠️  Device ist noch nicht konfiguriert!"
    echo "============================================================"
    echo ""
    echo "Bitte führe zuerst das Onboarding durch:"
    echo ""
    echo "  python bootstrap.py"
    echo ""
    echo "Wähle dann:"
    echo "  1) Pairing-Code (Empfohlen)"
    echo "  2) Direct-Login (Power-User)"
    echo ""
    exit 1
fi

# Agent starten
echo "Starte GrowDash Hardware-Agent..."
python agent.py