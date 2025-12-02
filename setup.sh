#!/bin/bash
# Setup-Wrapper für einfacheren Einstieg

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
fi

# .env erstellen falls nicht vorhanden
if [ ! -f ".env" ]; then
    echo "📄 Erstelle .env..."
    cp .env.example .env
    echo "✅ .env erstellt"
    echo ""
fi

# Onboarding starten
python bootstrap.py

# Wenn erfolgreich, Agent starten
if [ $? -eq 0 ]; then
    echo ""
    read -p "Agent jetzt starten? (j/n): " start
    if [[ "$start" =~ ^[jJyY]$ ]]; then
        echo ""
        ./grow_start.sh
    else
        echo ""
        echo "Agent später starten mit:"
        echo "  ./grow_start.sh"
        echo ""
    fi
fi
