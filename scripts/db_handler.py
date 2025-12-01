# scripts/db_handler.py
"""
GrowDash Laravel-DB-Proxy
-------------------------
Statt einer lokalen SQLite-DB werden alle Daten an eine Laravel-API gesendet
und von dort wieder gelesen.
"""

import os
import time
from typing import Dict, List, Optional, Any

import requests

_DB_HANDLER_INSTANCE = None


class DbHandler:
    def __init__(self) -> None:
        base = os.getenv("LARAVEL_BASE_URL", "http://192.168.178.12")
        self.base_url = base.rstrip("/")
        self.device_slug = os.getenv("GROWDASH_DEVICE_SLUG", "growdash-1")
        self.token = os.getenv("GROWDASH_WEBHOOK_TOKEN", "")
        self.timeout = float(os.getenv("LARAVEL_HTTP_TIMEOUT", "2.0"))

    # --- interne Hilfen ---

    def _headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["X-Growdash-Token"] = self.token
        return headers

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            r = requests.post(url, json=payload, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[Laravel POST Fehler] {url}: {e}")
            return {}

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        try:
            r = requests.get(url, params=params or {}, headers=self._headers(), timeout=self.timeout)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f"[Laravel GET Fehler] {url}: {e}")
            return {}

    # --- bisherige API-Oberfläche, jetzt proxied ---

    def process_arduino_message(self, message: str) -> None:
        """Wird von app.py/WebSocket für jede Arduino-Zeile aufgerufen."""
        payload = {
            "device_slug": self.device_slug,
            "message": message,
            "level": "info",
        }
        self._post("/api/growdash/log", payload)

    def manual_spray_on(self) -> bool:
        payload = {"device_slug": self.device_slug, "action": "on"}
        resp = self._post("/api/growdash/manual-spray", payload)
        return bool(resp.get("success"))

    def manual_spray_off(self) -> bool:
        payload = {"device_slug": self.device_slug, "action": "off"}
        resp = self._post("/api/growdash/manual-spray", payload)
        return bool(resp.get("success"))

    def manual_fill_start(self, target_liters: Optional[float] = None,
                          target_level: Optional[float] = None) -> bool:
        payload = {
            "device_slug": self.device_slug,
            "action": "start",
            "target_liters": target_liters,
            "target_level": target_level,
        }
        resp = self._post("/api/growdash/manual-fill", payload)
        return bool(resp.get("success"))

    def manual_fill_stop(self) -> bool:
        payload = {"device_slug": self.device_slug, "action": "stop"}
        resp = self._post("/api/growdash/manual-fill", payload)
        return bool(resp.get("success"))

    def get_system_status(self) -> Dict[str, Any]:
        resp = self._get("/api/growdash/status", {"device_slug": self.device_slug})
        if not resp:
            # Fallback Default
            return {
                "water_level": 0,
                "water_liters": 0,
                "spray_active": False,
                "filling_active": False,
                "last_tds": None,
                "last_temperature": None,
                "timestamp": time.time(),
            }
        return resp

    def get_water_history(self, limit: int = 100, days: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"device_slug": self.device_slug, "limit": limit}
        if days is not None:
            params["days"] = days
        resp = self._get("/api/growdash/water-history", params)
        return resp.get("history", [])

    def get_tds_history(self, limit: int = 100, days: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"device_slug": self.device_slug, "limit": limit}
        if days is not None:
            params["days"] = days
        resp = self._get("/api/growdash/tds-history", params)
        return resp.get("history", [])

    def get_temperature_history(self, limit: int = 100, days: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"device_slug": self.device_slug, "limit": limit}
        if days is not None:
            params["days"] = days
        resp = self._get("/api/growdash/temperature-history", params)
        return resp.get("history", [])

    def get_spray_events(self, limit: int = 50, days: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"device_slug": self.device_slug, "limit": limit}
        if days is not None:
            params["days"] = days
        resp = self._get("/api/growdash/spray-events", params)
        return resp.get("events", [])

    def get_fill_events(self, limit: int = 50, days: Optional[int] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"device_slug": self.device_slug, "limit": limit}
        if days is not None:
            params["days"] = days
        resp = self._get("/api/growdash/fill-events", params)
        return resp.get("events", [])

    def get_logs(self, limit: int = 100, level: Optional[str] = None) -> List[Dict[str, Any]]:
        params: Dict[str, Any] = {"device_slug": self.device_slug, "limit": limit}
        if level is not None:
            params["level"] = level
        resp = self._get("/api/growdash/logs", params)
        return resp.get("logs", [])

    def log_message(self, message: str, level: str = "info") -> None:
        payload = {
            "device_slug": self.device_slug,
            "message": message,
            "level": level,
        }
        self._post("/api/growdash/log", payload)


def get_db_handler() -> DbHandler:
    global _DB_HANDLER_INSTANCE
    if _DB_HANDLER_INSTANCE is None:
        _DB_HANDLER_INSTANCE = DbHandler()
    return _DB_HANDLER_INSTANCE
