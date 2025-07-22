from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
from datetime import datetime

app = FastAPI(title="Telegram Raffle API - Simple")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "message": "Telegram Raffle API - Simple Version",
        "status": "running",
        "timestamp": datetime.utcnow().isoformat()
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "version": "simple",
        "database_url": bool(os.getenv("DATABASE_URL")),
        "bot_token": bool(os.getenv("BOT_TOKEN"))
    }

@app.get("/api/test")
async def test():
    return {"test": "ok"}

# Экспортируем для Timeweb
application = app