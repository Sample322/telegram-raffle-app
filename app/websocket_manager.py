from fastapi import WebSocket
from typing import Dict, List, Set
import logging
import asyncio

logger = logging.getLogger(__name__)

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
        self.connection_ids: Dict[WebSocket, str] = {}
        self.message_cache: Dict[str, Set[str]] = {}  # Кеш обработанных сообщений
        self.lock = asyncio.Lock()
    
    async def connect(self, websocket: WebSocket, raffle_id: int):
        await websocket.accept()
        
        async with self.lock:
            if raffle_id not in self.active_connections:
                self.active_connections[raffle_id] = []
                self.message_cache[f"raffle_{raffle_id}"] = set()
            
            self.active_connections[raffle_id].append(websocket)
            
            # Генерируем уникальный ID соединения
            import uuid
            connection_id = str(uuid.uuid4())
            self.connection_ids[websocket] = connection_id
            
            logger.info(f"Client {connection_id} connected to raffle {raffle_id}")
    
    def disconnect(self, websocket: WebSocket, raffle_id: int):
        if raffle_id in self.active_connections:
            self.active_connections[raffle_id].remove(websocket)
            if not self.active_connections[raffle_id]:
                del self.active_connections[raffle_id]
                # Очищаем кеш сообщений
                cache_key = f"raffle_{raffle_id}"
                if cache_key in self.message_cache:
                    del self.message_cache[cache_key]
        
        if websocket in self.connection_ids:
            connection_id = self.connection_ids[websocket]
            del self.connection_ids[websocket]
            logger.info(f"Client {connection_id} disconnected from raffle {raffle_id}")
    
    async def broadcast(self, message: dict, raffle_id: int):
        """Broadcast with deduplication"""
        if raffle_id in self.active_connections:
            # Создаем уникальный ключ для сообщения
            import json
            import hashlib
            
            message_key = None
            if message.get("type") in ["winner_confirmed", "slot_start"]:
                # Для критичных сообщений создаем ключ
                content = f"{message.get('type')}_{message.get('position')}_{raffle_id}"
                message_key = hashlib.md5(content.encode()).hexdigest()
                
                cache_key = f"raffle_{raffle_id}"
                if message_key in self.message_cache.get(cache_key, set()):
                    logger.info(f"Skipping duplicate broadcast: {message_key}")
                    return
                
                # Добавляем в кеш
                if cache_key not in self.message_cache:
                    self.message_cache[cache_key] = set()
                self.message_cache[cache_key].add(message_key)
            
            disconnected = []
            for connection in self.active_connections[raffle_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    if "ConnectionClosedOK" not in str(type(e).__name__):
                        logger.debug(f"Broadcast error: {e}")
                    disconnected.append(connection)
            
            # Remove disconnected clients
            for conn in disconnected:
                self.disconnect(conn, raffle_id)

# Создаем глобальный экземпляр
manager = ConnectionManager()