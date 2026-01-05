#!/usr/bin/env python3
"""
Script to clear rate limit for a specific phone number
Useful for development/testing when rate limit is hit
"""
import os
import sys
import redis

# Add the app directory to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app.core.config import settings

def clear_rate_limit(phone: str):
    """
    Clear rate limit for a specific phone number
    """
    try:
        if settings.REDIS_URL:
            print(f"Connecting to Redis at {settings.REDIS_URL}...")
            redis_client = redis.Redis.from_url(settings.REDIS_URL)
            redis_client.ping()
            
            # Clear rate limit keys for this phone
            patterns = [
                f"rl:login:{phone}:*",
                f"rl:register:{phone}:*",
                f"rl:resend_otp:{phone}:*",
            ]
            
            cleared = 0
            for pattern in patterns:
                keys = redis_client.keys(pattern)
                if keys:
                    redis_client.delete(*keys)
                    cleared += len(keys)
                    print(f"Cleared {len(keys)} keys matching {pattern}")
            
            if cleared == 0:
                print("No rate limit keys found for this phone number")
            else:
                print(f"\n[SUCCESS] Cleared {cleared} rate limit entries for {phone}")
        else:
            print("[INFO] Redis not configured. Rate limits are stored in memory.")
            print("[INFO] Restart the server to clear memory-based rate limits.")
            print(f"[INFO] Or set MAX_REQUESTS_PER_WINDOW environment variable to increase limits.")
            
    except Exception as e:
        print(f"\n[ERROR] Failed to clear rate limit: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python clear_rate_limit.py <phone_number>")
        print("Example: python clear_rate_limit.py +917730831829")
        sys.exit(1)
    
    phone = sys.argv[1]
    print(f"Clearing rate limit for phone: {phone}")
    print("=" * 50)
    clear_rate_limit(phone)
    print("=" * 50)
    print("[SUCCESS] Done!")

