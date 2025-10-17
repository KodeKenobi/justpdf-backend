import redis
import json
import time
from datetime import datetime, timedelta
from flask import current_app
import os

class RateLimiter:
    """Redis-based rate limiter for API endpoints"""
    
    def __init__(self):
        self.redis_client = None
        self._connect_redis()
    
    def _connect_redis(self):
        """Connect to Redis server"""
        try:
            redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
            self.redis_client = redis.from_url(redis_url, decode_responses=True)
            # Test connection
            self.redis_client.ping()
        except Exception as e:
            print(f"Redis connection failed: {e}")
            print("Rate limiting will use in-memory fallback")
            self.redis_client = None
    
    def is_allowed(self, key, limit, window_seconds=3600):
        """
        Check if request is allowed based on rate limit
        
        Args:
            key: Unique identifier (e.g., api_key_id)
            limit: Maximum requests allowed in window
            window_seconds: Time window in seconds (default: 1 hour)
        
        Returns:
            tuple: (is_allowed, remaining_requests, reset_time)
        """
        if not self.redis_client:
            return self._memory_fallback(key, limit, window_seconds)
        
        try:
            current_time = int(time.time())
            window_start = current_time - (current_time % window_seconds)
            redis_key = f"rate_limit:{key}:{window_start}"
            
            # Use Redis pipeline for atomic operations
            pipe = self.redis_client.pipeline()
            
            # Increment counter
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds)
            
            # Get current count
            pipe.get(redis_key)
            
            results = pipe.execute()
            current_count = int(results[2])
            
            # Check if limit exceeded
            if current_count > limit:
                return False, 0, window_start + window_seconds
            
            remaining = limit - current_count
            reset_time = window_start + window_seconds
            
            return True, remaining, reset_time
            
        except Exception as e:
            print(f"Redis rate limiting error: {e}")
            return self._memory_fallback(key, limit, window_seconds)
    
    def _memory_fallback(self, key, limit, window_seconds):
        """Fallback to in-memory rate limiting if Redis fails"""
        # This is a simple fallback - in production, you might want to use
        # a more sophisticated in-memory solution or database-based approach
        return True, limit, int(time.time()) + window_seconds
    
    def get_usage(self, key, window_seconds=3600):
        """Get current usage for a key"""
        if not self.redis_client:
            return 0
        
        try:
            current_time = int(time.time())
            window_start = current_time - (current_time % window_seconds)
            redis_key = f"rate_limit:{key}:{window_start}"
            
            count = self.redis_client.get(redis_key)
            return int(count) if count else 0
            
        except Exception as e:
            print(f"Error getting usage: {e}")
            return 0
    
    def reset_limit(self, key, window_seconds=3600):
        """Reset rate limit for a key"""
        if not self.redis_client:
            return
        
        try:
            current_time = int(time.time())
            window_start = current_time - (current_time % window_seconds)
            redis_key = f"rate_limit:{key}:{window_start}"
            
            self.redis_client.delete(redis_key)
            
        except Exception as e:
            print(f"Error resetting limit: {e}")

# Global rate limiter instance
rate_limiter = RateLimiter()

def check_rate_limit(api_key_id, limit=1000, window_seconds=3600):
    """
    Check rate limit for an API key
    
    Args:
        api_key_id: The API key ID
        limit: Maximum requests per window
        window_seconds: Time window in seconds
    
    Returns:
        tuple: (is_allowed, remaining_requests, reset_timestamp)
    """
    return rate_limiter.is_allowed(api_key_id, limit, window_seconds)

def get_rate_limit_info(api_key_id, limit=1000, window_seconds=3600):
    """Get current rate limit information for an API key"""
    current_usage = rate_limiter.get_usage(api_key_id, window_seconds)
    remaining = max(0, limit - current_usage)
    
    current_time = int(time.time())
    window_start = current_time - (current_time % window_seconds)
    reset_time = window_start + window_seconds
    
    return {
        'limit': limit,
        'remaining': remaining,
        'used': current_usage,
        'reset_time': reset_time,
        'window_seconds': window_seconds
    }

def reset_rate_limit(api_key_id, window_seconds=3600):
    """Reset rate limit for an API key"""
    rate_limiter.reset_limit(api_key_id, window_seconds)
