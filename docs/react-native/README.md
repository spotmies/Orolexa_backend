# React Native Integration Guide

This directory contains React Native code examples for integrating OTA firmware updates with your backend.

## 📁 Files

- **FirmwareNotificationService.js** - Service for handling Firebase push notifications
- **FirmwareUpdateScreen.js** - UI screen for displaying and triggering firmware updates (WiFi-based)
- **WiFiDeviceService.js** - Service for WiFi connection and communication with ESP32
- **AppIntegration.js** - Example of integrating notifications into your main App component
- **WIFI_SETUP.md** - Complete guide for WiFi OTA setup

## 🚀 Quick Start

### 1. Install Dependencies

```bash
npm install @react-native-firebase/app @react-native-firebase/messaging
# No WiFi library needed - uses standard React Native fetch/XMLHttpRequest
```

### 2. Firebase Setup

Follow the platform-specific setup guides:
- **iOS**: https://rnfirebase.io/messaging/ios-setup
- **Android**: https://rnfirebase.io/messaging/android-setup

### 3. Copy Files to Your Project

Copy the files from this directory to your React Native project:

```bash
# Copy notification service
cp docs/react-native/FirmwareNotificationService.js src/services/

# Copy WiFi device service
cp docs/react-native/WiFiDeviceService.js src/services/

# Copy firmware update screen
cp docs/react-native/FirmwareUpdateScreen.js src/screens/

# Copy config
cp docs/react-native/config.js src/config/

# Update your App.js with integration example
```

### 4. Configure Backend URL

The backend URL is already configured in `config.js`:

```javascript
// config.js
export const API_CONFIG = {
  BASE_URL: 'https://orolexabackend-production.up.railway.app',
  // ...
};
```

If you need to change it, update `config.js` instead of individual files.

### 5. Integrate into Your App

Add the notification service initialization to your main App component:

```javascript
import FirmwareNotificationService from './services/FirmwareNotificationService';

// In your App component
useEffect(() => {
  FirmwareNotificationService.initialize((notification) => {
    // Handle notification
    if (notification.type === 'firmware_update') {
      navigation.navigate('FirmwareUpdate', {
        version: notification.version
      });
    }
  });
}, []);
```

## 📱 Features

### ✅ What's Included

- **Firebase Cloud Messaging Integration**
  - Automatic subscription to `all-users` topic
  - Foreground and background notification handling
  - Notification tap handling

- **Firmware Update UI**
  - Display current and latest firmware versions
  - Check for updates from backend
  - Trigger OTA updates via BLE
  - Progress tracking

- **Device Connection**
  - BLE connection status
  - Device scanning and connection
  - Firmware version reading

### 🔧 Customization Needed

You'll need to customize:

1. **BLE Implementation**
   - Replace placeholder BLE code with your actual implementation
   - Define your service UUIDs and characteristic UUIDs
   - Implement OTA command sending

2. **Navigation**
   - Integrate with your navigation library (React Navigation, etc.)
   - Add navigation refs for programmatic navigation

3. **Device-Specific Logic**
   - ESP32 BLE service/characteristic UUIDs
   - OTA command format
   - Progress reporting mechanism

## 📶 ESP32 WiFi Integration

### Required ESP32 HTTP Endpoints

Your ESP32 should expose these HTTP endpoints on the local network:

1. **`GET /info`** - Device information
2. **`GET /version`** - Current firmware version
3. **`POST /update`** - OTA update endpoint (multipart/form-data)

See **WIFI_SETUP.md** for complete ESP32 implementation guide.

### Example ESP32 Endpoints

```cpp
// GET /info
server.on("/info", []() {
  server.send(200, "application/json", 
    "{\"name\":\"ESP32\",\"firmware_version\":\"1.0.3\"}");
});

// GET /version
server.on("/version", []() {
  server.send(200, "application/json", "{\"version\":\"1.0.3\"}");
});

// POST /update - Handles firmware upload
server.on("/update", HTTP_POST, handleUpdate);
```

### Mobile App Connection

```javascript
import WiFiDeviceService from './services/WiFiDeviceService';

// Connect to ESP32 (user enters IP: 192.168.1.100)
await WiFiDeviceService.connectToDevice('192.168.1.100');

// Get device version
const version = await WiFiDeviceService.getDeviceVersion();

// Upload firmware
await WiFiDeviceService.uploadFirmware(
  firmwareData,
  version,
  checksum,
  (progress) => console.log(`Progress: ${progress}%`)
);
```

## 📊 API Integration

### Check Latest Firmware

```javascript
import API_CONFIG from './config';

const response = await fetch(API_CONFIG.getUrl(API_CONFIG.ENDPOINTS.FIRMWARE_LATEST));
const firmwareInfo = await response.json();
// Returns: { version, filename, checksum, file_size, url, release_notes, ... }
```

### Download Firmware

```javascript
import API_CONFIG from './config';

const response = await fetch(API_CONFIG.getUrl(API_CONFIG.ENDPOINTS.FIRMWARE_DOWNLOAD));
const firmwareBinary = await response.arrayBuffer();
// Send to ESP32 via BLE or Wi-Fi
```

### Report OTA Status

```javascript
import API_CONFIG from './config';

await fetch(API_CONFIG.getUrl(API_CONFIG.ENDPOINTS.FIRMWARE_REPORT), {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    device_id: 'ESP32-ABC123',
    firmware_version: '1.0.4',
    status: 'success', // or 'failed', 'in_progress'
    progress_percent: 100,
    error_message: null
  })
});
```

## 🧪 Testing

### Test Notification Reception

1. Upload firmware to backend
2. Check app logs for subscription confirmation
3. Verify notification is received
4. Test notification tap navigation

### Test OTA Update Flow

1. Connect to ESP32 device via BLE
2. Navigate to Firmware Update screen
3. Check for latest firmware
4. Trigger update
5. Monitor progress
6. Verify device reboots with new firmware

## 🔒 Security Considerations

- **HTTPS Only**: Always use HTTPS in production
- **Token Validation**: Validate FCM tokens on backend if needed
- **Device Authentication**: Implement device authentication for OTA commands
- **Checksum Verification**: Always verify firmware checksum before flashing

## 📚 Additional Resources

- [React Native Firebase Documentation](https://rnfirebase.io/)
- [Firebase Cloud Messaging](https://firebase.google.com/docs/cloud-messaging)
- [React Native BLE Manager](https://github.com/innoveit/react-native-ble-manager)
- [ESP32 OTA Updates](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/system/ota.html)

## 🐛 Troubleshooting

### Notifications Not Received

- Verify Firebase setup is correct
- Check app is subscribed to `all-users` topic
- Verify notification permissions are granted
- Check Firebase Console for delivery reports

### WiFi Connection Issues

- Verify ESP32 and phone are on same WiFi network
- Check ESP32 IP address is correct
- Ensure ESP32 HTTP server is running
- Test endpoints with curl/Postman first
- Check firewall settings on router

### OTA Update Fails

- Verify firmware URL is accessible
- Check ESP32 has enough free space
- Verify checksum matches
- Check device logs for errors

