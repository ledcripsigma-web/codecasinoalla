import logging
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters

# Включим логирование для отладки
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Токен вашего бота, полученный от @BotFather
BOT_TOKEN = "8021571057:AAHAk5Avw9HBLBFb_b9CtozOEZKw6upkf3U"

# Простая "база данных" в виде словаря (в реальном проекте используйте настоящую БД!)
user_data = {}

# Магазин предметов
SHOP_ITEMS = {
    "lucky_charm": {"name": "🍀 Счастливый талисман", "price": 50, "description": "Увеличивает шанс выигрыша в костях на 10%"},
    "double_or_nothing": {"name": "🎲 Удвоитель", "price": 100, "description": "Дает шанс удвоить выигрыш в слотах"},
    "vip_status": {"name": "👑 VIP Статус", "price": 500, "description": "Ежедневный бонус +100 монет"},
}

# Функция для получения баланса пользователя
def get_balance(user_id):
    if user_id not in user_data:
        user_data[user_id] = {"balance": 100, "inventory": {}}  # Начальный баланс 100
    return user_data[user_id]["balance"]

# Функция для обновления баланса
def update_balance(user_id, amount):
    if user_id not in user_data:
        user_data[user_id] = {"balance": 100, "inventory": {}}
    user_data[user_id]["balance"] += amount
    return user_data[user_id]["balance"]

# Функция для получения инвентаря
def get_inventory(user_id):
    if user_id not in user_data:
        user_data[user_id] = {"balance": 100, "inventory": {}}
    return user_data[user_id]["inventory"]

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    
    welcome_text = (
        f"🎰 Добро пожаловать в Crypto Casino! 🎰\n\n"
        f"Ваш баланс: {balance} монет\n\n"
        f"Доступные игры:\n"
        f"🎲 /dice - Игра в кости (ставка 10 монет)\n"
        f"🎯 /slots - Игровые автоматы (ставка 5 монет)\n"
        f"🏪 /shop - Магазин предметов\n"
        f"💰 /balance - Проверить баланс\n"
        f"🎁 /daily - Ежедневный бонус"
    )
    
    await update.message.reply_text(welcome_text)

# Команда /balance
async def balance_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    
    await update.message.reply_text(f"💰 Ваш баланс: {balance} монет")

# Команда /daily - ежедневный бонус
async def daily_bonus(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = update_balance(user_id, 50)  # Добавляем 50 монет ежедневно
    
    await update.message.reply_text(f"🎁 Вы получили ежедневный бонус: 50 монет!\n💰 Теперь у вас: {balance} монет")

# Игра в кости
async def play_dice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    
    # Проверка баланса
    if balance < 10:
        await update.message.reply_text("❌ Недостаточно монет для игры! Минимальная ставка: 10 монет")
        return
    
    # Вычитаем ставку
    new_balance = update_balance(user_id, -10)
    
    # Бросок костей
    player_dice = random.randint(1, 6)
    bot_dice = random.randint(1, 6)
    
    # Проверяем, есть ли у пользователя счастливый талисман
    inventory = get_inventory(user_id)
    if "lucky_charm" in inventory and random.random() < 0.1:  # 10% шанс
        player_dice += 1
        result_text = "🍀 Ваш талисман сработал! +1 к броску\n"
    else:
        result_text = ""
    
    # Определяем победителя
    if player_dice > bot_dice:
        win_amount = 20  # Выигрыш 20 монет
        update_balance(user_id, win_amount)
        result_text += f"🎲 Вы выиграли! {player_dice} vs {bot_dice}\n💰 Выигрыш: {win_amount} монет"
    elif player_dice < bot_dice:
        result_text += f"🎲 Вы проиграли! {player_dice} vs {bot_dice}"
    else:
        win_amount = 10  # Возвращаем ставку
        update_balance(user_id, win_amount)
        result_text += f"🎲 Ничья! {player_dice} vs {bot_dice}\n💰 Возврат ставки"
    
    result_text += f"\n💰 Баланс: {get_balance(user_id)} монет"
    await update.message.reply_text(result_text)

# Игровые автоматы
async def play_slots(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    
    # Проверка баланса
    if balance < 5:
        await update.message.reply_text("❌ Недостаточно монет для игры! Минимальная ставка: 5 монет")
        return
    
    # Вычитаем ставку
    update_balance(user_id, -5)
    
    # Генерируем случайные символы
    symbols = ["🍒", "🍋", "🍊", "🍇", "🔔", "💎", "7️⃣"]
    result = [random.choice(symbols) for _ in range(3)]
    
    # Проверяем выигрыш
    if result[0] == result[1] == result[2]:
        if result[0] == "💎":
            win_amount = 100  # Джекпот!
        else:
            win_amount = 50  # Большой выигрыш
        win_text = f"🎰 ДЖЕКПОТ! {''.join(result)} 🎰\n💰 Выигрыш: {win_amount} монет!"
        
        # Проверяем удвоитель
        inventory = get_inventory(user_id)
        if "double_or_nothing" in inventory and random.random() < 0.5:  # 50% шанс удвоения
            win_amount *= 2
            win_text = f"🎲 Удвоитель сработал! 🎲\n" + win_text.replace(f"Выигрыш: {win_amount//2}", f"Выигрыш: {win_amount}")
            
        update_balance(user_id, win_amount)
    elif result[0] == result[1] or result[1] == result[2]:
        win_amount = 10
        update_balance(user_id, win_amount)
        win_text = f"🎰 Почти угадали! {''.join(result)}\n💰 Выигрыш: {win_amount} монет!"
    else:
        win_text = f"🎰 Повезет в следующий раз! {''.join(result)}"
    
    win_text += f"\n💰 Баланс: {get_balance(user_id)} монет"
    await update.message.reply_text(win_text)

# Магазин предметов
async def shop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    balance = get_balance(user_id)
    
    keyboard = []
    shop_text = "🏪 Магазин предметов\n\n"
    
    for item_id, item in SHOP_ITEMS.items():
        shop_text += f"{item['name']} - {item['price']} монет\n{item['description']}\n\n"
        keyboard.append([InlineKeyboardButton(f"Купить {item['name']}", callback_data=f"buy_{item_id}")])
    
    shop_text += f"💰 Ваш баланс: {balance} монет"
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(shop_text, reply_markup=reply_markup)

# Обработка покупок в магазине
async def handle_shop_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    item_id = query.data.split("_")[1]  # Получаем ID предмета
    
    if item_id not in SHOP_ITEMS:
        await query.edit_message_text("❌ Этот предмет больше не доступен!")
        return
    
    item = SHOP_ITEMS[item_id]
    balance = get_balance(user_id)
    inventory = get_inventory(user_id)
    
    # Проверяем, достаточно ли денег
    if balance < item["price"]:
        await query.edit_message_text(f"❌ Недостаточно монет для покупки {item['name']}!")
        return
    
    # Покупаем предмет
    update_balance(user_id, -item["price"])
    
    # Добавляем в инвентарь
    if item_id in inventory:
        inventory[item_id] += 1
    else:
        inventory[item_id] = 1
    
    await query.edit_message_text(
        f"🎉 Вы успешно купили {item['name']}!\n"
        f"💰 Остаток: {get_balance(user_id)} монет\n"
        f"📦 Ваш инвентарь: {inventory}"
    )

# Главная функция
def main():
    # Создаем приложение и передаем ему токен бота
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Добавляем обработчики команд
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("balance", balance_cmd))
    application.add_handler(CommandHandler("daily", daily_bonus))
    application.add_handler(CommandHandler("dice", play_dice))
    application.add_handler(CommandHandler("slots", play_slots))
    application.add_handler(CommandHandler("shop", shop))
    
    # Добавляем обработчик callback-запросов от кнопок
    application.add_handler(CallbackQueryHandler(handle_shop_callback, pattern="^buy_"))
    
    # Запускаем бота
    application.run_polling()
    print("Бот запущен!")

if __name__ == "__main__":
    main()
