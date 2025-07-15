# backend/app/routers/admin.py
from __future__ import annotations

# ────────────────────────── stdlib
import os
import uuid
from datetime import datetime, timezone
from typing import List, Optional

# ────────────────────────── 3‑rd party
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    Header,
    File,
    UploadFile,
)
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

# ────────────────────────── project
from ..database import get_db
from ..models import Raffle, User, Admin
from ..schemas import RaffleCreate, Raffle as RaffleSchema
from ..services.telegram import TelegramService
from ..utils.auth import get_current_admin

# ------------------------------------------------------------------------------
router = APIRouter(prefix="/api/admin", tags=["admin"])

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# ───────────────────────────────────────────────────────────────────────────────
@router.post("/raffles", response_model=RaffleSchema)
async def create_raffle(
    raffle_data: RaffleCreate,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Создать новый розыгрыш (только для админов)."""
    raffle = Raffle(**raffle_data.dict())
    db.add(raffle)
    await db.commit()
    await db.refresh(raffle)

    # уведомляем пользователей с включёнными уведомлениями
    users_result = await db.execute(
        select(User).where(User.notifications_enabled.is_(True))
    )
    user_ids = [u.telegram_id for u in users_result.scalars().all()]

    await TelegramService.notify_new_raffle(raffle.id, user_ids, raffle_data.dict())
    return raffle


# ───────────────────────────────────────────────────────────────────────────────
@router.post("/upload-image")
async def upload_image(
    file: UploadFile = File(...),
    x_api_key: Optional[str] = Header(None),
    current_admin: Admin = Depends(get_current_admin),
):
    """
    Загрузить изображение для розыгрыша.

    • либо с заголовком `X-API-Key`  
    • либо будучи авторизованным администратором
    """
    # ── авторизация ────────────────────────────────────────────────────
    if x_api_key:
        expected_key = os.getenv("ADMIN_API_KEY", "your-secret-admin-api-key-12345")
        if x_api_key != expected_key:
            raise HTTPException(status_code=403, detail="Invalid API key")
    elif not current_admin:
        raise HTTPException(status_code=401, detail="Authentication required")

    # ── валидация файла ───────────────────────────────────────────────
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    # ── сохранение ────────────────────────────────────────────────────
    ext = (file.filename.rsplit(".", 1)[-1] or "jpg") if file.filename else "jpg"
    file_name = f"{uuid.uuid4()}.{ext}"
    file_path = os.path.join(UPLOAD_DIR, file_name)

    content = await file.read()
    with open(file_path, "wb") as fp:
        fp.write(content)

    return {"url": f"/uploads/{file_name}"}


# ───────────────────────────────────────────────────────────────────────────────
@router.patch("/raffles/{raffle_id}/end")
async def end_raffle_manually(
    raffle_id: int,
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Досрочно завершить розыгрыш (админ)."""
    result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
    raffle = result.scalar_one_or_none()

    if not raffle:
        raise HTTPException(status_code=404, detail="Raffle not found")
    if raffle.is_completed:
        raise HTTPException(status_code=400, detail="Raffle already completed")

    raffle.end_date = datetime.now(timezone.utc)
    await db.commit()

    return {"status": "success", "message": "Raffle will end soon"}


# ───────────────────────────────────────────────────────────────────────────────
@router.get("/statistics")
async def get_statistics(
    current_admin: Admin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Статистика платформы (админ)."""
    total_users = (
        await db.execute(select(func.count(User.id)))  # noqa: WPS437
    ).scalar()
    active_users = (
        await db.execute(
            select(func.count(User.id)).where(User.notifications_enabled.is_(True))
        )
    ).scalar()
    total_raffles = (
        await db.execute(select(func.count(Raffle.id)))
    ).scalar()
    active_raffles = (
        await db.execute(
            select(func.count(Raffle.id)).where(
                Raffle.is_active.is_(True), Raffle.is_completed.is_(False)
            )
        )
    ).scalar()

    return {
        "total_users": total_users,
        "active_users": active_users,
        "total_raffles": total_raffles,
        "active_raffles": active_raffles,
    }
