"""
GrowDash Hardware Agent
=======================
Vereinfachter Agent, der nur Hardware-Zugriff für Laravel-Backend bereitstellt.
Keine Business-Logik, nur Device-Token-Auth und Hardware-Kommunikation.
"""

import os
import sys
import time
import json
import logging
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime, timezone
from queue import Queue
from pathlib import Path
import threading

import requests
from pydantic_settings import BaseSettings
from pydantic import Field

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentConfig(BaseSettings):
    """Konfiguration aus .env Datei laden"""
    
    # Laravel Backend
    laravel_base_url: str = Field(default="http://localhost")
    laravel_api_path: str = Field(default="/api/growdash")
    
    # Device Identifikation (Device-Token-Auth, kein User-Login)
    device_public_id: str = Field(default="growdash-001")
    device_token: str = Field(default="")
    
    # Hardware
    serial_port: str = Field(default="/dev/ttyACM0")
    baud_rate: int = Field(default=9600)
    
    # Agent Verhalten
    telemetry_interval: int = Field(default=10)
    command_poll_interval: int = Field(default=5)
    
    # Lokale API (nur für Debugging)
    local_api_enabled: bool = Field(default=True)
    local_api_host: str = Field(default="127.0.0.1")
    local_api_port: int = Field(default=8000)
    
    # Firmware Update (sichere Kapselung)
    firmware_dir: str = Field(default="./firmware")
    arduino_cli_path: str = Field(default="/usr/local/bin/arduino-cli")
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore'  # Extra Keys in .env ignorieren
        extra = 'ignore'  # Extra Keys in .env ignorieren


class SerialProtocol:
    """
    Seriell-Layer für Arduino-Kommunikation.
    Spricht einfaches Text-Protokoll mit dem Arduino.
    """
    
    def __init__(self, port: str, baud: int):
        import serial
        
        self.port = port
        self.baud = baud
        self.ser: Optional[serial.Serial] = None
        self.receive_queue = Queue()
        self._stop_event = threading.Event()
        self._reader_thread = None
        
        self._connect()
    
    def _connect(self):
        """Verbindung zum Arduino herstellen"""
        import serial
        
        try:
            self.ser = serial.Serial(self.port, self.baud, timeout=0.1)
            time.sleep(2)  # Arduino Reset abwarten
            logger.info(f"Verbunden mit {self.port} @ {self.baud} baud")
            
            # Reader-Thread starten
            self._reader_thread = threading.Thread(target=self._read_loop, daemon=True)
            self._reader_thread.start()
            
        except Exception as e:
            logger.error(f"Fehler beim Verbinden mit {self.port}: {e}")
            raise
    
    def _read_loop(self):
        """Kontinuierlich Daten vom Arduino lesen"""
        while not self._stop_event.is_set():
            try:
                if self.ser and self.ser.in_waiting:
                    line = self.ser.readline().decode('utf-8', errors='ignore').strip()
                    if line:
                        self._parse_message(line)
                time.sleep(0.01)
            except Exception as e:
                logger.error(f"Fehler beim Lesen: {e}")
                time.sleep(0.1)
    
    def _parse_message(self, line: str):
        """
        Arduino-Nachricht parsen und in Queue legen.
        
        Beispiel-Formate vom Arduino:
        - "WaterLevel: 45"
        - "TDS=320 TempC=22.5"
        - "Spray: ON"
        - "Tab: ON"
        """
        try:
            telemetry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "raw": line
            }
            
            # WaterLevel Status
            if "WaterLevel:" in line:
                value = line.split(":")[-1].strip()
                telemetry["sensor_id"] = "water_level"
                telemetry["value"] = float(value)
                telemetry["unit"] = "percent"
                
            # TDS und Temperatur
            elif "TDS=" in line:
                parts = line.split()
                for part in parts:
                    if "TDS=" in part:
                        telemetry["sensor_id"] = "tds"
                        telemetry["value"] = float(part.split("=")[1])
                        telemetry["unit"] = "ppm"
                    elif "TempC=" in part:
                        temp_val = part.split("=")[1]
                        if temp_val != "NaN":
                            # Separate Telemetrie für Temperatur
                            self.receive_queue.put({
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "sensor_id": "temperature",
                                "value": float(temp_val),
                                "unit": "celsius",
                                "raw": line
                            })
            
            # Spray Status
            elif "Spray:" in line:
                telemetry["sensor_id"] = "spray_status"
                telemetry["value"] = 1 if "ON" in line else 0
                telemetry["unit"] = "boolean"
                
            # Fill/Tab Status
            elif "Tab:" in line:
                telemetry["sensor_id"] = "fill_status"
                telemetry["value"] = 1 if "ON" in line else 0
                telemetry["unit"] = "boolean"
            
            # In Queue legen, wenn Sensor identifiziert wurde
            if "sensor_id" in telemetry:
                self.receive_queue.put(telemetry)
                logger.debug(f"Telemetrie geparst: {telemetry['sensor_id']} = {telemetry['value']}")
            
        except Exception as e:
            logger.error(f"Fehler beim Parsen von '{line}': {e}")
    
    def send_command(self, command: str) -> bool:
        """
        Befehl an Arduino senden.
        
        Beispiele:
        - "SprayOn" / "SprayOff"
        - "Spray 5000" (5 Sekunden)
        - "FillL 5.0" (auf 5 Liter füllen)
        - "CancelFill"
        - "Status" (Status abfragen)
        - "TDS" (TDS-Messung anfordern)
        """
        try:
            if self.ser and self.ser.is_open:
                self.ser.write(f"{command}\n".encode('utf-8'))
                self.ser.flush()
                logger.info(f"Befehl an Arduino: {command}")
                return True
            return False
        except Exception as e:
            logger.error(f"Fehler beim Senden von '{command}': {e}")
            return False
    
    def get_telemetry_batch(self, max_items: int = 100) -> List[Dict]:
        """Telemetrie-Batch aus Queue holen"""
        batch = []
        while not self.receive_queue.empty() and len(batch) < max_items:
            batch.append(self.receive_queue.get())
        return batch
    
    def close(self):
        """Verbindung schließen"""
        self._stop_event.set()
        if self._reader_thread:
            self._reader_thread.join(timeout=2)
        if self.ser and self.ser.is_open:
            self.ser.close()
            logger.info("Serielle Verbindung geschlossen")


class LaravelClient:
    """
    HTTP-Client für Laravel-Backend.
    Alle Requests tragen Device-Token-Auth im Header.
    """
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.base_url = f"{config.laravel_base_url}{config.laravel_api_path}"
        self.session = requests.Session()
        
        # Device-Token-Auth in allen Requests
        self.session.headers.update({
            "X-Device-ID": config.device_public_id,
            "X-Device-Token": config.device_token,
            "Content-Type": "application/json"
        })
    
    def send_telemetry(self, data: List[Dict]) -> bool:
        """Telemetrie-Batch an Laravel senden"""
        if not data:
            return True
            
        try:
            response = self.session.post(
                f"{self.base_url}/telemetry",
                json={
                    "device_id": self.config.device_public_id,
                    "readings": data
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Telemetrie gesendet: {len(data)} Messwerte")
            return True
            
        except Exception as e:
            logger.error(f"Fehler beim Senden der Telemetrie: {e}")
            return False
    
    def poll_commands(self) -> List[Dict]:
        """
        Befehle von Laravel abfragen (Polling-Loop).
        
        Erwartetes Response-Format (neue Laravel-API):
        {
            "success": true,
            "commands": [
                {
                    "id": 42,
                    "type": "serial_command",
                    "params": {"command": "STATUS"},
                    "created_at": "2025-12-02T10:30:00.000000Z"
                }
            ]
        }
        """
        try:
            response = self.session.get(
                f"{self.base_url}/commands/pending",
                timeout=10
            )
            response.raise_for_status()
            
            data = response.json()
            
            # Success-Feld prüfen (neue API)
            if not data.get("success", True):
                logger.warning(f"API returned success=false: {data.get('message', 'Unknown error')}")
                return []
            
            commands = data.get("commands", [])
            
            if commands:
                logger.info(f"Empfangene Befehle: {len(commands)}")
            
            return commands
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Befehle: {e}")
            return []
    
    def report_command_result(self, command_id: str, success: bool, message: str = ""):
        """Befehlsausführung an Laravel melden (neue API-Struktur)"""
        try:
            # Status basierend auf success bestimmen
            status = "completed" if success else "failed"
            
            response = self.session.post(
                f"{self.base_url}/commands/{command_id}/result",
                json={
                    "status": status,
                    "result_message": message
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Befehlsergebnis gemeldet: {command_id} -> {status}")
            
        except Exception as e:
            logger.error(f"Fehler beim Melden des Ergebnisses für {command_id}: {e}")
    
    def send_log(self, level: str, message: str):
        """Log-Nachricht an Laravel senden"""
        try:
            self.session.post(
                f"{self.base_url}/logs",
                json={
                    "device_id": self.config.device_public_id,
                    "level": level,
                    "message": message,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                },
                timeout=5
            )
        except Exception:
            pass  # Logs sind nicht kritisch
    
    def send_heartbeat(self, last_state: Optional[Dict] = None) -> bool:
        """
        Heartbeat an Laravel senden (alle 30-60 Sekunden).
        Hält Device-Status auf "online" und aktualisiert last_seen_at.
        
        Args:
            last_state: Optional dict mit Systemstatus (uptime, memory, etc.)
            
        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        try:
            payload = {}
            if last_state:
                payload["last_state"] = last_state
            
            response = self.session.post(
                f"{self.base_url}/heartbeat",
                json=payload if payload else None,
                timeout=5
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"Heartbeat fehlgeschlagen: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Heartbeat-Fehler: {e}")
            return False


class FirmwareManager:
    """
    Sichere Kapselung für Arduino-Firmware-Updates.
    Nur vordefinierte Module können geflasht werden.
    """
    
    # Erlaubte Firmware-Module (Whitelist)
    ALLOWED_MODULES = {
        "main": "GrowDash_Main.ino",
        "sensor": "GrowDash_Sensors.ino",
        "actuator": "GrowDash_Actuators.ino",
    }
    
    def __init__(self, config: AgentConfig):
        self.config = config
        self.firmware_dir = config.firmware_dir
        self.arduino_cli = config.arduino_cli_path
        
        # Prüfen, ob arduino-cli verfügbar ist
        if not os.path.exists(self.arduino_cli):
            logger.warning(f"Arduino-CLI nicht gefunden: {self.arduino_cli}")
    
    def flash_firmware(self, module_id: str, port: str = None) -> tuple[bool, str]:
        """
        Firmware auf Arduino flashen.
        Nur erlaubte Module werden akzeptiert (Whitelist).
        
        Args:
            module_id: ID des Moduls (z.B. "main", "sensor")
            port: Serial-Port (optional, nutzt config wenn nicht angegeben)
            
        Returns:
            (success, message)
        """
        # Sicherheitsprüfung: Nur erlaubte Module
        if module_id not in self.ALLOWED_MODULES:
            msg = f"Unbekanntes Modul: {module_id}. Erlaubt: {list(self.ALLOWED_MODULES.keys())}"
            logger.error(msg)
            return False, msg
        
        firmware_file = self.ALLOWED_MODULES[module_id]
        firmware_path = os.path.join(self.firmware_dir, firmware_file)
        
        # Prüfen, ob Datei existiert
        if not os.path.exists(firmware_path):
            msg = f"Firmware-Datei nicht gefunden: {firmware_path}"
            logger.error(msg)
            return False, msg
        
        # Port bestimmen
        target_port = port or self.config.serial_port
        
        try:
            # Arduino-CLI Befehl ausführen
            timestamp = datetime.now(timezone.utc).isoformat()
            
            logger.info(f"[{timestamp}] Starte Firmware-Flash: {module_id} -> {target_port}")
            
            # Kompilieren
            compile_cmd = [
                self.arduino_cli,
                "compile",
                "--fqbn", "arduino:avr:uno",  # Standard: Arduino Uno
                firmware_path
            ]
            
            result = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                msg = f"Kompilierung fehlgeschlagen: {result.stderr}"
                logger.error(msg)
                return False, msg
            
            logger.info("Kompilierung erfolgreich")
            
            # Upload
            upload_cmd = [
                self.arduino_cli,
                "upload",
                "--fqbn", "arduino:avr:uno",
                "--port", target_port,
                firmware_path
            ]
            
            result = subprocess.run(
                upload_cmd,
                capture_output=True,
                text=True,
                timeout=60
            )
            
            if result.returncode != 0:
                msg = f"Upload fehlgeschlagen: {result.stderr}"
                logger.error(msg)
                return False, msg
            
            msg = f"Firmware erfolgreich geflasht: {module_id}"
            logger.info(f"[{timestamp}] {msg}")
            
            # Flash-Ereignis loggen
            self._log_flash_event(timestamp, module_id, target_port, True)
            
            return True, msg
            
        except subprocess.TimeoutExpired:
            msg = "Firmware-Flash timeout"
            logger.error(msg)
            self._log_flash_event(datetime.now(timezone.utc).isoformat(), module_id, target_port, False, msg)
            return False, msg
            
        except Exception as e:
            msg = f"Fehler beim Flashen: {e}"
            logger.error(msg)
            self._log_flash_event(datetime.now(timezone.utc).isoformat(), module_id, target_port, False, msg)
            return False, msg
    
    def _log_flash_event(self, timestamp: str, module: str, port: str, success: bool, error: str = ""):
        """Flash-Ereignis in Logdatei schreiben"""
        log_file = os.path.join(self.firmware_dir, "flash_log.json")
        
        event = {
            "timestamp": timestamp,
            "module": module,
            "port": port,
            "success": success,
            "error": error
        }
        
        try:
            # Bestehende Logs laden
            if os.path.exists(log_file):
                with open(log_file, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            # Neues Event hinzufügen
            logs.append(event)
            
            # Nur letzte 100 Events behalten
            logs = logs[-100:]
            
            # Speichern
            os.makedirs(self.firmware_dir, exist_ok=True)
            with open(log_file, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            logger.error(f"Fehler beim Loggen des Flash-Events: {e}")


class HardwareAgent:
    """
    Hauptklasse des Hardware-Agents.
    Verwaltet Serial-Kommunikation, Telemetrie und Befehls-Polling.
    """
    
    def __init__(self):
        self.config = AgentConfig()
        self.serial = SerialProtocol(self.config.serial_port, self.config.baud_rate)
        self.laravel = LaravelClient(self.config)
        self.firmware_mgr = FirmwareManager(self.config)
        self._stop_event = threading.Event()
        
        logger.info(f"Agent gestartet für Device: {self.config.device_public_id}")
        logger.info(f"Laravel Backend: {self.config.laravel_base_url}{self.config.laravel_api_path}")
        
        # Startup Health Check
        self._startup_health_check()
    
    def _startup_health_check(self):
        """Startup-Health-Check: Verbindung zu Laravel testen"""
        logger.info("Führe Startup-Health-Check durch...")
        
        # Device-Credentials prüfen
        if not self.config.device_public_id or not self.config.device_token:
            logger.error("")
            logger.error("="*60)
            logger.error("❌ DEVICE_PUBLIC_ID oder DEVICE_TOKEN fehlt in .env!")
            logger.error("="*60)
            logger.error("")
            logger.error("Bitte führe zuerst das Onboarding durch:")
            logger.error("  python bootstrap.py")
            logger.error("")
            logger.error("Oder für Pairing-Code direkt:")
            logger.error("  python pairing.py")
            logger.error("")
            sys.exit(1)
        
        # Laravel-Verbindung testen
        try:
            response = self.laravel.session.get(
                f"{self.laravel.base_url}/commands/pending",
                timeout=10
            )
            
            if response.status_code == 200:
                logger.info("✅ Laravel-Backend erreichbar und Auth erfolgreich")
            elif response.status_code == 404:
                logger.error("")
                logger.error("="*60)
                logger.error("❌ Laravel-Backend nicht vollständig eingerichtet!")
                logger.error("="*60)
                logger.error("")
                logger.error(f"Route nicht gefunden: {self.laravel.base_url}/commands/pending")
                logger.error("")
                logger.error("Das Backend muss erst konfiguriert werden:")
                logger.error("  → Siehe LARAVEL_IMPLEMENTATION.md")
                logger.error("")
                logger.error("Credentials werden zurückgesetzt...")
                self._clear_credentials()
                logger.error("")
                logger.error("Nach Backend-Setup neu pairen:")
                logger.error("  ./setup.sh")
                logger.error("")
                sys.exit(1)
            elif response.status_code in [401, 403]:
                logger.error("")
                logger.error("="*60)
                logger.error("❌ Device-Authentifizierung fehlgeschlagen!")
                logger.error("="*60)
                logger.error("")
                logger.error("Token ungültig oder Device in Laravel-DB gelöscht")
                logger.error(f"Device-ID: {self.config.device_public_id}")
                logger.error("")
                logger.error("Credentials werden zurückgesetzt...")
                self._clear_credentials()
                logger.error("")
                logger.error("Bitte neu pairen:")
                logger.error("  ./setup.sh")
                logger.error("")
                sys.exit(1)
            else:
                logger.warning(f"⚠️ Unerwarteter Status-Code: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            logger.error("")
            logger.error("="*60)
            logger.error("❌ Keine Verbindung zum Laravel-Backend")
            logger.error("="*60)
            logger.error("")
            logger.error(f"URL: {self.config.laravel_base_url}")
            logger.error("")
            logger.error("Mögliche Ursachen:")
            logger.error("  • Backend ist offline")
            logger.error("  • Netzwerkproblem")
            logger.error("  • Falsche LARAVEL_BASE_URL in .env")
            logger.error("")
            logger.error("Prüfe Backend-Erreichbarkeit:")
            logger.error(f"  curl -I {self.config.laravel_base_url}")
            logger.error("")
            sys.exit(1)
        except Exception as e:
            logger.error(f"❌ Health-Check fehlgeschlagen: {e}")
            sys.exit(1)
    
    def _clear_credentials(self):
        """Lösche Device-Credentials aus .env bei Backend-Problemen"""
        env_file = Path(".env")
        if not env_file.exists():
            return
        
        try:
            with open(env_file, 'r') as f:
                lines = f.readlines()
            
            with open(env_file, 'w') as f:
                for line in lines:
                    if line.startswith("DEVICE_PUBLIC_ID="):
                        f.write("DEVICE_PUBLIC_ID=\n")
                    elif line.startswith("DEVICE_TOKEN="):
                        f.write("DEVICE_TOKEN=\n")
                    else:
                        f.write(line)
            
            logger.info("✅ Credentials aus .env entfernt")
        except Exception as e:
            logger.error(f"Fehler beim Löschen der Credentials: {e}")
    
    def execute_command(self, command: Dict) -> tuple[bool, str]:
        """
        Befehl ausführen und in Arduino-Befehle übersetzen.
        
        Unterstützte Befehle:
        - serial_command: Direkter Serial-Befehl ans Arduino (params.command)
        - firmware_update: Firmware flashen (nur erlaubte Module)
        
        Legacy-Befehle (für Kompatibilität):
        - spray_on, spray_off, fill_start, fill_stop, request_status, request_tds
        """
        cmd_type = command.get("type", "")
        params = command.get("params", {})
        
        try:
            # Haupt-Befehlstyp: serial_command (neue Laravel-API)
            if cmd_type == "serial_command":
                arduino_command = params.get("command", "")
                if not arduino_command:
                    return False, "Kein command in params angegeben"
                
                # Direkt an Arduino senden
                self.serial.send_command(arduino_command)
                return True, f"Command '{arduino_command}' sent to Arduino"
            
            # Legacy: Spray-Befehle
            elif cmd_type == "spray_on":
                duration = params.get("duration", 0)
                if duration > 0:
                    self.serial.send_command(f"Spray {int(duration * 1000)}")  # ms
                    return True, f"Spray für {duration}s aktiviert"
                else:
                    self.serial.send_command("SprayOn")
                    return True, "Spray aktiviert"
                    
            elif cmd_type == "spray_off":
                self.serial.send_command("SprayOff")
                return True, "Spray deaktiviert"
            
            # Legacy: Füll-Befehle
            elif cmd_type == "fill_start":
                target_liters = params.get("target_liters", 5.0)
                self.serial.send_command(f"FillL {target_liters}")
                return True, f"Füllen gestartet (Ziel: {target_liters}L)"
                
            elif cmd_type == "fill_stop":
                self.serial.send_command("CancelFill")
                return True, "Füllen gestoppt"
            
            # Legacy: Status-Abfragen
            elif cmd_type == "request_status":
                self.serial.send_command("Status")
                return True, "Status angefordert"
                
            elif cmd_type == "request_tds":
                self.serial.send_command("TDS")
                return True, "TDS-Messung angefordert"
            
            # Firmware-Update (sichere Kapselung)
            elif cmd_type == "firmware_update":
                module_id = params.get("module_id")
                if not module_id:
                    return False, "Kein module_id angegeben"
                
                # Serial-Verbindung schließen vor Flash
                self.serial.close()
                time.sleep(1)
                
                # Firmware flashen
                success, message = self.firmware_mgr.flash_firmware(module_id)
                
                # Serial-Verbindung wiederherstellen
                time.sleep(2)
                self.serial = SerialProtocol(self.config.serial_port, self.config.baud_rate)
                
                return success, message
            
            else:
                return False, f"Unbekannter Befehl: {cmd_type}"
                
        except Exception as e:
            logger.error(f"Fehler bei Befehlsausführung '{cmd_type}': {e}")
            return False, str(e)
    
    def telemetry_loop(self):
        """Telemetrie-Sendeloop (Hintergrund-Thread)"""
        while not self._stop_event.is_set():
            try:
                # Telemetrie sammeln und senden
                batch = self.serial.get_telemetry_batch()
                if batch:
                    self.laravel.send_telemetry(batch)
                
                time.sleep(self.config.telemetry_interval)
                
            except Exception as e:
                logger.error(f"Fehler in Telemetrie-Loop: {e}")
                time.sleep(5)
    
    def command_loop(self):
        """Befehls-Polling-Loop (Hintergrund-Thread)"""
        while not self._stop_event.is_set():
            try:
                # Befehle abrufen und ausführen
                commands = self.laravel.poll_commands()
                
                for cmd in commands:
                    cmd_id = cmd.get("id")
                    cmd_type = cmd.get("type")
                    
                    logger.info(f"Führe Befehl aus: {cmd_type}")
                    
                    # Optional: Command als 'executing' markieren (vor Ausführung)
                    # Aktuell nicht implementiert, da Laravel-API das nicht erwartet
                    
                    # Befehl ausführen
                    success, message = self.execute_command(cmd)
                    
                    # Ergebnis melden
                    if cmd_id:
                        self.laravel.report_command_result(cmd_id, success, message)
                
                time.sleep(self.config.command_poll_interval)
                
            except Exception as e:
                logger.error(f"Fehler in Command-Loop: {e}")
                time.sleep(5)
    
    def heartbeat_loop(self):
        """Heartbeat-Loop (Hintergrund-Thread)"""
        import platform
        import psutil
        
        start_time = time.time()
        
        while not self._stop_event.is_set():
            try:
                # System-Status sammeln
                uptime = int(time.time() - start_time)
                memory = psutil.virtual_memory()
                
                last_state = {
                    "uptime": uptime,
                    "memory_used": memory.used,
                    "memory_percent": memory.percent,
                    "python_version": platform.python_version(),
                    "platform": platform.system().lower(),
                }
                
                # Heartbeat senden
                success = self.laravel.send_heartbeat(last_state)
                
                if success:
                    logger.debug(f"✅ Heartbeat gesendet (uptime: {uptime}s)")
                
                # Warte 30 Sekunden
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Fehler in Heartbeat-Loop: {e}")
                time.sleep(30)
    
    def run(self):
        """Agent starten (Hauptschleife)"""
        # Loops in separaten Threads starten
        telemetry_thread = threading.Thread(target=self.telemetry_loop, daemon=True)
        command_thread = threading.Thread(target=self.command_loop, daemon=True)
        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        
        telemetry_thread.start()
        command_thread.start()
        heartbeat_thread.start()
        
        logger.info("Agent läuft... (Strg+C zum Beenden)")
        logger.info(f"  Telemetrie: alle {self.config.telemetry_interval}s")
        logger.info(f"  Befehle: alle {self.config.command_poll_interval}s")
        logger.info(f"  Heartbeat: alle 30s")
        
        try:
            while not self._stop_event.is_set():
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Agent wird beendet...")
            self.stop()
    
    def stop(self):
        """Agent stoppen"""
        self._stop_event.set()
        self.serial.close()
        logger.info("Agent gestoppt")


if __name__ == "__main__":
    agent = HardwareAgent()
    agent.run()
