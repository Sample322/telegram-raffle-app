import asyncio
import time
from typing import Optional
import logging

logger = logging.getLogger(__name__)

class InMemoryLock:
    """Simple in-memory lock for single instance"""
    def __init__(self):
        self.locks = {}
    
    async def acquire(self, key: str, timeout: int = 10) -> bool:
        """Acquire lock with timeout"""
        if key not in self.locks:
            self.locks[key] = {
                'locked': False,
                'expires': 0
            }
        
        lock = self.locks[key]
        now = time.time()
        
        # Check if lock expired
        if lock['locked'] and now > lock['expires']:
            lock['locked'] = False
        
        # Try to acquire
        if not lock['locked']:
            lock['locked'] = True
            lock['expires'] = now + timeout
            return True
        
        return False
    
    async def release(self, key: str):
        """Release lock"""
        if key in self.locks:
            self.locks[key]['locked'] = False

# Global lock instance
distributed_lock = InMemoryLock()