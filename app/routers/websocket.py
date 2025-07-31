from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import asyncio
import random
import json
import math
from typing import List, Dict
from datetime import datetime
import logging
from ..database import get_db, async_session_maker
from ..models import Raffle, Participant, User, Winner
from ..websocket_manager import manager
from ..services.telegram import TelegramService
from ..services.notifications import NotificationService
from sqlalchemy.dialects.postgresql import insert

router = APIRouter()
logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания состояния розыгрышей
raffle_states = {}
processed_messages = {}
async def run_slot(raffle_id: int, db: AsyncSession):
    """Run the raffle slot machine animation"""
    try:
        # Get raffle and participants
        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()
        
        if not raffle or raffle.is_completed:
            logger.warning(f"Raffle {raffle_id} not found or already completed")
            return
        
        # Get all participants WITH CONSISTENT ORDERING
        participants_result = await db.execute(
            select(User).join(Participant)
            .where(Participant.raffle_id == raffle_id)
            .order_by(User.telegram_id)  # ВАЖНО: фиксированная сортировка!
        )
        participants = participants_result.scalars().all()
        
        if len(participants) < len(raffle.prizes):
            await manager.broadcast({
                "type": "error",
                "message": "Недостаточно участников для проведения розыгрыша"
            }, raffle_id)
            return
        
        logger.info(f"Starting raffle {raffle_id} with {len(participants)} participants")
        
        # Создаем фиксированный порядок участников
        participant_order = [p.telegram_id for p in participants]
        
        # Инициализируем состояние розыгрыша
        raffle_states[raffle_id] = {
            "participants": list(participants),
            "remaining_participants": list(participants),
            "current_round": None,
            "waiting_for_result": False,
            "winners": [],
            "completed_positions": set(),
            "participant_order": participant_order
        }
        
        # Announce start
        await manager.broadcast({
            "type": "raffle_starting",
            "total_participants": len(participants),
            "total_prizes": len(raffle.prizes)
        }, raffle_id)
        
        await asyncio.sleep(3)
        
        # Start from last place to first
        sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)
        
        # Константы для слот-машины
        ITEM_HEIGHT = 60  # Должно совпадать с frontend
        
        for position in sorted_positions:
            state = raffle_states.get(raffle_id)
            if not state:
                logger.error(f"State lost for raffle {raffle_id}")
                break
                
            if int(position) in state['completed_positions']:
                logger.warning(f"Position {position} already completed, skipping")
                continue
                
            if not state['remaining_participants']:
                logger.warning(f"No remaining participants for position {position}")
                break
            
            # Устанавливаем текущий раунд
            state['current_round'] = {
                'position': int(position),
                'prize': raffle.prizes[position]
            }
            state['waiting_for_result'] = True
            
            # Prepare participant data for slot WITH CONSISTENT ORDER
            slot_participants = []
            remaining_ids = {p.telegram_id for p in state['remaining_participants']}
            
            for tid in state['participant_order']:
                if tid in remaining_ids:
                    participant = next(p for p in state['remaining_participants'] if p.telegram_id == tid)
                    slot_participants.append({
                        "id": participant.telegram_id,
                        "username": participant.username or f"{participant.first_name} {participant.last_name or ''}".strip(),
                        "first_name": participant.first_name,
                        "last_name": participant.last_name
                    })
            
            # Выбираем победителя
            winner_index = random.randint(0, len(slot_participants) - 1)
            winner_id = slot_participants[winner_index]['id']
            
            # Рассчитываем точную позицию остановки в пикселях
            base_offset = winner_index * ITEM_HEIGHT
            
            # Добавляем случайное смещение (±10% от высоты элемента)
            random_offset = random.uniform(-0.1, 0.1) * ITEM_HEIGHT
            target_offset = base_offset + random_offset
            
            # Убеждаемся, что offset в пределах
            target_offset = max(0, min(target_offset, (len(slot_participants) - 1) * ITEM_HEIGHT))
            
            # Сохраняем в состоянии
            state['predetermined_winner'] = {
                'index': winner_index,
                'id': winner_id,
                'position': int(position),
                'offset': target_offset
            }
            
            # Send slot data
            await manager.broadcast({
                "type": "wheel_start",  # Оставляем тот же тип для совместимости
                "position": int(position),
                "prize": raffle.prizes[position],
                "participants": slot_participants,
                "participant_order": [p["id"] for p in slot_participants],
                "target_winner_index": winner_index,
                "target_offset": target_offset  # Вместо target_angle
            }, raffle_id)
            
            logger.info(f"Started slot for position {position}, target offset: {target_offset}px, waiting for result...")
            
            # Ждем результат от фронтенда
            timeout = 60
            waited = 0
            while state.get('waiting_for_result', False) and waited < timeout:
                await asyncio.sleep(0.5)
                waited += 0.5
                
                if raffle_id not in raffle_states:
                    logger.error(f"State lost during waiting for raffle {raffle_id}")
                    return
            
            if waited >= timeout:
                logger.error(f"Timeout waiting for slot result for position {position}")
                
                # При таймауте выбираем предопределенного победителя
                if state['remaining_participants'] and 'predetermined_winner' in state:
                    predetermined = state['predetermined_winner']
                    winner_participant = next(
                        p for p in state['remaining_participants'] 
                        if p.telegram_id == predetermined['id']
                    )
                    winner_data = {
                        "id": winner_participant.telegram_id,
                        "username": winner_participant.username,
                        "first_name": winner_participant.first_name,
                        "last_name": winner_participant.last_name
                    }
                    
                    # Сохраняем победителя
                    success = await handle_winner_selected(
                        db, 
                        raffle_id, 
                        winner_data, 
                        int(position), 
                        raffle.prizes[position]
                    )
                    
                    if success:
                        await manager.broadcast({
                            "type": "winner_confirmed",
                            "position": int(position),
                            "winner": winner_data,
                            "prize": raffle.prizes[position],
                            "auto_selected": True
                        }, raffle_id)
            
            # Даем время на анимацию победителя
            await asyncio.sleep(3)
            
            # Переходим к следующему месту
            await manager.broadcast({
                "type": "round_complete",
                "position": int(position)
            }, raffle_id)
            
            # Небольшая пауза между раундами
            await asyncio.sleep(2)
        
        # Финальная проверка и завершение
        await finalize_raffle(db, raffle_id)
        
    except Exception as e:
        logger.exception(f"Error running slot for raffle {raffle_id}")
        await manager.broadcast({
            "type": "error",
            "message": "Произошла ошибка при проведении розыгрыша"
        }, raffle_id)
        if raffle_id in raffle_states:
            del raffle_states[raffle_id]


async def handle_winner_selected(db: AsyncSession, raffle_id: int, winner_data: dict, position: int, prize: str) -> bool:
    """Handle winner selection from frontend. Returns True if successful."""
    try:
        # Получаем состояние розыгрыша
        state = raffle_states.get(raffle_id)
        if not state:
            logger.error(f"No state found for raffle {raffle_id}")
            return False
            
        # Проверяем messageId для идемпотентности
        message_id = winner_data.get('messageId')
        if message_id and message_id in processed_messages.get(raffle_id, set()):
            logger.info(f"Duplicate message {message_id} ignored")
            return False
            
        # Проверяем предопределённого победителя
        predetermined = state.get('predetermined_winner')
        if predetermined and predetermined['position'] == position:
            if winner_data['id'] != predetermined['id']:
                logger.warning(f"Winner mismatch: expected {predetermined['id']}, got {winner_data['id']}")
                # Используем предопределенного победителя для консистентности
                winner_id = predetermined['id']
                # Находим правильные данные победителя
                for p in state['participants']:
                    if p.telegram_id == winner_id:
                        winner_data = {
                            "id": p.telegram_id,
                            "username": p.username,
                            "first_name": p.first_name,
                            "last_name": p.last_name
                        }
                        break
                
        logger.info(f"Handling winner for raffle {raffle_id}, position {position}, winner_id: {winner_data.get('id')}")
        
        # Проверяем, что это правильная позиция
        current_round = state.get('current_round')
        if not current_round or current_round['position'] != position:
            logger.warning(f"Position mismatch: expected {current_round}, got {position}")
            return False
        
        # Проверяем, не обработан ли уже этот раунд
        if position in state.get('completed_positions', set()):
            logger.warning(f"Position {position} already completed")
            return False
            
        if not state.get('waiting_for_result'):
            logger.warning(f"Not waiting for result for position {position}")
            return False
        
        # Find user by telegram_id
        user_result = await db.execute(
            select(User).where(User.telegram_id == winner_data['id'])
        )
        user = user_result.scalar_one_or_none()
        
        if not user:
            logger.error(f"User with telegram_id {winner_data['id']} not found")
            return False
        
        try:
            # Используем INSERT ... ON CONFLICT для идемпотентности
            stmt = insert(Winner).values(
                raffle_id=raffle_id,
                user_id=user.id,
                position=position,
                prize=prize,
                won_at=datetime.utcnow()
            )
            
            # При конфликте обновляем временную метку (для логирования попыток)
            stmt = stmt.on_conflict_do_update(
                index_elements=['raffle_id', 'position'],
                set_=dict(won_at=datetime.utcnow())
            )
            
            result = await db.execute(stmt)
            await db.commit()
            
            # Проверяем, была ли это вставка или обновление
            if result.rowcount > 0:
                logger.info(f"Winner saved/updated for position {position}")
            else:
                logger.warning(f"No changes made for position {position} (possible duplicate)")
            
            # В любом случае обновляем состояние
            state['waiting_for_result'] = False
            state['completed_positions'].add(position)
            state['winners'].append(winner_data)
            
            # Удаляем победителя из оставшихся участников
            state['remaining_participants'] = [
                p for p in state['remaining_participants'] 
                if p.telegram_id != winner_data['id']
            ]
            
            # Broadcast winner to all clients
            await manager.broadcast({
                "type": "winner_confirmed",
                "position": position,
                "winner": winner_data,
                "prize": prize
            }, raffle_id)
            
            # Сохраняем messageId в кеш
            if message_id:
                if raffle_id not in processed_messages:
                    processed_messages[raffle_id] = set()
                processed_messages[raffle_id].add(message_id)
            
            logger.info(f"Winner confirmed for position {position}: {winner_data.get('username', 'Unknown')}")
            return True
                
        except Exception as e:
            await db.rollback()
            logger.exception(f"Error in transaction: {e}")
            # При ошибке все равно сбрасываем флаг ожидания
            state['waiting_for_result'] = False
            return False
                
    except Exception as e:
        logger.exception(f"Error handling winner selection: {e}")
        return False

async def finalize_raffle(db: AsyncSession, raffle_id: int):
    """Finalize raffle and check if all prizes have been distributed"""
    try:
        # Get final winner count
        winners_count_result = await db.execute(
            select(func.count(Winner.id)).where(Winner.raffle_id == raffle_id)
        )
        winners_count = winners_count_result.scalar()
        
        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()
        
        if raffle and winners_count >= len(raffle.prizes):
            logger.info(f"All prizes distributed for raffle {raffle_id}")
            
            # Complete the raffle
            raffle.is_completed = True
            raffle.is_active = False
            await db.commit()
            
            # Clear state AND message cache
            if raffle_id in raffle_states:
                del raffle_states[raffle_id]
            if raffle_id in processed_messages:
                del processed_messages[raffle_id]
                logger.info(f"Cleared message cache for raffle {raffle_id}")
            
            # Get all winners for final broadcast
            winners_result = await db.execute(
                select(Winner, User).join(User).where(
                    Winner.raffle_id == raffle_id
                ).order_by(Winner.position)
            )
            winners_data = winners_result.all()
            
            winners = []
            for winner, user in winners_data:
                winners.append({
                    "position": winner.position,
                    "user": {
                        "id": user.telegram_id,
                        "username": user.username,
                        "first_name": user.first_name,
                        "last_name": user.last_name
                    },
                    "prize": winner.prize
                })
            
            await manager.broadcast({
                "type": "raffle_complete",
                "winners": winners
            }, raffle_id)
            
            # Send notifications
            await NotificationService.notify_winners(raffle_id, winners)
            await NotificationService.notify_raffle_results(raffle_id, winners)
            
            logger.info(f"Raffle {raffle_id} completed successfully with {len(winners)} winners")
            
    except Exception as e:
        logger.exception(f"Error finalizing raffle {raffle_id}: {e}")

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
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                raise  # Пробрасываем для обработки снаружи
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break
            
            # Handle messages from frontend
            try:
                message = json.loads(data)
                
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
                # Обработка результата от фронтенда
                elif message.get("type") == "winner_selected":
                    logger.info(f"Received winner selection: {message}")
                    async with async_session_maker() as db:
                        success = await handle_winner_selected(
                            db,
                            raffle_id,
                            message.get("winner"),
                            message.get("position"),
                            message.get("prize")
                        )
                        if not success:
                            logger.error(f"Failed to handle winner selection: {message}")
                        
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)