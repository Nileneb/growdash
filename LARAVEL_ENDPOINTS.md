# Laravel API Endpoints für GrowDash Agent

## 🔗 Pairing Endpoints

### 1. Pairing initiieren

**POST** `/api/growdash/agent/pairing/init`

Erstellt einen neuen Pairing-Request.

**Request:**
```json
{
  "device_id": "growdash-a1b2",
  "pairing_code": "123456",
  "device_info": {
    "platform": "raspberry-pi",
    "version": "2.0"
  }
}
```

**Response (201):**
```json
{
  "success": true,
  "message": "Pairing initiiert",
  "device_id": "growdash-a1b2",
  "expires_at": "2025-12-01T22:10:00Z"
}
```

**Laravel-Implementierung:**
```php
// app/Http/Controllers/GrowDash/PairingController.php

public function init(Request $request)
{
    $validated = $request->validate([
        'device_id' => 'required|string|unique:devices,public_id',
        'pairing_code' => 'required|string|size:6',
        'device_info' => 'nullable|array',
    ]);
    
    // Pairing-Request erstellen (läuft nach 5 Minuten ab)
    $pairing = DevicePairing::create([
        'device_id' => $validated['device_id'],
        'pairing_code' => $validated['pairing_code'],
        'device_info' => $validated['device_info'] ?? null,
        'status' => 'pending',
        'expires_at' => now()->addMinutes(5),
    ]);
    
    return response()->json([
        'success' => true,
        'message' => 'Pairing initiiert',
        'device_id' => $pairing->device_id,
        'expires_at' => $pairing->expires_at,
    ], 201);
}
```

### 2. Pairing-Status abfragen

**GET** `/api/growdash/agent/pairing/status`

Query-Parameter:
- `device_id` (required)
- `pairing_code` (required)

**Response (200) - Pending:**
```json
{
  "status": "pending",
  "device_id": "growdash-a1b2"
}
```

**Response (200) - Paired:**
```json
{
  "status": "paired",
  "device_id": "growdash-a1b2",
  "agent_token": "klartext-token-hier",
  "user_email": "user@example.com"
}
```

**Response (200) - Expired/Rejected:**
```json
{
  "status": "expired"
}
```

**Laravel-Implementierung:**
```php
public function status(Request $request)
{
    $validated = $request->validate([
        'device_id' => 'required|string',
        'pairing_code' => 'required|string',
    ]);
    
    $pairing = DevicePairing::where('device_id', $validated['device_id'])
        ->where('pairing_code', $validated['pairing_code'])
        ->first();
    
    if (!$pairing) {
        return response()->json(['status' => 'not_found'], 404);
    }
    
    // Abgelaufen?
    if ($pairing->expires_at < now()) {
        $pairing->update(['status' => 'expired']);
        return response()->json(['status' => 'expired']);
    }
    
    // Status zurückgeben
    $response = [
        'status' => $pairing->status,
        'device_id' => $pairing->device_id,
    ];
    
    // Wenn gepairt, Token zurückgeben
    if ($pairing->status === 'paired' && $pairing->device) {
        // WICHTIG: Nur einmalig den Klartext-Token zurückgeben!
        // Danach nur noch Hash in DB speichern
        $response['agent_token'] = $pairing->plaintext_token;
        $response['user_email'] = $pairing->device->user->email ?? null;
    }
    
    return response()->json($response);
}
```

### 3. Pairing bestätigen (Web-UI)

**POST** `/api/growdash/devices/pair` (Auth required)

Wird vom eingeloggten User in der Web-UI aufgerufen.

**Request:**
```json
{
  "pairing_code": "123456"
}
```

**Response (200):**
```json
{
  "success": true,
  "device_id": "growdash-a1b2",
  "device_name": "GrowDash Pi"
}
```

**Laravel-Implementierung:**
```php
// app/Http/Controllers/DeviceController.php

public function pair(Request $request)
{
    $validated = $request->validate([
        'pairing_code' => 'required|string|size:6',
    ]);
    
    $pairing = DevicePairing::where('pairing_code', $validated['pairing_code'])
        ->where('status', 'pending')
        ->where('expires_at', '>', now())
        ->firstOrFail();
    
    // Token generieren
    $token = Str::random(64);
    
    // Device erstellen
    $device = Device::create([
        'user_id' => auth()->id(),
        'public_id' => $pairing->device_id,
        'agent_token' => Hash::make($token), // Hash speichern!
        'device_info' => $pairing->device_info,
        'status' => 'active',
    ]);
    
    // Pairing aktualisieren
    $pairing->update([
        'status' => 'paired',
        'device_id' => $device->id,
        'plaintext_token' => $token, // Nur temporär für Polling!
    ]);
    
    return response()->json([
        'success' => true,
        'device_id' => $device->public_id,
        'device_name' => $device->name ?? 'GrowDash Pi',
    ]);
}
```

---

## 🔒 Agent Endpoints (Auth via Device-Token)

### Middleware: Device-Auth

```php
// app/Http/Middleware/DeviceAuth.php

namespace App\Http\Middleware;

use Closure;
use App\Models\Device;
use Illuminate\Support\Facades\Hash;

class DeviceAuth
{
    public function handle($request, Closure $next)
    {
        $deviceId = $request->header('X-Device-ID');
        $token = $request->header('X-Device-Token');
        
        if (!$deviceId || !$token) {
            return response()->json(['error' => 'Missing credentials'], 401);
        }
        
        $device = Device::where('public_id', $deviceId)->first();
        
        if (!$device || !Hash::check($token, $device->agent_token)) {
            return response()->json(['error' => 'Invalid credentials'], 401);
        }
        
        // Device an Request anhängen
        $request->merge(['device' => $device]);
        
        return $next($request);
    }
}
```

### 1. Telemetrie senden

**POST** `/api/growdash/agent/telemetry`

Headers:
- `X-Device-ID: growdash-a1b2`
- `X-Device-Token: xxx`

**Request:**
```json
{
  "device_id": "growdash-a1b2",
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

### 2. Befehle abrufen

**GET** `/api/growdash/agent/commands/pending`

Headers:
- `X-Device-ID: growdash-a1b2`
- `X-Device-Token: xxx`

**Response:**
```json
{
  "success": true,
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

### 3. Befehlsergebnis melden

**POST** `/api/growdash/agent/commands/{id}/result`

Headers:
- `X-Device-ID: growdash-a1b2`
- `X-Device-Token: xxx`

**Request:**
```json
{
  "success": true,
  "message": "Spray für 5s aktiviert",
  "timestamp": "2025-12-01T10:30:05Z"
}
```

---

## 🗺️ Laravel Routes

```php
// routes/api.php

use App\Http\Controllers\GrowDash\PairingController;
use App\Http\Controllers\GrowDash\AgentController;

Route::prefix('growdash/agent')->group(function () {
    
    // Pairing (keine Auth)
    Route::post('/pairing/init', [PairingController::class, 'init']);
    Route::get('/pairing/status', [PairingController::class, 'status']);
    
    // Agent Endpoints (Device-Token-Auth)
    Route::middleware('device.auth')->group(function () {
        Route::post('/telemetry', [AgentController::class, 'telemetry']);
        Route::get('/commands/pending', [AgentController::class, 'pendingCommands']);
        Route::post('/commands/{id}/result', [AgentController::class, 'commandResult']);
        Route::post('/logs', [AgentController::class, 'logs']);
    });
});

// Web-UI Pairing (User-Auth)
Route::middleware('auth:sanctum')->group(function () {
    Route::post('/growdash/devices/pair', [DeviceController::class, 'pair']);
});
```

---

## 📊 Datenbank-Migrations

```php
// Migration: device_pairings

Schema::create('device_pairings', function (Blueprint $table) {
    $table->id();
    $table->string('device_id')->unique();
    $table->string('pairing_code', 6);
    $table->json('device_info')->nullable();
    $table->enum('status', ['pending', 'paired', 'expired', 'rejected'])->default('pending');
    $table->foreignId('device_id')->nullable()->constrained()->onDelete('cascade');
    $table->string('plaintext_token')->nullable(); // Nur temporär!
    $table->timestamp('expires_at');
    $table->timestamps();
    
    $table->index(['pairing_code', 'status']);
});

// Migration: devices

Schema::create('devices', function (Blueprint $table) {
    $table->id();
    $table->foreignId('user_id')->constrained()->onDelete('cascade');
    $table->string('public_id')->unique();
    $table->string('name')->nullable();
    $table->string('agent_token'); // Hashed!
    $table->json('device_info')->nullable();
    $table->enum('status', ['active', 'inactive', 'disabled'])->default('active');
    $table->timestamp('last_seen_at')->nullable();
    $table->timestamps();
    
    $table->index('public_id');
});
```

---

## ✅ Sicherheits-Checklist

- [ ] Pairing-Codes laufen nach 5 Minuten ab
- [ ] Klartext-Token nur einmalig beim Polling zurückgeben
- [ ] Token in DB nur als Hash speichern
- [ ] Device-Auth-Middleware für alle Agent-Endpoints
- [ ] Rate-Limiting für Pairing-Endpoints
- [ ] HTTPS in Production!
