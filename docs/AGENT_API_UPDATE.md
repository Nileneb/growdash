# Agent API Update - Laravel Struktur Anpassung

**Datum:** 2. Dezember 2025  
**Status:** ✅ Implementiert, Ready for Testing

---

## Änderungsübersicht

Der Python Agent wurde an die neue Laravel API-Struktur angepasst:

### 1. Command-Execution (serial_command)

**Alt:**
```python
{
  "type": "spray_on",
  "params": {"duration": 5}
}
```

**Neu:**
```python
{
  "type": "serial_command",
  "params": {
    "command": "STATUS"  # Direkter Arduino-Befehl
  }
}
```

**Implementierung in `execute_command()`:**
```python
if cmd_type == "serial_command":
    arduino_command = params.get("command", "")
    if not arduino_command:
        return False, "Kein command in params angegeben"
    
    # Direkt an Arduino senden
    self.serial.send_command(arduino_command)
    return True, f"Command '{arduino_command}' sent to Arduino"
```

**Legacy-Support:** Die alten Command-Typen (`spray_on`, `spray_off`, etc.) werden weiterhin unterstützt für Rückwärtskompatibilität.

---

### 2. Command-Result-Format

**Alt:**
```python
{
  "success": true,
  "message": "Spray für 5s aktiviert",
  "timestamp": "2025-12-02T10:30:05.000000Z"
}
```

**Neu:**
```python
{
  "status": "completed",  # oder "failed", "executing"
  "result_message": "Command 'STATUS' sent to Arduino"
}
```

**Implementierung in `report_command_result()`:**
```python
def report_command_result(self, command_id: str, success: bool, message: str = ""):
    status = "completed" if success else "failed"
    
    response = self.session.post(
        f"{self.base_url}/commands/{command_id}/result",
        json={
            "status": status,
            "result_message": message
        },
        timeout=10
    )
```

**Status-Werte:**
- `executing` - Command wird gerade ausgeführt (aktuell nicht verwendet)
- `completed` - Erfolgreich abgeschlossen
- `failed` - Fehlgeschlagen

---

### 3. Command-Response-Format

**Alt:**
```python
{
  "commands": [...]
}
```

**Neu:**
```python
{
  "success": true,
  "commands": [
    {
      "id": 42,
      "type": "serial_command",
      "params": {"command": "STATUS"},
      "created_at": "2025-12-02T10:30:00.000000Z"
    }
  ]
}
```

**Implementierung in `poll_commands()`:**
```python
data = response.json()

# Success-Feld prüfen
if not data.get("success", True):
    logger.warning(f"API returned success=false: {data.get('message', 'Unknown error')}")
    return []

commands = data.get("commands", [])
```

---

## Testing

### Backend-Anforderungen

Der Laravel-Backend muss folgende Endpoints implementieren (siehe `LARAVEL_ENDPOINTS.md`):

1. ✅ `GET /api/growdash/agent/commands/pending`
   - Auth: X-Device-ID + X-Device-Token Headers
   - Response: `{"success": true, "commands": [...]}`

2. ✅ `POST /api/growdash/agent/commands/{id}/result`
   - Auth: X-Device-ID + X-Device-Token Headers
   - Body: `{"status": "completed", "result_message": "..."}`

### Test-Szenario

1. **Command via Laravel Frontend erstellen:**
   ```bash
   # Via Tinker oder Web-Interface
   POST /api/growdash/devices/{device}/commands
   {
     "type": "serial_command",
     "params": {"command": "STATUS"}
   }
   ```

2. **Agent startet und pollt Commands:**
   ```bash
   ./grow_start.sh
   
   # Logs zeigen:
   # INFO - Empfangene Befehle: 1
   # INFO - Führe Befehl aus: serial_command
   # INFO - Befehl an Arduino: STATUS
   # INFO - Befehlsergebnis gemeldet: 42 -> completed
   ```

3. **Ergebnis im Frontend prüfen:**
   ```bash
   GET /api/growdash/devices/{device}/commands
   
   # Zeigt Command mit status="completed"
   ```

---

## Kompatibilität

### Legacy Commands (funktionieren weiterhin)

Der Agent unterstützt weiterhin alte Command-Typen:
- `spray_on` → sendet "SprayOn" oder "Spray {ms}"
- `spray_off` → sendet "SprayOff"
- `fill_start` → sendet "FillL {liters}"
- `fill_stop` → sendet "CancelFill"
- `request_status` → sendet "Status"
- `request_tds` → sendet "TDS"

### Neue Commands (empfohlen)

Nutze `serial_command` für maximale Flexibilität:
```json
{
  "type": "serial_command",
  "params": {
    "command": "STATUS"       // Beliebiger Arduino-Befehl
  }
}
```

**Beispiele:**
- `{"command": "STATUS"}` - Status abfragen
- `{"command": "SprayOn"}` - Spray aktivieren
- `{"command": "Spray 5000"}` - Spray für 5 Sekunden
- `{"command": "FillL 3.5"}` - Auf 3.5 Liter füllen
- `{"command": "TDS"}` - TDS-Messung anfordern

---

## Fehlerbehebung

### 422 Unprocessable Content

**Problem:** Agent sendet alte Felder (`success`, `message`, `timestamp`), Laravel erwartet neue (`status`, `result_message`).

**Lösung:** ✅ Agent wurde angepasst auf neue Felder.

### Commands werden nicht abgeholt

**Checklist:**
1. Device-Status in Laravel auf `online`?
2. Heartbeat-Loop läuft? (alle 30s)
3. Command-Poll-Interval korrekt? (Standard: 5s)
4. Device-Token in `.env` korrekt gesetzt?

### Serial-Befehle kommen nicht am Arduino an

**Debug:**
```python
# In execute_command() wurde Logging hinzugefügt:
logger.info(f"Führe Befehl aus: {cmd_type}")
# Und in SerialProtocol.send_command():
logger.info(f"Befehl an Arduino: {command}")
```

Prüfe Logs ob Befehle gesendet werden.

---

## Nächste Schritte

1. ✅ Agent-Code angepasst
2. ⏳ Backend-Endpoints testen (Laravel muss deployed sein)
3. ⏳ End-to-End-Test: Frontend → Laravel → Agent → Arduino
4. ⏳ WebSocket für Live-Updates (optional)

---

## Dateien geändert

- `agent.py`:
  - `execute_command()` - serial_command Support
  - `report_command_result()` - Neue Felder (status, result_message)
  - `poll_commands()` - Success-Feld Validierung
  - `command_loop()` - Logging verbessert

---

## Kompatibilitäts-Matrix

| Feature | Alte API | Neue API | Agent-Support |
|---------|----------|----------|---------------|
| Command-Typen | spray_on, fill_start, etc. | serial_command | ✅ Beide |
| Result-Format | success + message | status + result_message | ✅ Neu |
| Response-Format | {commands: [...]} | {success: true, commands: [...]} | ✅ Neu |
| Firmware-Update | firmware_update | firmware_update | ✅ Unverändert |
| Heartbeat | POST /heartbeat | POST /heartbeat | ✅ Unverändert |
| Telemetrie | POST /telemetry | POST /telemetry | ✅ Unverändert |

---

**Wichtig:** Der Agent ist backward-compatible - alte Commands funktionieren weiterhin, aber neue `serial_command` ist empfohlen!
