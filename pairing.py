"""
GrowDash Device Pairing
=======================
Pairing-Prozess für neue Agents:
1. Agent ruft Laravel Bootstrap-Endpoint auf
2. Laravel generiert bootstrap_id + bootstrap_code
3. User gibt Code in Laravel-Web-UI ein
4. Agent erhält Token und speichert in .env
"""

import os
import time
import logging
import requests
import socket
import platform
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
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore'


class DevicePairing:
    """Verwaltet den Pairing-Prozess"""
    
    def __init__(self):
        self.config = PairingConfig()
        self.base_url = f"{self.config.laravel_base_url}/api/agents"
        self.env_file = Path(".env")
    
    def start_pairing(self) -> Tuple[str, str]:
        """
        Starte Pairing-Prozess.
        
        Returns:
            (bootstrap_id, bootstrap_code)
        """
        logger.info("🔄 Starte Bootstrap bei Laravel...")
        
        # Device-Info sammeln
        device_info = {
            "platform": platform.system().lower(),
            "version": "2.0",
            "hostname": socket.gethostname(),
        }
        
        # Bootstrap bei Laravel initiieren
        try:
            response = requests.post(
                f"{self.base_url}/bootstrap",
                json={"device_info": device_info},
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                bootstrap_id = data.get("bootstrap_id")
                bootstrap_code = data.get("bootstrap_code")
                
                if bootstrap_id and bootstrap_code:
                    logger.info("✅ Bootstrap erfolgreich")
                    return bootstrap_id, bootstrap_code
                else:
                    logger.error("❌ Fehlende Werte in Response")
                    logger.error(data)
                    raise Exception("Bootstrap-Response unvollständig")
            else:
                logger.error(f"❌ Bootstrap fehlgeschlagen: {response.status_code}")
                logger.error(response.text[:500] if response.text else "No response")
                raise Exception(f"Bootstrap fehlgeschlagen: {response.status_code}")
                
        except requests.exceptions.ConnectionError:
            logger.error("❌ Verbindung zu Laravel fehlgeschlagen")
            logger.error(f"URL: {self.config.laravel_base_url}")
            raise
        except Exception as e:
            logger.error(f"❌ Fehler beim Bootstrap: {e}")
            raise
    
    def poll_for_token(self, bootstrap_id: str, timeout: int = 300) -> Optional[Tuple[str, str]]:
        """
        Warte auf Pairing-Bestätigung und hole Token.
        
        Args:
            bootstrap_id: Bootstrap-ID von Laravel
            timeout: Max. Wartezeit in Sekunden (default: 5 Minuten)
            
        Returns:
            (device_id, agent_token) oder None bei Timeout
        """
        logger.info("⏳ Warte auf Pairing-Bestätigung...")
        logger.info(f"   Timeout: {timeout} Sekunden")
        
        start_time = time.time()
        poll_interval = 5  # Alle 5 Sekunden prüfen
        
        while time.time() - start_time < timeout:
            try:
                response = requests.get(
                    f"{self.base_url}/pairing/status",
                    params={"bootstrap_id": bootstrap_id},
                    headers={
                        "Accept": "application/json"
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if data.get("status") == "paired":
                        device_id = data.get("device_id")
                        agent_token = data.get("agent_token")
                        user_email = data.get("user_email", "Unbekannt")
                        
                        if device_id and agent_token:
                            logger.info("✅ Pairing erfolgreich!")
                            logger.info(f"   Verknüpft mit User: {user_email}")
                            logger.info(f"   Device-ID: {device_id}")
                            
                            return device_id, agent_token
                        else:
                            logger.error("❌ Fehlende Werte in Response")
                            return None
                    
                    elif data.get("status") == "pending":
                        # Noch nicht bestätigt
                        remaining = int(timeout - (time.time() - start_time))
                        print(f"\r⏳ Warte auf Bestätigung... ({remaining}s verbleibend)", end="", flush=True)
                    
                    elif data.get("status") == "expired":
                        logger.error("❌ Bootstrap-Code abgelaufen")
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
        
        try:
            # 1. Bootstrap initiieren (Laravel generiert Code)
            bootstrap_id, bootstrap_code = self.start_pairing()
        except Exception as e:
            logger.error("❌ Bootstrap fehlgeschlagen – manueller Fallback")
            # Manueller Fallback
            try:
                device_id = input("\nDevice-ID (manuell): ").strip()
                device_token = input("Device-Token (manuell): ").strip()
            except KeyboardInterrupt:
                print("\nAbgebrochen.")
                return False
            if device_id and device_token:
                self.save_to_env(device_id, device_token)
                print("\n✅ Credentials manuell gespeichert")
                return True
            print("❌ Keine Credentials eingegeben")
            return False
        
        # 2. Code anzeigen
        print()
        print("╔════════════════════════════════════════════════════════╗")
        print("║                                                        ║")
        print(f"║    Dein Pairing-Code:  {bootstrap_code}                         ║")
        print("║                                                        ║")
        print("╚════════════════════════════════════════════════════════╝")
        print()
        print(f"📱 Gehe zu: {self.config.laravel_base_url}/devices/pair")
        print(f"🔢 Gib den Code ein: {bootstrap_code}")
        print()
        
        # 3. Auf Bestätigung warten
        result = self.poll_for_token(bootstrap_id, timeout)
        
        if result:
            device_id, agent_token = result
            # 4. In .env speichern
            self.save_to_env(device_id, agent_token)
            
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
