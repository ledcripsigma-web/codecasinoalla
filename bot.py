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
import requests
import time

# Создаем Flask сервер для Render
app = Flask(__name__)

@app.route('/')
def home():
    return "🤖 Бот работает! Telegram: @ledcripsigma_bot"

def run_web():
    app.run(host='0.0.0.0', port=10000, debug=False)

# Запускаем веб-сервер в отдельном потоке
threading.Thread(target=run_web, daemon=True).start()

# 🔥 АВТОПИНГ ДЛЯ RENDER - БОТ НЕ УСНЕТ
def keep_awake():
    while True:
        time.sleep(240)  # 4 минуты
        try:
            requests.get('https://codecasinoalla-1.onrender.com/')
            print("🔄 Автопинг - бот активен")
        except Exception as e:
            print(f"❌ Ошибка автопинга: {e}")

# Запускаем автопинг в отдельном потоке
threading.Thread(target=keep_awake, daemon=True).start()

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Конфигурация
BOT_TOKEN = "8207041880:AAEM1F0YaWF3jEKJ-GfRPPOosOBbpTnSY4M"
ADMIN_ID = 8054980148
APPEAL_TEXT = "🆘Если вас замутило по ошибке: @rilyglrletukdetuluft (моментальный ответ 14:00 — 2:00)"
MAX_WARNS = 3  # Максимум варнов перед баном
WARN_EXPIRE_DAYS = 3  # Варны сгорают через 3 дня

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
user_warns = defaultdict(int)  # Хранит количество варнов пользователя

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
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS warns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                reason TEXT,
                admin_id INTEGER,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expire_time TIMESTAMP,
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
    
    def add_warn(self, user_id, chat_id, reason, admin_id):
        """Добавление варна пользователю"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        expire_time = datetime.now() + timedelta(days=WARN_EXPIRE_DAYS)
        
        cursor.execute('''
            INSERT INTO warns (user_id, chat_id, reason, admin_id, expire_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, chat_id, reason, admin_id, expire_time))
        
        # Обновляем счетчик активных варнов
        cursor.execute('UPDATE users SET warning_count = warning_count + 1 WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
        
        # Обновляем кэш
        user_warns[user_id] = self.get_active_warn_count(user_id, chat_id)
        
        # Записываем в лог
        with open('warns_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] ЮЗ: {user_id} | ВАРН | Причина: {reason} | Админ: {admin_id} | Сгорает: {expire_time.strftime('%d.%m.%Y %H:%M')}\n")
    
    def remove_warn(self, user_id, chat_id, admin_id):
        """Удаление последнего варна"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Находим последний варн
        cursor.execute('''
            SELECT id FROM warns 
            WHERE user_id = ? AND chat_id = ?
            ORDER BY timestamp DESC 
            LIMIT 1
        ''', (user_id, chat_id))
        
        result = cursor.fetchone()
        if result:
            warn_id = result[0]
            # Удаляем варн
            cursor.execute('DELETE FROM warns WHERE id = ?', (warn_id,))
            # Обновляем счетчик
            cursor.execute('UPDATE users SET warning_count = GREATEST(warning_count - 1, 0) WHERE user_id = ?', (user_id,))
            
        conn.commit()
        conn.close()
        
        # Обновляем кэш
        user_warns[user_id] = self.get_active_warn_count(user_id, chat_id)
        
        # Записываем в лог
        with open('warns_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] ЮЗ: {user_id} | АНВАРН | Админ: {admin_id}\n")
    
    def get_active_warn_count(self, user_id, chat_id):
        """Получает количество активных варнов пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND chat_id = ? AND is_active = 1 AND (expire_time IS NULL OR expire_time > CURRENT_TIMESTAMP)', (user_id, chat_id))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_user_warns(self, user_id, chat_id):
        """Получает все варны пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT * FROM warns 
            WHERE user_id = ? AND chat_id = ?
            ORDER BY timestamp DESC 
            LIMIT 10
        ''', (user_id, chat_id))
        warns = cursor.fetchall()
        conn.close()
        return warns
    
    def get_user_stats(self, user_id, chat_id):
        """Получение статистики пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM message_history WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        message_count = cursor.fetchone()[0]
        conn.close()
        return message_count
    
    def get_user_stats_today(self, user_id, chat_id):
        """Получение статистики пользователя за сегодня"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM message_history WHERE user_id = ? AND chat_id = ? AND DATE(timestamp) = ?', (user_id, chat_id, today))
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

def check_repeated_patterns(message_text):
    """Проверяет повторяющиеся паттерны в одном сообщении"""
    lines = message_text.strip().split('\n')
    if len(lines) < 3:  # Минимум 3 строки для паттерна
        return False
    
    # Проверяем, есть ли повторяющиеся блоки текста
    unique_blocks = set()
    block_count = 0
    
    current_block = []
    for line in lines:
        line = line.strip()
        if line:  # Игнорируем пустые строки
            current_block.append(line)
        else:
            if current_block:  # Пустая строка - конец блока
                block_text = '\n'.join(current_block)
                unique_blocks.add(block_text)
                current_block = []
                block_count += 1
    
    # Обрабатываем последний блок
    if current_block:
        block_text = '\n'.join(current_block)
        unique_blocks.add(block_text)
        block_count += 1
    
    # Если блоков больше 2 и уникальных мало - это спам
    if block_count >= 3 and len(unique_blocks) <= 2:
        return True
    
    # Проверяем повторяющиеся строки
    line_counts = {}
    for line in lines:
        line = line.strip()
        if line and len(line) > 5:  # Игнорируем короткие строки
            line_counts[line] = line_counts.get(line, 0) + 1
    
    # Если есть строка, повторяющаяся много раз
    for line, count in line_counts.items():
        if count >= 5:
            return True
    
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

def punish_user(user_id, chat_id, user_name, reason, duration, admin_name="Система", message_text=""):
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
            duration // 3600 if duration > 0 else 0, ADMIN_ID, message_text, 
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
        punish_user(user_id, chat_id, message.from_user.first_name, reason, duration, message_text=message_text)
        bot.delete_message(chat_id, message.message_id)
        return
    
    # Проверка на идентичные сообщения подряд
    if check_consecutive_identical(user_id, message_text):
        punish_user(user_id, chat_id, message.from_user.first_name, "спам (5 одинаковых сообщений подряд)", SPAM_MUTE_DURATION, message_text=message_text)
        bot.delete_message(chat_id, message.message_id)
        return
    
    # Проверка на повторяющиеся паттерны в одном сообщении
    if check_repeated_patterns(message_text):
        punish_user(user_id, chat_id, message.from_user.first_name, "спам (повторяющиеся паттерны)", SPAM_MUTE_DURATION, message_text=message_text)
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
        punish_user(user_id, chat_id, message.from_user.first_name, "спам стикерами (5 подряд)", SPAM_MUTE_DURATION, message_text="[СТИКЕР]")
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
    print("🚫 Анти-спам: 5 одинаковых сообщений ИЛИ повторяющиеся паттерны")
    bot.infinity_polling()
