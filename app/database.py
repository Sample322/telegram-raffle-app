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

# Если нет DATABASE_URL, используем SQLite в памяти для старта
if not DATABASE_URL:
    logger.warning("DATABASE_URL not set, using in-memory SQLite")
    DATABASE_URL = "sqlite+aiosqlite:///:memory:"
else:
    # Преобразуем postgres:// в postgresql+asyncpg://
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
    elif DATABASE_URL.startswith("postgresql://"):
        DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)
    
    # Обработка SSL параметров для asyncpg
    if "sslmode=" in DATABASE_URL:
        # Удаляем sslmode из URL и добавляем ssl=require для asyncpg
        DATABASE_URL = DATABASE_URL.replace("?sslmode=verify-full", "?ssl=require")
        DATABASE_URL = DATABASE_URL.replace("&sslmode=verify-full", "&ssl=require")
        DATABASE_URL = DATABASE_URL.replace("?sslmode=require", "?ssl=require")
        DATABASE_URL = DATABASE_URL.replace("&sslmode=require", "&ssl=require")

logger.info(f"Using database: {DATABASE_URL.split('@')[0] if '@' in DATABASE_URL else DATABASE_URL}")

# Создаем engine с защитой от ошибок
try:
    engine = create_async_engine(
        DATABASE_URL,
        echo=False,  # Отключаем echo для production
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
            logger.error(f"Database session error: {e}")
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