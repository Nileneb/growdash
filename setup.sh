#!/bin/bash
# GrowDash Setup - Clean Version

cd "$(dirname "$0")"

echo ""
echo "🌱 GrowDash Setup"
echo "================="
echo ""

# Virtual Environment aktivieren ODER erstellen
if [ ! -d "venv" ]; then
    echo "📦 Erstelle Python Virtual Environment..."
    python3 -m venv venv
    source venv/bin/activate
    echo "✅ Virtual Environment erstellt"
    echo ""
    echo "📚 Installiere Dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
    echo "✅ Dependencies installiert"
    echo ""
else
    source venv/bin/activate
    echo "✅ Virtual Environment aktiviert"
fi

# .env erstellen falls nicht vorhanden
if [ ! -f ".env" ]; then
    echo ""
    echo "📄 Erstelle .env aus .env.example..."
    cp .env.example .env
    echo "✅ .env erstellt"
    echo ""
    echo "⚠️  WICHTIG: Trage Device-Credentials in .env ein:"
    echo "   - DEVICE_PUBLIC_ID=deine-device-id"
    echo "   - DEVICE_TOKEN=dein-token"
    echo ""
    echo "Diese erhältst du vom Laravel-Backend unter:"
    echo "   https://grow.linn.games/devices"
    echo ""
else
    echo "✅ .env vorhanden"
fi

# Check ob Credentials gesetzt sind
if ! grep -q "^DEVICE_PUBLIC_ID=.\+" .env || ! grep -q "^DEVICE_TOKEN=.\+" .env; then
    echo ""
    echo "⚠️  DEVICE_PUBLIC_ID oder DEVICE_TOKEN fehlt in .env!"
    echo ""
    echo "Bitte trage folgende Werte in .env ein:"
    echo "   DEVICE_PUBLIC_ID=deine-device-id"
    echo "   DEVICE_TOKEN=dein-token"
    echo ""
    echo "Diese erhältst du vom Laravel-Backend:"
    echo "   1. Gehe zu https://grow.linn.games/devices"
    echo "   2. Klicke auf 'Neues Device hinzufügen'"
    echo "   3. Kopiere Device-ID und Token"
    echo "   4. Füge sie in .env ein"
    echo ""
    read -p "Möchtest du .env jetzt bearbeiten? (j/n): " edit
    if [[ "$edit" =~ ^[jJyY]$ ]]; then
        ${EDITOR:-nano} .env
    fi
    echo ""
    echo "Nach dem Eintragen starte den Agent mit:"
    echo "  ./grow_start.sh"
    echo ""
    exit 0
fi

echo ""
echo "✅ Setup abgeschlossen!"
echo ""
echo "Agent starten:"
echo "  ./grow_start.sh"
echo ""
