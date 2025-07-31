from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta, timezone
import asyncio
import logging
from ..routers.websocket import run_slot
from ..database import async_session_maker
from ..models import Raffle, Participant, User
from ..services.telegram import TelegramService
from ..services.notifications import NotificationService
from ..websocket_manager import manager

logger = logging.getLogger(__name__)

class RaffleService:
    @staticmethod
    async def check_and_start_draws():
        """Check for raffles that need to start drawing"""
        async with async_session_maker() as db:
            # Find raffles where end_date has passed but draw hasn't started
            result = await db.execute(
                select(Raffle).where(
                    Raffle.is_active == True,
                    Raffle.is_completed == False,
                    Raffle.draw_started == False,
                    Raffle.end_date <= datetime.utcnow()
                )
            )
            raffles = result.scalars().all()
            
            for raffle in raffles:
                # Mark draw as started
                raffle.draw_started = True
                await db.commit()
                
                # Get participants
                participants_result = await db.execute(
                    select(User).join(Participant).where(
                        Participant.raffle_id == raffle.id
                    )
                )
                participants = participants_result.scalars().all()
                
                # Check if we have enough participants
                if len(participants) < len(raffle.prizes):
                    # Not enough participants, cancel raffle
                    raffle.is_active = False
                    raffle.is_completed = True
                    await db.commit()
                    
                    # Notify about cancellation
                    logger.warning(f"Raffle {raffle.id} cancelled due to insufficient participants")
                    continue
                
                # Notify users that draw will start
                await NotificationService.notify_raffle_starting(raffle.id)
                
                # Schedule wheel start after delay
                asyncio.create_task(
                    RaffleService._start_wheel_after_delay(
                        raffle.id, 
                        raffle.draw_delay_minutes
                    )
                )
    
    @staticmethod
    async def _start_wheel_after_delay(raffle_id: int, delay_minutes: int):
        """Start wheel after specified delay with countdown"""
        try:
            # Send countdown updates every second
            total_seconds = delay_minutes * 60
            
            while total_seconds > 0:
                # Send countdown to all connected clients
                await manager.broadcast({
                    "type": "countdown",
                    "seconds": total_seconds
                }, raffle_id)
                
                # Wait 1 second
                await asyncio.sleep(1)
                total_seconds -= 1
            
            # Send final countdown
            await manager.broadcast({
                "type": "countdown",
                "seconds": 0
            }, raffle_id)
            
            # Start the wheel
            async with async_session_maker() as db:
                # Импортируем функцию правильно
                from ..routers.websocket import run_slot
                
                # Check if raffle is still active
                result = await db.execute(
                    select(Raffle).where(Raffle.id == raffle_id)
                )
                raffle = result.scalar_one_or_none()
                
                if raffle and not raffle.is_completed:
                    logger.info(f"Starting wheel for raffle {raffle_id}")
                    await run_slot(raffle_id, db)
                    
        except Exception as e:
            logger.error(f"Error in wheel delay for raffle {raffle_id}: {e}")