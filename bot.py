from flask import Flask
import threading
import logging
import re
import sqlite3
import json
from datetime import datetime, timedelta
from collections import defaultdict, deque
import telebot
from telebot.types import ChatPermissions, InlineKeyboardMarkup, InlineKeyboardButton
import io

# Создаем Flask сервер для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот работает! Telegram: @ledcripsigma_bot"

def run_web():
    app.run(host='0.0.0.0', port=10000, debug=False)

# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_web, daemon=True).start()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8207041880:AAEM1F0YaWF3jEKJ-GfRPPOosOBbpTnSY4M"
ADMIN_ID = 8054980148
APPEAL_TEXT = "🆘Если вас замутило по ошибке: @rilyglrletukdetuluft (моментальный ответ 14:00 — 2:00)"

# Настройки анти-спама
MAX_CONSECUTIVE_IDENTICAL = 5
MAX_CONSECUTIVE_STICKERS = 5
SPAM_MUTE_DURATION = 3600
INSULT_MUTE_DURATION = 86400

# Запрещенные фразы для мута
BANNED_PHRASES = [
    # Оскорбления родни
    "мама шлюха", "мамку ебал", "у тебя мать шалава", "мать шалава", 
    "мать ебал", "мамку твою", "мамке кончил в рот",
    
    # Реклама аренды аккаунтов
    "ТАКЖЕ БЕРУ ВАШИ ТГ АККАУНТЫ В АРЕНДУ ДОРОГО🇷🇺",
    "•ПИСАТЬ сюда @rozatopld✅",
    "плачу за задание в лс",
    "@rozatopld ТАКЖЕ БЕРУ ВАШИ ТГ АККАУНТЫ В АРЕНДУ ДОРОГО🇷🇺",
    "плачу 7000, подробности в лс",
    "@rozatopld"
]

# Инициализация бота
bot = telebot.TeleBot(BOT_TOKEN)

# Списки для отслеживания активности
user_message_history = defaultdict(lambda: deque(maxlen=MAX_CONSECUTIVE_IDENTICAL))
user_sticker_history = defaultdict(lambda: deque(maxlen=MAX_CONSECUTIVE_STICKERS))

class Database:
    def __init__(self, db_path="anti_spam.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                join_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0,
                warning_count INTEGER DEFAULT 0
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS message_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                message_text TEXT,
                message_type TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS restrictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                restriction_type TEXT,
                reason TEXT,
                duration_hours INTEGER,
                start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                end_time TIMESTAMP,
                admin_id INTEGER,
                message_text TEXT,
                message_history TEXT,
                is_active BOOLEAN DEFAULT 1,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id, username, first_name, last_name):
        """Добавление пользователя в БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO users (user_id, username, first_name, last_name) VALUES (?, ?, ?, ?)', 
                     (user_id, username, first_name, last_name))
        conn.commit()
        conn.close()
    
    def add_message_to_history(self, user_id, chat_id, message_text, message_type='text'):
        """Добавление сообщения в историю"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('INSERT INTO message_history (user_id, chat_id, message_text, message_type) VALUES (?, ?, ?, ?)', 
                     (user_id, chat_id, message_text, message_type))
        cursor.execute('UPDATE users SET message_count = message_count + 1 WHERE user_id = ?', (user_id,))
        conn.commit()
        conn.close()
    
    def add_restriction(self, user_id, chat_id, restriction_type, reason, duration_hours, admin_id, message_text, message_history):
        """Добавление мута/бана в БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_time = datetime.now()
        end_time = None if duration_hours == 0 else start_time + timedelta(hours=duration_hours)
        history_json = json.dumps(list(message_history) if isinstance(message_history, deque) else message_history)
        
        cursor.execute('''
            INSERT INTO restrictions 
            (user_id, chat_id, restriction_type, reason, duration_hours, start_time, end_time, admin_id, message_text, message_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, chat_id, restriction_type, reason, duration_hours, start_time, end_time, admin_id, message_text, history_json))
        
        conn.commit()
        conn.close()
        
        # Записываем в TXT файл
        with open('restrictions_log.txt', 'a', encoding='utf-8') as f:
            end_time_str = "НИКОГДА" if end_time is None else end_time.strftime('%d.%m.%Y %H:%M')
            f.write(f"[{start_time.strftime('%d.%m.%Y %H:%M:%S')}] ЮЗ: {user_id} | Причина: {reason} | До: {end_time_str} | Сообщение: {message_text}\n")
    
    def get_user_stats(self, user_id, chat_id):
        """Получение статистики пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM message_history WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        message_count = cursor.fetchone()[0]
        conn.close()
        return message_count
    
    def get_user_restrictions(self, user_id, chat_id):
        """Получает все ограничения пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM restrictions 
            WHERE user_id = ? AND chat_id = ?
            ORDER BY start_time DESC 
            LIMIT 10
        ''', (user_id, chat_id))
        restrictions = cursor.fetchall()
        conn.close()
        return restrictions
    
    def get_active_restriction(self, user_id, chat_id):
        """Получает активное ограничение пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM restrictions 
            WHERE user_id = ? AND chat_id = ? 
            AND (end_time IS NULL OR end_time > CURRENT_TIMESTAMP)
            AND is_active = 1
            ORDER BY start_time DESC 
            LIMIT 1
        ''', (user_id, chat_id))
        restriction = cursor.fetchone()
        conn.close()
        return restriction

    def find_user_by_username(self, username):
        """Находит пользователя по юзернейму"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None

# Инициализация БД
db = Database()

def format_end_time(end_time):
    """Форматирование времени окончания"""
    if end_time is None:
        return "Никогда 🔒"
    else:
        if isinstance(end_time, str):
            # Убираем микросекунды если есть
            if '.' in end_time:
                end_time = end_time.split('.')[0]
            end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
        return end_time.strftime("%d.%m.%Y %H:%M") + " ⏰"

def is_admin(user_id):
    """Проверка, является ли пользователь администратором"""
    return user_id == ADMIN_ID

def check_consecutive_identical(user_id, message_text):
    """Проверяет одинаковые сообщения"""
    history = user_message_history[user_id]
    
    if history and all(msg == message_text for msg in list(history)[-MAX_CONSECUTIVE_IDENTICAL+1:]):
        history.append(message_text)
        return len(history) == MAX_CONSECUTIVE_IDENTICAL and all(msg == message_text for msg in history)
    
    history.append(message_text)
    return False

def check_consecutive_stickers(user_id, sticker_file_id):
    """Проверяет одинаковые стикеры"""
    history = user_sticker_history[user_id]
    
    if history and all(sticker == sticker_file_id for sticker in list(history)[-MAX_CONSECUTIVE_STICKERS+1:]):
        history.append(sticker_file_id)
        return len(history) == MAX_CONSECUTIVE_STICKERS and all(sticker == sticker_file_id for sticker in history)
    
    history.append(sticker_file_id)
    return False

def check_banned_phrases(message_text):
    """Проверяет запрещенные фразы"""
    text_lower = message_text.lower()
    
    # Проверка оскорблений родни
    insult_patterns = [
        r'мам[ауы].*шлюх', r'мамк[ау].*ебал', r'мать.*шалав', 
        r'мать.*ебал', r'мамк[ау].*твою', r'мамк[е].*кончил'
    ]
    
    for pattern in insult_patterns:
        if re.search(pattern, text_lower, re.IGNORECASE):
            return "оскорбление родни", INSULT_MUTE_DURATION
    
    # Проверка точных запрещенных фраз
    for phrase in BANNED_PHRASES:
        if phrase.lower() in text_lower:
            if "аренд" in phrase.lower() or "рассыльщик" in phrase.lower() or "@rozatopld" in phrase:
                return "реклама/спам", 0  # навсегда
            elif any(word in phrase.lower() for word in ['мам', 'мать', 'шлюх', 'шалав']):
                return "оскорбление родни", INSULT_MUTE_DURATION
    
    return None, None

def punish_user(user_id, chat_id, user_name, reason, duration, admin_name="Система"):
    """Наказывает пользователя"""
    try:
        until_date = datetime.now() + timedelta(seconds=duration) if duration > 0 else None
        
        bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(can_send_messages=False),
            until_date=until_date
        )
        
        # Добавляем в БД
        db.add_restriction(
            user_id, chat_id, 'mute', reason, 
            duration // 3600 if duration > 0 else 0, ADMIN_ID, "Авто-модерация", 
            deque()
        )
        
        # Получаем статистику
        message_count = db.get_user_stats(user_id, chat_id)
        
        # Формируем сообщение с эмодзи но без **
        end_time = format_end_time(until_date)
        mute_message = f"🚫 Пользователь замучен\n👤 Пользователь: {user_name}\n🛡️ Администратор: {admin_name}\n📝 Причина: {reason}\n⏰ Конец: {end_time}\n\n📊 Сообщений в чате: {message_count}"
        
        bot.send_message(chat_id, mute_message)
        logger.info(f"Пользователь {user_id} замьючен по причине: {reason}")
        
    except Exception as e:
        logger.error(f"Ошибка при муте пользователя {user_id}: {e}")
        return False
    return True

def unmute_user(user_id, chat_id, user_name, admin_name="Система"):
    """Размучивает пользователя"""
    try:
        bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=user_id,
            permissions=ChatPermissions(
                can_send_messages=True,
                can_send_media_messages=True,
                can_send_polls=True,
                can_send_other_messages=True,
                can_add_web_page_previews=True
            )
        )
        
        response = f"✅ Пользователь размучен\n👤 Пользователь: {user_name}\n🛡️ Администратор: {admin_name}\n⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        bot.send_message(chat_id, response)
        logger.info(f"Пользователь {user_id} размучен администратором {admin_name}")
        
        # Записываем в лог
        with open('restrictions_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] ЮЗ: {user_id} | РАЗМУЧЕН | Админ: {admin_name}\n")
        
    except Exception as e:
        logger.error(f"Ошибка при размуте пользователя {user_id}: {e}")
        return False
    return True

# КОМАНДА /log ДЛЯ ПОЛУЧЕНИЯ ЛОГОВ ПОЛЬЗОВАТЕЛЯ
@bot.message_handler(commands=['log'])
def user_log_command(message):
    """Команда /log для получения логов пользователя"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещен!")
        return
    
    try:
        # Получаем параметр из команды: /log 123456 или /log @username
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Используй: /log ID_пользователя или /log @username")
            return
        
        search_param = parts[1]
        
        # Определяем, это ID или юзернейм
        user_id = None
        if search_param.startswith('@'):
            # Поиск по юзернейму
            username = search_param[1:]  # Убираем @
            user_id = db.find_user_by_username(username)
            if not user_id:
                bot.reply_to(message, f"🔍 Пользователь @{username} не найден в базе")
                return
        else:
            # Поиск по ID
            try:
                user_id = int(search_param)
            except ValueError:
                bot.reply_to(message, "❌ Неверный формат. Используй: /log 123456 или /log @username")
                return
        
        # Получаем все ограничения пользователя
        restrictions = db.get_user_restrictions(user_id, message.chat.id)
        
        if not restrictions:
            bot.reply_to(message, f"🔍 Пользователь {search_param} не найден в базе нарушений")
            return
        
        # Формируем подробный лог
        log_text = f"📋 ЛОГ НАРУШЕНИЙ ПОЛЬЗОВАТЕЛЯ: {search_param}\n"
        log_text += f"👤 ID пользователя: {user_id}\n"
        log_text += f"📅 Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        log_text += f"📊 Всего нарушений: {len(restrictions)}\n\n"
        log_text += "=" * 50 + "\n\n"
        
        for i, restriction in enumerate(restrictions, 1):
            log_text += f"🚨 НАРУШЕНИЕ #{i}\n"
            log_text += f"👤 ID пользователя: {restriction[1]}\n"
            log_text += f"💬 Тип: {restriction[3]}\n"
            log_text += f"📝 Причина: {restriction[4]}\n"
            log_text += f"⏱️ Длительность: {restriction[5]} часов\n"
            
            # Исправляем обработку времени с микросекундами
            start_time = restriction[6]
            if isinstance(start_time, str):
                # Убираем микросекунды если есть
                if '.' in start_time:
                    start_time = start_time.split('.')[0]
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            log_text += f"🕐 Начало: {start_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
            
            end_time = restriction[7]
            if end_time:
                if isinstance(end_time, str):
                    # Убираем микросекунды если есть
                    if '.' in end_time:
                        end_time = end_time.split('.')[0]
                    end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
                log_text += f"🕒 Конец: {end_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                # Проверяем активно ли еще ограничение
                if end_time > datetime.now():
                    log_text += f"📊 Статус: 🔴 АКТИВНО\n"
                else:
                    log_text += f"📊 Статус: 🟢 ЗАВЕРШЕНО\n"
            else:
                log_text += f"🕒 Конец: НИКОГДА\n"
                log_text += f"📊 Статус: 🔴 АКТИВНО\n"
            
            log_text += f"👮 Админ ID: {restriction[8]}\n"
            if restriction[9]:  # message_text
                log_text += f"💭 Сообщение: {restriction[9][:100]}...\n"
            
            log_text += "─" * 40 + "\n\n"
        
        # Создаем файл в памяти
        file = io.BytesIO(log_text.encode('utf-8'))
        
        # Определяем имя файла
        if search_param.startswith('@'):
            file.name = f'user_{search_param[1:]}_log.txt'
        else:
            file.name = f'user_{search_param}_log.txt'
        
        # Отправляем файл
        bot.send_document(
            message.chat.id, 
            file, 
            caption=f"📄 Лог нарушений пользователя {search_param}\n📊 Нарушений: {len(restrictions)}"
        )
        
        logger.info(f"Админ {message.from_user.id} запросил лог пользователя {search_param}")
            
    except Exception as e:
        error_msg = f"❌ Ошибка при получении лога: {e}"
        bot.reply_to(message, error_msg)
        logger.error(error_msg)

# АДМИН ПАНЕЛЬ
def admin_panel_keyboard():
    """Клавиатура админ-панели"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔇 Мут", callback_data="admin_mute"),
        InlineKeyboardButton("🔊 Размут", callback_data="admin_unmute")
    )
    return keyboard

@bot.message_handler(commands=['admin'])
def admin_command(message):
    """Админ-панель (только для админа)"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещен!")
        return
    
    bot.send_message(
        message.chat.id,
        "🛠️ **Админ-панель**\nВыберите действие:",
        reply_markup=admin_panel_keyboard()
    )

# Глобальные переменные для хранения данных
admin_data = {}

@bot.callback_query_handler(func=lambda call: True)
def handle_admin_actions(call):
    """Обработка действий админ-панели"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
        return
    
    if call.data == "admin_mute":
        msg = bot.send_message(
            call.message.chat.id,
            "🔇 **Мут пользователя**\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_mute_chat)
        
    elif call.data == "admin_unmute":
        msg = bot.send_message(
            call.message.chat.id,
            "🔊 **Размут пользователя**\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_unmute_chat)
    
    bot.answer_callback_query(call.id)

def process_mute_chat(message):
    """Получаем ID чата для мута"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'mute'}
        msg = bot.send_message(
            message.chat.id,
            "🔇 **Мут пользователя**\nВведите ID пользователя и время в часах:\n`123456789 24 причина`"
        )
        bot.register_next_step_handler(msg, process_mute_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_unmute_chat(message):
    """Получаем ID чата для размута"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'unmute'}
        msg = bot.send_message(
            message.chat.id,
            "🔊 **Размут пользователя**\nВведите ID пользователя:\n`123456789`"
        )
        bot.register_next_step_handler(msg, process_unmute_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_mute_final(message):
    """Выполняет мут пользователя"""
    try:
        user_data = admin_data.get(message.from_user.id)
        if not user_data:
            bot.reply_to(message, "❌ Ошибка данных!")
            return
        
        chat_id = user_data['chat_id']
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Формат: user_id часы [причина]")
            return
        
        user_id = int(parts[0])
        hours = int(parts[1])
        reason = ' '.join(parts[2:]) if len(parts) > 2 else "Мут из админ-панели"
        
        # Получаем информацию о пользователе
        try:
            user = bot.get_chat_member(chat_id, user_id)
            user_name = user.user.first_name
        except:
            user_name = f"ID: {user_id}"
        
        # ВЫПОЛНЯЕМ РЕАЛЬНЫЙ МУТ
        duration = hours * 3600 if hours > 0 else 0
        success = punish_user(user_id, chat_id, user_name, reason, duration, message.from_user.first_name)
        
        if success:
            bot.reply_to(message, f"✅ Пользователь {user_name} замьючен в чате {chat_id}")
        else:
            bot.reply_to(message, f"❌ Ошибка при муте пользователя")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def process_unmute_final(message):
    """Выполняет размут пользователя"""
    try:
        user_data = admin_data.get(message.from_user.id)
        if not user_data:
            bot.reply_to(message, "❌ Ошибка данных!")
            return
        
        chat_id = user_data['chat_id']
        user_id = int(message.text.strip())
        
        # Получаем информацию о пользователе
        try:
            user = bot.get_chat_member(chat_id, user_id)
            user_name = user.user.first_name
        except:
            user_name = f"ID: {user_id}"
        
        # ВЫПОЛНЯЕМ РЕАЛЬНЫЙ РАЗМУТ
        success = unmute_user(user_id, chat_id, user_name, message.from_user.first_name)
        
        if success:
            bot.reply_to(message, f"✅ Пользователь {user_name} размучен в чате {chat_id}")
        else:
            bot.reply_to(message, f"❌ Ошибка при размуте пользователя")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# Обработчики команд
@bot.message_handler(commands=['start'])
def start_command(message):
    """Обрабатывает команду /start"""
    start_text = """📖 Правила модерации:

🔇 Муты:
• Спам сообщениями – 1 час
• Спам стикерами – 1 час
• Оскорбления родни – 24 часа
• Реклама – навсегда
• Запрещенный контент – навсегда

🆘 Замутили в чате по ошибке?
@rilyglrletukdetuluft (14:00-2:00)

🤖 Бот работает 24/7"""
    bot.reply_to(message, start_text)

@bot.message_handler(commands=['check'])
def check_command(message):
    """Команда /check для проверки пользователя"""
    if not message.text or len(message.text.split()) < 2:
        bot.reply_to(message, "❌ Использование: /check @username")
        return
    
    username = message.text.split()[1].replace('@', '')
    
    try:
        # Для теста используем фиксированный ID
        user_id = 123456789  # Замените на реальный ID при необходимости
        
        restrictions = db.get_user_restrictions(user_id, message.chat.id)
        active_restriction = db.get_active_restriction(user_id, message.chat.id)
        message_count = db.get_user_stats(user_id, message.chat.id)
        
        response = f"🔍 **Информация о пользователе** @{username}\n\n"
        
        if active_restriction:
            end_time = format_end_time(active_restriction[7])
            
            # Исправляем обработку start_time
            start_time = active_restriction[6]
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            
            response += f"📊 Статус: 🔇 Замучен\n"
            response += f"📝 Причина: {active_restriction[4]}\n"
            response += f"⏰ Начало: {start_time.strftime('%d.%m.%Y %H:%M')}\n"
            response += f"🕒 Конец: {end_time}\n"
        else:
            response += f"📊 Статус: ✅ Активен\n"
        
        response += f"💬 Сообщений в чате: {message_count}\n"
        response += f"📋 Всего нарушений: {len(restrictions)}\n"
        
        if restrictions:
            response += f"\n📜 Последние нарушения:\n"
            for i, restriction in enumerate(restrictions[:3], 1):
                end_time = format_end_time(restriction[7])
                
                # Исправляем обработку start_time
                start_time = restriction[6]
                if isinstance(start_time, str):
                    start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
                
                response += f"{i}. {restriction[4]} - {start_time.strftime('%d.%m.%Y %H:%M')}\n"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при проверке: {e}")

# Обработчики сообщений
@bot.message_handler(content_types=['text'])
def handle_text(message):
    """Обрабатывает текстовые сообщения"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    message_text = message.text
    
    # Добавляем в БД
    db.add_user(
        user_id,
        message.from_user.username,
        message.from_user.first_name,
        message.from_user.last_name
    )
    db.add_message_to_history(user_id, chat_id, message_text)
    
    # Проверка на запрещенные фразы
    reason, duration = check_banned_phrases(message_text)
    if reason:
        punish_user(user_id, chat_id, message.from_user.first_name, reason, duration)
        bot.delete_message(chat_id, message.message_id)
        return
    
    # Проверка на идентичные сообщения
    if check_consecutive_identical(user_id, message_text):
        punish_user(user_id, chat_id, message.from_user.first_name, "спам (5 одинаковых сообщений подряд)", SPAM_MUTE_DURATION)
        bot.delete_message(chat_id, message.message_id)
        return
    
    # Проверка на триггеры для ответа с инструкцией по размуту
    if any(trigger in message_text.lower() for trigger in ['он не спамил', 'она не спамила', 'зачем замутил', 'размути']):
        bot.reply_to(message, APPEAL_TEXT)

@bot.message_handler(content_types=['sticker'])
def handle_sticker(message):
    """Обрабатывает стикеры"""
    user_id = message.from_user.id
    chat_id = message.chat.id
    sticker_file_id = message.sticker.file_id
    
    db.add_message_to_history(user_id, chat_id, sticker_file_id, 'sticker')
    
    if check_consecutive_stickers(user_id, sticker_file_id):
        punish_user(user_id, chat_id, message.from_user.first_name, "спам стикерами (5 подряд)", SPAM_MUTE_DURATION)
        bot.delete_message(chat_id, message.message_id)

# Запуск бота
if __name__ == '__main__':
    logger.info("Бот запускается...")
    print("🤖 Бот запущен!")
    print("🔧 Токен: 8207041880:AAEM1F0YaWF3jEKJ-GfRPPOosOBbpTnSY4M")
    print("👑 Админ ID: 8054980148")
    print("🛠️ Админ-панель: /admin")
    print("📄 Команда /log ID/@username - получить лог нарушений пользователя")
    print("🔍 Команда /check работает!")
    bot.infinity_polling()
