/**
 * API Configuration
 * Centralized configuration for backend API endpoints
 */

export const API_CONFIG = {
  // Production backend URL
  BASE_URL: 'https://orolexabackend-production.up.railway.app',
  
  // API Endpoints
  ENDPOINTS: {
    FIRMWARE_LATEST: '/api/firmware/latest',
    FIRMWARE_DOWNLOAD: '/api/firmware/download',
    FIRMWARE_REPORT: '/api/firmware/report',
    FIRMWARE_UPLOAD: '/api/firmware/upload', // Admin only
    FIRMWARE_REPORTS: '/api/firmware/reports', // Admin only
  },
  
  // Get full URL for an endpoint
  getUrl(endpoint) {
    return `${this.BASE_URL}${endpoint}`;
  },
};

// For easy import
export default API_CONFIG;

