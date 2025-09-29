import random
import sqlite3
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton

API_ID = 29703279
API_HASH = "fd7fd0ff9892775020a9cdf834c2729b"
BOT_TOKEN = "ТВОЙ_ТОКЕН"

REQUIRED_CHANNELS = [
    {"id": -1002200798308, "username": "starstoritirt", "name": "⭐ Наш канал"},
    {"id": -1005000433071, "username": "p1ushpepe", "name": "Канал Dotka📊"},
    {"id": -1005000262445, "username": "id1337", "name": "1337🃏"},
    {"id": -1005000035033, "username": "totechkaj", "name": "totechkaj🎰"}
]

conn = sqlite3.connect('stats.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users
                 (user_id INTEGER PRIMARY KEY, 
                  username TEXT,
                  first_join_date TEXT,
                  random_count INTEGER DEFAULT 0,
                  roulette_count INTEGER DEFAULT 0,
                  max_number INTEGER DEFAULT 0,
                  min_number INTEGER DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS stats
                 (id INTEGER PRIMARY KEY,
                  total_random INTEGER DEFAULT 0,
                  total_roulette INTEGER DEFAULT 0,
                  global_max_number INTEGER DEFAULT 0,
                  global_min_number INTEGER DEFAULT 0)''')
conn.commit()

app = Client("RandomBot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
user_states = {}

async def check_subscription(user_id):
    try:
        for channel in REQUIRED_CHANNELS:
            try:
                member = await app.get_chat_member(channel["id"], user_id)
                if member.status in ["left", "kicked", "restricted"]:
                    return False, channel
            except Exception:
                return False, channel
        return True, None
    except Exception:
        return False, REQUIRED_CHANNELS[0]

def update_user_stats(user_id, username, is_random=False, is_roulette=False, number=0):
    cursor = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute("INSERT INTO users (user_id, username, first_join_date) VALUES (?, ?, ?)",
                      (user_id, username, now))
    
    if is_random:
        cursor.execute("UPDATE users SET random_count = random_count + 1 WHERE user_id = ?", (user_id,))
        cursor.execute("SELECT * FROM stats WHERE id = 1")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO stats (id, total_random) VALUES (1, 1)")
        else:
            cursor.execute("UPDATE stats SET total_random = total_random + 1 WHERE id = 1")
    
    if is_roulette:
        cursor.execute("UPDATE users SET roulette_count = roulette_count + 1 WHERE user_id = ?", (user_id,))
        cursor.execute("SELECT * FROM stats WHERE id = 1")
        if not cursor.fetchone():
            cursor.execute("INSERT INTO stats (id, total_roulette) VALUES (1, 1)")
        else:
            cursor.execute("UPDATE stats SET total_roulette = total_roulette + 1 WHERE id = 1")
    
    if number > 0:
        cursor.execute("SELECT max_number FROM users WHERE user_id = ?", (user_id,))
        current_max = cursor.fetchone()
        if not current_max or not current_max[0] or number > current_max[0]:
            cursor.execute("UPDATE users SET max_number = ? WHERE user_id = ?", (number, user_id))
        
        cursor.execute("SELECT min_number FROM users WHERE user_id = ?", (user_id,))
        current_min = cursor.fetchone()
        if not current_min or not current_min[0] or number < current_min[0]:
            cursor.execute("UPDATE users SET min_number = ? WHERE user_id = ?", (number, user_id))
        
        cursor.execute("SELECT global_max_number FROM stats WHERE id = 1")
        global_max = cursor.fetchone()
        if not global_max or not global_max[0] or number > global_max[0]:
            cursor.execute("UPDATE stats SET global_max_number = ? WHERE id = 1", (number,))
        
        cursor.execute("SELECT global_min_number FROM stats WHERE id = 1")
        global_min = cursor.fetchone()
        if not global_min or not global_min[0] or number < global_min[0]:
            cursor.execute("UPDATE stats SET global_min_number = ? WHERE id = 1", (number,))
    
    conn.commit()

def get_user_stats(user_id):
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()

def get_global_stats():
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM stats WHERE id = 1")
    stats = cursor.fetchone()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    return stats, total_users

@app.on_message(filters.command("start"))
async def start(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    is_subscribed, channel = await check_subscription(user_id)
    
    if not is_subscribed:
        buttons = []
        for req_channel in REQUIRED_CHANNELS:
            buttons.append([InlineKeyboardButton(
                f"{req_channel['name']}", 
                url=f"https://t.me/{req_channel['username']}"
            )])
        
        buttons.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        
        await message.reply(
            f"📢 Для использования бота необходимо подписаться на наши каналы:\n\n"
            f"• {REQUIRED_CHANNELS[0]['name']} - обязательный\n"
            f"• Спонсоры бота\n\n"
            f"После подписки нажмите кнопку '✅ Я подписался'",
            reply_markup=keyboard
        )
        return
    
    update_user_stats(user_id, username)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомайзер", callback_data="randomizer")],
        [InlineKeyboardButton("🎯 Рулетка", callback_data="roulette")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📢 Добавить в канал", url="https://t.me/Randomiser_bot?startchannel=true")],
        [InlineKeyboardButton("💎 Наш канал", url=f"https://t.me/{REQUIRED_CHANNELS[0]['username']}")]
    ])
    
    user_data = get_user_stats(user_id)
    join_date = user_data[2] if user_data else "сегодня"
    
    await message.reply(
        f"🎰 Добро пожаловать, {username}!\n"
        f"📅 Первый раз здесь: {join_date}\n\n"
        "Выберите режим:",
        reply_markup=keyboard
    )

@app.on_callback_query(filters.regex("^check_subscription$"))
async def check_subscription_callback(client, callback_query):
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or callback_query.from_user.first_name
    
    is_subscribed, channel = await check_subscription(user_id)
    
    if not is_subscribed:
        await callback_query.answer(f"❌ Вы не подписались на {channel['name']}!", show_alert=True)
        return
    
    update_user_stats(user_id, username)
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомайзер", callback_data="randomizer")],
        [InlineKeyboardButton("🎯 Рулетка", callback_data="roulette")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📢 Добавить в канал", url="https://t.me/Randomiser_bot?startchannel=true")],
        [InlineKeyboardButton("💎 Наш канал", url=f"https://t.me/{REQUIRED_CHANNELS[0]['username']}")]
    ])
    
    user_data = get_user_stats(user_id)
    join_date = user_data[2] if user_data else "сегодня"
    
    await callback_query.message.edit_text(
        f"🎰 Добро пожаловать, {username}!\n"
        f"📅 Первый раз здесь: {join_date}\n\n"
        "Выберите режим:",
        reply_markup=keyboard
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^randomizer$"))
async def random_callback(client, callback_query):
    user_id = callback_query.from_user.id
    
    is_subscribed, channel = await check_subscription(user_id)
    if not is_subscribed:
        await callback_query.answer(f"❌ Сначала подпишитесь на {channel['name']}!", show_alert=True)
        return
    
    user_states[user_id] = {"mode": "randomizer", "step": 1}
    await callback_query.message.edit_text(
        "🔢 Рандомайзер\n\nВведите максимальное число (от 1 до X):\n\n"
        "Пример: если введете 100, я выберу число от 1 до 100"
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^roulette$"))
async def roulette_callback(client, callback_query):
    user_id = callback_query.from_user.id
    
    is_subscribed, channel = await check_subscription(user_id)
    if not is_subscribed:
        await callback_query.answer(f"❌ Сначала подпишитесь на {channel['name']}!", show_alert=True)
        return
    
    user_states[user_id] = {"mode": "roulette", "step": 1}
    await callback_query.message.edit_text(
        "🎯 Рулетка\n\nВведите количество вариантов (от 2 до 10):\n\n"
        "Пример: если введете 3, нужно будет ввести 3 варианта"
    )
    await callback_query.answer()

@app.on_callback_query(filters.regex("^stats$"))
async def stats_callback(client, callback_query):
    user_id = callback_query.from_user.id
    
    is_subscribed, channel = await check_subscription(user_id)
    if not is_subscribed:
        await callback_query.answer(f"❌ Сначала подпишитесь на {channel['name']}!", show_alert=True)
        return
    
    user_data = get_user_stats(user_id)
    global_stats, total_users = get_global_stats()
    
    if user_data:
        user_text = (
            f"📊 Ваша статистика:\n\n"
            f"• 🎲 Рандомайзер: {user_data[3]} раз\n"
            f"• 🎯 Рулетка: {user_data[4]} раз\n"
            f"• 🔢 Макс. число: {user_data[5] or 0}\n"
            f"• 🔢 Мин. число: {user_data[6] or 0}\n"
            f"• 📅 Первый визит: {user_data[2]}"
        )
    else:
        user_text = "📊 Статистика пока недоступна"
    
    if global_stats:
        global_text = (
            f"\n\n🌐 Глобальная статистика:\n\n"
            f"• 👥 Всего пользователей: {total_users}\n"
            f"• 🎲 Всего рандомов: {global_stats[1] or 0}\n"
            f"• 🎯 Всего рулеток: {global_stats[2] or 0}\n"
            f"• 🔢 Макс. число: {global_stats[3] or 0}\n"
            f"• 🔢 Мин. число: {global_stats[4] or 0}"
        )
    else:
        global_text = "\n\n🌐 Глобальная статистика пока недоступна"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Назад", callback_data="back_to_main")]
    ])
    
    await callback_query.message.edit_text(user_text + global_text, reply_markup=keyboard)
    await callback_query.answer()

@app.on_callback_query(filters.regex("^back_to_main$"))
async def back_to_main(client, callback_query):
    user_id = callback_query.from_user.id
    username = callback_query.from_user.username or callback_query.from_user.first_name
    
    is_subscribed, channel = await check_subscription(user_id)
    if not is_subscribed:
        await callback_query.answer(f"❌ Сначала подпишитесь на {channel['name']}!", show_alert=True)
        return
    
    user_data = get_user_stats(user_id)
    join_date = user_data[2] if user_data else "сегодня"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎲 Рандомайзер", callback_data="randomizer")],
        [InlineKeyboardButton("🎯 Рулетка", callback_data="roulette")],
        [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
        [InlineKeyboardButton("📢 Добавить в канал", url="https://t.me/Randomiser_bot?startchannel=true")],
        [InlineKeyboardButton("💎 Наш канал", url=f"https://t.me/{REQUIRED_CHANNELS[0]['username']}")]
    ])
    
    await callback_query.message.edit_text(
        f"🎰 Добро пожаловать, {username}!\n"
        f"📅 Первый раз здесь: {join_date}\n\n"
        "Выберите режим:",
        reply_markup=keyboard
    )
    await callback_query.answer()

@app.on_message(filters.channel & filters.text)
async def handle_channel_commands(client, message: Message):
    if message.text.startswith('@Randomiser_bot'):
        try:
            parts = message.text.split()
            if len(parts) >= 2 and parts[1].isdigit():
                max_num = int(parts[1])
                if max_num < 1:
                    return
                
                rand_num = random.randint(1, max_num)
                await message.reply(f"🎉 Случайное число от 1 до {max_num}:\n🎲 **{rand_num}** 🎲")
                
        except (ValueError, IndexError):
            pass

@app.on_message(filters.text & filters.private)
async def handle_input(client, message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or message.from_user.first_name
    
    is_subscribed, channel = await check_subscription(user_id)
    if not is_subscribed:
        buttons = []
        for req_channel in REQUIRED_CHANNELS:
            buttons.append([InlineKeyboardButton(
                f"{req_channel['name']}", 
                url=f"https://t.me/{req_channel['username']}"
            )])
        
        buttons.append([InlineKeyboardButton("✅ Я подписался", callback_data="check_subscription")])
        
        keyboard = InlineKeyboardMarkup(buttons)
        
        await message.reply(
            f"❌ Для использования бота необходимо подписаться на {channel['name']}!\n\n"
            f"После подписки нажмите кнопку '✅ Я подписался'",
            reply_markup=keyboard
        )
        return
    
    if user_id not in user_states:
        return
    
    state = user_states[user_id]
    text = message.text.strip()
    
    if state["mode"] == "randomizer" and state["step"] == 1:
        try:
            max_num = int(text)
            if max_num < 1:
                await message.reply("❌ Число должно быть больше 0!")
                return
            
            rand_num = random.randint(1, max_num)
            update_user_stats(user_id, username, is_random=True, number=rand_num)
            
            await message.reply(
                f"🎉 Случайное число от 1 до {max_num}:\n"
                f"🎲 **{rand_num}** 🎲\n\n"
                "Хотите еще раз? Нажмите /start"
            )
            del user_states[user_id]
            
        except ValueError:
            await message.reply("❌ Пожалуйста, введите целое число!")
    
    elif state["mode"] == "roulette" and state["step"] == 1:
        try:
            options_count = int(text)
            if options_count < 2:
                await message.reply("❌ Нужно минимум 2 варианта!")
                return
            if options_count > 10:
                await message.reply("❌ Максимум 10 вариантов!")
                return
            
            user_states[user_id] = {
                "mode": "roulette", 
                "step": 2, 
                "options_count": options_count,
                "options": [],
                "current_option": 1
            }
            
            await message.reply(
                f"🎯 Отлично! Будет {options_count} вариантов.\n\n"
                "Введите вариант 1:"
            )
            
        except ValueError:
            await message.reply("❌ Пожалуйста, введите число от 2 до 10!")
    
    elif state["mode"] == "roulette" and state["step"] == 2:
        options = state["options"]
        options_count = state["options_count"]
        current_option = state["current_option"]
        
        options.append(text)
        
        if len(options) < options_count:
            user_states[user_id]["options"] = options
            user_states[user_id]["current_option"] = current_option + 1
            await message.reply(f"✅ Вариант {current_option} принят!\n\nВведите вариант {current_option + 1}:")
        else:
            update_user_stats(user_id, username, is_roulette=True)
            winner = random.choice(options)
            options_text = "\n".join([f"{i+1}. {opt}" for i, opt in enumerate(options)])
            
            await message.reply(
                f"🎉 Рулетка завершена!\n\n"
                f"Все варианты:\n{options_text}\n\n"
                f"🏆 Победитель:\n**{winner}** 🎯\n\n"
                "Хотите еще раз? Нажмите /start"
            )
            del user_states[user_id]

if __name__ == '__main__':
    print("🎰 Бот с обязательной подпиской и статистикой запущен!")
    app.run()
