# GrowDash - Generic Serial Device Support 🚀

## Was ist neu?

Das GrowDash-System unterstützt jetzt **beliebige serielle Geräte**, nicht nur Arduino Uno/Nano/ESP32!

### ✨ Neue Features

1. **Universelle USB-Erkennung**

   - Alle `/dev/ttyACM*` und `/dev/ttyUSB*` Geräte werden erkannt
   - Intelligente Klassifikation basierend auf VID/PID
   - Keywords nur noch als Hints, keine harten Filter

2. **Board-Typen**

   - `arduino_uno` - Arduino Uno Boards
   - `arduino_nano` - Arduino Nano (CH340/FTDI)
   - `esp32` - ESP32 Development Boards
   - `generic_serial` - **NEU!** Alle anderen seriellen Geräte

3. **Laravel-Integration**
   - Agent sendet Board-Typ, VID/PID, Port-Info
   - "Unknown Device Wizard" im Dashboard
   - Persistente VID/PID Mappings für Auto-Konfiguration

## Quick Start

### Test-Skript ausführen

```bash
python test_generic_serial.py
```

**Output-Beispiel:**

```
🔍 USB Device Scanner - Generic Serial Support
============================================================

✅ 2 Device(s) gefunden:

Device #1
  Port:        /dev/ttyACM0
  Board Type:  arduino_uno
  Vendor ID:   2341
  Product ID:  0043
  Description: Arduino Uno
  Status:      🔵 arduino_uno

Device #2
  Port:        /dev/ttyUSB0
  Board Type:  generic_serial
  Vendor ID:   1a86
  Product ID:  7523
  Description: USB Serial Device
  Status:      ⚪ generic_serial

⚠️  Generic Serial Devices gefunden!
============================================================

Im Laravel-Dashboard würde jetzt der Wizard erscheinen:
  1️⃣  Board-Profil wählen
  2️⃣  Serielles Protokoll definieren
  3️⃣  Sensoren/Aktoren konfigurieren
  4️⃣  VID/PID Mapping speichern
```

### Code-Beispiel

```python
from usb_device_manager import USBScanner

# Alle Devices scannen
devices = USBScanner.scan_ports()

for dev in devices:
    print(f"{dev.port}: {dev.board_type}")
    # Output: /dev/ttyUSB0: generic_serial

    # Handshake testen
    if USBScanner.try_handshake(dev.port):
        print("Device antwortet!")
```

## Dokumentation

📚 **Vollständige Dokumentation:**

- [`docs/GENERIC_SERIAL_SUPPORT.md`](docs/GENERIC_SERIAL_SUPPORT.md) - Ausführlicher Guide
- [`docs/IMPLEMENTATION_SUMMARY.md`](docs/IMPLEMENTATION_SUMMARY.md) - Implementation Summary

### Wichtige Abschnitte:

1. **Agent-Änderungen**: Wie USBScanner jetzt funktioniert
2. **Laravel-Backend**: Erforderliche Datenbank-Änderungen und Endpoints
3. **UI-Wizard**: Step-by-Step Konfiguration für unbekannte Geräte
4. **Workflow**: Vom ersten Anstecken bis zur Auto-Konfiguration

## Laravel-Setup

### Schritt 1: Datenbank-Migration

```bash
php artisan make:migration add_generic_serial_support
```

**Migration-Inhalt:**

```php
// Neue Tabelle für Board-Mappings
Schema::create('board_types', function (Blueprint $table) {
    $table->id();
    $table->string('vendor_id', 4);
    $table->string('product_id', 4);
    $table->string('board_type', 50);
    $table->text('description')->nullable();
    $table->json('serial_config')->nullable();
    $table->json('sensor_capabilities')->nullable();
    $table->json('actuator_capabilities')->nullable();
    $table->timestamps();
    $table->unique(['vendor_id', 'product_id']);
});

// Erweitere devices Tabelle
Schema::table('devices', function (Blueprint $table) {
    $table->string('board_type', 50)->nullable();
    $table->string('vendor_id', 4)->nullable();
    $table->string('product_id', 4)->nullable();
    $table->string('port', 50)->nullable();
    $table->boolean('is_configured')->default(false);
});
```

### Schritt 2: Heartbeat-Endpoint erweitern

```php
public function heartbeat(Request $request)
{
    $device = auth('device')->user();

    $device->update([
        'last_seen_at' => now(),
        'last_state' => $request->input('last_state'),
        'board_type' => $request->input('board_type'),
        'vendor_id' => $request->input('vendor_id'),
        'product_id' => $request->input('product_id'),
        'port' => $request->input('port'),
    ]);

    // Auto-Configure wenn VID/PID bekannt
    if (!$device->is_configured) {
        $boardType = BoardType::where('vendor_id', $request->vendor_id)
                              ->where('product_id', $request->product_id)
                              ->first();

        if ($boardType) {
            $device->update([
                'board_type' => $boardType->board_type,
                'is_configured' => true,
            ]);
        } elseif ($device->board_type === 'generic_serial') {
            event(new UnknownDeviceDetected($device));
        }
    }

    return response()->json(['status' => 'ok']);
}
```

### Schritt 3: UI-Wizard erstellen

Siehe `docs/GENERIC_SERIAL_SUPPORT.md` für vollständige UI-Spezifikation.

## Workflow

### 🆕 Neues Generic Device (erstes Mal)

```
1. Device anstecken → /dev/ttyUSB0
2. Agent erkennt → generic_serial (VID:1a86 PID:7523)
3. Heartbeat → Laravel
4. Laravel → Kein Mapping gefunden
5. UI → "Unknown device" Banner
6. User → "Configure" klicken
7. Wizard → Protokoll & Capabilities definieren
8. Speichern → VID/PID Mapping in DB
9. Device → is_configured = true ✅
```

### 🔄 Gleiches Device (nächstes Mal)

```
1. Device anstecken → /dev/ttyUSB0
2. Agent → Heartbeat mit VID:1a86 PID:7523
3. Laravel → Findet Mapping in DB
4. Auto-Config → Device als "my_custom_board"
5. Ready to use! ✅ (kein Wizard)
```

## Testing

### Unit Tests

```bash
# USB Scanner testen
python -c "from usb_device_manager import USBScanner; \
           print(USBScanner.scan_ports())"

# Handshake testen
python -c "from usb_device_manager import USBScanner; \
           print(USBScanner.try_handshake('/dev/ttyUSB0'))"
```

### Integration Test

```bash
# Test-Skript mit allen Features
python test_generic_serial.py
```

### Agent mit Generic Device

```bash
# .env anpassen
SERIAL_PORT=/dev/ttyUSB0
DEVICE_PUBLIC_ID=test-generic-001

# Agent starten
python agent.py
```

**Erwartete Logs:**

```
📱 Device-Instanz erstellt: test-generic-001 auf /dev/ttyUSB0
🆕 Neues Device erkannt: /dev/ttyUSB0 → test-generic-001 (Type: generic_serial)
📡 Heartbeat gesendet mit board_type: generic_serial
```

## Bekannte Board-Mappings

| VID    | PID    | Board Type     | Chip       |
| ------ | ------ | -------------- | ---------- |
| `2341` | `0043` | `arduino_uno`  | ATmega328P |
| `1a86` | `7523` | `arduino_nano` | CH340      |
| `0403` | `6001` | `arduino_nano` | FTDI FT232 |
| `10c4` | `ea60` | `esp32`        | CP2102     |
| `1a86` | `55d4` | `esp32`        | CH9102     |

**Eigene Mappings hinzufügen:**

```python
# In usb_device_manager.py
KNOWN_BOARDS = {
    ("your_vid", "your_pid"): "your_board_type",
}
```

## FAQ

**Q: Was wenn mein Device keine VID/PID hat?**  
A: Es wird als `generic_serial` erkannt mit `vendor_id=None`. Du kannst es trotzdem manuell konfigurieren, aber Auto-Recognition funktioniert nicht.

**Q: Kann ich ein Arduino als generic_serial nutzen?**  
A: Ja! Wenn du ein Custom-Protokoll nutzt oder die Auto-Erkennung nicht funktioniert.

**Q: Unterstützt das System Bluetooth/Network Serial?**  
A: Aktuell nur USB-Serial. Support für andere Transporte ist geplant.

## Nächste Schritte

- [ ] Laravel-Datenbank migrieren
- [ ] Backend-Endpoints implementieren
- [ ] UI-Wizard bauen
- [ ] Mit echten Devices testen
- [ ] Board-Profile Import/Export (optional)
- [ ] Community Board Library (optional)

## Support

Bei Fragen oder Problemen:

1. Siehe [`docs/GENERIC_SERIAL_SUPPORT.md`](docs/GENERIC_SERIAL_SUPPORT.md)
2. Prüfe Logs: `journalctl -u growdash-agent -f`
3. Test-Skript ausführen: `python test_generic_serial.py`

---

**Happy Growing! 🌱**
