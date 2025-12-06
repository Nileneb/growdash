"""
GrowDash Agent Bootstrap
========================
Onboarding-Wizard für neue Agents mit zwei Modi:
1. Pairing-Code-Flow (empfohlen, sicher)
2. Direct-Login-Flow (für Power-User/Dev)
"""

import os
import sys
import getpass
from pathlib import Path
from typing import Optional, Tuple

import requests
from pydantic_settings import BaseSettings
from pydantic import Field

# Lokale Imports
from pairing import DevicePairing


class BootstrapConfig(BaseSettings):
    """Minimale Config für Bootstrap"""
    laravel_base_url: str = Field(default="https://grow.linn.games")
    laravel_api_path: str = Field(default="/api/growdash/agent")
    
    class Config:
        env_file = ".env"
        env_file_encoding = 'utf-8'
        extra = 'ignore'


class DirectLogin:
    """Direct-Login-Flow für Power-User"""
    
    def __init__(self):
        self.config = BootstrapConfig()
        self.base_url = self.config.laravel_base_url
        self.env_file = Path(".env")
    
    def login_user(self, email: str, password: str) -> Optional[str]:
        """
        User-Login via email+password.
        
        Returns:
            Bearer-Token oder None bei Fehler
        """
        print("🔐 Authentifiziere User...")
        
        try:
            response = requests.post(
                f"{self.base_url}/api/auth/login",
                json={
                    "email": email,
                    "password": password
                },
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                token = data.get("token") or data.get("access_token")
                
                if token:
                    print("✅ Login erfolgreich")
                    return token
                else:
                    print("❌ Kein Token in Response")
                    return None
            
            elif response.status_code == 401:
                print("❌ Login fehlgeschlagen: Falsche Credentials")
                return None
            
            else:
                print(f"❌ Login fehlgeschlagen: {response.status_code}")
                if response.text:
                    print(response.text[:500])
                return None
                
        except requests.exceptions.ConnectionError:
            print(f"❌ Verbindung zu {self.base_url} fehlgeschlagen")
            return None
        except Exception as e:
            print(f"❌ Fehler beim Login: {e}")
            return None
    
    def register_device(self, user_token: str, device_name: str = None) -> Optional[Tuple[str, str]]:
        """
        Registriere Device mit User-Token.
        
        Args:
            user_token: Bearer-Token vom User-Login
            device_name: Optional device name
            
        Returns:
            (device_public_id, agent_token) oder None
        """
        print("📱 Registriere Device...")
        
        try:
            # Device-Info sammeln
            import socket
            import platform
            
            device_info = {
                "name": device_name or f"GrowDash {socket.gethostname()}",
                "platform": platform.system().lower(),
                "version": "2.0",
                "hostname": socket.gethostname(),
            }
            
            response = requests.post(
                f"{self.base_url}/api/growdash/devices/register",
                json=device_info,
                headers={
                    "Authorization": f"Bearer {user_token}",
                    "Content-Type": "application/json",
                    "Accept": "application/json"
                },
                timeout=10
            )
            
            if response.status_code in [200, 201]:
                data = response.json()
                
                device_id = data.get("device_id") or data.get("public_id")
                agent_token = data.get("agent_token") or data.get("token")
                
                if device_id and agent_token:
                    print("✅ Device registriert")
                    print(f"   Device-ID: {device_id}")
                    return device_id, agent_token
                else:
                    print("❌ Fehlende Werte in Response")
                    print(data)
                    return None
            
            else:
                print(f"❌ Registrierung fehlgeschlagen: {response.status_code}")
                print(response.text[:500] if response.text else "")
                return None
                
        except Exception as e:
            print(f"❌ Fehler bei Registrierung: {e}")
            return None
    
    def revoke_user_token(self, user_token: str):
        """
        Revoke User-Token nach erfolgreicher Device-Registrierung.
        
        Sicherheits-Best-Practice: User-Token nicht auf Device belassen!
        """
        try:
            requests.post(
                f"{self.base_url}/api/auth/logout",
                headers={"Authorization": f"Bearer {user_token}"},
                timeout=5
            )
            print("🔒 User-Token revoked (Sicherheit)")
        except Exception:
            pass  # Nicht kritisch
    
    def save_to_env(self, device_id: str, agent_token: str):
        """Speichere Device-Credentials in .env"""
        print("💾 Speichere Credentials in .env...")
        
        # .env lesen
        if self.env_file.exists():
            with open(self.env_file, 'r') as f:
                lines = f.readlines()
        else:
            lines = []
        
        # Device-ID und Token setzen
        new_lines = []
        device_id_set = False
        token_set = False
        
        for line in lines:
            if line.startswith("DEVICE_PUBLIC_ID="):
                new_lines.append(f"DEVICE_PUBLIC_ID={device_id}\n")
                device_id_set = True
            elif line.startswith("DEVICE_TOKEN="):
                new_lines.append(f"DEVICE_TOKEN={agent_token}\n")
                token_set = True
            else:
                new_lines.append(line)
        
        if not device_id_set:
            new_lines.append(f"\nDEVICE_PUBLIC_ID={device_id}\n")
        if not token_set:
            new_lines.append(f"DEVICE_TOKEN={agent_token}\n")
        
        # Speichern
        with open(self.env_file, 'w') as f:
            f.writelines(new_lines)
        
        print("✅ Credentials gespeichert")
    
    def run(self):
        """Führe Direct-Login-Flow durch"""
        print("\n" + "="*60)
        print("🔐 Direct Login - Device Registration")
        print("="*60)
        print()
        print("⚠️  WICHTIG: Email & Passwort werden NICHT gespeichert!")
        print("   Nur Device-Token wird in .env geschrieben.")
        print()
        
        # 1. Email & Passwort abfragen
        try:
            email = input("📧 Email: ").strip()
            password = getpass.getpass("🔑 Passwort: ")
            
            if not email or not password:
                print("\n❌ Email und Passwort erforderlich")
                return False
            
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            return False
        
        print()
        
        # 2. User-Login
        user_token = self.login_user(email, password)
        
        # Credentials sofort aus dem Speicher löschen
        email = None
        password = None
        
        if not user_token:
            print("\n❌ Login fehlgeschlagen")
            # Manueller Fallback
            try:
                device_id = input("Device-ID (manuell): ").strip()
                device_token = input("Device-Token (manuell): ").strip()
            except KeyboardInterrupt:
                print("\nAbgebrochen.")
                return False
            if device_id and device_token:
                self.save_to_env(device_id, device_token)
                print("\n✅ Credentials manuell gespeichert")
                return True
            return False
        
        print()
        
        # 3. Device-Name optional
        device_name = input("📱 Device-Name (Enter für Auto): ").strip() or None
        print()
        
        # 4. Device registrieren
        result = self.register_device(user_token, device_name)
        
        if not result:
            print("\n❌ Device-Registrierung fehlgeschlagen")
            # User-Token trotzdem revoken
            self.revoke_user_token(user_token)
            # Manueller Fallback
            try:
                device_id = input("Device-ID (manuell): ").strip()
                device_token = input("Device-Token (manuell): ").strip()
            except KeyboardInterrupt:
                print("\nAbgebrochen.")
                return False
            if device_id and device_token:
                self.save_to_env(device_id, device_token)
                print("\n✅ Credentials manuell gespeichert")
                return True
            return False
        
        device_id, agent_token = result
        
        # 5. User-Token sofort revoken (Sicherheit!)
        self.revoke_user_token(user_token)
        user_token = None  # Aus Speicher löschen
        
        print()
        
        # 6. In .env speichern
        self.save_to_env(device_id, agent_token)
        
        print()
        print("="*60)
        print("✅ Device registriert und verknüpft!")
        print("="*60)
        print()
        print(f"Device-ID: {device_id}")
        print()
        print("Nächster Schritt: Agent starten")
        print("  ./grow_start.sh")
        print()
        
        return True


class OnboardingWizard:
    """Haupt-Wizard für Agent-Onboarding"""
    
    def __init__(self):
        self.env_file = Path(".env")
    
    def check_already_configured(self) -> bool:
        """Prüfe, ob Device bereits konfiguriert ist"""
        if not self.env_file.exists():
            return False
        
        with open(self.env_file, 'r') as f:
            content = f.read()
        
        has_device_id = "DEVICE_PUBLIC_ID=" in content and \
                       not content.startswith("DEVICE_PUBLIC_ID=\n") and \
                       not "DEVICE_PUBLIC_ID=\n" in content
        
        has_token = "DEVICE_TOKEN=" in content and \
                   not content.startswith("DEVICE_TOKEN=\n") and \
                   not "DEVICE_TOKEN=\n" in content
        
        return has_device_id and has_token
    
    def show_welcome(self):
        """Zeige Welcome-Screen"""
        print("\n" + "="*60)
        print("🌱 GrowDash Agent - Ersteinrichtung")
        print("="*60)
        print()
        print("Wähle einen Onboarding-Modus:")
        print()
        print("1) 🔢 Pairing-Code (Empfohlen)")
        print("   → Agent generiert 6-stelligen Code")
        print("   → Du gibst ihn in der Web-UI ein")
        print("   → Sicher & einfach")
        print()
        print("2) 🔐 Direct Login (Advanced)")
        print("   → Login mit Email & Passwort")
        print("   → Device wird automatisch registriert")
        print("   → Schnell für Power-User/Dev")
        print()
        print("3) ❌ Abbrechen")
        print()
    
    def run(self):
        """Führe Onboarding-Wizard durch"""
        # Prüfen ob bereits konfiguriert
        if self.check_already_configured():
            print("\n✅ Device ist bereits konfiguriert!")
            print()
            print("Wenn du neu pairen willst:")
            print("  1. Leere DEVICE_PUBLIC_ID und DEVICE_TOKEN in .env")
            print("  2. Starte bootstrap.py erneut")
            print()
            print("Oder starte direkt den Agent:")
            print("  ./grow_start.sh")
            print()
            return
        
        # Welcome-Screen
        self.show_welcome()
        
        # Auswahl
        try:
            choice = input("Auswahl (1-3): ").strip()
        except KeyboardInterrupt:
            print("\n\nAbgebrochen.")
            return
        
        if choice == "1":
            # Pairing-Code-Flow
            print()
            pairing = DevicePairing()
            pairing.run(timeout=300)
        
        elif choice == "2":
            # Direct-Login-Flow
            print()
            direct_login = DirectLogin()
            direct_login.run()
        
        elif choice == "3":
            print("\nAbgebrochen.")
        
        else:
            print("\n❌ Ungültige Auswahl")


def main():
    """Hauptfunktion"""
    wizard = OnboardingWizard()
    wizard.run()


if __name__ == "__main__":
    main()
