/**
 * Firmware Notification Service
 * Handles Firebase Cloud Messaging for OTA firmware updates
 * 
 * Installation:
 * npm install @react-native-firebase/app @react-native-firebase/messaging
 * 
 * iOS Setup:
 * - Follow: https://rnfirebase.io/messaging/ios-setup
 * 
 * Android Setup:
 * - Follow: https://rnfirebase.io/messaging/android-setup
 */

import messaging from '@react-native-firebase/messaging';
import { Platform, Alert, AppState } from 'react-native';

const FIRMWARE_TOPIC = 'all-users';

class FirmwareNotificationService {
  constructor() {
    this.unsubscribeForeground = null;
    this.onNotificationReceived = null;
  }

  /**
   * Initialize the notification service
   * Call this when your app starts
   */
  async initialize(onNotificationCallback) {
    try {
      // Store callback for notifications
      this.onNotificationReceived = onNotificationCallback;

      // Request notification permissions
      const authStatus = await messaging().requestPermission();
      const enabled =
        authStatus === messaging.AuthorizationStatus.AUTHORIZED ||
        authStatus === messaging.AuthorizationStatus.PROVISIONAL;

      if (!enabled) {
        console.warn('Notification permissions not granted');
        return false;
      }

      // Get FCM token (for debugging)
      const token = await messaging().getToken();
      console.log('FCM Token:', token);

      // Subscribe to firmware updates topic
      await messaging().subscribeToTopic(FIRMWARE_TOPIC);
      console.log('✅ Subscribed to firmware updates topic:', FIRMWARE_TOPIC);

      // Handle foreground messages (when app is open)
      this.unsubscribeForeground = messaging().onMessage(async remoteMessage => {
        console.log('📱 Foreground notification received:', remoteMessage);
        this.handleNotification(remoteMessage);
      });

      // Handle background/quit state messages
      messaging().setBackgroundMessageHandler(async remoteMessage => {
        console.log('📱 Background notification received:', remoteMessage);
        this.handleNotification(remoteMessage);
      });

      // Handle notification taps (when app is opened from notification)
      messaging().onNotificationOpenedApp(remoteMessage => {
        console.log('📱 Notification opened app:', remoteMessage);
        this.handleNotification(remoteMessage, true);
      });

      // Check if app was opened from a notification (app was quit)
      messaging()
        .getInitialNotification()
        .then(remoteMessage => {
          if (remoteMessage) {
            console.log('📱 App opened from notification:', remoteMessage);
            this.handleNotification(remoteMessage, true);
          }
        });

      return true;
    } catch (error) {
      console.error('❌ Failed to initialize notification service:', error);
      return false;
    }
  }

  /**
   * Handle incoming notification
   */
  handleNotification(remoteMessage, fromTap = false) {
    const { data, notification } = remoteMessage;

    // Check if it's a firmware update notification
    if (data?.type === 'firmware_update') {
      const version = data.version || 'unknown';
      const title = notification?.title || `Firmware v${version} Available`;
      const body = notification?.body || 'A new firmware update is available';

      // Call the callback if provided
      if (this.onNotificationReceived) {
        this.onNotificationReceived({
          type: 'firmware_update',
          version,
          title,
          body,
          fromTap,
        });
      } else {
        // Default behavior: show alert
        Alert.alert(
          title,
          body,
          [
            { text: 'Later', style: 'cancel' },
            {
              text: 'Update Now',
              onPress: () => {
                // Navigate to firmware update screen
                // You'll need to implement navigation here
                console.log('Navigate to firmware update for version:', version);
              },
            },
          ]
        );
      }
    }
  }

  /**
   * Unsubscribe from firmware updates
   */
  async unsubscribe() {
    try {
      await messaging().unsubscribeFromTopic(FIRMWARE_TOPIC);
      console.log('Unsubscribed from firmware updates');
    } catch (error) {
      console.error('Failed to unsubscribe:', error);
    }

    if (this.unsubscribeForeground) {
      this.unsubscribeForeground();
    }
  }

  /**
   * Get current FCM token
   */
  async getToken() {
    try {
      return await messaging().getToken();
    } catch (error) {
      console.error('Failed to get FCM token:', error);
      return null;
    }
  }

  /**
   * Delete FCM token (for logout, etc.)
   */
  async deleteToken() {
    try {
      await messaging().deleteToken();
      console.log('FCM token deleted');
    } catch (error) {
      console.error('Failed to delete FCM token:', error);
    }
  }
}

// Export singleton instance
export default new FirmwareNotificationService();

