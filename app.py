# Wrapper для Timeweb Cloud Apps
import sys
import os
import traceback

# Добавляем текущую директорию в путь Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Пытаемся импортировать основное приложение
try:
    from app.main import app
    print("Successfully imported app from app.main")
    application = app
    
except Exception as e:
    print(f"Failed to import main app: {e}")
    print("Full traceback:")
    traceback.print_exc()
    
    # Fallback на простое приложение
    print("Creating fallback application...")
    
    from fastapi import FastAPI
    import datetime
    
    application = FastAPI(title="Telegram Raffle API - Fallback Mode")
    
    @application.get("/")
    async def root():
        return {
            "status": "fallback",
            "message": "Main app failed to load, running in fallback mode",
            "error": str(e),
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    
    @application.get("/health")
    async def health():
        return {
            "status": "unhealthy",
            "mode": "fallback",
            "error": "Check logs for details"
        }
    
    app = application

# Для совместимости
APP = application
fastapi_app = application

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(application, host="0.0.0.0", port=8000)