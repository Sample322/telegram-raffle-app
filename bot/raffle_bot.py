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

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.exceptions import TelegramBadRequest

# Загружаем переменные окружения
load_dotenv()

# Для работы с Excel
try:
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    EXCEL_AVAILABLE = True
except ImportError:
    EXCEL_AVAILABLE = False
    logging.warning("openpyxl не установлен. Экспорт будет в CSV формате.")

# Настройки бота
BOT_TOKEN = os.getenv("BOT_TOKEN", "8056583131:AAH9qRCnWHcFKBkpmjTRk_zVGlHjCOx58Fs")
WEBAPP_URL = os.getenv("WEBAPP_URL", "https://raffle-app.onrender.com")
API_URL = os.getenv("API_URL", "https://raffle-api.onrender.com")
ADMIN_IDS = [int(id) for id in os.getenv("ADMIN_IDS", "888007035").split(",")]

# Инициализация логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# Состояния для FSM
class RaffleStates(StatesGroup):
    waiting_title = State()
    waiting_description = State()
    waiting_photo = State()
    waiting_channels = State()
    waiting_prizes = State()
    waiting_end_datetime = State()
    waiting_prize_details = State()

class APIClient:
    """Клиент для работы с API"""
    
    def __init__(self, api_url: str):
        self.api_url = api_url
        self.session = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def create_raffle(self, raffle_data: dict) -> dict:
        """Создание розыгрыша через API"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_url}/api/admin/raffles"
            
            # Подготовка данных
            api_data = {
                "title": raffle_data['title'],
                "description": raffle_data['description'],
                "photo_url": raffle_data.get('photo_url', ''),
                "channels": raffle_data['channels'].split() if raffle_data['channels'] else [],
                "prizes": raffle_data['prizes'],
                "end_date": raffle_data['end_date'].isoformat(),
                "draw_delay_minutes": 5
            }
            
            try:
                async with session.post(url, json=api_data) as response:
                    if response.status == 200:
                        return await response.json()
                    else:
                        error_text = await response.text()
                        raise Exception(f"API error {response.status}: {error_text}")
            except aiohttp.ClientError as e:
                logger.error(f"Network error: {e}")
                raise Exception(f"Ошибка сети: {e}")
    
    async def get_active_raffles(self) -> List[dict]:
        """Получение активных розыгрышей"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_url}/api/raffles/active"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
            except:
                return []
    
    async def get_completed_raffles(self, limit: int = 10) -> List[dict]:
        """Получение завершенных розыгрышей"""
        async with aiohttp.ClientSession() as session:
            url = f"{self.api_url}/api/raffles/completed?limit={limit}"
            try:
                async with session.get(url) as response:
                    if response.status == 200:
                        return await response.json()
                    return []
            except:
                return []

class LocalDatabaseManager:
    """Локальная база для хранения пользователей и настроек"""
    
    def __init__(self, db_path: str = "/app/data/bot_users.db"):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_database()
    
    def init_database(self):
        """Инициализация базы данных для пользователей"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Таблица пользователей бота
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS bot_users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    notifications_enabled INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str):
        """Добавление нового пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO bot_users (user_id, username, first_name, last_name)
                VALUES (?, ?, ?, ?)
            ''', (user_id, username, first_name, last_name))
            conn.commit()
    
    def toggle_notifications(self, user_id: int) -> bool:
        """Переключение уведомлений для пользователя"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT notifications_enabled FROM bot_users WHERE user_id = ?', (user_id,))
            result = cursor.fetchone()
            
            new_status = 0 if result and result[0] else 1
            cursor.execute('UPDATE bot_users SET notifications_enabled = ? WHERE user_id = ?', (new_status, user_id))
            conn.commit()
            
            return bool(new_status)
    
    def get_users_with_notifications(self) -> List[int]:
        """Получение списка пользователей с включенными уведомлениями"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM bot_users WHERE notifications_enabled = 1')
            return [row[0] for row in cursor.fetchall()]

# Создание экземпляров
db = LocalDatabaseManager()
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
    """Загрузка фото на сервер через Telegram API"""
    try:
        # Получаем файл от Telegram
        file = await bot.get_file(photo_file_id)
        file_path = file.file_path
        
        # Скачиваем файл
        file_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
        
        async with aiohttp.ClientSession() as session:
            async with session.get(file_url) as resp:
                if resp.status == 200:
                    file_data = await resp.read()
                    
                    # Загружаем на наш сервер
                    form = aiohttp.FormData()
                    form.add_field('file',
                                 file_data,
                                 filename='raffle_image.jpg',
                                 content_type='image/jpeg')
                    
                    async with session.post(f"{API_URL}/api/admin/upload-image", data=form) as upload_resp:
                        if upload_resp.status == 200:
                            result = await upload_resp.json()
                            return f"{API_URL}{result['url']}"
        
        # Если не удалось загрузить, возвращаем file_id
        return photo_file_id
    except Exception as e:
        logger.error(f"Error uploading photo: {e}")
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
        raffles = await api_client.get_active_raffles()
        
        if not raffles:
            await message.answer("😔 Сейчас нет активных розыгрышей. Следите за обновлениями!")
            return
        
        # Показываем первый активный розыгрыш
        raffle = raffles[0]
        
        # Форматируем дату окончания
        end_date = datetime.fromisoformat(raffle['end_date'].replace('Z', '+00:00'))
        end_date_str = end_date.strftime("%d.%m.%Y в %H:%M")
        
        # Создаем кнопку для участия с Web App
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(
                text="🎯 Участвовать", 
                web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{raffle['id']}")
            )]
        ])
        
        # Форматируем призы
        prizes_text = "\n".join([f"{pos}. {prize}" for pos, prize in raffle.get('prizes', {}).items()])
        
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
            
    except Exception as e:
        logger.error(f"Error showing active raffles: {e}")
        await message.answer("Произошла ошибка при загрузке розыгрышей. Попробуйте позже.")

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
                for winner in raffle['winners'][:3]:  # Показываем первых 3
                    history_text += f"🏆 {winner['position']} место: @{winner['user']['username'] or winner['user']['first_name']}\n"
                if len(raffle['winners']) > 3:
                    history_text += f"... и еще {len(raffle['winners']) - 3} победителей\n"
            
            history_text += "─" * 30 + "\n\n"
        
        # Telegram имеет лимит в 4096 символов
        if len(history_text) > 4000:
            history_text = history_text[:4000] + "\n\n... (показаны последние розыгрыши)"
        
        await message.answer(history_text, parse_mode="Markdown")
        
    except Exception as e:
        logger.error(f"Error showing history: {e}")
        await message.answer("Произошла ошибка при загрузке истории. Попробуйте позже.")

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
        # Загружаем фото на сервер
        photo_url = await upload_photo_to_api(message.photo[-1].file_id)
        await state.update_data(photo_url=photo_url)
    elif message.text and message.text.lower() == 'пропустить':
        await state.update_data(photo_url='')
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
    await message.answer(
        "Шаг 5/6: Введите количество призовых мест:"
    )

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
            raffle = await api_client.create_raffle(data)
            
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
            if raffle_data.get('photo_url'):
                await bot.send_photo(
                    chat_id=user_id,
                    photo=raffle_data['photo_url'],
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

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())