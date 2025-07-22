from fastapi import APIRouter, Request
import aiohttp
import os

router = APIRouter()

BOT_TOKEN = os.getenv("BOT_TOKEN")

@router.post("/webhook")
async def bot_webhook(request: Request):
    """Прокси webhook для бота на Railway"""
    data = await request.json()
    
    # Переадресация на бота на Railway
    bot_url = os.getenv("BOT_WEBHOOK_URL", "https://your-bot.up.railway.app/webhook")
    
    async with aiohttp.ClientSession() as session:
        async with session.post(bot_url, json=data) as response:
            return await response.json()