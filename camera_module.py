"""
GrowDash Camera Module
======================
⚠️  DEPRECATED - Verwende stattdessen local_api.py für:
    - On-Demand Kamera-Streaming (/stream/{device})
    - Snapshots (/snapshot/{device})
    - Unified Device-Scanning (/cameras, /ports, /devices)

Dieses Modul wird noch vom Agent für CameraConfig, CameraEndpointBuilder
und CameraWebhookPublisher genutzt, aber der FastAPI-Server (--serve)
sollte nicht mehr verwendet werden.

Migration:
    Alt: python camera_module.py --serve (Port 8090)
    Neu: python local_api.py (Port 8000)
=========================================================================

Hilfsscript, das USB-Webcams erkennt, den lokalen Stream-Endpunkt ausgibt
und optional einem Laravel-Webhook meldet. Das Modul läuft separat von
`agent.py` und liefert nur Informationen, damit der Agent die Kamera
verlinken kann.
Integriert Board-Registry für zentrale Device-Verwaltung (Serial + Cameras).
"""

import argparse
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import quote_plus

import cv2
import requests
import uvicorn
import websocket
import base64
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import Field
from pydantic_settings import BaseSettings
from board_registry import BoardRegistry


logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class CameraConfig(BaseSettings):
    laravel_base_url: str = Field(default="https://grow.linn.games")
    laravel_api_path: str = Field(default="/api/growdash/agent")
    device_public_id: str = Field(default="")
    device_token: str = Field(default="")

    webcam_host: str = Field(default="127.0.0.1")
    webcam_port: int = Field(default=8090)
    webcam_endpoint_prefix: str = Field(default="/stream/webcam")

    webcam_webhook_path: str = Field(default="/api/growdash/agent/webcams")
    
    board_registry_path: str = Field(default="./boards.json")
    arduino_cli_path: str = Field(default="/usr/local/bin/arduino-cli")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


class CameraDetector:
    """Verwendet den Port-Scan um verfügbare Video4Linux-Geräte zu erkennen."""

    @staticmethod
    def scan() -> List[Dict[str, str]]:
        cameras: List[Dict[str, str]] = []
        base = Path("/dev")
        if not base.exists():
            return cameras

        for entry in sorted(base.iterdir()):
            if not entry.name.startswith("video"):
                continue
            if not entry.is_char_device():
                continue

            friendly_name = entry.name
            name_file = Path(f"/sys/class/video4linux/{entry.name}/name")
            if name_file.exists():
                friendly_name = name_file.read_text(encoding="utf-8", errors="ignore").strip()

            cameras.append({
                "device": str(entry),
                "name": friendly_name,
                "sys_path": f"/sys/class/video4linux/{entry.name}",
            })
        return cameras


class CameraEndpointBuilder:
    def __init__(self, config: CameraConfig):
        self.config = config

    def build(self, camera: Dict[str, str]) -> str:
        encoded = quote_plus(camera["device"])
        return f"http://{self.config.webcam_host}:{self.config.webcam_port}{self.config.webcam_endpoint_prefix}?device={encoded}"


class VideoStreamManager:
    def stream_via_websocket(self, device_path: str, ws_url: str, device_id: str, device_token: str):
        """Sendet JPEG-Frames als WebSocket-Frames an den Laravel-Server."""
        cap = self.get_or_create_stream(device_path)
        if not cap:
            logger.error(f"Kamera für WebSocket-Stream nicht verfügbar: {device_path}")
            return
        lock = self.stream_locks.get(device_path)

        def on_open(ws):
            logger.info(f"WebSocket-Video-Stream gestartet: {ws_url}")

        def on_error(ws, error):
            logger.error(f"WebSocket-Video Fehler: {error}")

        def on_close(ws, code, msg):
            logger.warning(f"WebSocket-Video Verbindung geschlossen: {code} {msg}")

        ws = websocket.WebSocketApp(
            ws_url,
            on_open=on_open,
            on_error=on_error,
            on_close=on_close,
            header=[
                f"X-Device-ID: {device_id}",
                f"X-Device-Token: {device_token}"
            ]
        )

        def send_frames():
            while True:
                try:
                    with lock:
                        success, frame = cap.read()
                        if not success:
                            time.sleep(0.1)
                            continue
                        ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                        if not ret:
                            continue
                        frame_bytes = buffer.tobytes()
                        # Base64-encode für JSON-Kompatibilität
                        frame_b64 = base64.b64encode(frame_bytes).decode('ascii')
                        payload = json.dumps({
                            "event": "video_frame",
                            "device": device_id,
                            "frame": frame_b64,
                            "timestamp": time.time()
                        })
                        ws.send(payload)
                    time.sleep(0.066)  # ~15fps
                except Exception as exc:
                    logger.error(f"WebSocket-Video Streaming-Fehler: {exc}")
                    break

        # Starte WebSocket in eigenem Thread
        thread = threading.Thread(target=ws.run_forever, daemon=True)
        thread.start()
        # Starte Frame-Sender
        send_frames()

    def __init__(self):
        self.active_streams: Dict[str, cv2.VideoCapture] = {}
        self.stream_locks: Dict[str, threading.Lock] = {}
    
    def get_or_create_stream(self, device_path: str) -> Optional[cv2.VideoCapture]:
        """Öffnet einen Video-Stream oder gibt den existierenden zurück."""
        if device_path not in self.active_streams:
            try:
                cap = cv2.VideoCapture(device_path)
                if not cap.isOpened():
                    logger.error(f"Konnte Kamera nicht öffnen: {device_path}")
                    return None
                
                # Optimale Settings für Web-Streaming
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                cap.set(cv2.CAP_PROP_FPS, 15)
                
                self.active_streams[device_path] = cap
                self.stream_locks[device_path] = threading.Lock()
                logger.info(f"Video-Stream geöffnet: {device_path}")
            except Exception as exc:
                logger.error(f"Fehler beim Öffnen der Kamera {device_path}: {exc}")
                return None
        
        return self.active_streams.get(device_path)
    
    def generate_mjpeg_stream(self, device_path: str):
        """Generator für MJPEG-Frames (Multipart HTTP Response)."""
        cap = self.get_or_create_stream(device_path)
        if not cap:
            yield b''
            return
        
        lock = self.stream_locks.get(device_path)
        
        while True:
            try:
                with lock:
                    success, frame = cap.read()
                    if not success:
                        logger.warning(f"Frame-Read fehlgeschlagen: {device_path}")
                        time.sleep(0.1)
                        continue
                    
                    # Frame zu JPEG komprimieren
                    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
                    if not ret:
                        continue
                    
                    frame_bytes = buffer.tobytes()
                
                # MJPEG-Multipart-Format
                yield (b'--frame\r\n'
                       b'Content-Type: image/jpeg\r\n\r\n' + frame_bytes + b'\r\n')
                
                time.sleep(0.033)  # ~30fps max
                
            except Exception as exc:
                logger.error(f"Streaming-Fehler für {device_path}: {exc}")
                break
    
    def release_stream(self, device_path: str):
        """Gibt einen Video-Stream frei."""
        if device_path in self.active_streams:
            self.active_streams[device_path].release()
            del self.active_streams[device_path]
            del self.stream_locks[device_path]
            logger.info(f"Video-Stream geschlossen: {device_path}")
    
    def release_all(self):
        """Gibt alle Video-Streams frei."""
        for device_path in list(self.active_streams.keys()):
            self.release_stream(device_path)


class CameraWebhookPublisher:
    def __init__(self, config: CameraConfig):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/json",
            "X-Device-ID": config.device_public_id or "",
            "X-Device-Token": config.device_token or "",
        })

    def publish(self, cameras: List[Dict[str, str]], endpoint_builder: CameraEndpointBuilder) -> bool:
        if not self.config.device_public_id or not self.config.device_token:
            logger.warning("Keine Device-Credentials, Webhook wird nicht aufgerufen.")
            return False

        payload = {
            "webcams": [
                {
                    "device_path": cam["device"],
                    "stream_endpoint": endpoint_builder.build(cam),
                    "name": cam["name"],
                }
                for cam in cameras
            ],
        }

        url = f"{self.config.laravel_base_url}{self.config.webcam_webhook_path}"
        try:
            response = self.session.post(url, json=payload, timeout=10)
            if response.status_code >= 400:
                logger.error(
                    f"Webhook Fehler {response.status_code}: {response.text[:500]}"
                )
                response.raise_for_status()
            logger.info("Webcam-Endpunkte an das Backend gemeldet.")
            return True
        except Exception as exc:
            logger.error(f"Webhook konnte nicht aufgerufen werden: {exc}")
            return False


def create_app(config: CameraConfig) -> FastAPI:
    detector = CameraDetector()
    builder = CameraEndpointBuilder(config)
    stream_manager = VideoStreamManager()
    
    # Board Registry initialisieren
    board_registry = BoardRegistry(
        registry_file=config.board_registry_path,
        arduino_cli=config.arduino_cli_path
    )

    app = FastAPI(title="GrowDash Camera Module")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["GET", "POST"],
        allow_headers=["*"]
    )
    
    @app.on_event("shutdown")
    def shutdown_event():
        """Gibt alle Video-Streams beim Herunterfahren frei."""
        stream_manager.release_all()

    @app.get("/webcams")
    def get_webcams():
        cameras = detector.scan()
        return {
            "count": len(cameras),
            "webcams": [
                {
                    "device": cam["device"],
                    "name": cam["name"],
                    "endpoint": builder.build(cam),
                }
                for cam in cameras
            ],
        }

    @app.get("/webcam-endpoint")
    def get_webcam_endpoint(device: str):
        cameras = detector.scan()
        match = next((cam for cam in cameras if cam["device"] == device), None)
        if not match:
            raise HTTPException(status_code=404, detail="Kamera nicht gefunden")
        return {"endpoint": builder.build(match)}
    
    @app.get("/stream/webcam")
    def stream_webcam(device: str):
        """MJPEG-Video-Stream für eine spezifische Webcam."""
        cameras = detector.scan()
        match = next((cam for cam in cameras if cam["device"] == device), None)
        if not match:
            raise HTTPException(status_code=404, detail="Kamera nicht gefunden")
        
        return StreamingResponse(
            stream_manager.generate_mjpeg_stream(device),
            media_type="multipart/x-mixed-replace; boundary=frame"
        )
    
    @app.get("/devices")
    def get_all_devices():
        """
        Gibt alle Devices aus der Board-Registry zurück (Serial + Cameras).
        Integriert Kamera-Endpoints für Video-Devices.
        """
        all_devices = board_registry.get_all_boards()
        
        devices_response = {
            "serial_ports": [],
            "cameras": []
        }
        
        for device_path, info in all_devices.items():
            device_type = info.get("type", "unknown")
            
            if device_type == "serial":
                devices_response["serial_ports"].append({
                    "port": device_path,
                    "board_fqbn": info.get("board_fqbn"),
                    "board_name": info.get("board_name"),
                    "vendor_id": info.get("vendor_id"),
                    "product_id": info.get("product_id"),
                    "description": info.get("description"),
                    "last_seen": info.get("last_seen")
                })
            
            elif device_type == "camera":
                # Kamera-Endpoint generieren
                cam_dict = {
                    "device": device_path,
                    "name": info.get("board_name", "Unknown Camera")
                }
                endpoint = builder.build(cam_dict)
                
                devices_response["cameras"].append({
                    "device": device_path,
                    "name": info.get("board_name"),
                    "endpoint": endpoint,
                    "description": info.get("description"),
                    "last_seen": info.get("last_seen")
                })
        
        return {
            "success": True,
            "total_devices": len(all_devices),
            "serial_count": len(devices_response["serial_ports"]),
            "camera_count": len(devices_response["cameras"]),
            "devices": devices_response
        }
    
    @app.post("/devices/refresh")
    def refresh_devices():
        """
        Scannt alle Devices neu und aktualisiert die Registry.
        """
        count = board_registry.refresh()
        return {
            "success": True,
            "message": f"Registry aktualisiert: {count} Devices erkannt",
            "count": count
        }

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="GrowDash Camera Module")
    parser.add_argument("--serve", action="store_true", help="Startet den FastAPI-Server für Endpunkte")
    parser.add_argument("--publish", action="store_true", help="Sendet gefundene Webcams als Webhook")
    parser.add_argument("--print", action="store_true", help="Gibt die gefundenen Webcams auf STDOUT aus")
    args = parser.parse_args()

    config = CameraConfig()
    detector = CameraDetector()
    builder = CameraEndpointBuilder(config)
    publisher = CameraWebhookPublisher(config)

    cameras = detector.scan()

    if args.print or not args.serve and not args.publish:
        print(json.dumps({
            "webcams": [
                {
                    "device": cam["device"],
                    "name": cam["name"],
                    "endpoint": builder.build(cam),
                }
                for cam in cameras
            ]
        }, indent=2))

    if args.publish:
        publisher.publish(cameras, builder)

    if args.serve:
        app = create_app(config)
        uvicorn.run(app, host=config.webcam_host, port=config.webcam_port)


if __name__ == "__main__":
    main()
