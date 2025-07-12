from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from typing import List

from ..database import get_db
from ..models import User
from ..schemas import User as UserSchema
from ..utils.auth import get_current_user

router = APIRouter()

@router.get("/me", response_model=UserSchema)
async def get_current_user_info(
    current_user: User = Depends(get_current_user)
):
    """Get current user information"""
    return current_user

@router.patch("/me/notifications")
async def toggle_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Toggle notifications for current user"""
    new_status = not current_user.notifications_enabled
    
    await db.execute(
        update(User).where(User.id == current_user.id).values(
            notifications_enabled=new_status
        )
    )
    await db.commit()
    
    return {
        "notifications_enabled": new_status,
        "message": f"Уведомления {'включены' if new_status else 'выключены'}"
    }

@router.get("/profile/{telegram_id}", response_model=UserSchema)
async def get_user_profile(
    telegram_id: int,
    db: AsyncSession = Depends(get_db)
):
    """Get user profile by telegram ID"""
    result = await db.execute(
        select(User).where(User.telegram_id == telegram_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return user

@router.post("/update-profile")
async def update_profile(
    first_name: str = None,
    last_name: str = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update user profile"""
    update_data = {}
    if first_name:
        update_data["first_name"] = first_name
    if last_name:
        update_data["last_name"] = last_name
    
    if update_data:
        await db.execute(
            update(User).where(User.id == current_user.id).values(**update_data)
        )
        await db.commit()
    
    return {"status": "success", "message": "Profile updated"}