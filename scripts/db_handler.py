"""
GrowDash Datenbankzugriff
------------------------
Bietet Funktionen zum Speichern und Abrufen von Daten aus der SQLite-Datenbank.
"""

import os
import datetime
import time
import threading
from typing import Dict, List, Optional, Any
from sqlalchemy import func, desc

from scripts.db_models import (
    get_session, init_db, WaterLevel, TDSReading, TemperatureReading, 
    SprayEvent, WaterFillEvent, SystemStatus, ArduinoLog
)

# Singleton-Instanz
_DB_HANDLER_INSTANCE = None

# Thread-Lock für sichere Zugriffe
_db_lock = threading.Lock()

class DbHandler:
    """
    Handler für Datenbankzugriffe.
    Bietet einfache Funktionen zum Speichern und Abrufen von Sensordaten und Ereignissen.
    """
    
    def __init__(self):
        """Initialisiert die Datenbank, falls sie noch nicht existiert."""
        init_db()
        # Aktuelle aktive Ereignisse
        self.active_spray = None
        self.active_fill = None
        
    def process_arduino_message(self, message: str):
        """
        Verarbeitet Arduino-Nachrichten und speichert relevante Daten in der Datenbank.
        
        Args:
            message: Die Nachricht vom Arduino
        """
        # Log-Nachricht speichern
        self.log_message(message)
        
        try:
            # Wasserstand auslesen
            if "WaterLevel:" in message:
                self._process_water_level(message)
            
            # TDS-Wert auslesen
            if "TDS:" in message:
                self._process_tds(message)
            
            # Temperatur auslesen
            if "Temp:" in message:
                self._process_temperature(message)
            
            # Sprühstatus auslesen
            if "Spray:" in message:
                self._process_spray_status(message)
            
            # Füllstatus auslesen
            if "Filling:" in message:
                self._process_fill_status(message)
                
        except Exception as e:
            self.log_message(f"Fehler bei der Verarbeitung: {e}", level="error")
    
    def _process_water_level(self, message: str):
        """Verarbeitet Wasserstandsnachrichten."""
        try:
            level_str = message.split("WaterLevel:")[1].strip()
            if "%" in level_str:
                level_str = level_str.replace("%", "").strip()
            
            # Wasserstand in Prozent
            level = float(level_str)
            level = max(0, min(100, level))  # Auf 0-100% begrenzen
            
            # Umrechnung in Liter (annahme: 10L Tank)
            liters = level * 0.1  # 100% = 10L
            
            # In Datenbank speichern
            with _db_lock:
                session = get_session()
                
                # Alle 10 Minuten oder bei größerer Änderung einen neuen Eintrag erstellen
                last_entry = session.query(WaterLevel).order_by(desc(WaterLevel.timestamp)).first()
                
                if (last_entry is None or 
                    (datetime.datetime.utcnow() - last_entry.timestamp).total_seconds() > 600 or
                    abs(last_entry.level - level) >= 2.0):
                    
                    # Neuen Eintrag erstellen
                    water_level = WaterLevel(level=level, liters=liters)
                    session.add(water_level)
                    
                    # System-Status aktualisieren
                    self._update_system_status(session, water_level=level, water_liters=liters)
                    
                    session.commit()
        except Exception as e:
            self.log_message(f"Fehler beim Parsen des Wasserstands: {e}", level="error")
    
    def _process_tds(self, message: str):
        """Verarbeitet TDS-Nachrichten."""
        try:
            tds_str = message.split("TDS:")[1].strip().split()[0]
            tds_value = float(tds_str)
            
            # In Datenbank speichern
            with _db_lock:
                session = get_session()
                
                # Alle 10 Minuten oder bei größerer Änderung einen neuen Eintrag erstellen
                last_entry = session.query(TDSReading).order_by(desc(TDSReading.timestamp)).first()
                
                if (last_entry is None or 
                    (datetime.datetime.utcnow() - last_entry.timestamp).total_seconds() > 600 or
                    abs(last_entry.value - tds_value) >= 5.0):
                    
                    # Neuen Eintrag erstellen
                    tds_reading = TDSReading(value=tds_value)
                    session.add(tds_reading)
                    
                    # System-Status aktualisieren
                    self._update_system_status(session, last_tds=tds_value)
                    
                    session.commit()
        except Exception as e:
            self.log_message(f"Fehler beim Parsen des TDS-Werts: {e}", level="error")
    
    def _process_temperature(self, message: str):
        """Verarbeitet Temperatur-Nachrichten."""
        try:
            temp_str = message.split("Temp:")[1].strip().split()[0]
            temp_value = float(temp_str)
            
            # In Datenbank speichern
            with _db_lock:
                session = get_session()
                
                # Alle 10 Minuten oder bei größerer Änderung einen neuen Eintrag erstellen
                last_entry = session.query(TemperatureReading).order_by(desc(TemperatureReading.timestamp)).first()
                
                if (last_entry is None or 
                    (datetime.datetime.utcnow() - last_entry.timestamp).total_seconds() > 600 or
                    abs(last_entry.value - temp_value) >= 0.5):
                    
                    # Neuen Eintrag erstellen
                    temp_reading = TemperatureReading(value=temp_value)
                    session.add(temp_reading)
                    
                    # System-Status aktualisieren
                    self._update_system_status(session, last_temperature=temp_value)
                    
                    session.commit()
        except Exception as e:
            self.log_message(f"Fehler beim Parsen der Temperatur: {e}", level="error")
    
    def _process_spray_status(self, message: str):
        """Verarbeitet Sprühstatus-Nachrichten."""
        try:
            active = "ON" in message.split("Spray:")[1].upper()
            
            with _db_lock:
                session = get_session()
                
                if active and not self.active_spray:
                    # Sprühvorgang wurde gestartet
                    self.active_spray = SprayEvent(start_time=datetime.datetime.utcnow())
                    session.add(self.active_spray)
                    
                elif not active and self.active_spray:
                    # Sprühvorgang wurde beendet
                    self.active_spray.end_time = datetime.datetime.utcnow()
                    duration = (self.active_spray.end_time - self.active_spray.start_time).total_seconds()
                    self.active_spray.duration_seconds = int(duration)
                    self.active_spray = None
                
                # System-Status aktualisieren
                self._update_system_status(session, spray_active=active)
                
                session.commit()
        except Exception as e:
            self.log_message(f"Fehler beim Parsen des Sprühstatus: {e}", level="error")
    
    def _process_fill_status(self, message: str):
        """Verarbeitet Füllstatus-Nachrichten."""
        try:
            active = "ON" in message.split("Filling:")[1].upper()
            
            with _db_lock:
                session = get_session()
                
                if active and not self.active_fill:
                    # Füllvorgang wurde gestartet
                    self.active_fill = WaterFillEvent(start_time=datetime.datetime.utcnow())
                    session.add(self.active_fill)
                    
                    # Wasserstand vor dem Befüllen erfassen
                    last_level = session.query(WaterLevel).order_by(desc(WaterLevel.timestamp)).first()
                    if last_level:
                        self.fill_start_level = last_level.liters
                    else:
                        self.fill_start_level = 0
                    
                elif not active and self.active_fill:
                    # Füllvorgang wurde beendet
                    self.active_fill.end_time = datetime.datetime.utcnow()
                    duration = (self.active_fill.end_time - self.active_fill.start_time).total_seconds()
                    self.active_fill.duration_seconds = int(duration)
                    
                    # Berechnung der hinzugefügten Wassermenge
                    last_level = session.query(WaterLevel).order_by(desc(WaterLevel.timestamp)).first()
                    if last_level and hasattr(self, 'fill_start_level'):
                        added_liters = last_level.liters - self.fill_start_level
                        self.active_fill.actual_liters = max(0, added_liters)  # Nicht negativ
                    
                    self.active_fill = None
                
                # System-Status aktualisieren
                self._update_system_status(session, filling_active=active)
                
                session.commit()
        except Exception as e:
            self.log_message(f"Fehler beim Parsen des Füllstatus: {e}", level="error")
    
    def _update_system_status(self, session, **kwargs):
        """
        Aktualisiert den System-Status in der Datenbank.
        
        Args:
            session: SQLAlchemy-Session
            **kwargs: Zu aktualisierende Statuswerte
        """
        # Aktuellen Status abrufen oder neu erstellen
        status = session.query(SystemStatus).order_by(desc(SystemStatus.timestamp)).first()
        
        if status is None or (datetime.datetime.utcnow() - status.timestamp).total_seconds() > 60:
            # Neuen Status erstellen, wenn keiner vorhanden oder zu alt
            new_status = SystemStatus()
            
            # Werte vom alten Status übernehmen, falls vorhanden
            if status:
                new_status.water_level = status.water_level
                new_status.water_liters = status.water_liters
                new_status.spray_active = status.spray_active
                new_status.filling_active = status.filling_active
                new_status.last_tds = status.last_tds
                new_status.last_temperature = status.last_temperature
            
            # Neue Werte setzen
            for key, value in kwargs.items():
                setattr(new_status, key, value)
            
            session.add(new_status)
        else:
            # Bestehenden Status aktualisieren
            for key, value in kwargs.items():
                setattr(status, key, value)
            
            # Zeitstempel aktualisieren
            status.timestamp = datetime.datetime.utcnow()
    
    def log_message(self, message: str, level: str = "info"):
        """
        Speichert eine Lognachricht in der Datenbank.
        
        Args:
            message: Lognachricht
            level: Log-Level (info, warning, error)
        """
        try:
            with _db_lock:
                session = get_session()
                log_entry = ArduinoLog(message=message, level=level)
                session.add(log_entry)
                session.commit()
        except Exception as e:
            print(f"Fehler beim Speichern des Logs: {e}")
    
    def manual_spray_on(self):
        """Startet den Sprühnebel manuell."""
        try:
            with _db_lock:
                session = get_session()
                
                # Neues Sprüh-Ereignis erstellen
                if not self.active_spray:
                    self.active_spray = SprayEvent(
                        start_time=datetime.datetime.utcnow(),
                        manual=True
                    )
                    session.add(self.active_spray)
                
                # Status aktualisieren
                self._update_system_status(session, spray_active=True)
                
                session.commit()
                return True
        except Exception as e:
            self.log_message(f"Fehler beim Starten des Sprühnebels: {e}", level="error")
            return False
    
    def manual_spray_off(self):
        """Stoppt den Sprühnebel manuell."""
        try:
            with _db_lock:
                session = get_session()
                
                # Aktives Sprüh-Ereignis abschließen
                if self.active_spray:
                    self.active_spray.end_time = datetime.datetime.utcnow()
                    duration = (self.active_spray.end_time - self.active_spray.start_time).total_seconds()
                    self.active_spray.duration_seconds = int(duration)
                    self.active_spray = None
                
                # Status aktualisieren
                self._update_system_status(session, spray_active=False)
                
                session.commit()
                return True
        except Exception as e:
            self.log_message(f"Fehler beim Stoppen des Sprühnebels: {e}", level="error")
            return False
    
    def manual_fill_start(self, target_liters=None, target_level=None):
        """
        Startet die Wasserzufuhr manuell.
        
        Args:
            target_liters: Zielmenge in Litern
            target_level: Zielfüllstand in Prozent
        """
        try:
            with _db_lock:
                session = get_session()
                
                # Neues Füll-Ereignis erstellen
                if not self.active_fill:
                    self.active_fill = WaterFillEvent(
                        start_time=datetime.datetime.utcnow(),
                        target_liters=target_liters,
                        target_level=target_level,
                        manual=True
                    )
                    session.add(self.active_fill)
                    
                    # Wasserstand vor dem Befüllen erfassen
                    last_level = session.query(WaterLevel).order_by(desc(WaterLevel.timestamp)).first()
                    if last_level:
                        self.fill_start_level = last_level.liters
                    else:
                        self.fill_start_level = 0
                
                # Status aktualisieren
                self._update_system_status(session, filling_active=True)
                
                session.commit()
                return True
        except Exception as e:
            self.log_message(f"Fehler beim Starten der Wasserzufuhr: {e}", level="error")
            return False
    
    def manual_fill_stop(self):
        """Stoppt die Wasserzufuhr manuell."""
        try:
            with _db_lock:
                session = get_session()
                
                # Aktives Füll-Ereignis abschließen
                if self.active_fill:
                    self.active_fill.end_time = datetime.datetime.utcnow()
                    duration = (self.active_fill.end_time - self.active_fill.start_time).total_seconds()
                    self.active_fill.duration_seconds = int(duration)
                    
                    # Berechnung der hinzugefügten Wassermenge
                    last_level = session.query(WaterLevel).order_by(desc(WaterLevel.timestamp)).first()
                    if last_level and hasattr(self, 'fill_start_level'):
                        added_liters = last_level.liters - self.fill_start_level
                        self.active_fill.actual_liters = max(0, added_liters)  # Nicht negativ
                    
                    self.active_fill = None
                
                # Status aktualisieren
                self._update_system_status(session, filling_active=False)
                
                session.commit()
                return True
        except Exception as e:
            self.log_message(f"Fehler beim Stoppen der Wasserzufuhr: {e}", level="error")
            return False
    
    def get_system_status(self) -> Dict:
        """
        Gibt den aktuellen Systemstatus zurück.
        
        Returns:
            Dictionary mit Statuswerten
        """
        try:
            with _db_lock:
                session = get_session()
                status = session.query(SystemStatus).order_by(desc(SystemStatus.timestamp)).first()
                
                if status:
                    return {
                        "water_level": status.water_level,
                        "water_liters": status.water_liters,
                        "spray_active": status.spray_active,
                        "filling_active": status.filling_active,
                        "last_tds": status.last_tds,
                        "last_temperature": status.last_temperature,
                        "timestamp": status.timestamp.timestamp()
                    }
                else:
                    return {
                        "water_level": 0,
                        "water_liters": 0,
                        "spray_active": False,
                        "filling_active": False,
                        "last_tds": None,
                        "last_temperature": None,
                        "timestamp": time.time()
                    }
        except Exception as e:
            self.log_message(f"Fehler beim Abrufen des Systemstatus: {e}", level="error")
            return {
                "water_level": 0,
                "water_liters": 0,
                "spray_active": False,
                "filling_active": False,
                "last_tds": None,
                "last_temperature": None,
                "timestamp": time.time(),
                "error": str(e)
            }
    
    def get_water_history(self, limit=100, days=None) -> List[Dict]:
        """
        Gibt die Wasserstandshistorie zurück.
        
        Args:
            limit: Maximale Anzahl zurückzugebender Einträge
            days: Anzahl der Tage zurück
            
        Returns:
            Liste mit Wasserstandsdaten
        """
        try:
            with _db_lock:
                session = get_session()
                query = session.query(WaterLevel).order_by(desc(WaterLevel.timestamp))
                
                if days:
                    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
                    query = query.filter(WaterLevel.timestamp >= since)
                
                records = query.limit(limit).all()
                
                return [{
                    "timestamp": record.timestamp.timestamp(),
                    "level": record.level,
                    "liters": record.liters
                } for record in records]
        except Exception as e:
            self.log_message(f"Fehler beim Abrufen der Wasserstandshistorie: {e}", level="error")
            return []
    
    def get_tds_history(self, limit=100, days=None) -> List[Dict]:
        """
        Gibt die TDS-Messwerthistorie zurück.
        
        Args:
            limit: Maximale Anzahl zurückzugebender Einträge
            days: Anzahl der Tage zurück
            
        Returns:
            Liste mit TDS-Daten
        """
        try:
            with _db_lock:
                session = get_session()
                query = session.query(TDSReading).order_by(desc(TDSReading.timestamp))
                
                if days:
                    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
                    query = query.filter(TDSReading.timestamp >= since)
                
                records = query.limit(limit).all()
                
                return [{
                    "timestamp": record.timestamp.timestamp(),
                    "value": record.value
                } for record in records]
        except Exception as e:
            self.log_message(f"Fehler beim Abrufen der TDS-Historie: {e}", level="error")
            return []
    
    def get_temperature_history(self, limit=100, days=None) -> List[Dict]:
        """
        Gibt die Temperatur-Messwerthistorie zurück.
        
        Args:
            limit: Maximale Anzahl zurückzugebender Einträge
            days: Anzahl der Tage zurück
            
        Returns:
            Liste mit Temperatur-Daten
        """
        try:
            with _db_lock:
                session = get_session()
                query = session.query(TemperatureReading).order_by(desc(TemperatureReading.timestamp))
                
                if days:
                    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
                    query = query.filter(TemperatureReading.timestamp >= since)
                
                records = query.limit(limit).all()
                
                return [{
                    "timestamp": record.timestamp.timestamp(),
                    "value": record.value
                } for record in records]
        except Exception as e:
            self.log_message(f"Fehler beim Abrufen der Temperatur-Historie: {e}", level="error")
            return []
    
    def get_spray_events(self, limit=50, days=None) -> List[Dict]:
        """
        Gibt die Sprühnebel-Ereignisse zurück.
        
        Args:
            limit: Maximale Anzahl zurückzugebender Einträge
            days: Anzahl der Tage zurück
            
        Returns:
            Liste mit Sprühnebel-Ereignissen
        """
        try:
            with _db_lock:
                session = get_session()
                query = session.query(SprayEvent).order_by(desc(SprayEvent.start_time))
                
                if days:
                    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
                    query = query.filter(SprayEvent.start_time >= since)
                
                records = query.limit(limit).all()
                
                return [{
                    "start_time": record.start_time.timestamp(),
                    "end_time": record.end_time.timestamp() if record.end_time else None,
                    "duration_seconds": record.duration_seconds,
                    "manual": record.manual,
                    "active": record.end_time is None
                } for record in records]
        except Exception as e:
            self.log_message(f"Fehler beim Abrufen der Sprühereignisse: {e}", level="error")
            return []
    
    def get_fill_events(self, limit=50, days=None) -> List[Dict]:
        """
        Gibt die Wasserzufuhr-Ereignisse zurück.
        
        Args:
            limit: Maximale Anzahl zurückzugebender Einträge
            days: Anzahl der Tage zurück
            
        Returns:
            Liste mit Wasserzufuhr-Ereignissen
        """
        try:
            with _db_lock:
                session = get_session()
                query = session.query(WaterFillEvent).order_by(desc(WaterFillEvent.start_time))
                
                if days:
                    since = datetime.datetime.utcnow() - datetime.timedelta(days=days)
                    query = query.filter(WaterFillEvent.start_time >= since)
                
                records = query.limit(limit).all()
                
                return [{
                    "start_time": record.start_time.timestamp(),
                    "end_time": record.end_time.timestamp() if record.end_time else None,
                    "duration_seconds": record.duration_seconds,
                    "target_level": record.target_level,
                    "target_liters": record.target_liters,
                    "actual_liters": record.actual_liters,
                    "manual": record.manual,
                    "active": record.end_time is None
                } for record in records]
        except Exception as e:
            self.log_message(f"Fehler beim Abrufen der Füllereignisse: {e}", level="error")
            return []
    
    def get_logs(self, limit=100, level=None) -> List[Dict]:
        """
        Gibt die Lognachrichten zurück.
        
        Args:
            limit: Maximale Anzahl zurückzugebender Einträge
            level: Optionales Log-Level zum Filtern
            
        Returns:
            Liste mit Lognachrichten
        """
        try:
            with _db_lock:
                session = get_session()
                query = session.query(ArduinoLog).order_by(desc(ArduinoLog.timestamp))
                
                if level:
                    query = query.filter(ArduinoLog.level == level)
                
                records = query.limit(limit).all()
                
                return [{
                    "timestamp": record.timestamp.timestamp(),
                    "level": record.level,
                    "message": record.message
                } for record in records]
        except Exception as e:
            print(f"Fehler beim Abrufen der Logs: {e}")
            return []


def get_db_handler() -> DbHandler:
    """
    Gibt die Singleton-Instanz des DbHandlers zurück.
    
    Returns:
        DbHandler-Instanz
    """
    global _DB_HANDLER_INSTANCE
    
    if _DB_HANDLER_INSTANCE is None:
        _DB_HANDLER_INSTANCE = DbHandler()
    
    return _DB_HANDLER_INSTANCE
