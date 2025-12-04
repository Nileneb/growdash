"""
GrowDash Local Debug API










































































































































































































































































































































































































































































































**Nächster Schritt:** Laravel-Controller implementieren**Status:** ✅ Python-Agent bereit, Laravel + Frontend TODO  ---- [ ] Auto-Select erster Port- [ ] Fallback bei Fehler (Standard-Ports)- [ ] Loading-State während Scan- [ ] API-Call an `/api/growdash/agent/ports`- [ ] Port-Dropdown in Firmware-Upload-Modal### Frontend- [ ] `ip_address` Spalte in `devices` Table (optional)- [ ] Caching (30s TTL)- [ ] Error-Handling (timeout, unreachable)- [ ] HTTP-Proxy zu Agent's Local API- [ ] `AgentController@getPorts` implementieren- [ ] `/api/growdash/agent/ports` Route erstellen### Laravel-Backend- [ ] HTTPS für Local API (optional)- [ ] IP-Adresse bei Heartbeat mitsenden (optional)- [x] `/ports` Endpoint in `local_api.py`- [x] `get_available_ports()` Methode in `LaravelClient`### Python-Agent## ✅ Checkliste---```])->get("https://{$device->ip_address}:8443/ports");    'timeout' => 10    'verify' => true,$response = Http::withOptions([// Nur HTTPS erlauben```php### 3. HTTPS für Laravel-Agent-Kommunikation```    ...def get_ports():@app.get("/ports", dependencies=[Depends(verify_api_key)])        raise HTTPException(401, "Invalid API Key")    if x_api_key != os.getenv('LOCAL_API_KEY'):def verify_api_key(x_api_key: str = Header(None)):from fastapi import Header, HTTPException# local_api.py```python### 2. API-Key für Local API```sudo ufw deny 8000sudo ufw allow from 192.168.0.0/16 to any port 8000# Agent's Local API nur im LAN erlauben```bash### 1. Firewall-Regeln## ⚠️ Sicherheit---```}    "api_port": self.config.local_api_port    "ip_address": get_local_ip(),  # z.B. 192.168.1.100    "last_state": {...},payload = {# agent.py - send_heartbeat()```pythonAgent kann IP bei Heartbeat mitsenden:```});    $table->integer('api_port')->default(8000)->after('ip_address');    $table->string('ip_address')->nullable()->after('last_seen_at');Schema::table('devices', function (Blueprint $table) {```phpFalls Device IP-Adressen gespeichert werden sollen:## 📊 Database Schema (Optional)---```  -H "Accept: application/json"  -H "X-Device-Token: $DEVICE_TOKEN" \  -H "X-Device-ID: $DEVICE_ID" \curl -X GET https://grow.linn.games/api/growdash/agent/ports \DEVICE_TOKEN="7f3d9a8b..."DEVICE_ID="9b1deb4d-..."```bash### 2. Laravel-Endpoint testen```}  "count": 1  ],    }      "serial_number": "85739313137351F06191"      "manufacturer": "Arduino LLC",      "product_id": "0043",      "vendor_id": "2341",      "description": "Arduino Uno",      "port": "/dev/ttyACM0",    {  "ports": [  "success": true,{```json**Erwartete Antwort:**```curl http://localhost:8000/ports | jq# Port-Scan testenLOCAL_API_ENABLED=true python3 local_api.pysource venv/bin/activatecd ~/growdash# Agent mit Local API starten```bash### 1. Local API testen (Python-Agent)## 🧪 Testing---```</button>  </span>    <i class="fa fa-upload"></i> Firmware hochladen  <span v-else>  </span>    <i class="fa fa-spinner fa-spin"></i> Upload läuft...  <span v-if="uploading">>  class="btn btn-primary"  :disabled="!selectedPort || uploading"  @click="uploadFirmware" <button </select>  </option>    <span v-if="port.manufacturer"> ({{ port.manufacturer }})</span>    {{ port.port }} - {{ port.description }}  >    :value="port.port"    :key="port.port"    v-for="port in availablePorts"   <option   <option value="" disabled>-- Port wählen --</option><select v-model="selectedPort" class="form-select">```html### HTML Dropdown```}, [modalOpen, selectedDevice]);  }    loadAvailablePorts(selectedDevice.id);  if (modalOpen && selectedDevice) {useEffect(() => {// Beim Öffnen des Modals}  }    setLoading(false);  } finally {    showNotification('Port-Scan fehlgeschlagen. Bitte Port manuell wählen.', 'warning');        ]);      { port: '/dev/ttyUSB0', description: 'USB-Serial (Standard)' }      { port: '/dev/ttyACM0', description: 'Arduino Uno (Standard)' },    setAvailablePorts([    // Fallback: Standard-Ports anzeigen        console.error('Port-Scan fehlgeschlagen:', error);  } catch (error) {        }      setSelectedPort(data.ports[0].port);    if (data.ports.length > 0) {    // Auto-select erster Port        setAvailablePorts(data.ports);    // Ports in Dropdown füllen        const data = await response.json();        }      throw new Error(`HTTP ${response.status}`);    if (!response.ok) {        });      }        'Authorization': `Bearer ${userToken}`        'Accept': 'application/json',        'X-Device-Token': getDeviceToken(deviceId),        'X-Device-ID': deviceId,      headers: {    const response = await fetch(`/api/growdash/agent/ports`, {  try {    setLoading(true);async function loadAvailablePorts(deviceId) {```javascript### Vue/React Component (Firmware Upload Modal)## 🎨 Frontend-Integration---```}    ], 504);        'message' => 'Device did not respond in time'        'error' => 'Port scan timeout',    return response()->json([    // Timeout        }        }            ]);                'cached' => false                'count' => count($ports),                'ports' => $ports,                'success' => true,            return response()->json([        if ($ports) {        $ports = Cache::get($cacheKey);                usleep(500000); // 0.5s    for ($i = 0; $i < 10; $i++) {    // Warte kurz auf Ergebnis (Polling)        ScanDevicePorts::dispatch($device->id);    // Dispatch Job        }        ]);            'cached' => true            'count' => count($cachedPorts),            'ports' => $cachedPorts,            'success' => true,        return response()->json([    if ($cachedPorts) {        $cachedPorts = Cache::get($cacheKey);    $cacheKey = "device_ports_{$device->id}";    // Prüfe Cache (30s TTL)        $device = $request->attributes->get('device');{public function getPorts(Request $request)use Illuminate\Support\Facades\Cache;use App\Jobs\ScanDevicePorts;```php#### Option C: Queue + WebSocket (für Production)```}    }        ], 503);            'error' => 'SSH connection failed'        return response()->json([                Log::error("SSH port scan failed: {$e->getMessage()}");    } catch (\Exception $e) {                ], 500);            'error' => 'Invalid response from device'        return response()->json([                }            return response()->json($output);        if ($output && isset($output['success'])) {                $output = json_decode($result, true);                    ->execute("python3 -c '{$script}'");        $result = SSH::into($device->ssh_connection)        PYTHON;print(json.dumps({"success": True, "ports": ports, "count": len(ports)}))    })        "serial_number": port.serial_number or None        "manufacturer": port.manufacturer or None,        "product_id": f"{port.pid:04x}" if port.pid else None,        "vendor_id": f"{port.vid:04x}" if port.vid else None,        "description": port.description or "Unknown",        "port": port.device,    ports.append({for port in list_ports.comports():ports = []import serial.tools.list_ports as list_portsimport json        $script = <<<'PYTHON'        // Python-Script auf Agent ausführen    try {        }        ], 400);            'error' => 'Device SSH not configured'        return response()->json([    if (!$device->ssh_connection) {        $device = $request->attributes->get('device');{public function getPorts(Request $request)use Illuminate\Support\Facades\SSH;```php#### Option B: SSH-Command```}    }        ], 503);            'message' => 'Could not connect to device'            'error' => 'Device unreachable',        return response()->json([                Log::error("Port scan failed for device {$device->public_id}: {$e->getMessage()}");    } catch (\Exception $e) {                ], 502);            'status' => $response->status()            'error' => 'Failed to fetch ports from device',        return response()->json([                }            return response()->json($response->json());        if ($response->successful()) {                    ->get("http://{$device->ip_address}:8000/ports");            ])                'Accept' => 'application/json'            ->withHeaders([        $response = Http::timeout(10)        // HTTP-Request an Agent's Local API    try {        }        ], 400);            'error' => 'Device IP address not configured'        return response()->json([    if (!$device->ip_address) {    // Prüfe ob Device IP-Adresse hat        $device = $request->attributes->get('device');{public function getPorts(Request $request)use Illuminate\Support\Facades\Http;```php#### Option A: HTTP-Proxy an Agent's Local API### Controller (app/Http/Controllers/Api/AgentController.php)```});    // ... andere Routes    Route::get('/ports', [AgentController::class, 'getPorts']);Route::middleware('device.auth')->prefix('growdash/agent')->group(function () {```php### Route (routes/api.php)## 🏗️ Laravel-Implementierung---```}  "count": 2  ],    }      "serial_number": null      "manufacturer": "QinHeng Electronics",      "product_id": "7523",      "vendor_id": "1a86",      "description": "USB-Serial Controller",      "port": "/dev/ttyUSB0",    {    },      "serial_number": "85739313137351F06191"      "manufacturer": "Arduino LLC",      "product_id": "0043",      "vendor_id": "2341",      "description": "Arduino Uno",      "port": "/dev/ttyACM0",    {  "ports": [  "success": true,{```jsonLaravel sendet Ports-Liste zurück:### 4. Laravel → Frontend```return ports    })        "serial_number": port.serial_number        "manufacturer": port.manufacturer,        "product_id": f"{port.pid:04x}" if port.pid else None,        "vendor_id": f"{port.vid:04x}" if port.vid else None,        "description": port.description,        "port": port.device,    ports.append({for port in list_ports.comports():ports = []import serial.tools.list_ports as list_ports```pythonPython-Agent führt Port-Scan durch:### 3. Agent scannt Ports```$ports = DeviceConnection::send($device->id, 'scan_ports');// Option C: WebSocket/MQTT (für Echtzeit-Kommunikation)$ports = SSH::into($device->ssh_connection)->exec('python3 ~/growdash/get_ports.py');// Option B: SSH-Command (wenn SSH-Zugriff vorhanden)$response = Http::timeout(5)->get("http://{$device->ip_address}:8000/ports");// Option A: HTTP-Request an Agent's Local API (wenn Agent local_api.py läuft)```phpLaravel muss Request an den Python-Agent weiterleiten:### 2. Laravel → Agent (Proxy-Request)```})  }    'Accept': 'application/json'    'X-Device-Token': device.agent_token,    'X-Device-ID': device.public_id,  headers: {fetch('https://grow.linn.games/api/growdash/agent/ports', {```javascriptFrontend ruft Laravel-Endpoint auf:### 1. Frontend → Laravel## 🔄 Flow---```X-Device-Token: <agent_token>X-Device-ID: <device_id>```**Headers**:**Authentication**: Device-Token-Headers**GET** `/api/growdash/agent/ports`## 📡 Endpoint---Ermöglicht dem Frontend, verfügbare Serial-Ports eines Devices dynamisch abzurufen. Wird im Firmware-Upload-Modal verwendet, um Port-Dropdown automatisch zu befüllen.## 🎯 Zweck=========================
Optionale lokale FastAPI für manuelle Tests und Debug-Infos.
Nur auf localhost oder im LAN verfügbar - nicht für Internet gedacht!
"""

from typing import Optional, Dict, List
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import uvicorn

from agent import HardwareAgent, AgentConfig

app = FastAPI(
    title="GrowDash Local Debug API",
    version="2.0",
    description="Lokale API für Hardware-Debugging (nicht für Internet gedacht)"
)

# Globale Agent-Instanz
agent: Optional[HardwareAgent] = None


class CommandRequest(BaseModel):
    """Modell für manuelle Befehle"""
    type: str
    params: dict = {}


class TelemetryResponse(BaseModel):
    """Modell für Telemetrie-Antworten"""
    count: int
    readings: List[Dict]


@app.on_event("startup")
async def startup():
    """Agent beim Start initialisieren"""
    global agent
    config = AgentConfig()
    
    if config.local_api_enabled:
        agent = HardwareAgent()
        # Loops starten
        import threading
        threading.Thread(target=agent.telemetry_loop, daemon=True).start()
        threading.Thread(target=agent.command_loop, daemon=True).start()


@app.on_event("shutdown")
async def shutdown():
    """Agent beim Herunterfahren stoppen"""
    if agent:
        agent.stop()


@app.get("/")
def root():
    """Root-Endpoint mit API-Info"""
    return {
        "name": "GrowDash Local Debug API",
        "version": "2.0",
        "device_id": agent.config.device_public_id if agent else None,
        "status": "online" if agent else "offline"
    }


@app.get("/health")
def health_check():
    """Gesundheitscheck"""
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    return {
        "status": "ok",
        "device_id": agent.config.device_public_id,
        "laravel_backend": f"{agent.config.laravel_base_url}{agent.config.laravel_api_path}",
        "serial_port": agent.config.serial_port
    }


@app.post("/command", response_model=Dict)
def send_command(cmd: CommandRequest):
    """
    Manuellen Befehl senden (nur für Tests).
    
    Beispiele:
    - {"type": "spray_on", "params": {"duration": 5}}
    - {"type": "spray_off"}
    - {"type": "fill_start", "params": {"target_liters": 3.0}}
    - {"type": "request_status"}
    """
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    success, message = agent.execute_command(cmd.dict())
    
    return {
        "success": success,
        "message": message,
        "command": cmd.type
    }


@app.get("/telemetry", response_model=TelemetryResponse)
def get_telemetry(max_items: int = 50):
    """
    Aktuelle Telemetrie-Daten abrufen.
    
    Zeigt die letzten Messwerte aus der Queue.
    """
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    # Kurz Status anfordern
    agent.serial.send_command("Status")
    agent.serial.send_command("TDS")
    
    # Warten auf Antwort
    import time
    time.sleep(1.0)
    
    # Telemetrie abrufen (ohne aus Queue zu entfernen für Debug)
    batch = []
    temp_queue = []
    
    while not agent.serial.receive_queue.empty() and len(batch) < max_items:
        item = agent.serial.receive_queue.get()
        batch.append(item)
        temp_queue.append(item)
    
    # Items zurück in Queue (für Telemetrie-Loop)
    for item in temp_queue:
        agent.serial.receive_queue.put(item)
    
    return {
        "count": len(batch),
        "readings": batch
    }


@app.get("/status")
def get_status():
    """
    Aktuellen Hardware-Status abrufen.
    
    Fordert Status vom Arduino an und gibt Telemetrie zurück.
    """
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    # Status anfordern
    agent.serial.send_command("Status")
    agent.serial.send_command("TDS")
    
    # Kurz warten
    import time
    time.sleep(1.0)
    
    # Letzte Telemetrie
    batch = agent.serial.get_telemetry_batch(max_items=20)
    
    return {
        "requested": True,
        "telemetry": batch
    }


@app.get("/config")
def get_config():
    """Aktuelle Agent-Konfiguration anzeigen"""
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    return {
        "device_public_id": agent.config.device_public_id,
        "laravel_base_url": agent.config.laravel_base_url,
        "laravel_api_path": agent.config.laravel_api_path,
        "serial_port": agent.config.serial_port,
        "baud_rate": agent.config.baud_rate,
        "telemetry_interval": agent.config.telemetry_interval,
        "command_poll_interval": agent.config.command_poll_interval,
        "local_api_host": agent.config.local_api_host,
        "local_api_port": agent.config.local_api_port
    }


@app.post("/firmware/flash")
def flash_firmware(module_id: str):
    """
    Firmware auf Arduino flashen.
    
    Nur erlaubte Module können geflasht werden (Whitelist).
    Verfügbare Module: main, sensor, actuator
    """
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    success, message = agent.execute_command({
        "type": "firmware_update",
        "params": {"module_id": module_id}
    })
    
    if not success:
        raise HTTPException(400, message)
    
    return {
        "success": True,
        "message": message,
        "module": module_id
    }


@app.get("/firmware/log")
def get_firmware_log():
    """Flash-Log abrufen"""
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    import json
    import os
    
    log_file = os.path.join(agent.config.firmware_dir, "flash_log.json")
    
    if not os.path.exists(log_file):
        return {"logs": []}
    
    try:
        with open(log_file, 'r') as f:
            logs = json.load(f)
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(500, f"Fehler beim Lesen des Logs: {e}")


@app.get("/firmware/modules")
def get_firmware_modules():
    """Verfügbare Firmware-Module auflisten"""
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    from agent import FirmwareManager
    
    return {
        "allowed_modules": FirmwareManager.ALLOWED_MODULES,
        "firmware_dir": agent.config.firmware_dir
    }


@app.get("/ports")
def get_available_ports():
    """
    Scanne verfügbare Serial-Ports.
    Wird vom Frontend aufgerufen um Port-Dropdown zu füllen.
    
    Returns:
        {
            "success": true,
            "ports": [
                {
                    "port": "/dev/ttyACM0",
                    "description": "Arduino Uno",
                    "vendor_id": "2341",
                    "product_id": "0043",
                    "manufacturer": "Arduino",
                    "serial_number": "12345"
                },
                ...
            ]
        }
    """
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    try:
        ports = agent.laravel.get_available_ports()
        
        return {
            "success": True,
            "ports": ports,
            "count": len(ports)
        }
        
    except Exception as e:
        raise HTTPException(500, f"Fehler beim Port-Scan: {e}")


if __name__ == "__main__":
    config = AgentConfig()
    
    if config.local_api_enabled:
        print(f"Starte Local Debug API auf {config.local_api_host}:{config.local_api_port}")
        print("WARNUNG: Diese API ist nur für lokales Debugging gedacht!")
        print("Nicht im Internet verfügbar machen!")
        
        uvicorn.run(
            app,
            host=config.local_api_host,
            port=config.local_api_port
        )
    else:
        print("Local API ist deaktiviert (LOCAL_API_ENABLED=false)")
