# Laravel Agent API - Endpoints Reference

## 🔐 Authentication

Alle Requests nutzen **Device-Token-Auth**:

```http
X-Device-ID: growdash-abc123
X-Device-Token: your-device-token
```

---

## 📡 Agent → Laravel Endpoints

### 1. Heartbeat (Device Online-Status)

**POST** `/api/growdash/agent/heartbeat`

**Frequency:** Alle 30 Sekunden

**Request:**

```json
{
  "ip_address": "192.168.1.100",
  "api_port": 8000
}
```

**Response:**

```json
{
  "success": true
}
```

**Purpose:** Hält Device-Status auf "online", aktualisiert `last_seen_at`

---

### 2. Commands abrufen

**GET** `/api/growdash/agent/commands/pending`

**Frequency:** Alle 5 Sekunden

**Response:**

```json
{
  "success": true,
  "commands": [
    {
      "id": "cmd-123",
      "type": "serial_command",
      "params": {
        "command": "Status"
      }
    },
    {
      "id": "cmd-124",
      "type": "arduino_upload",
      "params": {
        "code": "void setup() {...}",
        "board": "arduino:avr:uno",
        "port": "/dev/ttyACM0"
      }
    }
  ]
}
```

**Purpose:** Agent holt pending Commands von Laravel

---

### 3. Command-Result melden

**POST** `/api/growdash/agent/commands/{id}/result`

**Request (Success):**

```json
{
  "status": "completed",
  "result_message": "✅ Upload auf /dev/ttyACM0",
  "output": "Sketch uses 1234 bytes...",
  "error": ""
}
```

**Request (Failed):**

```json
{
  "status": "failed",
  "result_message": "❌ Compile-Fehler",
  "output": "Linking everything together...",
  "error": "error: 'LO' was not declared in this scope"
}
```

**Response:**

```json
{
  "success": true
}
```

**Purpose:** Agent meldet Ausführungs-Ergebnis zurück an Laravel

---

## 🎮 Command Types

### `serial_command` - Direkt ans Arduino

**Params:**

```json
{
  "command": "Status"
}
```

**Was passiert:**

1. Agent sendet `Status\n` an Serial-Port
2. Wartet 0.5s auf Antwort
3. Meldet Result zurück

**Use Cases:**

- Sensor-Werte abfragen
- Pumpen steuern
- Status prüfen

---

### `arduino_compile` - Code kompilieren (ohne Upload)

**Params:**

```json
{
  "code": "void setup() { pinMode(LED_BUILTIN, OUTPUT); }\nvoid loop() { digitalWrite(LED_BUILTIN, HIGH); }",
  "board": "arduino:avr:uno"
}
```

**Was passiert:**

1. Agent erstellt temp Sketch-Datei
2. Ruft `arduino-cli compile` auf
3. Meldet Compile-Output + Errors zurück
4. Löscht temp Dateien

**Use Cases:**

- Code vor Upload testen
- Syntax-Check
- LLM-basierte Fehleranalyse

---

### `arduino_upload` - Code kompilieren + uploaden

**Params:**

```json
{
  "code": "void setup() {...}",
  "board": "arduino:avr:uno",
  "port": "/dev/ttyACM0"
}
```

**Was passiert:**

1. Agent erstellt temp Sketch-Datei
2. Ruft `arduino-cli compile --upload` auf
3. Serial-Connection wird kurz geschlossen (während Upload)
4. Meldet Upload-Result + Errors zurück
5. Löscht temp Dateien

**Use Cases:**

- Firmware-Updates
- Code-Upload vom Frontend
- OTA-Updates (Over-The-Air)

---

### `scan_ports` - Verfügbare Serial-Ports scannen

**Params:**

```json
{}
```

**Was passiert:**

1. Agent scannt alle `/dev/ttyACM*` und `/dev/ttyUSB*` (Linux) bzw. `COM*` (Windows)
2. Sammelt VID/PID/Description
3. Gibt JSON-Liste zurück

**Response in `output`:**

```json
{
  "success": true,
  "ports": [
    {
      "port": "/dev/ttyACM0",
      "description": "Arduino Uno",
      "vendor_id": "2341",
      "product_id": "0043"
    }
  ],
  "count": 1
}
```

**Use Cases:**

- Port-Dropdown im Frontend befüllen
- Auto-Discovery von Devices
- Hardware-Check

---

## 📊 Data Flow

### Command Execution (Laravel → Arduino)

```
User (Frontend)
    ↓ Klick "Pump ON"

Laravel Backend
    ↓ Command.create(type: 'serial_command', params: {command: 'PUMP_ON'}, status: 'pending')

Agent (command_loop alle 5s)
    ↓ GET /commands/pending
    ↓ Findet Command cmd-123

Agent (execute_command)
    ↓ serial.send('PUMP_ON\n')

Arduino (Serial)
    ↓ digitalWrite(PUMP_PIN, HIGH)
    ↓ Serial.println("OK")

Agent
    ↓ Empfängt "OK"
    ↓ POST /commands/cmd-123/result
    ↓ {status: 'completed', output: 'OK'}

Laravel Backend
    ↓ Command status → 'completed'
    ↓ Command output → 'OK'

Frontend (WebSocket/Polling)
    ↓ Zeige ✅ "Pumpe aktiviert"
```

**WICHTIG:** Arduino antwortet NUR auf Befehle - KEINE automatische Telemetrie!

Wenn du Sensor-Werte brauchst, musst du sie aktiv abfragen:

```
Laravel: Command.create(type: 'serial_command', params: {command: 'STATUS'})
Arduino: Serial.println("Pump:ON,Water:45,Temp:22.5")
Laravel: Speichert Output in Command.output
```

---

### Arduino-CLI Workflow

```
User (Frontend)
    ↓ Upload Code
Laravel Backend
    ↓ Command.create(type: 'arduino_upload', params: {code: '...', board: 'arduino:avr:uno'})
Agent (command_loop)
    ↓ GET /commands/pending
Agent (ArduinoCLI.upload)
    ↓ Create temp sketch
    ↓ arduino-cli compile --upload
    ↓ [Serial closed during upload]
    ↓ Parse stdout/stderr
Agent
    ↓ POST /commands/{id}/result (output + error)
Laravel Backend
    ↓ Update Command (status, output, error)
Frontend
    ↓ Show Compile-Errors or Success
    ↓ [Optional] LLM analyzes error → suggest fix
```

---

## 🔧 Laravel Backend Implementation

### Required Routes

```php
// routes/api.php
Route::prefix('growdash/agent')->middleware('device.auth')->group(function () {
    Route::post('/heartbeat', [AgentController::class, 'heartbeat']);
    Route::get('/commands/pending', [AgentController::class, 'pendingCommands']);
    Route::post('/commands/{id}/result', [AgentController::class, 'commandResult']);
});
```

---

### Controller Methods

#### `heartbeat()`

```php
public function heartbeat(Request $request)
{
    $device = $request->attributes->get('device'); // from middleware

    $device->update([
        'last_seen_at' => now(),
        'ip_address' => $request->input('ip_address'),
        'api_port' => $request->input('api_port', 8000)
    ]);

    return response()->json(['success' => true]);
}
```

---

#### `pendingCommands()`

```php
public function pendingCommands(Request $request)
{
    $device = $request->attributes->get('device');

    $commands = Command::where('device_id', $device->id)
        ->where('status', 'pending')
        ->orderBy('created_at', 'asc')
        ->get(['id', 'type', 'params']);

    return response()->json([
        'success' => true,
        'commands' => $commands
    ]);
}
```

---

#### `commandResult()`

```php
public function commandResult(Request $request, $id)
{
    $device = $request->attributes->get('device');

    $command = Command::where('device_id', $device->id)
        ->findOrFail($id);

    $command->update([
        'status' => $request->input('status'), // 'completed' | 'failed'
        'result_message' => $request->input('result_message'),
        'output' => $request->input('output'),
        'error' => $request->input('error'),
        'completed_at' => now()
    ]);

    return response()->json(['success' => true]);
}
```

---

## 🗄️ Database Schema

### `devices` Table

```sql
id              BIGINT PRIMARY KEY
user_id         BIGINT (FK users)
public_id       VARCHAR(255) UNIQUE
name            VARCHAR(255)
agent_token     VARCHAR(255) -- HASHED!
ip_address      VARCHAR(45) NULLABLE
api_port        INT DEFAULT 8000
last_seen_at    TIMESTAMP NULLABLE
status          ENUM('active', 'offline')
created_at      TIMESTAMP
updated_at      TIMESTAMP
```

---

### `commands` Table

```sql
id              BIGINT PRIMARY KEY
device_id       BIGINT (FK devices)
type            VARCHAR(255) -- 'serial_command', 'arduino_upload', etc.
params          JSON
status          ENUM('pending', 'completed', 'failed')
result_message  TEXT NULLABLE
output          TEXT NULLABLE
error           TEXT NULLABLE
created_at      TIMESTAMP
completed_at    TIMESTAMP NULLABLE
```

---

## 🚀 Quick Start

### 1. Device registrieren (Laravel)

```php
$device = Device::create([
    'user_id' => auth()->id(),
    'public_id' => 'growdash-' . Str::random(4),
    'name' => 'GrowDash Pi',
    'agent_token' => Hash::make($plainToken = Str::random(64))
]);

// Gib $plainToken NUR EINMAL zurück!
return response()->json([
    'device_id' => $device->public_id,
    'token' => $plainToken // Agent trägt das in .env ein
]);
```

---

### 2. Agent konfigurieren

```bash
# .env
DEVICE_PUBLIC_ID=growdash-abc123
DEVICE_TOKEN=your-plain-token-here
LARAVEL_BASE_URL=https://grow.linn.games
SERIAL_PORT=/dev/ttyACM0
```

---

### 3. Agent starten

```bash
./setup.sh
./grow_start.sh
```

---

### 4. Command senden (Laravel)

```php
Command::create([
    'device_id' => $device->id,
    'type' => 'serial_command',
    'params' => ['command' => 'Status'],
    'status' => 'pending'
]);
```

Agent holt es automatisch (alle 5s) und führt es aus!

---

## 💡 Async Pattern (Optional - für bessere Performance)

**Problem:** Synchrones Polling = Agent wartet immer 5s zwischen Commands

**Lösung:** Async mit WebSocket oder Long-Polling

### Option A: WebSocket (empfohlen)

```php
// Laravel Backend sendet Command direkt an Agent
use App\Events\CommandCreated;

Command::create([...]);
broadcast(new CommandCreated($command));
```

```python
# Agent connected zu Laravel WebSocket
import socketio

sio = socketio.Client()
sio.connect('https://grow.linn.games')

@sio.on('command')
def on_command(data):
    result = agent.execute_command(data)
    agent.laravel.report_result(data['id'], result)
```

**Vorteil:** Instant-Ausführung, keine 5s Wartezeit!

### Option B: Long-Polling

```php
// Laravel: Blockiere Request bis Command vorhanden
public function waitForCommand(Request $request)
{
    $timeout = 30;
    $start = time();

    while (time() - $start < $timeout) {
        $cmd = Command::where('device_id', $device->id)
            ->where('status', 'pending')
            ->first();

        if ($cmd) {
            return response()->json(['command' => $cmd]);
        }

        usleep(500000); // 0.5s
    }

    return response()->json(['command' => null]);
}
```

**Vorteil:** Weniger Requests, schnellere Response

---

## 🎯 Empfohlener Workflow

### 1. Arduino Code schreiben (in Laravel)

```cpp
// User schreibt im Frontend
void setup() {
  Serial.begin(9600);
  pinMode(13, OUTPUT);
}

void loop() {
  if (Serial.available()) {
    String cmd = Serial.readStringUntil('\n');

    if (cmd == "LED_ON") {
      digitalWrite(13, HIGH);
      Serial.println("LED:ON");
    }
    else if (cmd == "LED_OFF") {
      digitalWrite(13, LOW);
      Serial.println("LED:OFF");
    }
    else if (cmd == "STATUS") {
      Serial.println("LED:" + String(digitalRead(13) ? "ON" : "OFF"));
    }
  }
}
```

### 2. Laravel kompiliert + uploaded Code

```php
Command::create([
    'device_id' => $device->id,
    'type' => 'arduino_upload',
    'params' => [
        'code' => $arduinoCode,
        'board' => 'arduino:avr:uno',
        'port' => '/dev/ttyACM0'
    ]
]);
```

### 3. Agent führt Upload aus

```
Agent → Arduino-CLI → Arduino
Result: "✅ Upload erfolgreich"
```

### 4. User sendet Commands

```php
// Frontend: "LED an"
Command::create([
    'type' => 'serial_command',
    'params' => ['command' => 'LED_ON']
]);

// Agent führt aus
// Arduino antwortet: "LED:ON"
// Laravel speichert in Command.output
```

### 5. Frontend pollt/websocket für Result

```javascript
// Polling
setInterval(() => {
  fetch(`/api/commands/${commandId}`)
    .then((r) => r.json())
    .then((data) => {
      if (data.status === "completed") {
        showNotification("LED aktiviert: " + data.output);
      }
    });
}, 1000);

// Oder WebSocket
Echo.channel("device." + deviceId).listen("CommandCompleted", (e) => {
  showNotification("✅ " + e.output);
});
```

---

## 📝 Logs

Agent loggt nach **stdout**:

```
2025-12-05 10:30:00 - INFO - 🚀 Agent gestartet: growdash-abc123
2025-12-05 10:30:00 - INFO - 📡 Laravel: https://grow.linn.games
2025-12-05 10:30:00 - INFO - 🔌 Serial: /dev/ttyACM0
2025-12-05 10:30:00 - INFO - ✅ Serial verbunden: /dev/ttyACM0
2025-12-05 10:30:00 - INFO - ✅ Agent läuft...
```

**In Production:**

```bash
python agent.py 2>&1 | tee -a agent.log
```

Oder systemd Service:

```ini
[Service]
ExecStart=/home/pi/growdash/venv/bin/python /home/pi/growdash/agent.py
StandardOutput=journal
StandardError=journal
```

Dann:

```bash
sudo journalctl -u growdash-agent -f
```

---

**SIMPLE. CLEAN. NO BULLSHIT.**
