# Fix: Heartbeat 404 Error

## Problem

Agent sendete Heartbeats, bekam aber 404-Fehler:
```
2025-12-02 00:52:58,719 - __main__ - WARNING - Heartbeat fehlgeschlagen: 404
```

## Ursache

**Doppelter `/agent` Pfad** in der URL-Konstruktion:

- Config: `LARAVEL_API_PATH=/api/growdash/agent`
- `base_url` = `https://grow.linn.games/api/growdash/agent`
- Heartbeat-Call: `f"{self.base_url}/agent/heartbeat"`
- **Resultat**: `https://grow.linn.games/api/growdash/agent/agent/heartbeat` ❌

## Lösung

**Datei**: `agent.py`, Zeile ~340

```python
# VORHER (falsch):
response = self.session.post(
    f"{self.base_url}/agent/heartbeat",  # ❌ Doppeltes /agent
    ...
)

# NACHHER (richtig):
response = self.session.post(
    f"{self.base_url}/heartbeat",  # ✅ Kein Duplikat
    ...
)
```

## Verifikation

### Test-Skript erstellt: `test_heartbeat.sh`

```bash
./test_heartbeat.sh
```

**Output**:
```
✅ Heartbeat erfolgreich!
HTTP Status: 200
{
  "success": true,
  "message": "Heartbeat received",
  "last_seen_at": "2025-12-01T23:56:50.000000Z"
}
```

### Agent-Logs (nach Fix):

```bash
./grow_start.sh
```

**Erwartete Logs** (alle 30s):
```
Agent läuft...
  Telemetrie: alle 10s
  Befehle: alle 5s
  Heartbeat: alle 30s
✅ Heartbeat gesendet (uptime: 30s)
✅ Heartbeat gesendet (uptime: 60s)
```

## Weitere Checks

### 1. Backend-Status prüfen

```bash
# Im Laravel-Projekt:
php artisan tinker
>>> $device = Device::where('public_id', '1d850062-9d28-4455-9736-98bdf8318746')->first();
>>> $device->last_seen_at;  // Sollte < 1 Minute alt sein
>>> $device->status;  // Sollte 'online' sein
>>> $device->last_state;  // Enthält uptime, memory, etc.
```

### 2. Alle Agent-URLs prüfen

Alle URLs in `LaravelClient` verwenden jetzt korrekt `base_url` ohne Duplikate:

- ✅ `/heartbeat` → `https://grow.linn.games/api/growdash/agent/heartbeat`
- ✅ `/telemetry` → `https://grow.linn.games/api/growdash/agent/telemetry`
- ✅ `/commands/pending` → `https://grow.linn.games/api/growdash/agent/commands/pending`
- ✅ `/commands/{id}/result` → `https://grow.linn.games/api/growdash/agent/commands/{id}/result`
- ✅ `/logs` → `https://grow.linn.games/api/growdash/agent/logs`

## Status

✅ **FIXED** - Heartbeat funktioniert jetzt korrekt  
✅ **TESTED** - Manueller Test erfolgreich (200 OK)  
✅ **READY** - Agent kann produktiv gestartet werden

---

**Datum**: 2025-12-02  
**Commit**: Fix double /agent path in heartbeat URL
