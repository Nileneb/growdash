"""
GrowDash Local API - CLEAN VERSION
===================================
Minimale Debug-API für Port-Scanning und Status-Abfragen

KEIN Agent-Start! Local API ist NUR für Debug-Zwecke.
Agent läuft separat via grow_start.sh
"""

import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# Import Port-Scanner
from agent import scan_ports

app = FastAPI(title="GrowDash Local API")

# CORS für Laravel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def root():
    """API Info"""
    return {
        "name": "GrowDash Local API",
        "version": "2.0",
        "endpoints": ["/ports"]
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


if __name__ == "__main__":
    host = os.getenv("LOCAL_API_HOST", "0.0.0.0")
    port = int(os.getenv("LOCAL_API_PORT", "8000"))
    
    print(f"🚀 Starting Local API on {host}:{port}")
    uvicorn.run(app, host=host, port=port)
