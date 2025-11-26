#!/usr/bin/env python3
"""
Example script to upload firmware to the OTA backend

Usage:
    python scripts/upload_firmware.py --version 1.0.5 --file build/esp32p4_v1.0.5.bin

Requirements:
    pip install requests

Environment Variables:
    BASE_URL: Backend base URL (default: http://localhost:8000)
    ADMIN_USER: Admin username
    ADMIN_PASS: Admin password
"""
import os
import sys
import argparse
import requests
from pathlib import Path


def upload_firmware(
    version: str,
    file_path: str,
    base_url: str,
    admin_user: str,
    admin_pass: str,
    release_notes: str = None,
    rollout_percent: int = 100
):
    """Upload firmware to the backend"""
    
    # Validate file exists
    if not os.path.exists(file_path):
        print(f"Error: File not found: {file_path}")
        sys.exit(1)
    
    # Prepare request
    url = f"{base_url}/api/firmware/upload"
    
    with open(file_path, 'rb') as f:
        files = {'file': (os.path.basename(file_path), f, 'application/octet-stream')}
        data = {
            'version': version,
            'rollout_percent': rollout_percent
        }
        
        if release_notes:
            data['release_notes'] = release_notes
        
        try:
            print(f"Uploading firmware {version} from {file_path}...")
            response = requests.post(
                url,
                files=files,
                data=data,
                auth=(admin_user, admin_pass),
                timeout=300  # 5 minutes for large files
            )
            
            response.raise_for_status()
            result = response.json()
            
            if result.get('success'):
                print(f"[SUCCESS] Firmware {version} uploaded successfully!")
                print(f"   Checksum: {result['data']['checksum']}")
                print(f"   File size: {result['data']['file_size']} bytes")
                print(f"   URL: {result['data']['url']}")
                if result['data'].get('release_notes'):
                    print(f"   Release notes: {result['data']['release_notes']}")
            else:
                print(f"[ERROR] Upload failed: {result.get('message', 'Unknown error')}")
                sys.exit(1)
                
        except requests.exceptions.ConnectionError as e:
            print(f"[ERROR] Cannot connect to backend server at {base_url}")
            print(f"   Make sure your backend is running. Start it with: python -m app.main")
            print(f"   Or check if BASE_URL is correct in your .env file")
            sys.exit(1)
        except requests.exceptions.RequestException as e:
            print(f"[ERROR] Error uploading firmware: {e}")
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.json()
                    print(f"   Details: {error_detail}")
                except:
                    print(f"   Status: {e.response.status_code}")
                    print(f"   Response: {e.response.text[:200]}")
            sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description='Upload firmware to OTA backend')
    parser.add_argument('--version', required=True, help='Firmware version (e.g., 1.0.5)')
    parser.add_argument('--file', required=True, help='Path to firmware binary file')
    parser.add_argument('--base-url', default=os.getenv('BASE_URL', 'http://localhost:8000'),
                       help='Backend base URL')
    parser.add_argument('--admin-user', default=os.getenv('ADMIN_USER', 'admin'),
                       help='Admin username')
    parser.add_argument('--admin-pass', default=os.getenv('ADMIN_PASS'),
                       help='Admin password')
    parser.add_argument('--release-notes', help='Release notes for this version')
    parser.add_argument('--rollout-percent', type=int, default=100,
                       help='Rollout percentage (0-100)')
    
    args = parser.parse_args()
    
    if not args.admin_pass:
        print("Error: Admin password required. Set ADMIN_PASS environment variable or use --admin-pass")
        sys.exit(1)
    
    upload_firmware(
        version=args.version,
        file_path=args.file,
        base_url=args.base_url,
        admin_user=args.admin_user,
        admin_pass=args.admin_pass,
        release_notes=args.release_notes,
        rollout_percent=args.rollout_percent
    )


if __name__ == '__main__':
    main()

