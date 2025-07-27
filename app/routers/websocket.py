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

router = APIRouter()
logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания состояния розыгрышей
raffle_states = {}
processed_messages = {}
async def run_wheel(raffle_id: int, db: AsyncSession):
    """Run the raffle wheel animation"""
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
            "participant_order": participant_order  # НОВОЕ: сохраняем порядок
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
        
        for position in sorted_positions:
            state = raffle_states.get(raffle_id)
            if not state:
                logger.error(f"State lost for raffle {raffle_id}")
                break
                
            # Проверяем, не была ли уже разыграна эта позиция
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
            
            # Prepare participant data for wheel WITH CONSISTENT ORDER
            wheel_participants = []
            # Используем только оставшихся участников, но сохраняем порядок из participant_order
            remaining_ids = {p.telegram_id for p in state['remaining_participants']}
            
            for tid in state['participant_order']:
                if tid in remaining_ids:
                    # Находим участника
                    participant = next(p for p in state['remaining_participants'] if p.telegram_id == tid)
                    wheel_participants.append({
                        "id": participant.telegram_id,
                        "username": participant.username or f"{participant.first_name} {participant.last_name or ''}".strip(),
                        "first_name": participant.first_name,
                        "last_name": participant.last_name
                    })
            winner_index = random.randint(0, len(wheel_participants) - 1)
            winner_id = wheel_participants[winner_index]['id']
            
            # Рассчитываем точный угол для остановки
            # Колесо вращается против часовой, стрелка сверху (270°)
            segment_angle = (2 * math.pi) / len(wheel_participants)
            # Центр сегмента победителя
            target_angle = winner_index * segment_angle + segment_angle / 2
            # Добавляем случайное смещение для естественности (±10% от размера сегмента)
            offset = (random.random() - 0.5) * segment_angle * 0.2
            target_angle += offset
            # Добавляем несколько полных оборотов для красоты
            full_rotations = random.randint(4, 8)
            target_angle += full_rotations * 2 * math.pi
            
            # Сохраняем в состоянии
            state['predetermined_winner'] = {
                'index': winner_index,
                'id': winner_id,
                'position': int(position),
                'angle': target_angle
            }
            # Send wheel data
            await manager.broadcast({
                "type": "wheel_start",
                "position": int(position),
                "prize": raffle.prizes[position],
                "participants": wheel_participants,
                "participant_order": [p["id"] for p in wheel_participants],
                "target_winner_index": winner_index,
                "target_angle": target_angle  # Точный угол остановки
            }, raffle_id)
            
            logger.info(f"Started wheel for position {position}, waiting for result...")
            
            # Ждем результат от фронтенда с увеличенным таймаутом
            timeout = 60  # 60 секунд
            waited = 0
            while state.get('waiting_for_result', False) and waited < timeout:
                await asyncio.sleep(0.5)
                waited += 0.5
                
                # Проверяем, не потеряли ли мы состояние
                if raffle_id not in raffle_states:
                    logger.error(f"State lost during waiting for raffle {raffle_id}")
                    return
            
            if waited >= timeout:
                logger.error(f"Timeout waiting for wheel result for position {position}")
                
                # При таймауте выбираем случайного победителя
                if state['remaining_participants']:
                    random_winner = random.choice(state['remaining_participants'])
                    winner_data = {
                        "id": random_winner.telegram_id,
                        "username": random_winner.username,
                        "first_name": random_winner.first_name,
                        "last_name": random_winner.last_name
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
        logger.exception(f"Error running wheel for raffle {raffle_id}")
        await manager.broadcast({
            "type": "error",
            "message": "Произошла ошибка при проведении розыгрыша"
        }, raffle_id)
        if raffle_id in raffle_states:
            del raffle_states[raffle_id]

async def handle_winner_selected(db: AsyncSession, raffle_id: int, winner_data: dict, position: int, prize: str) -> bool:
    # Проверяем предопределённого победителя
    predetermined = state.get('predetermined_winner')
    if predetermined and predetermined['position'] == position:
            if winner_data['id'] != predetermined['id']:
                logger.warning(f"Winner mismatch: expected {predetermined['id']}, got {winner_data['id']}")
                # Но всё равно продолжаем с тем, что прислал фронт для обратной совместимости
    """Handle winner selection from frontend. Returns True if successful."""
    try:
                # Проверяем messageId для идемпотентности
        message_id = winner_data.get('messageId')
        if message_id and message_id in processed_messages.get(raffle_id, set()):
            logger.info(f"Duplicate message {message_id} ignored")
            return False
        logger.info(f"Handling winner for raffle {raffle_id}, position {position}, winner_id: {winner_data.get('id')}")
        
        # Проверяем состояние розыгрыша
        state = raffle_states.get(raffle_id)
        if not state:
            logger.error(f"No state found for raffle {raffle_id}")
            return False
            
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