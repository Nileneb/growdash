"""
GrowDash Agent Bootstrap
========================
Onboarding-Wizard für neue Agents mit zwei Modi:
1. Pairing-Code-Flow (empfohlen, sicher)
2. Direct-Login-Flow (für Power-User/Dev)
"""

import os
import sys
import time
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
                    "Accept": "application/json",
                    "Content-Type": "application/json"
                },
                timeout=10
            )
            
            if response.status_code == 200:
                # Erfolgreich: erst Text NICHT ausgeben, direkt JSON parsen
                try:
                    data = response.json()
                except ValueError:
                    print("❌ Antwort kein gültiges JSON")
                    print(response.text[:500])
                    return None

                token = data.get("token") or data.get("access_token")
                if not token:
                    print("❌ Kein Token in Response")
                    print(data)
                    return None

                # Gültigkeits-Heuristik: Sanctum-Format id|hash
                if "|" not in token:
                    print("⚠️ Unerwartetes Token-Format (kein '|'). Weiter, aber Laravel-Konfiguration prüfen.")

                print("✅ Login erfolgreich")
                # Maskiertes Token zur Kontrolle (erste 8 Zeichen)
                masked = token.split('|')[0] + '|…' if '|' in token else token[:8] + '…'
                print(f"🔎 Erhaltenes User-Token: {masked}")
                return token

            # Typische Fehlerfälle differenziert behandeln
            if response.status_code in (401, 403):
                print(f"❌ Login verweigert ({response.status_code})")
                self._print_error_body(response)
                return None
            if response.status_code == 422:
                print("❌ Validierungsfehler (422)")
                self._print_error_body(response)
                return None
            if response.status_code >= 500:
                print(f"❌ Serverfehler ({response.status_code})")
                self._print_error_body(response)
                return None

            # Fallback für andere Codes
            print(f"❌ Unerwarteter Status {response.status_code}")
            self._print_error_body(response)
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
            import uuid
            
            # Bootstrap-ID generieren (Hardware-eindeutig)
            # In Production: MAC-Adresse, CPU-Serial etc. verwenden
            bootstrap_id = f"growdash-{socket.gethostname()}-{uuid.getnode():012x}"
            
            device_info = {
                "bootstrap_id": bootstrap_id,
                "name": device_name or f"GrowDash {socket.gethostname()}",
                "device_info": {
                    "platform": platform.system().lower(),
                    "version": "2.0",
                    "hostname": socket.gethostname(),
                }
            }
            # Debug-Ausgabe des Zielendpunkts & Header (teilmaskiert)
            masked_user_token = user_token.split('|')[0] + '|…' if '|' in user_token else user_token[:8] + '…'
            print(f"➡️ POST /api/growdash/devices/register mit Bearer {masked_user_token}")
            print(f"🆔 Bootstrap-ID: {bootstrap_id}")

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

            # Erfolgsfälle
            if response.status_code in (200, 201):
                ct = response.headers.get('Content-Type','')
                if 'application/json' not in ct.lower():
                    print(f"❌ Unerwarteter Content-Type '{ct}' bei Status {response.status_code} (erwartet JSON).")
                    self._print_error_body(response)
                    print("🔧 Wahrscheinlich liefert Laravel eine HTML-View statt API-JSON. Prüfe Route in routes/api.php und API-Controller.")
                    return None
                try:
                    data = response.json()
                except ValueError:
                    print("❌ Antwort kein gültiges JSON")
                    self._print_error_body(response)
                    return None

                device_id = data.get("device_id") or data.get("public_id")
                agent_token = data.get("agent_token") or data.get("token")
                if not device_id or not agent_token:
                    print("❌ Fehlende Werte in Erfolgs-Response")
                    print(data)
                    return None

                print("✅ Device registriert")
                print(f"   Device-ID: {device_id}")
                masked_agent = agent_token[:8] + '…'
                print(f"   Agent-Token: {masked_agent}")
                return device_id, agent_token

            # Fehlerszenarien differenziert
            if response.status_code in (401, 403):
                print(f"❌ Keine Berechtigung zur Registrierung ({response.status_code}). Prüfe User-Token oder auth:sanctum Middleware.")
                self._print_error_body(response)
                return None
            if response.status_code == 404:
                print("❌ Endpoint nicht gefunden (404). Wahrscheinlich fehlt Route oder Prefix stimmt nicht.")
                self._print_error_body(response)
                print("🔍 Erwartet laut Python: POST /api/growdash/devices/register unter Basis-URL", self.base_url)
                return None
            if response.status_code == 200:
                # Sonderfall: 200 aber kein JSON (meist HTML-Landing-Page)
                ct = response.headers.get('Content-Type','')
                if 'application/json' not in ct.lower():
                    print("❌ 200 OK aber HTML statt JSON – API-Route fehlt oder falsches Guard.")
                    print("   Prüfe: routes/api.php enthält innerhalb prefix('growdash')->middleware('auth:sanctum') die Zeile:")
                    print("   Route::post('/devices/register', [DeviceController::class, 'register']);")
                    print("   Und stelle sicher, dass kein Web-Route diesen Pfad überschreibt.")
                    self._print_error_body(response)
                    return None
            if response.status_code == 422:
                print("❌ Validierungsfehler (422) – Felder prüfen.")
                self._print_error_body(response)
                print("📦 Gesendeter Body:", device_info)
                print("💡 Laravel erwartet: bootstrap_id (required), name (optional), device_info (optional JSON)")
                return None
            if response.status_code >= 500:
                print(f"❌ Serverfehler ({response.status_code}) – Laravel Logs prüfen.")
                self._print_error_body(response)
                return None

            # Fallback
            print(f"❌ Unerwarteter Status {response.status_code}")
            self._print_error_body(response)
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

    def _print_error_body(self, response: requests.Response):
        """Hilfsfunktion: gib Fehler-Body (JSON oder Text) strukturiert aus."""
        body_printed = False
        try:
            data = response.json()
            print("🧪 Response JSON:")
            print(data)
            body_printed = True
        except ValueError:
            # Kein JSON – zeige ersten Teil des Textes
            pass
        if not body_printed:
            text = response.text
            if len(text) > 1000:
                text = text[:1000] + "… (gekürzt)"
            print("📄 Response Text:")
            print(text)
    
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
