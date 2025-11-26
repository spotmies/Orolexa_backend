# 🚀 Quick Start Guide - React Native Integration

Your backend is ready at: **https://orolexabackend-production.up.railway.app**

## Step-by-Step Integration

### 1️⃣ Copy Files to Your React Native Project

```bash
# Navigate to your React Native project root
cd /path/to/your/react-native-project

# Create directories
mkdir -p src/services src/screens src/config

# Copy files from backend docs
cp docs/react-native/FirmwareNotificationService.js src/services/
cp docs/react-native/WiFiDeviceService.js src/services/
cp docs/react-native/FirmwareUpdateScreen.js src/screens/
cp docs/react-native/config.js src/config/
```

### 2️⃣ Install Dependencies

```bash
# Firebase Cloud Messaging
npm install @react-native-firebase/app @react-native-firebase/messaging

# No WiFi library needed - uses standard React Native fetch/XMLHttpRequest

# For iOS
cd ios && pod install && cd ..
```

### 3️⃣ Update Import Paths

In `FirmwareUpdateScreen.js`, update the import:

```javascript
// Change this line:
import API_CONFIG from '../config/config'; // Adjust path as needed

// To match your project structure:
// If config.js is in src/config/ → import API_CONFIG from '../config/config';
// If config.js is in src/ → import API_CONFIG from '../config';
// If config.js is in same folder → import API_CONFIG from './config';
```

### 4️⃣ Verify Backend URL

The backend URL is already configured in `src/config/config.js`:

```javascript
BASE_URL: 'https://orolexabackend-production.up.railway.app'
```

✅ **No changes needed** - it's already set to your production backend!

### 5️⃣ Integrate into App.js

Add this to your main `App.js` or `App.tsx`:

```javascript
import React, { useEffect } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import FirmwareNotificationService from './src/services/FirmwareNotificationService';
import FirmwareUpdateScreen from './src/screens/FirmwareUpdateScreen';

// ... your navigation setup ...

function App() {
  useEffect(() => {
    // Initialize notification service
    FirmwareNotificationService.initialize((notification) => {
      if (notification.type === 'firmware_update') {
        // Navigate to firmware update screen
        // Use your navigation method here
        navigation.navigate('FirmwareUpdate', {
          version: notification.version
        });
      }
    });
  }, []);

  // ... rest of your app
}
```

### 6️⃣ Add to Navigation

Add the FirmwareUpdate screen to your navigation stack:

```javascript
import FirmwareUpdateScreen from './src/screens/FirmwareUpdateScreen';

// In your Stack Navigator:
<Stack.Screen
  name="FirmwareUpdate"
  component={FirmwareUpdateScreen}
  options={{ title: 'Firmware Update' }}
/>
```

### 7️⃣ Configure Firebase

Follow the Firebase setup guide: `docs/FIREBASE_SETUP.md`

Key steps:
- Create Firebase project
- Add `GoogleService-Info.plist` (iOS) and `google-services.json` (Android)
- Enable Cloud Messaging API
- Add service account credentials to backend `.env`

### 7️⃣ Setup ESP32 WiFi Server

Your ESP32 needs to expose HTTP endpoints for OTA updates. See **WIFI_SETUP.md** for complete guide.

Required endpoints:
- `GET /info` - Device information
- `GET /version` - Current firmware version  
- `POST /update` - OTA update endpoint

The mobile app will connect to ESP32 via WiFi (same local network) and upload firmware directly.

## ✅ Testing

### Test Backend Connection

```bash
# Check if backend is accessible
curl https://orolexabackend-production.up.railway.app/health

# Check latest firmware
curl https://orolexabackend-production.up.railway.app/api/firmware/latest
```

### Test in App

1. **Check for Updates**: Open FirmwareUpdate screen → Should fetch latest version
2. **Connect Device**: Connect ESP32 via BLE → Should show connected status
3. **Trigger Update**: Tap "Update" → Should start OTA process

## 📝 Important Notes

- **Backend URL**: Already configured to `https://orolexabackend-production.up.railway.app`
- **API Endpoints**: All endpoints use the centralized config
- **Firebase Topic**: Uses `all-users` topic (configurable in backend)
- **HTTPS**: All API calls use HTTPS (secure)

## 🔗 Useful Links

- **Backend API Docs**: https://orolexabackend-production.up.railway.app/docs
- **Backend Health**: https://orolexabackend-production.up.railway.app/health
- **Firebase Setup Guide**: `docs/FIREBASE_SETUP.md`
- **Full Integration Guide**: `docs/react-native/README.md`
- **Integration Checklist**: `docs/react-native/INTEGRATION_CHECKLIST.md`

## 🐛 Troubleshooting

### Import Errors
- Check that file paths match your project structure
- Verify all files are copied to correct locations

### Backend Connection Errors
- Verify backend is running: https://orolexabackend-production.up.railway.app/health
- Check network connectivity
- Verify CORS settings allow your app origin

### Firebase Errors
- Verify Firebase setup is complete
- Check that `GoogleService-Info.plist` / `google-services.json` are added
- Verify service account credentials in backend

---

**Ready to go!** Your backend is configured and ready. Just copy the files and integrate! 🚀

