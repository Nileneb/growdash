"""
GrowDash Hardware Agent
=======================
Vereinfachter Agent, der nur Hardware-Zugriff für Laravel-Backend bereitstellt.
Keine Business-Logik, nur Device-Token-Auth und Hardware-Kommunikation.
"""

import os
import time
import json
import logging
import subprocess
from typing import Dict, List, Optional, Any
from datetime import datetime
from queue import Queue
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
                "timestamp": datetime.utcnow().isoformat(),
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
                                "timestamp": datetime.utcnow().isoformat(),
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
        
        Erwartetes Response-Format:
        {
            "commands": [
                {
                    "id": "cmd-123",
                    "type": "spray_on",
                    "params": {"duration": 5}
                },
                ...
            ]
        }
        """
        try:
            response = self.session.get(
                f"{self.base_url}/commands/pending",
                timeout=10
            )
            response.raise_for_status()
            commands = response.json().get("commands", [])
            
            if commands:
                logger.info(f"Empfangene Befehle: {len(commands)}")
            
            return commands
            
        except Exception as e:
            logger.error(f"Fehler beim Abrufen der Befehle: {e}")
            return []
    
    def report_command_result(self, command_id: str, success: bool, message: str = ""):
        """Befehlsausführung an Laravel melden"""
        try:
            response = self.session.post(
                f"{self.base_url}/commands/{command_id}/result",
                json={
                    "success": success,
                    "message": message,
                    "timestamp": datetime.utcnow().isoformat()
                },
                timeout=10
            )
            response.raise_for_status()
            logger.info(f"Befehlsergebnis gemeldet: {command_id} -> {'Erfolg' if success else 'Fehler'}")
            
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
                    "timestamp": datetime.utcnow().isoformat()
                },
                timeout=5
            )
        except Exception:
            pass  # Logs sind nicht kritisch


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
            timestamp = datetime.utcnow().isoformat()
            
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
            self._log_flash_event(datetime.utcnow().isoformat(), module_id, target_port, False, msg)
            return False, msg
            
        except Exception as e:
            msg = f"Fehler beim Flashen: {e}"
            logger.error(msg)
            self._log_flash_event(datetime.utcnow().isoformat(), module_id, target_port, False, msg)
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
    
    def execute_command(self, command: Dict) -> tuple[bool, str]:
        """
        Befehl ausführen und in Arduino-Befehle übersetzen.
        
        Unterstützte Befehle:
        - spray_on: Spray aktivieren (optional: duration in Sekunden)
        - spray_off: Spray deaktivieren
        - fill_start: Füllen starten (optional: target_liters)
        - fill_stop: Füllen stoppen
        - request_status: Status abfragen
        - request_tds: TDS-Messung anfordern
        - firmware_update: Firmware flashen (nur erlaubte Module)
        """
        cmd_type = command.get("type", "")
        params = command.get("params", {})
        
        try:
            # Spray-Befehle
            if cmd_type == "spray_on":
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
            
            # Füll-Befehle
            elif cmd_type == "fill_start":
                target_liters = params.get("target_liters", 5.0)
                self.serial.send_command(f"FillL {target_liters}")
                return True, f"Füllen gestartet (Ziel: {target_liters}L)"
                
            elif cmd_type == "fill_stop":
                self.serial.send_command("CancelFill")
                return True, "Füllen gestoppt"
            
            # Status-Abfragen
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
                    logger.info(f"Führe Befehl aus: {cmd.get('type')}")
                    
                    success, message = self.execute_command(cmd)
                    
                    if cmd_id:
                        self.laravel.report_command_result(cmd_id, success, message)
                
                time.sleep(self.config.command_poll_interval)
                
            except Exception as e:
                logger.error(f"Fehler in Command-Loop: {e}")
                time.sleep(5)
    
    def run(self):
        """Agent starten (Hauptschleife)"""
        # Loops in separaten Threads starten
        telemetry_thread = threading.Thread(target=self.telemetry_loop, daemon=True)
        command_thread = threading.Thread(target=self.command_loop, daemon=True)
        
        telemetry_thread.start()
        command_thread.start()
        
        logger.info("Agent läuft... (Strg+C zum Beenden)")
        
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
