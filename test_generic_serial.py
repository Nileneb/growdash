#!/usr/bin/env python3
"""
Beispiel: Generic Serial Device Support testen
===============================================

Dieses Skript demonstriert die neuen Features:
1. USB-Scan mit allen Devices
2. Board-Klassifikation
3. Handshake-Test
4. Device-Info Display
"""

import sys
import time
from usb_device_manager import USBScanner, USBDeviceInfo


def scan_and_display():
    """Scanne alle USB-Devices und zeige Details"""
    print("=" * 60)
    print("🔍 USB Device Scanner - Generic Serial Support")
    print("=" * 60)
    print()
    
    devices = USBScanner.scan_ports()
    
    if not devices:
        print("❌ Keine seriellen Devices gefunden!")
        print()
        print("Tipps:")
        print("  - Stecke ein Arduino/USB-Device an")
        print("  - Prüfe ob pyserial installiert ist: pip install pyserial")
        print("  - Unter Linux: Prüfe Berechtigungen (dialout group)")
        return
    
    print(f"✅ {len(devices)} Device(s) gefunden:\n")
    
    for i, dev in enumerate(devices, 1):
        print(f"Device #{i}")
        print(f"  Port:        {dev.port}")
        print(f"  Board Type:  {dev.board_type}")
        print(f"  Vendor ID:   {dev.vendor_id or 'N/A'}")
        print(f"  Product ID:  {dev.product_id or 'N/A'}")
        print(f"  Description: {dev.description or 'N/A'}")
        
        # Emoji für Board-Typ
        emoji_map = {
            "arduino_uno": "🔵",
            "arduino_nano": "🟢",
            "esp32": "🟡",
            "generic_serial": "⚪"
        }
        emoji = emoji_map.get(dev.board_type, "❓")
        print(f"  Status:      {emoji} {dev.board_type}")
        
        print()
    
    return devices


def test_handshake(device: USBDeviceInfo):
    """Teste Handshake mit Device"""
    print(f"\n🤝 Teste Handshake mit {device.port}...")
    print(f"   (Sendet 'Status' und wartet auf Antwort)")
    
    try:
        success = USBScanner.try_handshake(device.port, baud=9600, timeout=3.0)
        
        if success:
            print(f"   ✅ Handshake erfolgreich!")
            print(f"   → Device antwortet auf Kommandos")
            return True
        else:
            print(f"   ⚠️  Kein Response vom Device")
            print(f"   → Mögliche Ursachen:")
            print(f"      - Device nutzt anderes Protokoll")
            print(f"      - Falsche Baud-Rate (versuche 115200)")
            print(f"      - Device wartet auf spezielle Init-Sequenz")
            return False
    except Exception as e:
        print(f"   ❌ Fehler: {e}")
        return False


def simulate_agent_payload(device: USBDeviceInfo):
    """Zeige wie der Agent-Payload aussehen würde"""
    print(f"\n📡 Agent würde folgendes an Laravel senden:")
    print("   POST /agent/heartbeat")
    
    import json
    payload = {
        "last_state": {
            "uptime": 3600,
            "memory_free": 512000,
            "python_version": "3.11.0",
            "platform": "linux"
        },
        "board_type": device.board_type,
        "port": device.port,
        "vendor_id": device.vendor_id,
        "product_id": device.product_id,
        "description": device.description
    }
    
    print(json.dumps(payload, indent=2))


def main():
    """Hauptfunktion"""
    # Schritt 1: Scanne Devices
    devices = scan_and_display()
    
    if not devices:
        sys.exit(1)
    
    # Schritt 2: Zeige Actions für generic_serial devices
    generic_devices = [d for d in devices if d.board_type == "generic_serial"]
    
    if generic_devices:
        print("=" * 60)
        print("⚠️  Generic Serial Devices gefunden!")
        print("=" * 60)
        print()
        print("Diese Devices sind noch nicht konfiguriert.")
        print("Im Laravel-Dashboard würde jetzt der Wizard erscheinen:")
        print()
        print("  1️⃣  Board-Profil wählen")
        print("  2️⃣  Serielles Protokoll definieren")
        print("  3️⃣  Sensoren/Aktoren konfigurieren")
        print("  4️⃣  VID/PID Mapping speichern")
        print()
        
        for dev in generic_devices:
            print(f"🔧 {dev.port} (VID:{dev.vendor_id} PID:{dev.product_id})")
    
    # Schritt 3: Handshake-Test (optional)
    print("\n" + "=" * 60)
    response = input("🤝 Handshake-Test durchführen? (y/n): ").strip().lower()
    
    if response == 'y':
        for dev in devices:
            test_handshake(dev)
            time.sleep(0.5)
    
    # Schritt 4: Zeige Beispiel-Payload
    if devices:
        print("\n" + "=" * 60)
        simulate_agent_payload(devices[0])
    
    print("\n" + "=" * 60)
    print("✅ Test abgeschlossen!")
    print("=" * 60)
    print()
    print("Nächste Schritte:")
    print("  1. Laravel-Datenbank migrieren (siehe GENERIC_SERIAL_SUPPORT.md)")
    print("  2. Backend-Endpoints implementieren")
    print("  3. UI-Wizard erstellen")
    print("  4. Agent mit neuem Device testen")
    print()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n👋 Abgebrochen")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fehler: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
