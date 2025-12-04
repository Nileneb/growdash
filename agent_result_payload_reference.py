#!/usr/bin/env python3
"""
Quick Reference: Agent Result Payload Format Changes
======================================================

WICHTIG: Diese Änderungen sind bereits implementiert in agent.py!

Key Points:
-----------
1. execute_command() gibt DICT zurück (nicht Tuple!)
2. report_command_result() sendet ALLE Felder an Laravel
3. FirmwareManager-Methoden geben 4-tuple zurück: (success, message, output, error)
"""

# ============================================================================
# BEISPIEL 1: Erfolgreiche Kompilierung
# ============================================================================

# Agent sendet diesen Dict an Laravel:
successful_compile_result = {
    'status': 'completed',
    'message': '✅ Sketch erfolgreich kompiliert',
    'output': '''Sketch uses 1234 bytes (4.79%) of program storage space.
Maximum is 25728 bytes.
Global variables use 12 bytes (0.47%) of dynamic memory.''',
    'error': ''
}

# LaravelClient.report_command_result() sendet zu Laravel:
successful_compile_payload = {
    "status": "completed",
    "result_message": "✅ Sketch erfolgreich kompiliert",
    "output": "Sketch uses 1234 bytes...",
    "error": ""
}


# ============================================================================
# BEISPIEL 2: Kompilierungsfehler
# ============================================================================

# Agent sendet diesen Dict an Laravel:
failed_compile_result = {
    'status': 'failed',
    'message': 'Kompilierung fehlgeschlagen',
    'output': '''Linking everything together...
/tmp/arduino_sketch_abc123/arduino_sketch_abc123.ino:21:9: error: 'LO' was not declared in this scope''',
    'error': '''/tmp/arduino_sketch_abc123/arduino_sketch_abc123.ino: In function 'void blinkLong()':
/tmp/arduino_sketch_abc123/arduino_sketch_abc123.ino:21:9: error: 'LO' was not declared in this scope
   delay(LO LONG_ON);
         ^~
/tmp/arduino_sketch_abc123/arduino_sketch_abc123.ino:21:14: error: 'LONG_ON' was not declared in this scope
   delay(LO LONG_ON);
            ^~~~~~~
exit status 1
Compilation error: exit status 1'''
}

# LaravelClient sendet zu Laravel:
failed_compile_payload = {
    "status": "failed",
    "result_message": "Kompilierung fehlgeschlagen",
    "output": "Linking everything together...",
    "error": "error: 'LO' was not declared in this scope\nerror: 'LONG_ON' was not declared..."
}


# ============================================================================
# BEISPIEL 3: Upload erfolgreich
# ============================================================================

successful_upload_result = {
    'status': 'completed',
    'message': '✅ Sketch erfolgreich kompiliert und auf /dev/ttyUSB0 uploaded',
    'output': 'Sketch uses 1234 bytes...',
    'error': ''
}


# ============================================================================
# BEISPIEL 4: Upload fehlgeschlagen (Device nicht verbunden)
# ============================================================================

failed_upload_result = {
    'status': 'failed',
    'message': 'Upload fehlgeschlagen',
    'output': 'Compiling sketch...',
    'error': 'SerialException: port not found'
}


# ============================================================================
# BEISPIEL 5: Serial Command erfolgreich
# ============================================================================

serial_command_result = {
    'status': 'completed',
    'message': 'Arduino: WaterLevel: 45',
    'output': 'WaterLevel: 45'
}


# ============================================================================
# BEISPIEL 6: Serial Command fehlgeschlagen (Timeout)
# ============================================================================

serial_command_timeout_result = {
    'status': 'completed',  # Befehl wurde gesendet
    'message': "Command 'Status' sent (no response)",
    'output': ''
}


# ============================================================================
# Neue execute_command() Rückgabewerte - Checkliste
# ============================================================================

"""
Serial Commands:
  ✅ serial_command
  ✅ spray_on
  ✅ spray_off
  ✅ fill_start
  ✅ fill_stop
  ✅ request_status
  ✅ request_tds

Arduino-CLI Commands:
  ✅ arduino_compile
  ✅ arduino_upload
  ✅ arduino_compile_upload

Firmware:
  ✅ firmware_update
  
Alle geben jetzt Dict zurück mit:
  - status: 'completed' | 'failed'
  - message: str (kurze Beschreibung)
  - output: str (Vollständiger Output)
  - error: str (nur wenn status='failed')
"""


# ============================================================================
# LaravelClient.report_command_result() - Neue Signatur
# ============================================================================

"""
ALT (nicht mehr verwendet):
  report_command_result(command_id: str, success: bool, message: str = "")

NEU (aktuell):
  report_command_result(command_id: str, result: Dict[str, Any])
  
Sendet zu Laravel:
  {
    "status": result.get('status'),
    "result_message": result.get('message', ''),
    "output": result.get('output', ''),
    "error": result.get('error', '')
  }
"""


# ============================================================================
# FirmwareManager - Neue Return-Types
# ============================================================================

"""
ALT:
  compile_sketch(path, board) -> (bool, str)
  upload_hex(path, board, port) -> (bool, str)
  compile_and_upload(path, board, port) -> (bool, str)
  flash_firmware(module_id, port) -> (bool, str)

NEU:
  compile_sketch(path, board) -> (bool, str, str, str)
                                 success, message, output, error
  
  compile_and_upload(path, board, port) -> (bool, str, str, str)
                                            success, message, output, error
  
  flash_firmware(module_id, port) -> (bool, str, str, str)
                                     success, message, output, error
"""


# ============================================================================
# Testing-Workflow
# ============================================================================

"""
1. Start Agent:
   $ python agent.py
   
2. Send Compile Command from Laravel Backend:
   POST /api/growdash/agent/commands
   {
     "type": "arduino_compile",
     "params": {
       "code": "void setup() { delay(LO LONG_ON); }",
       "board": "arduino:avr:nano"
     }
   }

3. Agent Response Flow:
   ├─ execute_command() returns:
   │  {
   │    "status": "failed",
   │    "message": "Kompilierung fehlgeschlagen",
   │    "output": "Linking...",
   │    "error": "error: 'LO' was not declared..."
   │  }
   │
   ├─ command_loop() calls:
   │  report_command_result(cmd_id, result)
   │
   └─ report_command_result() sends:
      POST /api/growdash/agent/commands/{id}/result
      {
        "status": "failed",
        "result_message": "Kompilierung fehlgeschlagen",
        "output": "Linking...",
        "error": "error: 'LO' was not declared..."
      }

4. Laravel receives complete error details
   → Frontend can display full error message
   → LLM can analyze the error
   → Auto-fix suggestion generated

5. Frontend UI shows:
   ❌ ERROR: error: 'LO' was not declared in this scope
   
   🤖 AI SUGGESTION:
   The variable 'LO' is not defined. Did you mean:
   - LON (if you have LON defined)
   - Define 'LO' constant at the top
   
   ✅ TRY FIX: Define 'const int LO = 1000;'
"""


# ============================================================================
# Debugging-Tipps
# ============================================================================

"""
Falls etwas nicht funktioniert:

1. Agent-Logs prüfen:
   $ tail -f ~/.local/share/growdash/agent.log
   
   Sollte zeigen:
   2025-12-04 14:00:25 - ERROR - Kompilierung fehlgeschlagen:
   error: 'LO' was not declared in this scope

2. Laravel-Logs prüfen:
   $ php artisan tail
   
   Sollte zeigen:
   [2025-12-04 14:00:25] local.INFO: Command result received
   {\"command_id\":28,\"status\":\"failed\",\"error\":\"error: 'LO' was not declared...\"}

3. Test Manual:
   import json
   result = {
       'status': 'failed',
       'error': 'Test error',
       'output': 'Test output'
   }
   print(json.dumps(result))
   # Sollte korrekt JSON encodiert sein
   
4. Check JSON Escaping:
   Errors mit \\n sollten korrekt zu \\n\\n werden
"""


# ============================================================================
# Kompatibilität
# ============================================================================

"""
✅ BACKWARDS COMPATIBLE:
  - Old commands (spray_on, fill_start) still work
  - Only return format changed (dict instead of tuple)
  - Laravel backend automatically handles new fields

❌ BREAKING CHANGES:
  - None! Complete backward compatible.
  - New fields are optional in Laravel payload
"""


if __name__ == "__main__":
    import json
    
    print("=" * 70)
    print("AGENT RESULT PAYLOAD EXAMPLES")
    print("=" * 70)
    print()
    
    print("✅ ERFOLG - Kompilierung:")
    print(json.dumps(successful_compile_result, indent=2))
    print()
    
    print("❌ FEHLER - Kompilierung:")
    print(json.dumps(failed_compile_result, indent=2))
    print()
    
    print("📤 PAYLOAD an Laravel (Fehler):")
    print(json.dumps(failed_compile_payload, indent=2))
    print()
