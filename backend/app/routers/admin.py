from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, delete
from typing import List
import os
import uuid
from datetime import datetime
import aiohttp
import logging
from ..database import get_db
from ..models import Raffle, User, Admin, Winner, Participant
from ..schemas import RaffleCreate, Raffle as RaffleSchema
from ..services.telegram import TelegramService
from ..utils.auth import get_current_admin
logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BACKEND_URL = os.getenv("API_URL", "http://localhost:8000")

@router.post("/raffles", response_model=RaffleSchema)
async def create_raffle(
    raffle_data: RaffleCreate,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Create new raffle"""
    from ..config import parse_moscow_time, convert_to_utc
    
    # Конвертируем дату из московского времени в UTC для хранения
    raffle_dict = raffle_data.dict()
        # Исправляем URL изображения если оно есть
    if raffle_dict.get('photo_url'):
        # Если это относительный путь, добавляем базовый URL
        if not raffle_dict['photo_url'].startswith('http'):
            # Получаем правильный backend URL из переменных окружения
            backend_url = os.getenv('BACKEND_URL', os.getenv('API_URL', 'http://localhost:8000'))
            # Убираем /api если есть
            backend_url = backend_url.replace('/api', '')
            # Убираем trailing slash
            backend_url = backend_url.rstrip('/')
            # Добавляем слеш к пути если его нет
            photo_path = raffle_dict['photo_url']
            if not photo_path.startswith('/'):
                photo_path = '/' + photo_path
            raffle_dict['photo_url'] = f"{backend_url}{photo_path}"
    
    logger.info(f"Photo URL after processing: {raffle_dict['photo_url']}")
    # Парсим дату как московское время и конвертируем в UTC
    end_date_str = raffle_dict['end_date']
    if isinstance(end_date_str, str):
        moscow_time = parse_moscow_time(end_date_str)
    else:
        moscow_time = end_date_str
    
    utc_time = convert_to_utc(moscow_time)
    raffle_dict['end_date'] = utc_time
    
    # Исправляем URL изображения если оно есть
    if raffle_dict.get('photo_url'):
        # Если это относительный путь, добавляем базовый URL
        if not raffle_dict['photo_url'].startswith('http'):
            # Получаем правильный backend URL из переменных окружения
            backend_url = os.getenv('BACKEND_URL') or os.getenv('API_URL', 'http://localhost:8000')
            # Убираем /api если есть
            backend_url = backend_url.replace('/api', '')
            raffle_dict['photo_url'] = f"{backend_url}{raffle_dict['photo_url']}"
        
        logger.info(f"Photo URL after processing: {raffle_dict['photo_url']}")
    
    raffle = Raffle(**raffle_dict)
    db.add(raffle)
    await db.commit()
    await db.refresh(raffle)
    
    # ДОБАВИТЬ: Проверка что розыгрыш создался
    logger.info(f"Created raffle with ID: {raffle.id}")
    
    # ДОБАВИТЬ: Проверочный запрос
    check_result = await db.execute(
        select(Raffle).where(Raffle.id == raffle.id)
    )
    check_raffle = check_result.scalar_one_or_none()
    
    if not check_raffle:
        logger.error(f"Raffle {raffle.id} not found after creation!")
        raise HTTPException(status_code=500, detail="Raffle creation failed")
    # Постинг в каналы для публикации
    if raffle_data.post_channels:
        await post_to_channels(raffle, raffle_data.post_channels)
    
    # Notify ONLY users with notifications enabled
    users_result = await db.execute(
        select(User).where(User.notifications_enabled == True)
    )
    users = users_result.scalars().all()

    if users:
        user_ids = [user.telegram_id for user in users]
        
        # For notifications, format the date back to Moscow time
        from ..config import convert_from_utc
        # Конвертируем UTC время обратно в московское для уведомлений
        moscow_time_for_notification = convert_from_utc(raffle.end_date)
        
        notification_data = raffle_data.dict()
        notification_data['end_date'] = moscow_time_for_notification.strftime('%d.%m.%Y в %H:%M МСК')
        notification_data['id'] = raffle.id
        # Передаем полный URL изображения
        notification_data['photo_url'] = raffle.photo_url
        
        # Send notifications
        await TelegramService.notify_new_raffle(
            raffle.id,
            user_ids,
            notification_data
        )
    
    return raffle

async def post_to_channels(raffle: Raffle, channels: List[str]):
    """Публикация розыгрыша в указанные каналы"""
    # Форматируем призы
    prizes_text = "\n".join([f"{pos}. {prize}" for pos, prize in raffle.prizes.items()])
    
    # Форматируем дату для отображения
    from ..config import convert_from_utc
    moscow_time = convert_from_utc(raffle.end_date)
    
    text = (
        f"🎉 *Новый розыгрыш!*\n\n"
        f"*{raffle.title}*\n\n"
        f"{raffle.description}\n\n"
        f"🏆 *Призы:*\n{prizes_text}\n\n"
        f"⏰ До {moscow_time.strftime('%d.%m.%Y в %H:%M МСК')}"
    )
    
    # Получаем username бота из переменной окружения
    bot_username = os.getenv('TELEGRAM_BOT_USERNAME', 'your_bot')
    
    # Кнопка для участия
    keyboard = {
        "inline_keyboard": [[{
            "text": "🎯 Участвовать",
            "url": f"https://t.me/{bot_username}?start=raffle_{raffle.id}"
        }]]
    }
    
    for channel in channels:
        channel = channel.replace('@', '')
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
            
            # Если есть фото И это полный URL
            if raffle.photo_url and raffle.photo_url.startswith('http'):
                # Отправляем как фото
                data = {
                    "chat_id": f"@{channel}",
                    "photo": raffle.photo_url,
                    "caption": text,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard
                }
                method = "sendPhoto"
            else:
                # Отправляем как текст
                data = {
                    "chat_id": f"@{channel}",
                    "text": text,
                    "parse_mode": "Markdown",
                    "reply_markup": keyboard
                }
                method = "sendMessage"
            
            logger.info(f"Posting to channel @{channel}, method: {method}, photo_url: {raffle.photo_url}")
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url + method, json=data) as response:
                    result = await response.json()
                    if not result.get("ok"):
                        logger.error(f"Failed to post to @{channel}: {result}")
                    else:
                        logger.info(f"Successfully posted to @{channel}")
                        
        except Exception as e:
            logger.error(f"Error posting to channel @{channel}: {e}")

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
    
    # Return relative URL
    return {"url": f"/uploads/{file_name}"}

@router.post("/upload-telegram-photo")
async def upload_telegram_photo(
    file_id: str,
    current_admin: Admin = Depends(get_current_admin)
):
    """Download photo from Telegram and save it"""
    try:
        # Get file info from Telegram
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getFile"
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json={"file_id": file_id}) as response:
                data = await response.json()
                
                if not data.get("ok"):
                    raise HTTPException(status_code=400, detail="Failed to get file info")
                
                file_path = data["result"]["file_path"]
                
        # Download file
        download_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                if response.status != 200:
                    raise HTTPException(status_code=400, detail="Failed to download file")
                
                content = await response.read()
                
                # Save file
                file_ext = file_path.split(".")[-1]
                file_name = f"{uuid.uuid4()}.{file_ext}"
                local_file_path = os.path.join(UPLOAD_DIR, file_name)
                
                with open(local_file_path, "wb") as f:
                    f.write(content)
                
                return {"url": f"/uploads/{file_name}"}
                
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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

@router.delete("/raffles/{raffle_id}")
async def delete_raffle(
    raffle_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """Полностью удалить розыгрыш вместе с участниками и победителями."""
    # Проверяем наличие
    result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
    raffle = result.scalar_one_or_none()
    if not raffle:
        raise HTTPException(status_code=404, detail="Raffle not found")

    # Удаляем каскадом: winners → participants → raffle
    await db.execute(delete(Winner).where(Winner.raffle_id == raffle_id))
    await db.execute(delete(Participant).where(Participant.raffle_id == raffle_id))
    await db.delete(raffle)
    await db.commit()
    return {"status": "success"}


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