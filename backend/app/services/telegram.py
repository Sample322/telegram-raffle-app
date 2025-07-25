import aiohttp
import hashlib
import hmac
from typing import Optional, List, Dict
import os
from datetime import datetime, timedelta
import urllib.parse
import json
import asyncio
from functools import lru_cache
import time

BOT_TOKEN = os.getenv("BOT_TOKEN")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://your-app.onrender.com")

# Кеш для результатов проверки подписки
subscription_cache: Dict[str, Dict] = {}
CACHE_TTL = 60  # 60 секунд

class TelegramService:
    @staticmethod
    def validate_init_data(init_data: str) -> dict:
        """Validate Telegram WebApp init data"""
        try:
            # Создаем секретный ключ
            secret_key = hmac.new(
                b"WebAppData", 
                BOT_TOKEN.encode(), 
                hashlib.sha256
            ).digest()
            
            # Парсим параметры
            params = {}
            for param in init_data.split('&'):
                if '=' in param:
                    key, value = param.split('=', 1)
                    # URL-декодируем значения
                    params[key] = urllib.parse.unquote(value)
            
            # Извлекаем и удаляем hash
            received_hash = params.pop('hash', '')
            
            # Формируем строку для проверки подписи
            data_check_arr = []
            for key in sorted(params.keys()):
                data_check_arr.append(f"{key}={params[key]}")
            
            data_check_string = '\n'.join(data_check_arr)
            
            # Вычисляем hash
            calculated_hash = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # Проверяем подпись
            if calculated_hash == received_hash:
                # Парсим user JSON, если есть
                if 'user' in params:
                    try:
                        params['user'] = json.loads(params['user'])
                    except:
                        pass
                return params
            
            return None
            
        except Exception as e:
            print(f"Error validating init data: {e}")
            return None
    
    @staticmethod
    async def check_channel_subscription(user_id: int, channel_username: str, retry_count: int = 3) -> bool:
        """Check if user is subscribed to channel with caching and retries"""
        channel = channel_username.replace('@', '')
        cache_key = f"{user_id}:{channel}"
        
        # Проверяем кеш
        if cache_key in subscription_cache:
            cached_data = subscription_cache[cache_key]
            if time.time() - cached_data['timestamp'] < CACHE_TTL:
                return cached_data['is_subscribed']
        
        url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember"
        
        async with aiohttp.ClientSession() as session:
            for attempt in range(retry_count):
                try:
                    async with session.post(url, json={
                        "chat_id": f"@{channel}",
                        "user_id": user_id
                    }, timeout=aiohttp.ClientTimeout(total=10)) as response:
                        data = await response.json()
                        
                        if data.get("ok"):
                            status = data["result"]["status"]
                            is_subscribed = status in ["creator", "administrator", "member"]
                            
                            # Сохраняем в кеш
                            subscription_cache[cache_key] = {
                                'is_subscribed': is_subscribed,
                                'timestamp': time.time()
                            }
                            
                            return is_subscribed
                        
                        # Если ошибка от API Telegram
                        error_code = data.get("error_code")
                        if error_code == 400:  # Bad Request - канал не существует или бот не админ
                            print(f"Bot is not admin in channel @{channel} or channel doesn't exist")
                            return False
                        
                except asyncio.TimeoutError:
                    print(f"Timeout checking subscription for user {user_id} in @{channel}, attempt {attempt + 1}/{retry_count}")
                except Exception as e:
                    print(f"Error checking subscription: {e}, attempt {attempt + 1}/{retry_count}")
                
                # Ждем перед следующей попыткой
                if attempt < retry_count - 1:
                    await asyncio.sleep(1)
            
            # Если все попытки неудачны, считаем что не подписан
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
                "text": "🎰 Смотреть розыгрыш",
                "web_app": {"url": f"{WEBAPP_URL}/raffle/{raffle_id}/live"}
            }]]
        }
        
        text = (
            f"🎰 **Розыгрыш начался!**\n\n"
            f"**{raffle_data['title']}**\n\n"
            f"Нажмите кнопку ниже, чтобы посмотреть live-розыгрыш!"
        )
        
        # Используем существующий метод send_notification
        for user_id in users:
            await TelegramService.send_notification(
                user_id, 
                text,
                raffle_data.get('photo_url'),
                keyboard
            )
            await asyncio.sleep(0.05)  # Rate limiting
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
        
        # ВАЖНО: Используем существующий метод send_notification
        for user_id in users:
            await TelegramService.send_notification(
                user_id,
                text,
                raffle_data.get('photo_url'),
                keyboard
            )
            await asyncio.sleep(0.05)  # Rate limiting
    
    @staticmethod
    async def notify_raffle_complete(raffle_id: int, users: List[int], raffle_data: dict, winners: List[dict]):
        """Notify users about raffle completion"""
        keyboard = {
            "inline_keyboard": [[{
                "text": "📊 Посмотреть результаты",
                "web_app": {"url": f"{WEBAPP_URL}/raffle/{raffle_id}/live"}
            }]]
        }
        
        # Format winners
        winners_text = "\n".join([
            f"{w['position']}. @{w['user']['username'] or w['user']['first_name']} - {w['prize']}"
            for w in sorted(winners, key=lambda x: x['position'])
        ])
        
        text = (
            f"🎊 **Розыгрыш завершен!**\n\n"
            f"**{raffle_data['title']}**\n\n"
            f"🏆 **Победители:**\n{winners_text}\n\n"
            f"Поздравляем победителей! 🎉"
        )
        
        for user_id in users:
            await TelegramService.send_notification(
                user_id,
                text,
                raffle_data.get('photo_url'),
                keyboard
            )
            await asyncio.sleep(0.05)  # Rate limiting