"""
GrowDash Hardware Agent - CLEAN VERSION
========================================
Einziger Zweck: Hardware-Brücke zwischen Laravel und Arduino.

WAS WIR TUN:
- Serial-Port öffnen und Befehle senden (Request/Response)
- Arduino-CLI aufrufen (compile/upload)
- USB-Ports scannen
- Commands von Laravel abholen und ausführen
- Heartbeat senden (Device online)

WAS WIR NICHT TUN:
- Business-Logik (-> Laravel)
- Daten speichern (-> Laravel)
- Automatische Telemetrie (Arduino antwortet NUR auf Commands!)
"""

import os
import sys
import time
import json
import logging
import subprocess
import threading
import requests
from typing import Dict, List, Optional, Any
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# ============================================================================
# CONFIGURATION
# ============================================================================

class Config(BaseSettings):
    """Lädt Config aus .env"""
    laravel_base_url: str = Field(default="http://localhost")
    laravel_api_path: str = Field(default="/api/growdash/agent")
    device_public_id: str = Field(default="")
    device_token: str = Field(default="")
    serial_port: str = Field(default="/dev/ttyACM0")
    baud_rate: int = Field(default=9600)
    command_poll_interval: int = Field(default=5)
    arduino_cli_path: str = Field(default="/usr/local/bin/arduino-cli")
    
    class Config:
        env_file = ".env"
        extra = 'ignore'


# ============================================================================
# SERIAL COMMUNICATION
# ============================================================================

class SerialPort:
    """Einfache Serial-Kommunikation - NUR Request/Response!"""
    
    def __init__(self, port: str, baud: int):
        self.port = port
        self.baud = baud
        self.serial = None
        self._connect()
    
    def _connect(self):
        try:
            import serial
            self.serial = serial.Serial(self.port, self.baud, timeout=1)
            logger.info(f"✅ Serial verbunden: {self.port}")
        except Exception as e:
            logger.error(f"❌ Serial-Fehler: {e}")
    
    def send(self, command: str) -> Optional[str]:
        """Befehl senden und auf Antwort warten"""
        try:
            if self.serial:
                self.serial.write(f"{command}\n".encode())
                time.sleep(0.5)
                if self.serial.in_waiting:
                    return self.serial.readline().decode('utf-8').strip()
            return None
        except Exception as e:
            logger.error(f"Send failed: {e}")
            return None
    
    def close(self):
        if self.serial:
            self.serial.close()


# ============================================================================
# ARDUINO CLI WRAPPER
# ============================================================================

class ArduinoCLI:
    """Arduino-CLI Wrapper - compile/upload"""
    
    def __init__(self, cli_path: str):
        self.cli = cli_path
    
    def compile(self, code: str, board: str = "arduino:avr:uno") -> Dict[str, Any]:
        """Kompiliert Arduino-Code"""
        import tempfile
        import shutil
        
        sketch_dir = Path(tempfile.mkdtemp(prefix="sketch_"))
        sketch_file = sketch_dir / f"{sketch_dir.name}.ino"
        
        try:
            sketch_file.write_text(code)
            
            result = subprocess.run(
                [self.cli, "compile", "--fqbn", board, str(sketch_file)],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            success = result.returncode == 0
            return {
                'status': 'completed' if success else 'failed',
                'message': '✅ Kompiliert' if success else '❌ Compile-Fehler',
                'output': result.stdout,
                'error': result.stderr if not success else ''
            }
        except Exception as e:
            return {'status': 'failed', 'message': str(e), 'output': '', 'error': str(e)}
        finally:
            shutil.rmtree(sketch_dir, ignore_errors=True)
    
    def upload(self, code: str, board: str, port: str) -> Dict[str, Any]:
        """Kompiliert und uploaded"""
        import tempfile
        import shutil
        
        sketch_dir = Path(tempfile.mkdtemp(prefix="upload_"))
        sketch_file = sketch_dir / f"{sketch_dir.name}.ino"
        
        try:
            sketch_file.write_text(code)
            
            result = subprocess.run(
                [self.cli, "compile", "--upload", "--fqbn", board, "--port", port, str(sketch_file)],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            success = result.returncode == 0
            return {
                'status': 'completed' if success else 'failed',
                'message': f'✅ Upload auf {port}' if success else '❌ Upload-Fehler',
                'output': result.stdout,
                'error': result.stderr if not success else ''
            }
        except Exception as e:
            return {'status': 'failed', 'message': str(e), 'output': '', 'error': str(e)}
        finally:
            shutil.rmtree(sketch_dir, ignore_errors=True)


# ============================================================================
# PORT SCANNER
# ============================================================================

def scan_ports() -> List[Dict]:
    """Scannt verfügbare Serial-Ports"""
    try:
        import serial.tools.list_ports as list_ports
        ports = []
        for port in list_ports.comports():
            ports.append({
                "port": port.device,
                "description": port.description or "Unknown",
                "vendor_id": f"{port.vid:04x}" if port.vid else None,
                "product_id": f"{port.pid:04x}" if port.pid else None
            })
        return ports
    except:
        return []


# ============================================================================
# LARAVEL CLIENT
# ============================================================================

class LaravelClient:
    """HTTP-Client für Laravel-Backend"""
    
    def __init__(self, config: Config):
        self.config = config
        self.base_url = f"{config.laravel_base_url}{config.laravel_api_path}"
        self.session = requests.Session()
        self.session.headers.update({
            "X-Device-ID": config.device_public_id,
            "X-Device-Token": config.device_token,
            "Content-Type": "application/json"
        })
    
    def heartbeat(self, ip_address: str = "127.0.0.1") -> bool:
        """Heartbeat an Laravel"""
        try:
            response = self.session.post(
                f"{self.base_url}/heartbeat",
                json={"ip_address": ip_address, "api_port": 8000},
                timeout=8
            )
            return response.status_code == 200
        except:
            return False
    
    def get_commands(self) -> List[Dict]:
        """Pending Commands abrufen"""
        try:
            response = self.session.get(f"{self.base_url}/commands/pending", timeout=10)
            if response.status_code == 200:
                return response.json().get("commands", [])
        except:
            pass
        return []
    
    def report_result(self, command_id: str, result: Dict):
        """Command-Result melden"""
        try:
            self.session.post(
                f"{self.base_url}/commands/{command_id}/result",
                json={
                    "status": result.get('status'),
                    "result_message": result.get('message', ''),
                    "output": result.get('output', ''),
                    "error": result.get('error', '')
                },
                timeout=10
            )
        except:
            pass


# ============================================================================
# AGENT
# ============================================================================

class Agent:
    """Hardware-Agent - DIE BRÜCKE zwischen Laravel und Arduino"""
    
    def __init__(self):
        self.config = Config()
        self.serial = SerialPort(self.config.serial_port, self.config.baud_rate)
        self.laravel = LaravelClient(self.config)
        self.arduino = ArduinoCLI(self.config.arduino_cli_path)
        self._stop = threading.Event()
        
        logger.info(f"🚀 Agent gestartet: {self.config.device_public_id}")
        logger.info(f"📡 Laravel: {self.config.laravel_base_url}")
        logger.info(f"🔌 Serial: {self.config.serial_port}")
    
    def execute_command(self, command: Dict) -> Dict[str, Any]:
        """Führt Command aus - KEINE BUSINESS-LOGIK!"""
        cmd_type = command.get("type")
        params = command.get("params", {})
        
        # Serial-Befehl direkt ans Arduino
        if cmd_type == "serial_command":
            arduino_cmd = params.get("command", "")
            response = self.serial.send(arduino_cmd)
            return {
                'status': 'completed',
                'message': f'Arduino: {response}' if response else 'Sent',
                'output': response or ''
            }
        
        # Arduino-CLI: Kompilieren
        elif cmd_type == "arduino_compile":
            return self.arduino.compile(params.get("code", ""), params.get("board", "arduino:avr:uno"))
        
        # Arduino-CLI: Upload
        elif cmd_type == "arduino_upload":
            return self.arduino.upload(
                params.get("code", ""),
                params.get("board", "arduino:avr:uno"),
                params.get("port", self.config.serial_port)
            )
        
        # Port-Scan
        elif cmd_type == "scan_ports":
            ports = scan_ports()
            return {
                'status': 'completed',
                'message': f'{len(ports)} ports found',
                'output': json.dumps({"success": True, "ports": ports, "count": len(ports)})
            }
        
        else:
            return {'status': 'failed', 'error': f'Unknown command: {cmd_type}'}
    
    def _command_loop(self):
        """Commands von Laravel abrufen"""
        while not self._stop.is_set():
            commands = self.laravel.get_commands()
            for cmd in commands:
                result = self.execute_command(cmd)
                self.laravel.report_result(cmd['id'], result)
            time.sleep(self.config.command_poll_interval)
    
    def _heartbeat_loop(self):
        """Heartbeat an Laravel"""
        while not self._stop.is_set():
            self.laravel.heartbeat(self._get_ip())
            time.sleep(30)
    
    def _get_ip(self) -> str:
        """Lokale IP ermitteln"""
        try:
            import socket
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except:
            return "127.0.0.1"
    
    def run(self):
        """Agent starten - NUR Commands + Heartbeat!"""
        threads = [
            threading.Thread(target=self._command_loop, daemon=True),
            threading.Thread(target=self._heartbeat_loop, daemon=True)
        ]
        
        for t in threads:
            t.start()
        
        logger.info("✅ Agent läuft...")
        
        try:
            while not self._stop.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("🛑 Stoppe Agent...")
            self._stop.set()
            self.serial.close()


# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    # Config prüfen
    config = Config()
    if not config.device_public_id or not config.device_token:
        logger.error("❌ DEVICE_PUBLIC_ID oder DEVICE_TOKEN fehlt in .env")
        logger.error("Run: python bootstrap.py")
        sys.exit(1)
    
    # Agent starten
    agent = Agent()
    agent.run()
