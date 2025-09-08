"""
GrowDash SQLite-Datenbankmodell
-------------------------------
Enthält die Datenbankmodelle für die Speicherung von Sensordaten und Statusupdates.
"""

from sqlalchemy import create_engine, Column, Integer, Float, Boolean, String, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os
import datetime

# Basispfad für die Datenbankdatei
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'data', 'growdash.db')

# Stellen Sie sicher, dass das Verzeichnis existiert
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# Datenbankverbindung
engine = create_engine(f'sqlite:///{DB_PATH}')
session_factory = sessionmaker(bind=engine)
Session = scoped_session(session_factory)

Base = declarative_base()

class WaterLevel(Base):
    """Speichert Wasserstands-Messungen."""
    __tablename__ = 'water_levels'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    level = Column(Float, nullable=False)  # Wasserstand in Prozent (0-100)
    liters = Column(Float)  # Wasserstand in Liter (berechnet)
    
    def __repr__(self):
        return f"<WaterLevel(timestamp={self.timestamp}, level={self.level}%, liters={self.liters})>"

class TDSReading(Base):
    """Speichert TDS-Messungen (Total Dissolved Solids)."""
    __tablename__ = 'tds_readings'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    value = Column(Float, nullable=False)  # TDS-Wert in ppm
    
    def __repr__(self):
        return f"<TDSReading(timestamp={self.timestamp}, value={self.value} ppm)>"

class TemperatureReading(Base):
    """Speichert Temperatur-Messungen."""
    __tablename__ = 'temperature_readings'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    value = Column(Float, nullable=False)  # Temperatur in °C
    
    def __repr__(self):
        return f"<TemperatureReading(timestamp={self.timestamp}, value={self.value}°C)>"

class SprayEvent(Base):
    """Speichert Sprühnebel-Aktivitäten."""
    __tablename__ = 'spray_events'
    
    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, nullable=False, index=True)  # Startzeitpunkt
    end_time = Column(DateTime)  # Endzeitpunkt (NULL wenn noch aktiv)
    duration_seconds = Column(Integer)  # Dauer in Sekunden (berechnet)
    manual = Column(Boolean, default=True)  # Manuell ausgelöst oder automatisch
    
    def __repr__(self):
        status = "aktiv" if self.end_time is None else "beendet"
        return f"<SprayEvent(start={self.start_time}, status={status}, duration={self.duration_seconds}s)>"

class WaterFillEvent(Base):
    """Speichert Wasserzufuhr-Aktivitäten."""
    __tablename__ = 'fill_events'
    
    id = Column(Integer, primary_key=True)
    start_time = Column(DateTime, nullable=False, index=True)  # Startzeitpunkt
    end_time = Column(DateTime)  # Endzeitpunkt (NULL wenn noch aktiv)
    duration_seconds = Column(Integer)  # Dauer in Sekunden (berechnet)
    target_level = Column(Float)  # Ziel-Füllstand in Prozent (optional)
    target_liters = Column(Float)  # Ziel-Füllstand in Litern (optional)
    actual_liters = Column(Float)  # Tatsächlich hinzugefügte Liter (berechnet)
    manual = Column(Boolean, default=True)  # Manuell ausgelöst oder automatisch
    
    def __repr__(self):
        status = "aktiv" if self.end_time is None else "beendet"
        return f"<WaterFillEvent(start={self.start_time}, status={status}, duration={self.duration_seconds}s)>"

class SystemStatus(Base):
    """Speichert den aktuellen Systemstatus."""
    __tablename__ = 'system_status'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    water_level = Column(Float)  # Aktueller Wasserstand in Prozent
    water_liters = Column(Float)  # Aktueller Wasserstand in Liter
    spray_active = Column(Boolean, default=False)
    filling_active = Column(Boolean, default=False)
    last_tds = Column(Float)  # Letzter TDS-Messwert
    last_temperature = Column(Float)  # Letzte Temperatur
    
    def __repr__(self):
        return f"<SystemStatus(timestamp={self.timestamp}, water_level={self.water_level}%)>"

class ArduinoLog(Base):
    """Speichert Lognachrichten vom Arduino."""
    __tablename__ = 'arduino_logs'
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, index=True)
    message = Column(String, nullable=False)  # Log-Nachricht
    level = Column(String, default="info")  # Log-Level (info, warning, error)
    
    def __repr__(self):
        return f"<ArduinoLog(timestamp={self.timestamp}, level={self.level}, message={self.message})>"

# Tabellen erstellen, falls sie nicht existieren
def init_db():
    Base.metadata.create_all(engine)
    
def get_session():
    return Session()
