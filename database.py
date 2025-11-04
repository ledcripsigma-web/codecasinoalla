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
        
        # Таблица варнов
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
        """Получение статистики пользователя в конкретном чате"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT COUNT(*) FROM message_history 
            WHERE user_id = ? AND chat_id = ?
        ''', (user_id, chat_id))
        
        message_count = cursor.fetchone()[0]
        conn.close()
        return message_count
    
    def get_user_stats_all_chats(self, user_id):
        """Получение статистики пользователя во всех чатах"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM message_history WHERE user_id = ?', (user_id,))
        message_count = cursor.fetchone()[0]
        conn.close()
        return message_count
    
    def get_user_stats_today(self, user_id, chat_id):
        """Получение статистики пользователя за сегодня в конкретном чате"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM message_history WHERE user_id = ? AND chat_id = ? AND DATE(timestamp) = ?', (user_id, chat_id, today))
        message_count = cursor.fetchone()[0]
        conn.close()
        return message_count
    
    def get_user_stats_today_all_chats(self, user_id):
        """Получение статистики пользователя за сегодня во всех чатах"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        today = datetime.now().strftime('%Y-%m-%d')
        cursor.execute('SELECT COUNT(*) FROM message_history WHERE user_id = ? AND DATE(timestamp) = ?', (user_id, today))
        message_count = cursor.fetchone()[0]
        conn.close()
        return message_count
    
    def get_user_join_date(self, user_id):
        """Получает дату регистрации пользователя в боте"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT join_date FROM users WHERE user_id = ?', (user_id,))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            join_date = result[0]
            if isinstance(join_date, str):
                join_date = datetime.strptime(join_date, '%Y-%m-%d %H:%M:%S')
            return join_date
        return None
    
    def get_user_first_message_date(self, user_id, chat_id):
        """Получает дату первого сообщения пользователя в чате"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT MIN(timestamp) FROM message_history WHERE user_id = ? AND chat_id = ?', (user_id, chat_id))
        result = cursor.fetchone()
        conn.close()
        
        if result and result[0]:
            first_date = result[0]
            if isinstance(first_date, str):
                first_date = datetime.strptime(first_date, '%Y-%m-%d %H:%M:%S')
            return first_date
        return None
    
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
    
    def add_warn(self, user_id, chat_id, reason, admin_id, expire_days=3):
        """Добавление варна пользователю"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        expire_time = datetime.now() + timedelta(days=expire_days)
        
        cursor.execute('''
            INSERT INTO warns (user_id, chat_id, reason, admin_id, expire_time)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, chat_id, reason, admin_id, expire_time))
        
        # Обновляем счетчик активных варнов
        cursor.execute('UPDATE users SET warning_count = warning_count + 1 WHERE user_id = ?', (user_id,))
        
        conn.commit()
        conn.close()
    
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
    
    def get_active_warn_count(self, user_id, chat_id):
        """Получает количество активных варнов пользователя в чате"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND chat_id = ? AND is_active = 1 AND (expire_time IS NULL OR expire_time > CURRENT_TIMESTAMP)', (user_id, chat_id))
        count = cursor.fetchone()[0]
        conn.close()
        return count
    
    def get_active_warn_count_all_chats(self, user_id):
        """Получает количество активных варнов пользователя во всех чатах"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT COUNT(*) FROM warns WHERE user_id = ? AND is_active = 1 AND (expire_time IS NULL OR expire_time > CURRENT_TIMESTAMP)', (user_id,))
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
    
    def find_user_by_username(self, username):
        """Находит пользователя по юзернейму"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('SELECT user_id FROM users WHERE username = ?', (username,))
        result = cursor.fetchone()
        conn.close()
        return result[0] if result else None
