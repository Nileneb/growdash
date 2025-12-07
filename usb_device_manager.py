import json
import os
import threading
import time
import logging
from typing import Dict, Optional, Tuple, Set

from agent import HardwareAgent, _install_log_handler, AgentConfig

logger = logging.getLogger(__name__)


class USBDeviceManager:
    """
    Multi-Device Manager: scannt periodisch USB-Serial-Ports und
    startet/stopt je Port eine eigene HardwareAgent-Instanz.
    - Filtert strikt auf /dev/ttyACM* und /dev/ttyUSB* (keine ttyS* Crashes)
    - Optional: USB_DEVICE_MAP (JSON) mit dedizierten Credentials pro Port
    """

    def __init__(self, config_template: AgentConfig, scan_interval: int = 12000):
        self.config_template = config_template
        self.scan_interval = scan_interval
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._agents: Dict[str, Tuple[HardwareAgent, threading.Thread]] = {}
        self._scanner_thread: Optional[threading.Thread] = None
        self._device_map = self._load_device_map()

    def start(self):
        if self._scanner_thread and self._scanner_thread.is_alive():
            return
        self._stop_event.clear()
        # Initialer Scan synchron, damit sofort Agents starten
        self._scan_once()
        self._scanner_thread = threading.Thread(target=self._run, daemon=True)
        self._scanner_thread.start()
        logger.info("USBDeviceManager gestartet (Multi-Device)")

    def stop(self):
        self._stop_event.set()
        if self._scanner_thread:
            self._scanner_thread.join(timeout=5)
        with self._lock:
            for port, (agent, thread) in list(self._agents.items()):
                try:
                    agent.stop()
                except Exception:
                    pass
                if thread:
                    thread.join(timeout=5)
                logger.info(f"Agent für {port} gestoppt")
            self._agents.clear()
        logger.info("USBDeviceManager gestoppt")

    def get_device_count(self) -> int:
        with self._lock:
            return len(self._agents)

    # ---------- Internals ----------
    def _run(self):
        while not self._stop_event.is_set():
            time.sleep(self.scan_interval)
            self._scan_once()

    def _load_device_map(self) -> Dict[str, Dict[str, str]]:
        """Lade optionale Port→Credential-Zuordnung aus JSON (USB_DEVICE_MAP)."""
        path = os.getenv("USB_DEVICE_MAP")
        if not path:
            return {}
        try:
            with open(path, "r") as f:
                data = json.load(f)
            mapping = {}
            for entry in data if isinstance(data, list) else []:
                port = entry.get("port")
                dev_id = entry.get("device_public_id")
                token = entry.get("device_token")
                if port and dev_id and token:
                    mapping[port] = {"device_public_id": dev_id, "device_token": token}
            logger.info(f"USB_DEVICE_MAP geladen: {len(mapping)} Ports")
            return mapping
        except FileNotFoundError:
            logger.warning(f"USB_DEVICE_MAP nicht gefunden: {path}")
        except Exception as exc:
            logger.error(f"USB_DEVICE_MAP konnte nicht geladen werden: {exc}")
        return {}

    def _scan_once(self):
        ports = self._detect_serial_ports()
        with self._lock:
            current_ports = set(self._agents.keys())
            new_ports = ports - current_ports
            gone_ports = current_ports - ports

            for port in gone_ports:
                agent, thread = self._agents.pop(port, (None, None))
                if agent:
                    try:
                        agent.stop()
                    except Exception:
                        pass
                if thread:
                    thread.join(timeout=5)
                logger.info(f"Agent für {port} entfernt")

            for port in new_ports:
                self._start_agent_for_port(port)

    def _detect_serial_ports(self) -> Set[str]:
        """Scanne verfügbare USB-Serial-Ports (ttyACM*/ttyUSB*)."""
        try:
            import serial.tools.list_ports as list_ports
        except Exception as exc:
            logger.error(f"pyserial fehlt oder defekt: {exc}")
            return set()

        found: Set[str] = set()
        try:
            ports = list_ports.comports()
            for port in ports:
                dev = port.device
                if dev and (dev.startswith("/dev/ttyACM") or dev.startswith("/dev/ttyUSB")):
                    found.add(dev)
        except Exception as exc:
            logger.error(f"Port-Scan fehlgeschlagen: {exc}")
        return found

    def _get_credentials_for_port(self, port: str) -> Optional[Dict[str, str]]:
        """Liefert optionale Device-Credentials für einen Port."""
        return self._device_map.get(port)

    def _start_agent_for_port(self, port: str):
        cfg_dict = self.config_template.model_dump()
        cfg_dict["serial_port"] = port
        creds = self._get_credentials_for_port(port)
        if creds:
            cfg_dict["device_public_id"] = creds.get("device_public_id", cfg_dict.get("device_public_id"))
            cfg_dict["device_token"] = creds.get("device_token", cfg_dict.get("device_token"))
            logger.info(f"Port {port}: setze dedizierte Credentials aus USB_DEVICE_MAP")
        cfg = AgentConfig(**cfg_dict)

        try:
            agent = HardwareAgent(config_override=cfg)
        except Exception as exc:
            logger.error(f"Agent-Start für {port} fehlgeschlagen: {exc}")
            return

        _install_log_handler(agent._log_buffer)
        thread = threading.Thread(target=agent.run, daemon=True)
        thread.start()
        self._agents[port] = (agent, thread)
        logger.info(f"Agent für {port} gestartet")
