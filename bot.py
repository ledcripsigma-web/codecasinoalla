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
    
    # Добавляем текущее сообщение в историю
    history.append(message_text)
    
    # Проверяем только если в истории достаточно сообщений
    if len(history) < MAX_CONSECUTIVE_IDENTICAL:
        return False
    
    # Берем последние 5 сообщений
    last_messages = list(history)[-MAX_CONSECUTIVE_IDENTICAL:]
    
    # Проверяем, что все 5 сообщений одинаковые
    first_message = last_messages[0]
    if all(msg == first_message for msg in last_messages):
        return True
    
    return False
    
    # Проверяем паттерны типа "1 1 1 1 1" или "а а а а а"
    words = cleaned_text.split()
    if len(words) >= 5:
        # Проверяем, все ли слова одинаковые
        if all(word == words[0] for word in words):
            return True
        
        # Проверяем много повторяющихся слов
        if len(words) >= 8:
            word_counts = {}
            for word in words:
                word_counts[word] = word_counts.get(word, 0) + 1
            
            # Если есть слово, которое повторяется 5+ раз
            for word, count in word_counts.items():
                if count >= 5:
                    return True
            
            # Если очень мало уникальных слов в длинном сообщении
            unique_words = set(words)
            if len(unique_words) <= 3 and len(words) >= 10:
                return True
    
    # Проверяем повторение одинаковых символов или цифр
    if len(message_text) >= 10:
        # Проверяем паттерны типа "11111", "aaaaa", "+-+-+-"
        chars = list(message_text.replace(' ', '').replace('\n', ''))
        if len(chars) >= 5:
            char_counts = {}
            for char in chars:
                char_counts[char] = char_counts.get(char, 0) + 1
            
            # Если один символ повторяется много раз
            for char, count in char_counts.items():
                if count >= 8:
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

def ban_user(user_id, chat_id, user_name, reason, admin_name="Система"):
    """Банит пользователя"""
    try:
        bot.ban_chat_member(
            chat_id=chat_id,
            user_id=user_id
        )
        
        # Добавляем в БД
        db.add_restriction(
            user_id, chat_id, 'ban', reason, 
            0, ADMIN_ID, "Бан из админ-панели", 
            deque()
        )
        
        ban_message = f"🔨 Пользователь забанен\n👤 Пользователь: {user_name}\n🛡️ Администратор: {admin_name}\n📝 Причина: {reason}"
        
        bot.send_message(chat_id, ban_message)
        logger.info(f"Пользователь {user_id} забанен по причине: {reason}")
        
    except Exception as e:
        logger.error(f"Ошибка при бане пользователя {user_id}: {e}")
        return False
    return True

def unban_user(user_id, chat_id, user_name, admin_name="Система"):
    """Разбанивает пользователя"""
    try:
        bot.unban_chat_member(
            chat_id=chat_id,
            user_id=user_id
        )
        
        response = f"✅ Пользователь разбанен\n👤 Пользователь: {user_name}\n🛡️ Администратор: {admin_name}\n⏰ Время: {datetime.now().strftime('%d.%m.%Y %H:%M')}"
        
        bot.send_message(chat_id, response)
        logger.info(f"Пользователь {user_id} разбанен администратором {admin_name}")
        
        # Записываем в лог
        with open('restrictions_log.txt', 'a', encoding='utf-8') as f:
            f.write(f"[{datetime.now().strftime('%d.%m.%Y %H:%M:%S')}] ЮЗ: {user_id} | РАЗБАНЕН | Админ: {admin_name}\n")
        
    except Exception as e:
        logger.error(f"Ошибка при разбане пользователя {user_id}: {e}")
        return False
    return True

def warn_user(user_id, chat_id, user_name, reason, admin_name="Система"):
    """Выдает предупреждение пользователю"""
    try:
        # Добавляем варн в БД
        db.add_warn(user_id, chat_id, reason, ADMIN_ID)
        
        warn_count = db.get_active_warn_count(user_id, chat_id)
        
        warn_message = f"⚠️ Пользователь получил предупреждение\n👤 Пользователь: {user_name}\n🛡️ Администратор: {admin_name}\n📝 Причина: {reason}\n📊 Всего варнов: {warn_count}/{MAX_WARNS}\n⏰ Сгорит через: {WARN_EXPIRE_DAYS} дней"
        
        if warn_count >= MAX_WARNS:
            # Автоматический бан при достижении лимита варнов
            ban_reason = f"Автобан за {MAX_WARNS} предупреждений"
            ban_user(user_id, chat_id, user_name, ban_reason, admin_name)
            warn_message += f"\n\n🔨 Достигнут лимит {MAX_WARNS} варнов - пользователь забанен!"
        
        bot.send_message(chat_id, warn_message)
        logger.info(f"Пользователь {user_id} получил варн: {reason}")
        
    except Exception as e:
        logger.error(f"Ошибка при выдаче варна пользователю {user_id}: {e}")
        return False
    return True

def unwarn_user(user_id, chat_id, user_name, admin_name="Система"):
    """Снимает предупреждение пользователю"""
    try:
        current_warns = db.get_active_warn_count(user_id, chat_id)
        
        if current_warns > 0:
            db.remove_warn(user_id, chat_id, ADMIN_ID)
            new_warns = db.get_active_warn_count(user_id, chat_id)
            
            response = f"✅ Предупреждение снято\n👤 Пользователь: {user_name}\n🛡️ Администратор: {admin_name}\n📊 Теперь варнов: {new_warns}/{MAX_WARNS}"
        else:
            response = f"ℹ️ У пользователя {user_name} нет активных предупреждений"
        
        bot.send_message(chat_id, response)
        logger.info(f"Пользователь {user_id} лишен варна администратором {admin_name}")
        
    except Exception as e:
        logger.error(f"Ошибка при снятии варна пользователя {user_id}: {e}")
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

def delete_message_by_link(chat_id, message_id, admin_name="Система"):
    """Удаляет сообщение по ссылке"""
    try:
        bot.delete_message(chat_id, message_id)
        logger.info(f"Сообщение {message_id} удалено из чата {chat_id} администратором {admin_name}")
        return True
    except Exception as e:
        logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
        return False

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
        warns = db.get_user_warns(user_id, message.chat.id)
        
        if not restrictions and not warns:
            bot.reply_to(message, f"🔍 Пользователь {search_param} не найден в базе нарушений")
            return
        
        # Формируем подробный лог
        log_text = f"📋 ЛОГ НАРУШЕНИЙ ПОЛЬЗОВАТЕЛЯ: {search_param}\n"
        log_text += f"👤 ID пользователя: {user_id}\n"
        log_text += f"📅 Сформирован: {datetime.now().strftime('%d.%m.%Y %H:%M:%S')}\n"
        log_text += f"📊 Всего нарушений: {len(restrictions)}\n"
        log_text += f"⚠️ Всего варнов: {len(warns)}\n\n"
        log_text += "=" * 50 + "\n\n"
        
        # Добавляем варны в лог
        if warns:
            log_text += "🔸 ИСТОРИЯ ПРЕДУПРЕЖДЕНИЙ:\n\n"
            for i, warn in enumerate(warns, 1):
                log_text += f"⚠️ ВАРН #{i}\n"
                log_text += f"📝 Причина: {warn[3]}\n"
                
                # Исправляем обработку времени
                warn_time = warn[5]
                if isinstance(warn_time, str):
                    if '.' in warn_time:
                        warn_time = warn_time.split('.')[0]
                    warn_time = datetime.strptime(warn_time, '%Y-%m-%d %H:%M:%S')
                log_text += f"🕐 Время: {warn_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                
                expire_time = warn[6]
                if expire_time:
                    if isinstance(expire_time, str):
                        if '.' in expire_time:
                            expire_time = expire_time.split('.')[0]
                        expire_time = datetime.strptime(expire_time, '%Y-%m-%d %H:%M:%S')
                    log_text += f"⏰ Сгорит: {expire_time.strftime('%d.%m.%Y %H:%M:%S')}\n"
                
                log_text += f"👮 Админ ID: {warn[4]}\n"
                log_text += "─" * 30 + "\n\n"
        
        # Добавляем нарушения в лог
        if restrictions:
            log_text += "🔹 ИСТОРИЯ НАРУШЕНИЙ:\n\n"
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
            caption=f"📄 Лог нарушений пользователя {search_param}\n📊 Нарушений: {len(restrictions)} | Варнов: {len(warns)}"
        )
        
        logger.info(f"Админ {message.from_user.id} запросил лог пользователя {search_param}")
            
    except Exception as e:
        error_msg = f"❌ Ошибка при получении лога: {e}"
        bot.reply_to(message, error_msg)
        logger.error(error_msg)

# КОМАНДА /profile ДЛЯ ПОЛЬЗОВАТЕЛЕЙ
@bot.message_handler(commands=['profile'])
def profile_command(message):
    """Команда /profile для просмотра статистики пользователя"""
    try:
        user_id = message.from_user.id
        chat_id = message.chat.id
        
        # Получаем статистику
        total_messages = db.get_user_stats(user_id, chat_id)
        today_messages = db.get_user_stats_today(user_id, chat_id)
        warn_count = db.get_active_warn_count(user_id, chat_id)
        
        # Получаем информацию о пользователе
        user_name = message.from_user.first_name
        username = f"@{message.from_user.username}" if message.from_user.username else "Не указан"
        
        profile_text = f"👤 Профиль пользователя\n\n"
        profile_text += f"🆔 ID: {user_id}\n"
        profile_text += f"📛 Имя: {user_name}\n"
        profile_text += f"🔗 Юзернейм: {username}\n\n"
        profile_text += f"📊 Статистика в этом чате:\n"
        profile_text += f"💬 Всего сообщений: {total_messages}\n"
        profile_text += f"📅 Сообщений сегодня: {today_messages}\n"
        profile_text += f"⚠️ Активных предупреждений: {warn_count}/{MAX_WARNS}\n"
        
        if warn_count > 0:
            profile_text += f"⏰ Предупреждения сгорят через {WARN_EXPIRE_DAYS} дней\n"
        
        bot.reply_to(message, profile_text)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при получении профиля: {e}")

# АДМИН ПАНЕЛЬ
def admin_panel_keyboard():
    """Клавиатура админ-панели"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("🔇 Мут", callback_data="admin_mute"),
        InlineKeyboardButton("🔊 Размут", callback_data="admin_unmute"),
        InlineKeyboardButton("⚠️ Варн", callback_data="admin_warn"),
        InlineKeyboardButton("✅ Анварн", callback_data="admin_unwarn"),
        InlineKeyboardButton("🔨 Бан", callback_data="admin_ban"),
        InlineKeyboardButton("🔄 Анбан", callback_data="admin_unban"),
        InlineKeyboardButton("🗑️ Удалить сообщение", callback_data="admin_delete")
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
        "🛠️ Админ-панель\nВыберите действие:",
        reply_markup=admin_panel_keyboard()
    )

# КЛАВИАТУРА ДЛЯ СТАРТА
def start_keyboard():
    """Клавиатура для команды /start"""
    keyboard = InlineKeyboardMarkup(row_width=2)
    
    # Кнопки для всех пользователей
    keyboard.add(
        InlineKeyboardButton("👤 Мой профиль", callback_data="start_profile")
    )
    
    # Кнопки только для админа
    if ADMIN_ID:
        keyboard.add(
            InlineKeyboardButton("🛠️ Админ-панель", callback_data="start_admin"),
            InlineKeyboardButton("📊 Проверить пользователя", callback_data="start_check"),
            InlineKeyboardButton("📄 Логи пользователя", callback_data="start_log")
        )
    
    return keyboard

@bot.message_handler(commands=['start'])
def start_command(message):
    """Обрабатывает команду /start"""
    start_text = """🤖 Добро пожаловать в Anti-Spam Bot!

📋 Перед началом работы:
1. Добавьте бота в ваш чат
2. Выдайте боту права администратора
3. Убедитесь, что бот может:
   - Удалять сообщения
   - Банить пользователей
   - Ограничивать права (мутить)

📖 Правила модерации:

🔇 Муты:
• Спам сообщениями – 1 час
• Спам стикерами – 1 час  
• Оскорбления родни – 24 часа
• Реклама – навсегда
• Запрещенный контент – навсегда
• Повторяющиеся паттерны в одном сообщении – 1 час

⚠️ Система предупреждений:
• Варны выдаются по усмотрению администратора
• 3 предупреждения = автоматический бан
• Варны сгорают через 3 дня

🆘 Замутили в чате по ошибке?
@rilyglrletukdetuluft (14:00-2:00)

Выберите действие:"""
    
    bot.send_message(
        message.chat.id, 
        start_text,
        reply_markup=start_keyboard()
    )

# ОБРАБОТКА КНОПОК СТАРТА
@bot.callback_query_handler(func=lambda call: call.data.startswith('start_'))
def handle_start_actions(call):
    """Обработка действий из стартового меню"""
    if call.data == "start_profile":
        # Показываем инструкцию по использованию команды /profile
        profile_instruction = """👤 **Как посмотреть свой профиль:**

Чтобы посмотреть свою статистику, просто напишите команду в любом чате где есть бот:

`/profile`

📊 **В профиле вы увидите:**
• Ваш ID и юзернейм
• Количество сообщений в чате  
• Сообщений за сегодня
• Активные предупреждения

💡 *Команда работает в любом чате где добавлен бот!*"""
        
        bot.send_message(call.message.chat.id, profile_instruction, parse_mode='Markdown')
    
    elif call.data == "start_admin":
        # Админ-панель только для админа
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
            return
        admin_command(call.message)
    
    elif call.data == "start_check":
        # Проверка пользователя только для админа
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
            return
        msg = bot.send_message(call.message.chat.id, "Введите @username для проверки:")
        bot.register_next_step_handler(msg, process_check_from_button)
    
    elif call.data == "start_log":
        # Логи пользователя только для админа
        if not is_admin(call.from_user.id):
            bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
            return
        msg = bot.send_message(call.message.chat.id, "Введите ID или @username для получения логов:")
        bot.register_next_step_handler(msg, process_log_from_button)
    
    bot.answer_callback_query(call.id)

def process_check_from_button(message):
    """Обработка проверки пользователя из кнопки"""
    try:
        username = message.text.replace('@', '')
        user_id = 123456789  # Замени на реальную логику
        
        restrictions = db.get_user_restrictions(user_id, message.chat.id)
        active_restriction = db.get_active_restriction(user_id, message.chat.id)
        message_count = db.get_user_stats(user_id, message.chat.id)
        warn_count = db.get_active_warn_count(user_id, message.chat.id)
        
        response = f"🔍 Информация о пользователе @{username}\n\n"
        
        if active_restriction:
            end_time = format_end_time(active_restriction[7])
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
        response += f"⚠️ Предупреждений: {warn_count}/{MAX_WARNS}\n"
        response += f"📋 Всего нарушений: {len(restrictions)}\n"
        
        bot.reply_to(message, response)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при проверке: {e}")

def process_log_from_button(message):
    """Обработка логов пользователя из кнопки"""
    user_log_command(message)

# Глобальные переменные для хранения данных
admin_data = {}

@bot.callback_query_handler(func=lambda call: call.data.startswith('admin_'))
def handle_admin_actions(call):
    """Обработка действий админ-панели"""
    if not is_admin(call.from_user.id):
        bot.answer_callback_query(call.id, "❌ Доступ запрещен!")
        return
    
    if call.data == "admin_mute":
        msg = bot.send_message(
            call.message.chat.id,
            "🔇 Мут пользователя\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_mute_chat)
        
    elif call.data == "admin_unmute":
        msg = bot.send_message(
            call.message.chat.id,
            "🔊 Размут пользователя\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_unmute_chat)
        
    elif call.data == "admin_warn":
        msg = bot.send_message(
            call.message.chat.id,
            "⚠️ Выдать предупреждение\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_warn_chat)
        
    elif call.data == "admin_unwarn":
        msg = bot.send_message(
            call.message.chat.id,
            "✅ Снять предупреждение\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_unwarn_chat)
        
    elif call.data == "admin_ban":
        msg = bot.send_message(
            call.message.chat.id,
            "🔨 Забанить пользователя\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_ban_chat)
        
    elif call.data == "admin_unban":
        msg = bot.send_message(
            call.message.chat.id,
            "🔄 Разбанить пользователя\nВведите ID чата:"
        )
        bot.register_next_step_handler(msg, process_unban_chat)
        
    elif call.data == "admin_delete":
        msg = bot.send_message(
            call.message.chat.id,
            "🗑️ Удалить сообщение\nВведите ссылку на сообщение в формате:\n`https://t.me/c/CHAT_ID/MESSAGE_ID`\n\n💡 *Как получить ссылку:*\n1. Нажмите на сообщение в чате\n2. Выберите 'Копировать ссылку'\n3. Отправьте ссылку боту",
            parse_mode='Markdown'
        )
        bot.register_next_step_handler(msg, process_delete_message)
    
    bot.answer_callback_query(call.id)

def process_mute_chat(message):
    """Получаем ID чата для мута"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'mute'}
        msg = bot.send_message(
            message.chat.id,
            "🔇 Мут пользователя\nВведите ID пользователя и время в часах:\n123456789 24 причина"
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
            "🔊 Размут пользователя\nВведите ID пользователя:\n123456789"
        )
        bot.register_next_step_handler(msg, process_unmute_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_warn_chat(message):
    """Получаем ID чата для варна"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'warn'}
        msg = bot.send_message(
            message.chat.id,
            "⚠️ Выдать предупреждение\nВведите ID пользователя и причину:\n123456789 спам"
        )
        bot.register_next_step_handler(msg, process_warn_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_unwarn_chat(message):
    """Получаем ID чата для анварна"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'unwarn'}
        msg = bot.send_message(
            message.chat.id,
            "✅ Снять предупреждение\nВведите ID пользователя:\n123456789"
        )
        bot.register_next_step_handler(msg, process_unwarn_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_ban_chat(message):
    """Получаем ID чата для бана"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'ban'}
        msg = bot.send_message(
            message.chat.id,
            "🔨 Забанить пользователя\nВведите ID пользователя и причину:\n123456789 спам"
        )
        bot.register_next_step_handler(msg, process_ban_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_unban_chat(message):
    """Получаем ID чата для анбана"""
    try:
        chat_id = int(message.text)
        admin_data[message.from_user.id] = {'chat_id': chat_id, 'action': 'unban'}
        msg = bot.send_message(
            message.chat.id,
            "🔄 Разбанить пользователя\nВведите ID пользователя:\n123456789"
        )
        bot.register_next_step_handler(msg, process_unban_final)
    except ValueError:
        bot.reply_to(message, "❌ Неверный ID чата!")

def process_delete_message(message):
    """Обрабатывает удаление сообщения по ссылке"""
    try:
        message_link = message.text.strip()
        
        # Парсим ссылку на сообщение
        # Формат: https://t.me/c/CHAT_ID/MESSAGE_ID
        if "t.me/c/" in message_link:
            parts = message_link.split("/")
            if len(parts) >= 6:
                chat_id = int("-100" + parts[4])  # Преобразуем в формат для бота
                message_id = int(parts[5])
                
                # Пытаемся удалить сообщение
                success = delete_message_by_link(chat_id, message_id, message.from_user.first_name)
                
                if success:
                    bot.reply_to(message, f"✅ Сообщение успешно удалено!\n💬 ID сообщения: {message_id}\n👥 Чат ID: {chat_id}")
                else:
                    bot.reply_to(message, "❌ Не удалось удалить сообщение. Проверьте:\n• Права бота в чате\n• Корректность ссылки\n• Существование сообщения")
            else:
                bot.reply_to(message, "❌ Неверный формат ссылки. Используйте: https://t.me/c/CHAT_ID/MESSAGE_ID")
        else:
            bot.reply_to(message, "❌ Неверная ссылка. Убедитесь, что это ссылка на сообщение из чата.")
            
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка при удалении сообщения: {e}")

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
        success = punish_user(user_id, chat_id, user_name, reason, duration, message.from_user.first_name, message_text=reason)
        
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

def process_warn_final(message):
    """Выдает предупреждение пользователю"""
    try:
        user_data = admin_data.get(message.from_user.id)
        if not user_data:
            bot.reply_to(message, "❌ Ошибка данных!")
            return
        
        chat_id = user_data['chat_id']
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Формат: user_id [причина]")
            return
        
        user_id = int(parts[0])
        reason = ' '.join(parts[1:]) if len(parts) > 1 else "Предупреждение из админ-панели"
        
        # Получаем информацию о пользователе
        try:
            user = bot.get_chat_member(chat_id, user_id)
            user_name = user.user.first_name
        except:
            user_name = f"ID: {user_id}"
        
        # ВЫДАЕМ ПРЕДУПРЕЖДЕНИЕ
        success = warn_user(user_id, chat_id, user_name, reason, message.from_user.first_name)
        
        if success:
            bot.reply_to(message, f"✅ Пользователь {user_name} получил предупреждение в чате {chat_id}")
        else:
            bot.reply_to(message, f"❌ Ошибка при выдаче предупреждения")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def process_unwarn_final(message):
    """Снимает предупреждение пользователю"""
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
        
        # СНИМАЕМ ПРЕДУПРЕЖДЕНИЕ
        success = unwarn_user(user_id, chat_id, user_name, message.from_user.first_name)
        
        if success:
            bot.reply_to(message, f"✅ С пользователя {user_name} снято предупреждение в чате {chat_id}")
        else:
            bot.reply_to(message, f"❌ Ошибка при снятии предупреждения")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def process_ban_final(message):
    """Выполняет бан пользователя"""
    try:
        user_data = admin_data.get(message.from_user.id)
        if not user_data:
            bot.reply_to(message, "❌ Ошибка данных!")
            return
        
        chat_id = user_data['chat_id']
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "❌ Формат: user_id [причина]")
            return
        
        user_id = int(parts[0])
        reason = ' '.join(parts[1:]) if len(parts) > 1 else "Бан из админ-панели"
        
        # Получаем информацию о пользователе
        try:
            user = bot.get_chat_member(chat_id, user_id)
            user_name = user.user.first_name
        except:
            user_name = f"ID: {user_id}"
        
        # ВЫПОЛНЯЕМ РЕАЛЬНЫЙ БАН
        success = ban_user(user_id, chat_id, user_name, reason, message.from_user.first_name)
        
        if success:
            bot.reply_to(message, f"✅ Пользователь {user_name} забанен в чате {chat_id}")
        else:
            bot.reply_to(message, f"❌ Ошибка при бане пользователя")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

def process_unban_final(message):
    """Выполняет разбан пользователя"""
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
        
        # ВЫПОЛНЯЕМ РЕАЛЬНЫЙ РАЗБАН
        success = unban_user(user_id, chat_id, user_name, message.from_user.first_name)
        
        if success:
            bot.reply_to(message, f"✅ Пользователь {user_name} разбанен в чате {chat_id}")
        else:
            bot.reply_to(message, f"❌ Ошибка при разбане пользователя")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Ошибка: {e}")

# Обработчики команд
@bot.message_handler(commands=['check'])
def check_command(message):
    """Команда /check для проверки пользователя"""
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Доступ запрещен!")
        return
    
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
        warn_count = db.get_active_warn_count(user_id, message.chat.id)
        
        response = f"🔍 Информация о пользователе @{username}\n\n"
        
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
        response += f"⚠️ Предупреждений: {warn_count}/{MAX_WARNS}\n"
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
        punish_user(user_id, chat_id, message.from_user.first_name, reason, duration, message_text=message_text)
        bot.delete_message(chat_id, message.message_id)
        return
    
    # Проверка на повторяющиеся паттерны в одном сообщении
    if check_repeated_patterns(message_text):
        punish_user(user_id, chat_id, message.from_user.first_name, "спам (повторяющиеся паттерны в сообщении)", SPAM_MUTE_DURATION, message_text=message_text)
        bot.delete_message(chat_id, message.message_id)
        return
    
    # Проверка на идентичные сообщения подряд
    if check_consecutive_identical(user_id, message_text):
        punish_user(user_id, chat_id, message.from_user.first_name, "спам (5 одинаковых сообщений подряд)", SPAM_MUTE_DURATION, message_text=message_text)
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
    print("👤 Команда /profile - статистика пользователя")
    print("📄 Команда /log ID/@username - получить лог нарушений пользователя")
    print("⚠️ Система предупреждений: 3 варна = бан (сгорают через 3 дня)")
    print("🔍 Команда /check работает!")
    print("🆕 Обнаружение спама: повторяющиеся паттерны в одном сообщении")
    print("🗑️ Новая функция: удаление сообщений по ссылке в админ-панели")
    bot.infinity_polling()
