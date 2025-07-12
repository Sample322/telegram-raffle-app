from fastapi import WebSocket
from typing import Dict, List

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[int, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, raffle_id: int):
        await websocket.accept()
        if raffle_id not in self.active_connections:
            self.active_connections[raffle_id] = []
        self.active_connections[raffle_id].append(websocket)
    
    def disconnect(self, websocket: WebSocket, raffle_id: int):
        if raffle_id in self.active_connections:
            self.active_connections[raffle_id].remove(websocket)
            if not self.active_connections[raffle_id]:
                del self.active_connections[raffle_id]
    
    async def broadcast(self, message: dict, raffle_id: int):
        if raffle_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[raffle_id]:
                try:
                    await connection.send_json(message)
                except:
                    disconnected.append(connection)
            
            # Remove disconnected clients
            for conn in disconnected:
                self.disconnect(conn, raffle_id)

# Создаем глобальный экземпляр
manager = ConnectionManager()