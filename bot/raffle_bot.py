import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import List, Dict, Any
import random
from pathlib import Path
import csv
import json
import os
from dotenv import load_dotenv
import aiohttp
import time
import hashlib
import hmac
import urllib.parse
from aiogram import types, F
from aiogram.fsm.context import FSMContext
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, \
                         ReplyKeyboardMarkup, KeyboardButton
from aiogram.exceptions import TelegramBadRequest

# ────────────────────────────────
# переменные окружения
# ────────────────────────────────
load_dotenv()

BOT_TOKEN  = os.getenv("BOT_TOKEN", "")
# В файле bot/raffle_bot.py в начале файла:
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://raffle-app-qtma.onrender.com")
API_URL    = os.getenv("API_URL",   "https://raffle-api-y3im.onrender.com")
ADMIN_IDS  = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x]

# ────────────────────────────────
# aiogram setup
# ────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())

# ────────────────────────────────
# FSM‑состояния (без изменений)
# ────────────────────────────────
class RaffleStates(StatesGroup):
    waiting_title         = State()
    waiting_description   = State()
    waiting_photo         = State()
    waiting_channels      = State()
    waiting_prizes        = State()
    waiting_prize_details = State()
    waiting_end_datetime  = State()
    waiting_speed        = State()

# ────────────────────────────────
# ИСПРАВЛЕННЫЙ класс APIClient
# ────────────────────────────────
class APIClient:
    """Клиент, подписывающий запросы как Telegram Web‑App"""

    def __init__(self, api_url: str):
        self.api_url = api_url.rstrip("/")

    # ──────────────────────────────────────────────────────────
    async def create_raffle(self, raffle_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/admin/raffles"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_url}/api/admin/raffles"

            # 1. тело запроса
            api_data = {
                "title":  raffle_data["title"],
                "description": raffle_data["description"],
                "photo_url": raffle_data.get("photo_url", ""),
                "photo_file_id": raffle_data.get("photo_file_id"),
                "channels": raffle_data["channels"].split() if raffle_data.get("channels") else [],
                "prizes": raffle_data.get("prizes", {}),
                "end_date": raffle_data["end_date"].isoformat(),
                "draw_delay_minutes": 5,
                "wheel_speed": raffle_data.get("wheel_speed", "fast"),
            }

            # 2. формируем initData администратора
            auth_date = int(time.time())
            
            # ВАЖНО: id должен быть строкой в JSON
            admin_data = {
                "id": str(ADMIN_IDS[0]),     # Преобразуем в строку!
                "first_name": "Admin",
                "username": "admin",
            }

            # 2‑a JSON без пробелов
            user_json = json.dumps(admin_data, separators=(",", ":"), ensure_ascii=False)
            
            # 2‑b URL‑кодируем JSON
            encoded_user = urllib.parse.quote(user_json)
            
            # 2‑c формируем параметры для подписи
            params = {
                "auth_date": str(auth_date),
                "user": user_json  # Используем НЕ закодированный JSON для подписи
            }
            
            # 2‑d создаем строку для подписи
            data_check_arr = []
            for key in sorted(params.keys()):
                data_check_arr.append(f"{key}={params[key]}")
            data_check_string = "\n".join(data_check_arr)
            
            # 2‑e вычисляем hash
            secret_key = hmac.new(
                b"WebAppData",
                BOT_TOKEN.encode(),
                hashlib.sha256
            ).digest()
            
            hash_value = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            # 2‑f итоговый initData (с URL-кодированным user)
            init_data = f"user={encoded_user}&auth_date={auth_date}&hash={hash_value}"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {init_data}",
            }

            # 3. сам POST
            try:
                logger.info(f"Creating raffle with admin_id: {ADMIN_IDS[0]}")
                logger.debug(f"Init data: {init_data[:50]}...")
                
                async with session.post(url, json=api_data, headers=headers, ssl=False) as resp:
                    resp_text = await resp.text()
                    logger.debug(f"Response status: {resp.status}")
                    logger.debug(f"Response text: {resp_text}")
                    
                    if resp.status in (200, 201):
                        return await resp.json()
                    raise Exception(f"API error {resp.status}: {resp_text}")
            except aiohttp.ClientError as exc:
                logger.error(f"Network error: {exc}")
                raise Exception(f"Ошибка сети: {exc}") from exc
    # ──────────────────────────────────────────────────────────
    
    async def get_active_raffles(self) -> List[dict]:
        """Получение активных розыгрышей из API"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_url}/api/raffles/active"
            try:
                async with session.get(url, ssl=False) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
            except Exception as e:
                logger.error(f"Error getting active raffles: {e}")
                return []
    
    async def get_completed_raffles(self, limit: int = 10) -> List[dict]:
        """Получение завершенных розыгрышей из API"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_url}/api/raffles/completed?limit={limit}"
            try:
                async with session.get(url, ssl=False) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
            except Exception as e:
                logger.error(f"Error getting completed raffles: {e}")
                return []
class DatabaseManager:
    """Класс для работы с локальной базой данных"""
    
    def __init__(self, db_path: str = "/app/data/raffle_bot.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    notifications_enabled INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Таблица розыгрышей (для локального кеша)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raffles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    api_id INTEGER,
                    title TEXT NOT NULL,
                    description TEXT,
                    photo_file_id TEXT,
                    photo_url TEXT,
                    channels TEXT,
                    prizes TEXT,
                    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_date TIMESTAMP,
                    winners_count INTEGER DEFAULT 1,
                    wheel_speed TEXT DEFAULT 'fast',
                    is_active INTEGER DEFAULT 1,
                    is_completed INTEGER DEFAULT 0,
                    result_message TEXT
                )
            ''')
            
            # Таблица участников розыгрышей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raffle_id INTEGER,
                    user_id INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (raffle_id) REFERENCES raffles (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id),
                    UNIQUE(raffle_id, user_id)
                )
            ''')
            
            # Таблица победителей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS winners (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    raffle_id INTEGER,
                    user_id INTEGER,
                    won_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (raffle_id) REFERENCES raffles (id),
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')
            
            conn.commit()
    
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Добавление нового пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_name=excluded.last_name
            ''', (user_id, username, first_name, last_name))
            conn.commit()
    
    def toggle_notifications(self, user_id: int) -> bool:
        """Переключение уведомлений для пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT notifications_enabled FROM users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            new_status = 0 if result and result[0] else 1
            cursor.execute('UPDATE users SET notifications_enabled = ? WHERE user_id = ?', (new_status, user_id))
            conn.commit()
            
            return bool(new_status)
    
    def get_users_with_notifications(self) -> List[int]:
        """Получение списка пользователей с включенными уведомлениями"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM users WHERE notifications_enabled = 1')
            return [row[0] for row in cursor.fetchall()]
    
    def create_raffle_cache(self, api_id: int, title: str, description: str, photo_file_id: str,
                          photo_url: str, channels: str, prizes: dict, end_date: datetime,
                          wheel_speed: str) -> int:
        """Создание локальной копии розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO raffles (api_id, title, description, photo_file_id, photo_url, channels, prizes, end_date, winners_count, wheel_speed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (api_id, title, description, photo_file_id, photo_url, channels,
                  json.dumps(prizes), end_date, len(prizes), wheel_speed))
            conn.commit()
            return cursor.lastrowid
    
    def get_active_raffle(self) -> Dict[str, Any]:
        """Получение активного розыгрыша из локального кеша"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM raffles WHERE is_active = 1 AND is_completed = 0 ORDER BY id DESC LIMIT 1')
            row = cursor.fetchone()
            if row:
                result = dict(row)
                # Преобразуем prizes из JSON строки в словарь
                if result.get('prizes'):
                    try:
                        result['prizes'] = json.loads(result['prizes'])
                    except:
                        result['prizes'] = {}
                return result
            return None

# Создание экземпляров
db = DatabaseManager()
api_client = APIClient(API_URL)

# Вспомогательные функции
def create_main_keyboard():
    """Создание основной клавиатуры"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Получать уведомления")],
            [KeyboardButton(text="🎯 Активные розыгрыши")],
            [KeyboardButton(text="📜 История розыгрышей")],
            [KeyboardButton(text="ℹ️ Информация")]
        ],
        resize_keyboard=True
    )
    return keyboard

def create_admin_keyboard():
    """Создание клавиатуры администратора"""
    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📢 Получать уведомления")],
            [KeyboardButton(text="🎯 Активные розыгрыши")],
            [KeyboardButton(text="➕ Создать розыгрыш")],
            [KeyboardButton(text="📜 История розыгрышей")],
            [KeyboardButton(text="ℹ️ Информация")]
        ],
        resize_keyboard=True
    )
    return keyboard

async def upload_photo_to_api(photo_file_id: str) -> str:
    """Загрузка фото на сервер (возвращает file_id как URL)"""
    # Пока возвращаем file_id, так как API может не поддерживать загрузку
    return photo_file_id

# Обработчики команд
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработка команды /start"""
    user = message.from_user
    db.add_user(user.id, user.username, user.first_name, user.last_name)
    
    keyboard = create_admin_keyboard() if user.id in ADMIN_IDS else create_main_keyboard()
    
    await message.answer(
        f"👋 Привет, {user.first_name}!\n\n"
        "🎉 Добро пожаловать в бот розыгрышей!\n\n"
        "Здесь вы можете:\n"
        "• Участвовать в розыгрышах призов\n"
        "• Получать уведомления о новых розыгрышах\n"
        "• Смотреть историю прошлых розыгрышей\n"
        "• Следить за результатами\n\n"
        "Используйте кнопки меню для навигации:",
        reply_markup=keyboard
    )
# ───────────────────────────────────────────────
# Админ‑кнопка «Создать розыгрыш»
# ───────────────────────────────────────────────
@dp.message(
    F.text == "➕ Создать розыгрыш",          # текст ровно как на кнопке
    F.from_user.id.in_(ADMIN_IDS)            # фильтр: только админы
)
async def create_raffle_start(message: types.Message, state: FSMContext):
    """Первый шаг мастера создания розыгрыша"""
    await state.clear()                                # сбросим старое FSM‑состояние
    await state.set_state(RaffleStates.waiting_title)  # переходим к шагу 1
    await message.answer(
        "Шаг 1/6: Введите **название** розыгрыша:",
        reply_markup=types.ReplyKeyboardRemove(),      # временно убираем меню
        parse_mode="Markdown"
    )

# Если вдруг не‑админ пришлёт тот же текст вручную
@dp.message(F.text == "➕ Создать розыгрыш")
async def create_raffle_not_allowed(message: types.Message):
    await message.answer("⛔️ Недостаточно прав для этой команды.")

@dp.message(F.text == "📢 Получать уведомления")
async def manage_notifications(message: types.Message):
    """Получать уведомления"""
    user_id = message.from_user.id
    notifications_enabled = db.toggle_notifications(user_id)
    
    status = "включены ✅" if notifications_enabled else "выключены ❌"
    await message.answer(
        f"Уведомления {status}\n\n"
        f"{'Теперь вы будете получать информацию о новых розыгрышах!' if notifications_enabled else 'Вы больше не будете получать уведомления о новых розыгрышах.'}"
    )

@dp.message(F.text == "🎯 Активные розыгрыши")
async def show_active_raffles(message: types.Message):
    """Показ активных розыгрышей"""
    try:
        # Сначала пробуем получить из API
        raffles = await api_client.get_active_raffles()
        
        if raffles:
            raffle = raffles[0]  # Показываем первый активный
            
            # Создаем кнопку для участия с Web App
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(
                    text="🎯 Участвовать", 
                    web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{raffle['id']}")
                )]
            ])
            
            # Форматируем призы
            prizes_text = ""
            if isinstance(raffle.get('prizes'), dict):
                prizes_text = "\n".join([f"{pos}. {prize}" for pos, prize in raffle['prizes'].items()])
            
            # Форматируем дату
            end_date = datetime.fromisoformat(raffle['end_date'].replace('Z', '+00:00'))
            end_date_str = end_date.strftime("%d.%m.%Y в %H:%M")
            
            caption = (
                f"🎉 **{raffle['title']}**\n\n"
                f"{raffle['description']}\n\n"
                f"🏆 **Призы:**\n{prizes_text}\n\n"
                f"⏰ Завершится: {end_date_str}\n"
                f"👥 Участников: {raffle.get('participants_count', 0)}"
            )
            
            if raffle.get('photo_url'):
                await message.answer_photo(
                    photo=raffle['photo_url'],
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await message.answer(caption, reply_markup=keyboard, parse_mode="Markdown")
        else:
            # Если API недоступен, пробуем локальный кеш
            raffle = db.get_active_raffle()
            if raffle:
                # Создаем кнопку для участия
                api_id = raffle.get('api_id', raffle['id'])
                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(
                        text="🎯 Участвовать", 
                        web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{api_id}")
                    )]
                ])
                
                # Форматируем призы
                prizes = raffle.get('prizes', {})
                if isinstance(prizes, str):
                    try:
                        prizes = json.loads(prizes)
                    except:
                        prizes = {}
                
                prizes_text = "\n".join([f"{pos}. {prize}" for pos, prize in prizes.items()])
                
                # Форматируем дату
                end_date = datetime.fromisoformat(raffle['end_date'])
                end_date_str = end_date.strftime("%d.%m.%Y в %H:%M")
                
                caption = (
                    f"🎉 **{raffle['title']}**\n\n"
                    f"{raffle['description']}\n\n"
                    f"🏆 **Призы:**\n{prizes_text}\n\n"
                    f"⏰ Завершится: {end_date_str}"
                )
                
                if raffle.get('photo_file_id'):
                    await message.answer_photo(
                        photo=raffle['photo_file_id'],
                        caption=caption,
                        reply_markup=keyboard,
                        parse_mode="Markdown"
                    )
                else:
                    await message.answer(caption, reply_markup=keyboard, parse_mode="Markdown")
            else:
                await message.answer("😔 Сейчас нет активных розыгрышей. Следите за обновлениями!")
                
    except Exception as e:
        logger.error(f"Error showing active raffles: {e}")
        await message.answer("😔 Сейчас нет активных розыгрышей. Следите за обновлениями!")

@dp.message(F.text == "📜 История розыгрышей")
async def show_history(message: types.Message):
    """Показ истории розыгрышей"""
    try:
        history = await api_client.get_completed_raffles(limit=10)
        
        if not history:
            await message.answer("📜 История розыгрышей пуста")
            return
        
        history_text = "📜 **История последних розыгрышей:**\n\n"
        
        for raffle in history:
            # Форматируем дату
            end_date = datetime.fromisoformat(raffle['end_date'].replace('Z', '+00:00'))
            date_str = end_date.strftime("%d.%m.%Y")
            
            history_text += f"🎯 **{raffle['title']}**\n"
            history_text += f"📅 Завершен: {date_str}\n"
            history_text += f"👥 Участников: {raffle.get('participants_count', 0)}\n"
            
            # Показываем победителей
            if raffle.get('winners'):
                history_text += "🏆 **Победители:**\n"
                for winner in sorted(raffle['winners'], key=lambda w: w['position']):
                    username = winner['user']['username'] or f"{winner['user']['first_name']} {winner['user'].get('last_name', '')}".strip()
                    history_text += f"  {winner['position']} место: @{username} - {winner['prize']}\n"
            
            history_text += "─" * 30 + "\n\n"
        
        # Если текст слишком длинный, разбиваем на части
        if len(history_text) > 4000:
            # Отправляем по частям
            parts = []
            current_part = ""
            lines = history_text.split('\n')
            
            for line in lines:
                if len(current_part) + len(line) + 1 < 4000:
                    current_part += line + '\n'
                else:
                    if current_part:
                        parts.append(current_part)
                    current_part = line + '\n'
            
            if current_part:
                parts.append(current_part)
            
            for i, part in enumerate(parts):
                if i == 0:
                    await message.answer(part, parse_mode="Markdown")
                else:
                    await message.answer(part, parse_mode="Markdown")
                await asyncio.sleep(0.1)
        else:
            await message.answer(history_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error showing history: {e}")
        await message.answer("📜 История розыгрышей временно недоступна")

@dp.message(F.text == "ℹ️ Информация")
async def show_info(message: types.Message):
    """Показ информации о боте"""
    await message.answer(
        "ℹ️ **О боте**\n\n"
        "Этот бот создан для проведения честных розыгрышей призов.\n\n"
        "**Как это работает:**\n"
        "1️⃣ Включите уведомления, чтобы не пропустить розыгрыши\n"
        "2️⃣ Подпишитесь на необходимые каналы\n"
        "3️⃣ Нажмите кнопку 'Участвовать'\n"
        "4️⃣ Дождитесь автоматических результатов\n\n"
        "**Гарантии:**\n"
        "• Все победители выбираются случайным образом\n"
        "• Результаты публикуются автоматически в указанное время\n"
        "• Полная прозрачность процесса\n"
        "• История всех розыгрышей доступна каждому\n\n"
        "Удачи в розыгрышах! 🍀",
        parse_mode="Markdown"
    )

# Обработчики для администраторов
@dp.message(RaffleStates.waiting_photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Обработка фото розыгрыша"""
    if message.photo:
        photo_file_id = message.photo[-1].file_id
        
        # Загружаем фото на сервер через API
        try:
            admin_data = {
                "id": str(ADMIN_IDS[0]),
                "first_name": "Admin",
                "username": "admin",
            }
            
            auth_date = int(time.time())
            user_json = json.dumps(admin_data, separators=(",", ":"), ensure_ascii=False)
            encoded_user = urllib.parse.quote(user_json)
            
            params = {
                "auth_date": str(auth_date),
                "user": user_json
            }
            
            data_check_arr = []
            for key in sorted(params.keys()):
                data_check_arr.append(f"{key}={params[key]}")
            data_check_string = "\n".join(data_check_arr)
            
            secret_key = hmac.new(
                b"WebAppData",
                BOT_TOKEN.encode(),
                hashlib.sha256
            ).digest()
            
            hash_value = hmac.new(
                secret_key,
                data_check_string.encode(),
                hashlib.sha256
            ).hexdigest()
            
            init_data = f"user={encoded_user}&auth_date={auth_date}&hash={hash_value}"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {init_data}",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{API_URL}/api/admin/upload-telegram-photo",
                    json={"file_id": photo_file_id},
                    headers=headers,
                    ssl=False
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        photo_url = f"{API_URL}{data['url']}"
                        await state.update_data(photo_file_id=photo_file_id, photo_url=photo_url)
                    else:
                        await state.update_data(photo_file_id=photo_file_id, photo_url='')
        except Exception as e:
            logger.error(f"Error uploading photo: {e}")
            await state.update_data(photo_file_id=photo_file_id, photo_url='')
            
    elif message.text and message.text.lower() == 'пропустить':
        await state.update_data(photo_file_id=None, photo_url='')
    else:
        await message.answer("Пожалуйста, отправьте фото или напишите 'пропустить'")
        return
    
    await state.set_state(RaffleStates.waiting_channels)
    await message.answer(
        "Шаг 4/6: Введите каналы для обязательной подписки\n"
        "Формат: @channel1 @channel2 @channel3\n"
        "(или напишите 'пропустить' если подписка не требуется)"
    )

@dp.message(RaffleStates.waiting_title)
async def process_title(message: types.Message, state: FSMContext):
    """Обработка названия розыгрыша"""
    await state.update_data(title=message.text)
    await state.set_state(RaffleStates.waiting_description)
    await message.answer("Шаг 2/6: Введите описание розыгрыша (что разыгрывается, условия и т.д.):")

@dp.message(RaffleStates.waiting_description)
async def process_description(message: types.Message, state: FSMContext):
    """Обработка описания розыгрыша"""
    await state.update_data(description=message.text)
    await state.set_state(RaffleStates.waiting_photo)
    await message.answer("Шаг 3/6: Отправьте фото для розыгрыша (или напишите 'пропустить'):")

# В файле bot/raffle_bot.py нужно обновить функцию process_photo:



@dp.message(RaffleStates.waiting_channels)
async def process_channels(message: types.Message, state: FSMContext):
    """Обработка списка каналов"""
    if message.text.lower() == 'пропустить':
        await state.update_data(channels='')
    else:
        channels = message.text.strip()
        await state.update_data(channels=channels)
    
    await state.set_state(RaffleStates.waiting_prizes)
    await message.answer("Шаг 5/6: Введите количество призовых мест:")

@dp.message(RaffleStates.waiting_prizes)
async def process_prizes_count(message: types.Message, state: FSMContext):
    """Обработка количества призов"""
    try:
        prizes_count = int(message.text)
        if prizes_count < 1:
            raise ValueError
        
        await state.update_data(prizes_count=prizes_count, prizes={}, current_prize=1)
        await state.set_state(RaffleStates.waiting_prize_details)
        await message.answer(f"Введите приз для 1 места:")
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число призовых мест (минимум 1)")

@dp.message(RaffleStates.waiting_prize_details)
async def process_prize_details(message: types.Message, state: FSMContext):
    """Обработка деталей призов"""
    data = await state.get_data()
    current_prize = data['current_prize']
    prizes = data['prizes']
    prizes_count = data['prizes_count']
    
    # Сохраняем текущий приз
    prizes[str(current_prize)] = message.text
    
    if current_prize < prizes_count:
        # Еще есть призы для ввода
        await state.update_data(prizes=prizes, current_prize=current_prize + 1)
        await message.answer(f"Введите приз для {current_prize + 1} места:")
    else:
        # Все призы введены
        await state.update_data(prizes=prizes)
        await state.set_state(RaffleStates.waiting_end_datetime)
        await message.answer(
            "Шаг 6/6: Введите дату и время окончания розыгрыша\n\n"
            "Формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 25.12.2024 18:00"
        )

@dp.message(RaffleStates.waiting_end_datetime)
async def process_end_datetime(message: types.Message, state: FSMContext):
    """Обработка даты и времени завершения"""
    try:
        # Парсим дату и время (считаем что пользователь вводит московское время)
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        
        # Проверяем, что дата в будущем
        moscow_now = datetime.now()
        if end_date <= moscow_now:
            await message.answer("❌ Дата должна быть в будущем! Попробуйте еще раз:")
            return
        await state.update_data(end_date=end_date)
        await state.set_state(RaffleStates.waiting_speed)
        kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text="Быстро"), KeyboardButton(text="Средняя"), KeyboardButton(text="Медленно")]],
            resize_keyboard=True
        )
        await message.answer(
            "Шаг 7/7: Выберите скорость вращения колеса:",
            reply_markup=kb
        )
        
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n\n"
            "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 25.12.2024 18:00"
        )

@dp.message(RaffleStates.waiting_speed)
async def process_speed(message: types.Message, state: FSMContext):
    speed_map = {"Быстро": "fast", "Средняя": "medium", "Медленно": "slow"}
    speed = speed_map.get(message.text)
    if not speed:
        await message.answer("Пожалуйста, выберите скорость из предложенных кнопок.")
        return
    data = await state.get_data()
    data["wheel_speed"] = speed
    loading_msg = await message.answer("⏳ Создаю розыгрыш...")
    try:
        raffle = await api_client.create_raffle(data)
        db.create_raffle_cache(
            api_id=raffle['id'],
            title=data['title'],
            description=data['description'],
            photo_file_id=data.get('photo_file_id'),
            photo_url=data.get('photo_url', ''),
            channels=data.get('channels', ''),
            prizes=data['prizes'],
            end_date=data['end_date'],
            wheel_speed=speed
        )
        await loading_msg.delete()
        await state.clear()
        keyboard = create_admin_keyboard()
        await message.answer(
            "✅ Розыгрыш успешно создан!\n\n"
            f"📋 Название: {data['title']}\n"
            f"📅 Завершится: {data['end_date'].strftime('%d.%m.%Y в %H:%M')} (МСК)\n"
            f"🏆 Призовых мест: {data['prizes_count']}\n\n"
            "⏰ Результаты будут подведены автоматически!\n\n"
            "Сейчас начнется рассылка уведомлений...",
            reply_markup=keyboard
        )
    except Exception as e:
        await loading_msg.delete()
        logger.error(f"Error creating raffle: {e}")
        await message.answer(
            f"❌ Ошибка при создании розыгрыша: {str(e)}\n\n"
            "Попробуйте еще раз или обратитесь к разработчику.",
            reply_markup=create_admin_keyboard()
        )
        await state.clear()

async def send_raffle_notification(raffle_id: int, raffle_data: dict):
    """Отправка уведомлений о новом розыгрыше"""
    users = db.get_users_with_notifications()
    
    # Кнопка с Web App для участия
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎯 Участвовать",
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{raffle_id}")
        )]
    ])
    
    # Форматируем призы
    prizes_text = "\n".join([f"{pos}. {prize}" for pos, prize in raffle_data['prizes'].items()])
    
    caption = (
        f"🎉 **Новый розыгрыш!**\n\n"
        f"**{raffle_data['title']}**\n\n"
        f"{raffle_data['description']}\n\n"
        f"🏆 **Призы:**\n{prizes_text}\n\n"
        f"⏰ До {raffle_data['end_date'].strftime('%d.%m.%Y в %H:%M')}"
    )
    
    success_count = 0
    for user_id in users:
        try:
            if raffle_data.get('photo_file_id'):
                await bot.send_photo(
                    chat_id=user_id,
                    photo=raffle_data['photo_file_id'],
                    caption=caption,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=caption,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            success_count += 1
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")
    
    # Уведомляем админов о результатах рассылки
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"✅ Рассылка завершена!\n"
                f"Отправлено: {success_count} из {len(users)} уведомлений"
            )
        except:
            pass

async def notify_raffle_live(raffle_id: int):
    """Уведомление о начале live розыгрыша"""
    # Получаем данные о розыгрыше
    raffle = db.get_active_raffle()
    if not raffle:
        return
    
    # Получаем всех заинтересованных пользователей
    notif_users = db.get_users_with_notifications()
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎰 Смотреть розыгрыш",
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{raffle_id}/live")
        )]
    ])
    
    text = (
        f"🎰 **Розыгрыш начался!**\n\n"
        f"**{raffle['title']}**\n\n"
        f"Нажмите кнопку ниже, чтобы посмотреть live-розыгрыш!"
    )
    
    for user_id in notif_users:
        try:
            if raffle.get('photo_file_id'):
                await bot.send_photo(
                    chat_id=user_id,
                    photo=raffle['photo_file_id'],
                    caption=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown"
                )
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())