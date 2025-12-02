"""
USB Device Manager für Multi-Device Support
============================================
Scannt automatisch USB-Ports und verwaltet separate Device-Instanzen.
"""

import time
import logging
import threading
from typing import Dict, List, Set, Optional
from dataclasses import dataclass
from queue import Queue

logger = logging.getLogger(__name__)


@dataclass
class USBDeviceInfo:
    """Info über ein erkanntes USB-Device"""
    port: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    description: Optional[str] = None
    board_type: str = "generic_serial"  # arduino_nano, arduino_uno, esp32, generic_serial


class USBScanner:
    """Scannt verfügbare USB-Ports und erkennt Arduino-Devices"""
    
    # Bekannte VID/PID Mappings für Board-Erkennung
    KNOWN_BOARDS = {
        ("2341", "0043"): "arduino_uno",     # Arduino Uno
        ("2341", "0001"): "arduino_uno",     # Arduino Uno (alternative)
        ("1a86", "7523"): "arduino_nano",    # CH340 (oft Nano Clone)
        ("0403", "6001"): "arduino_nano",    # FTDI (oft Nano)
        ("10c4", "ea60"): "esp32",           # CP2102 (oft ESP32)
        ("1a86", "55d4"): "esp32",           # CH9102 (ESP32)
    }
    
    @staticmethod
    def scan_ports() -> List[USBDeviceInfo]:
        """
        Scannt alle verfügbaren seriellen Ports.
        Akzeptiert ALLE /dev/ttyACM* und /dev/ttyUSB* (Linux) bzw. COM* (Windows).
        Keywords werden nur für Klassifikations-Hints verwendet.
        """
        try:
            import serial.tools.list_ports as list_ports
            
            devices = []
            ports = list_ports.comports()
            
            for port in ports:
                # Alle ttyACM*, ttyUSB* (Linux) oder COM* (Windows) akzeptieren
                port_name = port.device.lower()
                is_serial_device = (
                    "ttyacm" in port_name or 
                    "ttyusb" in port_name or 
                    "com" in port_name
                )
                
                if not is_serial_device:
                    continue
                
                # VID/PID extrahieren
                vendor_id = f"{port.vid:04x}" if port.vid else None
                product_id = f"{port.pid:04x}" if port.pid else None
                
                # Board-Typ klassifizieren
                board_type = USBScanner._classify_board(
                    vendor_id, 
                    product_id, 
                    port.description or ""
                )
                
                device_info = USBDeviceInfo(
                    port=port.device,
                    vendor_id=vendor_id,
                    product_id=product_id,
                    description=port.description,
                    board_type=board_type
                )
                devices.append(device_info)
                logger.debug(
                    f"Erkanntes Device: {port.device} - {port.description} "
                    f"(VID:PID={vendor_id}:{product_id}, Type={board_type})"
                )
            
            return devices
            
        except ImportError:
            logger.error("pyserial nicht installiert - USB-Scan nicht möglich")
            return []
        except Exception as e:
            logger.error(f"Fehler beim USB-Scan: {e}")
            return []
    
    @staticmethod
    def _classify_board(vendor_id: Optional[str], product_id: Optional[str], description: str) -> str:
        """
        Klassifiziert Board-Typ basierend auf VID/PID und Description.
        
        Returns:
            Board-Typ als String: arduino_nano, arduino_uno, esp32, oder generic_serial
        """
        # Prüfe bekannte VID/PID Kombinationen
        if vendor_id and product_id:
            board_type = USBScanner.KNOWN_BOARDS.get((vendor_id, product_id))
            if board_type:
                return board_type
        
        # Fallback: Klassifikation über Description-Keywords (nur Hints!)
        desc_lower = description.lower()
        
        if "arduino" in desc_lower:
            if "uno" in desc_lower:
                return "arduino_uno"
            elif "nano" in desc_lower:
                return "arduino_nano"
            else:
                return "arduino_uno"  # Default Arduino
        
        if "esp32" in desc_lower or "esp-32" in desc_lower:
            return "esp32"
        
        # Alles andere: generic_serial
        return "generic_serial"
    
    @staticmethod
    def try_handshake(port: str, baud: int = 9600, timeout: float = 3.0) -> bool:
        """
        Versucht einen einfachen Handshake mit dem Device.
        Sendet "Status" Befehl und prüft ob eine Antwort kommt.
        
        Args:
            port: Serial Port
            baud: Baud Rate
            timeout: Timeout in Sekunden
            
        Returns:
            True wenn Device antwortet, False sonst
        """
        try:
            import serial
            
            ser = serial.Serial(port, baud, timeout=1.0)
            time.sleep(2)  # Warte auf Arduino Reset
            
            # Sende Status-Anfrage
            ser.write(b"Status\n")
            ser.flush()
            
            # Warte auf Antwort
            start_time = time.time()
            while (time.time() - start_time) < timeout:
                if ser.in_waiting:
                    response = ser.readline().decode('utf-8', errors='ignore').strip()
                    if response:
                        logger.debug(f"Handshake erfolgreich auf {port}: {response}")
                        ser.close()
                        return True
                time.sleep(0.1)
            
            ser.close()
            logger.debug(f"Handshake fehlgeschlagen auf {port} (kein Response)")
            return False
            
        except Exception as e:
            logger.debug(f"Handshake fehlgeschlagen auf {port}: {e}")
            return False


class DeviceInstance:
    """
    Einzelne Device-Instanz mit eigenem Thread.
    Verwaltet SerialProtocol, LaravelClient und HardwareAgent.
    """
    
    def __init__(self, port: str, config_template, device_id: str, device_info: Optional[USBDeviceInfo] = None):
        """
        Args:
            port: USB-Port (z.B. /dev/ttyACM0)
            config_template: AgentConfig-Objekt als Template
            device_id: Eindeutige ID für dieses Device
            device_info: Optional USBDeviceInfo mit Hardware-Details
        """
        self.port = port
        self.device_id = device_id
        self.config_template = config_template
        self.device_info = device_info
        
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._agent = None
        
        logger.info(f"📱 Device-Instanz erstellt: {device_id} auf {port}")
    
    def start(self):
        """Startet Device-Thread"""
        if self._thread and self._thread.is_alive():
            logger.warning(f"Device {self.device_id} läuft bereits")
            return
        
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            name=f"Device-{self.device_id}",
            daemon=True
        )
        self._thread.start()
        logger.info(f"✅ Device-Thread gestartet: {self.device_id}")
    
    def _run(self):
        """Device-Thread-Hauptschleife"""
        try:
            # Importiere HardwareAgent hier um zirkuläre Imports zu vermeiden
            from agent import HardwareAgent, AgentConfig
            
            # Erstelle device-spezifische Config
            device_config = AgentConfig(
                serial_port=self.port,
                device_public_id=self.device_id,
                # Übernehme andere Werte vom Template
                laravel_base_url=self.config_template.laravel_base_url,
                laravel_api_path=self.config_template.laravel_api_path,
                baud_rate=self.config_template.baud_rate,
                telemetry_interval=self.config_template.telemetry_interval,
                command_poll_interval=self.config_template.command_poll_interval,
                # Token muss aus .env geladen oder separat gesetzt werden
                device_token=self.config_template.device_token
            )
            
            # Starte HardwareAgent für dieses Device mit device_info
            self._agent = HardwareAgent(
                config_override=device_config,
                device_info=self.device_info
            )
            
            logger.info(f"🚀 Agent läuft für Device {self.device_id} auf {self.port}")
            
            # Hauptschleife läuft bis Stop-Signal
            while not self._stop_event.is_set():
                time.sleep(1)
                
        except Exception as e:
            logger.error(f"❌ Fehler in Device {self.device_id}: {e}", exc_info=True)
        finally:
            logger.info(f"🛑 Device-Thread beendet: {self.device_id}")
    
    def stop(self):
        """Stoppt Device-Thread"""
        logger.info(f"Stoppe Device {self.device_id}...")
        self._stop_event.set()
        
        if self._agent:
            try:
                self._agent.stop()
            except Exception as e:
                logger.error(f"Fehler beim Stoppen von Agent {self.device_id}: {e}")
        
        if self._thread:
            self._thread.join(timeout=5)
            
        logger.info(f"✅ Device gestoppt: {self.device_id}")
    
    def is_alive(self) -> bool:
        """Prüft ob Device-Thread läuft"""
        return self._thread is not None and self._thread.is_alive()


class USBDeviceManager:
    """
    Multi-Device Manager.
    Scannt USB-Ports regelmäßig und verwaltet Device-Instanzen.
    """
    
    def __init__(self, config_template, scan_interval: int = 12000):
        """
        Args:
            config_template: AgentConfig-Objekt als Template für alle Devices
            scan_interval: Scan-Intervall in Sekunden (default: 12000 = 3.33h)
        """
        self.config_template = config_template
        self.scan_interval = scan_interval
        
        self._devices: Dict[str, DeviceInstance] = {}  # port -> DeviceInstance
        self._known_ports: Set[str] = set()
        
        self._stop_event = threading.Event()
        self._scanner_thread: Optional[threading.Thread] = None
        
        logger.info(f"🔍 USB Device Manager initialisiert (Scan alle {scan_interval}s)")
    
    def start(self):
        """Startet Device-Manager und Scanner-Thread"""
        # Initialer Scan beim Start
        self._scan_and_update()
        
        # Scanner-Thread starten
        self._stop_event.clear()
        self._scanner_thread = threading.Thread(
            target=self._scanner_loop,
            name="USB-Scanner",
            daemon=True
        )
        self._scanner_thread.start()
        logger.info("✅ USB Device Manager gestartet")
    
    def _scanner_loop(self):
        """Scanner-Thread: Regelmäßiger USB-Scan"""
        while not self._stop_event.is_set():
            try:
                # Warte Scan-Intervall
                if self._stop_event.wait(timeout=self.scan_interval):
                    break  # Stop-Signal erhalten
                
                # Führe Scan durch
                self._scan_and_update()
                
            except Exception as e:
                logger.error(f"Fehler im Scanner-Thread: {e}", exc_info=True)
                time.sleep(10)  # Kurze Pause bei Fehler
    
    def _scan_and_update(self):
        """Scannt USB-Ports und aktualisiert Device-Liste"""
        logger.info("🔍 Scanne USB-Ports...")
        
        # Scanne verfügbare Ports
        detected_devices = USBScanner.scan_ports()
        current_ports = {dev.port for dev in detected_devices}
        
        logger.info(f"Gefundene Ports: {current_ports if current_ports else 'keine'}")
        
        # Neue Devices starten
        for device_info in detected_devices:
            port = device_info.port
            
            if port not in self._devices:
                # Neues Device gefunden
                device_id = self._generate_device_id(device_info)
                
                logger.info(
                    f"🆕 Neues Device erkannt: {port} → {device_id} "
                    f"(Type: {device_info.board_type})"
                )
                
                device_instance = DeviceInstance(
                    port=port,
                    config_template=self.config_template,
                    device_id=device_id,
                    device_info=device_info
                )
                
                self._devices[port] = device_instance
                device_instance.start()
                
                self._known_ports.add(port)
        
        # Gestoppte/getrennte Devices entfernen
        disconnected_ports = self._known_ports - current_ports
        
        for port in disconnected_ports:
            if port in self._devices:
                logger.warning(f"🔌 Device getrennt: {port}")
                
                # Stoppe Device
                device = self._devices[port]
                device.stop()
                
                # Entferne aus Liste
                del self._devices[port]
                self._known_ports.discard(port)
        
        # Status-Log
        active_count = len(self._devices)
        logger.info(f"📊 Aktive Devices: {active_count}")
        
        for port, device in self._devices.items():
            status = "✅ läuft" if device.is_alive() else "❌ gestoppt"
            logger.info(f"  - {device.device_id} ({port}): {status}")
    
    def _generate_device_id(self, device_info: USBDeviceInfo) -> str:
        """
        Generiert eindeutige Device-ID basierend auf Port und Hardware-Info.
        
        Format: growdash-{vendor_id}-{product_id}-{port_nummer}
        Fallback: growdash-{port_name}
        """
        port_name = device_info.port.replace("/dev/", "").replace("/", "-")
        
        if device_info.vendor_id and device_info.product_id:
            return f"growdash-{device_info.vendor_id}-{device_info.product_id}-{port_name}"
        else:
            return f"growdash-{port_name}"
    
    def stop(self):
        """Stoppt alle Devices und Scanner-Thread"""
        logger.info("🛑 Stoppe USB Device Manager...")
        
        # Stoppe Scanner-Thread
        self._stop_event.set()
        
        if self._scanner_thread:
            self._scanner_thread.join(timeout=5)
        
        # Stoppe alle Device-Instanzen
        for port, device in list(self._devices.items()):
            device.stop()
        
        self._devices.clear()
        self._known_ports.clear()
        
        logger.info("✅ USB Device Manager gestoppt")
    
    def get_active_devices(self) -> Dict[str, DeviceInstance]:
        """Gibt Dict aller aktiven Devices zurück"""
        return self._devices.copy()
    
    def get_device_count(self) -> int:
        """Gibt Anzahl aktiver Devices zurück"""
        return len(self._devices)


def main():
    """Test-Funktion für USB Device Manager"""
    from agent import AgentConfig
    
    # Lade Config
    config = AgentConfig()
    
    # Starte Manager
    manager = USBDeviceManager(config_template=config, scan_interval=30)  # Test: alle 30s
    manager.start()
    
    try:
        logger.info("USB Device Manager läuft... (Strg+C zum Beenden)")
        
        while True:
            time.sleep(10)
            logger.info(f"Status: {manager.get_device_count()} aktive Devices")
            
    except KeyboardInterrupt:
        logger.info("\n🛑 Beende...")
        manager.stop()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    main()
