# Laravel API Endpoints für GrowDash Agent

## 🎯 Zwei Onboarding-Modi

### Modus 1: Pairing-Code-Flow (Empfohlen, Standard)

→ Agent generiert Code, User gibt ihn in Web-UI ein

### Modus 2: Direct-Login-Flow (Power-User, Dev)

→ Agent fragt nach Email+Passwort, registriert sich automatisch

---

## 🔐 Direct-Login-Flow (NEU)

### 1. User-Login (API)

**POST** `/api/auth/login`

**Request:**

```json
{
  "email": "user@example.com",
  "password": "secret123"
}
```

**Response (200):**

```json
{
  "success": true,
  "token": "1|abc123xyz...",
  "user": {
    "id": 1,
    "name": "John Doe",
    "email": "user@example.com"
  }
}
```

**Laravel-Implementierung (Sanctum):**

```php
// app/Http/Controllers/Auth/ApiAuthController.php

public function login(Request $request)
{
    $credentials = $request->validate([
        'email' => 'required|email',
        'password' => 'required',
    ]);

    if (!Auth::attempt($credentials)) {
        return response()->json([
            'success' => false,
            'message' => 'Invalid credentials'
        ], 401);
    }

    $user = Auth::user();

    // Token erstellen (wird nach Device-Registrierung revoked!)
    $token = $user->createToken('agent-bootstrap')->plainTextToken;

    return response()->json([
        'success' => true,
        'token' => $token,
        'user' => [
            'id' => $user->id,
            'name' => $user->name,
            'email' => $user->email,
        ],
    ]);
}
```

### 2. Device registrieren (mit User-Token)

**POST** `/api/growdash/devices/register`

**Headers:**

- `Authorization: Bearer 1|abc123xyz...`

**Request:**

```json
{
  "name": "GrowDash Pi Kitchen",
  "platform": "linux",
  "version": "2.0",
  "hostname": "raspberrypi"
}
```

**Response (201):**

```json
{
  "success": true,
  "device_id": "growdash-a1b2",
  "agent_token": "plaintext-device-token-hier",
  "message": "Device registered successfully"
}
```

**Laravel-Implementierung:**

```php
// app/Http/Controllers/GrowDash/DeviceController.php

public function register(Request $request)
{
    $validated = $request->validate([
        'name' => 'nullable|string|max:255',
        'platform' => 'nullable|string',
        'version' => 'nullable|string',
        'hostname' => 'nullable|string',
    ]);

    // User aus Token
    $user = auth()->user();

    // Device-ID generieren
    $publicId = 'growdash-' . Str::random(4);

    // Agent-Token generieren
    $agentToken = Str::random(64);

    // Device erstellen
    $device = Device::create([
        'user_id' => $user->id,
        'public_id' => $publicId,
        'name' => $validated['name'] ?? 'GrowDash Device',
        'agent_token' => Hash::make($agentToken), // Hash speichern!
        'device_info' => $validated,
        'status' => 'active',
    ]);

    // Klartext-Token nur im Response zurückgeben!
    return response()->json([
        'success' => true,
        'device_id' => $device->public_id,
        'agent_token' => $agentToken, // Nur hier im Klartext!
        'message' => 'Device registered successfully',
    ], 201);
}
```

### 3. User-Token revoken (nach Registrierung)

**POST** `/api/auth/logout`

**Headers:**

- `Authorization: Bearer 1|abc123xyz...`

**Response (200):**

```json
{
  "success": true,
  "message": "Logged out successfully"
}
```

**Laravel-Implementierung:**

```php
public function logout(Request $request)
{
    // Aktuellen Token revoken
    $request->user()->currentAccessToken()->delete();

    return response()->json([
        'success' => true,
        'message' => 'Logged out successfully',
    ]);
}
```

**⚠️ WICHTIG:** Agent ruft das direkt nach Device-Registrierung auf!  
Damit liegt kein User-Token auf dem Device.

---

## 🔗 Pairing-Code-Flow (Bestehend)

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

### 4. Verfügbare Serial-Ports abrufen (NEU)

**GET** `/api/growdash/agent/ports`

Headers:

- `X-Device-ID: growdash-a1b2`
- `X-Device-Token: xxx`

**Response (200):**

```json
{
  "success": true,
  "ports": [
    {
      "port": "/dev/ttyACM0",
      "description": "Arduino Uno",
      "vendor_id": "2341",
      "product_id": "0043",
      "manufacturer": "Arduino LLC",
      "serial_number": "85739313137351F06191"
    },
    {
      "port": "/dev/ttyUSB0",
      "description": "USB-Serial Controller",
      "vendor_id": "1a86",
      "product_id": "7523",
      "manufacturer": "QinHeng Electronics",
      "serial_number": null
    }
  ],
  "count": 2
}
```

**Response (503) - Agent nicht erreichbar:**

```json
{
  "error": "Device unreachable",
  "message": "Could not connect to device"
}
```

**Laravel-Implementierung:**

```php
// app/Http/Controllers/GrowDash/AgentController.php

public function getPorts(Request $request)
{
    $device = $request->attributes->get('device');

    // Agent's Local API ansprechen (wenn IP bekannt)
    if ($device->ip_address) {
        try {
            $response = Http::timeout(10)
                ->get("http://{$device->ip_address}:8000/ports");

            if ($response->successful()) {
                return response()->json($response->json());
            }

            return response()->json([
                'error' => 'Failed to fetch ports from device',
                'status' => $response->status()
            ], 502);

        } catch (\Exception $e) {
            return response()->json([
                'error' => 'Device unreachable',
                'message' => 'Could not connect to device'
            ], 503);
        }
    }

    // Fallback - Standard-Ports
    return response()->json([
        'success' => true,
        'ports' => [
            ['port' => '/dev/ttyACM0', 'description' => 'Arduino Uno (Standard)'],
            ['port' => '/dev/ttyUSB0', 'description' => 'USB-Serial (Standard)'],
        ],
        'count' => 2,
        'fallback' => true
    ]);
}
```

---

## 🗺️ Laravel Routes

```php
// routes/api.php

use App\Http\Controllers\Auth\ApiAuthController;
use App\Http\Controllers\GrowDash\PairingController;
use App\Http\Controllers\GrowDash\AgentController;
use App\Http\Controllers\GrowDash\DeviceController;

// ===== Auth Endpoints (für Direct-Login-Flow) =====
Route::prefix('auth')->group(function () {
    Route::post('/login', [ApiAuthController::class, 'login']);
    Route::post('/logout', [ApiAuthController::class, 'logout'])->middleware('auth:sanctum');
});

// ===== GrowDash Agent Endpoints =====
Route::prefix('growdash')->group(function () {

    // --- Agent Onboarding ---

    // Pairing-Code-Flow (keine Auth)
    Route::prefix('agent/pairing')->group(function () {
        Route::post('/init', [PairingController::class, 'init']);
        Route::get('/status', [PairingController::class, 'status']);
    });

    // Direct-Login-Flow (User-Auth)
    Route::middleware('auth:sanctum')->group(function () {
        Route::post('/devices/register', [DeviceController::class, 'register']);
        Route::post('/devices/pair', [DeviceController::class, 'pair']); // Web-UI
    });

    // --- Agent Runtime (Device-Token-Auth) ---

    Route::prefix('agent')->middleware('device.auth')->group(function () {
        Route::post('/telemetry', [AgentController::class, 'telemetry']);
        Route::get('/commands/pending', [AgentController::class, 'pendingCommands']);
        Route::post('/commands/{id}/result', [AgentController::class, 'commandResult']);
        Route::post('/logs', [AgentController::class, 'logs']);
        Route::get('/ports', [AgentController::class, 'getPorts']); // NEW: Port-Scan
    });
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
