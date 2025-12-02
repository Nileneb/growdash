# Generic Serial Device Support - Implementation Summary

## ✅ Implemented Changes

### 1. USBScanner Improvements (`usb_device_manager.py`)

#### ✨ Key Features:

- **Accepts ALL serial devices** (`/dev/ttyACM*`, `/dev/ttyUSB*`, `COM*`)
- **VID/PID-based classification** with known board mappings
- **Keyword hints** for fallback classification (not hard requirement)
- **Board types**: `arduino_uno`, `arduino_nano`, `esp32`, `generic_serial`

#### 🔧 Code Changes:

```python
@dataclass
class USBDeviceInfo:
    port: str
    vendor_id: Optional[str] = None
    product_id: Optional[str] = None
    description: Optional[str] = None
    board_type: str = "generic_serial"  # ← NEU
```

**Known Boards Mapping:**

```python
KNOWN_BOARDS = {
    ("2341", "0043"): "arduino_uno",
    ("1a86", "7523"): "arduino_nano",  # CH340
    ("0403", "6001"): "arduino_nano",  # FTDI
    ("10c4", "ea60"): "esp32",         # CP2102
    # ... erweiterbar
}
```

### 2. Handshake Detection

#### 🤝 New Method: `USBScanner.try_handshake()`

- Sendet `"Status\n"` an Device
- Wartet auf Response (configurable timeout)
- Returns `True` wenn Device antwortet
- **Use case**: Unterscheidung zwischen Arduino-Boards und generic serial devices

```python
has_protocol = USBScanner.try_handshake("/dev/ttyUSB0", baud=9600, timeout=3.0)
```

### 3. Agent-Laravel Communication

#### 📡 Extended Heartbeat Payload:

```json
{
  "last_state": {
    "uptime": 3600,
    "memory_free": 512000,
    "python_version": "3.11.0",
    "platform": "linux"
  },
  "board_type": "generic_serial", // ← NEU
  "port": "/dev/ttyUSB0", // ← NEU
  "vendor_id": "1a86", // ← NEU
  "product_id": "7523", // ← NEU
  "description": "USB Serial Device" // ← NEU
}
```

#### 📡 Extended Capabilities Payload:

```json
{
  "capabilities": {
    "board_name": "arduino_uno",
    "sensors": ["water_level", "tds"],
    "actuators": ["spray_pump", "fill_valve"]
  },
  "board_type": "generic_serial", // ← NEU
  "port": "/dev/ttyUSB0", // ← NEU
  "vendor_id": "1a86", // ← NEU
  "product_id": "7523", // ← NEU
  "description": "USB Serial Device" // ← NEU
}
```

### 4. DeviceInstance Integration

- `DeviceInstance` now stores `USBDeviceInfo`
- `HardwareAgent` receives `device_info` parameter
- Device info automatically included in heartbeat/capabilities

## 🎯 Laravel Implementation Requirements

### Database Schema

#### New Table: `board_types`

```sql
CREATE TABLE board_types (
    id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    vendor_id VARCHAR(4) NOT NULL,
    product_id VARCHAR(4) NOT NULL,
    board_type VARCHAR(50) NOT NULL,
    description TEXT NULL,
    serial_config JSON NULL,
    sensor_capabilities JSON NULL,
    actuator_capabilities JSON NULL,
    created_at TIMESTAMP NULL,
    updated_at TIMESTAMP NULL,
    UNIQUE KEY unique_vid_pid (vendor_id, product_id)
);
```

#### Extend `devices` Table:

```sql
ALTER TABLE devices
ADD COLUMN board_type VARCHAR(50) NULL,
ADD COLUMN vendor_id VARCHAR(4) NULL,
ADD COLUMN product_id VARCHAR(4) NULL,
ADD COLUMN port VARCHAR(50) NULL,
ADD COLUMN is_configured BOOLEAN DEFAULT FALSE;
```

### Backend Endpoints

#### `POST /agent/heartbeat`

- Accept extended payload with hardware info
- Check if `board_type === 'generic_serial' && !is_configured`
- Trigger `UnknownDeviceDetected` event
- Auto-configure if VID/PID mapping exists in `board_types`

#### `POST /agent/capabilities`

- Accept extended payload
- Store capabilities and hardware info

#### `POST /admin/board-profiles` (NEW)

- Save custom board profile
- Create VID/PID mapping in `board_types`
- Mark device as configured

### UI: Unknown Device Wizard

#### Step 1: Board Profile Selection

- Choose from predefined profiles or create custom

#### Step 2: Serial Protocol Configuration

- Baud rate
- Protocol type (line-based, binary, JSON)
- Delimiters and handshake

#### Step 3: Capabilities Definition

- Define sensors (key, name, unit, parse pattern)
- Define actuators (key, name, commands)

#### Step 4: Save & Test

- Test connection
- Save profile with VID/PID mapping
- Auto-apply to future devices

## 📋 Workflow Example

### First Time: Unknown Device

1. **User connects device** → `/dev/ttyUSB0`
2. **Agent detects** → `generic_serial` (VID:`1a86`, PID:`7523`)
3. **Agent sends heartbeat** → with hardware info
4. **Laravel checks** → No mapping found
5. **UI shows** → "Unknown device detected" banner
6. **User clicks** → "Configure Device"
7. **Wizard guides** → Protocol & capability setup
8. **User saves** → Profile as "my_custom_board"
9. **Laravel stores** → VID/PID mapping in DB
10. **Device configured** → `is_configured = true`

### Next Time: Auto-Recognition

1. **Agent sends heartbeat** → VID:`1a86`, PID:`7523`
2. **Laravel finds** → Mapping in `board_types`
3. **Auto-configure** → Device as "my_custom_board"
4. **Ready to use** → No wizard needed!

## 🧪 Testing Checklist

- [ ] Test with Arduino Uno → should detect as `arduino_uno`
- [ ] Test with Arduino Nano (CH340) → should detect as `arduino_nano`
- [ ] Test with ESP32 → should detect as `esp32`
- [ ] Test with unknown USB-Serial → should detect as `generic_serial`
- [ ] Test handshake with responding device
- [ ] Test handshake with non-responding device
- [ ] Verify heartbeat includes board_type
- [ ] Verify capabilities includes hardware info
- [ ] Test multi-device with mixed board types

## 📚 Documentation

See `docs/GENERIC_SERIAL_SUPPORT.md` for:

- Detailed implementation guide
- Laravel backend examples
- UI wizard specification
- Migration guide
- FAQ and troubleshooting

## 🚀 Next Steps

### Immediate:

1. Implement Laravel endpoints
2. Create database migrations
3. Build UI wizard component
4. Test with real devices

### Future Enhancements:

- Board profile import/export
- Community board library
- Auto-protocol detection
- Multi-protocol support (Modbus, I2C)
- Virtual device emulator for testing

## 🎉 Benefits

✅ **Flexibilität**: Support für beliebige serielle Geräte  
✅ **User-Friendly**: Wizard-basierte Konfiguration  
✅ **Persistent**: VID/PID Mappings für Auto-Recognition  
✅ **Skalierbar**: Leicht erweiterbar für neue Board-Typen  
✅ **Robust**: Keywords nur als Hints, keine harten Bedingungen
