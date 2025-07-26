import asyncio
from typing import List, Dict, Optional
from datetime import datetime
import logging

from ..services.telegram import TelegramService
from ..database import async_session_maker
from ..models import User, Raffle, Participant
from sqlalchemy import select

logger = logging.getLogger(__name__)

class NotificationService:
    """Service for managing notifications"""
    
    @staticmethod
    async def notify_new_raffle(raffle_id: int, raffle_data: dict):
        """Send notification about new raffle to all users with notifications enabled"""
        async with async_session_maker() as db:
            # Get users with notifications enabled
            result = await db.execute(
                select(User).where(User.notifications_enabled == True)
            )
            users = result.scalars().all()
            
            if not users:
                logger.info("No users with notifications enabled")
                return
            
            user_ids = [user.telegram_id for user in users]
            
            # Send notifications
            await TelegramService.notify_new_raffle(
                raffle_id,
                user_ids,
                raffle_data
            )
            
            logger.info(f"Sent new raffle notifications to {len(user_ids)} users")
    
    @staticmethod
    async def notify_raffle_starting(raffle_id: int):
        """Notify participants and subscribers that raffle is starting"""
        async with async_session_maker() as db:
            # Get raffle
            raffle_result = await db.execute(
                select(Raffle).where(Raffle.id == raffle_id)
            )
            raffle = raffle_result.scalar_one_or_none()
            
            if not raffle:
                logger.error(f"Raffle {raffle_id} not found")
                return
            
            # Get participants
            participants_result = await db.execute(
                select(User).join(Participant).where(
                    Participant.raffle_id == raffle_id
                )
            )
            participants = participants_result.scalars().all()
            participant_ids = [p.telegram_id for p in participants]
            
            # Get users with notifications
            notif_result = await db.execute(
                select(User).where(User.notifications_enabled == True)
            )
            notif_users = notif_result.scalars().all()
            notif_ids = [u.telegram_id for u in notif_users]
            
            # Combine and deduplicate
            all_user_ids = list(set(participant_ids + notif_ids))
            
            # Send notifications to users
            await TelegramService.notify_raffle_start(
                raffle_id,
                all_user_ids,
                {
                    "title": raffle.title,
                    "photo_url": raffle.photo_url
                }
            )
            
            # НОВОЕ: Отправка уведомления в каналы для публикации
            if raffle.post_channels:
                await NotificationService.notify_channels_raffle_start(
                    raffle_id,
                    raffle.title,
                    raffle.photo_url,
                    raffle.post_channels
                )
            
            logger.info(f"Sent raffle start notifications to {len(all_user_ids)} users")

    @staticmethod
    async def notify_channels_raffle_start(raffle_id: int, title: str, photo_url: str, channels: List[str]):
        """Уведомление каналов о начале розыгрыша"""
        import os
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        WEBAPP_URL = os.getenv("WEBAPP_URL")
        
        text = (
            f"🎰 **Розыгрыш начался!**\n\n"
            f"**{title}**\n\n"
            f"Прямо сейчас определяются победители!\n"
            f"Смотрите live-трансляцию розыгрыша!"
        )
        
        keyboard = {
            "inline_keyboard": [[{
                "text": "🎰 Смотреть розыгрыш",
                "url": f"{WEBAPP_URL}/raffle/{raffle_id}/live"
            }]]
        }
        
        import aiohttp
        
        for channel in channels:
            channel = channel.replace('@', '')
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
                
                if photo_url and photo_url.startswith('http'):
                    data = {
                        "chat_id": f"@{channel}",
                        "photo": photo_url,
                        "caption": text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard
                    }
                    method = "sendPhoto"
                else:
                    data = {
                        "chat_id": f"@{channel}",
                        "text": text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard
                    }
                    method = "sendMessage"
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url + method, json=data) as response:
                        result = await response.json()
                        if not result.get("ok"):
                            logger.error(f"Failed to notify channel @{channel}: {result}")
                        else:
                            logger.info(f"Successfully notified channel @{channel} about raffle start")
                            
            except Exception as e:
                logger.error(f"Error notifying channel @{channel}: {e}")
    
    @staticmethod
    async def notify_winners(raffle_id: int, winners: List[Dict]):
        """Notify winners about their prizes"""
        for winner in winners:
            try:
                text = (
                    f"🎉 **Поздравляем!**\n\n"
                    f"Вы заняли **{winner['position']} место** в розыгрыше и выиграли:\n"
                    f"**{winner['prize']}**\n\n"
                    f"Свяжитесь с администратором для получения приза!"
                )
                
                await TelegramService.send_notification(
                    winner['user']['id'],
                    text
                )
                
                await asyncio.sleep(0.1)  # Rate limiting
            except Exception as e:
                logger.error(f"Error notifying winner {winner['user']['id']}: {e}")
    
    @staticmethod
    async def notify_raffle_results(raffle_id: int, winners: List[Dict]):
        """Notify all users and channels about raffle results"""
        async with async_session_maker() as db:
            # Get raffle data
            raffle_result = await db.execute(
                select(Raffle).where(Raffle.id == raffle_id)
            )
            raffle = raffle_result.scalar_one_or_none()
            
            if not raffle:
                logger.error(f"Raffle {raffle_id} not found for results notification")
                return
            
            # Format winners text
            winners_text = "\n".join([
                f"{w['position']}. @{w['user']['username'] or w['user']['first_name']} - {w['prize']}"
                for w in sorted(winners, key=lambda x: x['position'])
            ])
            
            # Get users with notifications enabled
            users_result = await db.execute(
                select(User).where(User.notifications_enabled == True)
            )
            users = users_result.scalars().all()
            user_ids = [u.telegram_id for u in users]
            
            # Also get all participants
            participants_result = await db.execute(
                select(User).join(Participant).where(
                    Participant.raffle_id == raffle_id
                )
            )
            participants = participants_result.scalars().all()
            participant_ids = [p.telegram_id for p in participants]
            
            # Combine and deduplicate
            all_user_ids = list(set(user_ids + participant_ids))
            
            # Send to users
            keyboard = {
                "inline_keyboard": [[{
                    "text": "📊 Посмотреть результаты",
                    "web_app": {"url": f"{os.getenv('WEBAPP_URL')}/raffle/{raffle_id}/history"}
                }]]
            }
            
            text = (
                f"🎊 **Розыгрыш завершен!**\n\n"
                f"**{raffle.title}**\n\n"
                f"🏆 **Победители:**\n{winners_text}\n\n"
                f"Поздравляем победителей! 🎉"
            )
            
            for user_id in all_user_ids:
                await TelegramService.send_notification(
                    user_id,
                    text,
                    raffle.photo_url,
                    keyboard
                )
                await asyncio.sleep(0.05)
            
            # Send to post channels
            if raffle.post_channels:
                await NotificationService.notify_channels_results(
                    raffle_id,
                    raffle.title,
                    raffle.photo_url,
                    raffle.post_channels,
                    winners_text
                )

    @staticmethod
    async def notify_channels_results(raffle_id: int, title: str, photo_url: str, channels: List[str], winners_text: str):
        """Notify channels about raffle results"""
        import os
        BOT_TOKEN = os.getenv("BOT_TOKEN")
        WEBAPP_URL = os.getenv("WEBAPP_URL")
        
        text = (
            f"🎊 **Розыгрыш завершен!**\n\n"
            f"**{title}**\n\n"
            f"🏆 **Победители:**\n{winners_text}\n\n"
            f"Поздравляем победителей! 🎉"
        )
        
        keyboard = {
            "inline_keyboard": [[{
                "text": "📊 Все результаты",
                "url": f"{WEBAPP_URL}/raffle/{raffle_id}/history"
            }]]
        }
        
        import aiohttp
        
        for channel in channels:
            channel = channel.replace('@', '')
            try:
                url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
                
                if photo_url and photo_url.startswith('http'):
                    data = {
                        "chat_id": f"@{channel}",
                        "photo": photo_url,
                        "caption": text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard
                    }
                    method = "sendPhoto"
                else:
                    data = {
                        "chat_id": f"@{channel}",
                        "text": text,
                        "parse_mode": "Markdown",
                        "reply_markup": keyboard
                    }
                    method = "sendMessage"
                
                async with aiohttp.ClientSession() as session:
                    async with session.post(url + method, json=data) as response:
                        result = await response.json()
                        if not result.get("ok"):
                            logger.error(f"Failed to notify channel @{channel} about results: {result}")
                        else:
                            logger.info(f"Successfully notified channel @{channel} about results")
                            
            except Exception as e:
                logger.error(f"Error notifying channel @{channel} about results: {e}")

    @staticmethod
    async def notify_channel_check_reminder(raffle_id: int):
        """Send reminder to check channel subscriptions before raffle ends"""
        async with async_session_maker() as db:
            # Get participants who might need to verify subscriptions
            result = await db.execute(
                select(User, Raffle).join(Participant).join(Raffle).where(
                    Participant.raffle_id == raffle_id
                )
            )
            data = result.all()
            
            for user, raffle in data:
                # Check if user is still subscribed to all channels
                all_subscribed = True
                for channel in raffle.channels:
                    is_subscribed = await TelegramService.check_channel_subscription(
                        user.telegram_id,
                        channel
                    )
                    if not is_subscribed:
                        all_subscribed = False
                        break
                
                if not all_subscribed:
                    text = (
                        f"⚠️ **Напоминание**\n\n"
                        f"Розыгрыш '{raffle.title}' скоро завершится!\n"
                        f"Убедитесь, что вы подписаны на все необходимые каналы, "
                        f"иначе вы не сможете участвовать в розыгрыше."
                    )
                    
                    await TelegramService.send_notification(
                        user.telegram_id,
                        text
                    )
                    
                    await asyncio.sleep(0.1)