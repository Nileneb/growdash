# API-Endpunkte für den Datenzugriff
from fastapi import APIRouter, Query
from typing import List, Dict, Optional
from scripts.db_handler import get_db_handler

router = APIRouter(prefix="/api/data", tags=["data"])

@router.get("/water/status")
async def get_water_status():
    """Gibt den aktuellen Wasserstatus zurück."""
    db = get_db_handler()
    return db.get_system_status()

@router.get("/water/history")
async def get_water_history(limit: int = Query(100, ge=1, le=5000), days: int = Query(None)):
    """Gibt den Wasserstand-Verlauf zurück."""
    db = get_db_handler()
    return {"history": db.get_water_history(limit=limit, days=days)}

@router.get("/tds/history")
async def get_tds_history(limit: int = Query(100, ge=1, le=1000), days: int = Query(None)):
    """Gibt den TDS-Wert-Verlauf zurück."""
    db = get_db_handler()
    return {"history": db.get_tds_history(limit=limit, days=days)}

@router.get("/temperature/history")
async def get_temperature_history(limit: int = Query(100, ge=1, le=1000), days: int = Query(None)):
    """Gibt den Temperatur-Verlauf zurück."""
    db = get_db_handler()
    return {"history": db.get_temperature_history(limit=limit, days=days)}

@router.get("/events/spray")
async def get_spray_events(limit: int = Query(50, ge=1, le=500), days: int = Query(None)):
    """Gibt die Sprühnebel-Ereignisse zurück."""
    db = get_db_handler()
    return {"events": db.get_spray_events(limit=limit, days=days)}

@router.get("/events/fill")
async def get_fill_events(limit: int = Query(50, ge=1, le=500), days: int = Query(None)):
    """Gibt die Wasserzufuhr-Ereignisse zurück."""
    db = get_db_handler()
    return {"events": db.get_fill_events(limit=limit, days=days)}

@router.get("/logs")
async def get_logs(limit: int = Query(100, ge=1, le=1000), level: str = Query(None)):
    """Gibt die Systemlogs zurück."""
    db = get_db_handler()
    return {"logs": db.get_logs(limit=limit, level=level)}
