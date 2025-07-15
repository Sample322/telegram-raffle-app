# Создайте файл backend/app/config.py

import os
from datetime import datetime, timezone, timedelta

# Таймзона по умолчанию (Moscow Time)
DEFAULT_TIMEZONE = timezone(timedelta(hours=3))

# Или используйте переменную окружения
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "3"))  # Часы от UTC

def get_current_time():
    """Получить текущее время в нужной таймзоне"""
    return datetime.now(timezone(timedelta(hours=TIMEZONE_OFFSET)))

def convert_to_utc(dt: datetime) -> datetime:
    """Конвертировать локальное время в UTC"""
    if dt.tzinfo is None:
        # Если нет таймзоны, считаем что это локальное время
        local_tz = timezone(timedelta(hours=TIMEZONE_OFFSET))
        dt = dt.replace(tzinfo=local_tz)
    return dt.astimezone(timezone.utc)

def convert_from_utc(dt: datetime) -> datetime:
    """Конвертировать UTC в локальное время"""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    local_tz = timezone(timedelta(hours=TIMEZONE_OFFSET))
    return dt.astimezone(local_tz)