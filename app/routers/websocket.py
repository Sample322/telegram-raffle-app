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

        # Загружаем участников в фиксированном порядке (по Telegram ID)
        participants_result = await db.execute(
            select(User).join(Participant)
            .where(Participant.raffle_id == raffle_id)
            .order_by(User.telegram_id.asc())
        )
        participants = participants_result.scalars().all()

        if len(participants) < len(raffle.prizes):
            await manager.broadcast({
                "type": "error",
                "message": "Недостаточно участников для проведения розыгрыша"
            }, raffle_id)
            return

        logger.info(f"Starting raffle {raffle_id} with {len(participants)} participants")

        # Сохраняем список участников для синхронизации с клиентами
        participant_list = [{
            "id": p.telegram_id,
            "username": p.username or f"{p.first_name} {p.last_name or ''}".strip(),
            "first_name": p.first_name,
            "last_name": p.last_name
        } for p in participants]

        # Инициализируем состояние розыгрыша
        raffle_states[raffle_id] = {
            "participants": list(participants),
            "remaining_participants": list(participants),
            "winners": [],
            "completed_positions": set(),
            "participant_list": participant_list,
            "lock": asyncio.Lock()  # локальная блокировка
        }

        # Сообщаем всем клиентам о начале
        await manager.broadcast({
            "type": "raffle_starting",
            "total_participants": len(participants),
            "total_prizes": len(raffle.prizes)
        }, raffle_id)

        await asyncio.sleep(3)

        # Разыгрываем призы начиная с последнего места
        sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)

        for position in sorted_positions:
            state = raffle_states.get(raffle_id)
            if not state:
                break

            async with state['lock']:
                # пропускаем, если это место уже разыграно
                if int(position) in state['completed_positions']:
                    logger.info(f"Position {position} already completed")
                    continue

                remaining_participants = state['remaining_participants']
                if not remaining_participants:
                    logger.error(f"No participants left for position {position}")
                    break

                            # сервер выбирает случайного победителя
                winner_index = random.randint(0, len(remaining_participants) - 1)
                winner = remaining_participants[winner_index]
                winner_data = {
                    "id": winner.telegram_id,
                    "username": winner.username,
                    "first_name": winner.first_name,
                    "last_name": winner.last_name
                }

                # Логируем для отладки
                logger.info(f"Position {position}: Selected winner {winner.username} (id={winner.telegram_id})")
                logger.info(f"Remaining participants: {[p.telegram_id for p in remaining_participants]}")

                # отправляем клиентам событие wheel_start с ID победителя (не индекс!)
                await manager.broadcast({
                    "type": "wheel_start",
                    "position": int(position),
                    "prize": raffle.prizes[position],
                    "participants": state['participant_list'],
                    "predetermined_winner_id": winner.telegram_id,  # Отправляем ID, не индекс!
                    "predetermined_winner": winner_data,
                    "remaining_participants_ids": [p.telegram_id for p in remaining_participants]  # Для отладки
                }, raffle_id)

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

                        # обновляем состояние
                        state['completed_positions'].add(int(position))
                        state['winners'].append(winner_data)
                        state['remaining_participants'] = [
                            p for p in state['remaining_participants']
                            if p.telegram_id != winner.telegram_id
                        ]

                        # сообщаем всем о победителе
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
