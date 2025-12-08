"""
GrowDash Board Registry
=======================
Persistente Port→Board-Zuordnung für Multi-Device Support.
Scannt USB-Ports, erkennt Boards via arduino-cli und speichert Mapping in boards.json.
"""

import json
import logging
import subprocess
import time
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class BoardRegistry:
    """
    Verwaltet persistente Port→Board-Zuordnung.
    
    Format boards.json:
    {
        "/dev/ttyACM0": {
            "board_fqbn": "arduino:avr:uno",
            "board_name": "Arduino Uno",
            "vendor_id": "2341",
            "product_id": "0043",
            "description": "Arduino Uno",
            "last_seen": "2025-12-06T10:30:00Z"
        },
        ...
    }
    """
    
    def __init__(self, registry_file: str = "./boards.json", arduino_cli: str = "/usr/local/bin/arduino-cli", auto_refresh: bool = False):
        self.registry_file = Path(registry_file)
        self.arduino_cli = arduino_cli
        self._registry: Dict[str, Dict] = {}
        self._refresh_lock = threading.Lock()
        self._load()
        
        # Optional: Auto-Refresh beim Init
        if auto_refresh:
            logger.info("Auto-Refresh aktiviert, starte Scan...")
            self.refresh()
    
    def _load(self):
        """Lädt Registry aus JSON-Datei"""
        if self.registry_file.exists():
            try:
                with open(self.registry_file, 'r') as f:
                    self._registry = json.load(f)
                logger.info(f"Board-Registry geladen: {len(self._registry)} Einträge")
            except Exception as e:
                logger.error(f"Fehler beim Laden der Registry: {e}")
                self._registry = {}
        else:
            logger.info("Keine Registry-Datei gefunden, erstelle neue")
            self._registry = {}
    
    def _save(self):
        """Speichert Registry in JSON-Datei"""
        try:
            self.registry_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.registry_file, 'w') as f:
                json.dump(self._registry, f, indent=2)
            logger.debug(f"Registry gespeichert: {len(self._registry)} Einträge")
        except Exception as e:
            logger.error(f"Fehler beim Speichern der Registry: {e}")
    
    def _run_arduino_cli(self, args: List[str], timeout: int = 10) -> Tuple[bool, str, str]:
        """Führt arduino-cli Befehl aus"""
        cmd = [self.arduino_cli] + args
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.returncode == 0, result.stdout or "", result.stderr or ""
        except subprocess.TimeoutExpired:
            return False, "", "timeout"
        except Exception as e:
            return False, "", str(e)
    
    def _detect_board_for_port(self, port: str) -> Optional[Dict]:
        """
        Erkennt Board-Info für einen Port via arduino-cli.
        Überspringt Detection für bereits bekannte "empty" Ports (Performance).
        
        Returns:
            {"board_fqbn": "arduino:avr:uno", "board_name": "Arduino Uno"}
            oder None für leere Ports
        """
        # arduino-cli board list ausführen
        success, out, err = self._run_arduino_cli(["board", "list", "--format", "json"])
        if not success:
            logger.debug(f"Board-Detection für {port} fehlgeschlagen (arduino-cli error)")
            return None
        
        try:
            boards_data = json.loads(out)
            for board_entry in boards_data:
                detected_port = board_entry.get("address") or board_entry.get("port", {}).get("address")
                if detected_port == port:
                    matching_boards = board_entry.get("matching_boards") or board_entry.get("boards", [])
                    if matching_boards:
                        first_match = matching_boards[0]
                        return {
                            "board_fqbn": first_match.get("fqbn", "arduino:avr:uno"),
                            "board_name": first_match.get("name", "Unknown Board")
                        }
        except Exception as e:
            logger.debug(f"Fehler beim Parsen von arduino-cli board list für {port}: {e}")
        
        # Fallback: Einfache Text-Analyse
        out_lower = out.lower()
        if "arduino uno" in out_lower:
            return {"board_fqbn": "arduino:avr:uno", "board_name": "Arduino Uno"}
        elif "arduino mega" in out_lower:
            return {"board_fqbn": "arduino:avr:mega", "board_name": "Arduino Mega"}
        elif "arduino nano" in out_lower:
            return {"board_fqbn": "arduino:avr:nano", "board_name": "Arduino Nano"}
        elif "esp32" in out_lower:
            return {"board_fqbn": "esp32:esp32:esp32", "board_name": "ESP32"}
        elif "esp8266" in out_lower:
            return {"board_fqbn": "esp8266:esp8266:generic", "board_name": "ESP8266"}
        
        # Kein Board erkannt
        return None
    
    def _scan_serial_ports(self) -> List[Dict]:
        """Scannt verfügbare Serial-Ports via pyserial (nur ttyACM*/ttyUSB*)"""
        try:
            import serial.tools.list_ports as list_ports
            ports = []
            for port in list_ports.comports():
                dev = port.device
                # Nur echte USB-Serial-Ports (keine virtuellen ttyS*)
                if not dev or not (dev.startswith("/dev/ttyACM") or dev.startswith("/dev/ttyUSB")):
                    continue
                ports.append({
                    "port": dev,
                    "description": port.description or "Unknown",
                    "vendor_id": f"{port.vid:04x}" if port.vid else None,
                    "product_id": f"{port.pid:04x}" if port.pid else None,
                })
            return ports
        except ImportError:
            logger.error("pyserial nicht installiert")
            return []
        except Exception as e:
            logger.error(f"Fehler beim Port-Scan: {e}")
            return []
    
    def _scan_video_devices(self) -> List[Dict]:
        """Scannt Video-Devices (/dev/video*) für Kamera-Integration"""
        cameras = []
        base = Path("/dev")
        if not base.exists():
            return cameras
        # Mehrere /dev/video* Einträge können zur selben physischen Kamera gehören
        # (z.B. separate Knoten für MJPEG/H264/Metadata). Wir deduplizieren über
        # den gemeinsamen Gerätepfad in /sys, damit jede Kamera nur einmal erscheint.
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
                except:
                    pass
            # Parent-Gerätepfad bestimmen und als Deduplikations-Key nutzen
            parent_path = Path(f"/sys/class/video4linux/{entry.name}/device")
            try:
                parent_key = str(parent_path.resolve())
            except Exception:
                parent_key = str(parent_path)

            if parent_key in seen_parents:
                logger.debug(f"Überspringe Duplikat für Kamera {friendly_name} ({entry})")
                continue

            seen_parents.add(parent_key)
            cameras.append({
                "device": str(entry),
                "name": friendly_name,
                "type": "camera"
            })
        
        return cameras
    
    def refresh(self) -> int:
        """
        Scannt alle verfügbaren Ports/Devices und aktualisiert Registry.
        Thread-safe via Lock.
        
        Returns:
            Anzahl der aktualisierten Einträge
        """
        with self._refresh_lock:
            logger.info("Starte Board-Registry-Refresh...")
            timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            updated_count = 0
            
            # WICHTIG: Alte Registry leeren um veraltete Einträge zu entfernen
            # (z.B. duplizierte Kameras, abgesteckte Devices)
            self._registry.clear()
        
            # Serial-Ports scannen (nur ttyACM*/ttyUSB*)
            serial_ports = self._scan_serial_ports()
            for port_info in serial_ports:
                port = port_info["port"]
                
                # Board-Info erkennen
                board_info = self._detect_board_for_port(port)
                
                # Falls Detection fehlschlägt, als Unknown markieren
                if not board_info:
                    self._registry[port] = {
                        "board_fqbn": "unknown",
                        "board_name": "Unknown Device",
                        "vendor_id": port_info.get("vendor_id"),
                        "product_id": port_info.get("product_id"),
                        "description": port_info.get("description"),
                        "type": "serial",
                        "last_seen": timestamp
                    }
                    updated_count += 1
                    logger.info(f"? {port}: Unknown Device ({port_info.get('vendor_id')}:{port_info.get('product_id')})")
                    continue
                
                # Registry-Eintrag erstellen/aktualisieren für erkannte Boards
                self._registry[port] = {
                    "board_fqbn": board_info["board_fqbn"],
                    "board_name": board_info["board_name"],
                    "vendor_id": port_info.get("vendor_id"),
                    "product_id": port_info.get("product_id"),
                    "description": port_info.get("description"),
                    "type": "serial",
                    "last_seen": timestamp
                }
                updated_count += 1
                logger.info(f"✓ {port}: {board_info['board_name']} ({board_info['board_fqbn']})")
        
            # Video-Devices scannen (Kameras)
            cameras = self._scan_video_devices()
            for camera in cameras:
                device = camera["device"]
                self._registry[device] = {
                    "board_fqbn": None,  # Kameras haben kein FQBN
                    "board_name": camera["name"],
                    "vendor_id": None,
                    "product_id": None,
                    "description": camera["name"],
                    "type": "camera",
                    "last_seen": timestamp
                }
                updated_count += 1
                logger.info(f"✓ {device}: {camera['name']} (camera)")
        
            self._save()
            logger.info(f"Registry-Refresh abgeschlossen: {updated_count} Einträge")
            return updated_count
    
    def get_board(self, port: str) -> Optional[Dict]:
        """
        Gibt Board-Info für einen Port zurück.
        
        Returns:
            {"board_fqbn": "...", "board_name": "...", ...} oder None
        """
        return self._registry.get(port)
    
    def get_port_for_board(self, board_fqbn: str) -> Optional[str]:
        """
        Findet Port für ein bestimmtes Board-FQBN.
        
        Returns:
            Port-Pfad oder None
        """
        for port, info in self._registry.items():
            if info.get("board_fqbn") == board_fqbn:
                return port
        return None
    
    def get_all_boards(self) -> Dict[str, Dict]:
        """Gibt komplette Registry zurück"""
        return self._registry.copy()
    
    def get_serial_ports(self) -> Dict[str, Dict]:
        """Gibt nur Serial-Ports zurück (ohne Kameras und Empty Ports)"""
        return {
            k: v for k, v in self._registry.items() 
            if v.get("type") == "serial" and v.get("board_name") != "Empty Port"
        }
    
    def get_cameras(self) -> Dict[str, Dict]:
        """Gibt nur Kameras zurück"""
        return {k: v for k, v in self._registry.items() if v.get("type") == "camera"}
    
    def get_default_port(self) -> Optional[str]:
        """
        Gibt den ersten verfügbaren Serial-Port zurück (ohne Empty Ports).
        Nützlich wenn kein spezifischer Port konfiguriert ist.
        """
        serial_ports = self.get_serial_ports()
        if serial_ports:
            return next(iter(serial_ports.keys()))
        return None
    
    def cleanup_stale_entries(self, max_age_seconds: int = 86400):
        """
        Entfernt veraltete Einträge (älter als max_age_seconds).
        
        Args:
            max_age_seconds: Maximales Alter in Sekunden (default: 24h)
        """
        now = time.time()
        to_remove = []
        
        for port, info in self._registry.items():
            last_seen = info.get("last_seen", "")
            try:
                last_seen_ts = time.mktime(time.strptime(last_seen, "%Y-%m-%dT%H:%M:%SZ"))
                if now - last_seen_ts > max_age_seconds:
                    to_remove.append(port)
            except:
                pass
        
        for port in to_remove:
            del self._registry[port]
            logger.info(f"Veralteter Eintrag entfernt: {port}")
        
        if to_remove:
            self._save()
    
    def get_registry_age(self) -> Optional[int]:
        """
        Gibt das Alter der Registry in Sekunden zurück.
        Basierend auf dem neuesten last_seen Timestamp.
        
        Returns:
            Alter in Sekunden oder None wenn Registry leer
        """
        if not self._registry:
            return None
        
        newest_timestamp = None
        for info in self._registry.values():
            last_seen = info.get("last_seen", "")
            try:
                ts = time.mktime(time.strptime(last_seen, "%Y-%m-%dT%H:%M:%SZ"))
                if newest_timestamp is None or ts > newest_timestamp:
                    newest_timestamp = ts
            except:
                pass
        
        if newest_timestamp is None:
            return None
        
        return int(time.time() - newest_timestamp)
    
    def refresh_if_stale(self, max_age_seconds: int = 3600) -> bool:
        """
        Refresht Registry nur wenn sie älter als max_age_seconds ist.
        
        Args:
            max_age_seconds: Maximales Alter in Sekunden (default: 1h)
            
        Returns:
            True wenn Refresh durchgeführt wurde, False wenn übersprungen
        """
        age = self.get_registry_age()
        
        # Registry leer oder nicht existent → Refresh
        if age is None:
            logger.info("Registry leer, führe Refresh durch...")
            self.refresh()
            return True
        
        # Registry zu alt → Refresh
        if age > max_age_seconds:
            logger.info(f"Registry veraltet ({age}s > {max_age_seconds}s), führe Refresh durch...")
            self.refresh()
            return True
        
        # Registry aktuell genug → Skip
        logger.info(f"Registry aktuell ({age}s alt), überspringe Refresh")
        return False
    
    def async_refresh(self, callback: Optional[callable] = None) -> threading.Thread:
        """
        Startet Refresh in separatem Thread (non-blocking).
        
        Args:
            callback: Optional callback function(count: int) nach Refresh
            
        Returns:
            Thread-Objekt
        """
        def _worker():
            try:
                count = self.refresh()
                if callback:
                    callback(count)
            except Exception as e:
                logger.error(f"Async-Refresh fehlgeschlagen: {e}")
        
        thread = threading.Thread(target=_worker, daemon=True, name="BoardRegistryRefresh")
        thread.start()
        logger.info("Async-Refresh gestartet (Hintergrund-Thread)")
        return thread


def main():
    """CLI für Board-Registry"""
    import argparse
    
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    
    parser = argparse.ArgumentParser(description="GrowDash Board Registry")
    parser.add_argument("--refresh", action="store_true", help="Scannt Ports/Boards und aktualisiert Registry")
    parser.add_argument("--list", action="store_true", help="Zeigt alle Registry-Einträge")
    parser.add_argument("--cleanup", action="store_true", help="Entfernt veraltete Einträge")
    parser.add_argument("--registry-file", default="./boards.json", help="Pfad zur Registry-Datei")
    parser.add_argument("--arduino-cli", default="/usr/local/bin/arduino-cli", help="Pfad zu arduino-cli")
    
    args = parser.parse_args()
    
    registry = BoardRegistry(registry_file=args.registry_file, arduino_cli=args.arduino_cli)
    
    if args.refresh:
        count = registry.refresh()
        print(f"\n✅ Registry aktualisiert: {count} Einträge")
    
    if args.cleanup:
        registry.cleanup_stale_entries()
        print("\n✅ Veraltete Einträge entfernt")
    
    if args.list or not (args.refresh or args.cleanup):
        print("\n📋 Board Registry:")
        print("=" * 80)
        
        all_boards = registry.get_all_boards()
        serial_ports = {k: v for k, v in all_boards.items() if v.get("type") == "serial" and v.get("board_name") != "Empty Port"}
        empty_ports = {k: v for k, v in all_boards.items() if v.get("type") == "serial" and v.get("board_name") == "Empty Port"}
        
        if serial_ports:
            print("\n🔌 Serial-Ports (mit Board):")
            for port, info in serial_ports.items():
                print(f"  {port}")
                print(f"    Board: {info.get('board_name')} ({info.get('board_fqbn')})")
                print(f"    VID:PID: {info.get('vendor_id')}:{info.get('product_id')}")
                print(f"    Last Seen: {info.get('last_seen')}")
        
        if empty_ports:
            print(f"\n○ Empty Ports ({len(empty_ports)}): {', '.join(list(empty_ports.keys())[:5])}{'...' if len(empty_ports) > 5 else ''}")
        
        cameras = registry.get_cameras()
        if cameras:
            print("\n📷 Kameras:")
            for device, info in cameras.items():
                print(f"  {device}")
                print(f"    Name: {info.get('board_name')}")
                print(f"    Last Seen: {info.get('last_seen')}")
        
        if not serial_ports and not cameras:
            print("\n⚠️  Keine Einträge in Registry")
            print("   Führe --refresh aus um Devices zu scannen")


if __name__ == "__main__":
    main()
