#!/usr/bin/env python3
"""
Reset rate limit for a phone number (e.g. after hitting "Too many OTP requests").
Uses REDIS_URL from env to clear Redis keys, or calls the API if REDIS_URL is not set.

Usage:
  # Clear rate limit for +918688844843 (default)
  python scripts/clear_rate_limit.py

  # Clear for another number
  python scripts/clear_rate_limit.py +919876543210

  # Via API (set API_BASE_URL and ADMIN_PASS)
  API_BASE_URL=http://localhost:8080 ADMIN_PASS=your_admin_pass python scripts/clear_rate_limit.py +918688844843
"""
import os
import sys

# Default phone you asked to reset
DEFAULT_PHONE = "+918688844843"


def normalize_phone(phone: str) -> str:
    """Digits only, for rate limit key."""
    return "".join(c for c in phone if c.isdigit()) or phone


def clear_via_redis(phone: str) -> bool:
    try:
        import redis
    except ImportError:
        return False
    url = os.environ.get("REDIS_URL")
    if not url:
        return False
    try:
        r = redis.Redis.from_url(url)
        r.ping()
    except Exception as e:
        print(f"Redis connection failed: {e}", file=sys.stderr)
        return False
    phone_key = normalize_phone(phone)
    patterns = [
        f"rl:login:{phone_key}:*",
        f"rl:register:{phone_key}:*",
        f"rl:resend_otp:{phone_key}:*",
    ]
    cleared = 0
    for pattern in patterns:
        keys = r.keys(pattern)
        if keys:
            r.delete(*keys)
            cleared += len(keys)
    if cleared > 0:
        print(f"Cleared {cleared} rate limit key(s) for {phone} (Redis).")
    else:
        print(f"No rate limit keys found for {phone} (Redis).")
    return True


def clear_via_api(phone: str) -> bool:
    base = os.environ.get("API_BASE_URL", "").rstrip("/")
    admin_pass = os.environ.get("ADMIN_PASS")
    if not base or not admin_pass:
        return False
    try:
        import requests
    except ImportError:
        return False
    url = f"{base}/api/auth/admin/clear-rate-limit"
    try:
        resp = requests.post(
            url,
            json={"phone": phone, "admin_key": admin_pass},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            print(data.get("message", "Rate limit cleared."))
            return True
        print(f"API error {resp.status_code}: {resp.text}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"Request failed: {e}", file=sys.stderr)
        return False


def main():
    phone = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("PHONE", DEFAULT_PHONE)).strip()
    if not phone or not phone.lstrip("+").isdigit():
        print("Usage: python scripts/clear_rate_limit.py [phone e.g. +918688844843]", file=sys.stderr)
        sys.exit(1)
    if not phone.startswith("+"):
        phone = "+" + phone
    if clear_via_redis(phone):
        sys.exit(0)
    if clear_via_api(phone):
        sys.exit(0)
    print(
        "Set REDIS_URL (to clear via Redis) or API_BASE_URL and ADMIN_PASS (to clear via API).",
        file=sys.stderr,
    )
    sys.exit(1)


if __name__ == "__main__":
    # Load .env from project root
    try:
        from dotenv import load_dotenv
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        load_dotenv(os.path.join(root, ".env"))
    except ImportError:
        pass
    main()
