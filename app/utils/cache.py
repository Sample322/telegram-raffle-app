import json
from typing import List, Dict, Optional
import asyncio
from datetime import datetime, timedelta

class ParticipantsCache:
    """Кеш для участников розыгрыша"""
    
    def __init__(self, ttl_seconds: int = 60):
        self._cache: Dict[int, Dict] = {}
        self._ttl = ttl_seconds
        self._lock = asyncio.Lock()
    
    async def get(self, raffle_id: int) -> Optional[List[Dict]]:
        """Получить участников из кеша"""
        async with self._lock:
            if raffle_id in self._cache:
                entry = self._cache[raffle_id]
                if datetime.utcnow() < entry['expires']:
                    return entry['data']
                else:
                    del self._cache[raffle_id]
            return None
    
    async def set(self, raffle_id: int, participants: List[Dict]):
        """Сохранить участников в кеш"""
        async with self._lock:
            self._cache[raffle_id] = {
                'data': participants,
                'expires': datetime.utcnow() + timedelta(seconds=self._ttl)
            }
    
    async def invalidate(self, raffle_id: int):
        """Инвалидировать кеш для розыгрыша"""
        async with self._lock:
            if raffle_id in self._cache:
                del self._cache[raffle_id]

# Глобальный экземпляр кеша
participants_cache = ParticipantsCache()