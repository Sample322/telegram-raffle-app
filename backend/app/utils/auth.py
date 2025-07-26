from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json
import logging

from ..database import get_db
from ..models import User, Admin
from ..services.telegram import TelegramService
logger = logging.getLogger(__name__)
async def get_current_user(
    authorization: str = Header(...),
    db: AsyncSession = Depends(get_db)
) -> User:
    """Get current user from Telegram init data"""
    try:
        # Parse init data
        init_data = authorization.replace("Bearer ", "")
        validated_data = TelegramService.validate_init_data(init_data)
        
        if not validated_data:
            raise HTTPException(status_code=401, detail="Invalid authentication")
        
        # Get user data (already parsed as dict in validate_init_data)
        user_data = validated_data.get("user")
        
        if not user_data or not isinstance(user_data, dict):
            raise HTTPException(status_code=401, detail="Invalid user data")
        
        # Get telegram_id and convert to int
        telegram_id = user_data.get("id")
        if telegram_id:
            telegram_id = int(telegram_id)
        else:
            raise HTTPException(status_code=401, detail="Invalid user ID")
        
        # Get or create user
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
    # Создаем нового пользователя
            user = User(
                telegram_id=telegram_id,
                username=user_data.get("username"),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", ""),
                notifications_enabled=False  # По умолчанию выключены
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            logger.info(f"Auto-registered new user: {telegram_id}")
        else:
            # Update user info if changed
            update_needed = False
            if user_data.get("username") and user.username != user_data.get("username"):
                user.username = user_data.get("username")
                update_needed = True
            if user_data.get("first_name") and user.first_name != user_data.get("first_name"):
                user.first_name = user_data.get("first_name")
                update_needed = True
            if user_data.get("last_name") and user.last_name != user_data.get("last_name"):
                user.last_name = user_data.get("last_name")
                update_needed = True
            
            if update_needed:
                await db.commit()
                await db.refresh(user)
        
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"Authentication error: {e}")
        raise HTTPException(status_code=401, detail="Authentication failed")

async def get_current_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Admin:
    """Check if current user is admin"""
    result = await db.execute(
        select(Admin).where(Admin.telegram_id == current_user.telegram_id)
    )
    admin = result.scalar_one_or_none()
    
    if not admin:
        # Проверяем, есть ли пользователь в списке админов из переменных окружения
        import os
        admin_ids = os.getenv("ADMIN_IDS", "").split(",")
        admin_ids = [int(id.strip()) for id in admin_ids if id.strip()]
        
        if current_user.telegram_id in admin_ids:
            # Автоматически создаем запись админа
            admin = Admin(
                telegram_id=current_user.telegram_id,
                username=current_user.username
            )
            db.add(admin)
            await db.commit()
            await db.refresh(admin)
        else:
            raise HTTPException(status_code=403, detail="Admin access required")
    
    return admin