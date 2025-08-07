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
from ..services.distributed_lock import distributed_lock
router = APIRouter()
logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания состояния розыгрышей
raffle_states = {}
processed_messages = {}
async def run_wheel(raffle_id: int, db: AsyncSession):
    """Run the raffle wheel animation with server-side winner selection"""
    try:
        # Get raffle and participants
        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()
        
        if not raffle or raffle.is_completed:
            logger.warning(f"Raffle {raffle_id} not found or already completed")
            return
        
        # Get all participants WITH CONSISTENT ORDERING - КРИТИЧЕСКИ ВАЖНО!
        participants_result = await db.execute(
            select(User).join(Participant)
            .where(Participant.raffle_id == raffle_id)
            .order_by(User.telegram_id.asc())  # Строгая сортировка по ID
        )
        participants = participants_result.scalars().all()
        
        if len(participants) < len(raffle.prizes):
            await manager.broadcast({
                "type": "error",
                "message": "Недостаточно участников для проведения розыгрыша"
            }, raffle_id)
            return
        
        logger.info(f"Starting raffle {raffle_id} with {len(participants)} participants")
        
        # Фиксируем порядок участников для ВСЕХ клиентов
        participant_list = [{
            "id": p.telegram_id,
            "username": p.username or f"{p.first_name} {p.last_name or ''}".strip(),
            "first_name": p.first_name,
            "last_name": p.last_name
        } for p in participants]
        
        # Инициализируем состояние
        raffle_states[raffle_id] = {
            "participants": list(participants),
            "remaining_participants": list(participants),
            "winners": [],
            "completed_positions": set(),
            "participant_list": participant_list,
            "lock": asyncio.Lock()  # Добавляем блокировку
        }
        
        # Announce start
        await manager.broadcast({
            "type": "raffle_starting",
            "total_participants": len(participants),
            "total_prizes": len(raffle.prizes)
        }, raffle_id)
        
        await asyncio.sleep(3)
        
        # Process prizes from last to first
        sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)
        
        for position in sorted_positions:
            state = raffle_states.get(raffle_id)
            if not state:
                break
                
            async with state['lock']:  # Используем блокировку
                # Проверяем, не разыграна ли позиция
                if int(position) in state['completed_positions']:
                    logger.info(f"Position {position} already completed")
                    continue
                
                remaining_participants = state['remaining_participants']
                if not remaining_participants:
                    logger.error(f"No participants left for position {position}")
                    break
                
                # СЕРВЕР выбирает победителя
                import random
                winner_index = random.randint(0, len(remaining_participants) - 1)
                winner = remaining_participants[winner_index]
                
                # Находим индекс в общем списке для синхронизации с клиентами
                winner_data = {
                    "id": winner.telegram_id,
                    "username": winner.username,
                    "first_name": winner.first_name,
                    "last_name": winner.last_name
                }
                
                # Находим индекс в исходном списке для анимации
                display_index = next(
                    (i for i, p in enumerate(state['participant_list']) 
                     if p['id'] == winner.telegram_id), 
                    0
                )
                
                # Отправляем клиентам команду показать анимацию с заранее известным результатом
                await manager.broadcast({
                    "type": "wheel_start",
                    "position": int(position),
                    "prize": raffle.prizes[position],
                    "participants": state['participant_list'],
                    "predetermined_winner_index": display_index,  # Индекс победителя
                    "predetermined_winner": winner_data  # Данные победителя
                }, raffle_id)
                
                # Ждем завершения анимации (фиксированное время)
                wheel_duration = {
                    'fast': 5,
                    'medium': 7,
                    'slow': 10
                }.get(raffle.wheel_speed, 5)
                
                await asyncio.sleep(wheel_duration)
                # Сохраняем победителя в БД с распределённой блокировкой
                lock_key = f"raffle_{raffle_id}_position_{position}"
                lock_acquired = await distributed_lock.acquire(lock_key, timeout=30)

                if not lock_acquired:
                    logger.warning(f"Could not acquire lock for position {position}")
                    continue  # пропускаем эту позицию, если не получилось захватить блокировку
                # Сохраняем победителя в БД
                try:
                    # Проверяем дубликат с блокировкой
                    existing = await db.execute(
                        select(Winner).where(
                            Winner.raffle_id == raffle_id,
                            Winner.position == int(position)
                        ).with_for_update()
                    )
                    
                    if not existing.scalar_one_or_none():
                        winner_record = Winner(
                            raffle_id=raffle_id,
                            user_id=winner.id,
                            position=int(position),
                            prize=raffle.prizes[position]
                        )
                        db.add(winner_record)
                        await db.commit()
                        
                        # Обновляем состояние
                        state['completed_positions'].add(int(position))
                        state['winners'].append(winner_data)
                        state['remaining_participants'] = [
                            p for p in state['remaining_participants']
                            if p.telegram_id != winner.telegram_id
                        ]
                        
                        # Уведомляем всех о победителе
                        await manager.broadcast({
                            "type": "winner_confirmed",
                            "position": int(position),
                            "winner": winner_data,
                            "prize": raffle.prizes[position]
                        }, raffle_id)
                        
                        logger.info(f"Winner saved: position {position}, user {winner.telegram_id}")
                    else:
                        logger.warning(f"Winner already exists for position {position}")
                        
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Error saving winner: {e}")
                finally:
                    # обязательно освобождаем блокировку
                    await distributed_lock.release(lock_key)
                # Пауза между раундами
                await asyncio.sleep(3)
        
        # Финализация
        await finalize_raffle(db, raffle_id)
        
    except Exception as e:
        logger.exception(f"Error in run_wheel: {e}")
        await manager.broadcast({
            "type": "error",
            "message": "Произошла ошибка при проведении розыгрыша"
        }, raffle_id)

async def handle_winner_selected(db: AsyncSession, raffle_id: int, winner_data: dict, position: int, prize: str) -> bool:
    """Handle winner selection from frontend. Returns True if successful."""
    try:
        # Получаем состояние розыгрыша В НАЧАЛЕ функции
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
                # Но всё равно продолжаем с тем, что прислал фронт для обратной совместимости
                
        logger.info(f"Handling winner for raffle {raffle_id}, position {position}, winner_id: {winner_data.get('id')}")
        
        # Проверяем, что это правильная позиция
        current_round = state.get('current_round')
        if not current_round or current_round['position'] != position:
            logger.warning(f"Position mismatch: expected {current_round}, got {position}")
            return False
        
        # ... остальной код функции остается без изменений ...
        
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
        
        # ВАЖНО: Используем ту же сессию db, а не создаем новую!
        try:
            # Проверяем с блокировкой
            existing_winner = await db.execute(
                select(Winner).where(
                    Winner.raffle_id == raffle_id,
                    Winner.position == position
                ).with_for_update()
            )
            
            if existing_winner.scalar_one_or_none():
                logger.warning(f"Winner already exists for position {position} in raffle {raffle_id}")
                # Все равно обновляем состояние, чтобы не застрять
                state['waiting_for_result'] = False
                state['completed_positions'].add(position)
                return False
            
            # Создаем победителя
            winner_record = Winner(
                raffle_id=raffle_id,
                user_id=user.id,
                position=position,
                prize=prize
            )
            db.add(winner_record)
            
            # Сначала коммитим транзакцию
            await db.commit()
            logger.info(f"Winner saved to database for position {position}")
            
            # ТОЛЬКО ПОСЛЕ успешного коммита обновляем состояние
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
            
            # Clear state
            if raffle_id in raffle_states:
                del raffle_states[raffle_id]
                if raffle_id in processed_messages:
                    del processed_messages[raffle_id]
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
                        
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)