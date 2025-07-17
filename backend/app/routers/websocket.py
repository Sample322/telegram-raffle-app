from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
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
            
            # Shuffle participants
            participants_list = list(participants)
            random.shuffle(participants_list)
            
            winners = []
            remaining_participants = participants_list.copy()
            
            # Announce start
            await manager.broadcast({
                "type": "raffle_starting",
                "total_participants": len(participants),
                "total_prizes": len(raffle.prizes)
            }, raffle_id)
            
            await asyncio.sleep(3)  # Pause before starting
            
            # Start from last place to first
            # Start from last place to first
            sorted_positions = sorted(raffle.prizes.keys(), key=lambda x: int(x), reverse=True)
            for position in sorted_positions:
                if not remaining_participants:
                    break
                
                # ВАЖНО: Выбираем победителя ЗАРАНЕЕ на бэкенде
                winner = random.choice(remaining_participants)
                winner_index = participants_list.index(winner)  # Индекс победителя в исходном списке
                remaining_participants.remove(winner)
                
                # Prepare participant data for wheel
                wheel_participants = []
                for p in participants_list:  # Используем полный список, не remaining
                    wheel_participants.append({
                        "id": p.telegram_id,
                        "username": p.username or f"{p.first_name} {p.last_name or ''}".strip(),
                        "first_name": p.first_name,
                        "last_name": p.last_name
                    })
                
                # Send wheel data с информацией о победителе
                await manager.broadcast({
                    "type": "wheel_start",
                    "position": int(position),
                    "prize": raffle.prizes[position],
                    "participants": wheel_participants,
                    "winner_index": winner_index  # НОВОЕ: передаем индекс победителя
                }, raffle_id)
                
                logger.info(f"Starting wheel for position {position}, predetermined winner index: {winner_index}")
                
                # Wait for wheel animation (7 seconds)
                await asyncio.sleep(7)
                
                # Save winner to database
                winner_record = Winner(
                    raffle_id=raffle_id,
                    user_id=winner.id,
                    position=int(position),
                    prize=raffle.prizes[position]
                )
                db.add(winner_record)
                await db.commit()
                
                winner_data = {
                    "position": int(position),
                    "user": {
                        "id": winner.telegram_id,
                        "username": winner.username,
                        "first_name": winner.first_name,
                        "last_name": winner.last_name
                    },
                    "prize": raffle.prizes[position]
                }
                winners.append(winner_data)
                
                # Send winner result
                await manager.broadcast({
                    "type": "winner_selected",
                    "position": int(position),
                    "winner": {
                        "id": winner.telegram_id,
                        "username": winner.username or f"{winner.first_name} {winner.last_name or ''}".strip(),
                        "first_name": winner.first_name,
                        "last_name": winner.last_name
                    },
                    "prize": raffle.prizes[position]
                }, raffle_id)
                
                logger.info(f"Winner for position {position}: {winner.username or winner.first_name}")
                
                # Pause between rounds
                if position != "1":  # Don't pause after last winner
                    await asyncio.sleep(3)
            
            # Mark raffle as completed
            raffle.is_completed = True
            raffle.is_active = False
            await db.commit()
            
            # Send final results
            await manager.broadcast({
                "type": "raffle_complete",
                "winners": winners
            }, raffle_id)
            
            logger.info(f"Raffle {raffle_id} completed successfully")
            
            # Send notifications about completion
            await NotificationService.notify_winners(raffle_id, winners)
            
            # Get all users to notify
            users_result = await db.execute(
                select(User).where(User.notifications_enabled == True)
            )
            users = users_result.scalars().all()
            
            # Also get participants
            participants_result = await db.execute(
                select(User).join(Participant).where(Participant.raffle_id == raffle_id)
            )
            participants = participants_result.scalars().all()
            
            # Combine and deduplicate user IDs
            all_user_ids = list(set([u.telegram_id for u in users] + [p.telegram_id for p in participants]))
            
            # Send completion notifications
            await TelegramService.notify_raffle_complete(
                raffle_id,
                all_user_ids,
                {
                    "title": raffle.title,
                    "photo_url": raffle.photo_url
                },
                winners
            )
            
        except Exception as e:
            logger.error(f"Error running wheel for raffle {raffle_id}: {e}")
            await manager.broadcast({
                "type": "error",
                "message": "Произошла ошибка при проведении розыгрыша"
            }, raffle_id)

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
            
            # Handle admin commands if needed
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except:
                pass
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)