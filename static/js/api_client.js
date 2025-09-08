/* GrowDash API Client */

// API-Endpunkte
const API = {
  // Wassersystem-Status abrufen
  getWaterStatus: async () => {
    const response = await fetch('/api/data/water/status');
    return await response.json();
  },
  
  // Wasserstandsverlauf abrufen
  getWaterHistory: async (limit = 100, days = null) => {
    let url = `/api/data/water/history?limit=${limit}`;
    if (days) url += `&days=${days}`;
    const response = await fetch(url);
    return await response.json();
  },

  // TDS-Verlauf abrufen
  getTdsHistory: async (limit = 100, days = null) => {
    let url = `/api/data/tds/history?limit=${limit}`;
    if (days) url += `&days=${days}`;
    const response = await fetch(url);
    return await response.json();
  },

  // Temperatur-Verlauf abrufen
  getTemperatureHistory: async (limit = 100, days = null) => {
    let url = `/api/data/temperature/history?limit=${limit}`;
    if (days) url += `&days=${days}`;
    const response = await fetch(url);
    return await response.json();
  },

  // Sprühereignisse abrufen
  getSprayEvents: async (limit = 50, days = null) => {
    let url = `/api/data/events/spray?limit=${limit}`;
    if (days) url += `&days=${days}`;
    const response = await fetch(url);
    return await response.json();
  },

  // Füllereignisse abrufen
  getFillEvents: async (limit = 50, days = null) => {
    let url = `/api/data/events/fill?limit=${limit}`;
    if (days) url += `&days=${days}`;
    const response = await fetch(url);
    return await response.json();
  },

  // Logs abrufen
  getLogs: async (limit = 100, level = null) => {
    let url = `/api/data/logs?limit=${limit}`;
    if (level) url += `&level=${level}`;
    const response = await fetch(url);
    return await response.json();
  },

  // Arduino-Befehl senden
  sendCommand: async (command) => {
    const response = await fetch('/api/command', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ command })
    });
    return await response.json();
  }
};

// WebSocket-Verbindung für Echtzeitdaten
class GrowDashSocket {
  constructor() {
    this.socket = null;
    this.connected = false;
    this.eventListeners = {
      log: [],
      water_status: [],
      connect: [],
      disconnect: [],
      error: []
    };
  }

  // Verbindung herstellen
  connect() {
    // WebSocket-URL basierend auf aktueller Seiten-URL erstellen
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;
    
    this.socket = new WebSocket(wsUrl);
    
    this.socket.onopen = () => {
      console.log('WebSocket verbunden');
      this.connected = true;
      this._triggerEvent('connect');
    };
    
    this.socket.onclose = () => {
      console.log('WebSocket getrennt');
      this.connected = false;
      this._triggerEvent('disconnect');
      
      // Automatischer Wiederverbindungsversuch nach 5 Sekunden
      setTimeout(() => {
        if (!this.connected) this.connect();
      }, 5000);
    };
    
    this.socket.onerror = (error) => {
      console.error('WebSocket Fehler:', error);
      this._triggerEvent('error', error);
    };
    
    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type && this.eventListeners[data.type]) {
          this._triggerEvent(data.type, data);
        }
      } catch (error) {
        console.error('Fehler beim Verarbeiten der WebSocket-Nachricht:', error);
      }
    };
  }
  
  // Befehl senden
  send(command, params = {}) {
    if (!this.connected) {
      console.error('Nicht verbunden');
      return false;
    }
    
    if (typeof command === 'string') {
      // Einfacher Textbefehl
      this.socket.send(command);
    } else {
      // Strukturierter Befehl
      const message = {
        type: 'water_command',
        command: command,
        params: params
      };
      this.socket.send(JSON.stringify(message));
    }
    
    return true;
  }
  
  // Event-Listener hinzufügen
  on(event, callback) {
    if (this.eventListeners[event]) {
      this.eventListeners[event].push(callback);
    } else {
      this.eventListeners[event] = [callback];
    }
  }
  
  // Event-Listener entfernen
  off(event, callback) {
    if (this.eventListeners[event]) {
      this.eventListeners[event] = this.eventListeners[event].filter(cb => cb !== callback);
    }
  }
  
  // Events auslösen
  _triggerEvent(event, data) {
    if (this.eventListeners[event]) {
      for (const callback of this.eventListeners[event]) {
        callback(data);
      }
    }
  }
}

// Exportiere die API und Socket-Klasse
window.GrowDash = {
  API,
  Socket: new GrowDashSocket()
};
