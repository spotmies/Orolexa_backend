/**
 * WiFi Device Service
 * Handles WiFi connection and communication with ESP32 devices
 * 
 * The ESP32 should expose an HTTP server for OTA updates
 * Typical ESP32 OTA endpoint: http://192.168.x.x/update
 */

class WiFiDeviceService {
  constructor() {
    this.deviceIP = null;
    this.devicePort = 80; // Default HTTP port
    this.baseURL = null;
  }

  /**
   * Scan for ESP32 devices on local network
   * This is a simplified example - you may need to implement actual network scanning
   * or have the user manually enter the device IP
   */
  async scanForDevices() {
    // Option 1: User enters IP manually
    // Option 2: Use mDNS/Bonjour to discover devices
    // Option 3: Scan common IP ranges (192.168.1.x, 192.168.0.x, etc.)
    
    // For now, return empty array - user will enter IP manually
    return [];
  }

  /**
   * Connect to ESP32 device by IP address
   */
  async connectToDevice(ipAddress, port = 80) {
    try {
      this.deviceIP = ipAddress;
      this.devicePort = port;
      this.baseURL = `http://${ipAddress}:${port}`;

      // Test connection by checking device info endpoint
      const response = await fetch(`${this.baseURL}/info`, {
        method: 'GET',
        timeout: 5000,
      });

      if (response.ok) {
        const deviceInfo = await response.json();
        return {
          success: true,
          deviceInfo,
        };
      } else {
        throw new Error('Device not responding');
      }
    } catch (error) {
      console.error('Failed to connect to device:', error);
      return {
        success: false,
        error: error.message,
      };
    }
  }

  /**
   * Get current firmware version from ESP32
   */
  async getDeviceVersion() {
    if (!this.baseURL) {
      throw new Error('Not connected to device');
    }

    try {
      const response = await fetch(`${this.baseURL}/version`, {
        method: 'GET',
        timeout: 5000,
      });

      if (response.ok) {
        const data = await response.json();
        return data.version || data.firmware_version;
      } else {
        throw new Error('Failed to get device version');
      }
    } catch (error) {
      console.error('Failed to get device version:', error);
      throw error;
    }
  }

  /**
   * Get device information
   */
  async getDeviceInfo() {
    if (!this.baseURL) {
      throw new Error('Not connected to device');
    }

    try {
      const response = await fetch(`${this.baseURL}/info`, {
        method: 'GET',
        timeout: 5000,
      });

      if (response.ok) {
        return await response.json();
      } else {
        throw new Error('Failed to get device info');
      }
    } catch (error) {
      console.error('Failed to get device info:', error);
      throw error;
    }
  }

  /**
   * Upload firmware to ESP32 over WiFi
   * @param {ArrayBuffer} firmwareData - Binary firmware data
   * @param {string} version - Firmware version
   * @param {string} checksum - SHA256 checksum
   * @param {Function} onProgress - Progress callback (progress: number 0-100)
   */
  async uploadFirmware(firmwareData, version, checksum, onProgress) {
    if (!this.baseURL) {
      throw new Error('Not connected to device');
    }

    try {
      // ESP32 OTA update endpoint (typical implementation)
      const updateURL = `${this.baseURL}/update`;

      // Create FormData for multipart upload
      const formData = new FormData();
      
      // Convert ArrayBuffer to Blob
      const firmwareBlob = new Blob([firmwareData], { type: 'application/octet-stream' });
      formData.append('firmware', firmwareBlob, `firmware_${version}.bin`);
      formData.append('version', version);
      formData.append('checksum', checksum);

      // Use XMLHttpRequest for progress tracking
      return new Promise((resolve, reject) => {
        const xhr = new XMLHttpRequest();

        // Track upload progress
        xhr.upload.addEventListener('progress', (event) => {
          if (event.lengthComputable && onProgress) {
            const progress = Math.round((event.loaded / event.total) * 100);
            onProgress(progress);
          }
        });

        // Handle completion
        xhr.addEventListener('load', () => {
          if (xhr.status === 200) {
            try {
              const response = JSON.parse(xhr.responseText);
              resolve({
                success: true,
                message: response.message || 'Firmware uploaded successfully',
              });
            } catch (e) {
              // Some ESP32 implementations return plain text
              resolve({
                success: true,
                message: xhr.responseText || 'Firmware uploaded successfully',
              });
            }
          } else {
            reject(new Error(`Upload failed: ${xhr.status} ${xhr.statusText}`));
          }
        });

        // Handle errors
        xhr.addEventListener('error', () => {
          reject(new Error('Network error during upload'));
        });

        xhr.addEventListener('timeout', () => {
          reject(new Error('Upload timeout'));
        });

        // Configure and send
        xhr.open('POST', updateURL);
        xhr.timeout = 300000; // 5 minutes timeout for large files
        xhr.send(formData);
      });
    } catch (error) {
      console.error('Firmware upload failed:', error);
      throw error;
    }
  }

  /**
   * Check if device is connected
   */
  isConnected() {
    return this.baseURL !== null;
  }

  /**
   * Get device IP
   */
  getDeviceIP() {
    return this.deviceIP;
  }

  /**
   * Disconnect from device
   */
  disconnect() {
    this.deviceIP = null;
    this.devicePort = 80;
    this.baseURL = null;
  }
}

// Export singleton instance
export default new WiFiDeviceService();

