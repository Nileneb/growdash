# GrowDash v2.0 - Setup & Deployment

## 🎯 Nächste Schritte

### 1. .env Konfiguration erstellen

```bash
cd /home/nileneb/growdash
cp .env.example .env
nano .env
```

Wichtige Einstellungen anpassen:

```env
# Laravel Backend URL
LARAVEL_BASE_URL=http://192.168.178.12

# Device-Credentials vom Laravel-Backend erhalten
DEVICE_PUBLIC_ID=growdash-device-001
DEVICE_TOKEN=hier-das-token-von-laravel-eintragen

# Serial-Port prüfen
SERIAL_PORT=/dev/ttyACM0  # oder /dev/ttyUSB0
```

### 2. Serial-Port Berechtigungen

```bash
# Port finden
ls -l /dev/ttyACM* /dev/ttyUSB*

# User zu dialout-Gruppe hinzufügen
sudo usermod -a -G dialout $USER

# Neu einloggen oder:
newgrp dialout
```

### 3. Dependencies installieren

```bash
# Virtual Environment erstellen
python -m venv .venv
source .venv/bin/activate

# Packages installieren
pip install -r requirements.txt
```

### 4. Laravel-Backend vorbereiten

Das Laravel-Backend muss folgende Endpoints bereitstellen:

#### POST /api/growdash/telemetry
Empfängt Telemetrie-Batches vom Agent.

**Request:**
```json
{
  "device_id": "growdash-device-001",
  "readings": [
    {
      "timestamp": "2025-12-01T10:30:00Z",
      "sensor_id": "water_level",
      "value": 45.5,
      "unit": "percent",
      "raw": "WaterLevel: 45"
    }
  ]
}
```

#### GET /api/growdash/commands/pending
Liefert ausstehende Befehle für das Device.

**Response:**
```json
{
  "commands": [
    {
      "id": "cmd-123",
      "type": "spray_on",
      "params": {
        "duration": 5
      }
    }
  ]
}
```

#### POST /api/growdash/commands/{id}/result
Empfängt Befehlsergebnisse.

**Request:**
```json
{
  "success": true,
  "message": "Spray für 5s aktiviert",
  "timestamp": "2025-12-01T10:30:05Z"
}
```

#### Authentifizierung
Alle Requests tragen Header:
```
X-Device-ID: growdash-device-001
X-Device-Token: your-token-here
```

### 5. Agent testen

```bash
# Manuell starten für erste Tests
source .venv/bin/activate
python agent.py
```

Erwartete Ausgabe:
```
2025-12-01 10:30:00 - INFO - Agent gestartet für Device: growdash-device-001
2025-12-01 10:30:00 - INFO - Laravel Backend: http://192.168.178.12/api/growdash
2025-12-01 10:30:00 - INFO - Verbunden mit /dev/ttyACM0 @ 9600 baud
2025-12-01 10:30:00 - INFO - Agent läuft... (Strg+C zum Beenden)
```

### 6. Local Debug API testen (optional)

```bash
# In separatem Terminal
python local_api.py
```

Dann im Browser: http://127.0.0.1:8000/docs

Nützliche Endpoints:
- GET `/health` - Status prüfen
- GET `/status` - Hardware-Status
- POST `/command` - Manuellen Befehl senden
- GET `/telemetry` - Aktuelle Messwerte

### 7. Systemd Service einrichten (Production)

```bash
sudo nano /etc/systemd/system/growdash-agent.service
```

```ini
[Unit]
Description=GrowDash Hardware Agent
After=network.target

[Service]
Type=simple
User=nileneb
WorkingDirectory=/home/nileneb/growdash
Environment="PATH=/home/nileneb/growdash/.venv/bin:/usr/local/bin:/usr/bin"
ExecStart=/home/nileneb/growdash/.venv/bin/python agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
# Service aktivieren
sudo systemctl daemon-reload
sudo systemctl enable growdash-agent
sudo systemctl start growdash-agent

# Status prüfen
sudo systemctl status growdash-agent

# Logs ansehen
sudo journalctl -u growdash-agent -f
```

## 🔧 Laravel-Backend Entwicklung

### Beispiel-Controller (Laravel)

```php
<?php
// app/Http/Controllers/GrowDashController.php

namespace App\Http\Controllers;

use Illuminate\Http\Request;

class GrowDashController extends Controller
{
    // Middleware für Device-Auth
    public function __construct()
    {
        $this->middleware('device.auth');
    }
    
    // Telemetrie empfangen
    public function telemetry(Request $request)
    {
        $validated = $request->validate([
            'device_id' => 'required|string',
            'readings' => 'required|array',
            'readings.*.timestamp' => 'required|date',
            'readings.*.sensor_id' => 'required|string',
            'readings.*.value' => 'required|numeric',
            'readings.*.unit' => 'nullable|string',
        ]);
        
        foreach ($validated['readings'] as $reading) {
            Telemetry::create([
                'device_id' => $validated['device_id'],
                'sensor_id' => $reading['sensor_id'],
                'value' => $reading['value'],
                'unit' => $reading['unit'] ?? null,
                'measured_at' => $reading['timestamp'],
            ]);
        }
        
        return response()->json(['success' => true]);
    }
    
    // Befehle liefern
    public function pendingCommands(Request $request)
    {
        $deviceId = $request->header('X-Device-ID');
        
        $commands = Command::where('device_id', $deviceId)
            ->where('status', 'pending')
            ->get()
            ->map(function ($cmd) {
                return [
                    'id' => $cmd->id,
                    'type' => $cmd->type,
                    'params' => $cmd->params,
                ];
            });
        
        return response()->json(['commands' => $commands]);
    }
    
    // Befehlsergebnis empfangen
    public function commandResult(Request $request, $id)
    {
        $validated = $request->validate([
            'success' => 'required|boolean',
            'message' => 'nullable|string',
            'timestamp' => 'required|date',
        ]);
        
        $command = Command::findOrFail($id);
        $command->update([
            'status' => $validated['success'] ? 'completed' : 'failed',
            'result_message' => $validated['message'],
            'completed_at' => $validated['timestamp'],
        ]);
        
        return response()->json(['success' => true]);
    }
}
```

### Middleware für Device-Auth

```php
<?php
// app/Http/Middleware/DeviceAuth.php

namespace App\Http\Middleware;

use Closure;
use App\Models\Device;

class DeviceAuth
{
    public function handle($request, Closure $next)
    {
        $deviceId = $request->header('X-Device-ID');
        $token = $request->header('X-Device-Token');
        
        if (!$deviceId || !$token) {
            return response()->json(['error' => 'Missing device credentials'], 401);
        }
        
        $device = Device::where('public_id', $deviceId)
            ->where('token', $token)
            ->first();
        
        if (!$device) {
            return response()->json(['error' => 'Invalid device credentials'], 401);
        }
        
        $request->merge(['device' => $device]);
        
        return $next($request);
    }
}
```

### Routes (Laravel)

```php
<?php
// routes/api.php

Route::prefix('growdash')->group(function () {
    Route::post('/telemetry', [GrowDashController::class, 'telemetry']);
    Route::get('/commands/pending', [GrowDashController::class, 'pendingCommands']);
    Route::post('/commands/{id}/result', [GrowDashController::class, 'commandResult']);
    Route::post('/logs', [GrowDashController::class, 'logs']);
});
```

## 🧪 Testing

### 1. Manual Command Test

```bash
curl -X POST http://127.0.0.1:8000/command \
  -H "Content-Type: application/json" \
  -d '{
    "type": "spray_on",
    "params": {"duration": 5}
  }'
```

### 2. Telemetrie prüfen

```bash
curl http://127.0.0.1:8000/telemetry
```

### 3. Laravel-Backend testen

```bash
# Telemetrie senden
curl -X POST http://192.168.178.12/api/growdash/telemetry \
  -H "Content-Type: application/json" \
  -H "X-Device-ID: growdash-device-001" \
  -H "X-Device-Token: your-token" \
  -d '{
    "device_id": "growdash-device-001",
    "readings": [
      {
        "timestamp": "2025-12-01T10:30:00Z",
        "sensor_id": "test",
        "value": 42,
        "unit": "test"
      }
    ]
  }'

# Befehle abrufen
curl http://192.168.178.12/api/growdash/commands/pending \
  -H "X-Device-ID: growdash-device-001" \
  -H "X-Device-Token: your-token"
```

## 📊 Monitoring

### Logs ansehen

```bash
# Systemd Service
sudo journalctl -u growdash-agent -f

# Oder direkt beim Starten
python agent.py
```

### Flash-Log prüfen

```bash
cat firmware/flash_log.json | jq
```

## 🔒 Sicherheit

1. **Device-Token geheim halten** - Nicht in Git committen
2. **Local API nur im LAN** - `LOCAL_API_HOST=127.0.0.1`
3. **Firmware Whitelist** - Nur bekannte Module können geflasht werden
4. **HTTPS verwenden** - Für Production Laravel-Backend

## 📝 Changelog v2.0

### Entfernt ✂️
- ❌ Lokale SQLite-Datenbank
- ❌ Frontend-UI (HTML/JS)
- ❌ WebSocket-Server
- ❌ User-Authentication
- ❌ Komplexe Business-Logik
- ❌ Camera-Streaming (kann optional reaktiviert werden)

### Hinzugefügt ✨
- ✅ Device-Token-Auth
- ✅ Laravel HTTP-Client
- ✅ Telemetrie-Batching
- ✅ Command-Polling
- ✅ Firmware-Manager mit Whitelist
- ✅ Local Debug API
- ✅ Strukturiertes Logging
- ✅ Pydantic Settings

### Vereinfacht 🎯
- ✅ Nur noch 2 Hauptdateien (`agent.py`, `local_api.py`)
- ✅ Klare Konfiguration (`.env`)
- ✅ Einfaches Deployment
- ✅ Wartbare Architektur

## 🆘 Troubleshooting

Problem: Serial-Port nicht verfügbar
```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
sudo usermod -a -G dialout $USER
```

Problem: Laravel nicht erreichbar
```bash
ping 192.168.178.12
curl -v http://192.168.178.12/api/growdash/commands/pending
```

Problem: Dependencies fehlen
```bash
source .venv/bin/activate
pip install -r requirements.txt
```

## 📚 Weitere Dokumentation

- `README_v2.md` - Vollständige Dokumentation
- `firmware/README.md` - Firmware-Updates
- `archive_old_version/README.md` - Alte Version

---

**Status:** ✅ Umstrukturierung abgeschlossen  
**Version:** 2.0  
**Datum:** 1. Dezember 2025
