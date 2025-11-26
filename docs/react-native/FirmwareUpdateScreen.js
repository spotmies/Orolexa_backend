/**
 * Firmware Update Screen
 * Screen for displaying firmware update information and triggering OTA updates
 * 
 * WiFi-based OTA: Mobile app downloads firmware from backend and uploads to ESP32 over WiFi
 */

import React, { useState, useEffect } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
  ScrollView,
  TextInput,
} from 'react-native';
import { useNavigation, useRoute } from '@react-navigation/native';
import WiFiDeviceService from './WiFiDeviceService';
import API_CONFIG from '../config/config';

const FirmwareUpdateScreen = () => {
  const navigation = useNavigation();
  const route = useRoute();
  const [firmwareInfo, setFirmwareInfo] = useState(null);
  const [currentVersion, setCurrentVersion] = useState(null);
  const [isUpdating, setIsUpdating] = useState(false);
  const [updateProgress, setUpdateProgress] = useState(0);
  const [isConnected, setIsConnected] = useState(false);
  const [deviceIP, setDeviceIP] = useState('');
  const [deviceInfo, setDeviceInfo] = useState(null);
  const [isConnecting, setIsConnecting] = useState(false);
  const [isLoadingVersion, setIsLoadingVersion] = useState(false);

  // Get firmware version from route params (if navigated from notification)
  const notificationVersion = route.params?.version;

  useEffect(() => {
    checkLatestFirmware();
    checkDeviceConnection();
  }, []);

  /**
   * Check for latest firmware from backend
   */
  const checkLatestFirmware = async () => {
    try {
      const response = await fetch(API_CONFIG.getUrl(API_CONFIG.ENDPOINTS.FIRMWARE_LATEST));
      const data = await response.json();
      setFirmwareInfo(data);
    } catch (error) {
      console.error('Failed to fetch firmware info:', error);
      Alert.alert('Error', 'Failed to check for firmware updates');
    }
  };

  /**
   * Check device connection status
   */
  const checkDeviceConnection = async () => {
    if (WiFiDeviceService.isConnected()) {
      setIsConnected(true);
      setDeviceIP(WiFiDeviceService.getDeviceIP());
      // Try to get current version
      loadDeviceVersion();
    } else {
      setIsConnected(false);
    }
  };

  /**
   * Load firmware version from connected device
   */
  const loadDeviceVersion = async () => {
    if (!WiFiDeviceService.isConnected()) return;

    setIsLoadingVersion(true);
    try {
      const version = await WiFiDeviceService.getDeviceVersion();
      setCurrentVersion(version);
      
      // Also get device info
      const info = await WiFiDeviceService.getDeviceInfo();
      setDeviceInfo(info);
    } catch (error) {
      console.error('Failed to load device version:', error);
      // Don't show error - device might not have version endpoint
    } finally {
      setIsLoadingVersion(false);
    }
  };

  /**
   * Connect to ESP32 device via WiFi
   */
  const connectToDevice = async () => {
    if (!deviceIP.trim()) {
      Alert.alert('Error', 'Please enter device IP address');
      return;
    }

    setIsConnecting(true);
    try {
      const result = await WiFiDeviceService.connectToDevice(deviceIP.trim());
      
      if (result.success) {
        setIsConnected(true);
        setDeviceInfo(result.deviceInfo);
        Alert.alert('Success', 'Connected to device');
        // Load device version
        loadDeviceVersion();
      } else {
        Alert.alert('Connection Failed', result.error || 'Could not connect to device');
      }
    } catch (error) {
      console.error('Connection error:', error);
      Alert.alert('Error', error.message || 'Failed to connect to device');
    } finally {
      setIsConnecting(false);
    }
  };

  /**
   * Disconnect from device
   */
  const disconnectFromDevice = () => {
    WiFiDeviceService.disconnect();
    setIsConnected(false);
    setDeviceIP('');
    setDeviceInfo(null);
    setCurrentVersion(null);
  };

  /**
   * Compare versions (semantic versioning)
   */
  const compareVersions = (v1, v2) => {
    const parts1 = v1.split('.').map(Number);
    const parts2 = v2.split('.').map(Number);
    
    for (let i = 0; i < Math.max(parts1.length, parts2.length); i++) {
      const part1 = parts1[i] || 0;
      const part2 = parts2[i] || 0;
      if (part1 > part2) return 1;
      if (part1 < part2) return -1;
    }
    return 0;
  };

  /**
   * Download firmware from backend and upload to ESP32
   */
  const startOTAUpdate = async () => {
    if (!isConnected) {
      Alert.alert('Device Not Connected', 'Please connect to your ESP32 device first');
      return;
    }

    if (!firmwareInfo) {
      Alert.alert('Error', 'Firmware information not available');
      return;
    }

    // Confirm update
    Alert.alert(
      'Confirm Update',
      `Update device to firmware version ${firmwareInfo.version}?`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Update',
          onPress: async () => {
            await performOTAUpdate();
          },
        },
      ]
    );
  };

  /**
   * Perform the actual OTA update
   */
  const performOTAUpdate = async () => {
    try {
      setIsUpdating(true);
      setUpdateProgress(0);

      // Step 1: Download firmware from backend
      console.log('Downloading firmware from backend...');
      const downloadResponse = await fetch(
        API_CONFIG.getUrl(API_CONFIG.ENDPOINTS.FIRMWARE_DOWNLOAD)
      );

      if (!downloadResponse.ok) {
        throw new Error('Failed to download firmware from backend');
      }

      // Get firmware data as ArrayBuffer
      const firmwareData = await downloadResponse.arrayBuffer();
      const firmwareVersion = downloadResponse.headers.get('X-Firmware-Version');
      const firmwareChecksum = downloadResponse.headers.get('X-Firmware-Checksum');

      console.log(`Downloaded firmware: ${firmwareData.byteLength} bytes`);

      // Step 2: Upload firmware to ESP32 over WiFi
      console.log('Uploading firmware to device...');
      const uploadResult = await WiFiDeviceService.uploadFirmware(
        firmwareData,
        firmwareVersion || firmwareInfo.version,
        firmwareChecksum || firmwareInfo.checksum,
        (progress) => {
          // Progress callback - update UI
          setUpdateProgress(progress);
          console.log(`Upload progress: ${progress}%`);
        }
      );

      if (uploadResult.success) {
        // Step 3: Report success to backend
        await reportOTAStatus('success');
        
        Alert.alert(
          'Success',
          'Firmware update completed! The device will reboot with the new firmware.',
          [
            {
              text: 'OK',
              onPress: () => {
                setIsUpdating(false);
                setUpdateProgress(0);
                // Disconnect and reload version after device reboots
                setTimeout(() => {
                  disconnectFromDevice();
                }, 2000);
              },
            },
          ]
        );
      } else {
        throw new Error(uploadResult.message || 'Upload failed');
      }
    } catch (error) {
      console.error('OTA update failed:', error);
      Alert.alert('Update Failed', error.message || 'Firmware update failed');
      setIsUpdating(false);
      setUpdateProgress(0);
      
      // Report failure to backend
      await reportOTAStatus('failed', error.message);
    }
  };

  /**
   * Report OTA status to backend
   */
  const reportOTAStatus = async (status, errorMessage = null) => {
    try {
      const deviceId = WiFiDeviceService.getDeviceIP() || 'unknown';
      
      await fetch(API_CONFIG.getUrl(API_CONFIG.ENDPOINTS.FIRMWARE_REPORT), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          device_id: deviceId,
          firmware_version: firmwareInfo?.version,
          status: status,
          error_message: errorMessage,
          progress_percent: status === 'success' ? 100 : updateProgress,
          ip_address: deviceId,
        }),
      });
    } catch (error) {
      console.error('Failed to report OTA status:', error);
    }
  };

  const needsUpdate = firmwareInfo && currentVersion && 
    compareVersions(firmwareInfo.version, currentVersion) > 0;

  return (
    <ScrollView style={styles.container}>
      <View style={styles.content}>
        <Text style={styles.title}>Firmware Update</Text>

        {/* Device Connection Section */}
        <View style={styles.section}>
          <Text style={styles.sectionTitle}>Device Connection</Text>
          
          {!isConnected ? (
            <View>
              <Text style={styles.label}>Device IP Address:</Text>
              <TextInput
                style={styles.input}
                placeholder="192.168.1.100"
                value={deviceIP}
                onChangeText={setDeviceIP}
                keyboardType="numeric"
                editable={!isConnecting}
              />
              <TouchableOpacity
                style={[styles.button, isConnecting && styles.buttonDisabled]}
                onPress={connectToDevice}
                disabled={isConnecting}
              >
                {isConnecting ? (
                  <ActivityIndicator color="#fff" />
                ) : (
                  <Text style={styles.buttonText}>Connect to Device</Text>
                )}
              </TouchableOpacity>
            </View>
          ) : (
            <View>
              <Text style={styles.label}>Connected to:</Text>
              <Text style={styles.value}>{deviceIP}</Text>
              {deviceInfo && (
                <Text style={styles.deviceInfo}>
                  {deviceInfo.name || deviceInfo.device_id || 'ESP32 Device'}
                </Text>
              )}
              <TouchableOpacity
                style={[styles.button, styles.buttonSecondary]}
                onPress={disconnectFromDevice}
              >
                <Text style={styles.buttonTextSecondary}>Disconnect</Text>
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Current Version */}
        {currentVersion && (
          <View style={styles.section}>
            <Text style={styles.label}>Current Version:</Text>
            {isLoadingVersion ? (
              <ActivityIndicator size="small" />
            ) : (
              <Text style={styles.value}>{currentVersion}</Text>
            )}
          </View>
        )}

        {/* Latest Version */}
        {firmwareInfo && (
          <View style={styles.section}>
            <Text style={styles.label}>Latest Version:</Text>
            <Text style={styles.value}>{firmwareInfo.version}</Text>
            {firmwareInfo.release_notes && (
              <Text style={styles.releaseNotes}>{firmwareInfo.release_notes}</Text>
            )}
            <Text style={styles.fileInfo}>
              Size: {(firmwareInfo.file_size / 1024).toFixed(2)} KB
            </Text>
          </View>
        )}

        {/* Update Status */}
        {needsUpdate && isConnected && (
          <View style={styles.section}>
            <Text style={styles.updateAvailable}>
              Update Available! 🎉
            </Text>
          </View>
        )}

        {/* Update Button */}
        {needsUpdate && isConnected && (
          <TouchableOpacity
            style={[styles.button, styles.buttonPrimary, isUpdating && styles.buttonDisabled]}
            onPress={startOTAUpdate}
            disabled={isUpdating}
          >
            {isUpdating ? (
              <View style={styles.progressContainer}>
                <ActivityIndicator color="#fff" />
                <Text style={styles.buttonText}>Updating... {updateProgress}%</Text>
              </View>
            ) : (
              <Text style={styles.buttonText}>Update to v{firmwareInfo.version}</Text>
            )}
          </TouchableOpacity>
        )}

        {/* Progress Bar */}
        {isUpdating && (
          <View style={styles.progressBarContainer}>
            <View style={[styles.progressBar, { width: `${updateProgress}%` }]} />
          </View>
        )}

        {/* Refresh Button */}
        <TouchableOpacity
          style={[styles.button, styles.buttonSecondary]}
          onPress={checkLatestFirmware}
        >
          <Text style={styles.buttonTextSecondary}>Check for Updates</Text>
        </TouchableOpacity>
      </View>
    </ScrollView>
  );
};

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#f5f5f5',
  },
  content: {
    padding: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: 'bold',
    marginBottom: 20,
    color: '#333',
  },
  section: {
    marginBottom: 20,
    padding: 15,
    backgroundColor: '#fff',
    borderRadius: 8,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 2,
    elevation: 2,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 10,
    color: '#333',
  },
  label: {
    fontSize: 14,
    color: '#666',
    marginBottom: 5,
  },
  value: {
    fontSize: 18,
    fontWeight: '600',
    color: '#333',
  },
  deviceInfo: {
    fontSize: 14,
    color: '#999',
    marginTop: 5,
  },
  releaseNotes: {
    marginTop: 10,
    fontSize: 14,
    color: '#666',
    fontStyle: 'italic',
  },
  fileInfo: {
    marginTop: 5,
    fontSize: 12,
    color: '#999',
  },
  updateAvailable: {
    fontSize: 16,
    fontWeight: '600',
    color: '#4CAF50',
    textAlign: 'center',
  },
  input: {
    borderWidth: 1,
    borderColor: '#ddd',
    borderRadius: 8,
    padding: 12,
    fontSize: 16,
    marginBottom: 10,
    backgroundColor: '#fff',
  },
  button: {
    padding: 15,
    borderRadius: 8,
    alignItems: 'center',
    marginTop: 10,
  },
  buttonPrimary: {
    backgroundColor: '#2196F3',
  },
  buttonDisabled: {
    backgroundColor: '#ccc',
  },
  buttonSecondary: {
    backgroundColor: '#fff',
    borderWidth: 1,
    borderColor: '#2196F3',
  },
  buttonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  buttonTextSecondary: {
    color: '#2196F3',
    fontSize: 16,
    fontWeight: '600',
  },
  progressContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  progressBarContainer: {
    height: 4,
    backgroundColor: '#e0e0e0',
    borderRadius: 2,
    marginTop: 10,
    overflow: 'hidden',
  },
  progressBar: {
    height: '100%',
    backgroundColor: '#4CAF50',
  },
});

export default FirmwareUpdateScreen;
