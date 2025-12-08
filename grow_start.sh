#!/bin/bash
# GrowDash Agent starten (clean)

set -e

cd "$(dirname "$0")"

# Virtual Environment aktivieren
if [ ! -d "venv" ]; then
    echo "❌ Virtual Environment fehlt!"
    echo "Bitte erst ./setup.sh ausführen"
    exit 1
fi

source venv/bin/activate

# .env prüfen
if [ ! -f ".env" ]; then
    echo "❌ .env fehlt!"
    echo "Bitte erst ./setup.sh ausführen"
    exit 1
fi

# Credentials prüfen
if ! grep -q "^DEVICE_PUBLIC_ID=.\+" .env || ! grep -q "^DEVICE_TOKEN=.\+" .env; then
    echo ""
    echo "❌ DEVICE_PUBLIC_ID oder DEVICE_TOKEN fehlt in .env!"
    echo "Bitte ./setup.sh ausführen und Pairing abschließen."
    exit 1
fi

check_arduino_cli() {
    if command -v arduino-cli >/dev/null 2>&1; then
        return 0
    fi

    echo ""
    read -p "Arduino-CLI installieren? (j/n): " install_cli
    if [[ ! "$install_cli" =~ ^[jJyY]$ ]]; then
        echo "Übersprungen (Firmware-Updates nicht verfügbar)."
        return 0
    fi

    echo "📦 Installiere Arduino-CLI..."

    ARCH=$(uname -m)
    case $ARCH in
        x86_64) ARDUINO_ARCH="Linux_64bit" ;;
        aarch64|arm64) ARDUINO_ARCH="Linux_ARM64" ;;
        armv7l) ARDUINO_ARCH="Linux_ARMv7" ;;
        *)
            echo "❌ Unbekannte Architektur: $ARCH"
            echo "Bitte manuell installieren: https://arduino.github.io/arduino-cli/latest/installation/"
            return 1
            ;;
    esac

    TEMP_DIR=$(mktemp -d)
    cd "$TEMP_DIR"
    DOWNLOAD_URL="https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_${ARDUINO_ARCH}.tar.gz"
    if command -v wget >/dev/null 2>&1; then
        wget -q "$DOWNLOAD_URL" -O arduino-cli.tar.gz
    else
        curl -fsSL "$DOWNLOAD_URL" -o arduino-cli.tar.gz
    fi
    tar -xzf arduino-cli.tar.gz

    if [ -w "/usr/local/bin" ]; then
        mv arduino-cli /usr/local/bin/
        echo "✅ Arduino-CLI installiert: /usr/local/bin/arduino-cli"
    else
        echo "Keine Schreibrechte für /usr/local/bin, versuche sudo..."
        if sudo mv arduino-cli /usr/local/bin/ 2>/dev/null; then
            echo "✅ Arduino-CLI installiert: /usr/local/bin/arduino-cli"
        else
            mkdir -p "$HOME/.local/bin"
            mv arduino-cli "$HOME/.local/bin/"
            echo "✅ Arduino-CLI installiert: $HOME/.local/bin/arduino-cli"
            if grep -q "^ARDUINO_CLI_PATH=" .env 2>/dev/null; then
                sed -i "s|^ARDUINO_CLI_PATH=.*|ARDUINO_CLI_PATH=$HOME/.local/bin/arduino-cli|" .env
            else
                echo "ARDUINO_CLI_PATH=$HOME/.local/bin/arduino-cli" >> .env
            fi
            echo "Bitte PATH anpassen: export PATH=\"$HOME/.local/bin:$PATH\""
        fi
    fi

    cd - >/dev/null
    rm -rf "$TEMP_DIR"

    echo "📦 Installiere Arduino AVR Boards..."
    arduino-cli core update-index
    arduino-cli core install arduino:avr
    echo "✅ Arduino-CLI Setup abgeschlossen"
}

# Arduino-CLI nur einmal prüfen
if [ ! -f ".arduino_cli_checked" ]; then
    check_arduino_cli || true
    touch .arduino_cli_checked
fi

echo "Installiere Python-Dependencies (requirements.txt in venv)..."
pip install -q --upgrade pip || { echo "❌ Upgrade pip fehlgeschlagen"; exit 1; }
pip install -q -r requirements.txt || { echo "❌ Pip-Installation fehlgeschlagen"; exit 1; }

echo "🚀 Starte GrowDash Agent..."

# Local API im Hintergrund starten (für Kamera-Streaming, Logs, etc.)
python3 /home/nileneb/growdash/local_api.py &
LOCAL_API_PID=$!
echo "📡 Local API gestartet (PID: $LOCAL_API_PID)"

# Agent im Vordergrund starten
exec python3 /home/nileneb/growdash/agent.py
python3 /home/nileneb/growdash/local_api.py &