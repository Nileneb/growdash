#!/bin/bash
# GrowDash Agent starten

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
    echo ""
    echo "Hole Device-Credentials von Laravel:"
    echo "  1. https://grow.linn.games/devices"
    echo "  2. Neues Device erstellen"
    echo "  3. ID + Token in .env eintragen"
    echo ""
    exit 1
fi

echo ""
echo "🚀 Starte GrowDash Agent..."
echo ""

# Agent starten
python agent.py
            echo "📦 Installiere Arduino-CLI..."
            
            # Detect architecture
            ARCH=$(uname -m)
            case $ARCH in
                x86_64)
                    ARDUINO_ARCH="Linux_64bit"
                    ;;
                aarch64|arm64)
                    ARDUINO_ARCH="Linux_ARM64"
                    ;;
                armv7l)
                    ARDUINO_ARCH="Linux_ARMv7"
                    ;;
                *)
                    echo "❌ Unbekannte Architektur: $ARCH"
                    echo "Bitte installiere Arduino-CLI manuell:"
                    echo "  https://arduino.github.io/arduino-cli/latest/installation/"
                    return 1
                    ;;
            esac
            
            # Download latest version
            TEMP_DIR=$(mktemp -d)
            cd "$TEMP_DIR" || exit 1
            
            echo "Lade Arduino-CLI für $ARDUINO_ARCH..."
            DOWNLOAD_URL="https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_${ARDUINO_ARCH}.tar.gz"
            
            if command -v wget &> /dev/null; then
                wget -q "$DOWNLOAD_URL" -O arduino-cli.tar.gz
            elif command -v curl &> /dev/null; then
                curl -fsSL "$DOWNLOAD_URL" -o arduino-cli.tar.gz
            else
                echo "❌ Weder wget noch curl gefunden. Bitte manuell installieren."
                cd - > /dev/null
                rm -rf "$TEMP_DIR"
                return 1
            fi
            
            if [ $? -ne 0 ]; then
                echo "❌ Download fehlgeschlagen"
                cd - > /dev/null
                rm -rf "$TEMP_DIR"
                return 1
            fi
            
            # Extract
            tar -xzf arduino-cli.tar.gz
            
            # Install to /usr/local/bin (requires sudo) or ~/.local/bin
            if [ -w "/usr/local/bin" ]; then
                mv arduino-cli /usr/local/bin/
                echo "✅ Arduino-CLI installiert: /usr/local/bin/arduino-cli"
            else
                echo "Keine Schreibrechte für /usr/local/bin, versuche sudo..."
                sudo mv arduino-cli /usr/local/bin/
                if [ $? -eq 0 ]; then
                    echo "✅ Arduino-CLI installiert: /usr/local/bin/arduino-cli"
                else
                    # Fallback: user local bin
                    mkdir -p "$HOME/.local/bin"
                    mv arduino-cli "$HOME/.local/bin/"
                    echo "✅ Arduino-CLI installiert: $HOME/.local/bin/arduino-cli"
                    echo ""
                    echo "⚠️  Füge zur .env hinzu:"
                    echo "ARDUINO_CLI_PATH=$HOME/.local/bin/arduino-cli"
                    echo ""
                    # Update .env
                    if grep -q "^ARDUINO_CLI_PATH=" .env 2>/dev/null; then
                        sed -i "s|^ARDUINO_CLI_PATH=.*|ARDUINO_CLI_PATH=$HOME/.local/bin/arduino-cli|" .env
                    else
                        echo "ARDUINO_CLI_PATH=$HOME/.local/bin/arduino-cli" >> .env
                    fi
                fi
            fi
            
            # Cleanup
            cd - > /dev/null
            rm -rf "$TEMP_DIR"
            
            # Install Arduino AVR boards
            echo ""
            echo "📦 Installiere Arduino AVR Boards..."
            arduino-cli core update-index
            arduino-cli core install arduino:avr
            
            echo ""
            echo "✅ Arduino-CLI Setup abgeschlossen"
            echo ""
        else
            echo ""
            echo "ℹ️  Arduino-CLI wird NICHT installiert."
            echo "   Firmware-Updates sind nicht verfügbar."
            echo ""
            echo "Manuelle Installation später:"
            echo "  https://arduino.github.io/arduino-cli/latest/installation/"
            echo ""
        fi
    fi
}

# Arduino-CLI Check ausführen (nur einmal, nicht bei jedem Start nerven)
if [ ! -f ".arduino_cli_checked" ]; then
    check_arduino_cli
    touch .arduino_cli_checked
fi

# Agent starten
echo "Installiere Python-Dependencies (requirements.txt in venv)..."
pip install -q --upgrade pip || { echo "❌ Upgrade pip fehlgeschlagen"; exit 1; }
pip install -r requirements.txt || { echo "❌ Pip-Installation fehlgeschlagen"; exit 1; }

echo "Starte GrowDash Hardware-Agent..."
python3 agent.py