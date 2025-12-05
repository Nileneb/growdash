# 🔧 Fehlende Laravel Route: `/api/growdash/agent/ports`

## Problem

Das Frontend ruft `/api/growdash/agent/ports` auf, um verfügbare Serial-Ports zu laden.
Diese Route existiert **noch nicht** im Laravel-Backend.

## Lösung

### 1. Route hinzufügen (`routes/api.php`)

```php
Route::prefix('agent')->middleware('device.auth')->group(function () {
    Route::post('/telemetry', [AgentController::class, 'telemetry']);
    Route::get('/commands/pending', [AgentController::class, 'pendingCommands']);
    Route::post('/commands/{id}/result', [AgentController::class, 'commandResult']);
    Route::post('/logs', [AgentController::class, 'logs']);

    // NEU: Port-Scan Endpoint
    Route::get('/ports', [AgentController::class, 'getPorts']);
});
```

### 2. Controller-Methode (`app/Http/Controllers/GrowDash/AgentController.php`)

```php
public function getPorts(Request $request)
{
    /** @var Device $device */
    $device = $request->attributes->get('device');

    // Option A: Agent's Local API ansprechen (wenn IP bekannt)
    if ($device->ip_address) {
        try {
            $response = Http::timeout(10)
                ->withHeaders([
                    'Accept' => 'application/json'
                ])
                ->get("http://{$device->ip_address}:8000/ports");

            if ($response->successful()) {
                return response()->json($response->json());
            }

            return response()->json([
                'error' => 'Failed to fetch ports from device',
                'status' => $response->status()
            ], 502);

        } catch (\Exception $e) {
            Log::error("Port scan failed for device {$device->public_id}: {$e->getMessage()}");

            return response()->json([
                'error' => 'Device unreachable',
                'message' => 'Could not connect to device'
            ], 503);
        }
    }

    // Option B: Fallback - Standard-Ports zurückgeben
    return response()->json([
        'success' => true,
        'ports' => [
            [
                'port' => '/dev/ttyACM0',
                'description' => 'Arduino Uno (Standard)',
                'vendor_id' => null,
                'product_id' => null,
                'manufacturer' => null,
                'serial_number' => null,
            ],
            [
                'port' => '/dev/ttyUSB0',
                'description' => 'USB-Serial (Standard)',
                'vendor_id' => null,
                'product_id' => null,
                'manufacturer' => null,
                'serial_number' => null,
            ],
        ],
        'count' => 2,
        'fallback' => true
    ]);
}
```

### 3. Device IP-Adresse speichern (Optional)

Agent kann IP-Adresse bei Heartbeat mitsenden:

**Migration:**

```php
Schema::table('devices', function (Blueprint $table) {
    $table->string('ip_address')->nullable()->after('last_seen_at');
    $table->integer('api_port')->default(8000)->after('ip_address');
});
```

**Agent (`agent.py`):**

```python
def send_heartbeat(self, state: Dict) -> bool:
    try:
        payload = {
            "last_state": state,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ip_address": self._get_local_ip(),  # NEU
            "api_port": self.config.local_api_port  # NEU
        }
        # ...
```

**Laravel Heartbeat Controller:**

```php
public function heartbeat(Request $request)
{
    $device = $request->attributes->get('device');

    $device->update([
        'last_seen_at' => now(),
        'last_state' => $request->input('last_state'),
        'ip_address' => $request->input('ip_address'),  // NEU
        'api_port' => $request->input('api_port', 8000),  // NEU
    ]);

    return response()->json(['success' => true]);
}
```

## Testing

### 1. Agent Local API testen

```bash
# Agent starten
cd ~/growdash
source venv/bin/activate
LOCAL_API_ENABLED=true python3 local_api.py

# Port-Scan testen
curl http://localhost:8000/ports | jq
```

**Erwartete Antwort:**

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
    }
  ],
  "count": 1
}
```

### 2. Laravel-Endpoint testen

```bash
DEVICE_ID="growdash-..."
DEVICE_TOKEN="7f3d9a8b..."

curl -X GET https://grow.linn.games/api/growdash/agent/ports \
  -H "X-Device-ID: $DEVICE_ID" \
  -H "X-Device-Token: $DEVICE_TOKEN" \
  -H "Accept: application/json"
```

## Status

- ✅ **Agent:** `local_api.py` hat `/ports` Endpoint
- ✅ **Agent:** `LaravelClient.get_available_ports()` implementiert
- ❌ **Laravel:** Route `/api/growdash/agent/ports` fehlt
- ❌ **Laravel:** Controller-Methode `getPorts()` fehlt
- ❌ **Laravel:** Device `ip_address` Feld fehlt (optional)

## Nächste Schritte

1. Laravel Route hinzufügen
2. Controller-Methode implementieren
3. Optional: Device IP-Adresse speichern für Auto-Discovery
4. Frontend testen

---

**Verwandte Dokumentation:**

- `docs/LARAVEL_ENDPOINTS.md` - Alle API-Endpunkte
- `local_api.py` - Agent's Local API (Port 8000)
- `agent.py` - `LaravelClient.get_available_ports()`
