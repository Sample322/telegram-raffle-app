from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import os
import sys
import traceback
from datetime import datetime

print("=== STARTING MINIMAL APP ===")
print(f"Python: {sys.version}")
print(f"CWD: {os.getcwd()}")

app = FastAPI(title="Telegram Raffle API - Minimal")

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
        "message": "Minimal API Running",
        "timestamp": datetime.utcnow().isoformat(),
        "database_url": bool(os.getenv("DATABASE_URL")),
        "bot_token": bool(os.getenv("BOT_TOKEN"))
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "mode": "minimal"}

@app.get("/debug/env")
async def debug_env():
    """Debug endpoint to check environment"""
    return {
        "has_database_url": bool(os.getenv("DATABASE_URL")),
        "has_bot_token": bool(os.getenv("BOT_TOKEN")),
        "has_secret_key": bool(os.getenv("SECRET_KEY")),
        "has_s3_config": bool(os.getenv("S3_ENDPOINT")),
        "python_version": sys.version,
        "cwd": os.getcwd()
    }

@app.get("/debug/imports")
async def debug_imports():
    """Test imports"""
    results = {}
    
    # Test basic imports
    for module in ["asyncpg", "aiosqlite", "sqlalchemy", "aiohttp"]:
        try:
            __import__(module)
            results[module] = "OK"
        except Exception as e:
            results[module] = str(e)
    
    # Test app imports
    try:
        from app import database
        results["app.database"] = "OK"
    except Exception as e:
        results["app.database"] = str(e)
    
    try:
        from app import models
        results["app.models"] = "OK"
    except Exception as e:
        results["app.models"] = str(e)
    
    return results

# Export for Timeweb
application = app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)