# GrowDash Pairing - Laravel Endpoint Requirements

## Aktuelle Situation

**Pairing Flow (Agent-generiert):**
1. Agent generiert `device_id` + `pairing_code` lokal
2. Agent sendet an Laravel: `POST /api/growdash/agent/pairing/init`
3. Laravel speichert temporär in DB
4. User gibt Code im Frontend ein
5. Agent pollt: `GET /api/growdash/agent/pairing/status`

## Required Laravel Endpoints

### 1. POST `/api/growdash/agent/pairing/init`

**Request:**
```json
{
  "device_id": "growdash-abc1",
  "pairing_code": "123456",
  "device_info": {
    "platform": "raspberry-pi",
    "version": "2.0"
  }
}
```

**Response (201 Created):**
```json
{
  "status": "pending",
  "expires_at": "2025-12-06T12:35:00Z"
}
```

**Was Laravel tun muss:**
- Speichere `device_id`, `pairing_code`, `expires_at` (5 Min) in Tabelle `device_pairings`
- Status: `pending`

---

### 2. GET `/api/growdash/agent/pairing/status`

**Query Params:**
- `device_id=growdash-abc1`
- `pairing_code=123456`

**Response A - Noch pending:**
```json
{
  "status": "pending"
}
```

**Response B - User hat Code eingegeben:**
```json
{
  "status": "paired",
  "agent_token": "your-device-token-here",
  "user_email": "bene.linn@yahoo.de"
}
```

**Response C - Expired:**
```json
{
  "status": "expired"
}
```

**Was Laravel tun muss:**
- Prüfe `device_pairings` Tabelle
- Wenn User Code eingegeben hat → Device erstellen, Token generieren
- Return Status + Token

---

### 3. POST `/api/growdash/devices/pair` (Frontend-Endpoint)

**Request (vom Frontend):**
```json
{
  "pairing_code": "123456"
}
```

**Headers:**
```
Authorization: Bearer {user_token}
```

**Response:**
```json
{
  "success": true,
  "device_id": "growdash-abc1",
  "device_name": "GrowDash Device"
}
```

**Was Laravel tun muss:**
- Finde `device_pairing` mit Code
- Erstelle `Device` für User
- Generiere `agent_token`
- Update `device_pairing.status = 'paired'`
- Speichere `agent_token` in `device_pairing`

---

## Alternative: Direct Login Flow

**Request:**
```
POST /api/growdash/devices/register
Authorization: Bearer {user_token}
```

**Body:**
```json
{
  "name": "GrowDash u-server",
  "platform": "linux",
  "version": "2.0"
}
```

**Response:**
```json
{
  "device_id": "growdash-xyz",
  "agent_token": "token-here"
}
```

**Was Laravel tun muss:**
- Erstelle Device für User
- Generiere eindeutige `public_id` und `agent_token`
- Return beide Werte

---

## Database Schema

### `device_pairings` Table

```sql
CREATE TABLE device_pairings (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    device_id VARCHAR(255) UNIQUE,
    pairing_code VARCHAR(6),
    status ENUM('pending', 'paired', 'expired') DEFAULT 'pending',
    agent_token VARCHAR(255) NULL,
    user_id BIGINT NULL,
    device_info JSON,
    expires_at TIMESTAMP,
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    INDEX(pairing_code),
    INDEX(status),
    INDEX(expires_at)
);
```

### `devices` Table

```sql
CREATE TABLE devices (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    user_id BIGINT NOT NULL,
    public_id VARCHAR(255) UNIQUE,
    name VARCHAR(255),
    agent_token VARCHAR(255), -- HASHED!
    platform VARCHAR(50),
    version VARCHAR(50),
    ip_address VARCHAR(45) NULL,
    api_port INT DEFAULT 8000,
    last_seen_at TIMESTAMP NULL,
    status ENUM('active', 'offline') DEFAULT 'active',
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    
    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE,
    INDEX(user_id),
    INDEX(status)
);
```

---

## Agent Implementation Status

✅ **bootstrap.py** - Wizard mit Pairing + Direct Login
✅ **pairing.py** - DevicePairing Klasse
✅ **setup.sh** - Ruft bootstrap.py auf

**Was funktioniert:**
- Agent generiert Code lokal
- Polling für Status
- .env speichern

**Was Laravel implementieren muss:**
- `/api/growdash/agent/pairing/init` - Code speichern
- `/api/growdash/agent/pairing/status` - Status + Token zurück
- `/api/growdash/devices/pair` - Frontend-Endpoint
- `/api/growdash/devices/register` - Direct Login

---

## Testing

```bash
# Agent-Seite
./setup.sh
# Wähle Option 1 (Pairing-Code)
# Code wird angezeigt

# Laravel-Seite (manuell testen)
curl -X POST https://grow.linn.games/api/growdash/agent/pairing/init \
  -H "Content-Type: application/json" \
  -d '{"device_id":"growdash-test","pairing_code":"123456","device_info":{}}'

# Frontend: Code eingeben
# Agent pollt automatisch und erhält Token
```
