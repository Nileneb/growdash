#!/bin/bash
# GrowDash Agent - Einfacher Installer

echo ""
echo "🌱 GrowDash Agent - Installation"
echo "================================="
echo ""

# 1. Virtual Environment
if [ ! -d ".venv" ]; then
    echo "📦 Erstelle virtuelle Python-Umgebung..."
    python3 -m venv .venv
    echo "✅ Virtual Environment erstellt"
    echo ""
fi

# Aktivieren
source .venv/bin/activate

# 2. Dependencies
echo "📚 Installiere Dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ Dependencies installiert"
echo ""

# 3. .env erstellen
if [ ! -f ".env" ]; then
    echo "📄 Erstelle .env Konfiguration..."
    cp .env.example .env
    echo "✅ .env erstellt"
    echo ""
fi

# 4. Fertig
echo "✅ Installation abgeschlossen!"
echo ""
echo "Nächster Schritt: Onboarding"
echo "  ./setup.sh"
echo ""
echo "Oder direkt:"
echo "  source .venv/bin/activate"
echo "  python bootstrap.py"
echo ""
