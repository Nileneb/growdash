# Anpassungen für WebSocket-Videostream in Laravel

## 1. WebSocket-Server/Backend
- Stelle sicher, dass Laravel Reverb (oder ein kompatibler WebSocket-Server) WebSocket-Verbindungen auf `/ws/video/{device_public_id}` akzeptiert.
- Die Authentifizierung erfolgt per Header oder Query-String:
  - `X-Device-ID`
  - `X-Device-Token`

## 2. Event-Handling
- Implementiere einen Listener für eingehende WebSocket-Nachrichten auf `/ws/video/{device_public_id}`.
- Erwarte Nachrichten im JSON-Format:
  ```json
  {
    "event": "video_frame",
    "device": "<device_public_id>",
    "frame": "<base64-jpeg>",
    "timestamp": 1700000000.123
  }
  ```
- Verifiziere die Device-Authentifizierung wie bei anderen Agent-Events.

## 3. Speicherung/Verteilung
- Option 1: Leite die Frames direkt an verbundene Frontend-Clients weiter (Broadcast, Echo, etc.).
- Option 2: Puffer die letzten N Frames im Speicher (z.B. Redis, RAM), damit neue Clients sofort ein Bild erhalten.
- Option 3: Optional: Schreibe Snapshots auf Disk oder in die Datenbank.

## 4. Frontend
- Implementiere einen WebSocket-Client im Frontend, der sich mit `/ws/video/{device_public_id}` verbindet.
- Dekodiere das Base64-JPEG und zeige es als `<img>` oder Canvas an (z.B. per `src="data:image/jpeg;base64,..."`).
- Optional: Fallback auf MJPEG-HTTP-Stream, falls kein WebSocket verfügbar.

## 5. Sicherheit
- Prüfe Device-Token bei jeder eingehenden Verbindung und jedem Frame.
- Setze Rate-Limits, um Missbrauch zu verhindern.

## 6. Beispiel (Node.js-ähnlicher Pseudocode für Backend-Handler)
```js
wsServer.on('connection', (ws, req) => {
  // Authentifizierung prüfen
  // ...
  ws.on('message', (msg) => {
    const data = JSON.parse(msg);
    if (data.event === 'video_frame') {
      // Frame an Frontend-Broadcast weiterleiten
      broadcastToClients(data.device, data.frame);
    }
  });
});
```

## 7. Hinweise
- Laravel selbst ist für große Binärdatenströme nicht optimiert. Für hohe Video-Last ggf. Node.js, Go oder Python als Proxy/Relay nutzen.
- Die WebSocket-URL und das Protokoll müssen mit dem Agenten abgestimmt sein.

---
**Status:** Agent sendet Frames per WebSocket. Backend muss Channel `/ws/video/{device_public_id}` entgegennehmen, authentifizieren und Frames an Frontend weiterleiten.
