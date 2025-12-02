# Onboarding-Modi Vergleich

## 🆚 Pairing-Code vs. Direct-Login

| Aspekt | 🔢 Pairing-Code | 🔐 Direct-Login |
|--------|----------------|-----------------|
| **Zielgruppe** | Normale User, Production | Power-User, Entwickler |
| **Komplexität** | Einfach | Advanced |
| **Schritte** | 3 (Code generieren, Web-UI, Bestätigen) | 2 (Email+PW, Fertig) |
| **Credentials auf Device** | Nur Device-Token | Nur Device-Token |
| **User-Token Exposure** | Niemals | Kurz (wird sofort revoked) |
| **Sicherheit** | ⭐⭐⭐⭐⭐ Sehr sicher | ⭐⭐⭐⭐ Sicher (mit Revoke) |
| **Multi-User** | ✅ Jeder User kann pairen | ✅ Jeder User kann sich einloggen |
| **Offline-Setup** | ❌ Benötigt Web-UI | ✅ Nur CLI |
| **Headless-Server** | ❌ Nicht ideal | ✅ Perfekt |
| **Versand-Geräte** | ✅ Perfekt | ❌ User-Credentials nötig |

---

## 🔢 Pairing-Code-Flow

### Vorteile:
✅ **Keine Credentials auf CLI** - User gibt nur 6-stelligen Code ein  
✅ **Web-UI Kontrolle** - User sieht alle Devices, kann Name vergeben  
✅ **Versand-ready** - Geräte können vorinstalliert versendet werden  
✅ **Audit-Log** - Jedes Pairing ist in Web-UI nachvollziehbar  

### Nachteile:
❌ **Browser erforderlich** - Nicht rein CLI-basiert  
❌ **2-Step-Prozess** - Code generieren + Web-UI öffnen  
❌ **Timeout** - Code läuft nach 5 Minuten ab  

### Use Cases:
- 🏠 Enduser-Installation
- 📦 Versand von vorkonfigurierten Geräten
- 👨‍👩‍👧‍👦 Mehrere User am gleichen Device
- 🔒 Maximale Sicherheit

---

## 🔐 Direct-Login-Flow

### Vorteile:
✅ **Schnell** - Nur Email+Passwort, fertig  
✅ **CLI-only** - Kein Browser nötig  
✅ **Headless-ready** - Perfekt für Server/Remote-Setup  
✅ **Dev-Workflow** - Schnelles Re-Pairing bei Entwicklung  

### Nachteile:
❌ **Credentials auf CLI** - User muss PW eingeben (wird nicht gespeichert!)  
❌ **Kein Web-UI Feedback** - Device erscheint einfach in Liste  
❌ **User-Token Exposure** - Kurz ein vollwertiger Token (wird revoked)  

### Use Cases:
- 💻 Entwickler-Setup
- 🖥️ Headless-Server via SSH
- ⚡ Schnelles Re-Pairing
- 🔧 Advanced-User

---

## 🛡️ Sicherheits-Vergleich

### Pairing-Code:
```
Agent          Laravel
  │               │
  ├─ POST /init ──►│ Erstellt Pairing-Request
  │               │ Code läuft nach 5 Min ab
  │               │
User (Browser)    │
  │               │
  ├─ POST /pair ──►│ Verknüpft mit user_id
  │               │ Generiert Device-Token
  │               │
Agent             │
  │               │
  ├─ GET /status ─►│ Gibt Device-Token zurück
  │               │
  └─ Speichert in .env

RISIKO: ⭐ Minimal
- Nur 6-stelliger Code exposed
- Code ist einmalig & läuft ab
- Kein User-Token auf Device
```

### Direct-Login:
```
Agent             Laravel
  │                 │
User (CLI)          │
  ├─ Email+PW ──────┤
  │                 │
Agent               │
  │                 │
  ├─ POST /login ───►│ User-Token (Bearer)
  │◄────────────────┤
  │                 │
  ├─ POST /register ►│ Device-Token
  │◄────────────────┤ (public_id + token)
  │                 │
  ├─ POST /logout ──►│ Revoke User-Token!
  │                 │
  └─ Speichert nur Device-Token

RISIKO: ⭐⭐ Niedrig (mit Revoke)
- User-Token existiert kurz (< 1 Sekunde)
- Wird sofort nach Registrierung revoked
- Email+PW werden nicht gespeichert
- Device-Token hat minimale Rechte
```

---

## 📋 Implementierungs-Checklist

### Laravel-Backend:

#### Pairing-Code-Flow:
- [ ] `POST /api/growdash/agent/pairing/init`
- [ ] `GET /api/growdash/agent/pairing/status`
- [ ] `POST /api/growdash/devices/pair` (Web-UI)
- [ ] `device_pairings` Migration
- [ ] Pairing-Code läuft nach 5 Min ab
- [ ] Web-UI Pairing-Seite

#### Direct-Login-Flow:
- [ ] `POST /api/auth/login` (Sanctum)
- [ ] `POST /api/auth/logout`
- [ ] `POST /api/growdash/devices/register` (auth:sanctum)
- [ ] Token-Revoke nach Registrierung
- [ ] Rate-Limiting auf Login

#### Beide:
- [ ] `devices` Migration (user_id, public_id, agent_token)
- [ ] Device-Auth Middleware (Hash::check)
- [ ] Agent-Endpoints (telemetry, commands, logs)

### Agent:

- [x] `bootstrap.py` - Onboarding-Wizard
- [x] `pairing.py` - Pairing-Code-Flow
- [x] Direct-Login in bootstrap.py
- [x] Token-Revoke nach Registrierung
- [x] Email+PW aus Speicher löschen
- [x] Nur Device-Token in .env

---

## 🎯 Empfehlung

### Für Production / Enduser:
→ **Pairing-Code-Flow** verwenden

### Für Dev / Power-User:
→ **Direct-Login-Flow** nutzen

### Beide aktiviert?
→ **JA!** User kann selbst wählen (bootstrap.py Wizard)

---

## 🧪 Testing

### Pairing-Code testen:
```bash
python bootstrap.py
# Wähle Option 1
# Gehe zu Web-UI
# Gib Code ein
```

### Direct-Login testen:
```bash
python bootstrap.py
# Wähle Option 2
# Email: test@example.com
# Passwort: secret123
```

### Beide Flows sollten funktionieren!

---

## 📚 Siehe auch

- `bootstrap.py` - Onboarding-Wizard
- `pairing.py` - Pairing-Code-Implementierung
- `LARAVEL_ENDPOINTS.md` - Laravel-API-Dokumentation
- `PAIRING_FLOW.md` - Detaillierter Ablauf
- `QUICKSTART.md` - Setup-Anleitung
