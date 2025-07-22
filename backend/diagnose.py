#!/usr/bin/env python3
import os
import sys
import traceback

print("=== DIAGNOSTIC START ===")
print(f"Python: {sys.version}")
print(f"Path: {sys.path}")
print(f"CWD: {os.getcwd()}")

# Проверка переменных окружения
print("\n=== ENVIRONMENT VARIABLES ===")
env_vars = [
    "DATABASE_URL", "BOT_TOKEN", "SECRET_KEY", 
    "S3_ENDPOINT", "S3_BUCKET", "S3_ACCESS_KEY"
]
for var in env_vars:
    value = os.getenv(var)
    if value:
        if "PASSWORD" in var or "SECRET" in var or "TOKEN" in var:
            print(f"{var}: ***HIDDEN***")
        else:
            print(f"{var}: {value[:20]}..." if len(str(value)) > 20 else f"{var}: {value}")
    else:
        print(f"{var}: NOT SET")

# Проверка импортов
print("\n=== CHECKING IMPORTS ===")
modules = [
    "fastapi", "uvicorn", "sqlalchemy", "asyncpg", 
    "aiosqlite", "aiohttp", "pydantic", "dotenv"
]
for module in modules:
    try:
        __import__(module)
        print(f"✓ {module}")
    except ImportError as e:
        print(f"✗ {module}: {e}")

# Проверка структуры приложения
print("\n=== APP STRUCTURE ===")
if os.path.exists("app"):
    for file in ["__init__.py", "main.py", "database.py", "models.py"]:
        path = f"app/{file}"
        if os.path.exists(path):
            print(f"✓ {path}")
        else:
            print(f"✗ {path} NOT FOUND")

# Попытка импорта приложения
print("\n=== TRYING APP IMPORT ===")
try:
    from app.database import DATABASE_URL, engine
    print(f"✓ Database URL type: {type(DATABASE_URL)}")
    print(f"✓ Database URL: {DATABASE_URL.split('@')[0]}@...")
    print(f"✓ Engine created: {engine}")
except Exception as e:
    print(f"✗ Database import failed: {e}")
    traceback.print_exc()

try:
    from app.main import app
    print("✓ App imported successfully")
    print(f"✓ App type: {type(app)}")
    print(f"✓ App title: {app.title}")
except Exception as e:
    print(f"✗ App import failed: {e}")
    traceback.print_exc()

# Проверка app.py wrapper
print("\n=== CHECKING APP.PY ===")
try:
    from app import application
    print(f"✓ application imported from app.py: {type(application)}")
except Exception as e:
    print(f"✗ Failed to import from app.py: {e}")

print("\n=== DIAGNOSTIC COMPLETE ===")