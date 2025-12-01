# 🔗 GrowDash Pairing-Flow

## Problemstellung

**Frage:** Wie weiß Laravel, welchem User der Agent zugeordnet werden muss?

**Antwort:** Via **Device-Pairing** mit 6-stelligem Code!

---

## 🔄 Ablauf

```
┌─────────────┐                              ┌──────────────┐
│   Agent     │                              │   Laravel    │
│ (Raspberry) │                              │  (Backend)   │
└──────┬──────┘                              └──────┬───────┘
       │                                            │
       │ 1. python pairing.py                       │
       ├────────────────────────────────────────────┤
       │                                            │
       │ 2. POST /pairing/init                      │
       │    {device_id, pairing_code}               │
       ├───────────────────────────────────────────>│
       │                                            │
       │ 3. 201 Created                             │
       │<───────────────────────────────────────────┤
       │                                            │
       │ ╔════════════════════════════╗             │
       │ ║  Code: 123456             ║             │
       │ ╚════════════════════════════╝             │
       │                                            │
       │ 4. Polling: GET /pairing/status            │
       │    ?device_id=xxx&pairing_code=123456      │
       ├───────────────────────────────────────────>│
       │                                            │
       │ 5. {status: "pending"}                     │
       │<───────────────────────────────────────────┤
       │                                            │
       │    (wartet...)                             │
       │                                            │
       
┌──────┴──────┐                              
│    User     │                              
│  (Browser)  │                              
└──────┬──────┘                              
       │                                            │
       │ 6. Login auf grow.linn.games               │
       │    Geht zu: /devices/pair                  │
       │    Gibt Code ein: 123456                   │
       │                                            │
       │ 7. POST /devices/pair                      │
       │    {pairing_code: "123456"}                │
       ├───────────────────────────────────────────>│
       │                                            │
       │                                         ┌──┴──┐
       │                                         │ DB  │
       │                                         │     │
       │                                         │ • Device erstellen
       │                                         │ • Token generieren
       │                                         │ • user_id verknüpfen
       │                                         └──┬──┘
       │                                            │
       │ 8. {success: true, device_id: xxx}         │
       │<───────────────────────────────────────────┤
       │                                            │
       
┌──────┴──────┐                              
│   Agent     │                              
└──────┬──────┘                              
       │                                            │
       │ 9. Nächster Poll: GET /pairing/status      │
       ├───────────────────────────────────────────>│
       │                                            │
       │ 10. {status: "paired",                     │
       │      agent_token: "xxx",                   │
       │      user_email: "user@example.com"}       │
       │<───────────────────────────────────────────┤
       │                                            │
       │ 11. Token in .env speichern                │
       │     ✅ Pairing abgeschlossen!              │
       │                                            │
       │ 12. ./grow_start.sh                        │
       │                                            │
       │ 13. POST /telemetry                        │
       │     Header: X-Device-Token: xxx            │
       ├───────────────────────────────────────────>│
       │                                            │
       │                                         ┌──┴──┐
       │                                         │ DB  │
       │                                         │     │
       │                                         │ Daten werden
       │                                         │ user_id zugeordnet
       │                                         └─────┘
```

---

## 📝 Schritt-für-Schritt

### Agent-Seite (Raspberry Pi):

1. **Pairing starten**
   ```bash
   python pairing.py
   ```

2. **Code generieren**
   - Agent generiert eindeutige Device-ID: `growdash-a1b2`
   - Agent generiert 6-stelligen Code: `123456`

3. **An Laravel senden**
   - POST zu `/api/growdash/agent/pairing/init`

4. **Code anzeigen**
   ```
   ╔════════════════════════════════════╗
   ║  Dein Code: 123456                ║
   ╚════════════════════════════════════╝
   Gehe zu: https://grow.linn.games/devices/pair
   ```

5. **Polling starten**
   - Alle 5 Sekunden GET `/pairing/status` 
   - Max. 5 Minuten warten

### User-Seite (Browser):

6. **Einloggen**
   - User loggt sich auf `grow.linn.games` ein

7. **Pairing-Seite öffnen**
   - Geht zu `/devices/pair`

8. **Code eingeben**
   - Gibt `123456` ein
   - Klickt "Pairen"

9. **Laravel-Backend**
   - Erstellt Device-Eintrag in DB
   - Verknüpft mit `user_id`
   - Generiert Token: `abc123xyz...`
   - Speichert Hash in DB: `Hash::make($token)`

### Agent-Seite (Fortsetzung):

10. **Pairing erkannt**
    - Polling erhält: `{status: "paired", agent_token: "abc123xyz..."}`

11. **Token speichern**
    - Schreibt in `.env`:
      ```env
      DEVICE_PUBLIC_ID=growdash-a1b2
      DEVICE_TOKEN=abc123xyz...
      ```

12. **Agent starten**
    ```bash
    ./grow_start.sh
    ```

13. **Authentifizierte Requests**
    - Alle Requests tragen Header:
      ```
      X-Device-ID: growdash-a1b2
      X-Device-Token: abc123xyz...
      ```
    - Laravel prüft: `Hash::check($token, $device->agent_token)`
    - Daten werden `user_id` zugeordnet ✅

---

## 🔒 Sicherheit

### Token-Handling

**Agent (Raspberry Pi):**
- Speichert **Klartext-Token** in `.env`
- Sendet Token bei jedem Request im Header

**Laravel (Backend):**
- Speichert **Token-Hash** in DB (`agent_token`)
- Vergleicht via `Hash::check()`
- Gibt Klartext-Token **nur einmalig** beim Pairing zurück

### Pairing-Code

- **6 Ziffern** = 1 Million Kombinationen
- **Läuft ab** nach 5 Minuten
- **Einmalig** verwendbar
- Kein Brute-Force möglich (Rate-Limiting)

### Device-Auth

```php
// Jeder Agent-Request
if (!Hash::check($token, $device->agent_token)) {
    return 401; // Unauthorized
}
```

---

## 🧪 Testen

### 1. Pairing-Flow testen

```bash
# Agent-Seite
cd ~/growdash
source .venv/bin/activate
python pairing.py

# Output:
# ╔════════════════════════════════════╗
# ║  Dein Code: 123456                ║
# ╚════════════════════════════════════╝
# ⏳ Warte auf Pairing-Bestätigung...
```

### 2. Browser-Seite

- Öffne: `https://grow.linn.games/devices/pair`
- Login als User
- Code eingeben: `123456`
- Bestätigen

### 3. Agent-Seite

```bash
# Output:
# ✅ Pairing erfolgreich!
#    Verknüpft mit User: user@example.com
# 💾 Speichere Credentials in .env...
# ✅ Credentials gespeichert
```

### 4. Agent starten

```bash
./grow_start.sh

# Output:
# Führe Startup-Health-Check durch...
# ✅ Laravel-Backend erreichbar und Auth erfolgreich
# Agent läuft...
```

---

## 🎯 Vorteile

✅ **Einfach** - User gibt nur 6-stelligen Code ein  
✅ **Sicher** - Token-Hash in DB, Pairing läuft ab  
✅ **Multi-User** - Jeder User kann mehrere Devices pairen  
✅ **Offline-fähig** - Token bleibt in `.env` gespeichert  
✅ **Revokable** - User kann Device in Web-UI entfernen  

---

## 🔄 Re-Pairing

Falls Token verloren geht oder Device zurückgesetzt wird:

```bash
# Agent-Seite
python pairing.py

# Bestätigt Re-Pairing
# Neuer Token wird generiert
# Alte Verknüpfung bleibt erhalten (selbe Device-ID)
```

---

## 📚 Siehe auch

- `LARAVEL_ENDPOINTS.md` - Laravel-Implementierung
- `QUICKSTART.md` - Setup-Anleitung
- `pairing.py` - Pairing-Script
