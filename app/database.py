from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import os
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Получаем DATABASE_URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Если нет DATABASE_URL, используем SQLite
if not DATABASE_URL:
    logger.warning("DATABASE_URL not set, using in-memory SQLite")
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
else:
    # Преобразуем postgres:// в postgresql+asyncpg://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Обработка SSL для Timeweb
    if "sslmode=" in DATABASE_URL:
        # Timeweb использует sslmode=verify-full, но asyncpg требует другой формат
        # Удаляем параметр sslmode и добавляем ssl=require
        import urllib.parse
        
        # Парсим URL
        parsed = urllib.parse.urlparse(DATABASE_URL)
        
        # Удаляем sslmode из query
        query_params = urllib.parse.parse_qs(parsed.query)
        query_params.pop('sslmode', None)
        
        # Добавляем ssl=require
        query_params['ssl'] = ['require']
        
        # Собираем URL обратно
        new_query = urllib.parse.urlencode(query_params, doseq=True)
        DATABASE_URL = urllib.parse.urlunparse((
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment
        ))

logger.info(f"Using database: {DATABASE_URL.split('@')[0] if '@' in DATABASE_URL else DATABASE_URL}")

# Создаем engine
try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Отключаем для production
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10
    )
except Exception as e:
    logger.error(f"Failed to create engine: {e}")
    # Fallback на SQLite
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
    engine = create_async_engine(DATABASE_URL, echo=False)

async_session_maker = async_sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            logger.exception("Database session error")  # Используем exception вместо error
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Initialize database with error handling"""
    try:
        # Для SQLite нужен специальный пакет
        if "sqlite" in DATABASE_URL:
            try:
                import aiosqlite
            except ImportError:
                logger.warning("aiosqlite not installed, skipping DB init")
                return
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        # Не падаем, продолжаем работу