#!/bin/bash
# Arduino-CLI Installer für GrowDash

set -e

echo "🔧 Arduino-CLI Installation"
echo "==========================="
echo ""

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
        echo ""
        echo "Manuelle Installation:"
        echo "  https://arduino.github.io/arduino-cli/latest/installation/"
        exit 1
        ;;
esac

echo "System: $(uname -s) $ARCH"
echo "Arduino-CLI Architektur: $ARDUINO_ARCH"
echo ""

# Check if already installed
if command -v arduino-cli &> /dev/null; then
    CURRENT_VERSION=$(arduino-cli version | head -n1)
    echo "✅ Arduino-CLI bereits installiert:"
    echo "   $CURRENT_VERSION"
    echo "   Pfad: $(which arduino-cli)"
    echo ""
    read -p "Trotzdem neu installieren? (j/n): " -r REINSTALL
    if [ "$REINSTALL" != "j" ] && [ "$REINSTALL" != "J" ]; then
        exit 0
    fi
    echo ""
fi

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

cd "$TEMP_DIR"

# Download
echo "📦 Lade Arduino-CLI herunter..."
DOWNLOAD_URL="https://downloads.arduino.cc/arduino-cli/arduino-cli_latest_${ARDUINO_ARCH}.tar.gz"

if command -v wget &> /dev/null; then
    wget -q --show-progress "$DOWNLOAD_URL" -O arduino-cli.tar.gz
elif command -v curl &> /dev/null; then
    curl -fsSL --progress-bar "$DOWNLOAD_URL" -o arduino-cli.tar.gz
else
    echo "❌ Weder wget noch curl gefunden."
    echo "Bitte installiere eines dieser Tools:"
    echo "  sudo apt install wget"
    exit 1
fi

# Extract
echo "📂 Entpacke Archiv..."
tar -xzf arduino-cli.tar.gz

if [ ! -f "arduino-cli" ]; then
    echo "❌ Fehler beim Entpacken"
    exit 1
fi

# Make executable
chmod +x arduino-cli

# Install location
echo ""
echo "Wähle Installations-Ort:"
echo "  1) /usr/local/bin/arduino-cli (System-weit, benötigt sudo)"
echo "  2) ~/.local/bin/arduino-cli (Nur für aktuellen User)"
echo ""
read -p "Auswahl (1 oder 2): " -r INSTALL_CHOICE

case $INSTALL_CHOICE in
    1)
        INSTALL_PATH="/usr/local/bin/arduino-cli"
        if [ -w "/usr/local/bin" ]; then
            mv arduino-cli "$INSTALL_PATH"
        else
            echo "Benötige sudo-Rechte..."
            sudo mv arduino-cli "$INSTALL_PATH"
        fi
        ;;
    2)
        INSTALL_PATH="$HOME/.local/bin/arduino-cli"
        mkdir -p "$HOME/.local/bin"
        mv arduino-cli "$INSTALL_PATH"
        
        # Add to PATH if not already there
        if [[ ":$PATH:" != *":$HOME/.local/bin:"* ]]; then
            echo ""
            echo "⚠️  $HOME/.local/bin ist nicht in deinem PATH!"
            echo "Füge folgende Zeile zu ~/.bashrc hinzu:"
            echo ""
            echo '  export PATH="$HOME/.local/bin:$PATH"'
            echo ""
            echo "Dann shell neu laden:"
            echo "  source ~/.bashrc"
            echo ""
        fi
        ;;
    *)
        echo "❌ Ungültige Auswahl"
        exit 1
        ;;
esac

echo "✅ Arduino-CLI installiert: $INSTALL_PATH"
echo ""

# Update .env if in growdash directory
if [ -f ".env" ] || [ -f "../.env" ]; then
    ENV_FILE=".env"
    [ -f "../.env" ] && ENV_FILE="../.env"
    
    if grep -q "^ARDUINO_CLI_PATH=" "$ENV_FILE" 2>/dev/null; then
        sed -i "s|^ARDUINO_CLI_PATH=.*|ARDUINO_CLI_PATH=$INSTALL_PATH|" "$ENV_FILE"
        echo "✅ .env aktualisiert"
    else
        echo "ARDUINO_CLI_PATH=$INSTALL_PATH" >> "$ENV_FILE"
        echo "✅ ARDUINO_CLI_PATH zu .env hinzugefügt"
    fi
    echo ""
fi

# Verify installation
echo "🔍 Verifiziere Installation..."
VERSION=$("$INSTALL_PATH" version | head -n1)
echo "   $VERSION"
echo ""

# Install Arduino AVR core
echo "📦 Installiere Arduino AVR Boards (für Uno, Nano, etc.)..."
"$INSTALL_PATH" core update-index
"$INSTALL_PATH" core install arduino:avr

echo ""
echo "============================================"
echo "✅ Arduino-CLI Setup abgeschlossen!"
echo "============================================"
echo ""
echo "Testen:"
echo "  arduino-cli version"
echo "  arduino-cli board list"
echo ""
echo "Firmware-Updates sind jetzt verfügbar."
echo ""
