# Generic Serial Device Support

## Überblick

Das GrowDash-System unterstützt jetzt nicht nur bekannte Arduino-Boards (Uno, Nano, ESP32), sondern auch **generische serielle Geräte**. Dies ermöglicht:

- Automatische Erkennung aller `/dev/ttyACM*` und `/dev/ttyUSB*` Geräte
- Intelligente Klassifikation basierend auf VID/PID
- Wizard-basierte Konfiguration für unbekannte Geräte
- Persistente Board-Mappings für wiederholte Verwendung

## Agent-seitige Änderungen

### 1. USBScanner (robuster)

Der `USBScanner` akzeptiert jetzt **alle** seriellen Geräte:

```python
@dataclass
class USBDeviceInfo:
    port: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    description: Optional[str] = None
    board_type: str = "generic_serial"  # Neu!
```

**Board-Typen:**

- `arduino_uno` - Arduino Uno (erkannt via VID/PID oder Keywords)
- `arduino_nano` - Arduino Nano (CH340/FTDI basiert)
- `esp32` - ESP32 Boards (CP2102/CH9102)
- `generic_serial` - Alle anderen seriellen Geräte

**Klassifikationslogik:**

1. **VID/PID Matching** (höchste Priorität)
   - Bekannte Kombinationen in `KNOWN_BOARDS` Dictionary
2. **Description Keywords** (nur Hints, keine harte Bedingung)
   - Keywords wie "arduino", "esp32" helfen bei der Klassifikation
3. **Default: generic_serial**

### 2. Heartbeat & Capabilities Payload

Der Agent sendet jetzt erweiterte Hardware-Informationen:

#### `/agent/heartbeat` Payload:

```json
{
  "last_state": {
    "uptime": 3600,
    "memory_free": 512000,
    "python_version": "3.11.0",
    "platform": "linux"
  },
  "board_type": "generic_serial",
  "port": "/dev/ttyUSB0",
  "vendor_id": "1a86",
  "product_id": "7523",
  "description": "USB Serial Device"
}
```

#### `/agent/capabilities` Payload:

```json
{
  "capabilities": {
    "board_name": "arduino_uno",
    "sensors": ["water_level", "tds", "temperature"],
    "actuators": ["spray_pump", "fill_valve"]
  },
  "board_type": "generic_serial",
  "port": "/dev/ttyUSB0",
  "vendor_id": "1a86",
  "product_id": "7523",
  "description": "USB Serial Device"
}
```

### 3. Handshake-Methode

Optionale Methode zum Testen der Kommunikation:

```python
USBScanner.try_handshake(port="/dev/ttyUSB0", baud=9600, timeout=3.0)
```

Sendet `"Status\n"` und wartet auf Antwort. Kann verwendet werden um zwischen:

- **Bekannten Arduino-Boards** (antwortet mit bekanntem Protokoll)
- **Generic Serial Devices** (antwortet nicht oder mit unbekanntem Protokoll)

zu unterscheiden.

## Laravel-seitige Implementierung

### 1. Datenbank-Schema

#### Neue Tabelle: `board_types`

Persistente Mappings für VID/PID → Board-Typ:

```sql
CREATE TABLE board_types (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    vendor_id VARCHAR(4) NOT NULL,           -- z.B. "1a86"
    product_id VARCHAR(4) NOT NULL,          -- z.B. "7523"
    board_type VARCHAR(50) NOT NULL,         -- z.B. "my_custom_board"
    description TEXT NULL,
    serial_config JSON NULL,                 -- Baudrate, Protokoll-Details
    sensor_capabilities JSON NULL,           -- Liste von Sensoren
    actuator_capabilities JSON NULL,         -- Liste von Aktoren
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    UNIQUE KEY unique_vid_pid (vendor_id, product_id)
);
```

**Beispiel-Einträge:**

```json
{
  "vendor_id": "1a86",
  "product_id": "7523",
  "board_type": "my_hydroponics_controller",
  "description": "Custom Hydroponics Controller v2",
  "serial_config": {
    "baud_rate": 9600,
    "protocol": "line_based",
    "delimiter": "\n",
    "handshake": "STATUS"
  },
  "sensor_capabilities": [
    { "key": "ph", "name": "pH Sensor", "unit": "pH" },
    { "key": "ec", "name": "EC Sensor", "unit": "mS/cm" }
  ],
  "actuator_capabilities": [
    { "key": "pump_a", "name": "Nährlösung Pumpe A" },
    { "key": "pump_b", "name": "Nährlösung Pumpe B" }
  ]
}
```

#### Erweiterung `devices` Tabelle:

```sql
ALTER TABLE devices
ADD COLUMN board_type VARCHAR(50) NULL,
ADD COLUMN vendor_id VARCHAR(4) NULL,
ADD COLUMN product_id VARCHAR(4) NULL,
ADD COLUMN port VARCHAR(50) NULL;
```

### 2. Backend-Endpoints

#### `POST /agent/heartbeat`

**Erwartete Request-Daten:**

```json
{
  "last_state": { ... },
  "board_type": "generic_serial",
  "port": "/dev/ttyUSB0",
  "vendor_id": "1a86",
  "product_id": "7523",
  "description": "USB Serial Device"
}
```

**Backend-Logik:**

```php
public function heartbeat(Request $request)
{
    $device = auth('device')->user();

    // Update device info
    $device->update([
        'last_seen_at' => now(),
        'last_state' => $request->input('last_state'),
        'board_type' => $request->input('board_type'),
        'vendor_id' => $request->input('vendor_id'),
        'product_id' => $request->input('product_id'),
        'port' => $request->input('port'),
    ]);

    // Check if board_type is generic_serial and not yet configured
    if ($device->board_type === 'generic_serial' && !$device->is_configured) {
        // Trigger "Unknown Device Wizard" in UI
        event(new UnknownDeviceDetected($device));
    }

    return response()->json(['status' => 'ok']);
}
```

#### `POST /agent/capabilities`

Ähnlich wie Heartbeat, speichert zusätzlich Capabilities.

```php
public function capabilities(Request $request)
{
    $device = auth('device')->user();

    $device->update([
        'capabilities' => $request->input('capabilities'),
        'board_type' => $request->input('board_type'),
        'vendor_id' => $request->input('vendor_id'),
        'product_id' => $request->input('product_id'),
        'port' => $request->input('port'),
    ]);

    return response()->json(['status' => 'ok']);
}
```

### 3. UI: "Unknown Serial Device" Wizard

#### Trigger

Wenn ein Device mit `board_type = "generic_serial"` auftaucht und noch nicht konfiguriert ist, zeigt das Dashboard:

```
⚠️ Unknown serial device detected on /dev/ttyUSB0
   Vendor ID: 1a86 | Product ID: 7523
   Description: USB Serial Device

   [Configure Device] [Ignore]
```

#### Wizard-Schritte

**Step 1: Board-Profil wählen**

```
Choose a board profile:
○ Arduino Uno
○ Arduino Nano
○ ESP32
○ Generic 8-bit µC
● Create new custom profile
```

**Step 2: Serial-Protokoll definieren**

```
Serial Protocol Configuration:
- Baud Rate: [9600 ▼]
- Protocol Type: ○ Line-based  ○ Binary  ○ JSON
- Line Delimiter: [\n]
- Handshake String: [STATUS]
- Response Format: [Plain Text ▼]
```

**Step 3: Sensoren/Aktoren definieren**

```
Define Capabilities:

Sensors:
+ Add Sensor
  - Key: [water_level]
  - Name: [Water Level]
  - Unit: [percent]
  - Parse Pattern: [WaterLevel: (\d+)]

Actuators:
+ Add Actuator
  - Key: [pump]
  - Name: [Water Pump]
  - Command ON: [PUMP_ON]
  - Command OFF: [PUMP_OFF]
```

**Step 4: Speichern & Testen**

```
Profile Name: [My Custom Controller]

[x] Save VID/PID mapping for future devices
    (Devices with VID:1a86 PID:7523 will be auto-configured)

[Test Connection]  [Save Profile]
```

#### Backend-Speicherung

```php
public function saveBoardProfile(Request $request)
{
    $validated = $request->validate([
        'vendor_id' => 'required|string|size:4',
        'product_id' => 'required|string|size:4',
        'board_type' => 'required|string|max:50',
        'description' => 'nullable|string',
        'serial_config' => 'required|array',
        'sensor_capabilities' => 'nullable|array',
        'actuator_capabilities' => 'nullable|array',
    ]);

    // Create or update board_type mapping
    BoardType::updateOrCreate(
        [
            'vendor_id' => $validated['vendor_id'],
            'product_id' => $validated['product_id'],
        ],
        $validated
    );

    // Mark device as configured
    $device = Device::where('vendor_id', $validated['vendor_id'])
                    ->where('product_id', $validated['product_id'])
                    ->first();

    if ($device) {
        $device->update([
            'board_type' => $validated['board_type'],
            'is_configured' => true,
        ]);
    }

    return response()->json(['status' => 'ok']);
}
```

### 4. Auto-Recognition beim nächsten Anstecken

Wenn ein Device mit bekanntem VID/PID angesteckt wird:

```php
public function heartbeat(Request $request)
{
    $device = auth('device')->user();
    $vendorId = $request->input('vendor_id');
    $productId = $request->input('product_id');

    // Check for known board_type
    $boardType = BoardType::where('vendor_id', $vendorId)
                          ->where('product_id', $productId)
                          ->first();

    if ($boardType) {
        // Auto-configure device
        $device->update([
            'board_type' => $boardType->board_type,
            'is_configured' => true,
            'capabilities' => [
                'sensors' => $boardType->sensor_capabilities,
                'actuators' => $boardType->actuator_capabilities,
            ],
        ]);

        logger()->info("Device auto-configured as {$boardType->board_type}");
    }

    // ... rest of heartbeat logic
}
```

## Workflow-Beispiel

### Szenario: Neues Custom-Board zum ersten Mal anschließen

1. **User steckt Device an** `/dev/ttyUSB0`
2. **Agent erkennt:** `generic_serial` (VID: `1a86`, PID: `7523`)
3. **Agent sendet Heartbeat:**
   ```json
   {
     "board_type": "generic_serial",
     "vendor_id": "1a86",
     "product_id": "7523",
     "port": "/dev/ttyUSB0"
   }
   ```
4. **Laravel prüft:** Kein Mapping in `board_types` gefunden
5. **UI zeigt:** "Unknown device detected" Banner
6. **User klickt:** "Configure Device"
7. **Wizard:** User definiert Protokoll, Sensoren, Aktoren
8. **User speichert:** Board-Profil als "my_custom_board"
9. **Laravel speichert:** Mapping in `board_types` Tabelle
10. **Device ist konfiguriert:** `is_configured = true`

### Beim nächsten Anstecken (gleiches oder anderes Device mit gleicher VID/PID):

1. **Agent sendet Heartbeat:** VID: `1a86`, PID: `7523`
2. **Laravel findet:** Mapping in `board_types` Tabelle
3. **Auto-konfiguration:** Device wird automatisch als "my_custom_board" erkannt
4. **Kein Wizard nötig:** Device ist sofort einsatzbereit

## Testing

### Test 1: Generic Serial Device Detection

```bash
# Simuliere generic serial device
python -c "from usb_device_manager import USBScanner; print(USBScanner.scan_ports())"
```

**Erwartetes Output:**

```
[USBDeviceInfo(port='/dev/ttyUSB0', vendor_id='1a86', product_id='7523',
               description='USB Serial', board_type='generic_serial')]
```

### Test 2: Handshake

```bash
python -c "from usb_device_manager import USBScanner; \
           print(USBScanner.try_handshake('/dev/ttyUSB0'))"
```

### Test 3: Full Agent mit Generic Device

```bash
# In .env setzen:
SERIAL_PORT=/dev/ttyUSB0
DEVICE_PUBLIC_ID=test-generic-001

# Agent starten
python agent.py
```

Prüfe Logs für:

```
📱 Device-Instanz erstellt: test-generic-001 auf /dev/ttyUSB0
🆕 Neues Device erkannt: /dev/ttyUSB0 → test-generic-001 (Type: generic_serial)
```

## Migration Guide für bestehende Installationen

### Schritt 1: Datenbank Migration

```bash
php artisan make:migration add_board_type_support_to_devices
php artisan make:migration create_board_types_table
php artisan migrate
```

### Schritt 2: Agent Update

```bash
cd /path/to/growdash
git pull
pip install -r requirements.txt
sudo systemctl restart growdash-agent
```

### Schritt 3: UI/Dashboard Update

- Neue Vue-Komponenten für Wizard einbinden
- Event-Listener für `UnknownDeviceDetected` registrieren

## FAQ

**Q: Was passiert wenn VID/PID fehlen (z.B. bei virtuellen Ports)?**  
A: Device wird als `generic_serial` klassifiziert mit `vendor_id=null`, `product_id=null`. User kann trotzdem manuell konfigurieren, aber Auto-Recognition funktioniert nicht.

**Q: Kann ich ein Arduino Nano als generic_serial behandeln?**  
A: Ja! Wenn die automatische Erkennung fehlschlägt oder du ein Custom-Protokoll nutzt, kannst du es manuell als generic_serial konfigurieren.

**Q: Werden Board-Profile zwischen Usern geteilt?**  
A: Aktuell nicht, aber könnte als Feature hinzugefügt werden (Board-Profile als "Public Templates").

**Q: Unterstützt das System Bluetooth Serial oder Network Serial?**  
A: Aktuell nur USB-Serial (`/dev/ttyACM*`, `/dev/ttyUSB*`, `COM*`). Support für andere Transporte kann hinzugefügt werden.

## Roadmap

- [ ] Board-Profile Import/Export (JSON)
- [ ] Community Board-Profile Library
- [ ] Automatische Protokoll-Erkennung (Pattern-Learning)
- [ ] Multi-Protocol Support (Modbus, I2C, SPI)
- [ ] Virtual Serial Device Emulator für Testing
