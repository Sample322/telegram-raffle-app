from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List
import os
import uuid
from datetime import datetime

from ..database import get_db
from ..models import Raffle, User, Admin
from ..schemas import RaffleCreate, Raffle as RaffleSchema
from ..services.telegram import TelegramService
from ..utils.auth import get_current_admin

router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/raffles", response_model=RaffleSchema)
async def create_raffle(
    raffle_data: RaffleCreate,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new raffle"""
    raffle = Raffle(**raffle_data.dict())
    db.add(raffle)
    await db.commit()
    await db.refresh(raffle)
    
    # Notify users with notifications enabled
    users_result = await db.execute(
        select(User).where(User.notifications_enabled == True)
    )
    users = users_result.scalars().all()
    user_ids = [user.telegram_id for user in users]
    
    # Send notifications
    await TelegramService.notify_new_raffle(
        raffle.id,
        user_ids,
        raffle_data.dict()
    )
    
    return raffle

@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    current_admin: Admin = Depends(get_current_admin)
):
    """Upload raffle image"""
    # Validate file type
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")
    
    # Generate unique filename
    file_ext = file.filename.split(".")[-1]
    file_name = f"{uuid.uuid4()}.{file_ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)
    
    # Save file
    with open(file_path, "wb") as f:
        content = await file.read()
        f.write(content)
    
    # Return URL
    return {"url": f"/uploads/{file_name}"}

@router.patch("/raffles/{raffle_id}/end")
async def end_raffle_manually(
    raffle_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Manually end a raffle"""
    result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
    raffle = result.scalar_one_or_none()
    
    if not raffle:
        raise HTTPException(status_code=404, detail="Raffle not found")
    
    if raffle.is_completed:
        raise HTTPException(status_code=400, detail="Raffle already completed")
    
    # Update end date to trigger draw
    raffle.end_date = datetime.utcnow()
    await db.commit()
    
    return {"status": "success", "message": "Raffle will end soon"}

@router.get("/statistics")
async def get_statistics(
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Get platform statistics"""
    # Total users
    users_count = await db.execute(select(func.count(User.id)))
    total_users = users_count.scalar()
    
    # Active users (with notifications)
    active_count = await db.execute(
        select(func.count(User.id)).where(User.notifications_enabled == True)
    )
    active_users = active_count.scalar()
    
    # Total raffles
    raffles_count = await db.execute(select(func.count(Raffle.id)))
    total_raffles = raffles_count.scalar()
    
    # Active raffles
    active_raffles_count = await db.execute(
        select(func.count(Raffle.id)).where(
            Raffle.is_active == True,
            Raffle.is_completed == False
        )
    )
    active_raffles = active_raffles_count.scalar()
    
    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_raffles": total_raffles,
        "active_raffles": active_raffles
    }