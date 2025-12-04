# Backend Setup & Admin-Rechte

## 🎯 Ziel

- Laravel-Container neu bauen mit aktuellen Features
- Admin-Rechte für `bene.linn@yahoo.de` setzen
- Alle Agent-Endpoints testen

---

## 1️⃣ Container neu bauen

### Laravel-Backend

```bash
# Im Laravel-Projekt-Verzeichnis
cd ~/grow-backend  # oder wo dein Laravel-Projekt liegt

# Container stoppen
docker-compose down

# Container neu bauen (mit --no-cache für sauberen Build)
docker-compose build --no-cache

# Container starten
docker-compose up -d

# Logs prüfen
docker-compose logs -f app
```

### Migrations ausführen

```bash
# In Container einloggen
docker-compose exec app bash

# Migrations ausführen
php artisan migrate

# Cache clearen
php artisan config:clear
php artisan cache:clear
php artisan route:clear

# Routes verifizieren
php artisan route:list | grep growdash
php artisan route:list | grep auth
```

---

## 2️⃣ Admin-Rechte setzen

### Option A: Via Tinker (empfohlen)

```bash
# In Laravel-Container
docker-compose exec app php artisan tinker
```

```php
// User finden
$user = User::where('email', 'bene.linn@yahoo.de')->first();

// Admin-Rechte setzen (je nach deinem Setup)
// Variante 1: role-Spalte in users
$user->role = 'admin';
$user->save();

// Variante 2: Spatie Permission Package
$user->assignRole('admin');

// Variante 3: is_admin Spalte
$user->is_admin = true;
$user->save();

// Verifizieren
dd($user->role);  // oder $user->is_admin
```

### Option B: Via Migration

Erstelle Migration:

```bash
php artisan make:migration add_admin_role_to_users
```

**Datei**: `database/migrations/YYYY_MM_DD_HHMMSS_add_admin_role_to_users.php`

```php
<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;
use App\Models\User;

return new class extends Migration
{
    public function up(): void
    {
        // Füge role-Spalte hinzu falls nicht vorhanden
        if (!Schema::hasColumn('users', 'role')) {
            Schema::table('users', function (Blueprint $table) {
                $table->string('role')->default('user')->after('email');
            });
        }
        
        // Setze Admin für bene.linn@yahoo.de
        User::where('email', 'bene.linn@yahoo.de')->update(['role' => 'admin']);
    }

    public function down(): void
    {
        // Optional: Spalte entfernen
        Schema::table('users', function (Blueprint $table) {
            $table->dropColumn('role');
        });
    }
};
```

```bash
php artisan migrate
```

---

## 3️⃣ Backend-Code Updates

### Routes (routes/api.php)

```php
use App\Http\Controllers\Api\DeviceController;
use App\Http\Controllers\Api\AgentController;
use App\Http\Controllers\Auth\ApiAuthController;

// Auth Endpoints
Route::prefix('auth')->group(function () {
    Route::post('/login', [ApiAuthController::class, 'login']);
    Route::post('/logout', [ApiAuthController::class, 'logout'])->middleware('auth:sanctum');
});

// User-Auth Endpoints (Sanctum)
Route::middleware('auth:sanctum')->prefix('growdash')->group(function () {
    Route::post('/devices/register', [DeviceController::class, 'register']);
    
    // Admin-Only
    Route::middleware('admin')->group(function () {
        Route::get('/devices', [DeviceController::class, 'index']);
        Route::delete('/devices/{id}', [DeviceController::class, 'destroy']);
    });
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

### Admin Middleware

**Datei**: `app/Http/Middleware/EnsureUserIsAdmin.php`

```php
<?php

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

class EnsureUserIsAdmin
{
    public function handle(Request $request, Closure $next): Response
    {
        if (!$request->user() || $request->user()->role !== 'admin') {
            return response()->json([
                'error' => 'Unauthorized - Admin access required'
            ], 403);
        }
        
        return $next($request);
    }
}
```

**Registrierung in** `bootstrap/app.php`:

```php
->withMiddleware(function (Middleware $middleware) {
    $middleware->alias([
        'device.auth' => \App\Http\Middleware\AuthenticateDevice::class,
        'admin' => \App\Http\Middleware\EnsureUserIsAdmin::class,
    ]);
})
```

### Controllers erstellen/aktualisieren

#### AuthenticateDevice Middleware

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
        $request->attributes->set('device', $device);
        
        return $next($request);
    }
}
```

#### ApiAuthController

**Datei**: `app/Http/Controllers/Auth/ApiAuthController.php`

```php
<?php

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;

class ApiAuthController extends Controller
{
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
        
        // Token mit längerer Lebensdauer für Agent
        $token = $user->createToken('agent-bootstrap', ['*'], now()->addDays(7))->plainTextToken;
        
        return response()->json([
            'success' => true,
            'token' => $token,
            'user' => [
                'id' => $user->id,
                'name' => $user->name,
                'email' => $user->email,
                'role' => $user->role ?? 'user',
            ],
        ]);
    }
    
    public function logout(Request $request)
    {
        $request->user()->currentAccessToken()->delete();
        
        return response()->json([
            'success' => true,
            'message' => 'Logged out successfully',
        ]);
    }
}
```

#### DeviceController

**Datei**: `app/Http/Controllers/Api/DeviceController.php`

```php
<?php

namespace App\Http\Controllers\Api;

use App\Http\Controllers\Controller;
use App\Models\Device;
use Illuminate\Http\Request;
use Illuminate\Support\Str;

class DeviceController extends Controller
{
    public function register(Request $request)
    {
        $user = $request->user();
        
        $validated = $request->validate([
            'bootstrap_id' => 'required|string|max:255',
            'name' => 'nullable|string|max:255',
            'device_info' => 'nullable|array',
            'capabilities' => 'nullable|array',
            'revoke_user_token' => 'nullable|boolean',
        ]);
        
        // Prüfen ob Device bereits existiert (Re-Pairing)
        $device = Device::where('bootstrap_id', $validated['bootstrap_id'])->first();
        
        if ($device) {
            // Re-Pairing: neuen Token generieren
            $agentTokenPlain = Str::random(64);
            $device->update([
                'agent_token' => hash('sha256', $agentTokenPlain),
                'status' => 'paired',
                'last_seen_at' => now(),
            ]);
            
            // Optional: User-Token revoken
            if ($validated['revoke_user_token'] ?? false) {
                $request->user()->currentAccessToken()->delete();
            }
            
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
            'capabilities' => $validated['capabilities'] ?? [],
            'status' => 'paired',
            'paired_at' => now(),
        ]);
        
        // Optional: User-Token revoken
        if ($validated['revoke_user_token'] ?? false) {
            $request->user()->currentAccessToken()->delete();
        }
        
        return response()->json([
            'success' => true,
            'device_id' => $device->public_id,
            'agent_token' => $agentTokenPlain,
            'message' => 'Device registered successfully',
        ], 201);
    }
    
    public function index(Request $request)
    {
        $devices = Device::where('user_id', $request->user()->id)
                        ->orderBy('created_at', 'desc')
                        ->get();
        
        return response()->json([
            'success' => true,
            'devices' => $devices,
        ]);
    }
    
    public function destroy(Request $request, $id)
    {
        $device = Device::where('public_id', $id)
                       ->where('user_id', $request->user()->id)
                       ->firstOrFail();
        
        $device->delete();
        
        return response()->json([
            'success' => true,
            'message' => 'Device deleted successfully',
        ]);
    }
}
```

#### AgentController

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
        $device = $request->attributes->get('device');
        
        $device->update([
            'last_seen_at' => now(),
            'status' => 'online',
        ]);
        
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
    
    public function telemetry(Request $request)
    {
        $device = $request->attributes->get('device');
        
        $validated = $request->validate([
            'readings' => 'required|array',
            'readings.*.sensor_type' => 'required|string',
            'readings.*.value' => 'required',
            'readings.*.unit' => 'nullable|string',
            'readings.*.timestamp' => 'nullable|string',
        ]);
        
        // Speichere Telemetrie-Daten
        foreach ($validated['readings'] as $reading) {
            $device->telemetry()->create([
                'sensor_type' => $reading['sensor_type'],
                'value' => $reading['value'],
                'unit' => $reading['unit'] ?? null,
                'recorded_at' => $reading['timestamp'] ?? now(),
            ]);
        }
        
        return response()->json([
            'success' => true,
            'message' => 'Telemetry stored',
        ]);
    }
    
    public function pendingCommands(Request $request)
    {
        $device = $request->attributes->get('device');
        
        $commands = $device->commands()
                          ->where('status', 'pending')
                          ->orderBy('created_at', 'asc')
                          ->get();
        
        return response()->json([
            'success' => true,
            'commands' => $commands,
        ]);
    }
    
    public function commandResult(Request $request, $id)
    {
        $device = $request->attributes->get('device');
        
        $command = $device->commands()->findOrFail($id);
        
        $validated = $request->validate([
            'status' => 'required|in:completed,failed',
            'result_message' => 'nullable|string',
            'error_message' => 'nullable|string',
        ]);
        
        $command->update([
            'status' => $validated['status'],
            'result_message' => $validated['result_message'] ?? null,
            'error_message' => $validated['error_message'] ?? null,
            'executed_at' => now(),
        ]);
        
        return response()->json([
            'success' => true,
            'message' => 'Command result updated',
        ]);
    }
    
    public function updateCapabilities(Request $request)
    {
        $device = $request->attributes->get('device');
        
        $validated = $request->validate([
            'capabilities' => 'required|array',
        ]);
        
        $device->update([
            'capabilities' => $validated['capabilities'],
        ]);
        
        return response()->json([
            'success' => true,
            'message' => 'Capabilities updated',
        ]);
    }
    
    public function storeLogs(Request $request)
    {
        $device = $request->attributes->get('device');
        
        $validated = $request->validate([
            'logs' => 'required|array',
            'logs.*.level' => 'required|string',
            'logs.*.message' => 'required|string',
            'logs.*.timestamp' => 'nullable|string',
            'logs.*.context' => 'nullable|array',
        ]);
        
        foreach ($validated['logs'] as $log) {
            $device->logs()->create([
                'level' => $log['level'],
                'message' => $log['message'],
                'logged_at' => $log['timestamp'] ?? now(),
                'context' => $log['context'] ?? [],
            ]);
        }
        
        return response()->json([
            'success' => true,
            'message' => 'Logs stored',
        ]);
    }
}
```

---

## 4️⃣ Testing

### 1. Login testen

```bash
curl -X POST https://grow.linn.games/api/auth/login \
  -H "Content-Type: application/json" \
  -H "Accept: application/json" \
  -d '{
    "email": "bene.linn@yahoo.de",
    "password": "DEIN_PASSWORT"
  }'
```

**Erwartete Antwort:**
```json
{
  "success": true,
  "token": "1|abc123...",
  "user": {
    "id": 1,
    "name": "Bene",
    "email": "bene.linn@yahoo.de",
    "role": "admin"
  }
}
```

### 2. Device registrieren (via Direct-Login)

```bash
# Im Agent-Verzeichnis
cd ~/growdash
source venv/bin/activate

# Direct-Login starten
python3 -c "
from bootstrap import DirectLogin
dl = DirectLogin()
dl.run()
"

# Email: bene.linn@yahoo.de
# Passwort: ...
```

### 3. Agent starten

```bash
./grow_start.sh
```

### 4. Heartbeat verifizieren

```bash
# Logs prüfen
tail -f agent.log | grep Heartbeat

# Im Backend
docker-compose exec app php artisan tinker
>>> Device::latest()->first()->last_seen_at
```

---

## 5️⃣ Multi-Device testen

```bash
# Multi-Device aktivieren
echo "MULTI_DEVICE_MODE=true" >> .env

# Agent starten
./grow_start.sh

# Logs prüfen
tail -f agent.log | grep "Multi-Device"
```

---

## ✅ Checkliste

### Backend
- [ ] Container neu gebaut (`docker-compose build --no-cache`)
- [ ] Migrations ausgeführt (`php artisan migrate`)
- [ ] Admin-Rolle für bene.linn@yahoo.de gesetzt
- [ ] Routes verifiziert (`php artisan route:list`)
- [ ] Middleware registriert (device.auth, admin)
- [ ] Controllers erstellt (Auth, Device, Agent)

### Agent
- [ ] Direct-Login getestet
- [ ] Device erfolgreich registriert
- [ ] Heartbeat funktioniert
- [ ] Telemetry sendet Daten
- [ ] Commands werden empfangen
- [ ] Multi-Device-Modus getestet

### Admin-Panel (optional)
- [ ] Device-Liste im Frontend sichtbar
- [ ] Commands können gesendet werden
- [ ] Telemetrie-Daten werden angezeigt

---

**Nächster Schritt:** Container neu bauen und Admin-Rechte setzen!
