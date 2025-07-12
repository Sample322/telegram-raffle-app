from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timedelta
import asyncio

from ..database import async_session_maker
from ..models import Raffle, Participant, User
from ..services.telegram import TelegramService
from ..routers.websocket import RaffleWheel

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
                    await db.commit()
                    continue
                
                # Notify users that draw will start
                user_ids = [p.telegram_id for p in participants]
                
                # Also notify users with notifications enabled
                notif_users_result = await db.execute(
                    select(User).where(User.notifications_enabled == True)
                )
                notif_users = notif_users_result.scalars().all()
                
                all_user_ids = list(set(user_ids + [u.telegram_id for u in notif_users]))
                
                await TelegramService.notify_raffle_start(
                    raffle.id,
                    all_user_ids,
                    {
                        "title": raffle.title,
                        "photo_url": raffle.photo_url
                    }
                )
                
                # Schedule wheel start after delay
                asyncio.create_task(
                    RaffleService._start_wheel_after_delay(
                        raffle.id, 
                        raffle.draw_delay_minutes
                    )
                )
    
    @staticmethod
    async def _start_wheel_after_delay(raffle_id: int, delay_minutes: int):
        """Start wheel after specified delay"""
        await asyncio.sleep(delay_minutes * 60)
        
        async with async_session_maker() as db:
            await RaffleWheel.run_wheel(raffle_id, db)