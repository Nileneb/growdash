"""
GrowDash Device Pairing
=======================
Pairing-Prozess für neue Agents:
1. Agent generiert Device-ID und Pairing-Code
2. User gibt Code in Laravel-Web-UI ein
3. Agent erhält Token und speichert in .env
"""

import os
import time
import random
import string
import uuid
import logging
import requests
from pathlib import Path
from typing import Optional, Tuple

from pydantic_settings import BaseSettings
from pydantic import Field

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class PairingConfig(BaseSettings):
    """Minimale Config für Pairing"""
    laravel_base_url: str = Field(default="https://grow.linn.games")
    laravel_api_path: str = Field(default="/api/growdash/agent")
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore'


class DevicePairing:
    """Verwaltet den Pairing-Prozess"""
    
    def __init__(self):
        self.config = PairingConfig()
        self.base_url = f"{self.config.laravel_base_url}{self.config.laravel_api_path}"
        self.env_file = Path(".env")
        
    def generate_device_id(self) -> str:
        """Generiere eindeutige Device-ID"""
        # Format: growdash-XXXX (4 zufällige Zeichen)
        suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
        return f"growdash-{suffix}"
    
    def generate_pairing_code(self) -> str:
        """Generiere 6-stelligen Pairing-Code"""
        return ''.join(random.choices(string.digits, k=6))
    
    def start_pairing(self) -> Tuple[str, str]:
        """
        Starte Pairing-Prozess.
        
        Returns:
            (device_id, pairing_code)
        """
        device_id = self.generate_device_id()
        pairing_code = self.generate_pairing_code()
        
        logger.info("🔄 Starte Pairing-Prozess...")
        
        # Pairing bei Laravel initiieren
        try:
            response = requests.post(
                f"{self.base_url}/pairing/init",
                json={
                    "device_id": device_id,
                    "pairing_code": pairing_code,
                    "device_info": {
                        "platform": "raspberry-pi",
                        "version": "2.0"
                    }
                },
                timeout=10
            )
            
            if response.status_code == 201:
                logger.info("✅ Pairing initiiert")
                return device_id, pairing_code
            else:
                logger.error(f"❌ Pairing-Init fehlgeschlagen: {response.status_code}")
                logger.error(response.text)
                raise Exception(f"Pairing-Init fehlgeschlagen: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ Verbindung zu Laravel fehlgeschlagen")
            logger.error(f"URL: {self.config.laravel_base_url}")
            raise
        except Exception as e:
            logger.error(f"❌ Fehler beim Pairing-Init: {e}")
            raise
    
    def poll_for_token(self, device_id: str, pairing_code: str, timeout: int = 300) -> Optional[str]:
        """
        Warte auf Pairing-Bestätigung und hole Token.
        
        Args:
            device_id: Device-ID
            pairing_code: Pairing-Code
            timeout: Max. Wartezeit in Sekunden (default: 5 Minuten)
            
        Returns:
            Agent-Token oder None bei Timeout
        """
        logger.info("⏳ Warte auf Pairing-Bestätigung...")
        logger.info(f"   Timeout: {timeout} Sekunden")
        
        start_time = time.time()
        poll_interval = 5  # Alle 5 Sekunden prüfen
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/pairing/status",
                    params={
                        "device_id": device_id,
                        "pairing_code": pairing_code
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "paired":
                        token = data.get("agent_token")
                        user_email = data.get("user_email", "Unbekannt")
                        
                        logger.info("✅ Pairing erfolgreich!")
                        logger.info(f"   Verknüpft mit User: {user_email}")
                        
                        return token
                    
                    elif data.get("status") == "pending":
                        # Noch nicht bestätigt
                        remaining = int(timeout - (time.time() - start_time))
                        print(f"\r⏳ Warte auf Bestätigung... ({remaining}s verbleibend)", end="", flush=True)
                    
                    elif data.get("status") == "expired":
                        logger.error("❌ Pairing-Code abgelaufen")
                        return None
                    
                    elif data.get("status") == "rejected":
                        logger.error("❌ Pairing wurde abgelehnt")
                        return None
                
                time.sleep(poll_interval)
                
            except Exception as e:
                logger.error(f"\n❌ Fehler beim Polling: {e}")
                time.sleep(poll_interval)
        
        logger.error("\n❌ Pairing-Timeout - keine Bestätigung erhalten")
        return None
    
    def save_to_env(self, device_id: str, token: str):
        """
        Speichere Device-ID und Token in .env
        
        Args:
            device_id: Device-ID
            token: Agent-Token
        """
        logger.info("💾 Speichere Credentials in .env...")
        
        # .env lesen
        if self.env_file.exists():
            with open(self.env_file, 'r') as f:
                lines = f.readlines()
        else:
            lines = []
        
        # Device-ID und Token setzen/ersetzen
        new_lines = []
        device_id_set = False
        token_set = False
        
        for line in lines:
            if line.startswith("DEVICE_PUBLIC_ID="):
                new_lines.append(f"DEVICE_PUBLIC_ID={device_id}\n")
                device_id_set = True
            elif line.startswith("DEVICE_TOKEN="):
                new_lines.append(f"DEVICE_TOKEN={token}\n")
                token_set = True
            else:
                new_lines.append(line)
        
        # Falls nicht vorhanden, hinzufügen
        if not device_id_set:
            new_lines.append(f"\nDEVICE_PUBLIC_ID={device_id}\n")
        if not token_set:
            new_lines.append(f"DEVICE_TOKEN={token}\n")
        
        # Speichern
        with open(self.env_file, 'w') as f:
            f.writelines(new_lines)
        
        logger.info("✅ Credentials gespeichert")
    
    def run(self, timeout: int = 300):
        """
        Führe kompletten Pairing-Prozess durch.
        
        Args:
            timeout: Max. Wartezeit in Sekunden (default: 5 Minuten)
        """
        print("\n" + "="*60)
        print("🔗 GrowDash Device Pairing")
        print("="*60)
        print()
        
        # 1. Pairing initiieren
        device_id, pairing_code = self.start_pairing()
        
        # 2. Code anzeigen
        print()
        print("╔════════════════════════════════════════════════════════╗")
        print("║                                                        ║")
        print(f"║    Dein Pairing-Code:  {pairing_code}                         ║")
        print("║                                                        ║")
        print("╚════════════════════════════════════════════════════════╝")
        print()
        print(f"📱 Gehe zu: {self.config.laravel_base_url}/devices/pair")
        print(f"🔢 Gib den Code ein: {pairing_code}")
        print(f"🆔 Device-ID: {device_id}")
        print()
        
        # 3. Auf Bestätigung warten
        token = self.poll_for_token(device_id, pairing_code, timeout)
        
        if token:
            # 4. In .env speichern
            self.save_to_env(device_id, token)
            
            print()
            print("="*60)
            print("✅ Pairing abgeschlossen!")
            print("="*60)
            print()
            print("Nächster Schritt: Agent starten")
            print("  ./grow_start.sh")
            print()
            return True
        else:
            print()
            print("="*60)
            print("❌ Pairing fehlgeschlagen")
            print("="*60)
            print()
            print("Bitte erneut versuchen:")
            print("  python pairing.py")
            print()
            return False


def main():
    """Hauptfunktion"""
    pairing = DevicePairing()
    
    # Prüfen, ob bereits gepairt
    if os.getenv("DEVICE_PUBLIC_ID") and os.getenv("DEVICE_TOKEN"):
        print("\n⚠️  Device scheint bereits gepairt zu sein.")
        print(f"   Device-ID: {os.getenv('DEVICE_PUBLIC_ID')}")
        print()
        response = input("Erneut pairen? (j/n): ")
        if response.lower() not in ['j', 'y', 'ja', 'yes']:
            print("Abgebrochen.")
            return
    
    # Pairing durchführen
    success = pairing.run(timeout=300)
    
    if success:
        exit(0)
    else:
        exit(1)


if __name__ == "__main__":
    main()
