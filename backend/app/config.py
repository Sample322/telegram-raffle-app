import os
from datetime import datetime, timezone, timedelta
import pytz

# Московская таймзона
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

# Или используйте переменную окружения
TIMEZONE_OFFSET = int(os.getenv("TIMEZONE_OFFSET", "3"))  # Часы от UTC

def get_current_time():
    """Получить текущее время в московской таймзоне"""
    return datetime.now(MOSCOW_TZ)

def convert_to_utc(dt: datetime) -> datetime:
    """Конвертировать локальное время в UTC"""
    if dt.tzinfo is None:
        # Если нет таймзоны, считаем что это московское время
        dt = MOSCOW_TZ.localize(dt)
    return dt.astimezone(pytz.UTC)

def convert_from_utc(dt: datetime) -> datetime:
    """Конвертировать UTC в московское время"""
    if dt.tzinfo is None:
        dt = pytz.UTC.localize(dt)
    return dt.astimezone(MOSCOW_TZ)

def parse_moscow_time(time_str: str) -> datetime:
    """Парсить время как московское"""
    # Парсим время без таймзоны
    dt = datetime.fromisoformat(time_str.replace('Z', ''))
    if dt.tzinfo is None:
        # Считаем что это московское время
        dt = MOSCOW_TZ.localize(dt)
    return dt