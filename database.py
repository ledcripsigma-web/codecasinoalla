import sqlite3
import json
from datetime import datetime, timedelta
from collections import deque

class Database:
    def __init__(self, db_path="anti_spam.db"):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Инициализация базы данных"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Таблица пользователей
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
        
        # Таблица мутов/банов
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
                unmute_time TIMESTAMP,
                unmute_admin_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (user_id)
            )
        ''')
        
        # Таблица истории сообщений
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
        
        conn.commit()
        conn.close()
    
    def add_user(self, user_id, username, first_name, last_name):
        """Добавление пользователя в БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO users (user_id, username, first_name, last_name)
            VALUES (?, ?, ?, ?)
        ''', (user_id, username, first_name, last_name))
        
        conn.commit()
        conn.close()
    
    def add_message_to_history(self, user_id, chat_id, message_text, message_type='text'):
        """Добавление сообщения в историю"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO message_history (user_id, chat_id, message_text, message_type)
            VALUES (?, ?, ?, ?)
        ''', (user_id, chat_id, message_text, message_type))
        
        cursor.execute('''
            UPDATE users SET message_count = message_count + 1 
            WHERE user_id = ?
        ''', (user_id,))
        
        conn.commit()
        conn.close()
    
    def get_recent_messages(self, user_id, chat_id, limit=10):
        """Получение последних сообщений пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT message_text, message_type, timestamp 
            FROM message_history 
            WHERE user_id = ? AND chat_id = ?
            ORDER BY timestamp DESC 
            LIMIT ?
        ''', (user_id, chat_id, limit))
        
        messages = cursor.fetchall()
        conn.close()
        return messages
    
    def add_restriction(self, user_id, chat_id, restriction_type, reason, duration_hours, admin_id, message_text, message_history):
        """Добавление мута/бана в БД"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        start_time = datetime.now()
        if duration_hours == 0:
            end_time = None
        else:
            end_time = start_time + timedelta(hours=duration_hours)
        
        history_json = json.dumps(list(message_history) if isinstance(message_history, deque) else message_history)
        
        cursor.execute('''
            INSERT INTO restrictions 
            (user_id, chat_id, restriction_type, reason, duration_hours, start_time, end_time, admin_id, message_text, message_history)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, chat_id, restriction_type, reason, duration_hours, start_time, end_time, admin_id, message_text, history_json))
        
        conn.commit()
        conn.close()
        return cursor.lastrowid
    
    def get_user_restriction(self, user_id, chat_id):
        """Получение текущего мута/бана пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM restrictions 
            WHERE user_id = ? AND chat_id = ? 
            AND (end_time IS NULL OR end_time > CURRENT_TIMESTAMP)
            ORDER BY start_time DESC 
            LIMIT 1
        ''', (user_id, chat_id))
        
        restriction = cursor.fetchone()
        conn.close()
        return restriction
    
    def get_user_info(self, user_id):
        """Получение информации о пользователе"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
        user = cursor.fetchone()
        
        cursor.execute('''
            SELECT * FROM restrictions 
            WHERE user_id = ? 
            ORDER BY start_time DESC 
            LIMIT 5
        ''', (user_id,))
        
        restrictions = cursor.fetchall()
        conn.close()
        return user, restrictions
    
    def get_user_stats(self, user_id, chat_id):
        """Получение статистики пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM message_history 
            WHERE user_id = ? AND chat_id = ?
        ''', (user_id, chat_id))
        
        message_count = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT warning_count FROM users WHERE user_id = ?
        ''', (user_id,))
        
        warning_count = cursor.fetchone()[0] if cursor.fetchone() else 0
        
        conn.close()
        return message_count, warning_count
    
    def deactivate_restriction(self, user_id, chat_id, admin_id):
        """Деактивирует текущее ограничение пользователя (размут)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE restrictions 
            SET is_active = 0, 
                unmute_time = CURRENT_TIMESTAMP,
                unmute_admin_id = ?
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
        ''', (admin_id, user_id, chat_id))
        
        conn.commit()
        conn.close()
    
    def get_active_restriction(self, user_id, chat_id):
        """Получает активное ограничение пользователя"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT * FROM restrictions 
            WHERE user_id = ? AND chat_id = ? AND is_active = 1
            ORDER BY start_time DESC 
            LIMIT 1
        ''', (user_id, chat_id))
        
        restriction = cursor.fetchone()
        conn.close()
        return restriction
