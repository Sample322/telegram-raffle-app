import aiohttp
import hashlib
import hmac
from typing import Optional, List
import os
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app.onrender.com")

class TelegramService:
    @staticmethod
    def validate_init_data(init_data: str) -> dict:
        """Validate Telegram WebApp init data"""
        try:
            data_check_string = init_data
            secret_key = hmac.new(
                "WebAppData".encode(), 
                BOT_TOKEN.encode(), 
                hashlib.sha256
            ).digest()
            
            # Parse init data
            params = {}
            for param in init_data.split('&'):
                key, value = param.split('=')
                params[key] = value
            
            # Verify hash
            received_hash = params.pop('hash', '')
            data_check_arr = []
            for key in sorted(params.keys()):
                data_check_arr.append(f"{key}={params[key]}")
            
            data_check_string = '\n'.join(data_check_arr)
            
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            if calculated_hash == received_hash:
                return params
            return None
        except:
            return None
    
    @staticmethod
    async def check_channel_subscription(user_id: int, channel_username: str) -> bool:
        """Check if user is subscribed to channel"""
        channel = channel_username.replace('@', '')
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        
        async with aiohttp.ClientSession() as session:
            try:
                async with session.post(url, json={
                    "chat_id": f"@{channel}",
                    "user_id": user_id
                }) as response:
                    data = await response.json()
                    if data.get("ok"):
                        status = data["result"]["status"]
                        return status in ["creator", "administrator", "member"]
                    return False
            except:
                return False
    
    @staticmethod
    async def send_notification(user_id: int, text: str, photo: Optional[str] = None, 
                              keyboard: Optional[dict] = None):
        """Send notification to user"""
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/"
        
        async with aiohttp.ClientSession() as session:
            try:
                if photo:
                    method = "sendPhoto"
                    data = {
                        "chat_id": user_id,
                        "photo": photo,
                        "caption": text,
                        "parse_mode": "Markdown"
                    }
                else:
                    method = "sendMessage"
                    data = {
                        "chat_id": user_id,
                        "text": text,
                        "parse_mode": "Markdown"
                    }
                
                if keyboard:
                    data["reply_markup"] = keyboard
                
                async with session.post(url + method, json=data) as response:
                    return await response.json()
            except Exception as e:
                print(f"Error sending notification: {e}")
                return None
    
    @staticmethod
    async def notify_raffle_start(raffle_id: int, users: List[int], raffle_data: dict):
        """Notify users about raffle start"""
        keyboard = {
            "inline_keyboard": [[{
                "text": "🎯 Открыть розыгрыш",
                "web_app": {"url": f"{WEBAPP_URL}/raffle/{raffle_id}/live"}
            }]]
        }
        
        text = (
            f"🎰 **Розыгрыш начался!**\n\n"
            f"**{raffle_data['title']}**\n\n"
            f"Нажмите кнопку ниже, чтобы посмотреть live-розыгрыш!"
        )
        
        for user_id in users:
            await TelegramService.send_notification(
                user_id, 
                text,
                raffle_data.get('photo_url'),
                keyboard
            )
    
    @staticmethod
    async def notify_new_raffle(raffle_id: int, users: List[int], raffle_data: dict):
        """Notify users about new raffle"""
        keyboard = {
            "inline_keyboard": [[{
                "text": "🎯 Участвовать",
                "web_app": {"url": f"{WEBAPP_URL}/raffle/{raffle_id}"}
            }]]
        }
        
        # Format prizes
        prizes_text = "\n".join([f"{i}. {prize}" for i, prize in raffle_data['prizes'].items()])
        
        text = (
            f"🎉 **Новый розыгрыш!**\n\n"
            f"**{raffle_data['title']}**\n\n"
            f"{raffle_data['description']}\n\n"
            f"🏆 **Призы:**\n{prizes_text}\n\n"
            f"⏰ До {raffle_data['end_date']}"
        )
        
        for user_id in users:
            await TelegramService.send_notification(
                user_id,
                text,
                raffle_data.get('photo_url'),
                keyboard
            )