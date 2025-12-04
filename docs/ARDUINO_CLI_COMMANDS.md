# Arduino-CLI Command Integration

## 🎯 Übersicht

Der GrowDash Agent unterstützt jetzt **Arduino-CLI Commands** vom Laravel-Backend. Diese Commands ermöglichen dynamisches Kompilieren und Uploaden von Arduino-Sketches über die Web-UI.

---

## 📋 Unterstützte Command-Types

### 1. `arduino_compile`

Kompiliert Arduino-Code **ohne** Upload. Nützlich für Syntax-Checks.

**Params:**
```json
{
  "code": "void setup() { Serial.begin(9600); } void loop() { }",
  "board": "arduino:avr:uno",
  "sketch_name": "my_sketch"  // optional
}
```

**Agent-Verarbeitung:**
1. Erstellt temporäres Sketch-Verzeichnis
2. Schreibt Code in `.ino` Datei
3. Führt `arduino-cli compile` aus
4. Returned Compile-Output
5. Cleanup (temp files löschen)

**Erwartetes Result:**
```json
{
  "status": "completed",
  "result_message": "Sketch erfolgreich kompiliert\n[arduino-cli output]"
}
```

---

### 2. `arduino_upload`

Uploaded bereits kompilierte `.hex` Datei zum Arduino.

**Params:**
```json
{
  "hex_file": "/tmp/compiled_sketch.hex",
  "board": "arduino:avr:uno",
  "port": "/dev/ttyACM0"  // optional, nutzt config wenn nicht angegeben
}
```

**Agent-Verarbeitung:**
1. Prüft ob HEX-Datei existiert
2. Schließt Serial-Verbindung
3. Führt `arduino-cli upload` aus
4. Stellt Serial-Verbindung wieder her

**Erwartetes Result:**
```json
{
  "status": "completed",
  "result_message": "Firmware erfolgreich auf /dev/ttyACM0 uploaded\n[output]"
}
```

---

### 3. `arduino_compile_upload` ⭐ (Meistgenutzt)

Kompiliert **UND** uploaded Arduino-Code in einem Schritt.

**Params:**
```json
{
  "code": "void setup() { pinMode(13, OUTPUT); } void loop() { digitalWrite(13, HIGH); delay(1000); digitalWrite(13, LOW); delay(1000); }",
  "board": "arduino:avr:uno",
  "port": "/dev/ttyACM0",  // optional
  "sketch_name": "blink"   // optional
}
```

**Agent-Verarbeitung:**
1. Erstellt temp Sketch-Verzeichnis
2. Schreibt Code in `.ino` Datei
3. Schließt Serial-Verbindung
4. Kompiliert Sketch
5. Uploaded zum Arduino
6. Loggt Flash-Event in `firmware/flash_log.json`
7. Stellt Serial-Verbindung wieder her
8. Cleanup

**Erwartetes Result:**
```json
{
  "status": "completed",
  "result_message": "Sketch erfolgreich kompiliert und auf /dev/ttyACM0 uploaded\n[output]"
}
```

---

## 🏗️ Laravel Backend Integration

### Command erstellen (ArduinoCompileController)

```php
use App\Models\Command;

// Compile + Upload
$command = Command::create([
    'device_id' => $device->id,
    'type' => 'arduino_compile_upload',
    'params' => [
        'code' => $request->code,
        'board' => $request->board ?? 'arduino:avr:uno',
        'port' => $request->port ?? '/dev/ttyACM0',
        'sketch_name' => $request->sketch_name ?? 'custom_sketch'
    ],
    'status' => 'pending'
]);
```

### Agent holt Command ab

Agent pollt `/api/growdash/agent/commands/pending` alle 5s und findet:

```json
{
  "id": 123,
  "type": "arduino_compile_upload",
  "params": {
    "code": "void setup() { ... }",
    "board": "arduino:avr:uno",
    "port": "/dev/ttyACM0"
  },
  "status": "pending"
}
```

### Agent führt aus

```python
# agent.py - execute_command()
if cmd_type == "arduino_compile_upload":
    code = params.get("code", "")
    board = params.get("board", "arduino:avr:uno")
    port = params.get("port", self.config.serial_port)
    
    # Temp sketch erstellen
    sketch_file = create_temp_sketch(code)
    
    # Serial schließen
    self.serial.close()
    
    # Compile + Upload
    success, message = self.firmware_mgr.compile_and_upload(
        sketch_file,
        board,
        port
    )
    
    # Serial wiederherstellen
    self.serial = SerialProtocol(...)
    
    return success, message
```

### Agent meldet Ergebnis

POST `/api/growdash/agent/commands/123/result`:

```json
{
  "status": "completed",
  "result_message": "Sketch erfolgreich kompiliert und auf /dev/ttyACM0 uploaded\navrdude: verifying ...\navrdude done."
}
```

---

## 🔧 Unterstützte Boards

### Arduino

- `arduino:avr:uno` - Arduino Uno (Standard)
- `arduino:avr:mega` - Arduino Mega 2560
- `arduino:avr:nano` - Arduino Nano
- `arduino:avr:leonardo` - Arduino Leonardo

### ESP

- `esp32:esp32:esp32` - ESP32 Dev Module
- `esp8266:esp8266:nodemcuv2` - NodeMCU 1.0 (ESP-12E)

### Andere

- `adafruit:samd:adafruit_feather_m0` - Adafruit Feather M0

**Hinweis:** Boards müssen via `arduino-cli core install` installiert sein!

```bash
arduino-cli core install arduino:avr
arduino-cli core install esp32:esp32
arduino-cli core install esp8266:esp8266
```

---

## 🧪 Testing

### 1. Lokaler Test (ohne Laravel)

```bash
cd ~/growdash
source venv/bin/activate

# Test compile_and_upload
python3 -c "
from agent import FirmwareManager, AgentConfig

config = AgentConfig()
mgr = FirmwareManager(config)

# Einfacher Blink-Sketch
code = '''
void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
}

void loop() {
  digitalWrite(LED_BUILTIN, HIGH);
  delay(1000);
  digitalWrite(LED_BUILTIN, LOW);
  delay(1000);
}
'''

# Temp file erstellen
import tempfile
from pathlib import Path

sketch_dir = Path(tempfile.mkdtemp())
sketch_file = sketch_dir / 'blink.ino'
sketch_file.write_text(code)

# Compile + Upload
success, msg = mgr.compile_and_upload(
    str(sketch_file),
    'arduino:avr:uno',
    '/dev/ttyACM0'
)

print(f'Success: {success}')
print(f'Message: {msg}')

# Cleanup
import shutil
shutil.rmtree(sketch_dir)
"
```

### 2. Via Laravel Command

```bash
# Im Laravel-Container
php artisan tinker
```

```php
$device = App\Models\Device::first();

$command = App\Models\Command::create([
    'device_id' => $device->id,
    'type' => 'arduino_compile_upload',
    'params' => [
        'code' => "void setup() { pinMode(13, OUTPUT); } void loop() { digitalWrite(13, HIGH); delay(1000); digitalWrite(13, LOW); delay(1000); }",
        'board' => 'arduino:avr:uno',
        'port' => '/dev/ttyACM0'
    ],
    'status' => 'pending'
]);

echo "Command ID: {$command->id}\n";

// Warte 30s, dann prüfe Status
sleep(30);

$command->refresh();
echo "Status: {$command->status}\n";
echo "Result: {$command->result_message}\n";
```

### 3. Via Frontend (Web-UI)

1. **Device auswählen** in der Device-Liste
2. **"Arduino Upload" Modal öffnen**
3. **Code eingeben:**
   ```cpp
   void setup() {
     Serial.begin(9600);
     pinMode(13, OUTPUT);
   }
   
   void loop() {
     digitalWrite(13, HIGH);
     Serial.println("LED ON");
     delay(1000);
     digitalWrite(13, LOW);
     Serial.println("LED OFF");
     delay(1000);
   }
   ```
4. **Board wählen:** Arduino Uno
5. **Port wählen:** /dev/ttyACM0 (auto-detected via Port-Scanner)
6. **"Compile & Upload" klicken**
7. **Warte auf Result** (wird via WebSocket/Polling aktualisiert)

---

## 📊 Flash-Event Logging

Alle Firmware-Uploads werden in `firmware/flash_log.json` geloggt:

```json
[
  {
    "timestamp": "2025-12-04T10:30:15.123456Z",
    "module": "/tmp/arduino_sketch_xyz/blink.ino",
    "port": "/dev/ttyACM0",
    "success": true,
    "error": ""
  },
  {
    "timestamp": "2025-12-04T10:35:20.987654Z",
    "module": "/tmp/arduino_sketch_abc/sensor.ino",
    "port": "/dev/ttyACM0",
    "success": false,
    "error": "Kompilierung fehlgeschlagen: expected ';' before '}'"
  }
]
```

**Abrufen:**
```bash
cat firmware/flash_log.json | jq '.[-5:]'  # Letzte 5 Events
```

---

## ⚠️ Wichtige Hinweise

### 1. Serial-Verbindung wird unterbrochen

Während Compile+Upload wird die Serial-Verbindung **geschlossen** und danach **wiederhergestellt**. Das bedeutet:

- **Telemetrie** pausiert für ~10-30s
- **Commands** werden nicht empfangen während Upload
- **Heartbeat** wird nicht gesendet während Upload

→ Frontend sollte Loading-State anzeigen!

### 2. Timeouts

- **Compile:** 120s timeout
- **Upload:** 60s timeout
- **Gesamt (Compile+Upload):** ~180s max

→ Lange Sketches können timeout!

### 3. Fehlerbehandlung

Mögliche Fehler:

- **Syntax Error:** `expected ';' before '}' token`
- **Board nicht installiert:** `Error during build: Platform 'esp32:esp32' not found`
- **Port nicht verfügbar:** `can't open device "/dev/ttyACM0": Permission denied`
- **Upload failed:** `avrdude: stk500_recv(): programmer is not responding`

→ Agent meldet Details in `result_message` zurück!

### 4. Sicherheit

⚠️ **WICHTIG:** Arduino-Code wird **ungeprüft kompiliert und uploaded**!

**Gefahren:**
- Malicious Code könnte Hardware beschädigen
- Infinite Loops könnten Arduino blockieren
- Falsche Pin-Konfiguration könnte Kurzschluss verursachen

**Empfohlene Maßnahmen:**
- **Admin-Only:** Nur Admins dürfen Arduino-Code uploaden
- **Code-Review:** Optional Code-Review-Flow vor Upload
- **Sandbox:** Test-Upload auf separatem Device
- **Backup:** Immer funktionierende Firmware als Backup behalten

---

## 📚 Siehe auch

- **[PORT_SCANNER_API.md](PORT_SCANNER_API.md)** - Automatische Port-Erkennung
- **[FIRMWARE_MANAGER.md](FIRMWARE_MANAGER.md)** - Firmware-Update-System
- **[BACKEND_SETUP.md](BACKEND_SETUP.md)** - Laravel Backend Setup

---

**Status:** ✅ Implementiert und getestet  
**Letzte Aktualisierung:** 4. Dezember 2025
