/**
 * GrowDash - Wassersteuerungs-Frontend
 * 
 * Dieses Modul stellt Funktionen zur Anzeige und Steuerung des Wassersystems bereit:
 * - Wassertank-Anzeige
 * - Sprühnebel-Steuerung mit Zeitfunktion
 * - Wasserzufuhr-Steuerung
 */

// Wasserstand-Anzeige Element
let waterLevelIndicator = null;
let waterLevelText = null;

// Sprühsteuerungs-Elemente
let sprayActiveIndicator = null;
let sprayToggleButton = null;
let sprayDurationInput = null;

// Wasserfüll-Elemente
let fillActiveIndicator = null;
let fillStartButton = null;
let fillStopButton = null;
let fillTargetInput = null;
let fillDurationInput = null;

// Status-Werte
let waterLevel = 0;
let sprayActive = false;
let fillActive = false;

/**
 * Initialisiert das Wassersteuerungs-Frontend.
 * Diese Funktion muss aufgerufen werden, nachdem das DOM geladen wurde.
 */
function initWaterControls() {
  // Elemente aus dem DOM abrufen
  waterLevelIndicator = document.getElementById('waterLevelBar');
  waterLevelText = document.getElementById('waterLevelText');
  
  sprayActiveIndicator = document.getElementById('sprayActiveIndicator');
  sprayToggleButton = document.getElementById('sprayToggleButton');
  sprayDurationInput = document.getElementById('sprayDuration');
  
  fillActiveIndicator = document.getElementById('fillActiveIndicator');
  fillStartButton = document.getElementById('fillStartButton');
  fillStopButton = document.getElementById('fillStopButton');
  fillTargetInput = document.getElementById('fillTarget');
  fillDurationInput = document.getElementById('fillDuration');
  
  // Event-Listener hinzufügen
  if (sprayToggleButton) {
    sprayToggleButton.addEventListener('click', toggleSpray);
  }
  
  if (fillStartButton) {
    fillStartButton.addEventListener('click', startFill);
  }
  
  if (fillStopButton) {
    fillStopButton.addEventListener('click', stopFill);
  }
  
  // Wasserstand initial abfragen
  requestWaterLevel();
  
  // Status-Updates alle 10 Sekunden abfragen
  setInterval(requestWaterLevel, 10000);
}

/**
 * Aktualisiert die Wasserstandanzeige.
 * @param {number} level - Wasserstand in Prozent (0-100)
 */
function updateWaterLevel(level) {
  waterLevel = level;
  
  if (waterLevelIndicator) {
    waterLevelIndicator.style.width = `${level}%`;
    
    // Farbe basierend auf Füllstand anpassen
    if (level < 20) {
      waterLevelIndicator.classList.remove('bg-blue-500', 'bg-yellow-500');
      waterLevelIndicator.classList.add('bg-red-500');
    } else if (level < 50) {
      waterLevelIndicator.classList.remove('bg-blue-500', 'bg-red-500');
      waterLevelIndicator.classList.add('bg-yellow-500');
    } else {
      waterLevelIndicator.classList.remove('bg-red-500', 'bg-yellow-500');
      waterLevelIndicator.classList.add('bg-blue-500');
    }
  }
  
  if (waterLevelText) {
    waterLevelText.textContent = `${level}%`;
  }
}

/**
 * Aktualisiert die Sprühnebel-Statusanzeige.
 * @param {boolean} active - Ob der Sprühnebel aktiv ist
 */
function updateSprayStatus(active) {
  sprayActive = active;
  
  if (sprayActiveIndicator) {
    sprayActiveIndicator.classList.toggle('bg-green-500', active);
    sprayActiveIndicator.classList.toggle('bg-gray-300', !active);
  }
  
  if (sprayToggleButton) {
    sprayToggleButton.textContent = active ? 'Spray ausschalten' : 'Spray einschalten';
    sprayToggleButton.classList.toggle('btn-bad', active);
    sprayToggleButton.classList.toggle('btn-ok', !active);
  }
}

/**
 * Aktualisiert die Wasserfüll-Statusanzeige.
 * @param {boolean} active - Ob die Wasserzufuhr aktiv ist
 */
function updateFillStatus(active) {
  fillActive = active;
  
  if (fillActiveIndicator) {
    fillActiveIndicator.classList.toggle('bg-green-500', active);
    fillActiveIndicator.classList.toggle('bg-gray-300', !active);
  }
  
  if (fillStartButton && fillStopButton) {
    fillStartButton.disabled = active;
    fillStopButton.disabled = !active;
    
    fillStartButton.classList.toggle('opacity-50', active);
    fillStopButton.classList.toggle('opacity-50', !active);
  }
}

/**
 * Schaltet den Sprühnebel ein oder aus.
 */
function toggleSpray() {
  const duration = sprayDurationInput ? parseInt(sprayDurationInput.value, 10) || 0 : 0;
  
  if (sprayActive) {
    // Spray ausschalten
    sendWaterCommand('spray_off');
  } else {
    // Spray einschalten, optional mit Dauer
    if (duration > 0) {
      sendWaterCommand('spray_on', { duration });
      appendLog(`Spray für ${duration} Sekunden eingeschaltet`);
    } else {
      sendWaterCommand('spray_on');
      appendLog('Spray eingeschaltet');
    }
  }
}

/**
 * Startet die Wasserzufuhr.
 */
function startFill() {
  const target = fillTargetInput ? parseInt(fillTargetInput.value, 10) || 0 : 0;
  const duration = fillDurationInput ? parseInt(fillDurationInput.value, 10) || 0 : 0;
  
  const params = {};
  if (target > 0) params.target = target;
  if (duration > 0) params.duration = duration;
  
  let message = 'Wasserzufuhr gestartet';
  if (target > 0 && duration > 0) {
    message = `Wasserzufuhr bis ${target}% für max. ${duration} Sekunden gestartet`;
  } else if (target > 0) {
    message = `Wasserzufuhr bis ${target}% gestartet`;
  } else if (duration > 0) {
    message = `Wasserzufuhr für ${duration} Sekunden gestartet`;
  }
  
  sendWaterCommand('water_fill_start', params);
  appendLog(message);
}

/**
 * Stoppt die Wasserzufuhr.
 */
function stopFill() {
  sendWaterCommand('water_fill_stop');
  appendLog('Wasserzufuhr gestoppt');
}

/**
 * Fragt den aktuellen Wasserstand ab.
 */
function requestWaterLevel() {
  sendWaterCommand('water_level');
}

/**
 * Sendet einen Wassersteuerungs-Befehl über den WebSocket.
 * @param {string} command - Der Befehl
 * @param {object} params - Optionale Parameter
 */
function sendWaterCommand(command, params = {}) {
  if (window.ws && window.ws.readyState === WebSocket.OPEN) {
    window.ws.send(JSON.stringify({
      type: 'water_command',
      command,
      params
    }));
  } else {
    appendLog('WebSocket nicht verbunden. Befehl konnte nicht gesendet werden.');
  }
}

/**
 * Verarbeitet eingehende WebSocket-Nachrichten für Wassersteuerungen.
 * @param {object} message - Die empfangene Nachricht
 * @returns {boolean} true, wenn die Nachricht verarbeitet wurde, sonst false
 */
function handleWaterSocketMessage(message) {
  if (message.type === 'water_status') {
    if ('water_level' in message) {
      updateWaterLevel(message.water_level);
    }
    
    if ('spray_active' in message) {
      updateSprayStatus(message.spray_active);
    }
    
    if ('filling_active' in message) {
      updateFillStatus(message.filling_active);
    }
    
    return true;
  }
  
  return false;
}

// Export für globale Verfügbarkeit
window.waterControls = {
  init: initWaterControls,
  handleSocketMessage: handleWaterSocketMessage,
  updateWaterLevel: updateWaterLevel,
  updateSprayStatus: updateSprayStatus,
  updateFillStatus: updateFillStatus
};
