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
    """Запуск анимации розыгрыша и выбор победителя на сервере"""
    try:
        # Получаем розыгрыш и участников
        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()

        if not raffle or raffle.is_completed:
            logger.warning(f"Raffle {raffle_id} not found or already completed")
            return

        # ВАЖНО: Загружаем участников в ФИКСИРОВАННОМ порядке (по Telegram ID)
        participants_result = await db.execute(
            select(User).join(Participant)
            .where(Participant.raffle_id == raffle_id)
            .order_by(User.telegram_id.asc())  # ДЕТЕРМИНИРОВАННЫЙ ПОРЯДОК
        )
        participants = participants_result.scalars().all()

        if len(participants) < len(raffle.prizes):
            await manager.broadcast({
                "type": "error",
                "message": "Недостаточно участников для проведения розыгрыша"
            }, raffle_id)
            return

        logger.info(f"Starting raffle {raffle_id} with {len(participants)} participants")
        logger.info(f"Initial participants order: {[p.telegram_id for p in participants]}")

        # Сохраняем список участников для синхронизации с клиентами
        participant_list = [{
            "id": p.telegram_id,
            "username": p.username or f"{p.first_name} {p.last_name or ''}".strip(),
            "first_name": p.first_name,
            "last_name": p.last_name
        } for p in participants]

        # Инициализируем состояние розыгрыша с round counter
        raffle_states[raffle_id] = {
            "participants": list(participants),
            "remaining_participants": list(participants),
            "winners": [],
            "completed_positions": set(),
            "participant_list": participant_list,
            "lock": asyncio.Lock(),
            "round_seq": 0  # ИЗМЕНЕНО: round_seq вместо sequence
        }

        # Сообщаем всем клиентам о начале
        await manager.broadcast({
            "type": "raffle_starting",
            "total_participants": len(participants),
            "total_prizes": len(raffle.prizes),
            "round_seq": 0
        }, raffle_id)

        await asyncio.sleep(3)

        # Разыгрываем призы начиная с последнего места
        sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)

        for position in sorted_positions:
            state = raffle_states.get(raffle_id)
            if not state:
                break

            async with state['lock']:
                # Увеличиваем round_seq для каждого раунда
                state['round_seq'] += 1
                current_round_seq = state['round_seq']
                
                # пропускаем, если это место уже разыграно
                if int(position) in state['completed_positions']:
                    logger.info(f"Position {position} already completed, skipping")
                    continue

                remaining_participants = state['remaining_participants']
                if not remaining_participants:
                    logger.error(f"No participants left for position {position}")
                    break

                # КРИТИЧЕСКИ ВАЖНО: Логируем точное состояние перед выбором
                logger.info(f"=== ROUND {current_round_seq} - POSITION {position} ===")
                logger.info(f"Remaining participants COUNT: {len(remaining_participants)}")
                logger.info(f"Remaining participants IDs: {[p.telegram_id for p in remaining_participants]}")
                logger.info(f"Remaining participants ORDER: {[(i, p.telegram_id, p.username) for i, p in enumerate(remaining_participants)]}")

                # сервер выбирает случайного победителя
                winner_index = random.randint(0, len(remaining_participants) - 1)
                winner = remaining_participants[winner_index]
                
                logger.info(f"Random index selected: {winner_index}")
                logger.info(f"Winner at index {winner_index}: {winner.username} (id={winner.telegram_id})")
                
                winner_data = {
                    "id": winner.telegram_id,
                    "username": winner.username,
                    "first_name": winner.first_name,
                    "last_name": winner.last_name
                }

                # КРИТИЧЕСКИ ВАЖНО: Формируем список ТОЛЬКО из оставшихся участников В ТОМ ЖЕ ПОРЯДКЕ
                remaining_participant_list = [{
                    "id": p.telegram_id,
                    "username": p.username or f"{p.first_name} {p.last_name or ''}".strip(),
                    "first_name": p.first_name,
                    "last_name": p.last_name
                } for p in remaining_participants]

                # ДОБАВЛЯЕМ participant_ids для проверки на клиенте
                participant_ids = [p.telegram_id for p in remaining_participants]

                # отправляем клиентам событие slot_start с ДЕТАЛЬНОЙ информацией
                slot_start_event = {
                    "type": "slot_start",
                    "position": int(position),
                    "prize": raffle.prizes[position],
                    "participants": remaining_participant_list,  # Полные данные участников
                    "participant_ids": participant_ids,  # НОВОЕ: массив ID для проверки
                    "predetermined_winner_id": winner.telegram_id,
                    "predetermined_winner": winner_data,
                    "predetermined_winner_index": winner_index,  # НОВОЕ: индекс победителя
                    "round_seq": current_round_seq  # ВАЖНО: round_seq для последовательности
                }
                
                logger.info(f"Sending slot_start with round_seq={current_round_seq}, winner_id={winner.telegram_id}")
                await manager.broadcast(slot_start_event, raffle_id)

                # ждём окончания анимации
                wheel_duration = {
                    'fast': 5,
                    'medium': 7,
                    'slow': 10
                }.get(raffle.wheel_speed, 5)
                await asyncio.sleep(wheel_duration)

                # распределённая блокировка на сохранение
                lock_key = f"raffle_{raffle_id}_position_{position}"
                lock_acquired = await distributed_lock.acquire(lock_key, timeout=30)
                if not lock_acquired:
                    logger.warning(f"Could not acquire lock for position {position}")
                    continue

                try:
                    # проверяем дубликат
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

                        # обновляем состояние ПОСЛЕ сохранения в БД
                        state['completed_positions'].add(int(position))
                        state['winners'].append(winner_data)
                        # ВАЖНО: удаляем победителя из списка только после сохранения
                        state['remaining_participants'] = [
                            p for p in state['remaining_participants']
                            if p.telegram_id != winner.telegram_id
                        ]

                        # сообщаем всем о победителе с round_seq
                        await manager.broadcast({
                            "type": "winner_confirmed",
                            "position": int(position),
                            "winner": winner_data,
                            "winner_id": winner.telegram_id,  # НОВОЕ: явный ID
                            "prize": raffle.prizes[position],
                            "round_seq": current_round_seq  # ВАЖНО: тот же round_seq
                        }, raffle_id)

                        logger.info(f"Winner confirmed and saved: position {position}, user {winner.telegram_id}, round_seq {current_round_seq}")
                        logger.info(f"Remaining participants after removal: {[p.telegram_id for p in state['remaining_participants']]}")
                    else:
                        logger.warning(f"Winner already exists for position {position}")

                except Exception as e:
                    await db.rollback()
                    logger.error(f"Error saving winner: {e}")
                finally:
                    await distributed_lock.release(lock_key)

                await asyncio.sleep(3)

        # Финальное завершение
        await finalize_raffle(db, raffle_id)

    except Exception as e:
        logger.exception(f"Error in run_wheel: {e}")
        await manager.broadcast({
            "type": "error",
            "message": "Произошла ошибка при проведении розыгрыша"
        }, raffle_id)

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
    """WebSocket endpoint for live raffle"""
    await manager.connect(websocket, raffle_id)
    try:
        # при подключении отправляем текущий статус
        async with async_session_maker() as db:
            raffle_result = await db.execute(
                select(Raffle).where(Raffle.id == raffle_id)
            )
            raffle = raffle_result.scalar_one_or_none()
            if raffle:
                # Отправляем текущий round_seq если розыгрыш активен
                current_round_seq = 0
                if raffle_id in raffle_states:
                    current_round_seq = raffle_states[raffle_id].get('round_seq', 0)
                    
                await websocket.send_json({
                    "type": "connection_established",
                    "raffle": {
                        "id": raffle.id,
                        "title": raffle.title,
                        "is_completed": raffle.is_completed,
                        "draw_started": raffle.draw_started
                    },
                    "round_seq": current_round_seq  # текущий round_seq
                })

        while True:
            try:
                data = await websocket.receive_text()
            except WebSocketDisconnect:
                raise
            except Exception as e:
                logger.debug(f"WebSocket receive error: {e}")
                break

            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)