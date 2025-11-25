# ✅ React Native Integration Checklist

Use this checklist to ensure complete integration of the OTA firmware update system.

## 📋 Pre-Integration

- [ ] React Native project is set up and running
- [ ] Backend is deployed and accessible at: `https://orolexabackend-production.up.railway.app`
- [ ] Backend firmware endpoints are working (test with curl/Postman)

## 📦 Step 1: Install Dependencies

```bash
# Firebase Cloud Messaging
npm install @react-native-firebase/app @react-native-firebase/messaging

# BLE Communication (choose one)
npm install react-native-ble-manager
# OR
npm install react-native-ble-plx

# For iOS, run:
cd ios && pod install && cd ..
```

- [ ] Dependencies installed successfully
- [ ] iOS pods installed (if using iOS)

## 🔥 Step 2: Firebase Setup

- [ ] Firebase project created
- [ ] iOS: `GoogleService-Info.plist` added to iOS project
- [ ] Android: `google-services.json` added to Android project
- [ ] Cloud Messaging API enabled in Firebase Console
- [ ] Service account created and credentials added to backend `.env`

## 📁 Step 3: Copy Files

```bash
# Create directories if they don't exist
mkdir -p src/services src/screens

# Copy files
cp docs/react-native/FirmwareNotificationService.js src/services/
cp docs/react-native/FirmwareUpdateScreen.js src/screens/
cp docs/react-native/config.js src/config/
cp docs/react-native/AppIntegration.js src/  # Reference only
```

- [ ] Files copied to project
- [ ] Import paths updated if needed

## ⚙️ Step 4: Configuration

- [ ] Backend URL verified in `config.js`: `https://orolexabackend-production.up.railway.app`
- [ ] Firebase topic name matches backend: `all-users`
- [ ] API endpoints are correct

## 🔌 Step 5: BLE Configuration

- [ ] ESP32 BLE service UUID identified
- [ ] ESP32 BLE characteristic UUIDs identified:
  - [ ] Firmware version characteristic
  - [ ] OTA control characteristic
  - [ ] OTA progress characteristic
- [ ] BLE UUIDs updated in `FirmwareUpdateScreen.js`
- [ ] BLE permissions added to Android `AndroidManifest.xml`
- [ ] BLE permissions added to iOS `Info.plist`

## 🧩 Step 6: App Integration

### Update App.js/App.tsx

- [ ] Import `FirmwareNotificationService`
- [ ] Initialize notification service in `useEffect`
- [ ] Handle notification callback
- [ ] Add navigation to FirmwareUpdate screen

### Navigation Setup

- [ ] `FirmwareUpdateScreen` added to navigation stack
- [ ] Route name matches: `'FirmwareUpdate'`
- [ ] Navigation ref set up (if using programmatic navigation)

## 🧪 Step 7: Testing

### Backend Testing

- [ ] Test `/api/firmware/latest` endpoint
  ```bash
  curl https://orolexabackend-production.up.railway.app/api/firmware/latest
  ```
- [ ] Test `/api/firmware/download` endpoint
- [ ] Upload test firmware via script

### Firebase Testing

- [ ] App subscribes to `all-users` topic (check logs)
- [ ] FCM token received (check logs)
- [ ] Test notification sent from Firebase Console
- [ ] Notification received in app

### Integration Testing

- [ ] App can check for latest firmware
- [ ] App displays firmware version correctly
- [ ] BLE device connection works
- [ ] Firmware version read from ESP32
- [ ] OTA update command sent to ESP32
- [ ] Progress updates received
- [ ] OTA status reported to backend

## 🔒 Step 8: Security & Production

- [ ] HTTPS enforced (backend uses HTTPS)
- [ ] API credentials secured (not in code)
- [ ] Firebase service account key secured
- [ ] Error handling implemented
- [ ] User permissions requested properly

## 📱 Step 9: User Experience

- [ ] Notification permissions requested
- [ ] Clear update prompts shown
- [ ] Progress indicator works
- [ ] Error messages are user-friendly
- [ ] Success feedback provided

## 🐛 Troubleshooting

If something doesn't work:

- [ ] Check backend logs for errors
- [ ] Check React Native logs (Metro bundler)
- [ ] Check Firebase Console for notification delivery
- [ ] Verify BLE permissions are granted
- [ ] Test API endpoints directly with curl/Postman
- [ ] Check network connectivity

## 📊 Monitoring

- [ ] Backend logs monitored
- [ ] Firebase Console checked regularly
- [ ] OTA success rate tracked
- [ ] Error reports reviewed

## ✅ Final Verification

- [ ] Upload firmware → Notification sent
- [ ] User receives notification
- [ ] User taps notification → Navigates to update screen
- [ ] User connects device → Version displayed
- [ ] User triggers update → Progress shown
- [ ] Update completes → Status reported
- [ ] Device reboots with new firmware

---

## 🚀 Quick Test Commands

### Test Backend
```bash
# Check latest firmware
curl https://orolexabackend-production.up.railway.app/api/firmware/latest

# Health check
curl https://orolexabackend-production.up.railway.app/health
```

### Test Upload (from backend directory)
```bash
python scripts/upload_firmware.py \
  --version 1.0.5 \
  --file firmware.bin \
  --base-url https://orolexabackend-production.up.railway.app \
  --admin-user admin \
  --admin-pass YOUR_PASSWORD
```

---

**Backend URL**: `https://orolexabackend-production.up.railway.app`  
**API Docs**: `https://orolexabackend-production.up.railway.app/docs`

