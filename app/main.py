from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from contextlib import asynccontextmanager
import asyncio
import os
from datetime import datetime
import json

from .database import init_db
from .routers import raffles, users, admin, websocket
from .services.raffle import RaffleService
from .websocket_manager import manager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()
    # Start background task for checking raffles
    task = asyncio.create_task(check_expired_raffles())
    yield
    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

app = FastAPI(lifespan=lifespan, title="Telegram Raffle API")

@app.get("/test")
async def test():
    return {"message": "Backend is working!"}

# Dynamic CORS configuration for Timeweb
cors_origins_str = os.getenv("CORS_ORIGINS", '["http://localhost:3000"]')
try:
    cors_origins = json.loads(cors_origins_str)
except:
    cors_origins = ["http://localhost:3000"]

# Add wildcard for Timeweb subdomains
cors_origins.extend([
    "https://*.twc1.net",
    "http://localhost:3000",
    "http://localhost:3001"
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)

# Mount static files for uploads
upload_dir = os.getenv("UPLOAD_DIR", "uploads")
os.makedirs(upload_dir, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

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

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow().isoformat()}

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