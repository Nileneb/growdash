"""
GrowDash Local Debug API
=========================
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
