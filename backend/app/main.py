from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import asyncio
from typing import Dict, List
import json

from .database import init_db
from .routers import raffles, users, admin, websocket
from .services.raffle import RaffleService

# WebSocket connection manager
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
            for connection in self.active_connections[raffle_id]:
                try:
                    await connection.send_json(message)
                except:
                    pass

manager = ConnectionManager()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Start background task for checking raffles
    asyncio.create_task(check_expired_raffles())
    yield
    # Shutdown

app = FastAPI(lifespan=lifespan, title="Telegram Raffle API")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your domain
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(raffles.router, prefix="/api/raffles", tags=["raffles"])
app.include_router(admin.router, prefix="/api/admin", tags=["admin"])
app.include_router(websocket.router, prefix="/api/ws", tags=["websocket"])

# Background task to check expired raffles
async def check_expired_raffles():
    while True:
        try:
            # Check for expired raffles every minute
            await RaffleService.check_and_start_draws()
        except Exception as e:
            print(f"Error in background task: {e}")
        await asyncio.sleep(60)

@app.get("/")
async def root():
    return {"message": "Telegram Raffle API", "version": "1.0.0"}

# WebSocket endpoint for raffle wheel
@app.websocket("/ws/raffle/{raffle_id}")
async def websocket_endpoint(websocket: WebSocket, raffle_id: int):
    await manager.connect(websocket, raffle_id)
    try:
        while True:
            data = await websocket.receive_text()
            # Handle incoming messages if needed
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)