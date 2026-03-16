Структура проекта
plain
Copy
vpn-bot/
├── bot.py                 # Основной бот (обновлённый)
├── config.py              # Конфигурация
├── database.py            # Работа с БД
├── xray_manager.py        # Управление 3X-UI API
├── deploy/
│   ├── docker-compose.yml # Docker для 3X-UI
│   ├── install.sh         # Автоустановка сервера
│   └── xray-config.json   # Настройки Xray
└── requirements.txt
1. Обновлённый bot.py с управлением подписками
Python
Copy
import asyncio
import logging
import aiohttp
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, Message
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from database import Database
from xray_manager import XrayManager
from config import BOT_TOKEN, ADMIN_IDS, XRAY_PANEL_URL, XRAY_PANEL_USER, XRAY_PANEL_PASS

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
db = Database()
xray = XrayManager(XRAY_PANEL_URL, XRAY_PANEL_USER, XRAY_PANEL_PASS)

# ==================== СОСТОЯНИЯ ====================

class BuySubscription(StatesGroup):
    selecting_duration = State()
    selecting_payment = State()

class TopUpBalance(StatesGroup):
    entering_amount = State()

class AdminState(StatesGroup):
    broadcast = State()
    add_days = State()

# ==================== КЛАВИАТУРЫ ====================

def get_main_menu(is_admin=False):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="💳 Купить Подписку", callback_data="buy_sub"),
            InlineKeyboardButton(text="🌐 Подключиться", callback_data="connect")
        ],
        [
            InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up"),
            InlineKeyboardButton(text="👥 Пригласить друга", callback_data="invite")
        ],
        [
            InlineKeyboardButton(text="📈 Мой профиль", callback_data="profile"),
            InlineKeyboardButton(text="🆘 Поддержка", callback_data="support")
        ],
        [
            InlineKeyboardButton(text="🌍 Сменить язык", callback_data="change_lang")
        ]
    ])
    if is_admin:
        keyboard.inline_keyboard.append([
            InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")
        ])
    return keyboard

def get_subscription_menu():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1 мес - 299₽", callback_data="sub_1_299"),
            InlineKeyboardButton(text="3 мес - 799₽", callback_data="sub_3_799")
        ],
        [
            InlineKeyboardButton(text="6 мес - 1499₽", callback_data="sub_6_1499"),
            InlineKeyboardButton(text="12 мес - 2799₽", callback_data="sub_12_2799")
        ],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    return keyboard

def get_payment_methods():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")],
        [InlineKeyboardButton(text="₿ Крипта", callback_data="pay_crypto")],
        [InlineKeyboardButton(text="💎 Telegram Stars", callback_data="pay_stars")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_sub")]
    ])

def get_topup_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="100₽", callback_data="topup_100"),
            InlineKeyboardButton(text="300₽", callback_data="topup_300"),
            InlineKeyboardButton(text="500₽", callback_data="topup_500")
        ],
        [
            InlineKeyboardButton(text="1000₽", callback_data="topup_1000"),
            InlineKeyboardButton(text="2000₽", callback_data="topup_2000"),
            InlineKeyboardButton(text="5000₽", callback_data="topup_5000")
        ],
        [InlineKeyboardButton(text="💰 Своя сумма", callback_data="topup_custom")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def get_connect_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Android", callback_data="os_android")],
        [InlineKeyboardButton(text="🍎 iOS", callback_data="os_ios")],
        [InlineKeyboardButton(text="💻 Windows", callback_data="os_windows")],
        [InlineKeyboardButton(text="🐧 Linux", callback_data="os_linux")],
        [InlineKeyboardButton(text="🍏 macOS", callback_data="os_macos")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

def get_profile_menu(has_active=False):
    buttons = []
    if has_active:
        buttons.append([InlineKeyboardButton(text="📋 Мои конфиги", callback_data="my_configs")])
        buttons.append([InlineKeyboardButton(text="🔄 Продлить", callback_data="buy_sub")])
    else:
        buttons.append([InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_sub")])
    buttons.append([InlineKeyboardButton(text="📜 История", callback_data="payment_history")])
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def get_admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
        [InlineKeyboardButton(text="⚙️ Управление сервером", callback_data="admin_server")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

# ==================== ОБРАБОТЧИКИ ====================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username
    
    # Регистрация пользователя
    await db.add_user(user_id, username)
    
    is_admin = user_id in ADMIN_IDS
    welcome = (
        "👋 <b>Добро пожаловать в Xray VPN!</b>\n\n"
        "🚀 Быстрые Xray-конфиги для обхода блокировок\n"
        "⚡ Высокая скорость и стабильность\n"
        "🌍 Серверы по всему миру\n\n"
        "Выберите действие:"
    )
    await message.answer(welcome, reply_markup=get_main_menu(is_admin), parse_mode="HTML")

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=get_main_menu(is_admin),
        parse_mode="HTML"
    )
    await callback.answer()

# ==================== ПОКУПКА ПОДПИСКИ ====================

@dp.callback_query(F.data == "buy_sub")
async def buy_subscription(callback: CallbackQuery):
    user_id = callback.from_user.id
    
    # Проверяем, есть ли уже конфиг
    existing = await db.get_user_config(user_id)
    
    text = "💳 <b>Выберите тариф:</b>\n\n"
    if existing:
        text += "⚠️ У вас уже есть конфиг. После оплаты срок действия будет продлён!\n\n"
    
    text += (
        "✅ Неограниченный трафик\n"
        "✅ До 5 устройств\n"
        "✅ Поддержка 24/7\n"
        "✅ Автоматическая выдача"
    )
    await callback.message.edit_text(text, reply_markup=get_subscription_menu(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("sub_"))
async def process_subscription(callback: CallbackQuery, state: FSMContext):
    _, months, price = callback.data.split("_")
    months, price = int(months), int(price)
    
    await state.update_data(months=months, price=price)
    
    text = (
        f"💳 <b>Оформление подписки</b>\n\n"
        f"📅 Период: {months} мес\n"
        f"💰 Стоимость: {price}₽\n\n"
        f"Выберите способ оплаты:"
    )
    await callback.message.edit_text(text, reply_markup=get_payment_methods(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    price = data.get("price")
    months = data.get("months")
    method = callback.data.split("_")[1]
    
    # Создаём платёж в БД
    payment_id = await db.create_payment(callback.from_user.id, price, months, method)
    
    methods = {"card": "Банковская карта", "crypto": "Криптовалюта", "stars": "Telegram Stars"}
    
    text = (
        f"💳 <b>Оплата через {methods.get(method)}</b>\n\n"
        f"Сумма: <b>{price}₽</b>\n"
        f"ID платежа: <code>{payment_id}</code>\n\n"
        f"⚠️ После оплаты нажмите кнопку ниже.\n"
        f"Конфиг будет автоматически создан или продлён."
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Я оплатил {price}₽", callback_data=f"confirm_pay_{payment_id}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_sub")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id
    
    # Проверяем платёж
    payment = await db.get_payment(payment_id)
    if not payment or payment['status'] != 'pending':
        await callback.answer("❌ Платёж не найден или уже обработан!", show_alert=True)
        return
    
    # Помечаем как оплаченный (в реальности тут проверка от платёжки)
    await db.update_payment_status(payment_id, 'completed')
    
    months = payment['months']
    days = months * 30
    
    # Проверяем, есть ли у пользователя уже конфиг в 3X-UI
    existing_client = await db.get_user_config(user_id)
    
    if existing_client:
        # ПРОДЛЕВАЕМ СУЩЕСТВУЮЩИЙ КОНФИГ
        client_id = existing_client['client_id']
        
        # Получаем текущую дату окончания или сегодня
        current_expiry = existing_client['expiry_date']
        if current_expiry and current_expiry > datetime.now():
            new_expiry = current_expiry + timedelta(days=days)
        else:
            new_expiry = datetime.now() + timedelta(days=days)
        
        # Обновляем в 3X-UI (включаем если был выключен)
        success = await xray.update_client_expiry(client_id, new_expiry, enable=True)
        
        if success:
            await db.update_subscription(user_id, client_id, new_expiry, status='active')
            
            # Получаем конфиг для показа
            config_link = existing_client['config_link']
            
            text = (
                "✅ <b>Подписка успешно продлена!</b>\n\n"
                f"📅 Новый срок: до {new_expiry.strftime('%d.%m.%Y')}\n"
                f"⏳ Добавлено: {days} дней\n\n"
                "🔑 <b>Ваш конфиг (без изменений):</b>\n"
                f"<code>{config_link}</code>\n\n"
                "✅ Всё работает! Переподключение не требуется."
            )
        else:
            text = "❌ Ошибка продления. Обратитесь в поддержку."
    else:
        # СОЗДАЁМ НОВЫЙ КОНФИГ
        email = f"user_{user_id}_{int(datetime.now().timestamp())}"
        expiry = datetime.now() + timedelta(days=days)
        
        client = await xray.create_client(email, expiry)
        
        if client:
            # Сохраняем в БД
            await db.create_subscription(user_id, client['id'], client['config_link'], expiry)
            
            text = (
                "✅ <b>Оплата прошла успешно!</b>\n\n"
                f"📅 Подписка до: {expiry.strftime('%d.%m.%Y')}\n\n"
                "🔑 <b>Ваш Xray конфиг:</b>\n"
                f"<code>{client['config_link']}</code>\n\n"
                "📋 <b>Как подключиться:</b>\n"
                "1. Скопируйте конфиг (нажмите на него)\n"
                "2. Откройте приложение (V2RayNG, Nekoray)\n"
                "3. Импортируйте конфиг\n\n"
                "⚠️ <b>Сохраните этот конфиг!</b> При продлении он не меняется."
            )
        else:
            text = "❌ Ошибка создания конфига. Обратитесь в поддержку."
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Как подключиться", callback_data="connect")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()
    await callback.answer("✅ Успешно!")

# ==================== ПРОФИЛЬ ====================

@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    sub = await db.get_user_config(user_id)
    
    balance = user['balance'] if user else 0
    
    text = (
        "📈 <b>Мой профиль</b>\n\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"💰 Баланс: <b>{balance}₽</b>\n"
    )
    
    has_active = False
    if sub:
        expiry = sub['expiry_date']
        is_active = expiry > datetime.now() and sub['status'] == 'active'
        
        if is_active:
            days_left = (expiry - datetime.now()).days
            text += (
                f"\n📅 Подписка: ✅ Активна\n"
                f"⏳ Осталось: {days_left} дней\n"
                f"📆 До: {expiry.strftime('%d.%m.%Y')}\n"
                f"🔌 Статус: {'🟢 Включен' if sub['status'] == 'active' else '🔴 Отключен'}"
            )
            has_active = True
        else:
            text += f"\n📅 Подписка: ❌ Истекла ({expiry.strftime('%d.%m.%Y')})"
    else:
        text += "\n📅 Подписка: ❌ Нет активной"
    
    await callback.message.edit_text(text, reply_markup=get_profile_menu(has_active), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "my_configs")
async def show_configs(callback: CallbackQuery):
    user_id = callback.from_user.id
    sub = await db.get_user_config(user_id)
    
    if not sub:
        text = "📋 У вас пока нет конфигов"
    else:
        expiry = sub['expiry_date']
        status = "✅ Активен" if expiry > datetime.now() else "❌ Истёк"
        
        text = (
            "📋 <b>Ваш конфиг:</b>\n\n"
            f"Статус: {status}\n"
            f"До: {expiry.strftime('%d.%m.%Y')}\n\n"
            f"<code>{sub['config_link']}</code>\n\n"
            "⚠️ Не передавайте конфиг третьим лицам!"
        )
    
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()

def get_back_button():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])

# ==================== ПОДКЛЮЧЕНИЕ ====================

@dp.callback_query(F.data == "connect")
async def connect_menu(callback: CallbackQuery):
    text = "🌐 <b>Выберите платформу:</b>"
    await callback.message.edit_text(text, reply_markup=get_connect_menu(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("os_"))
async def show_instructions(callback: CallbackQuery):
    os_name = callback.data.split("_")[1]
    
    instructions = {
        "android": (
            "📱 <b>Android</b>\n\n"
            "1. Установите <b>V2RayNG</b> из Google Play\n"
            "2. Откройте приложение\n"
            "3. Нажмите '+' → 'Импорт из буфера'\n"
            "4. Вставьте ваш конфиг\n"
            "5. Нажмите на сервер для подключения\n\n"
            "📥 <a href='https://play.google.com/store/apps/details?id=com.v2ray.ang'>V2RayNG</a>"
        ),
        "ios": (
            "🍎 <b>iOS</b>\n\n"
            "1. Установите <b>Shadowrocket</b> ($2.99)\n"
            "2. Нажмите '+' → вставьте конфиг\n"
            "3. Включите переключатель\n\n"
            "🆓 Альтернатива: <b>OneClick</b> (бесплатно)"
        ),
        "windows": (
            "💻 <b>Windows</b>\n\n"
            "1. Скачайте <b>Nekoray</b> с GitHub\n"
            "2. Распакуйте и запустите\n"
            "3. Сервер → Добавить (Ctrl+V)\n"
            "4. Вставьте конфиг → Запустить\n\n"
            "📥 <a href='https://github.com/MatsuriDayo/nekoray/releases'>Nekoray</a>"
        ),
        "linux": (
            "🐧 <b>Linux</b>\n\n"
            "1. Установите <b>Nekoray</b>\n"
            "2. Импортируйте конфиг\n"
            "3. Запустите подключение\n\n"
            "💡 Терминал:\n"
            "<code>sudo apt install v2ray</code>"
        ),
        "macos": (
            "🍏 <b>macOS</b>\n\n"
            "1. Установите <b>V2RayXS</b>\n"
            "2. Импортируйте конфиг\n"
            "3. Запустите из меню-бара\n\n"
            "📥 <a href='https://github.com/tzmax/V2RayXS/releases'>V2RayXS</a>"
        )
    }
    
    await callback.message.edit_text(
        instructions.get(os_name, "Нет инструкции"),
        reply_markup=get_back_button(),
        parse_mode="HTML",
        disable_web_page_preview=True
    )
    await callback.answer()

# ==================== ПОПОЛНЕНИЕ ====================

@dp.callback_query(F.data == "top_up")
async def top_up_menu(callback: CallbackQuery):
    text = "💰 <b>Выберите сумму пополнения:</b>"
    await callback.message.edit_text(text, reply_markup=get_topup_menu(), parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data.startswith("topup_"))
async def process_topup(callback: CallbackQuery, state: FSMContext):
    amount = callback.data.split("_")[1]
    
    if amount == "custom":
        await state.set_state(TopUpBalance.entering_amount)
        await callback.message.edit_text(
            "💰 Введите сумму (мин. 50₽):",
            reply_markup=get_back_button()
        )
    else:
        amount_int = int(amount)
        await callback.message.edit_text(
            f"💰 Пополнение на {amount_int}₽\n\nВыберите способ:",
            reply_markup=get_payment_methods(),
            parse_mode="HTML"
        )
    await callback.answer()

@dp.message(TopUpBalance.entering_amount)
async def custom_amount(message: Message, state: FSMContext):
    try:
        amount = int(message.text)
        if amount < 50:
            await message.answer("❌ Минимум 50₽", reply_markup=get_back_button())
            return
        
        await message.answer(
            f"💰 Пополнение на {amount}₽\n\nВыберите способ:",
            reply_markup=get_payment_methods(),
            parse_mode="HTML"
        )
        await state.clear()
    except ValueError:
        await message.answer("❌ Введите число", reply_markup=get_back_button())

# ==================== РЕФЕРАЛКА ====================

@dp.callback_query(F.data == "invite")
async def invite_friend(callback: CallbackQuery):
    bot_info = await bot.get_me()
    user_id = callback.from_user.id
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
    
    # Получаем статистику
    refs = await db.get_referral_stats(user_id)
    
    text = (
        "👥 <b>Приглашайте друзей!</b>\n\n"
        "🎁 <b>Награды:</b>\n"
        "• 50₽ за каждого друга\n"
        "• 10% от пополнений\n\n"
        f"📊 Статистика:\n"
        f"• Приглашено: {refs['count']}\n"
        f"• Заработано: {refs['earned']}₽\n\n"
        f"🔗 <b>Ваша ссылка:</b>\n"
        f"<code>{ref_link}</code>"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

# ==================== ПОДДЕРЖКА ====================

@dp.callback_query(F.data == "support")
async def support_menu(callback: CallbackQuery):
    text = (
        "🆘 <b>Поддержка 24/7</b>\n\n"
        "⏱️ Среднее время ответа: 5 минут\n\n"
        "💬 <a href='https://t.me/support_username'>Написать в поддержку</a>"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 FAQ", callback_data="faq")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()

@dp.callback_query(F.data == "faq")
async def show_faq(callback: CallbackQuery):
    text = (
        "📚 <b>FAQ:</b>\n\n"
        "<b>Какой протокол?</b>\n"
        "VLESS + XTLS-Reality - самый быстрый\n\n"
        "<b>Сколько устройств?</b>\n"
        "До 5 одновременно\n\n"
        "<b>Не подключается?</b>\n"
        "1. Проверьте срок подписки\n"
        "2. Обновите конфиг в приложении\n"
        "3. Напишите в поддержку"
    )
    await callback.message.edit_text(text, reply_markup=get_back_button(), parse_mode="HTML")
    await callback.answer()

# ==================== АДМИН-ПАНЕЛЬ ====================

@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return
    
    await callback.message.edit_text(
        "🔧 <b>Админ-панель</b>",
        reply_markup=get_admin_menu(),
        parse_mode="HTML"
    )
    await callback.answer()

@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    stats = await db.get_stats()
    
    text = (
        "📊 <b>Статистика:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"✅ Активных подписок: {stats['active_subs']}\n"
        f"💰 Продажи сегодня: {stats['today_sales']}₽\n"
        f"💰 Продажи всего: {stats['total_sales']}₽"
    )
    await callback.message.edit_text(text, reply_markup=get_admin_menu(), parse_mode="HTML")
    await callback.answer()

# ==================== ФОНОВЫЕ ЗАДАЧИ ====================

async def check_expired_subscriptions():
    """Проверка и отключение истёкших подписок"""
    while True:
        try:
            expired = await db.get_expired_subscriptions()
            for sub in expired:
                # Отключаем в 3X-UI
                await xray.disable_client(sub['client_id'])
                await db.update_subscription_status(sub['user_id'], 'expired')
                logging.info(f"Disabled expired subscription for user {sub['user_id']}")
            
            await asyncio.sleep(3600)  # Проверка каждый час
        except Exception as e:
            logging.error(f"Error in check_expired_subscriptions: {e}")
            await asyncio.sleep(3600)

# ==================== ЗАПУСК ====================

async def main():
    # Инициализация БД
    await db.init()
    
    # Запуск фоновой задачи проверки подписок
    asyncio.create_task(check_expired_subscriptions())
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
2. database.py - Управление подписками
Python
Copy
import aiosqlite
from datetime import datetime, timedelta
from typing import Optional, Dict, List

class Database:
    def __init__(self, db_path: str = "vpn_bot.db"):
        self.db_path = db_path
    
    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Пользователи
            await db.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance INTEGER DEFAULT 0,
                    language TEXT DEFAULT 'ru',
                    referred_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Подписки (связь с client_id в 3X-UI)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS subscriptions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    client_id TEXT UNIQUE,  -- ID в 3X-UI
                    config_link TEXT,       -- Ссылка на конфиг
                    expiry_date TIMESTAMP,
                    status TEXT DEFAULT 'active',  -- active, expired, disabled
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Платежи
            await db.execute("""
                CREATE TABLE IF NOT EXISTS payments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount INTEGER,
                    months INTEGER,
                    method TEXT,
                    status TEXT DEFAULT 'pending',  -- pending, completed, cancelled
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id)
                )
            """)
            
            # Рефералы
            await db.execute("""
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER,
                    referred_id INTEGER,
                    reward INTEGER DEFAULT 50,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            await db.commit()
    
    async def add_user(self, user_id: int, username: str, referred_by: Optional[int] = None):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                    (user_id, username, referred_by)
                )
                if referred_by:
                    await db.execute(
                        "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                        (referred_by, user_id)
                    )
                    # Начисляем бонус
                    await db.execute(
                        "UPDATE users SET balance = balance + 50 WHERE user_id = ?",
                        (referred_by,)
                    )
                await db.commit()
            except Exception as e:
                print(f"Error adding user: {e}")
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users WHERE user_id = ?", (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def create_subscription(self, user_id: int, client_id: str, config_link: str, expiry_date: datetime):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO subscriptions 
                   (user_id, client_id, config_link, expiry_date, status) 
                   VALUES (?, ?, ?, ?, 'active')""",
                (user_id, client_id, config_link, expiry_date)
            )
            await db.commit()
    
    async def get_user_config(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def update_subscription(self, user_id: int, client_id: str, expiry_date: datetime, status: str = 'active'):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subscriptions SET expiry_date = ?, status = ? WHERE user_id = ? AND client_id = ?",
                (expiry_date, status, user_id, client_id)
            )
            await db.commit()
    
    async def update_subscription_status(self, user_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subscriptions SET status = ? WHERE user_id = ?",
                (status, user_id)
            )
            await db.commit()
    
    async def get_expired_subscriptions(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM subscriptions 
                   WHERE expiry_date < ? AND status = 'active'""",
                (datetime.now(),)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
    
    async def create_payment(self, user_id: int, amount: int, months: int, method: str) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO payments (user_id, amount, months, method) VALUES (?, ?, ?, ?)",
                (user_id, amount, months, method)
            )
            await db.commit()
            return cursor.lastrowid
    
    async def get_payment(self, payment_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE id = ?", (payment_id,)
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None
    
    async def update_payment_status(self, payment_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE payments SET status = ? WHERE id = ?",
                (status, payment_id)
            )
            await db.commit()
    
    async def get_referral_stats(self, user_id: int) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute(
                "SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (user_id,)
            ) as cursor:
                count = (await cursor.fetchone())[0]
            
            async with db.execute(
                "SELECT COALESCE(SUM(reward), 0) FROM referrals WHERE referrer_id = ?",
                (user_id,)
            ) as cursor:
                earned = (await cursor.fetchone())[0]
            
            return {"count": count, "earned": earned}
    
    async def get_stats(self) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]
            
            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expiry_date > ?",
                (datetime.now(),)
            ) as cursor:
                active_subs = (await cursor.fetchone())[0]
            
            today = datetime.now().replace(hour=0, minute=0, second=0)
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'completed' AND created_at > ?",
                (today,)
            ) as cursor:
                today_sales = (await cursor.fetchone())[0]
            
            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'completed'"
            ) as cursor:
                total_sales = (await cursor.fetchone())[0]
            
            return {
                "total_users": total_users,
                "active_subs": active_subs,
                "today_sales": today_sales,
                "total_sales": total_sales
            }
3. xray_manager.py - Интеграция с 3X-UI
Python
Copy
import aiohttp
import json
import base64
import uuid
from datetime import datetime
from typing import Optional, Dict

class XrayManager:
    def __init__(self, panel_url: str, username: str, password: str):
        self.panel_url = panel_url.rstrip('/')
        self.username = username
        self.password = password
        self.session_cookie = None
        self.inbound_id = 1  # ID inbound в 3X-UI (обычно 1)
    
    async def _login(self) -> bool:
        """Авторизация в панели 3X-UI"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.panel_url}/login",
                    data={"username": self.username, "password": self.password}
                ) as resp:
                    if resp.status == 200:
                        self.session_cookie = resp.cookies.get('session').value
                        return True
                    return False
        except Exception as e:
            print(f"Login error: {e}")
            return False
    
    async def _api_request(self, method: str, endpoint: str, data: Optional[Dict] = None) -> Optional[Dict]:
        """API запрос к панели"""
        if not self.session_cookie:
            if not await self._login():
                return None
        
        headers = {"Content-Type": "application/json"}
        cookies = {"session": self.session_cookie}
        
        try:
            async with aiohttp.ClientSession() as session:
                url = f"{self.panel_url}/panel/api/{endpoint}"
                
                if method == "GET":
                    async with session.get(url, headers=headers, cookies=cookies) as resp:
                        return await resp.json()
                elif method == "POST":
                    async with session.post(url, json=data, headers=headers, cookies=cookies) as resp:
                        return await resp.json()
        except Exception as e:
            print(f"API request error: {e}")
            return None
    
    async def create_client(self, email: str, expiry_date: datetime) -> Optional[Dict]:
        """
        Создание нового клиента в 3X-UI
        Возвращает client_id и ссылку на конфиг
        """
        client_id = str(uuid.uuid4())
        
        # Конвертируем дату в timestamp (миллисекунды)
        expiry_timestamp = int(expiry_date.timestamp() * 1000)
        
        client_data = {
            "id": self.inbound_id,
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "flow": "xtls-rprx-vision",
                    "email": email,
                    "limitIp": 5,  # Макс. 5 устройств
                    "totalGB": 0,  # 0 = безлимит
                    "expiryTime": expiry_timestamp,
                    "enable": True,
                    "tgId": "",
                    "subId": ""
                }]
            })
        }
        
        result = await self._api_request("POST", "inbounds/addClient", client_data)
        
        if result and result.get("success"):
            # Получаем ссылку на подписку
            sub_link = await self._get_subscription_link(client_id, email)
            
            return {
                "id": client_id,
                "email": email,
                "config_link": sub_link
            }
        return None
    
    async def update_client_expiry(self, client_id: str, new_expiry: datetime, enable: bool = True) -> bool:
        """
        Обновление срока действия клиента (продление)
        Включает клиента если он был отключен
        """
        expiry_timestamp = int(new_expiry.timestamp() * 1000)
        
        # Получаем текущие данные клиента
        client_data = await self._get_client_data(client_id)
        if not client_data:
            return False
        
        update_data = {
            "id": self.inbound_id,
            "settings": json.dumps({
                "clients": [{
                    "id": client_id,
                    "flow": client_data.get("flow", "xtls-rprx-vision"),
                    "email": client_data.get("email", ""),
                    "limitIp": client_data.get("limitIp", 5),
                    "totalGB": client_data.get("totalGB", 0),
                    "expiryTime": expiry_timestamp,
                    "enable": enable,
                    "tgId": client_data.get("tgId", ""),
                    "subId": client_data.get("subId", "")
                }]
            })
        }
        
        result = await self._api_request("POST", "inbounds/updateClient/" + client_id, update_data)
        return result and result.get("success")
    
    async def disable_client(self, client_id: str) -> bool:
        """Отключение клиента (истечение подписки)"""
        client_data = await self._get_client_data(client_id)
        if not client_data:
            return False
        
        client_data["enable"] = False
        
        update_data = {
            "id": self.inbound_id,
            "settings": json.dumps({"clients": [client_data]})
        }
        
        result = await self._api_request("POST", "inbounds/updateClient/" + client_id, update_data)
        return result and result.get("success")
    
    async def _get_client_data(self, client_id: str) -> Optional[Dict]:
        """Получение данных клиента из панели"""
        result = await self._api_request("GET", f"inbounds/get/{self.inbound_id}")
        if result and result.get("success"):
            settings = json.loads(result["obj"]["settings"])
            for client in settings.get("clients", []):
                if client["id"] == client_id:
                    return client
        return None
    
    async def _get_subscription_link(self, client_id: str, email: str) -> str:
        """Генерация ссылки на подписку"""
        # Ссылка для импорта в приложения
        # Формат: vless://uuid@server:port?params#remark
        
        # Получаем настройки inbound
        result = await self._api_request("GET", f"inbounds/get/{self.inbound_id}")
        if not result or not result.get("success"):
            return "Ошибка генерации ссылки"
        
        inbound = result["obj"]
        stream_settings = json.loads(inbound.get("streamSettings", "{}"))
        
        # Параметры подключения (замените на свои)
        server = "your-server.com"  # Домен или IP сервера
        port = inbound.get("port", 443)
        protocol = inbound.get("protocol", "vless")
        
        # Параметры безопасности
        security = stream_settings.get("security", "tls")
        network = stream_settings.get("network", "tcp")
        
        # Формируем ссылку VLESS
        if protocol == "vless":
            params = f"type={network}&security={security}"
            if security == "tls" or security == "xtls":
                params += f"&sni={server}"
            
            config = f"{protocol}://{client_id}@{server}:{port}?{params}#{email}"
            return config
        
        return "Неподдерживаемый протокол"
    
    async def get_traffic_stats(self, client_id: str) -> Dict:
        """Получение статистики трафика клиента"""
        result = await self._api_request("GET", f"inbounds/getClientTraffics/{self.inbound_id}")
        if result and result.get("success"):
            for traffic in result.get("obj", []):
                if traffic.get("id") == client_id:
                    return {
                        "up": traffic.get("up", 0),
                        "down": traffic.get("down", 0),
                        "total": traffic.get("total", 0)
                    }
        return {"up": 0, "down": 0, "total": 0}
4. config.py - Конфигурация
Python
Copy
import os

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# 3X-UI Panel
XRAY_PANEL_URL = os.getenv("XRAY_PANEL_URL", "http://localhost:2053")
XRAY_PANEL_USER = os.getenv("XRAY_PANEL_USER", "admin")
XRAY_PANEL_PASS = os.getenv("XRAY_PANEL_PASS", "admin")

# Database
DATABASE_PATH = os.getenv("DATABASE_PATH", "vpn_bot.db")

# Payments (заглушки для примера)
PAYMENT_PROVIDERS = {
    "card": {"api_key": os.getenv("CARD_API_KEY", "")},
    "crypto": {"api_key": os.getenv("CRYPTO_API_KEY", "")},
    "stars": {"token": BOT_TOKEN}
}
5. deploy/install.sh - Автоустановка сервера
bash
Copy
#!/bin/bash

# Автоматическая установка Xray + 3X-UI + VPN Bot
# Запуск: curl -fsSL https://your-domain.com/install.sh | bash

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}=== Xray VPN Server Auto-Installer ===${NC}"

# Проверка root
if [ "$EUID" -ne 0 ]; then 
    echo -e "${RED}Запустите от root: sudo bash install.sh${NC}"
    exit 1
fi

# Ввод данных
read -p "Домен (или IP): " DOMAIN
read -p "Email для SSL: " EMAIL
read -p "Пароль для 3X-UI: " UI_PASSWORD
read -p "Bot Token: " BOT_TOKEN
read -p "Admin ID (Telegram): " ADMIN_ID

echo -e "${YELLOW}Установка зависимостей...${NC}"
apt-get update
apt-get install -y docker.io docker-compose git curl socat

# Настройка Docker
systemctl enable docker
systemctl start docker

# Создание директорий
mkdir -p /opt/vpn-bot
cd /opt/vpn-bot

# SSL сертификат (если домен, не IP)
if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${YELLOW}Используется IP, SSL не будет настроен${NC}"
    USE_SSL=false
else
    echo -e "${YELLOW}Получение SSL сертификата...${NC}"
    curl https://get.acme.sh | sh
    ~/.acme.sh/acme.sh --register-account -m "$EMAIL"
    ~/.acme.sh/acme.sh --issue -d "$DOMAIN" --standalone
    USE_SSL=true
fi

# Docker Compose для 3X-UI
cat > docker-compose.yml <<EOF
version: '3'

services:
  3x-ui:
    image: ghcr.io/mhsanaei/3x-ui:latest
    container_name: 3x-ui
    hostname: 3x-ui
    volumes:
      - ./db/:/etc/x-ui/
      - ./cert/:/root/cert/
    environment:
      XRAY_VMESS_AEAD_FORCED: "false"
    tty: true
    network_mode: host
    restart: unless-stopped
    
  vpn-bot:
    build: ./bot
    container_name: vpn-bot
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - ADMIN_IDS=${ADMIN_ID}
      - XRAY_PANEL_URL=http://localhost:2053
      - XRAY_PANEL_USER=admin
      - XRAY_PANEL_PASS=${UI_PASSWORD}
    volumes:
      - ./bot-data:/app/data
    restart: unless-stopped
    depends_on:
      - 3x-ui
EOF

# Создание Dockerfile для бота
mkdir -p bot
cat > bot/Dockerfile <<EOF
FROM python:3.11-slim

WORKDIR /app

RUN pip install aiogram aiosqlite aiohttp

COPY . .

CMD ["python", "bot.py"]
EOF

# Копирование файлов бота
cp /path/to/bot.py bot/
cp /path/to/database.py bot/
cp /path/to/xray_manager.py bot/
cp /path/to/config.py bot/

# Запуск
echo -e "${YELLOW}Запуск сервисов...${NC}"
docker-compose up -d

# Настройка 3X-UI
echo -e "${YELLOW}Ожидание запуска 3X-UI...${NC}"
sleep 10

# Смена пароля через API (или вручную)
echo -e "${GREEN}=== Установка завершена! ===${NC}"
echo -e "3X-UI: http://${DOMAIN}:2053"
echo -e "Логин: admin"
echo -e "Пароль: ${UI_PASSWORD}"
echo -e ""
echo -e "${YELLOW}Важно:${NC}"
echo -e "1. Зайдите в 3X-UI и настройте Inbound (VLESS + XTLS-Reality)"
echo -e "2. Проверьте статус бота: docker logs vpn-bot"
echo -e "3. Настройте автобэкап: docker exec 3x-ui x-ui backup"

# Создание скрипта обновления
cat > /opt/vpn-bot/update.sh <<'EOF'
#!/bin/bash
cd /opt/vpn-bot
docker-compose pull
docker-compose up -d
docker system prune -f
EOF
chmod +x /opt/vpn-bot/update.sh

# Cron для автобэкапа и проверки
(crontab -l 2>/dev/null; echo "0 3 * * * /opt/vpn-bot/update.sh >> /var/log/vpn-update.log 2>&1") | crontab -
6. deploy/docker-compose.yml (отдельно)
yaml
Copy
version: '3.8'

services:
  3x-ui:
    image: ghcr.io/mhsanaei/3x-ui:latest
    container_name: 3x-ui
    hostname: your-hostname
    volumes:
      - $PWD/db/:/etc/x-ui/
      - $PWD/cert/:/root/cert/
    environment:
      XRAY_VMESS_AEAD_FORCED: "false"
      XUI_LOG_LEVEL: "info"
      XUI_DEBUG: "false"
    network_mode: host
    restart: unless-stopped
    
  vpn-bot:
    build: 
      context: ../
      dockerfile: deploy/Dockerfile.bot
    container_name: vpn-bot
    environment:
      - BOT_TOKEN=${BOT_TOKEN}
      - ADMIN_IDS=${ADMIN_IDS}
      - XRAY_PANEL_URL=http://localhost:2053
      - XRAY_PANEL_USER=${UI_USER:-admin}
      - XRAY_PANEL_PASS=${UI_PASS:-admin}
      - DATABASE_PATH=/app/data/vpn_bot.db
    volumes:
      - bot-data:/app/data
    restart: unless-stopped
    depends_on:
      - 3x-ui

volumes:
  bot-data:
7. requirements.txt
plain
Copy
aiogram==3.4.1
aiosqlite==0.20.0
aiohttp==3.9.3
python-dotenv==1.0.1
Ключевые особенности реализации:
🔑 Управление подписками:
При первой покупке создаётся новый клиент в 3X-UI
При продлении обновляется только expiryTime, конфиг не меняется
Автоотключение по истечении срока (фоновая задача каждый час)
🔄 Автоматизация 3X-UI:
Создание клиентов через API
Обновление срока без смены UUID
Включение/отключение клиентов
Получение статистики трафика
🛡️ Безопасность:
Один конфиг = один пользователь
Лимит 5 устройств (limitIp)
Привязка к Telegram ID