# Laravel Backend-Implementierung für GrowDash Agent

## 🎯 Übersicht

Der GrowDash Python-Agent unterstützt **zwei Onboarding-Modi**:

1. **Pairing-Code-Flow** (empfohlen, sicher)
2. **Direct-Login-Flow** (für automatisierte Setups)

Beide Modi erwarten unterschiedliche Laravel-Endpoints.

---

## 📋 Aktueller Status

✅ **Route existiert**: `POST /api/growdash/devices/register` (mit `auth:sanctum`)  
⚠️ **Problem**: Controller erwartet `bootstrap_id` als Pflichtfeld  
🔧 **Lösung**: Controller muss beide Flows unterstützen

---

## 🔐 Direct-Login-Flow (Aktuell genutzt)

### Python sendet:

```json
{
  "bootstrap_id": "growdash-u-server-a1b2c3d4e5f6",
  "name": "GrowDash u-server",
  "device_info": {
    "platform": "linux",
    "version": "2.0",
    "hostname": "u-server"
  }
}
```

### Laravel muss erwarten:

**Controller**: `App\Http\Controllers\Api\DeviceController@register`  
**Middleware**: `auth:sanctum` (User-Token via `Authorization: Bearer <token>`)

**Validierung**:
```php
$validated = $request->validate([
    'bootstrap_id' => 'required|string|max:255',
    'name' => 'nullable|string|max:255',
    'device_info' => 'nullable|array',
]);
```

**Logik**:
```php
public function register(Request $request)
{
    $user = $request->user(); // via Sanctum
    
    $validated = $request->validate([
        'bootstrap_id' => 'required|string|max:255',
        'name' => 'nullable|string|max:255',
        'device_info' => 'nullable|array',
    ]);
    
    // Prüfen ob Device bereits existiert (für Re-Pairing)
    $device = Device::where('bootstrap_id', $validated['bootstrap_id'])->first();
    
    if ($device) {
        // Re-Pairing: neuen Token generieren
        $agentTokenPlain = Str::random(64);
        $device->update([
            'agent_token' => hash('sha256', $agentTokenPlain),
            'status' => 'active',
            'last_seen_at' => now(),
        ]);
        
        return response()->json([
            'success' => true,
            'device_id' => $device->public_id,
            'agent_token' => $agentTokenPlain,
            'message' => 'Device re-paired successfully',
        ], 200);
    }
    
    // Neue Registrierung
    $publicId = (string) Str::uuid();
    $agentTokenPlain = Str::random(64);
    
    $device = Device::create([
        'user_id' => $user->id,
        'public_id' => $publicId,
        'bootstrap_id' => $validated['bootstrap_id'],
        'name' => $validated['name'] ?? 'GrowDash Device',
        'agent_token' => hash('sha256', $agentTokenPlain),
        'device_info' => $validated['device_info'] ?? [],
        'status' => 'active',
        'paired_at' => now(),
    ]);
    
    return response()->json([
        'success' => true,
        'device_id' => $device->public_id,
        'agent_token' => $agentTokenPlain,
        'message' => 'Device registered successfully',
    ], 201);
}
```

---

## 💓 Heartbeat-Endpoint (Critical)

**Nach erfolgreicher Registrierung MUSS der Agent regelmäßig Heartbeats senden!**

### Endpoint

**POST** `/api/growdash/agent/heartbeat`

**Authentication**: Device-Token-Headers (NICHT Sanctum!)

**Headers**:
```
X-Device-ID: <device_id from registration>
X-Device-Token: <agent_token from registration>
```

**Request Body (optional)**:
```json
{
  "last_state": {
    "uptime": 3600,
    "memory": 45000,
    "wifi_rssi": -65,
    "python_version": "3.12.0"
  }
}
```

**Response (200)**:
```json
{
  "success": true,
  "message": "Heartbeat received",
  "last_seen_at": "2025-12-02T12:34:56.000000Z"
}
```

### Controller-Implementierung

**Datei**: `app/Http/Controllers/Api/AgentController.php`

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;

class AgentController extends Controller
{
    public function heartbeat(Request $request)
    {
        // Device kommt von AuthenticateDevice Middleware
        $device = $request->device;
        
        // last_seen_at aktualisieren
        $device->update([
            'last_seen_at' => now(),
            'status' => 'online',
        ]);
        
        // Optional: last_state speichern
        if ($request->has('last_state')) {
            $device->update([
                'last_state' => $request->last_state,
            ]);
        }
        
        Log::info("Heartbeat from device {$device->public_id}");
        
        return response()->json([
            'success' => true,
            'message' => 'Heartbeat received',
            'last_seen_at' => $device->last_seen_at,
        ]);
    }
}
```

### Middleware: AuthenticateDevice

**Datei**: `app/Http/Middleware/AuthenticateDevice.php`

```php
<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use App\Models\Device;
use Symfony\Component\HttpFoundation\Response;

class AuthenticateDevice
{
    public function handle(Request $request, Closure $next): Response
    {
        $deviceId = $request->header('X-Device-ID');
        $token = $request->header('X-Device-Token');
        
        if (!$deviceId || !$token) {
            return response()->json([
                'error' => 'Missing device credentials'
            ], 401);
        }
        
        $device = Device::where('public_id', $deviceId)->first();
        
        if (!$device) {
            return response()->json([
                'error' => 'Device not found'
            ], 404);
        }
        
        // Token-Verifikation (SHA256-Hash)
        if (!hash_equals($device->agent_token, hash('sha256', $token))) {
            return response()->json([
                'error' => 'Invalid device token'
            ], 401);
        }
        
        // Device an Request anhängen
        $request->merge(['device' => $device]);
        
        return $next($request);
    }
}
```

**Registrierung in** `bootstrap/app.php`:

```php
->withMiddleware(function (Middleware $middleware) {
    $middleware->alias([
        'device.auth' => \App\Http\Middleware\AuthenticateDevice::class,
    ]);
})
```

### Status-Logik

- **paired**: Device registriert, kein Heartbeat
- **online**: Heartbeat innerhalb letzter 2 Minuten
- **offline**: Kein Heartbeat > 2 Minuten (Cron-Job)
- **error**: Device meldet Fehler

**Cron-Job** (optional, automatisches Offline-Marking):

```php
// app/Console/Commands/MarkOfflineDevices.php
Device::where('last_seen_at', '<', now()->subMinutes(2))
      ->where('status', 'online')
      ->update(['status' => 'offline']);
```

**Registrierung in** `routes/console.php`:

```php
Schedule::command('devices:mark-offline')->everyMinute();
```

---

## 🗺️ Route-Konfiguration

**Datei**: `routes/api.php`

```php
use App\Http\Controllers\Api\DeviceController;
use App\Http\Controllers\Api\AgentController;

// User-Auth Endpoints (Sanctum)
Route::middleware('auth:sanctum')->prefix('growdash')->group(function () {
    Route::post('/devices/register', [DeviceController::class, 'register']);
});

// Agent Endpoints (Device-Token-Auth)
Route::middleware('device.auth')->prefix('growdash/agent')->group(function () {
    Route::post('/heartbeat', [AgentController::class, 'heartbeat']);
    Route::post('/telemetry', [AgentController::class, 'telemetry']);
    Route::get('/commands/pending', [AgentController::class, 'pendingCommands']);
    Route::post('/commands/{id}/result', [AgentController::class, 'commandResult']);
    Route::post('/capabilities', [AgentController::class, 'updateCapabilities']);
    Route::post('/logs', [AgentController::class, 'storeLogs']);
});
```

**Verifizierung**:
```bash
php artisan route:list | grep "devices/register"
```

**Erwartete Ausgabe**:
```
POST  api/growdash/devices/register  Api\DeviceController@register  auth:sanctum
```

---

## 🗄️ Datenbank-Migration

**Datei**: `database/migrations/YYYY_MM_DD_HHMMSS_add_bootstrap_fields_to_devices.php`

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::table('devices', function (Blueprint $table) {
            if (!Schema::hasColumn('devices', 'bootstrap_id')) {
                $table->string('bootstrap_id')->nullable()->unique()->after('public_id');
            }
            if (!Schema::hasColumn('devices', 'device_info')) {
                $table->json('device_info')->nullable()->after('name');
            }
            if (!Schema::hasColumn('devices', 'last_state')) {
                $table->json('last_state')->nullable()->after('device_info');
            }
            if (!Schema::hasColumn('devices', 'paired_at')) {
                $table->timestamp('paired_at')->nullable()->after('status');
            }
        });
    }

    public function down(): void
    {
        Schema::table('devices', function (Blueprint $table) {
            $table->dropColumn(['bootstrap_id', 'device_info', 'last_state', 'paired_at']);
        });
    }
};
```

**Ausführen**:
```bash
php artisan migrate
```

---

## 🔒 Sanctum-Konfiguration

### 1. Token-Erstellung (Login-Endpoint)

**Controller**: `App\Http\Controllers\Auth\ApiAuthController`

```php
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
    
    // Token mit ability 'device:register' für kurze Lebensdauer
    $token = $user->createToken('agent-bootstrap', ['device:register'])->plainTextToken;
    
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

### 2. Token-Revoke (Logout-Endpoint)

```php
public function logout(Request $request)
{
    $request->user()->currentAccessToken()->delete();
    
    return response()->json([
        'success' => true,
        'message' => 'Logged out successfully',
    ]);
}
```

### 3. Routes

```php
Route::prefix('auth')->group(function () {
    Route::post('/login', [ApiAuthController::class, 'login']);
    Route::post('/logout', [ApiAuthController::class, 'logout'])->middleware('auth:sanctum');
});
```

---

## 📝 Device Model

**Datei**: `app/Models/Device.php`

```php
<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Device extends Model
{
    use HasFactory;

    protected $fillable = [
        'user_id',
        'public_id',
        'bootstrap_id',
        'name',
        'agent_token',
        'device_info',
        'last_state',
        'status',
        'paired_at',
        'last_seen_at',
    ];

    protected $casts = [
        'device_info' => 'array',
        'last_state' => 'array',
        'paired_at' => 'datetime',
        'last_seen_at' => 'datetime',
    ];

    protected $hidden = [
        'agent_token',
    ];

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function verifyAgentToken(string $token): bool
    {
        return hash_equals($this->agent_token, hash('sha256', $token));
    }
}
```

---

## 🧪 Testing

### 1. Login testen

```bash
curl -X POST https://grow.linn.games/api/auth/login \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{"email":"bene.linn@yahoo.de","password":"dein-passwort"}'
```

**Erwartete Antwort**:
```json
{
  "success": true,
  "token": "6|abc123xyz...",
  "user": {...}
}
```

### 2. Device registrieren

```bash
TOKEN="6|abc123xyz..."

curl -X POST https://grow.linn.games/api/growdash/devices/register \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "bootstrap_id": "growdash-u-server-a1b2c3d4e5f6",
    "name": "Test Device",
    "device_info": {
      "platform": "linux",
      "version": "2.0",
      "hostname": "u-server"
    }
  }'
```

**Erwartete Antwort (201)**:
```json
{
  "success": true,
  "device_id": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "agent_token": "7f3d9a8b...64-char-token...c2e1f4a6",
  "message": "Device registered successfully"
}
```

### 3. Logout

```bash
curl -X POST https://grow.linn.games/api/auth/logout \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/json"
```

### 4. Heartbeat senden (nach Registrierung)

```bash
DEVICE_ID="9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d"
AGENT_TOKEN="7f3d9a8b...64-char-token...c2e1f4a6"

curl -X POST https://grow.linn.games/api/growdash/agent/heartbeat \
  -H "X-Device-ID: $DEVICE_ID" \
  -H "X-Device-Token: $AGENT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "last_state": {
      "uptime": 3600,
      "memory": 45000
    }
  }'
```

**Erwartete Antwort (200)**:
```json
{
  "success": true,
  "message": "Heartbeat received",
  "last_seen_at": "2025-12-02T12:34:56.000000Z"
}
```

---

## 🔍 Troubleshooting

### Problem: 404 Not Found

**Ursache**: Route nicht definiert oder falsches Prefix  
**Lösung**: `php artisan route:list | grep devices/register` prüfen

### Problem: 401 Unauthorized

**Ursache**: Token ungültig oder abgelaufen  
**Lösung**: Neu einloggen und frisches Token verwenden

### Problem: 422 Validation Error

**Ursache**: Pflichtfeld fehlt (z.B. `bootstrap_id`)  
**Lösung**: Request-Payload prüfen, siehe Struktur oben

### Problem: 500 Internal Server Error

**Ursache**: Migration nicht ausgeführt, Spalte fehlt  
**Lösung**: 
```bash
php artisan migrate
php artisan config:clear
php artisan cache:clear
```

---

## ✅ Checkliste

### Backend-Setup
- [ ] Migration ausgeführt (`bootstrap_id`, `device_info`, `paired_at`, `last_state` in `devices`)
- [ ] `Device` Model aktualisiert (fillable, casts, hidden)
- [ ] `DeviceController@register` implementiert
- [ ] `AgentController` erstellt (heartbeat, telemetry, commands, logs)
- [ ] `AuthenticateDevice` Middleware erstellt und registriert
- [ ] `ApiAuthController` für Login/Logout implementiert
- [ ] Routes in `api.php` registriert (User-Auth + Agent-Auth)
- [ ] Sanctum konfiguriert (`config/sanctum.php`)

### Testing
- [ ] Login-Endpoint getestet (Token erhalten)
- [ ] Register-Endpoint getestet (Device erstellt)
- [ ] Logout-Endpoint getestet (Token revoked)
- [ ] Heartbeat-Endpoint getestet (Status → online)
- [ ] Device-Token-Auth funktioniert (401 bei falschem Token)

### Optional
- [ ] Cron-Job für Offline-Marking (`devices:mark-offline`)
- [ ] Telemetry-Endpoint implementiert
- [ ] Commands-Queue implementiert

---

## 🚀 Nächste Schritte

Nach erfolgreicher Implementierung:

1. Python-Agent testen:
```bash
cd ~/growdash
./setup.sh
# → Wähle "2) Direct Login"
# → Gib Email/Passwort ein
```

2. Verifiziere Device in Datenbank:
```bash
php artisan tinker
>>> Device::latest()->first();
```

3. Starte Agent:
```bash
./grow_start.sh
```

---

**Version**: 1.0  
**Letzte Aktualisierung**: 2025-12-02  
**Autor**: GrowDash Team
