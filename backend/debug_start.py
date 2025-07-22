#!/usr/bin/env python3
import os
import sys

print("=== DEBUG START ===")
print(f"Python version: {sys.version}")
print(f"Current directory: {os.getcwd()}")
print(f"Directory contents: {os.listdir('.')}")

# Проверяем наличие app директории
if os.path.exists('app'):
    print(f"\nApp directory found!")
    print(f"App directory contents: {os.listdir('app')}")
    
    # Проверяем main.py
    if os.path.exists('app/main.py'):
        print("\n✓ app/main.py exists")
    else:
        print("\n✗ app/main.py NOT FOUND!")
else:
    print("\n✗ App directory NOT FOUND!")

# Проверяем наличие requirements.txt
if os.path.exists('requirements.txt'):
    print("\n✓ requirements.txt exists")
else:
    print("\n✗ requirements.txt NOT FOUND!")

# Пробуем импортировать
print("\n=== TRYING IMPORTS ===")
try:
    import fastapi
    print("✓ FastAPI imported successfully")
except:
    print("✗ FastAPI import failed")

try:
    import uvicorn
    print("✓ Uvicorn imported successfully")
except:
    print("✗ Uvicorn import failed")

print("\n=== TRYING TO START APP ===")
try:
    from app.main import app
    print("✓ App imported successfully")
    
    # Запускаем uvicorn
    import uvicorn
    print("Starting uvicorn...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
except Exception as e:
    print(f"✗ Failed to start: {e}")
    import traceback
    traceback.print_exc()