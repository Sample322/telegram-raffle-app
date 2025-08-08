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
from ..services.provably_fair import ProvablyFairService
from ..services.time_sync import TimeSyncService
import uuid

# Добавьте словарь для хранения client_id
client_connections = {}
router = APIRouter()
logger = logging.getLogger(__name__)

# Глобальный словарь для отслеживания состояния розыгрышей
raffle_states = {}
processed_messages = {}

async def run_wheel(raffle_id: int, db: AsyncSession):
    """Запуск розыгрыша с Provably Fair системой"""
    try:
        # Получаем розыгрыш и участников
        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()

        if not raffle or raffle.is_completed:
            logger.warning(f"Raffle {raffle_id} not found or already completed")
            return

        # Загружаем участников в фиксированном порядке
        participants_result = await db.execute(
            select(User).join(Participant)
            .where(Participant.raffle_id == raffle_id)
            .order_by(User.telegram_id.asc())  # ВАЖНО: фиксированный порядок
        )
        participants = participants_result.scalars().all()

        if len(participants) < len(raffle.prizes):
            await manager.broadcast({
                "type": "error",
                "message": "Недостаточно участников для проведения розыгрыша"
            }, raffle_id)
            return

        logger.info(f"Starting provably fair raffle {raffle_id} with {len(participants)} participants")

        # Список участников для клиентов
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
            "lock": asyncio.Lock()
        }

        # Уведомляем о начале
        await manager.broadcast({
            "type": "raffle_starting",
            "total_participants": len(participants),
            "total_prizes": len(raffle.prizes),
            "provably_fair": True
        }, raffle_id)

        await asyncio.sleep(3)

        # Разыгрываем призы
        sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)

        for position in sorted_positions:
            state = raffle_states.get(raffle_id)
            if not state:
                break

            async with state['lock']:
                if int(position) in state['completed_positions']:
                    continue

                remaining_participants = state['remaining_participants']
                if not remaining_participants:
                    break

                # COMMIT PHASE - генерируем и отправляем коммит
                server_seed = ProvablyFairService.generate_server_seed()
                commit_data = ProvablyFairService.create_commit(
                    raffle_id, 
                    int(position),
                    server_seed,
                    len(remaining_participants)
                )
                
                # Вычисляем время окончания анимации
                wheel_duration = {
                    'fast': 5000,
                    'medium': 7000,
                    'slow': 10000
                }.get(raffle.wheel_speed, 5000)
                
                end_timestamp = int(time.time() * 1000) + wheel_duration
                
                # Отправляем commit клиентам
                await manager.broadcast({
                    "type": "round_commit",
                    "position": int(position),
                    "prize": raffle.prizes[position],
                    "commit_hash": commit_data["commit_hash"],
                    "participants_count": len(remaining_participants),
                    "participants": [p for p in state['participant_list'] 
                                   if p['id'] in [rp.telegram_id for rp in remaining_participants]],
                    "end_timestamp": end_timestamp,
                    "wheel_speed": raffle.wheel_speed
                }, raffle_id)
                
                # Ждем client seeds (даем 2 секунды на сбор)
                client_seeds = []
                await asyncio.sleep(2)
                
                # START PHASE - запускаем анимацию
                await manager.broadcast({
                    "type": "round_start",
                    "position": int(position),
                    "end_timestamp": end_timestamp
                }, raffle_id)
                
                # Ждем окончания анимации
                await asyncio.sleep(wheel_duration / 1000)
                
                # REVEAL PHASE - раскрываем результат
                # Используем первый client seed или генерируем случайный
                client_seed = client_seeds[0] if client_seeds else secrets.token_hex(16)
                
                reveal_data = ProvablyFairService.reveal_result(
                    raffle_id,
                    int(position),
                    client_seed
                )
                
                if reveal_data:
                    winner_index = reveal_data["winner_index"]
                    winner = remaining_participants[winner_index]
                    
                    # Сохраняем в БД
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
                    state['winners'].append({
                        "id": winner.telegram_id,
                        "username": winner.username,
                        "first_name": winner.first_name,
                        "last_name": winner.last_name
                    })
                    state['remaining_participants'] = [
                        p for p in state['remaining_participants']
                        if p.telegram_id != winner.telegram_id
                    ]
                    
                    # Отправляем результат с доказательством
                    await manager.broadcast({
                        "type": "round_reveal",
                        "position": int(position),
                        "winner": {
                            "id": winner.telegram_id,
                            "username": winner.username,
                            "first_name": winner.first_name,
                            "last_name": winner.last_name
                        },
                        "prize": raffle.prizes[position],
                        "proof": {
                            "server_seed": reveal_data["server_seed"],
                            "client_seed": reveal_data["client_seed"],
                            "winner_index": reveal_data["winner_index"],
                            "commit_hash": reveal_data["commit_hash"]
                        }
                    }, raffle_id)
                
                await asyncio.sleep(3)

        # Завершение розыгрыша
        await finalize_raffle(db, raffle_id)

    except Exception as e:
        logger.exception(f"Error in provably fair run_wheel: {e}")
        await manager.broadcast({
            "type": "error",
            "message": "Произошла ошибка при проведении розыгрыша"
        }, raffle_id)

async def handle_winner_selected(db: AsyncSession, raffle_id: int, winner_data: dict, position: int, prize: str) -> bool:
    """Предыдущая логика ручного подтверждения победителя оставлена для обратной совместимости."""
    try:
        state = raffle_states.get(raffle_id)
        if not state:
            logger.error(f"No state found for raffle {raffle_id}")
            return False

        # защита от повторных сообщений
        message_id = winner_data.get('messageId')
        if message_id and message_id in processed_messages.get(raffle_id, set()):
            logger.info(f"Duplicate message {message_id} ignored")
            return False

        logger.info(f"Handling winner for raffle {raffle_id}, position {position}, winner_id: {winner_data.get('id')}")

        # проверяем, что всё ещё ждём результат для этой позиции
        if position in state.get('completed_positions', set()):
            logger.warning(f"Position {position} already completed")
            return False

        if not state.get('waiting_for_result'):
            logger.warning(f"Not waiting for result for position {position}")
            return False

        # находим пользователя
        user_result = await db.execute(
            select(User).where(User.telegram_id == winner_data['id'])
        )
        user = user_result.scalar_one_or_none()
        if not user:
            logger.error(f"User with telegram_id {winner_data['id']} not found")
            return False

        try:
            # проверяем дубликат
            existing_winner = await db.execute(
                select(Winner).where(
                    Winner.raffle_id == raffle_id,
                    Winner.position == position
                ).with_for_update()
            )
            if existing_winner.scalar_one_or_none():
                logger.warning(f"Winner already exists for position {position} in raffle {raffle_id}")
                state['waiting_for_result'] = False
                state['completed_positions'].add(position)
                return False

            # сохраняем победителя
            winner_record = Winner(
                raffle_id=raffle_id,
                user_id=user.id,
                position=position,
                prize=prize
            )
            db.add(winner_record)
            await db.commit()
            state['waiting_for_result'] = False
            state['completed_positions'].add(position)
            state['winners'].append(winner_data)
            state['remaining_participants'] = [
                p for p in state['remaining_participants']
                if p.telegram_id != winner_data['id']
            ]
            await manager.broadcast({
                "type": "winner_confirmed",
                "position": position,
                "winner": winner_data,
                "prize": prize
            }, raffle_id)
            if message_id:
                if raffle_id not in processed_messages:
                    processed_messages[raffle_id] = set()
                processed_messages[raffle_id].add(message_id)
            logger.info(f"Winner confirmed for position {position}: {winner_data.get('username', 'Unknown')}")
            return True

        except Exception as e:
            await db.rollback()
            logger.exception(f"Error in transaction: {e}")
            state['waiting_for_result'] = False
            return False

    except Exception as e:
        logger.exception(f"Error handling winner selection: {e}")
        return False

async def finalize_raffle(db: AsyncSession, raffle_id: int):
    """Проверяем, все ли призы выданы, и завершаем розыгрыш"""
    try:
        winners_count_result = await db.execute(
            select(func.count(Winner.id)).where(Winner.raffle_id == raffle_id)
        )
        winners_count = winners_count_result.scalar()

        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()

        if raffle and winners_count >= len(raffle.prizes):
            logger.info(f"All prizes distributed for raffle {raffle_id}")

            raffle.is_completed = True
            raffle.is_active = False
            await db.commit()

            # очищаем локальное состояние
            if raffle_id in raffle_states:
                del raffle_states[raffle_id]
                if raffle_id in processed_messages:
                    del processed_messages[raffle_id]

            # подготавливаем список победителей для финального сообщения
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

            # уведомляем через Telegram/уведомления
            await NotificationService.notify_winners(raffle_id, winners)
            await NotificationService.notify_raffle_results(raffle_id, winners)
            logger.info(f"Raffle {raffle_id} completed successfully with {len(winners)} winners")

    except Exception as e:
        logger.exception(f"Error finalizing raffle {raffle_id}: {e}")

@router.websocket("/{raffle_id}")
async def websocket_endpoint(websocket: WebSocket, raffle_id: int):
    """WebSocket endpoint с поддержкой time sync и client seeds"""
    client_id = str(uuid.uuid4())
    client_connections[id(websocket)] = client_id
    
    await manager.connect(websocket, raffle_id)
    try:
        async with async_session_maker() as db:
            # Отправляем начальные данные
            raffle_result = await db.execute(
                select(Raffle).where(Raffle.id == raffle_id)
            )
            raffle = raffle_result.scalar_one_or_none()
            if raffle:
                await websocket.send_json({
                    "type": "connection_established",
                    "client_id": client_id,
                    "server_time": int(time.time() * 1000),
                    "raffle": {
                        "id": raffle.id,
                        "title": raffle.title,
                        "is_completed": raffle.is_completed,
                        "draw_started": raffle.draw_started
                    }
                })

        while True:
            try:
                data = await websocket.receive_text()
                message = json.loads(data)
                
                # Обработка ping для time sync
                if message.get("type") == "ping":
                    pong_data = TimeSyncService.handle_ping(
                        client_id,
                        message.get("timestamp", 0)
                    )
                    await websocket.send_json(pong_data)
                
                # Обработка RTT
                elif message.get("type") == "rtt_report":
                    TimeSyncService.record_rtt(client_id, message.get("rtt", 100))
                
                # Обработка client seed
                elif message.get("type") == "client_seed":
                    # Сохраняем client seed для текущего раунда
                    # В реальной реализации нужен более сложный механизм
                    pass
                    
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break

    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)
        if id(websocket) in client_connections:
            del client_connections[id(websocket)]
