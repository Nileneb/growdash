"""
GrowDash Local API - Unified Version
=====================================
Kombiniert alle lokalen Endpunkte:
- Port-Scanning (Serial Devices)
- Kamera-Erkennung und On-Demand Streaming
- Log-Abruf (Pull statt Push)
- Device-Status und Registry

Auth: Bearer Token (Sanctum) oder X-Device-Token Header
"""

import os
import time
import threading
import logging
from pathlib import Path
from typing import Dict, List, Optional
from collections import deque
from urllib.parse import quote_plus

import cv2
import uvicorn
from fastapi import FastAPI, HTTPException, Header, Depends, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic_settings import BaseSettings
from pydantic import Field

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


# =============================================================================
# Configuration
# =============================================================================

class LocalAPIConfig(BaseSettings):
    """Konfiguration für die lokale API"""
    
    # Server
    host: str = Field(default="0.0.0.0", alias="LOCAL_API_HOST")
    port: int = Field(default=8000, alias="LOCAL_API_PORT")
    
    # Auth
    device_public_id: str = Field(default="")
    device_token: str = Field(default="")
    
    # Optionale zusätzliche API-Keys für externen Zugriff
    api_keys: str = Field(default="", description="Komma-getrennte Liste erlaubter API-Keys")
    
    # Camera Settings
    camera_frame_width: int = Field(default=640)
    camera_frame_height: int = Field(default=480)
    camera_fps: int = Field(default=15)
    camera_jpeg_quality: int = Field(default=80)
    camera_idle_timeout: int = Field(default=60, description="Sekunden ohne Clients bis Stream geschlossen wird")
    
    # Board Registry
    board_registry_path: str = Field(default="./boards.json")
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


# =============================================================================
# Auth Dependencies
# =============================================================================

def get_config() -> LocalAPIConfig:
    return LocalAPIConfig()


def verify_auth(
    x_device_token: Optional[str] = Header(None, alias="X-Device-Token"),
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None, alias="api_key"),
    config: LocalAPIConfig = Depends(get_config)
) -> bool:
    """
    Verifiziert Authentifizierung über:
    1. X-Device-Token Header (Agent-Auth)
    2. Authorization: Bearer <token> (Sanctum)
    3. api_key Query-Parameter (für einfache Tests)
    
    Für lokale Entwicklung: Wenn kein Token konfiguriert, alles erlauben.
    """
    # Wenn kein Device-Token konfiguriert, lokalen Zugriff erlauben
    if not config.device_token:
        return True
    
    # X-Device-Token prüfen
    if x_device_token and x_device_token == config.device_token:
        return True
    
    # Bearer Token prüfen (Sanctum)
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]
        # Hier könnte man gegen Laravel validieren, aber für lokale API
        # akzeptieren wir auch den device_token als Bearer
        if token == config.device_token:
            return True
    
    # API-Key prüfen
    if api_key:
        allowed_keys = [k.strip() for k in config.api_keys.split(",") if k.strip()]
        if api_key in allowed_keys or api_key == config.device_token:
            return True
    
    raise HTTPException(status_code=401, detail="Unauthorized")


# =============================================================================
# Camera Stream Manager (On-Demand)
# =============================================================================

class OnDemandStreamManager:
    """
    Verwaltet Video-Streams die nur bei Bedarf geöffnet werden.
    Schließt Streams automatisch nach Inaktivität.
    """
    
    def __init__(self, config: LocalAPIConfig):
        self.config = config
        self._streams: Dict[str, cv2.VideoCapture] = {}
        self._locks: Dict[str, threading.Lock] = {}
        self._last_access: Dict[str, float] = {}
        self._client_count: Dict[str, int] = {}
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_cleanup = threading.Event()
    
    def start_cleanup_thread(self):
        """Startet den Hintergrund-Thread für Stream-Cleanup."""
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            return
        self._stop_cleanup.clear()
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _cleanup_loop(self):
        """Schließt inaktive Streams nach Timeout."""
        while not self._stop_cleanup.is_set():
            time.sleep(10)
            now = time.time()
            to_close = []
            
            for device, last_access in list(self._last_access.items()):
                clients = self._client_count.get(device, 0)
                age = now - last_access
                
                if clients == 0 and age > self.config.camera_idle_timeout:
                    to_close.append(device)
            
            for device in to_close:
                self._close_stream(device)
                logger.info(f"Stream {device} wegen Inaktivität geschlossen")
    
    def _open_stream(self, device: str) -> Optional[cv2.VideoCapture]:
        """Öffnet einen Stream (intern)."""
        try:
            cap = cv2.VideoCapture(device)
            if not cap.isOpened():
                logger.error(f"Konnte Kamera nicht öffnen: {device}")
                return None
            
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.config.camera_frame_width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.config.camera_frame_height)
            cap.set(cv2.CAP_PROP_FPS, self.config.camera_fps)
            
            self._streams[device] = cap
            self._locks[device] = threading.Lock()
            self._client_count[device] = 0
            logger.info(f"Stream geöffnet: {device}")
            return cap
        except Exception as exc:
            logger.error(f"Fehler beim Öffnen von {device}: {exc}")
            return None
    
    def _close_stream(self, device: str):
        """Schließt einen Stream (intern)."""
        if device in self._streams:
            try:
                self._streams[device].release()
            except Exception:
                pass
            del self._streams[device]
            self._locks.pop(device, None)
            self._last_access.pop(device, None)
            self._client_count.pop(device, None)
    
    def get_stream(self, device: str) -> Optional[cv2.VideoCapture]:
        """Holt oder öffnet einen Stream."""
        if device not in self._streams:
            cap = self._open_stream(device)
            if not cap:
                return None
        
        self._last_access[device] = time.time()
        return self._streams.get(device)
    
    def register_client(self, device: str):
        """Registriert einen neuen Client für einen Stream."""
        self._client_count[device] = self._client_count.get(device, 0) + 1
        self._last_access[device] = time.time()
    
    def unregister_client(self, device: str):
        """Entfernt einen Client von einem Stream."""
        if device in self._client_count:
            self._client_count[device] = max(0, self._client_count[device] - 1)
    
    def generate_mjpeg(self, device: str):
        """Generator für MJPEG-Frames."""
        cap = self.get_stream(device)
        if not cap:
            yield b''
            return
        
        self.register_client(device)
        lock = self._locks.get(device)
        
        try:
            while True:
                try:
                    with lock:
                        success, frame = cap.read()
                        if not success:
                            time.sleep(0.1)
                            continue
                        
                        ret, buffer = cv2.imencode(
                            '.jpg', frame, 
                            [cv2.IMWRITE_JPEG_QUALITY, self.config.camera_jpeg_quality]
                        )
                        if not ret:
                            continue
                        
                        frame_bytes = buffer.tobytes()
                    
                    self._last_access[device] = time.time()
                    
                    yield (b'--frame\r\n'
                           b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                    
                    time.sleep(1.0 / self.config.camera_fps)
                    
                except GeneratorExit:
                    break
                except Exception as exc:
                    logger.error(f"Stream-Fehler {device}: {exc}")
                    break
        finally:
            self.unregister_client(device)
    
    def get_snapshot(self, device: str) -> Optional[bytes]:
        """Holt ein einzelnes Bild von einer Kamera."""
        cap = self.get_stream(device)
        if not cap:
            return None
        
        lock = self._locks.get(device)
        try:
            with lock:
                success, frame = cap.read()
                if not success:
                    return None
                
                ret, buffer = cv2.imencode(
                    '.jpg', frame,
                    [cv2.IMWRITE_JPEG_QUALITY, self.config.camera_jpeg_quality]
                )
                if not ret:
                    return None
                
                return buffer.tobytes()
        except Exception as exc:
            logger.error(f"Snapshot-Fehler {device}: {exc}")
            return None
    
    def get_status(self) -> Dict:
        """Gibt Status aller aktiven Streams zurück."""
        now = time.time()
        return {
            "active_streams": len(self._streams),
            "streams": [
                {
                    "device": device,
                    "clients": self._client_count.get(device, 0),
                    "idle_seconds": int(now - self._last_access.get(device, now))
                }
                for device in self._streams.keys()
            ]
        }
    
    def shutdown(self):
        """Beendet alle Streams."""
        self._stop_cleanup.set()
        for device in list(self._streams.keys()):
            self._close_stream(device)


# =============================================================================
# Log Buffer (für Pull-Endpoint)
# =============================================================================

class LogBuffer:
    """Thread-safe Log-Buffer für Pull-basierte Log-Abholung."""
    
    def __init__(self, maxlen: int = 1000):
        self._buffer: deque = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._sequence = 0
    
    def add(self, level: str, message: str, context: Optional[Dict] = None):
        """Fügt einen Log-Eintrag hinzu."""
        with self._lock:
            self._sequence += 1
            self._buffer.append({
                "seq": self._sequence,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "level": level,
                "message": message,
                "context": context or {}
            })
    
    def get_since(self, since_seq: int = 0) -> List[Dict]:
        """Holt alle Logs seit einer Sequenznummer."""
        with self._lock:
            return [log for log in self._buffer if log["seq"] > since_seq]
    
    def get_all(self) -> List[Dict]:
        """Holt alle Logs."""
        with self._lock:
            return list(self._buffer)
    
    def clear(self) -> int:
        """Leert den Buffer und gibt die Anzahl gelöschter Einträge zurück."""
        with self._lock:
            count = len(self._buffer)
            self._buffer.clear()
            return count
    
    def get_latest_seq(self) -> int:
        """Gibt die höchste Sequenznummer zurück."""
        with self._lock:
            return self._sequence


# Globaler Log-Buffer (kann von Agent importiert werden)
log_buffer = LogBuffer()


# =============================================================================
# Device Scanner
# =============================================================================

class DeviceScanner:
    """Scannt Serial-Ports und Video-Devices."""
    
    @staticmethod
    def scan_serial_ports() -> List[Dict]:
        """Scannt USB-Serial-Ports (ttyACM*/ttyUSB*)."""
        try:
            import serial.tools.list_ports as list_ports
            
            ports = []
            for port in list_ports.comports():
                dev = port.device
                # Nur echte USB-Serial-Ports
                if not dev or not (dev.startswith("/dev/ttyACM") or dev.startswith("/dev/ttyUSB")):
                    continue
                
                ports.append({
                    "port": dev,
                    "description": port.description or "Unknown",
                    "vendor_id": f"{port.vid:04x}" if port.vid else None,
                    "product_id": f"{port.pid:04x}" if port.pid else None,
                    "manufacturer": port.manufacturer,
                    "serial_number": port.serial_number,
                })
            return ports
        except ImportError:
            logger.error("pyserial nicht installiert")
            return []
        except Exception as exc:
            logger.error(f"Serial-Scan Fehler: {exc}")
            return []
    
    @staticmethod
    def scan_cameras() -> List[Dict]:
        """Scannt Video-Devices mit Deduplizierung."""
        cameras = []
        base = Path("/dev")
        if not base.exists():
            return cameras
        
        seen_parents = set()
        
        for entry in sorted(base.iterdir()):
            if not entry.name.startswith("video"):
                continue
            if not entry.is_char_device():
                continue
            
            friendly_name = entry.name
            name_file = Path(f"/sys/class/video4linux/{entry.name}/name")
            if name_file.exists():
                try:
                    friendly_name = name_file.read_text(encoding="utf-8", errors="ignore").strip()
                except Exception:
                    pass
            
            # Deduplizierung über Parent-Device
            parent_path = Path(f"/sys/class/video4linux/{entry.name}/device")
            try:
                parent_key = str(parent_path.resolve())
            except Exception:
                parent_key = str(parent_path)
            
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            
            cameras.append({
                "device": str(entry),
                "name": friendly_name,
            })
        
        return cameras


# =============================================================================
# FastAPI App
# =============================================================================

def create_app() -> FastAPI:
    config = LocalAPIConfig()
    stream_manager = OnDemandStreamManager(config)
    stream_manager.start_cleanup_thread()
    scanner = DeviceScanner()
    
    app = FastAPI(
        title="GrowDash Local API",
        description="Unified API für Devices, Kameras und Logs",
        version="3.0"
    )
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.on_event("shutdown")
    def shutdown():
        stream_manager.shutdown()
    
    # -------------------------------------------------------------------------
    # Info
    # -------------------------------------------------------------------------
    
    @app.get("/")
    def root():
        return {
            "name": "GrowDash Local API",
            "version": "3.0",
            "endpoints": {
                "devices": "/devices",
                "ports": "/ports",
                "cameras": "/cameras",
                "stream": "/stream/{device}",
                "snapshot": "/snapshot/{device}",
                "logs": "/logs",
                "status": "/status"
            }
        }
    
    # -------------------------------------------------------------------------
    # Device Endpoints
    # -------------------------------------------------------------------------
    
    @app.get("/devices")
    def get_all_devices(_: bool = Depends(verify_auth)):
        """Alle erkannten Devices (Serial + Kameras)."""
        ports = scanner.scan_serial_ports()
        cameras = scanner.scan_cameras()
        
        return {
            "success": True,
            "serial_ports": ports,
            "cameras": [
                {
                    **cam,
                    "stream_url": f"/stream/{quote_plus(cam['device'])}",
                    "snapshot_url": f"/snapshot/{quote_plus(cam['device'])}"
                }
                for cam in cameras
            ]
        }
    
    @app.get("/ports")
    def get_ports(_: bool = Depends(verify_auth)):
        """Nur Serial-Ports."""
        ports = scanner.scan_serial_ports()
        return {"success": True, "ports": ports, "count": len(ports)}
    
    @app.get("/cameras")
    def get_cameras(_: bool = Depends(verify_auth)):
        """Nur Kameras."""
        cameras = scanner.scan_cameras()
        return {
            "success": True,
            "cameras": [
                {
                    **cam,
                    "stream_url": f"/stream/{quote_plus(cam['device'])}",
                    "snapshot_url": f"/snapshot/{quote_plus(cam['device'])}"
                }
                for cam in cameras
            ],
            "count": len(cameras)
        }
    
    # -------------------------------------------------------------------------
    # Camera Streaming (On-Demand)
    # -------------------------------------------------------------------------
    
    @app.get("/stream/{device:path}")
    def stream_camera(device: str, _: bool = Depends(verify_auth)):
        """
        MJPEG-Stream für eine Kamera.
        Stream wird erst bei Anfrage geöffnet und nach Inaktivität geschlossen.
        """
        # Device-Pfad rekonstruieren
        if not device.startswith("/dev/"):
            device = f"/dev/{device}"
        
        # Prüfen ob Device existiert
        if not Path(device).exists():
            raise HTTPException(404, f"Device nicht gefunden: {device}")
        
        return StreamingResponse(
            stream_manager.generate_mjpeg(device),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    
    @app.get("/snapshot/{device:path}")
    def get_snapshot(device: str, _: bool = Depends(verify_auth)):
        """Einzelnes Bild von einer Kamera."""
        if not device.startswith("/dev/"):
            device = f"/dev/{device}"
        
        if not Path(device).exists():
            raise HTTPException(404, f"Device nicht gefunden: {device}")
        
        image_bytes = stream_manager.get_snapshot(device)
        if not image_bytes:
            raise HTTPException(500, "Konnte kein Bild aufnehmen")
        
        return StreamingResponse(
            iter([image_bytes]),
            media_type="image/jpeg"
        )
    
    @app.get("/streams/status")
    def stream_status(_: bool = Depends(verify_auth)):
        """Status aller aktiven Streams."""
        return stream_manager.get_status()
    
    # -------------------------------------------------------------------------
    # Logs (Pull-basiert)
    # -------------------------------------------------------------------------
    
    @app.get("/logs")
    def get_logs(
        since: int = Query(0, description="Logs seit dieser Sequenznummer"),
        _: bool = Depends(verify_auth)
    ):
        """
        Holt Logs seit einer Sequenznummer (Round-Robin Pull).
        Client merkt sich die letzte seq und fragt nur neue Logs ab.
        """
        logs = log_buffer.get_since(since)
        latest_seq = log_buffer.get_latest_seq()
        
        return {
            "success": True,
            "logs": logs,
            "count": len(logs),
            "latest_seq": latest_seq,
            "next_since": latest_seq  # Client nutzt diesen Wert für nächste Anfrage
        }
    
    @app.delete("/logs")
    def clear_logs(_: bool = Depends(verify_auth)):
        """Leert den Log-Buffer."""
        count = log_buffer.clear()
        return {"success": True, "cleared": count}
    
    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------
    
    @app.get("/status")
    def get_status(_: bool = Depends(verify_auth)):
        """Gesamtstatus der lokalen API."""
        import psutil
        import platform
        
        memory = psutil.virtual_memory()
        
        return {
            "success": True,
            "api_version": "3.0",
            "system": {
                "platform": platform.system(),
                "python_version": platform.python_version(),
                "memory_available_mb": int(memory.available / 1024 / 1024),
                "memory_percent": memory.percent
            },
            "streams": stream_manager.get_status(),
            "logs": {
                "buffer_size": len(log_buffer.get_all()),
                "latest_seq": log_buffer.get_latest_seq()
            }
        }
    
    return app


# =============================================================================
# Main
# =============================================================================

if __name__ == "__main__":
    config = LocalAPIConfig()
    
    print(f"🚀 GrowDash Local API v3.0")
    print(f"   Host: {config.host}:{config.port}")
    print(f"   Auth: {'enabled' if config.device_token else 'disabled (local dev)'}")
    print()
    
    app = create_app()
    uvicorn.run(app, host=config.host, port=config.port)
