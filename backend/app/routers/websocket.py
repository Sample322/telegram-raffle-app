# backend/app/routers/websocket.py - ИСПРАВЛЕННАЯ ВЕРСИЯ

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import random
import json
from typing import List, Dict
from datetime import datetime

from ..database import get_db, async_session_maker
from ..models import Raffle, Participant, User, Winner
from ..websocket_manager import manager
from ..services.telegram import TelegramService

router = APIRouter()

class RaffleWheel:
    @staticmethod
    async def run_wheel(raffle_id: int, db: AsyncSession):
        """Run the raffle wheel animation"""
        # Get raffle and participants
        raffle_result = await db.execute(select(Raffle).where(Raffle.id == raffle_id))
        raffle = raffle_result.scalar_one_or_none()
        
        if not raffle or raffle.is_completed:
            return
        
        # Get all participants
        participants_result = await db.execute(
            select(User).join(Participant).where(Participant.raffle_id == raffle_id)
        )
        participants = participants_result.scalars().all()
        
        if len(participants) < len(raffle.prizes):
            await manager.broadcast({
                "type": "error",
                "message": "Not enough participants"
            }, raffle_id)
            return
        
        # Send initial countdown
        for i in range(300, 0, -1):  # 5 minutes countdown
            await manager.broadcast({
                "type": "countdown",
                "seconds": i
            }, raffle_id)
            await asyncio.sleep(1)
        
        # Start the wheel
        await manager.broadcast({
            "type": "wheel_starting",
            "message": "Розыгрыш начинается!"
        }, raffle_id)
        
        await asyncio.sleep(3)  # Dramatic pause
        
        # Shuffle participants
        participants_list = list(participants)
        random.shuffle(participants_list)
        
        winners = []
        remaining_participants = participants_list.copy()
        
        # Start from last place to first
        for position in sorted(raffle.prizes.keys(), reverse=True):
            if not remaining_participants:
                break
            
            position_int = int(position)
            
            # Send wheel data
            await manager.broadcast({
                "type": "wheel_start",
                "position": position_int,
                "prize": raffle.prizes[position],
                "participants": [
                    {
                        "id": p.telegram_id, 
                        "username": p.username,
                        "first_name": p.first_name,
                        "last_name": p.last_name
                    } 
                    for p in remaining_participants
                ]
            }, raffle_id)
            
            # Wait for wheel animation (7 seconds)
            await asyncio.sleep(7)
            
            # Select winner
            winner = random.choice(remaining_participants)
            remaining_participants.remove(winner)
            
            # Save winner to database
            winner_record = Winner(
                raffle_id=raffle_id,
                user_id=winner.id,
                position=position_int,
                prize=raffle.prizes[position]
            )
            db.add(winner_record)
            await db.commit()
            
            winners.append({
                "position": position_int,
                "user": {
                    "id": winner.telegram_id,
                    "username": winner.username,
                    "first_name": winner.first_name,
                    "last_name": winner.last_name
                },
                "prize": raffle.prizes[position]
            })
            
            # Send winner result
            await manager.broadcast({
                "type": "winner_selected",
                "position": position_int,
                "winner": {
                    "id": winner.telegram_id,
                    "username": winner.username,
                    "first_name": winner.first_name,
                    "last_name": winner.last_name
                },
                "prize": raffle.prizes[position]
            }, raffle_id)
            
            await asyncio.sleep(3)  # Pause between rounds
        
        # Mark raffle as completed
        raffle.is_completed = True
        raffle.is_active = False
        await db.commit()
        
        # Send final results
        await manager.broadcast({
            "type": "raffle_complete",
            "winners": winners
        }, raffle_id)
        
        # Send notifications to winners
        await TelegramService.notify_winners(raffle_id, winners)

@router.websocket("/{raffle_id}")
async def websocket_endpoint(websocket: WebSocket, raffle_id: int):
    """WebSocket endpoint for live raffle"""
    await manager.connect(websocket, raffle_id)
    
    try:
        # Check if wheel should be started automatically
        async with async_session_maker() as db:
            raffle_result = await db.execute(
                select(Raffle).where(Raffle.id == raffle_id)
            )
            raffle = raffle_result.scalar_one_or_none()
            
            if raffle and raffle.draw_started and not raffle.is_completed:
                # Start wheel automatically if draw has started
                asyncio.create_task(RaffleWheel.run_wheel(raffle_id, db))
        
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            
            # Handle messages if needed
            try:
                message = json.loads(data)
                if message.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
            except:
                pass
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)