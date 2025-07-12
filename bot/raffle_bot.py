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
    waiting_post_channel = State()     
    waiting_end_datetime = State()
    waiting_winners_count = State()

class DatabaseManager:
    """Класс для работы с базой данных"""
    
    def __init__(self, db_path: str = "/app/data/raffle_bot.db"):
        self.db_path = db_path
        # Создаем директорию если её нет
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
            
            # Таблица розыгрышей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS raffles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT,
                    photo_file_id TEXT,
                    channels TEXT,  -- JSON список каналов
                    start_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    end_date TIMESTAMP,
                    winners_count INTEGER DEFAULT 1,
                    post_channel TEXT DEFAULT '',
                    is_active INTEGER DEFAULT 1,
                    is_completed INTEGER DEFAULT 0,
                    result_message TEXT  -- Сообщение с результатами
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
    
    def create_raffle(self, title: str, description: str, photo_file_id: str, 
                     channels: str, end_date: datetime, winners_count: int) -> int:
        """Создание нового розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO raffles (title, description, photo_file_id, channels, end_date, winners_count)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (title, description, photo_file_id, channels, end_date, winners_count))
            conn.commit()
            return cursor.lastrowid
    
    def get_active_raffle(self) -> Dict[str, Any]:
        """Получение активного розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM raffles WHERE is_active = 1 AND is_completed = 0 ORDER BY id DESC LIMIT 1')
            row = cursor.fetchone()
            return dict(row) if row else None
    
    def get_expired_raffles(self) -> List[Dict[str, Any]]:
        """Получение розыгрышей, которые пора завершить"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM raffles 
                WHERE is_active = 1 
                AND is_completed = 0 
                AND datetime(end_date) <= datetime('now', 'localtime')
            ''')
            return [dict(row) for row in cursor.fetchall()]
    
    def add_participant(self, raffle_id: int, user_id: int) -> bool:
        """Добавление участника в розыгрыш"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO participants (raffle_id, user_id) VALUES (?, ?)', (raffle_id, user_id))
                conn.commit()
                return True
        except sqlite3.IntegrityError:
            return False  # Пользователь уже участвует
    
    def get_participants(self, raffle_id: int) -> List[Dict[str, Any]]:
        """Получение списка участников розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, u.last_name
                FROM participants p
                JOIN users u ON p.user_id = u.user_id
                WHERE p.raffle_id = ?
            ''', (raffle_id,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_participant_ids(self, raffle_id: int) -> List[int]:
        """Получение списка ID участников розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT user_id FROM participants WHERE raffle_id = ?', (raffle_id,))
            return [row[0] for row in cursor.fetchall()]
    
    def complete_raffle(self, raffle_id: int, winner_ids: List[int], result_message: str):
        """Завершение розыгрыша и сохранение победителей"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Отмечаем розыгрыш как завершенный
            cursor.execute(
                'UPDATE raffles SET is_completed = 1, is_active = 0, result_message = ? WHERE id = ?', 
                (result_message, raffle_id)
            )
            
            # Сохраняем победителей
            for winner_id in winner_ids:
                cursor.execute('INSERT INTO winners (raffle_id, user_id) VALUES (?, ?)', (raffle_id, winner_id))
            
            conn.commit()
    
    def get_raffle_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение истории завершенных розыгрышей"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT r.*, 
                       (SELECT COUNT(*) FROM participants WHERE raffle_id = r.id) as participants_count
                FROM raffles r
                WHERE r.is_completed = 1
                ORDER BY r.end_date DESC
                LIMIT ?
            ''', (limit,))
            return [dict(row) for row in cursor.fetchall()]
    
    def get_raffle_winners(self, raffle_id: int) -> List[Dict[str, Any]]:
        """Получение победителей конкретного розыгрыша"""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT u.user_id, u.username, u.first_name, u.last_name
                FROM winners w
                JOIN users u ON w.user_id = u.user_id
                WHERE w.raffle_id = ?
            ''', (raffle_id,))
            return [dict(row) for row in cursor.fetchall()]

# Создание экземпляра менеджера БД
db = DatabaseManager()

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
            [KeyboardButton(text="🏆 Завершить розыгрыш")],
            [KeyboardButton(text="📊 Статистика")],
            [KeyboardButton(text="📥 Экспорт участников")],
            [KeyboardButton(text="🏅 Экспорт победителей")],
            [KeyboardButton(text="📜 История розыгрышей")],
            [KeyboardButton(text="ℹ️ Информация")]
        ],
        resize_keyboard=True
    )
    return keyboard

async def check_channel_subscription(user_id: int, channel_username: str) -> bool:
    """Проверка подписки пользователя на канал"""
    try:
        # Убираем @ если он есть
        channel_username = channel_username.replace('@', '')
        member = await bot.get_chat_member(f"@{channel_username}", user_id)
        return member.status in ['creator', 'administrator', 'member']
    except Exception as e:
        logger.error(f"Ошибка проверки подписки: {e}")
        return False

def export_to_excel(data: List[Dict], filename: str, title: str):
    """Экспорт данных в Excel файл"""
    if not EXCEL_AVAILABLE:
        # Если openpyxl не установлен, экспортируем в CSV
        csv_filename = filename.replace('.xlsx', '.csv')
        with open(csv_filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
            if data:
                fieldnames = data[0].keys()
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)
        return csv_filename
    
    # Создаем Excel файл
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = title
    
    # Стили
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="366092", end_color="366092", fill_type="solid")
    header_alignment = Alignment(horizontal="center", vertical="center")
    
    # Заголовки
    if data:
        headers = list(data[0].keys())
        for col, header in enumerate(headers, 1):
            cell = ws.cell(row=1, column=col, value=header)
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = header_alignment
        
        # Данные
        for row_idx, row_data in enumerate(data, 2):
            for col_idx, (key, value) in enumerate(row_data.items(), 1):
                ws.cell(row=row_idx, column=col_idx, value=value)
        
        # Автоширина колонок
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
    
    wb.save(filename)
    return filename

# Вспомогательная функция для отправки уведомлений
async def send_notification_with_photo(user_id, text, photo_file_id, keyboard):
    """Вспомогательная функция для отправки уведомлений"""
    if photo_file_id:
        await bot.send_photo(
            chat_id=user_id,
            photo=photo_file_id,
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
    raffle = db.get_active_raffle()
    
    if not raffle:
        await message.answer("😔 Сейчас нет активных розыгрышей. Следите за обновлениями!")
        return
    
    # Форматируем дату окончания
    end_date = datetime.fromisoformat(raffle['end_date'])
    end_date_str = end_date.strftime("%d.%m.%Y в %H:%M")
    
    # Создаем кнопку для участия с Web App
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎯 Участвовать", 
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{raffle['id']}")
        )]
    ])
    
    # Считаем участников
    participants_count = len(db.get_participants(raffle['id']))
    
    caption = (
        f"🎉 **{raffle['title']}**\n\n"
        f"{raffle['description']}\n\n"
        f"⏰ Завершится: {end_date_str}\n"
        f"👥 Участников: {participants_count}\n"
        f"🏆 Победителей будет: {raffle['winners_count']}"
    )
    
    if raffle['photo_file_id']:
        await message.answer_photo(
            photo=raffle['photo_file_id'],
            caption=caption,
            reply_markup=keyboard,
            parse_mode="Markdown"
        )
    else:
        await message.answer(caption, reply_markup=keyboard, parse_mode="Markdown")

@dp.message(F.text == "📜 История розыгрышей")
async def show_history(message: types.Message):
    """Показ истории розыгрышей для всех пользователей"""
    history = db.get_raffle_history(limit=10)
    
    if not history:
        await message.answer("📜 История розыгрышей пуста")
        return
    
    history_text = "📜 **История последних розыгрышей:**\n\n"
    
    for raffle in history:
        # Получаем победителей
        winners = db.get_raffle_winners(raffle['id'])
        
        # Форматируем дату
        end_date = datetime.fromisoformat(raffle['end_date'])
        date_str = end_date.strftime("%d.%m.%Y")
        
        history_text += f"🎯 **{raffle['title']}**\n"
        history_text += f"📅 Завершен: {date_str}\n"
        history_text += f"👥 Участников: {raffle['participants_count']}\n"
        
        if raffle['result_message']:
            # Используем сохраненное сообщение с результатами
            lines = raffle['result_message'].split('\n')
            # Ищем строки с победителями
            in_winners_section = False
            for line in lines:
                if "Победители:" in line or "победители:" in line:
                    in_winners_section = True
                    continue
                if in_winners_section and line.strip() and not line.startswith("Поздравляем"):
                    history_text += f"🏆 {line.strip()}\n"
                elif in_winners_section and (line.startswith("Поздравляем") or not line.strip()):
                    break
        
        history_text += "─" * 30 + "\n\n"
    
    # Telegram имеет лимит в 4096 символов
    if len(history_text) > 4000:
        history_text = history_text[:4000] + "\n\n... (показаны последние розыгрыши)"
    
    await message.answer(history_text, parse_mode="Markdown")

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
        await state.update_data(photo_file_id=message.photo[-1].file_id)
    elif message.text and message.text.lower() == 'пропустить':
        await state.update_data(photo_file_id=None)
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
    
    await state.set_state(RaffleStates.waiting_post_channel)
    await message.answer(
        "Шаг 5/7: Укажите @канал, куда опубликовать розыгрыш\n"
        "(или напишите 'пропустить')"
    )

@dp.message(RaffleStates.waiting_post_channel)
async def process_post_channel(message: types.Message, state: FSMContext):
    text = message.text.strip()
    if text.lower() == 'пропустить':
        await state.update_data(post_channel='')
    else:
        if not text.startswith('@'):
            await message.answer("Канал должен начинаться с @. Попробуйте ещё раз:")
            return
        await state.update_data(post_channel=text)
    await state.set_state(RaffleStates.waiting_end_datetime)
    await message.answer(
        "Шаг 6/7: Введите дату и время окончания розыгрыша\n"
        "Формат: ДД.ММ.ГГГГ ЧЧ:ММ"
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
        
        await state.update_data(end_date=end_date)
        await state.set_state(RaffleStates.waiting_winners_count)
        await message.answer("Шаг 7/7: Введите количество победителей:")
        
    except ValueError:
        await message.answer(
            "❌ Неверный формат даты!\n\n"
            "Используйте формат: ДД.ММ.ГГГГ ЧЧ:ММ\n"
            "Например: 25.12.2024 18:00"
        )

@dp.message(RaffleStates.waiting_winners_count)
async def process_winners_count(message: types.Message, state: FSMContext):
    """Обработка количества победителей и создание розыгрыша"""
    try:
        winners_count = int(message.text)
        if winners_count < 1:
            raise ValueError
        
        # Получаем все данные
        data = await state.get_data()
        
        # Создаем розыгрыш в БД
        raffle_id = db.create_raffle(
            title=data['title'],
            description=data['description'],
            photo_file_id=data['photo_file_id'],
            channels=data['channels'],
            end_date=data['end_date'],
            winners_count=winners_count
        )
        
        await state.clear()
        
        keyboard = create_admin_keyboard()
        await message.answer(
            "✅ Розыгрыш успешно создан!\n\n"
            f"📋 Название: {data['title']}\n"
            f"📅 Завершится: {data['end_date'].strftime('%d.%m.%Y в %H:%M')}\n"
            f"🏆 Победителей: {winners_count}\n\n"
            "⏰ Результаты будут подведены автоматически!\n\n"
            "Сейчас начнется рассылка уведомлений...",
            reply_markup=keyboard
        )
        
        # Отправляем уведомления
        await send_raffle_notification(raffle_id)
        
    except ValueError:
        await message.answer("Пожалуйста, введите корректное число победителей (минимум 1)")

async def send_raffle_notification(raffle_id: int):
    """Отправка уведомлений о новом розыгрыше"""
    raffle = db.get_active_raffle()
    if not raffle:
        return
    
    users = db.get_users_with_notifications()
    
    # Кнопка с Web App для участия
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🎯 Участвовать",
            web_app=types.WebAppInfo(url=f"{WEBAPP_URL}/raffle/{raffle_id}")
        )]
    ])
    
    # Форматируем дату окончания
    end_date = datetime.fromisoformat(raffle['end_date'])
    end_date_str = end_date.strftime("%d.%m.%Y в %H:%M")
    
    caption = (
        f"🎉 **Новый розыгрыш!**\n\n"
        f"**{raffle['title']}**\n\n"
        f"{raffle['description']}\n\n"
        f"⏰ Итоги будут подведены: {end_date_str}\n"
        f"🏆 Количество победителей: {raffle['winners_count']}"
    )
    
    success_count = 0
    for user_id in users:
        try:
            await send_notification_with_photo(user_id, caption, raffle.get('photo_file_id'), keyboard)
            success_count += 1
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
    raffle = db.get_active_raffle()
    if not raffle:
        return
    
    participants = db.get_participant_ids(raffle_id)
    notif_users = db.get_users_with_notifications()
    all_users = list(set(participants + notif_users))
    
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
    
    for user_id in all_users:
        try:
            await send_notification_with_photo(user_id, text, raffle.get('photo_file_id'), keyboard)
        except Exception as e:
            logger.error(f"Ошибка отправки уведомления пользователю {user_id}: {e}")

@dp.callback_query(F.data.startswith("join_"))
async def process_join_raffle(callback: types.CallbackQuery):
    """Обработка участия в розыгрыше (для обратной совместимости)"""
    raffle_id = int(callback.data.split("_")[1])
    
    # Открываем Web App для участия
    await callback.answer(
        "Нажмите кнопку 'Участвовать' в сообщении выше, чтобы открыть приложение",
        show_alert=True
    )

@dp.message(F.text == "🏆 Завершить розыгрыш", F.from_user.id.in_(ADMIN_IDS))
async def complete_raffle_manual(message: types.Message):
    """Ручное завершение активного розыгрыша"""
    raffle = db.get_active_raffle()
    
    if not raffle:
        await message.answer("Нет активных розыгрышей для завершения!")
        return
    
    await complete_raffle(raffle)
    await message.answer("✅ Розыгрыш успешно завершен!")

async def complete_raffle(raffle: Dict[str, Any]):
    """Завершение розыгрыша и отправка результатов"""
    participants = db.get_participants(raffle['id'])
    
    if len(participants) < raffle['winners_count']:
        # Недостаточно участников — шлём админам и отключаем розыгрыш навсегда
        for admin_id in ADMIN_IDS:
            try:
                await bot.send_message(
                    admin_id,
                    f"⚠️ Розыгрыш '{raffle['title']}' не может быть завершен!\n"
                    f"Участников: {len(participants)}\n"
                    f"Требуется победителей: {raffle['winners_count']}"
                )
            except:
                pass
        # Отключаем этот розыгрыш, чтобы не автозавершать его снова
        with sqlite3.connect(db.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("UPDATE raffles SET is_active = 0 WHERE id = ?", (raffle['id'],))
            conn.commit()
        return
    
    # Уведомляем о начале розыгрыша
    await notify_raffle_live(raffle['id'])
    
    # Выбираем победителей
    winners = random.sample(participants, raffle['winners_count'])
    winner_ids = [w['user_id'] for w in winners]
    
    # Формируем список победителей
    winners_text = "\n".join([
        f"{i+1}. {w['first_name']} {w['last_name'] or ''} (@{w['username'] or 'без username'})"
        for i, w in enumerate(winners)
    ])
    
    # Формируем сообщение с результатами
    result_text = (
        f"🏆 **Розыгрыш завершен!**\n\n"
        f"**{raffle['title']}**\n\n"
        f"🎉 **Победители:**\n{winners_text}\n\n"
        f"Поздравляем победителей! 🎊"
    )
    
    # Сохраняем результаты в БД
    db.complete_raffle(raffle['id'], winner_ids, result_text)
    
    # Получаем всех участников розыгрыша
    participant_ids = db.get_participant_ids(raffle['id'])
    
    # Отправляем результаты всем участникам
    for user_id in participant_ids:
        try:
            if raffle['photo_file_id']:
                await bot.send_photo(
                    chat_id=user_id,
                    photo=raffle['photo_file_id'],
                    caption=result_text,
                    parse_mode="Markdown"
                )
            else:
                await bot.send_message(
                    chat_id=user_id,
                    text=result_text,
                    parse_mode="Markdown"
                )
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.error(f"Ошибка отправки результатов пользователю {user_id}: {e}")
    
    # Уведомляем админов
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(
                admin_id,
                f"✅ Розыгрыш '{raffle['title']}' завершен!\n"
                f"Участников: {len(participants)}\n"
                f"Победителей: {len(winners)}\n"
                f"Уведомления отправлены всем участникам!"
            )
        except:
            pass

@dp.message(F.text == "📊 Статистика", F.from_user.id.in_(ADMIN_IDS))
async def show_statistics(message: types.Message):
    """Показ статистики для администраторов"""
    with sqlite3.connect(db.db_path) as conn:
        cursor = conn.cursor()
        
        # Общее количество пользователей
        cursor.execute("SELECT COUNT(*) FROM users")
        total_users = cursor.fetchone()[0]
        
        # Пользователи с уведомлениями
        cursor.execute("SELECT COUNT(*) FROM users WHERE notifications_enabled = 1")
        notif_users = cursor.fetchone()[0]
        
        # Количество розыгрышей
        cursor.execute("SELECT COUNT(*) FROM raffles")
        total_raffles = cursor.fetchone()[0]
        
        # Активные розыгрыши
        cursor.execute("SELECT COUNT(*) FROM raffles WHERE is_active = 1")
        active_raffles = cursor.fetchone()[0]
        
        # Текущие участники
        raffle = db.get_active_raffle()
        current_participants = len(db.get_participants(raffle['id'])) if raffle else 0
    
    await message.answer(
        f"📊 **Статистика бота**\n\n"
        f"👥 Всего пользователей: {total_users}\n"
        f"🔔 С уведомлениями: {notif_users}\n"
        f"🎯 Всего розыгрышей: {total_raffles}\n"
        f"✅ Активных: {active_raffles}\n"
        f"👤 Участников в текущем: {current_participants}",
        parse_mode="Markdown"
    )

@dp.message(F.text == "📥 Экспорт участников", F.from_user.id.in_(ADMIN_IDS))
async def export_participants(message: types.Message):
    """Экспорт списка участников текущего розыгрыша"""
    raffle = db.get_active_raffle()
    
    if not raffle:
        await message.answer("Нет активных розыгрышей!")
        return
    
    participants = db.get_participants(raffle['id'])
    
    if not participants:
        await message.answer("В розыгрыше пока нет участников!")
        return
    
    # Подготавливаем данные для экспорта
    export_data = []
    for p in participants:
        export_data.append({
            'ID': p['user_id'],
            'Username': p['username'] or 'Нет',
            'Имя': p['first_name'],
            'Фамилия': p['last_name'] or ''
        })
    
    # Экспортируем в файл
    filename = f"participants_{raffle['id']}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if EXCEL_AVAILABLE:
        filename += ".xlsx"
    else:
        filename += ".csv"
    
    exported_file = export_to_excel(export_data, filename, f"Участники - {raffle['title']}")
    
    # Отправляем файл
    with open(exported_file, 'rb') as f:
        await message.answer_document(
            document=types.input_file.FSInputFile(exported_file),
            caption=f"📊 Список участников розыгрыша:\n**{raffle['title']}**\n\nВсего: {len(participants)} чел."
        )
    
    # Удаляем временный файл
    os.remove(exported_file)

@dp.message(F.text == "🏅 Экспорт победителей", F.from_user.id.in_(ADMIN_IDS))
async def export_winners(message: types.Message):
    """Экспорт списка всех победителей"""
    with sqlite3.connect(db.db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('''
            SELECT 
                r.title as raffle_title,
                r.end_date,
                u.user_id,
                u.username,
                u.first_name,
                u.last_name,
                w.won_at
            FROM winners w
            JOIN users u ON w.user_id = u.user_id
            JOIN raffles r ON w.raffle_id = r.id
            ORDER BY w.won_at DESC
        ''')
        winners_data = cursor.fetchall()
    
    if not winners_data:
        await message.answer("Пока нет победителей в завершенных розыгрышах!")
        return
    
    # Подготавливаем данные для экспорта
    export_data = []
    for w in winners_data:
        export_data.append({
            'Розыгрыш': w['raffle_title'],
            'Дата розыгрыша': w['end_date'][:10],
            'ID победителя': w['user_id'],
            'Username': w['username'] or 'Нет',
            'Имя': w['first_name'],
            'Фамилия': w['last_name'] or '',
            'Дата победы': w['won_at'][:10]
        })
    
    # Экспортируем в файл
    filename = f"winners_all_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    if EXCEL_AVAILABLE:
        filename += ".xlsx"
    else:
        filename += ".csv"
    
    exported_file = export_to_excel(export_data, filename, "Все победители")
    
    # Отправляем файл
    with open(exported_file, 'rb') as f:
        await message.answer_document(
            document=types.input_file.FSInputFile(exported_file),
            caption=f"🏅 Список всех победителей\n\nВсего победителей: {len(export_data)}"
        )
    
    # Удаляем временный файл
    os.remove(exported_file)

# Автоматическая проверка и завершение розыгрышей
async def check_and_complete_raffles():
    """Проверка и автоматическое завершение розыгрышей по времени"""
    while True:
        try:
            # Получаем розыгрыши, которые пора завершить
            expired_raffles = db.get_expired_raffles()
            
            for raffle in expired_raffles:
                logger.info(f"Автозавершение розыгрыша: {raffle['title']}")
                await complete_raffle(raffle)
                await asyncio.sleep(1)  # Небольшая пауза между розыгрышами
        
        except Exception as e:
            logger.error(f"Ошибка в автозавершении розыгрышей: {e}")
        
        # Проверяем каждую минуту
        await asyncio.sleep(60)

async def main():
    """Основная функция запуска бота"""
    logger.info("Запуск бота...")
    
    # Запускаем фоновую задачу для автозавершения розыгрышей
    asyncio.create_task(check_and_complete_raffles())
    
    # Запускаем polling
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())