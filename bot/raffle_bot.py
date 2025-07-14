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
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://raffle-app-qtma.onrender.com")
API_URL    = os.getenv("API_URL",   "https://raffle-api.onrender.com")
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
                "channels": raffle_data["channels"].split() if raffle_data.get("channels") else [],
                "prizes": raffle_data.get("prizes", {}),
                "end_date": raffle_data["end_date"].isoformat(),
                "draw_delay_minutes": 5,
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
                INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
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
                          photo_url: str, channels: str, prizes: dict, end_date: datetime) -> int:
        """Создание локальной копии розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO raffles (api_id, title, description, photo_file_id, photo_url, channels, prizes, end_date, winners_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (api_id, title, description, photo_file_id, photo_url, channels, 
                  json.dumps(prizes), end_date, len(prizes)))
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
                for winner in raffle['winners'][:3]:
                    history_text += f"🏆 {winner['position']} место: @{winner['user']['username'] or winner['user']['first_name']}\n"
                if len(raffle['winners']) > 3:
                    history_text += f"... и еще {len(raffle['winners']) - 3} победителей\n"
            
            history_text += "─" * 30 + "\n\n"
        
        if len(history_text) > 4000:
            history_text = history_text[:4000] + "\n\n... (показаны последние розыгрыши)"
        
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
@dp.message(F.text == "➕ Создать розыгрыш", F.from_user.id.in_(ADMIN_IDS))
async def create_raffle_start(message: types.Message, state: FSMContext):
    """Начало создания розыгрыша"""
    await state.set_state(RaffleStates.waiting_title)
    await message.answer(
        "🎯 Создание нового розыгрыша\n\n"
        "Шаг 1/6: Введите название розыгрыша:",
        reply_markup=types.ReplyKeyboardRemove()
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

@dp.message(RaffleStates.waiting_photo)
async def process_photo(message: types.Message, state: FSMContext):
    """Обработка фото розыгрыша"""
    if message.photo:
        photo_file_id = message.photo[-1].file_id
        await state.update_data(photo_file_id=photo_file_id, photo_url=photo_file_id)
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
        # Парсим дату и время
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y %H:%M")
        
        # Проверяем, что дата в будущем
        if end_date <= datetime.now():
            await message.answer("❌ Дата должна быть в будущем! Попробуйте еще раз:")
            return
        
        # Получаем все данные
        data = await state.get_data()
        data['end_date'] = end_date
        
        # Создаем розыгрыш через API
        loading_msg = await message.answer("⏳ Создаю розыгрыш...")
        
        try:
            # Пробуем создать через API
            raffle = await api_client.create_raffle(data)
            
            # Сохраняем в локальный кеш
            db.create_raffle_cache(
                api_id=raffle['id'],
                title=data['title'],
                description=data['description'],
                photo_file_id=data.get('photo_file_id'),
                photo_url=data.get('photo_url', ''),
                channels=data.get('channels', ''),
                prizes=data['prizes'],
                end_date=end_date
            )
            
            await loading_msg.delete()
            await state.clear()
            
            keyboard = create_admin_keyboard()
            await message.answer(
                "✅ Розыгрыш успешно создан!\n\n"
                f"📋 Название: {data['title']}\n"
                f"📅 Завершится: {end_date.strftime('%d.%m.%Y в %H:%M')}\n"
                f"🏆 Призовых мест: {data['prizes_count']}\n\n"
                "⏰ Результаты будут подведены автоматически!\n\n"
                "Сейчас начнется рассылка уведомлений...",
                reply_markup=keyboard
            )
            
            # Отправляем уведомления
            await send_raffle_notification(raffle['id'], data)
            
        except Exception as e:
            await loading_msg.delete()
            logger.error(f"Error creating raffle: {e}")
            await message.answer(
                f"❌ Ошибка при создании розыгрыша: {str(e)}\n\n"
                "Попробуйте еще раз или обратитесь к разработчику.",
                reply_markup=create_admin_keyboard()
            )
            await state.clear()
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n\n"
            "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 25.12.2024 18:00"
        )

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