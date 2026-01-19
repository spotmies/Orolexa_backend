# app/services/rate_limit_service.py
import time
from typing import Optional
import logging

try:
    import redis
except ImportError:
    redis = None

from app.core.config import settings

logger = logging.getLogger(__name__)

class RateLimitService:
    def __init__(self):
        self.redis_client = None
        self.memory_store = {}  # Fallback to memory storage
        
        if redis and settings.REDIS_URL:
            try:
                self.redis_client = redis.Redis.from_url(settings.REDIS_URL)
                # Test connection
                self.redis_client.ping()
                logger.info("Redis rate limiter initialized")
            except Exception as e:
                logger.warning(f"Redis not available, using memory store: {e}")
                self.redis_client = None
        else:
            logger.info("Using memory-based rate limiting")

    def allow_request(self, key: str, max_requests: int = None, window_seconds: int = None) -> bool:
        """Check if request is allowed based on rate limits"""
        max_requests = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
        window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SEC
        
        if self.redis_client:
            return self._redis_rate_limit(key, max_requests, window_seconds)
        else:
            return self._memory_rate_limit(key, max_requests, window_seconds)

    def _redis_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Redis-based rate limiting"""
        try:
            # Ensure window_seconds is an integer for Redis EXPIRE command
            window_seconds = int(window_seconds)
            rk = f"rl:{key}:{window_seconds}"
            pipe = self.redis_client.pipeline()
            pipe.incr(rk, 1)
            pipe.expire(rk, window_seconds)
            count, _ = pipe.execute()
            return int(count) <= int(max_requests)
        except Exception as e:
            logger.error(f"Redis rate limit error: {e}")
            return self._memory_rate_limit(key, max_requests, window_seconds)

    def _memory_rate_limit(self, key: str, max_requests: int, window_seconds: int) -> bool:
        """Memory-based rate limiting (fallback)"""
        # Ensure window_seconds is numeric (convert from float if needed)
        window_seconds = int(window_seconds)
        current_time = time.time()
        window_key = f"{key}:{window_seconds}"
        
        if window_key not in self.memory_store:
            self.memory_store[window_key] = []
        
        # Clean old entries
        cutoff_time = current_time - window_seconds
        self.memory_store[window_key] = [
            timestamp for timestamp in self.memory_store[window_key]
            if timestamp > cutoff_time
        ]
        
        # Check if under limit
        if len(self.memory_store[window_key]) < max_requests:
            self.memory_store[window_key].append(current_time)
            return True
        
        return False

    def get_remaining_requests(self, key: str, max_requests: int = None, window_seconds: int = None) -> int:
        """Get remaining requests for a key"""
        max_requests = max_requests or settings.RATE_LIMIT_MAX_REQUESTS
        window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SEC
        
        if self.redis_client:
            try:
                # Ensure window_seconds is an integer
                window_seconds = int(window_seconds)
                rk = f"rl:{key}:{window_seconds}"
                count = self.redis_client.get(rk)
                return max(0, max_requests - int(count or 0))
            except Exception as e:
                logger.error(f"Error getting remaining requests: {e}")
                return max_requests
        else:
            current_time = time.time()
            window_key = f"{key}:{window_seconds}"
            cutoff_time = current_time - window_seconds
            
            if window_key in self.memory_store:
                recent_requests = [
                    timestamp for timestamp in self.memory_store[window_key]
                    if timestamp > cutoff_time
                ]
                return max(0, max_requests - len(recent_requests))
            
            return max_requests
