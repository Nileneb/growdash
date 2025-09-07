import os
import pathlib
import uvicorn
import asyncio

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, StreamingResponse, Response
from pydantic import BaseModel

from arduino import ArduinoManager
from camera import Camera

# Datenmodelle für API-Endpunkte
class CommandRequest(BaseModel):
    command: str


# Base directories
BASE_DIR = pathlib.Path(__file__).parent.resolve()
STATIC_DIR = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
CAP_DIR = BASE_DIR / "captures"

# Create directories if they don't exist
CAP_DIR.mkdir(exist_ok=True)

# Get configuration from environment variables
SERIAL_PORT = os.getenv("SERIAL_PORT")
BAUD = int(os.getenv("BAUD", "9600"))
CAM_WIDTH = int(os.getenv("CAM_WIDTH", "640"))
CAM_HEIGHT = int(os.getenv("CAM_HEIGHT", "360"))
CAM_FPS = int(os.getenv("CAM_FPS", "7"))
AUDIO_ENABLED = os.getenv("AUDIO_ENABLED", "true").lower() in ("true", "1", "yes")
AUDIO_RATE = int(os.getenv("AUDIO_RATE", "44100"))

# Debug-Ausgabe
print(f"Konfiguration: SERIAL_PORT={SERIAL_PORT}, BAUD={BAUD}")

# Initialize our main components
arduino_mgr = ArduinoManager(SERIAL_PORT, BAUD)
camera = Camera(CAM_WIDTH, CAM_HEIGHT, CAM_FPS, audio_enabled=AUDIO_ENABLED, audio_rate=AUDIO_RATE)

# Create FastAPI application
app = FastAPI(title="GrowDash Simple", version="1.0")

# Mount static directories
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/captures", StaticFiles(directory=str(CAP_DIR)), name="captures")

# Root endpoint
@app.get("/")
def root():
    """Serve the main HTML page."""
    return FileResponse(str(STATIC_DIR / "index.html"))


# Camera endpoints
@app.get("/snapshot")
def snapshot():
    """Get a single snapshot from the camera."""
    b, _ = camera.wait_new(-1, 2.0)
    if b is None:
        return Response(status_code=503)
    return Response(
        content=b, 
        media_type="image/jpeg",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"}
    )


@app.get("/video.mjpg")
def video_mjpg():
    """Provide an MJPEG stream from the camera."""
    boundary = b"frame"
    
    def gen():
        last = -1
        while True:
            b, last = camera.wait_new(last, 2.0)
            if not b:
                continue
            yield (b"--" + boundary + b"\r\n"
                   b"Content-Type: image/jpeg\r\n"
                   b"Cache-Control: no-store\r\nPragma: no-cache\r\n"
                   b"Content-Length: " + str(len(b)).encode() + b"\r\n\r\n" + b + b"\r\n")
    
    return StreamingResponse(
        gen(),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"}
    )


# Arduino command endpoint
@app.post("/api/command")
async def send_command(command_data: CommandRequest):
    """Send a command to the Arduino."""
    try:
        # Command aus dem CommandRequest-Objekt verwenden
        if command_data.command:
            arduino_mgr.write(command_data.command)
            print(f"Arduino-Befehl gesendet: {command_data.command}")
            return {"success": True}
        else:
            return {"success": False, "error": "Kein Befehl angegeben"}
    except Exception as e:
        print(f"Fehler beim Senden des Befehls: {e}")
        return {"success": False, "error": str(e)}
    
    return {"success": True}


# Audio stream endpoint
@app.get("/audio.wav")
def audio_stream():
    """Provide a continuous audio stream from the camera's microphone."""
    if not camera.audio_enabled:
        return Response(status_code=404, content="Audio nicht verfügbar")
        
    def gen():
        last_id = -1
        header_sent = False
        
        # WAV Header Information
        channels = 1  # Mono
        sample_width = 2  # 16-bit
        sample_rate = camera.audio_rate
        
        # Generate WAV header
        def wav_header(sample_rate, bits_per_sample, channels):
            datasize = 2000 * 10 * sample_width
            header = bytes("RIFF", 'ascii')
            header += (datasize + 36).to_bytes(4, 'little')
            header += bytes("WAVE", 'ascii')
            header += bytes("fmt ", 'ascii')
            header += (16).to_bytes(4, 'little')  # Subchunk size
            header += (1).to_bytes(2, 'little')  # PCM
            header += (channels).to_bytes(2, 'little')
            header += (sample_rate).to_bytes(4, 'little')
            header += (sample_rate * channels * bits_per_sample // 8).to_bytes(4, 'little')  # Byte rate
            header += (channels * bits_per_sample // 8).to_bytes(2, 'little')  # Block align
            header += (bits_per_sample).to_bytes(2, 'little')
            header += bytes("data", 'ascii')
            header += datasize.to_bytes(4, 'little')
            return header
            
        while True:
            # Get new audio data
            audio_data, last_id = camera.wait_new_audio(last_id, 0.1)
            
            if not header_sent:
                # Send WAV header first
                header = wav_header(sample_rate, sample_width * 8, channels)
                yield header
                header_sent = True
                
            if audio_data:
                yield audio_data
    
    return StreamingResponse(
        gen(),
        media_type="audio/wav",
        headers={"Cache-Control": "no-store", "Pragma": "no-cache"}
    )

# WebSocket for Arduino communication only
@app.websocket("/ws")
async def ws(websocket: WebSocket):
    print("WebSocket Verbindung eingehend")
    await websocket.accept()
    print("WebSocket Verbindung akzeptiert")
    last_seq = 0
    
    # Hintergrundtask zum kontinuierlichen Senden neuer Log-Zeilen
    async def send_log_updates():
        nonlocal last_seq
        while True:
            try:
                # Alle 0.2 Sekunden nach neuen Log-Zeilen schauen
                lines, new_seq = arduino_mgr.get_since(last_seq)
                if lines:
                    print(f"WebSocket: {len(lines)} neue Log-Zeilen gefunden")
                    for line in lines:
                        print(f"WebSocket sende: {line}")
                        await websocket.send_json({"type": "log", "data": line})
                    last_seq = new_seq
                await asyncio.sleep(0.2)
            except Exception as e:
                print(f"Fehler im Log-Update-Task: {e}")
                await asyncio.sleep(1.0)
    
    try:
        # Sende Audio-Status
        await websocket.send_json({
            "type": "audio_status", 
            "enabled": camera.audio_enabled,
            "sample_rate": camera.audio_rate if camera.audio_enabled else 0
        })
        
        # Test-Nachricht senden
        await websocket.send_json({"type": "log", "data": "=== WebSocket Verbindung hergestellt ==="})
        
        # Starte Hintergrundtask für Log-Updates
        update_task = asyncio.create_task(send_log_updates())
        
        # Listen for commands to Arduino
        while True:
            # Wait for a command from the client
            data = await websocket.receive_text()
            print(f"WebSocket: Befehl empfangen: {data}")
            
            # Send command to Arduino
            try:
                arduino_mgr.write(data)
                # Befehl als Log ausgeben (Bestätigung)
                await websocket.send_json({"type": "log", "data": f">> {data}"})
            except Exception as e:
                print(f"Fehler beim Senden des Befehls: {e}")
                await websocket.send_json({"type": "log", "data": f"ERROR: {str(e)}"})
                
            # Warten bis zur nächsten Benutzer-Interaktion
    
    except WebSocketDisconnect:
        print("WebSocket Verbindung geschlossen")
    except Exception as e:
        print(f"WebSocket Fehler: {e}")
        try:
            await websocket.send_json({"type": "log", "data": f"WebSocket Fehler: {str(e)}"})
        except:
            pass
    finally:
        # Sicherstellen, dass der Update-Task beendet wird
        if 'update_task' in locals() and update_task:
            update_task.cancel()
            try:
                await update_task
            except asyncio.CancelledError:
                pass


# Serial port information endpoint
@app.get("/api/ports")
def api_ports():
    """Get information about available serial ports."""
    return {"candidates": ArduinoManager.candidates(), "current": arduino_mgr.port}


# Shutdown handler
@app.on_event("shutdown")
def on_shutdown():
    """Clean up resources when the application shuts down."""
    camera.close()
    arduino_mgr.close()


if __name__ == "__main__":
    # Run the FastAPI application with uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
