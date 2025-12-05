"""
GrowDash Local API - CLEAN VERSION
===================================
Minimale Debug-API für Port-Scanning und Status-Abfragen
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import Agent
from agent import Agent, scan_ports

app = FastAPI(title="GrowDash Local API")

# CORS für Laravel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Agent-Instanz (global)
agent = None


@app.on_event("startup")
async def startup():
    """Start Agent beim API-Start"""
    global agent
    try:
        agent = Agent()
        import threading
        threading.Thread(target=agent.run, daemon=True).start()
    except Exception as e:
        print(f"⚠️  Agent konnte nicht gestartet werden: {e}")


@app.get("/")
def root():
    """API Info"""
    return {
        "name": "GrowDash Local API",
        "version": "2.0",
        "endpoints": ["/ports", "/status", "/config"]
    }


@app.get("/ports")
def get_ports():
    """Scanne verfügbare Serial-Ports"""
    try:
        ports = scan_ports()
        return {
            "success": True,
            "ports": ports,
            "count": len(ports)
        }
    except Exception as e:
        raise HTTPException(500, f"Port-Scan fehlgeschlagen: {e}")


@app.get("/status")
def get_status():
    """Agent-Status"""
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    return {
        "status": "running",
        "device_id": agent.config.device_public_id,
        "serial_port": agent.config.serial_port,
        "laravel": agent.config.laravel_base_url
    }


@app.get("/config")
def get_config():
    """Aktuelle Config"""
    if not agent:
        raise HTTPException(503, "Agent nicht verfügbar")
    
    return {
        "device_public_id": agent.config.device_public_id,
        "laravel_base_url": agent.config.laravel_base_url,
        "serial_port": agent.config.serial_port,
        "baud_rate": agent.config.baud_rate
    }


if __name__ == "__main__":
    host = os.getenv("LOCAL_API_HOST", "0.0.0.0")
    port = int(os.getenv("LOCAL_API_PORT", "8000"))
    
    print(f"🚀 Starting Local API on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
