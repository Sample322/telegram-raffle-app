#!/bin/sh
echo "Starting backend application..."
cd /opt/build/backend || exit 1
echo "Current directory: $(pwd)"
echo "Files in directory:"
ls -la
echo "Starting uvicorn..."
exec uvicorn app:application --host 0.0.0.0 --port 8000