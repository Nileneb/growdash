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
import tempfile
import shutil
from contextlib import contextmanager
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone
from queue import Queue
from pathlib import Path
import threading

import requests
from pydantic_settings import BaseSettings
from pydantic import Field
from collections import deque

# Logging konfigurieren
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class AgentConfig(BaseSettings):
    """Konfiguration aus .env Datei laden"""
    
    # Laravel Backend
    laravel_base_url: str = Field(default="https://grow.linn.games")
    # Agent-API Pfad (z. B. /api/growdash/agent)
    laravel_api_path: str = Field(default="/api/growdash/agent")
    # Onboarding Modus: PAIRING | DIRECT_LOGIN | PRECONFIGURED
    onboarding_mode: str = Field(default="PAIRING")
    
    # Device Identifikation (Device-Token-Auth, kein User-Login)
    device_public_id: str = Field(default="growdash-001")
    device_token: str = Field(default="")
    
    # Hardware
    serial_port: str = Field(default="/dev/ttyACM0")
    baud_rate: int = Field(default=9600)
    
    # Agent Verhalten
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
        self.command_response_queue = Queue()  # Für Command-Antworten
        self._stop_event = threading.Event()
        self._reader_thread = None
        self._waiting_for_response = False
        
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
        - Direkte Command-Antworten (wenn _waiting_for_response aktiv)
        """
        try:
            # Wenn wir auf eine Command-Antwort warten, alles in command_response_queue
            if self._waiting_for_response:
                self.command_response_queue.put(line)
                return
            
            # Telemetrie-Parsing (Legacy - deaktiviert)
            # K\u00f6nnte sp\u00e4ter reaktiviert werden, wenn Laravel-Endpoint existiert
            logger.debug(f"Serial RX: {line}")
            
        except Exception as e:
            logger.error(f"Fehler beim Parsen von '{line}': {e}")
    
    def send_command(self, command: str) -> bool:
        """
        Befehl an Arduino senden (ohne auf Antwort zu warten).
        
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
    
    def send_command_with_response(self, command: str, timeout: float = 5.0) -> Optional[str]:
        """
        Befehl an Arduino senden und auf Antwort warten.
        
        Args:
            command: Der zu sendende Befehl
            timeout: Maximale Wartezeit in Sekunden
            
        Returns:
            Arduino-Antwort als String oder None bei Timeout/Fehler
        """
        try:
            if not self.ser or not self.ser.is_open:
                return None
            
            # Command-Response-Queue leeren
            while not self.command_response_queue.empty():
                self.command_response_queue.get()
            
            # Flag setzen dass wir auf Antwort warten
            self._waiting_for_response = True
            
            # Befehl senden
            self.ser.write(f"{command}\n".encode('utf-8'))
            self.ser.flush()
            logger.info(f"Befehl an Arduino (mit Response): {command}")
            
            # Auf Antwort warten
            try:
                response = self.command_response_queue.get(timeout=timeout)
                logger.info(f"Arduino Antwort: {response}")
                return response
            except Exception:
                logger.warning(f"Timeout bei Command '{command}' (keine Antwort nach {timeout}s)")
                return None
            finally:
                self._waiting_for_response = False
                
        except Exception as e:
            logger.error(f"Fehler beim Senden von '{command}': {e}")
            self._waiting_for_response = False
            return None
    
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
        self.set_device_headers(config.device_public_id, config.device_token)
        # Bootstrap helpers cache
        self._cached_bootstrap_id: Optional[str] = None
        # FirmwareManager reference wird später in HardwareAgent gesetzt
        self._firmware_mgr: Optional['FirmwareManager'] = None

    # -------- Helper Methods (Bootstrap / Board Detection) --------
    def _make_bootstrap_id(self) -> str:
        """Generate a semi-stable bootstrap_id (host + time fragment)."""
        if self._cached_bootstrap_id:
            return self._cached_bootstrap_id
        host = os.uname().nodename if hasattr(os, 'uname') else 'host'
        suffix = hex(int(time.time()))[-6:]
        self._cached_bootstrap_id = f"growdash-{host}-{suffix}"
        return self._cached_bootstrap_id

    def _get_device_name(self) -> str:
        """Generischer Device-Name basierend auf Hostname."""
        import socket
        return f"GrowDash {socket.gethostname()}"
    
    def _detect_board_name_for_bootstrap(self) -> str:
        """Delegiert Board-Erkennung an FirmwareManager für zentrale Verwaltung."""
        if hasattr(self, '_firmware_mgr') and self._firmware_mgr:
            return self._firmware_mgr.detect_board_name()
        # Fallback wenn FirmwareManager noch nicht initialisiert
        return 'arduino_uno'

    def set_device_headers(self, device_id: str, device_token: str):
        """Headers für Device-Auth setzen/aktualisieren"""
        self.session.headers.update({
            "X-Device-ID": device_id or "",
            "X-Device-Token": device_token or "",
            "Content-Type": "application/json"
        })

    # ---------- Onboarding / Auth Flows (außerhalb der Agent-API) ----------
    def start_pairing_bootstrap(self) -> Optional[Dict[str, Any]]:
        """/api/agents/bootstrap mit Details aufrufen und Bootstrap-Code erhalten"""
        url = f"{self.config.laravel_base_url}/api/agents/bootstrap"
        try:
            payload = {
                "bootstrap_id": self._make_bootstrap_id(),
                "name": self._get_device_name(),
                "board_type": self._detect_board_name_for_bootstrap(),
                "capabilities": {
                    "sensors": ["water_level", "tds", "temperature"],
                    "actuators": ["spray_pump", "fill_valve"],
                },
            }
            r = requests.post(url, json=payload, timeout=20)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Pairing-Bootstrap fehlgeschlagen: {e}")
            return None

    def poll_pairing_status(self, bootstrap_id: str, code: str) -> Optional[Dict[str, Any]]:
        """/api/agents/pairing/status pollen bis Device + Token geliefert werden"""
        url = f"{self.config.laravel_base_url}/api/agents/pairing/status"
        try:
            r = requests.get(url, params={"bootstrap_id": bootstrap_id, "bootstrap_code": code}, timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Pairing-Status-Abfrage fehlgeschlagen: {e}")
            return None

    def login_direct(self, email: str, password: str) -> Optional[str]:
        """/api/auth/login → Sanctum/Bearer Token zurück"""
        url = f"{self.config.laravel_base_url}/api/auth/login"
        try:
            r = requests.post(url, json={"email": email, "password": password}, timeout=20)
            r.raise_for_status()
            data = r.json()
            # Erwartet: { token: "..." } oder ähnliches
            token = data.get("token") or data.get("access_token")
            return token
        except Exception as e:
            logger.error(f"Login fehlgeschlagen: {e}")
            return None

    def register_device_from_agent(self, bearer_token: str) -> Optional[Dict[str, Any]]:
        """/api/growdash/devices/register → public_id + agent_token (PLAINTEXT)"""
        url = f"{self.config.laravel_base_url}/api/growdash/devices/register"
        try:
            headers = {"Authorization": f"Bearer {bearer_token}", "Content-Type": "application/json"}
            payload = {
                "bootstrap_id": self._make_bootstrap_id(),
                "name": self._get_device_name(),
                "board_type": self._detect_board_name_for_bootstrap(),
                "capabilities": {
                    "board_name": self._detect_board_name_for_bootstrap(),
                    "sensors": ["water_level", "ph", "ec"],
                    "actuators": ["spray_pump", "fill_valve"],
                },
                "revoke_user_token": True,
            }
            r = requests.post(url, json=payload, headers=headers, timeout=25)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            logger.error(f"Device-Registrierung fehlgeschlagen: {e}")
            return None
    
    
    
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
    
    def send_logs_batch(self, items: List[Dict[str, Any]]):
        """Mehrere Logs in einem Request senden"""
        if not items:
            return
        try:
            self.session.post(
                f"{self.base_url}/logs",
                json={"logs": items},
                timeout=8,
            )
        except Exception:
            pass
    
    def send_heartbeat(self, last_state: Optional[Dict] = None, device_info=None) -> bool:
        """
        Heartbeat an Laravel senden (alle 30-60 Sekunden).
        Hält Device-Status auf "online" und aktualisiert last_seen_at.
        
        Args:
            last_state: Optional dict mit Systemstatus (uptime, memory, etc.)
            device_info: Optional USBDeviceInfo mit Hardware-Details
            
        Returns:
            True wenn erfolgreich, False bei Fehler
        """
        try:
            payload = {"last_state": last_state} if last_state else {}
            
            # Hardware-Info hinzufügen wenn verfügbar
            if device_info:
                payload["board_type"] = device_info.board_type
                payload["port"] = device_info.port
                payload["vendor_id"] = device_info.vendor_id
                payload["product_id"] = device_info.product_id
                payload["description"] = device_info.description
            
            response = self.session.post(
                f"{self.base_url}/heartbeat",
                json=payload,
                timeout=8
            )
            
            if response.status_code == 200:
                return True
            else:
                logger.warning(f"Heartbeat fehlgeschlagen: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"Heartbeat-Fehler: {e}")
            return False
    
    def get_available_ports(self) -> List[Dict[str, str]]:
        """
        Scanne verfügbare Serial-Ports.
        Wird vom Backend über /ports Endpoint abgerufen.
        
        Returns:
            List von Port-Infos: [{port, description, vendor_id, product_id}, ...]
        """
        try:
            import serial.tools.list_ports as list_ports
            
            ports_info = []
            ports = list_ports.comports()
            
            for port in ports:
                port_data = {
                    "port": port.device,
                    "description": port.description or "Unknown",
                    "vendor_id": f"{port.vid:04x}" if port.vid else None,
                    "product_id": f"{port.pid:04x}" if port.pid else None,
                    "manufacturer": port.manufacturer or None,
                    "serial_number": port.serial_number or None,
                }
                ports_info.append(port_data)
                logger.debug(f"Erkannter Port: {port.device} - {port.description}")
            
            return ports_info
            
        except ImportError:
            logger.error("pyserial nicht installiert - Port-Scan nicht möglich")
            return []
        except Exception as e:
            logger.error(f"Fehler beim Port-Scan: {e}")
            return []


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
    
    def _run_arduino_cli(self, args: List[str], timeout: int = 60) -> Tuple[bool, str, str]:
        """
        Zentrale Ausführung von arduino-cli mit einheitlichem Error-Handling.
        
        Args:
            args: Arduino-CLI Argumente (ohne 'arduino-cli' prefix)
            timeout: Maximale Ausführungszeit in Sekunden
            
        Returns:
            (success, stdout, stderr)
        """
        cmd = [self.arduino_cli] + args
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            if result.returncode != 0:
                return False, result.stdout or "", result.stderr or ""
            return True, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            return False, "", "arduino-cli timeout"
        except Exception as e:
            return False, "", f"arduino-cli exception: {e}"
    
    def detect_board_name(self) -> str:
        """
        Zentrale Board-Erkennung über arduino-cli board list.
        Wird sowohl für Bootstrap (LaravelClient) als auch für Firmware-Flash genutzt.
        """
        try:
            if os.path.exists(self.arduino_cli):
                success, out, err = self._run_arduino_cli(["board", "list"], timeout=10)
                if success:
                    out = (out + "\n" + err).lower()
                    if "arduino uno" in out:
                        return "arduino_uno"
                    if "arduino mega" in out:
                        return "arduino_mega"
                    if "arduino nano" in out:
                        return "arduino_nano"
                    if "esp32" in out:
                        return "esp32"
                    if "esp8266" in out:
                        return "esp8266"
        except Exception:
            pass
        return "arduino_uno"
    
    def flash_firmware(self, module_id: str, port: str = None) -> Tuple[bool, str]:
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
            success, out, err = self._run_arduino_cli(
                ["compile", "--fqbn", "arduino:avr:uno", firmware_path],
                timeout=60
            )
            if not success:
                msg = f"Kompilierung fehlgeschlagen: {err}"
                logger.error(msg)
                return False, msg
            
            logger.info("Kompilierung erfolgreich")
            
            # Upload
            success, out, err = self._run_arduino_cli(
                ["upload", "--fqbn", "arduino:avr:uno", "--port", target_port, firmware_path],
                timeout=60
            )
            if not success:
                msg = f"Upload fehlgeschlagen: {err}"
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

    def compile_sketch(self, sketch_path: str, board: str = "arduino:avr:uno") -> Tuple[bool, str]:
        """
        Kompiliert ein Arduino-Sketch ohne Upload.
        
        Args:
            sketch_path: Pfad zur .ino Datei
            board: Board FQBN (z.B. arduino:avr:uno)
            
        Returns:
            (success, message)
        """
        logger.info(f"Kompiliere Sketch: {sketch_path} für Board: {board}")
        
        success, out, err = self._run_arduino_cli(
            ["compile", "--fqbn", board, sketch_path],
            timeout=120
        )
        if not success:
            msg = f"Kompilierung fehlgeschlagen:\n{err}"
            logger.error(msg)
            return False, msg
        
        msg = "Sketch erfolgreich kompiliert"
        logger.info(msg)
        return True, f"{msg}\n{out}"
    
    def upload_hex(self, hex_file: str, board: str, port: str) -> Tuple[bool, str]:
        """
        Uploaded kompilierte .hex Datei zum Arduino.
        
        Args:
            hex_file: Pfad zur .hex Datei
            board: Board FQBN
            port: Serial-Port
            
        Returns:
            (success, message)
        """
        logger.info(f"Uploade HEX: {hex_file} -> {port} (Board: {board})")
        
        success, out, err = self._run_arduino_cli(
            ["upload", "--fqbn", board, "--port", port, "--input-file", hex_file],
            timeout=60
        )
        if not success:
            msg = f"Upload fehlgeschlagen:\n{err}"
            logger.error(msg)
            return False, msg
        
        msg = f"Firmware erfolgreich auf {port} uploaded"
        logger.info(msg)
        return True, f"{msg}\n{out}"
    
    def compile_and_upload(self, sketch_path: str, board: str, port: str) -> Tuple[bool, str]:
        """
        Kompiliert UND uploaded Sketch in einem Schritt.
        
        Args:
            sketch_path: Pfad zur .ino Datei
            board: Board FQBN
            port: Serial-Port
            
        Returns:
            (success, message)
        """
        logger.info(f"Compile + Upload: {sketch_path} -> {port} (Board: {board})")
        
        # Compile
        compile_success, compile_msg = self.compile_sketch(sketch_path, board)
        if not compile_success:
            return False, f"Kompilierung fehlgeschlagen: {compile_msg}"
        
        # Upload
        success, out, err = self._run_arduino_cli(
            ["upload", "--fqbn", board, "--port", port, sketch_path],
            timeout=60
        )
        if not success:
            msg = f"Upload fehlgeschlagen:\n{err}"
            logger.error(msg)
            return False, msg
        
        msg = f"Sketch erfolgreich kompiliert und auf {port} uploaded"
        logger.info(msg)
        
        # Log Event
        timestamp = datetime.now(timezone.utc).isoformat()
        self._log_flash_event(timestamp, sketch_path, port, True)
        
        return True, f"{msg}\n{out}"


class HardwareAgent:
    """
    Hauptklasse des Hardware-Agents.
    Verwaltet Serial-Kommunikation und Befehls-Polling.
    """
    
    @contextmanager
    def _serial_temporarily_closed(self):
        """
        Schließt die serielle Verbindung für kritische Operationen (Flash/Upload)
        und stellt sie danach wieder her.
        """
        old_serial = self.serial
        try:
            old_serial.close()
        except Exception:
            pass
        time.sleep(1)
        try:
            yield
        finally:
            time.sleep(2)
            self.serial = SerialProtocol(self.config.serial_port, self.config.baud_rate)
    
    def _create_temp_sketch(self, code: str, sketch_name: str) -> Tuple[Path, Path]:
        """
        Erstellt ein temporäres Sketch-Verzeichnis und Datei.
        
        Der Sketch-Name wird IMMER aus dem Verzeichnisnamen abgeleitet (Arduino-Konvention),
        der sketch_name Parameter wird ignoriert.
        
        Returns:
            (sketch_dir, sketch_file)
        """
        sketch_dir = Path(tempfile.mkdtemp(prefix="arduino_sketch_"))
        # Arduino erwartet: Sketch-Name == Verzeichnis-Name
        sketch_file = sketch_dir / f"{sketch_dir.name}.ino"
        sketch_file.write_text(code)
        logger.info(f"Sketch erstellt: {sketch_file}")
        return sketch_dir, sketch_file
    
    def _cleanup_temp_sketch(self, sketch_dir: Path):
        """
        Löscht das temporäre Sketch-Verzeichnis sauber auf.
        """
        try:
            shutil.rmtree(sketch_dir, ignore_errors=True)
        except Exception as e:
            logger.error(f"Fehler beim Löschen des Temp-Sketches: {e}")
    
    def __init__(self, config_override=None, device_info=None):
        self.config = config_override if config_override else AgentConfig()
        self.device_info = device_info  # Optional USBDeviceInfo
        self.serial = SerialProtocol(self.config.serial_port, self.config.baud_rate)
        self.laravel = LaravelClient(self.config)
        self.firmware_mgr = FirmwareManager(self.config)
        # Set FirmwareManager reference in LaravelClient for centralized board detection
        self.laravel._firmware_mgr = self.firmware_mgr
        self._stop_event = threading.Event()
        self._log_buffer = deque(maxlen=500)
        
        logger.info(f"Agent gestartet für Device: {self.config.device_public_id}")
        logger.info(f"Laravel Backend: {self.config.laravel_base_url}{self.config.laravel_api_path}")
        
        # Startup Health Check
        self._startup_health_check()
    
    def _startup_health_check(self):
        """Startup-Health-Check: Verbindung zu Laravel testen"""
        logger.info("Führe Startup-Health-Check durch...")
        
        # Device-Credentials prüfen
        if not self.config.device_public_id or not self.config.device_token:
            logger.info("Keine Credentials gefunden – starte Onboarding-Wizard...")
            self._run_onboarding_wizard()
            # Nach Onboarding Konfiguration neu laden
            self.config = AgentConfig()
            self.laravel.set_device_headers(self.config.device_public_id, self.config.device_token)
        
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

    def _persist_credentials(self, device_id: str, token: str):
        """Speichere Credentials in .env (idempotent)"""
        env_file = Path(".env")
        lines = []
        if env_file.exists():
            with open(env_file, 'r') as f:
                lines = f.readlines()
        keys = {"DEVICE_PUBLIC_ID": device_id, "DEVICE_TOKEN": token}
        found = {k: False for k in keys}
        out = []
        for line in lines:
            if line.startswith("DEVICE_PUBLIC_ID="):
                out.append(f"DEVICE_PUBLIC_ID={device_id}\n")
                found["DEVICE_PUBLIC_ID"] = True
            elif line.startswith("DEVICE_TOKEN="):
                out.append(f"DEVICE_TOKEN={token}\n")
                found["DEVICE_TOKEN"] = True
            else:
                out.append(line)
        for k, v in keys.items():
            if not found[k]:
                out.append(f"{k}={v}\n")
        with open(env_file, 'w') as f:
            f.writelines(out)
        logger.info("✅ Credentials in .env gespeichert")

    def _run_onboarding_wizard(self):
        mode = (self.config.onboarding_mode or "PAIRING").strip().upper()
        if mode == "PRECONFIGURED":
            logger.error("ONBOARDING_MODE=PRECONFIGURED aber keine Credentials vorhanden. Abbruch.")
            sys.exit(1)
        if mode == "PAIRING":
            logger.info("Onboarding-Modus: PAIRING")
            data = self.laravel.start_pairing_bootstrap()
            if not data:
                logger.error("Bootstrap fehlgeschlagen.")
                sys.exit(1)
            bootstrap_id = data.get("device_id") or data.get("bootstrap_id") or self.laravel._make_bootstrap_id()
            code = data.get("bootstrap_code") or data.get("code")
            if not code:
                logger.error("Kein Pairing-Code erhalten.")
                sys.exit(1)
            logger.info("Bitte öffne im Browser die Geräte-Paarung und gib den Code ein:")
            logger.info(f"Pairing-Code: {code}")
            # Polling bis 2 Minuten
            deadline = time.time() + 120
            while time.time() < deadline:
                time.sleep(3)
                status = self.laravel.poll_pairing_status(bootstrap_id, code)
                if not status:
                    continue
                if (status.get("status") == "paired") and (status.get("agent_token") is not None):
                    device_id = status.get("public_id") or (status.get("device") or {}).get("public_id")
                    token = status.get("agent_token")
                    if device_id and token:
                        self._persist_credentials(device_id, token)
                        self.laravel.set_device_headers(device_id, token)
                        return
            logger.error("Pairing zeitüberschreitung.")
            sys.exit(1)
        elif mode == "DIRECT_LOGIN":
            logger.info("Onboarding-Modus: DIRECT_LOGIN")
            try:
                email = input("E-Mail: ").strip()
                password = input("Passwort: ").strip()
            except KeyboardInterrupt:
                logger.error("Abgebrochen.")
                sys.exit(1)
            token = self.laravel.login_direct(email, password)
            if not token:
                logger.error("Login fehlgeschlagen.")
                sys.exit(1)
            reg = self.laravel.register_device_from_agent(token)
            if not reg:
                logger.error("Device-Registrierung fehlgeschlagen.")
                sys.exit(1)
            device_id = reg.get("device_id") or (reg.get("device") or {}).get("public_id")
            agent_token = reg.get("agent_token") or reg.get("plaintext_token")
            if not device_id or not agent_token:
                logger.error("Ungültige Registrierungs-Antwort.")
                sys.exit(1)
            self._persist_credentials(device_id, agent_token)
            self.laravel.set_device_headers(device_id, agent_token)
        else:
            logger.error(f"Unbekannter ONBOARDING_MODE: {mode}")
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
        Befehl ausführen.
        
        Unterstützte Befehle:
        - serial_command: Direkter Serial-Befehl ans Arduino (params.command)
        - firmware_update: Firmware flashen (nur erlaubte Module)
        - arduino_compile: Arduino-Code kompilieren
        - arduino_upload: Kompilierte .hex hochladen
        - arduino_compile_upload: Kompilieren + Upload in einem Schritt
        """
        cmd_type = command.get("type", "")
        params = command.get("params", {})
        
        try:
            # Serial Command - Arduino kennt alle Befehle selbst
            if cmd_type == "serial_command":
                arduino_command = params.get("command", "")
                if not arduino_command:
                    return False, "Kein command in params angegeben"
                
                # An Arduino senden und auf Antwort warten
                response = self.serial.send_command_with_response(arduino_command, timeout=5.0)
                
                if response is not None:
                    return True, f"Arduino: {response}"
                else:
                    # Auch bei Timeout als Erfolg werten (Befehl wurde gesendet)
                    return True, f"Command '{arduino_command}' sent (no response)"
            
            # Firmware-Update (sichere Kapselung)
            elif cmd_type == "firmware_update":
                module_id = params.get("module_id")
                if not module_id:
                    return False, "Kein module_id angegeben"
                
                with self._serial_temporarily_closed():
                    success, message = self.firmware_mgr.flash_firmware(module_id)
                
                return success, message
            
            # Arduino-CLI Commands (von Laravel ArduinoCompileController)
            elif cmd_type == "arduino_compile":
                """
                Kompiliert Arduino-Code ohne Upload.
                Params:
                  - code: Arduino Sketch Code
                  - board: Board-Type (z.B. arduino:avr:uno)
                  - sketch_name: Optional, Name des Sketches
                """
                code = params.get("code", "")
                board = params.get("board", "arduino:avr:uno")
                sketch_name = params.get("sketch_name", "temp_sketch")
                
                if not code:
                    return False, "Kein Arduino-Code angegeben"
                
                sketch_dir, sketch_file = self._create_temp_sketch(code, sketch_name)
                try:
                    success, message = self.firmware_mgr.compile_sketch(
                        str(sketch_file),
                        board
                    )
                    return success, message
                finally:
                    self._cleanup_temp_sketch(sketch_dir)
            
            elif cmd_type == "arduino_upload":
                """
                Uploaded bereits kompilierten Code zum Arduino.
                Params:
                  - hex_file: Pfad zur kompilierten .hex Datei
                  - board: Board-Type
                  - port: Serial-Port (optional, nutzt config wenn nicht angegeben)
                """
                hex_file = params.get("hex_file", "")
                board = params.get("board", "arduino:avr:uno")
                port = params.get("port", self.config.serial_port)
                
                if not hex_file or not Path(hex_file).exists():
                    return False, f"HEX-Datei nicht gefunden: {hex_file}"
                
                with self._serial_temporarily_closed():
                    success, message = self.firmware_mgr.upload_hex(
                        hex_file,
                        board,
                        port
                    )
                
                return success, message
            
            elif cmd_type == "arduino_compile_upload":
                """
                Kompiliert UND uploaded Arduino-Code in einem Schritt.
                Params:
                  - code: Arduino Sketch Code
                  - board: Board-Type
                  - port: Serial-Port (optional)
                  - sketch_name: Optional
                """
                code = params.get("code", "")
                board = params.get("board", "arduino:avr:uno")
                port = params.get("port", self.config.serial_port)
                sketch_name = params.get("sketch_name", "temp_sketch")
                
                if not code:
                    return False, "Kein Arduino-Code angegeben"
                
                sketch_dir, sketch_file = self._create_temp_sketch(code, sketch_name)
                try:
                    with self._serial_temporarily_closed():
                        success, message = self.firmware_mgr.compile_and_upload(
                            str(sketch_file),
                            board,
                            port
                        )
                    return success, message
                finally:
                    self._cleanup_temp_sketch(sketch_dir)
            
            else:
                return False, f"Unbekannter Befehl: {cmd_type}"
                
        except Exception as e:
            logger.error(f"Fehler bei Befehlsausführung '{cmd_type}': {e}")
            return False, str(e)
    
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
                uptime = int(time.time() - start_time)
                memory = psutil.virtual_memory()
                last_state = {
                    "uptime": uptime,
                    "memory_free": int(memory.available / 1024),
                    "python_version": platform.python_version(),
                    "platform": platform.system().lower(),
                }
                success = self.laravel.send_heartbeat(last_state, self.device_info)
                
                if success:
                    logger.debug(f"✅ Heartbeat gesendet (uptime={uptime}s)")
                
                # Warte 30 Sekunden
                time.sleep(30)
                
            except Exception as e:
                logger.error(f"Fehler in Heartbeat-Loop: {e}")
                time.sleep(30)

    def logs_loop(self):
        """Sammelt Logs und sendet sie periodisch als Batch"""
        while not self._stop_event.is_set():
            try:
                time.sleep(60)
                if not self._log_buffer:
                    continue
                items = []
                while self._log_buffer:
                    items.append(self._log_buffer.popleft())
                self.laravel.send_logs_batch(items)
            except Exception:
                time.sleep(60)
    
    def run(self):
        """Agent starten (Hauptschleife)"""
        # Loops in separaten Threads starten
        command_thread = threading.Thread(target=self.command_loop, daemon=True)
        heartbeat_thread = threading.Thread(target=self.heartbeat_loop, daemon=True)
        logs_thread = threading.Thread(target=self.logs_loop, daemon=True)
        
        command_thread.start()
        heartbeat_thread.start()
        logs_thread.start()
        
        logger.info("Agent läuft... (Strg+C zum Beenden)")
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

def _install_log_handler(buffer: deque):
    class BufferingHandler(logging.Handler):
        def emit(self, record: logging.LogRecord):
            try:
                buffer.append({
                    "level": record.levelname.lower(),
                    "message": self.format(record),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "context": {
                        "logger": record.name,
                    }
                })
            except Exception:
                pass
    handler = BufferingHandler()
    handler.setLevel(logging.INFO)
    fmt = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    handler.setFormatter(fmt)
    logging.getLogger().addHandler(handler)


def run_multi_device():
    """
    Startet Agent im Multi-Device-Modus.
    Scannt USB-Ports und verwaltet mehrere Device-Instanzen.
    """
    from usb_device_manager import USBDeviceManager
    
    # Lade Basis-Config
    config = AgentConfig()
    
    # Scan-Intervall aus .env oder default 12000s (3.33h)
    scan_interval = int(os.getenv('USB_SCAN_INTERVAL', '12000'))
    
    logger.info("")
    logger.info("="*60)
    logger.info("🔌 GrowDash Multi-Device Manager")
    logger.info("="*60)
    logger.info(f"USB-Scan: beim Start + alle {scan_interval}s")
    logger.info("")
    
    # Starte USB Device Manager
    manager = USBDeviceManager(
        config_template=config,
        scan_interval=scan_interval
    )
    manager.start()
    
    try:
        while True:
            time.sleep(10)
            # Status-Log alle 10s (optional reduzieren)
            active = manager.get_device_count()
            if active > 0:
                logger.debug(f"📊 Multi-Device Status: {active} aktive Devices")
    
    except KeyboardInterrupt:
        logger.info("\n🛑 Beende Multi-Device Manager...")
        manager.stop()
        logger.info("✅ Alle Devices gestoppt")


if __name__ == "__main__":
    # Prüfe ob Multi-Device-Modus aktiviert ist
    multi_device_mode = os.getenv('MULTI_DEVICE_MODE', 'false').lower() == 'true'
    
    if multi_device_mode:
        # Multi-Device-Modus: USB-Scanner verwaltet mehrere Devices
        run_multi_device()
    else:
        # Single-Device-Modus (Legacy)
        # Log-Batching aktivieren
        # Hinweis: Handler wird im Konstruktor gesetzt, nachdem Buffer existiert
        agent = HardwareAgent()
        _install_log_handler(agent._log_buffer)
        agent.run()
