from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import asyncio
import random
import json
from typing import List, Dict
from datetime import datetime

from ..database import get_db
from ..models import Raffle, Participant, User, Winner
from ..main import manager

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
        
        # Shuffle participants
        participants_list = list(participants)
        random.shuffle(participants_list)
        
        winners = []
        remaining_participants = participants_list.copy()
        
        # Start from last place to first
        for position in sorted(raffle.prizes.keys(), reverse=True):
            if not remaining_participants:
                break
            
            # Send wheel data
            await manager.broadcast({
                "type": "wheel_start",
                "position": position,
                "prize": raffle.prizes[position],
                "participants": [
                    {"id": p.telegram_id, "username": p.username or p.first_name} 
                    for p in remaining_participants
                ]
            }, raffle_id)
            
            # Simulate wheel spinning (7 seconds)
            await asyncio.sleep(7)
            
            # Select winner
            winner = random.choice(remaining_participants)
            remaining_participants.remove(winner)
            
            # Save winner to database
            winner_record = Winner(
                raffle_id=raffle_id,
                user_id=winner.id,
                position=position,
                prize=raffle.prizes[position]
            )
            db.add(winner_record)
            
            winners.append({
                "position": position,
                "user": {
                    "id": winner.telegram_id,
                    "username": winner.username,
                    "first_name": winner.first_name
                },
                "prize": raffle.prizes[position]
            })
            
            # Send winner result
            await manager.broadcast({
                "type": "winner_selected",
                "position": position,
                "winner": {
                    "id": winner.telegram_id,
                    "username": winner.username or winner.first_name
                },
                "prize": raffle.prizes[position]
            }, raffle_id)
            
            await asyncio.sleep(2)  # Pause between rounds
        
        # Mark raffle as completed
        raffle.is_completed = True
        raffle.is_active = False
        await db.commit()
        
        # Send final results
        await manager.broadcast({
            "type": "raffle_complete",
            "winners": winners
        }, raffle_id)

@router.websocket("/{raffle_id}")
async def websocket_endpoint(websocket: WebSocket, raffle_id: int):
    """WebSocket endpoint for live raffle"""
    await manager.connect(websocket, raffle_id)
    
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            
            # Handle admin commands if needed
            message = json.loads(data)
            if message.get("type") == "start_wheel":
                # Check if user is admin and start wheel
                async with async_session_maker() as db:
                    await RaffleWheel.run_wheel(raffle_id, db)
                    
    except WebSocketDisconnect:
        manager.disconnect(websocket, raffle_id)