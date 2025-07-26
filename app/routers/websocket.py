from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import asyncio
import random
import json
from typing import List, Dict
from datetime import datetime
import logging
from ..database import get_db, async_session_maker
from ..models import Raffle, Participant, User, Winner
from ..websocket_manager import manager
from ..services.telegram import TelegramService
from ..services.notifications import NotificationService

router = APIRouter()
logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания состояния розыгрышей
raffle_states = {}

class RaffleWheel:
    @staticmethod
    async def run_wheel(raffle_id: int, db: AsyncSession):
        """Run the raffle wheel animation"""
        try:
            # Get raffle and participants
            raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
            raffle = raffle_result.scalar_one_or_none()
            
            if not raffle or raffle.is_completed:
                logger.warning(f"Raffle {raffle_id} not found or already completed")
                return
            
            # Get all participants
            participants_result = await db.execute(
                select(User).join(Participant).where(Participant.raffle_id == raffle_id)
            )
            participants = participants_result.scalars().all()
            
            if len(participants) < len(raffle.prizes):
                await manager.broadcast({
                    "type": "error",
                    "message": "Недостаточно участников для проведения розыгрыша"
                }, raffle_id)
                return
            
            logger.info(f"Starting raffle {raffle_id} with {len(participants)} participants")
            
            # Инициализируем состояние розыгрыша
            raffle_states[raffle_id] = {
                "participants": list(participants),
                "remaining_participants": list(participants),
                "current_round": None,
                "waiting_for_result": False,
                "winners": []
            }
            
            # Announce start
            await manager.broadcast({
                "type": "raffle_starting",
                "total_participants": len(participants),
                "total_prizes": len(raffle.prizes)
            }, raffle_id)
            
            await asyncio.sleep(3)  # Pause before starting
            
            # Start from last place to first
            sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)
            
            for position in sorted_positions:
                state = raffle_states.get(raffle_id)
                if not state or not state['remaining_participants']:
                    break
                
                # Устанавливаем текущий раунд
                state['current_round'] = {
                    'position': int(position),
                    'prize': raffle.prizes[position]
                }
                state['waiting_for_result'] = True
                
                # Prepare participant data for wheel
                wheel_participants = []
                for p in state['remaining_participants']:
                    wheel_participants.append({
                        "id": p.telegram_id,
                        "username": p.username or f"{p.first_name} {p.last_name or ''}".strip(),
                        "first_name": p.first_name,
                        "last_name": p.last_name
                    })
                
                # Send wheel data
                await manager.broadcast({
                    "type": "wheel_start",
                    "position": int(position),
                    "prize": raffle.prizes[position],
                    "participants": wheel_participants
                }, raffle_id)
                
                logger.info(f"Started wheel for position {position}, waiting for result...")
                
                # Ждем результат от фронтенда (с таймаутом)
                timeout = 30  # 30 секунд таймаут
                waited = 0
                while state['waiting_for_result'] and waited < timeout:
                    await asyncio.sleep(0.5)
                    waited += 0.5
                
                if waited >= timeout:
                    logger.error(f"Timeout waiting for wheel result for position {position}")
                    await manager.broadcast({
                        "type": "error",
                        "message": "Превышено время ожидания результата"
                    }, raffle_id)
                else:
                    # Даем время на анимацию победителя
                    await asyncio.sleep(3)
            
            # Очищаем состояние
            if raffle_id in raffle_states:
                del raffle_states[raffle_id]
                
        except Exception as e:
            logger.error(f"Error running wheel for raffle {raffle_id}: {e}")
            await manager.broadcast({
                "type": "error",
                "message": "Произошла ошибка при проведении розыгрыша"
            }, raffle_id)
            # Очищаем состояние при ошибке
            if raffle_id in raffle_states:
                del raffle_states[raffle_id]

@router.websocket("/{raffle_id}")
async def websocket_endpoint(websocket: WebSocket, raffle_id: int):
    """WebSocket endpoint for live raffle"""
    await manager.connect(websocket, raffle_id)
    
    try:
        # Send current state to new connection
        async with async_session_maker() as db:
            raffle_result = await db.execute(
                select(Raffle).where(Raffle.id == raffle_id)
            )
            raffle = raffle_result.scalar_one_or_none()
            
            if raffle:
                await websocket.send_json({
                    "type": "connection_established",
                    "raffle": {
                        "id": raffle.id,
                        "title": raffle.title,
                        "is_completed": raffle.is_completed,
                        "draw_started": raffle.draw_started
                    }
                })
        
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            
            # Handle messages from frontend
            try:
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
                # Обработка результата от фронтенда
                elif message.get("type") == "winner_selected":
                    logger.info(f"Received winner selection: {message}")
                    async with async_session_maker() as db:
                        await handle_winner_selected(
                            db,
                            raffle_id,
                            message.get("winner"),
                            message.get("position"),
                            message.get("prize")
                        )
                        
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)

# Предположим, что async_session_maker объявлен где-то выше
# from app.database import async_session_maker

async def handle_winner_selected(db: AsyncSession, raffle_id: int, winner_data: dict, position: int, prize: str):
    """Handle winner selection from frontend"""
    state = raffle_states.get(raffle_id)
    try:
        logger.info("Handling winner for raffle %s, position %s", raffle_id, position)

        # --- отдельная сессия, чтобы не конфликтовать с уже начатой ---
        async with async_session_maker() as new_db:
            async with new_db.begin():
                # 1. Проверка дубликата (с блокировкой строки позиции)
                existing = await new_db.execute(
                    select(Winner).where(
                        Winner.raffle_id == raffle_id,
                        Winner.position == position
                    ).with_for_update()
                )
                if existing.scalar_one_or_none():
                    logger.warning("Winner already exists for position %s", position)
                    # даже если уже есть, фронт надо уведомить
                    if state:
                        state["waiting_for_result"] = False
                    await manager.broadcast({
                        "type": "winner_confirmed",
                        "position": position,
                        "winner": winner_data,  # можно прислать что есть
                        "prize": prize,
                        "already_exists": True
                    }, raffle_id)
                    return

                # 2. Находим пользователя
                user_res = await new_db.execute(
                    select(User).where(User.telegram_id == winner_data["id"])
                )
                user = user_res.scalar_one_or_none()
                if not user:
                    logger.error("User with telegram_id %s not found", winner_data["id"])
                    if state:
                        state["waiting_for_result"] = False
                    # Можно отправить фронту событие об ошибке
                    await manager.broadcast({
                        "type": "winner_error",
                        "position": position,
                        "reason": "user_not_found"
                    }, raffle_id)
                    return

                # 3. Сохраняем победителя
                winner_row = Winner(
                    raffle_id=raffle_id,
                    user_id=user.id,
                    position=position,
                    prize=prize
                )
                new_db.add(winner_row)
                await new_db.flush()  # получим ID, если надо

            # ❗ транзакция закрылась, теперь commit за пределами begin
            await new_db.commit()

        # 4. Обновляем локальное состояние
        if state:
            state["waiting_for_result"] = False
            state["winners"].append(winner_data)
            state["remaining_participants"] = [
                p for p in state["remaining_participants"]
                if (p.get("id") if isinstance(p, dict) else getattr(p, "telegram_id", None)) != winner_data["id"]
            ]

        # 5. Шлём подтверждение клиентам
        await manager.broadcast({
            "type": "winner_confirmed",
            "position": position,
            "winner": winner_data,
            "prize": prize
        }, raffle_id)

        logger.info("Winner confirmed for position %s", position)

        # 6. Проверяем, не закончились ли призы
        await check_raffle_completion(raffle_id)

    except Exception:
        logger.exception("Error handling winner selection")
        if state:
            state["waiting_for_result"] = False
