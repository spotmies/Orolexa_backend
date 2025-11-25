# 🔥 Firebase Setup Guide for OTA Push Notifications

This guide explains how to set up Firebase Cloud Messaging (FCM) to send push notifications when new firmware is uploaded.

## 📋 Prerequisites

- Google account
- Firebase project (or create a new one)
- React Native app with Firebase SDK installed

## 🚀 Step-by-Step Setup

### Step 1: Create/Select Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **"Add project"** or select an existing project
3. Enter project name (e.g., "Orolexa OTA")
4. Follow the setup wizard (disable Google Analytics if not needed)

### Step 2: Enable Cloud Messaging (FCM)

1. In Firebase Console, go to **Project Settings** (gear icon)
2. Click on **"Cloud Messaging"** tab
3. Ensure **Cloud Messaging API (Legacy)** is enabled
   - If not, go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to **APIs & Services** → **Library**
   - Search for "Firebase Cloud Messaging API"
   - Click **Enable**

### Step 3: Create Service Account

1. In Firebase Console, go to **Project Settings** → **Service Accounts** tab
2. Click **"Generate new private key"**
3. Click **"Generate key"** in the dialog
4. A JSON file will download (e.g., `orolexa-ota-firebase-adminsdk-xxxxx.json`)

**⚠️ IMPORTANT:** Keep this file secure! Never commit it to git.

### Step 4: Extract Credentials from JSON

Open the downloaded JSON file. You'll see something like:

```json
{
  "type": "service_account",
  "project_id": "orolexa-ota",
  "private_key_id": "abc123...",
  "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
  "client_email": "firebase-adminsdk-xxxxx@orolexa-ota.iam.gserviceaccount.com",
  "client_id": "123456789",
  "auth_uri": "https://accounts.google.com/o/oauth2/auth",
  "token_uri": "https://oauth2.googleapis.com/token",
  "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
  "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/..."
}
```

You need these three values:
- `project_id` → `FIREBASE_PROJECT_ID`
- `private_key` → `FIREBASE_PRIVATE_KEY` (keep the `\n` characters)
- `client_email` → `FIREBASE_CLIENT_EMAIL`

### Step 5: Configure Environment Variables

Add these to your `.env` file:

```env
# Firebase Configuration
FIREBASE_PROJECT_ID=orolexa-ota
FIREBASE_CLIENT_EMAIL=firebase-adminsdk-xxxxx@orolexa-ota.iam.gserviceaccount.com
FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nMIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC...\n-----END PRIVATE KEY-----\n"
FIREBASE_TOPIC_ALL_USERS=all-users
```

**Important Notes:**
- Keep the `\n` characters in `FIREBASE_PRIVATE_KEY` (they represent newlines)
- Wrap the private key in quotes if it contains special characters
- In Railway/production, set these as environment variables (not in a file)

### Step 6: Configure React Native App

Your React Native app needs to:

1. **Install Firebase SDK:**
   ```bash
   npm install @react-native-firebase/app @react-native-firebase/messaging
   ```

2. **Subscribe to Topic on App Start:**
   ```javascript
   import messaging from '@react-native-firebase/messaging';
   
   // Subscribe to 'all-users' topic when app starts
   async function subscribeToFirmwareUpdates() {
     try {
       await messaging().subscribeToTopic('all-users');
       console.log('Subscribed to firmware updates');
     } catch (error) {
       console.error('Failed to subscribe:', error);
     }
   }
   
   // Call this when app initializes
   subscribeToFirmwareUpdates();
   ```

3. **Handle Notifications:**
   ```javascript
   // Handle foreground notifications
   messaging().onMessage(async remoteMessage => {
     if (remoteMessage.data?.type === 'firmware_update') {
       // Show notification to user
       // Navigate to firmware update screen
       console.log('New firmware available:', remoteMessage.data.version);
     }
   });
   
   // Handle background/quit notifications
   messaging().setBackgroundMessageHandler(async remoteMessage => {
     if (remoteMessage.data?.type === 'firmware_update') {
       // Handle notification
     }
   });
   ```

### Step 7: Test the Setup

1. **Upload firmware** (this will trigger a notification):
   ```bash
   python scripts/upload_firmware.py --version 1.0.5 --file firmware.bin
   ```

2. **Check backend logs** for:
   ```
   INFO: Firebase app initialized for notifications
   INFO: Firmware notification sent successfully: projects/.../messages/...
   ```

3. **Check React Native app** - you should receive a push notification

## 🔍 Troubleshooting

### Issue: "Firebase credentials not configured"
- **Solution:** Check that all three environment variables are set correctly
- Verify `FIREBASE_PRIVATE_KEY` includes `\n` characters

### Issue: "Permission denied" when sending notifications
- **Solution:** Ensure Cloud Messaging API is enabled in Google Cloud Console
- Check that the service account has proper permissions

### Issue: Notifications not received in app
- **Solution:** 
  - Verify app is subscribed to `all-users` topic
  - Check Firebase Console → Cloud Messaging → check delivery reports
  - Ensure app has proper notification permissions

### Issue: Private key format error
- **Solution:** The private key must include `\n` characters. In your `.env`:
  ```env
  FIREBASE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\nYOUR_KEY_HERE\n-----END PRIVATE KEY-----\n"
  ```

## 📱 React Native App Integration Example

Complete example for React Native:

```javascript
// App.js or App.tsx
import React, { useEffect } from 'react';
import messaging from '@react-native-firebase/messaging';

function App() {
  useEffect(() => {
    // Request notification permissions
    messaging().requestPermission();
    
    // Subscribe to firmware updates topic
    messaging()
      .subscribeToTopic('all-users')
      .then(() => console.log('Subscribed to firmware updates'))
      .catch(err => console.error('Subscription error:', err));
    
    // Handle foreground messages
    const unsubscribe = messaging().onMessage(async remoteMessage => {
      if (remoteMessage.data?.type === 'firmware_update') {
        Alert.alert(
          `Firmware v${remoteMessage.data.version} Available`,
          remoteMessage.notification?.body || 'A new firmware update is available',
          [
            { text: 'Later', style: 'cancel' },
            { 
              text: 'Update Now', 
              onPress: () => {
                // Navigate to firmware update screen
                navigation.navigate('FirmwareUpdate', {
                  version: remoteMessage.data.version
                });
              }
            }
          ]
        );
      }
    });
    
    return unsubscribe;
  }, []);
  
  return (
    // Your app components
  );
}
```

## 🔒 Security Best Practices

1. **Never commit** the service account JSON file to git
2. **Use environment variables** in production (Railway, etc.)
3. **Rotate keys** periodically
4. **Limit service account permissions** to only what's needed
5. **Monitor** notification delivery in Firebase Console

## 📊 Monitoring

- **Firebase Console** → Cloud Messaging → View delivery reports
- **Backend logs** → Check for notification send success/failure
- **React Native logs** → Check subscription and message receipt

## ✅ Verification Checklist

- [ ] Firebase project created
- [ ] Cloud Messaging API enabled
- [ ] Service account created and JSON downloaded
- [ ] Environment variables set in `.env`
- [ ] Backend can initialize Firebase (check logs)
- [ ] React Native app subscribes to `all-users` topic
- [ ] Test notification sent and received

---

For more information, see:
- [Firebase Cloud Messaging Documentation](https://firebase.google.com/docs/cloud-messaging)
- [React Native Firebase Documentation](https://rnfirebase.io/messaging/usage)

