# Agent Konfiguration - Quick Start

## 🚀 Ersteinrichtung - Onboarding Wizard

### Starte den Wizard:

```bash
cd ~/growdash
source .venv/bin/activate
python bootstrap.py
```

### Wähle deinen Onboarding-Modus:

```
🌱 GrowDash Agent - Ersteinrichtung
====================================

Wähle einen Onboarding-Modus:

1) 🔢 Pairing-Code (Empfohlen)
   → Agent generiert 6-stelligen Code
   → Du gibst ihn in der Web-UI ein
   → Sicher & einfach

2) 🔐 Direct Login (Advanced)
   → Login mit Email & Passwort
   → Device wird automatisch registriert
   → Schnell für Power-User/Dev

3) ❌ Abbrechen

Auswahl (1-3):
```

---

## Option 1: 🔢 Pairing-Code-Flow (Empfohlen)

### 1. Wähle Option "1"

Der Agent generiert einen **6-stelligen Code**:

```
╔════════════════════════════════════════════════════════╗
║                                                        ║
║    Dein Pairing-Code:  123456                         ║
║                                                        ║
╚════════════════════════════════════════════════════════╝

📱 Gehe zu: https://grow.linn.games/devices/pair
🔢 Gib den Code ein: 123456
🆔 Device-ID: growdash-a1b2

⏳ Warte auf Pairing-Bestätigung... (300s verbleibend)
```

### 2. In Laravel-Web-UI pairen

1. Öffne: **https://grow.linn.games/devices/pair**
2. Logge dich mit deinem User-Account ein
3. Gib den Pairing-Code ein: `123456`
4. Bestätige das Pairing

### 3. Automatische Konfiguration

```
✅ Pairing erfolgreich!
   Verknüpft mit User: deine@email.de
💾 Speichere Credentials in .env...
✅ Credentials gespeichert
```

---

## Option 2: 🔐 Direct-Login-Flow (Power-User)

### 1. Wähle Option "2"

Der Agent fragt nach deinen Laravel-Credentials:

```
🔐 Direct Login - Device Registration
======================================

⚠️  WICHTIG: Email & Passwort werden NICHT gespeichert!
   Nur Device-Token wird in .env geschrieben.

📧 Email: user@example.com
🔑 Passwort: ********
```

### 2. Automatische Registrierung

```
🔐 Authentifiziere User...
✅ Login erfolgreich

📱 Device-Name (Enter für Auto): Kitchen Pi

📱 Registriere Device...
✅ Device registriert
   Device-ID: growdash-a1b2
🔒 User-Token revoked (Sicherheit)

💾 Speichere Credentials in .env...
✅ Credentials gespeichert

====================================
✅ Device registriert und verknüpft!
====================================

Device-ID: growdash-a1b2
```

### ⚠️ Sicherheit

- **Email & Passwort** werden NICHT gespeichert
- **User-Token** wird sofort nach Registrierung revoked
- Nur **Device-Token** (minimale Rechte) bleibt in `.env`

---

## 🎯 Agent starten

Nach erfolgreichem Onboarding (egal welcher Modus):

```bash
./grow_start.sh
```

**Das war's!** 🎉

---

## 🔧 Ersteinrichtung: Device Pairing (Legacy - wird durch bootstrap.py ersetzt)

```bash
cp .env.example .env
nano .env
```

Setze diese Werte:

```env
# Production Laravel-Backend
LARAVEL_BASE_URL=https://grow.linn.games
LARAVEL_API_PATH=/api/growdash/agent

# Device-Credentials (aus Laravel-DB)
DEVICE_PUBLIC_ID=dein-device-public-id-hier
DEVICE_TOKEN=dein-klartext-token-hier

# Hardware
SERIAL_PORT=/dev/ttyACM0
BAUD_RATE=9600
```

## 2. Device-Credentials erhalten

Die Werte für `DEVICE_PUBLIC_ID` und `DEVICE_TOKEN` kommen aus deiner Laravel-Installation:

### Option A: Aus Laravel-DB
```sql
SELECT public_id FROM devices WHERE id = 1;
```

Der `DEVICE_TOKEN` ist der **Klartext-Token** aus dem Pairing-Prozess.  
⚠️ In der DB liegt nur der Hash (`agent_token`), nicht der Klartext!

### Option B: Via Laravel-Artisan
```bash
php artisan growdash:pair-device
```

## 3. Verbindung testen

```bash
cd ~/growdash
source .venv/bin/activate

# Env-Vars laden
export $(grep -v '^#' .env | xargs)

# Laravel-Route testen
curl -k -v \
  -H "X-Device-ID: $DEVICE_PUBLIC_ID" \
  -H "X-Device-Token: $DEVICE_TOKEN" \
  "$LARAVEL_BASE_URL$LARAVEL_API_PATH/commands/pending"
```

### Erwartete Responses:

**✅ OK (200):**
```json
{"success": true, "commands": []}
```

**❌ 404 - Route nicht gefunden:**
```
Prüfe in Laravel: routes/api.php
Route::prefix('growdash/agent')->group(...)
```

**❌ 401/403 - Auth fehlgeschlagen:**
```
Device-Token oder Public-ID stimmen nicht mit DB überein
```

## 4. Agent starten

```bash
./grow_start.sh
```

### Erwartete Log-Ausgabe:

```
2025-12-01 22:00:00 - INFO - Verbunden mit /dev/ttyACM0 @ 9600 baud
2025-12-01 22:00:00 - INFO - Agent gestartet für Device: dein-device-id
2025-12-01 22:00:00 - INFO - Laravel Backend: https://grow.linn.games/api/growdash/agent
2025-12-01 22:00:00 - INFO - Führe Startup-Health-Check durch...
2025-12-01 22:00:01 - INFO - ✅ Laravel-Backend erreichbar und Auth erfolgreich
2025-12-01 22:00:01 - INFO - Agent läuft... (Strg+C zum Beenden)
```

### Bei Problemen:

**Serial-Port nicht gefunden:**
```bash
ls -l /dev/ttyACM* /dev/ttyUSB*
sudo usermod -a -G dialout $USER
# Neu einloggen
```

**Laravel 404:**
```
❌ Laravel-Route nicht gefunden (404)
URL: https://grow.linn.games/api/growdash/agent/commands/pending
Prüfe routes/api.php in Laravel: Route::prefix('growdash/agent')
```

**Auth fehlgeschlagen:**
```
❌ Auth fehlgeschlagen (401/403)
Device-Token oder Public-ID stimmen nicht mit Laravel-DB überein
Device-ID: dein-device-id
```

## 5. Optional: Local Debug API

Für manuelle Tests:

```bash
python local_api.py
```

Dann: http://127.0.0.1:8000/docs

## Hinweise

- **Keine Kommentare in Werten:** In .env keine `#` nach Werten
- **Keine Leerzeichen:** `DEVICE_TOKEN=abc123` (nicht `DEVICE_TOKEN = abc123`)
- **Extra Keys ignoriert:** Alte Keys wie `bootstrap_id` werden ignoriert
- **Arduino-CLI optional:** Warnung kann ignoriert werden, wenn Firmware-Updates nicht genutzt werden
