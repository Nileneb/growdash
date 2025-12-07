import threading
import time
import logging
from typing import Optional

from agent import HardwareAgent, _install_log_handler, AgentConfig

logger = logging.getLogger(__name__)


class USBDeviceManager:
    """
    Minimaler Stub für Multi-Device-Betrieb.
    Aktuell wird genau eine HardwareAgent-Instanz hochgefahren, damit
    MULTI_DEVICE_MODE nicht mehr crasht. Später kann hier echtes USB-Scanning
    ergänzt werden.
    """

    def __init__(self, config_template: AgentConfig, scan_interval: int = 12000):
        self.config_template = config_template
        self.scan_interval = scan_interval
        self._stop_event = threading.Event()
        self._agent: Optional[HardwareAgent] = None
        self._agent_thread: Optional[threading.Thread] = None

    def start(self):
        if self._agent:
            return
        logger.info("USBDeviceManager: starte Einzel-Agent (Stub)")
        self._agent = HardwareAgent(config_override=self.config_template)
        _install_log_handler(self._agent._log_buffer)
        self._agent_thread = threading.Thread(target=self._agent.run, daemon=True)
        self._agent_thread.start()

    def stop(self):
        self._stop_event.set()
        if self._agent:
            try:
                self._agent.stop()
            except Exception:
                pass
        if self._agent_thread:
            self._agent_thread.join(timeout=5)
        logger.info("USBDeviceManager gestoppt")

    def get_device_count(self) -> int:
        return 1 if self._agent else 0
