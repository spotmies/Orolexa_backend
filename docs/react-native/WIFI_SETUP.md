# 📶 WiFi OTA Update Setup Guide

This guide explains how to set up WiFi-based OTA firmware updates where the mobile app acts as an intermediary between the backend and ESP32 device.

## 🔄 Architecture Overview

```
Backend (Railway) → Mobile App → ESP32 Device
     ↓                  ↓              ↓
  Firmware          Downloads      Receives &
  Storage           Firmware        Updates
```

**Flow:**
1. User receives push notification about new firmware
2. User opens app and connects to ESP32 via WiFi (local network)
3. App downloads firmware from backend
4. App uploads firmware to ESP32 over WiFi
5. ESP32 performs OTA update and reboots

## 📱 Mobile App Setup

### 1. Install Dependencies

No special WiFi libraries needed - uses standard React Native `fetch` and `XMLHttpRequest`.

### 2. Network Permissions

#### Android (`AndroidManifest.xml`)
```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
```

#### iOS (`Info.plist`)
```xml
<key>NSAppTransportSecurity</key>
<dict>
    <key>NSAllowsLocalNetworking</key>
    <true/>
</dict>
```

### 3. Connect to ESP32

The ESP32 should be on the same WiFi network as the mobile device. The user enters the device IP address manually, or you can implement device discovery.

## 🔌 ESP32 Setup

### Required ESP32 Endpoints

Your ESP32 firmware should expose these HTTP endpoints:

#### 1. Device Info (`GET /info`)
```json
{
  "name": "ESP32 Device",
  "device_id": "ESP32-ABC123",
  "firmware_version": "1.0.3",
  "chip_model": "ESP32-P4"
}
```

#### 2. Firmware Version (`GET /version`)
```json
{
  "version": "1.0.3"
}
```

#### 3. OTA Update (`POST /update`)
- Accepts multipart/form-data with firmware binary
- Parameters:
  - `firmware`: Binary file (.bin)
  - `version`: Firmware version string
  - `checksum`: SHA256 checksum
- Returns success/error response

### Example ESP32 Code (Arduino/ESP-IDF)

```cpp
#include <WebServer.h>
#include <Update.h>

WebServer server(80);

void handleInfo() {
  server.send(200, "application/json", 
    "{\"name\":\"ESP32 Device\",\"firmware_version\":\"1.0.3\"}");
}

void handleVersion() {
  server.send(200, "application/json", 
    "{\"version\":\"1.0.3\"}");
}

void handleUpdate() {
  HTTPUpload& upload = server.upload();
  
  if (upload.status == UPLOAD_FILE_START) {
    // Start OTA update
    if (!Update.begin(UPDATE_SIZE_UNKNOWN)) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_WRITE) {
    // Write firmware data
    if (Update.write(upload.buf, upload.currentSize) != upload.currentSize) {
      Update.printError(Serial);
    }
  } else if (upload.status == UPLOAD_FILE_END) {
    // Complete OTA update
    if (Update.end(true)) {
      server.send(200, "application/json", 
        "{\"success\":true,\"message\":\"Update complete\"}");
      delay(1000);
      ESP.restart();
    } else {
      Update.printError(Serial);
      server.send(500, "application/json", 
        "{\"success\":false,\"message\":\"Update failed\"}");
    }
  }
}

void setup() {
  // ... WiFi setup ...
  
  server.on("/info", handleInfo);
  server.on("/version", handleVersion);
  server.on("/update", HTTP_POST, []() {
    server.send(200, "application/json", "{\"success\":true}");
  }, handleUpdate);
  
  server.begin();
}
```

## 🔍 Device Discovery (Optional)

### Option 1: Manual IP Entry
- User enters device IP address manually
- Simplest implementation
- Used in current implementation

### Option 2: mDNS/Bonjour
```javascript
// Install: npm install react-native-zeroconf
import Zeroconf from 'react-native-zeroconf';

const zeroconf = new Zeroconf();
zeroconf.scan('http', 'tcp', 'local.');

zeroconf.on('found', (name, service) => {
  if (name.includes('esp32') || name.includes('ota')) {
    // Found ESP32 device
    const ip = service.addresses[0];
    // Connect to device
  }
});
```

### Option 3: Network Scanning
```javascript
// Scan common IP ranges (requires network permissions)
// Note: This may be slow and not recommended for production
const scanNetwork = async (baseIP) => {
  const devices = [];
  for (let i = 1; i < 255; i++) {
    const ip = `${baseIP}.${i}`;
    try {
      const response = await fetch(`http://${ip}/info`, { timeout: 1000 });
      if (response.ok) {
        devices.push({ ip, info: await response.json() });
      }
    } catch (e) {
      // Device not found or not responding
    }
  }
  return devices;
};
```

## 🧪 Testing

### 1. Test ESP32 Endpoints

```bash
# Test device info
curl http://192.168.1.100/info

# Test version
curl http://192.168.1.100/version

# Test update endpoint (with firmware file)
curl -X POST -F "firmware=@firmware.bin" -F "version=1.0.4" \
  http://192.168.1.100/update
```

### 2. Test Mobile App

1. **Connect to Device:**
   - Enter ESP32 IP address
   - Tap "Connect to Device"
   - Should show connected status

2. **Check for Updates:**
   - Tap "Check for Updates"
   - Should fetch latest version from backend

3. **Perform Update:**
   - If update available, tap "Update"
   - Monitor progress bar
   - Device should reboot after update

## 🔒 Security Considerations

### 1. Local Network Security
- ESP32 should only accept connections from local network
- Consider adding authentication for `/update` endpoint
- Use HTTPS if possible (requires SSL certificate on ESP32)

### 2. Firmware Verification
- Always verify checksum before flashing
- ESP32 should verify checksum after receiving firmware
- Reject firmware if checksum doesn't match

### 3. Network Isolation
- ESP32 should be on isolated network segment if possible
- Use firewall rules to restrict access
- Consider VPN for remote updates

## 🐛 Troubleshooting

### Device Not Found
- **Check IP address** - Ensure correct IP entered
- **Check network** - Device and phone on same WiFi network
- **Check firewall** - ESP32 firewall may block connections
- **Check ESP32 server** - Verify HTTP server is running

### Upload Fails
- **Check file size** - ESP32 may have size limits
- **Check memory** - Ensure enough free space for OTA partition
- **Check timeout** - Increase timeout for large files
- **Check ESP32 logs** - Review serial output for errors

### Update Doesn't Apply
- **Check checksum** - Verify checksum matches
- **Check OTA partition** - Ensure OTA partition is configured
- **Check reboot** - Device should reboot after update
- **Check version** - Verify new version after reboot

## 📊 Monitoring

### Backend Monitoring
- Check `/api/firmware/reports` for OTA status
- Monitor success/failure rates
- Track device IPs and versions

### ESP32 Monitoring
- Log OTA attempts to serial
- Report status to backend after update
- Store update history in NVS

## ✅ Checklist

- [ ] ESP32 HTTP server running
- [ ] `/info`, `/version`, `/update` endpoints implemented
- [ ] Mobile app can connect to ESP32
- [ ] Mobile app can download firmware from backend
- [ ] Mobile app can upload firmware to ESP32
- [ ] Progress tracking works
- [ ] Error handling implemented
- [ ] Status reporting to backend works
- [ ] Device reboots with new firmware
- [ ] Version verification after update

---

**Note:** This implementation uses HTTP (not HTTPS) for local network communication. For production, consider implementing HTTPS with self-signed certificates or using a more secure method.

