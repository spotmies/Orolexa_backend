/**
 * App Integration Example
 * Shows how to integrate firmware notifications into your main App component
 */

import React, { useEffect, useState } from 'react';
import { NavigationContainer } from '@react-navigation/native';
import { createStackNavigator } from '@react-navigation/stack';
import { Alert, AppState } from 'react-native';
import FirmwareNotificationService from './FirmwareNotificationService';
import FirmwareUpdateScreen from './FirmwareUpdateScreen';
import HomeScreen from './HomeScreen'; // Your existing screens
// ... import other screens

const Stack = createStackNavigator();

function App() {
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    // Initialize notification service when app starts
    initializeNotifications();
    
    // Handle app state changes
    const subscription = AppState.addEventListener('change', handleAppStateChange);
    
    return () => {
      subscription.remove();
      // Cleanup: unsubscribe when app closes
      FirmwareNotificationService.unsubscribe();
    };
  }, []);

  /**
   * Initialize Firebase notifications
   */
  const initializeNotifications = async () => {
    const success = await FirmwareNotificationService.initialize(
      handleFirmwareNotification
    );
    
    if (success) {
      console.log('✅ Notification service initialized');
      setInitialized(true);
    } else {
      console.warn('⚠️ Notification service initialization failed');
    }
  };

  /**
   * Handle incoming firmware update notifications
   */
  const handleFirmwareNotification = (notification) => {
    console.log('📱 Firmware notification received:', notification);
    
    const { version, title, body, fromTap } = notification;
    
    // If notification was tapped, navigate directly to update screen
    if (fromTap) {
      // Use navigation ref or context to navigate
      // navigationRef.current?.navigate('FirmwareUpdate', { version });
      return;
    }
    
    // If app is in foreground, show alert
    if (AppState.currentState === 'active') {
      Alert.alert(
        title,
        body,
        [
          {
            text: 'Later',
            style: 'cancel',
          },
          {
            text: 'Update Now',
            onPress: () => {
              // Navigate to firmware update screen
              // navigationRef.current?.navigate('FirmwareUpdate', { version });
            },
          },
        ],
        { cancelable: true }
      );
    }
  };

  /**
   * Handle app state changes
   */
  const handleAppStateChange = (nextAppState) => {
    if (nextAppState === 'active') {
      // App came to foreground - check for updates
      console.log('App is now active');
    }
  };

  return (
    <NavigationContainer>
      <Stack.Navigator initialRouteName="Home">
        <Stack.Screen 
          name="Home" 
          component={HomeScreen}
          options={{ title: 'Home' }}
        />
        <Stack.Screen
          name="FirmwareUpdate"
          component={FirmwareUpdateScreen}
          options={{ title: 'Firmware Update' }}
        />
        {/* Add your other screens here */}
      </Stack.Navigator>
    </NavigationContainer>
  );
}

export default App;

