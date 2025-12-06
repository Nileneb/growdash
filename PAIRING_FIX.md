# Pairing Fix - Agent ↔ Laravel Synchronisiert

## Problem

Der **Agent** (growdash) hat die **falschen Endpoints** verwendet:
- Agent rief auf: `POST /pairing/init` (existiert nicht)
- Laravel bietet: `POST /api/agents/bootstrap`

## Lösung

### ✅ Agent-Änderungen (pairing.py)

**Vorher:**
- Agent generierte `device_id` + `pairing_code` selbst
- Rief `/pairing/init` auf

**Nachher:**
- Laravel generiert `bootstrap_id` + `bootstrap_code`
- Agent ruft `/api/agents/bootstrap` auf
- Agent pollt `/api/agents/pairing/status?bootstrap_id=xxx`

### Pairing Flow (korrekt)

```
Agent (Python)                    Laravel (Backend)
├─ POST /api/agents/bootstrap     
│  └─ device_info: {platform, version}
│                                  ├─ Generiert bootstrap_id
│                                  ├─ Generiert bootstrap_code (6-stellig)
│                                  └─ Response: {bootstrap_id, bootstrap_code}
│
├─ Zeigt Code an: "123456"
│
├─ Pollt GET /api/agents/pairing/status?bootstrap_id=xxx
│                                  ├─ Status: "pending"
│                                  │
│  ┌─────────────────────────────────────────────────┐
│  │ User gibt Code im Frontend ein                  │
│  │ POST /api/devices/pair                          │
│  └─────────────────────────────────────────────────┘
│                                  │
│                                  ├─ Erstellt Device
│                                  ├─ Generiert agent_token
│                                  ├─ Update Status: "paired"
│                                  │
├─ Pollt erneut
│                                  └─ Response: {
│                                       status: "paired",
│                                       device_id: "growdash-xyz",
│                                       agent_token: "token..."
│                                     }
│
└─ Speichert in .env:
   DEVICE_PUBLIC_ID=growdash-xyz
   DEVICE_TOKEN=token...
```

## Laravel-Endpoints (bereits implementiert)

✅ `POST /api/agents/bootstrap` - BootstrapController@bootstrap
✅ `GET /api/agents/pairing/status` - BootstrapController@status
✅ `POST /api/devices/pair` - DevicePairingController@pair

Alle Endpoints sind **bereits im Laravel-Backend vorhanden** und funktionieren!

## Testen

```bash
cd /home/nileneb/growdash
source venv/bin/activate
python3 bootstrap.py

# Wähle "1" für Pairing-Code
# Agent zeigt 6-stelligen Code
# Gehe zu https://grow.linn.games/devices/pair
# Gib Code ein
# Agent erhält automatisch Token
```

## Alternative: Direct Login

Direct Login benötigt Laravel-Endpoint:
```
POST /api/growdash/devices/register
Authorization: Bearer {user_token}
```

Dieser Endpoint **fehlt noch** im Laravel-Backend.

**Empfehlung:** Nutze Pairing-Code Flow (funktioniert bereits)!
