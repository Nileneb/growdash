#!/bin/bash
# Test-Script für USB Device Manager

echo "🔍 GrowDash USB Device Manager - Test"
echo "======================================"
echo ""

# 1. USB-Ports scannen
echo "📌 Test 1: USB-Ports scannen"
echo "-----------------------------"
python3 -c "
from usb_device_manager import USBScanner
import json

devices = USBScanner.scan_ports()

if not devices:
    print('❌ Keine USB-Devices gefunden')
    print('   Stelle sicher dass Arduino angeschlossen ist')
else:
    print(f'✅ {len(devices)} Device(s) gefunden:')
    print()
    for dev in devices:
        print(f'  Port:        {dev.port}')
        print(f'  Vendor ID:   {dev.vendor_id or \"N/A\"}')
        print(f'  Product ID:  {dev.product_id or \"N/A\"}')
        print(f'  Description: {dev.description or \"N/A\"}')
        print()
"

echo ""

# 2. Device-ID Generator testen
echo "📌 Test 2: Device-ID Generierung"
echo "---------------------------------"
python3 -c "
from usb_device_manager import USBScanner, USBDeviceManager
from agent import AgentConfig

devices = USBScanner.scan_ports()
if devices:
    config = AgentConfig()
    manager = USBDeviceManager(config, scan_interval=60)
    
    for dev in devices:
        device_id = manager._generate_device_id(dev)
        print(f'  {dev.port} → {device_id}')
else:
    print('  ⚠️ Keine Devices zum Testen')
"

echo ""

# 3. Multi-Device Config prüfen
echo "📌 Test 3: Konfiguration prüfen"
echo "--------------------------------"

if grep -q "MULTI_DEVICE_MODE=true" .env 2>/dev/null; then
    echo "  ✅ MULTI_DEVICE_MODE=true (aktiviert)"
else
    echo "  ⚠️ MULTI_DEVICE_MODE=false oder nicht gesetzt"
    echo "     Aktivieren mit: echo 'MULTI_DEVICE_MODE=true' >> .env"
fi

if grep -q "USB_SCAN_INTERVAL" .env 2>/dev/null; then
    INTERVAL=$(grep "USB_SCAN_INTERVAL" .env | cut -d'=' -f2)
    echo "  ✅ USB_SCAN_INTERVAL=${INTERVAL}s"
else
    echo "  ⚠️ USB_SCAN_INTERVAL nicht gesetzt (default: 12000s)"
fi

echo ""

# 4. Serial-Permissions prüfen
echo "📌 Test 4: Serial-Port Permissions"
echo "-----------------------------------"

if groups | grep -q "dialout"; then
    echo "  ✅ User ist in 'dialout' Gruppe"
else
    echo "  ❌ User NICHT in 'dialout' Gruppe"
    echo "     Hinzufügen mit: sudo usermod -a -G dialout \$USER"
    echo "     Danach: Neuanmeldung erforderlich"
fi

# Teste verfügbare Serial-Ports
PORTS=$(ls /dev/ttyACM* /dev/ttyUSB* 2>/dev/null)
if [ -n "$PORTS" ]; then
    echo "  ✅ Serial-Ports gefunden:"
    for PORT in $PORTS; do
        if [ -r "$PORT" ] && [ -w "$PORT" ]; then
            echo "     $PORT (read/write OK)"
        else
            echo "     $PORT (keine Berechtigung)"
        fi
    done
else
    echo "  ⚠️ Keine Serial-Ports gefunden"
fi

echo ""

# 5. pyserial Version prüfen
echo "📌 Test 5: Dependencies"
echo "-----------------------"

python3 -c "
import sys
try:
    import serial
    print(f'  ✅ pyserial {serial.__version__}')
except ImportError:
    print('  ❌ pyserial nicht installiert')
    print('     Installieren mit: pip install pyserial')
    sys.exit(1)

try:
    import serial.tools.list_ports
    print('  ✅ serial.tools.list_ports verfügbar')
except ImportError:
    print('  ❌ serial.tools.list_ports nicht verfügbar')
    sys.exit(1)
"

echo ""

# 6. Manager-Test (30s)
echo "📌 Test 6: USB Device Manager (30s Test)"
echo "-----------------------------------------"
echo "  Starte Manager mit 30s Scan-Intervall..."
echo "  (Strg+C zum Abbrechen)"
echo ""

python3 -c "
import time
import signal
import sys
from usb_device_manager import USBDeviceManager
from agent import AgentConfig

def signal_handler(sig, frame):
    print('\n  ⚠️ Test abgebrochen')
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

config = AgentConfig()
manager = USBDeviceManager(config, scan_interval=30)
manager.start()

print('  ✅ Manager gestartet')
print()

try:
    for i in range(30):
        time.sleep(1)
        if i == 5:
            devices = manager.get_active_devices()
            print(f'  📊 Nach 5s: {len(devices)} aktive Device(s)')
            for port, dev in devices.items():
                status = '✅' if dev.is_alive() else '❌'
                print(f'     {status} {dev.device_id} ({port})')
        if i == 29:
            print()
            print('  ✅ Test erfolgreich abgeschlossen')
            
except KeyboardInterrupt:
    print('\n  ⚠️ Test abgebrochen')
finally:
    manager.stop()
    print('  🛑 Manager gestoppt')
" || true

echo ""
echo "======================================"
echo "✅ Test abgeschlossen"
echo ""
echo "Nächste Schritte:"
echo "  1. Multi-Device aktivieren: echo 'MULTI_DEVICE_MODE=true' >> .env"
echo "  2. Agent starten: ./grow_start.sh"
echo "  3. Logs prüfen: tail -f agent.log"
