# Wrapper для Timeweb Cloud Apps
import sys
import os

# Добавляем текущую директорию в путь Python
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from app.main import app
    print("Successfully imported app from app.main")
except ImportError as e:
    print(f"Import error: {e}")
    print(f"Current directory: {os.getcwd()}")
    print(f"Python path: {sys.path}")
    print(f"Directory contents: {os.listdir('.')}")
    if os.path.exists('app'):
        print(f"App directory contents: {os.listdir('app')}")
    raise

# Экспортируем приложение FastAPI
application = app

# Для совместимости можно добавить альтернативные имена
APP = app
fastapi_app = app

# Добавим простой тест
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(application, host="0.0.0.0", port=8000)