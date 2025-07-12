from fastapi import Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import json

from ..database import get_db
from ..models import User, Admin
from ..services.telegram import TelegramService

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
        
        # Parse user data
        user_data = json.loads(validated_data.get("user", "{}"))
        telegram_id = user_data.get("id")
        
        if not telegram_id:
            raise HTTPException(status_code=401, detail="Invalid user data")
        
        # Get or create user
        result = await db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        user = result.scalar_one_or_none()
        
        if not user:
            user = User(
                telegram_id=telegram_id,
                username=user_data.get("username"),
                first_name=user_data.get("first_name", ""),
                last_name=user_data.get("last_name", "")
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        return user
        
    except Exception as e:
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
        raise HTTPException(status_code=403, detail="Admin access required")
    
    return admin