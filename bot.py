import asyncio
import logging
import ssl
from datetime import datetime, timedelta

import aiohttp
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from aiohttp import web

from config import (
    ADMIN_IDS,
    BOT_TOKEN,
    WEBHOOK_PATH,
    WEBHOOK_URL,
    XRAY_PANEL_PASS,
    XRAY_PANEL_URL,
    XRAY_PANEL_USER,
)
from database import Database
from xray_manager import XrayManager

logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)

# Веб-сервер для webhook
app = web.Application()
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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="💳 Купить Подписку", callback_data="buy_sub"),
                InlineKeyboardButton(text="🌐 Подключиться", callback_data="connect"),
            ],
            [
                InlineKeyboardButton(text="💰 Пополнить баланс", callback_data="top_up"),
                InlineKeyboardButton(text="👥 Пригласить друга", callback_data="invite"),
            ],
            [
                InlineKeyboardButton(text="📈 Мой профиль", callback_data="profile"),
                InlineKeyboardButton(text="🆘 Поддержка", callback_data="support"),
            ],
            [InlineKeyboardButton(text="🌍 Сменить язык", callback_data="change_lang")],
        ]
    )
    if is_admin:
        keyboard.inline_keyboard.append(
            [InlineKeyboardButton(text="🔧 Админ-панель", callback_data="admin_panel")]
        )
    return keyboard


def get_subscription_menu():
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="1 мес - 299₽", callback_data="sub_1_299"),
                InlineKeyboardButton(text="3 мес - 799₽", callback_data="sub_3_799"),
            ],
            [
                InlineKeyboardButton(text="6 мес - 1499₽", callback_data="sub_6_1499"),
                InlineKeyboardButton(
                    text="12 мес - 2799₽", callback_data="sub_12_2799"
                ),
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )
    return keyboard


def get_payment_methods():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 Карта", callback_data="pay_card")],
            [InlineKeyboardButton(text="₿ Крипта", callback_data="pay_crypto")],
            [InlineKeyboardButton(text="💎 Telegram Stars", callback_data="pay_stars")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_sub")],
        ]
    )


def get_topup_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="100₽", callback_data="topup_100"),
                InlineKeyboardButton(text="300₽", callback_data="topup_300"),
                InlineKeyboardButton(text="500₽", callback_data="topup_500"),
            ],
            [
                InlineKeyboardButton(text="1000₽", callback_data="topup_1000"),
                InlineKeyboardButton(text="2000₽", callback_data="topup_2000"),
                InlineKeyboardButton(text="5000₽", callback_data="topup_5000"),
            ],
            [InlineKeyboardButton(text="💰 Своя сумма", callback_data="topup_custom")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_connect_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Android", callback_data="os_android")],
            [InlineKeyboardButton(text="🍎 iOS", callback_data="os_ios")],
            [InlineKeyboardButton(text="💻 Windows", callback_data="os_windows")],
            [InlineKeyboardButton(text="🐧 Linux", callback_data="os_linux")],
            [InlineKeyboardButton(text="🍏 macOS", callback_data="os_macos")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_profile_menu(has_active=False):
    buttons = []
    if has_active:
        buttons.append(
            [InlineKeyboardButton(text="📋 Мои конфиги", callback_data="my_configs")]
        )
        buttons.append(
            [InlineKeyboardButton(text="🔄 Продлить", callback_data="buy_sub")]
        )
    else:
        buttons.append(
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_sub")]
        )
    buttons.append(
        [InlineKeyboardButton(text="📜 История", callback_data="payment_history")]
    )
    buttons.append(
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def get_admin_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
            [InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast")],
            [InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users")],
            [
                InlineKeyboardButton(
                    text="➕ Добавить подписку", callback_data="admin_add_sub"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )


def get_admin_stats_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📈 Детальная статистика", callback_data="admin_detailed_stats"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")],
        ]
    )


def get_admin_users_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📋 Список пользователей", callback_data="admin_users_list"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔍 Поиск пользователя", callback_data="admin_user_search"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")],
        ]
    )


def get_admin_broadcast_menu():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 Начать рассылку", callback_data="admin_broadcast_start"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_panel")],
        ]
    )


def get_back_button():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")]
        ]
    )


# ==================== ОБРАБОТЧИКИ ====================


@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username

    # Проверка на реферальную ссылку
    referred_by = None
    if message.text and len(message.text.split()) > 1:
        try:
            referred_by = int(message.text.split()[1])
        except ValueError:
            pass

    # Регистрация пользователя
    await db.add_user(user_id, username, referred_by)

    is_admin = user_id in ADMIN_IDS
    welcome = (
        "👋 <b>Добро пожаловать в Xray VPN!</b>\n\n"
        "🚀 Быстрые Xray-конфиги для обхода блокировок\n"
        "⚡ Высокая скорость и стабильность\n"
        "🌍 Серверы по всему миру\n\n"
        "Выберите действие:"
    )
    await message.answer(
        welcome, reply_markup=get_main_menu(is_admin), parse_mode="HTML"
    )


@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: CallbackQuery):
    is_admin = callback.from_user.id in ADMIN_IDS
    await callback.message.edit_text(
        "👋 <b>Главное меню</b>\n\nВыберите действие:",
        reply_markup=get_main_menu(is_admin),
        parse_mode="HTML",
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
        text += (
            "⚠️ У вас уже есть конфиг. После оплаты срок действия будет продлён!\n\n"
        )

    text += (
        "✅ Неограниченный трафик\n"
        "✅ До 5 устройств\n"
        "✅ Поддержка 24/7\n"
        "✅ Автоматическая выдача"
    )
    await callback.message.edit_text(
        text, reply_markup=get_subscription_menu(), parse_mode="HTML"
    )
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
    await callback.message.edit_text(
        text, reply_markup=get_payment_methods(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("pay_"))
async def process_payment(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    price = data.get("price")
    months = data.get("months")
    method = callback.data.split("_")[1]

    # Создаём платёж в БД
    payment_id = await db.create_payment(callback.from_user.id, price, months, method)

    methods = {
        "card": "Банковская карта",
        "crypto": "Криптовалюта",
        "stars": "Telegram Stars",
    }

    text = (
        f"💳 <b>Оплата через {methods.get(method)}</b>\n\n"
        f"Сумма: <b>{price}₽</b>\n"
        f"ID платежа: <code>{payment_id}</code>\n\n"
        f"⚠️ После оплаты нажмите кнопку ниже.\n"
        f"Конфиг будет автоматически создан или продлён."
    )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"✅ Я оплатил {price}₽",
                    callback_data=f"confirm_pay_{payment_id}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="buy_sub")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await callback.answer()


@dp.callback_query(F.data.startswith("confirm_pay_"))
async def confirm_payment(callback: CallbackQuery, state: FSMContext):
    payment_id = int(callback.data.split("_")[2])
    user_id = callback.from_user.id

    # Проверяем платёж
    payment = await db.get_payment(payment_id)
    if not payment or payment["status"] != "pending":
        await callback.answer("❌ Платёж не найден или уже обработан!", show_alert=True)
        return

    # Помечаем как оплаченный (в реальности тут проверка от платёжки)
    await db.update_payment_status(payment_id, "completed")

    months = payment["months"]
    days = months * 30

    # Проверяем, есть ли у пользователя уже конфиг в 3X-UI
    existing_client = await db.get_user_config(user_id)

    if existing_client:
        # ПРОДЛЕВАЕМ СУЩЕСТВУЮЩИЙ КОНФИГ
        client_id = existing_client["client_id"]

        # Получаем текущую дату окончания или сегодня
        current_expiry = existing_client["expiry_date"]
        if current_expiry and current_expiry > datetime.now():
            new_expiry = current_expiry + timedelta(days=days)
        else:
            new_expiry = datetime.now() + timedelta(days=days)

        # Обновляем в 3X-UI (включаем если был выключен)
        success = await xray.update_client_expiry(client_id, new_expiry, enable=True)

        if success:
            await db.update_subscription(
                user_id, client_id, new_expiry, status="active"
            )

            # Получаем конфиг для показа
            config_link = existing_client["config_link"]

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
            await db.create_subscription(
                user_id, client["id"], client["config_link"], expiry
            )

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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📱 Как подключиться", callback_data="connect")],
            [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_to_menu")],
        ]
    )

    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()
    await callback.answer("✅ Успешно!")


# ==================== ПРОФИЛЬ ====================


@dp.callback_query(F.data == "profile")
async def show_profile(callback: CallbackQuery):
    user_id = callback.from_user.id
    user = await db.get_user(user_id)
    sub = await db.get_user_config(user_id)

    balance = user["balance"] if user else 0

    text = (
        "📈 <b>Мой профиль</b>\n\n"
        f"👤 ID: <code>{user_id}</code>\n"
        f"💰 Баланс: <b>{balance}₽</b>\n"
    )

    has_active = False
    if sub:
        expiry = sub["expiry_date"]
        is_active = expiry > datetime.now() and sub["status"] == "active"

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

    await callback.message.edit_text(
        text, reply_markup=get_profile_menu(has_active), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "my_configs")
async def show_configs(callback: CallbackQuery):
    user_id = callback.from_user.id
    sub = await db.get_user_config(user_id)

    if not sub:
        text = "📋 У вас пока нет конфигов"
    else:
        expiry = sub["expiry_date"]
        status = "✅ Активен" if expiry > datetime.now() else "❌ Истёк"

        text = (
            "📋 <b>Ваш конфиг:</b>\n\n"
            f"Статус: {status}\n"
            f"До: {expiry.strftime('%d.%m.%Y')}\n\n"
            f"<code>{sub['config_link']}</code>\n\n"
            "⚠️ Не передавайте конфиг третьим лицам!"
        )

    await callback.message.edit_text(
        text, reply_markup=get_back_button(), parse_mode="HTML"
    )
    await callback.answer()


# ==================== ПОДКЛЮЧЕНИЕ ====================


@dp.callback_query(F.data == "connect")
async def connect_menu(callback: CallbackQuery):
    text = "🌐 <b>Выберите платформу:</b>"
    await callback.message.edit_text(
        text, reply_markup=get_connect_menu(), parse_mode="HTML"
    )
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
        ),
    }

    await callback.message.edit_text(
        instructions.get(os_name, "Нет инструкции"),
        reply_markup=get_back_button(),
        parse_mode="HTML",
        disable_web_page_preview=True,
    )
    await callback.answer()


# ==================== ПОПОЛНЕНИЕ ====================


@dp.callback_query(F.data == "top_up")
async def top_up_menu(callback: CallbackQuery):
    text = "💰 <b>Выберите сумму пополнения:</b>"
    await callback.message.edit_text(
        text, reply_markup=get_topup_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("topup_"))
async def process_topup(callback: CallbackQuery, state: FSMContext):
    amount = callback.data.split("_")[1]

    if amount == "custom":
        await state.set_state(TopUpBalance.entering_amount)
        await callback.message.edit_text(
            "💰 Введите сумму (мин. 50₽):", reply_markup=get_back_button()
        )
    else:
        amount_int = int(amount)
        await callback.message.edit_text(
            f"💰 Пополнение на {amount_int}₽\n\nВыберите способ:",
            reply_markup=get_payment_methods(),
            parse_mode="HTML",
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
            parse_mode="HTML",
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

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📤 Поделиться", url=f"https://t.me/share/url?url={ref_link}"
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )

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
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📚 FAQ", callback_data="faq")],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_menu")],
        ]
    )
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
    await callback.message.edit_text(
        text, reply_markup=get_back_button(), parse_mode="HTML"
    )
    await callback.answer()


# ==================== АДМИН-ПАНЕЛЬ ====================


@dp.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await callback.message.edit_text(
        "🔧 <b>Админ-панель</b>", reply_markup=get_admin_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_stats")
async def admin_stats(callback: CallbackQuery):
    stats = await db.get_stats()
    traffic = await db.get_traffic_stats()

    text = (
        "📊 <b>Основная статистика:</b>\n\n"
        f"👥 Всего пользователей: {stats['total_users']}\n"
        f"✅ Активных подписок: {stats['active_subs']}\n"
        f"❌ Неактивных подписок: {stats['inactive_subs']}\n"
        f"🔑 Выданных конфигов: {stats['total_configs']}\n\n"
        f"💰 <b>Выручка:</b>\n"
        f"• Сегодня: {stats['today_sales']}₽\n"
        f"• Вчера: {stats['yesterday_sales']}₽\n"
        f"• Всего: {stats['total_sales']}₽\n\n"
        f"📈 <b>Трафик:</b>\n"
        f"• Входящий: {traffic['total_up_gb']:.2f} GB\n"
        f"• Исходящий: {traffic['total_down_gb']:.2f} GB\n"
        f"• Общий: {traffic['total_gb']:.2f} GB"
    )
    await callback.message.edit_text(
        text, reply_markup=get_admin_stats_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_detailed_stats")
async def admin_detailed_stats(callback: CallbackQuery):
    stats = await db.get_stats()
    recent_users = await db.get_recent_users(5)
    recent_payments = await db.get_recent_payments(5)

    text = "📈 <b>Детальная статистика</b>\n\n"

    # Основная статистика
    text += (
        f"👥 Пользователи: {stats['total_users']}\n"
        f"✅ Активные подписки: {stats['active_subs']}\n"
        f"❌ Неактивные: {stats['inactive_subs']}\n"
        f"🔑 Конфиги: {stats['total_configs']}\n\n"
    )

    # Финансы
    text += (
        f"💰 <b>Финансы:</b>\n"
        f"Сегодня: {stats['today_sales']}₽\n"
        f"Вчера: {stats['yesterday_sales']}₽\n"
        f"Всего: {stats['total_sales']}₽\n\n"
    )

    # Новые пользователи
    text += "🆕 <b>Последние пользователи:</b>\n"
    for user in recent_users:
        text += f"• @{user['username'] or 'N/A'} (ID: {user['user_id']})\n"
    text += "\n"

    # Последние платежи
    text += "💳 <b>Последние платежи:</b>\n"
    for payment in recent_payments:
        text += f"• {payment['amount']}₽ (ID: {payment['user_id']})\n"

    await callback.message.edit_text(
        text, reply_markup=get_admin_stats_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await callback.message.edit_text(
        "📢 <b>Рассылка сообщений</b>\n\n" "Выберите действие:",
        reply_markup=get_admin_broadcast_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_broadcast_start")
async def admin_broadcast_start(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.set_state(AdminState.broadcast)
    await callback.message.edit_text(
        "📢 <b>Рассылка</b>\n\n"
        "Отправьте сообщение для рассылки всем пользователям.\n"
        "Поддерживается HTML разметка.\n\n"
        "Для отмены нажмите кнопку ниже:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="admin_broadcast_cancel"
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(AdminState.broadcast)
async def process_broadcast(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    broadcast_text = message.text or message.caption or ""
    if not broadcast_text:
        await message.answer("❌ Отправьте текстовое сообщение!")
        return

    # Получаем всех пользователей
    users = await db.get_all_users(limit=1000)  # Ограничение для безопасности

    sent_count = 0
    failed_count = 0

    status_msg = await message.answer("📢 Начинаю рассылку...")

    for user in users:
        try:
            await bot.send_message(
                chat_id=user["user_id"], text=broadcast_text, parse_mode="HTML"
            )
            sent_count += 1

            # Обновляем статус каждые 10 сообщений
            if sent_count % 10 == 0:
                await status_msg.edit_text(
                    f"📢 Рассылка...\n"
                    f"Отправлено: {sent_count}\n"
                    f"Осталось: {len(users) - sent_count}"
                )

        except Exception as e:
            failed_count += 1
            logging.error(f"Failed to send to user {user['user_id']}: {e}")

    await status_msg.edit_text(
        f"✅ <b>Рассылка завершена!</b>\n\n"
        f"📤 Отправлено: {sent_count}\n"
        f"❌ Ошибок: {failed_count}",
        reply_markup=get_admin_broadcast_menu(),
        parse_mode="HTML",
    )

    await state.clear()


@dp.callback_query(F.data == "admin_broadcast_cancel")
async def admin_broadcast_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ Рассылка отменена",
        reply_markup=get_admin_broadcast_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_users")
async def admin_users_menu(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await callback.message.edit_text(
        "👥 <b>Управление пользователями</b>\n\n" "Выберите действие:",
        reply_markup=get_admin_users_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_users_list")
async def admin_users_list(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    users = await db.get_all_users(limit=20)

    text = "👥 <b>Список пользователей</b>\n\n"

    for user in users:
        sub_info = await db.get_user_subscription_details(user["user_id"])
        if sub_info:
            status = (
                "✅ Активна" if sub_info["expiry_date"] > datetime.now() else "❌ Истекла"
            )
            text += f"👤 @{user['username'] or 'N/A'} (ID: {user['user_id']})\n"
            text += f"💰 Баланс: {user['balance']}₽ | Подписка: {status}\n\n"
        else:
            text += f"👤 @{user['username'] or 'N/A'} (ID: {user['user_id']})\n"
            text += f"💰 Баланс: {user['balance']}₽ | Подписка: Нет\n\n"

    await callback.message.edit_text(
        text, reply_markup=get_admin_users_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_user_search")
async def admin_user_search(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.set_state(AdminState.add_days)
    await callback.message.edit_text(
        "🔍 <b>Поиск пользователя</b>\n\n" "Отправьте ID пользователя или @username:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="admin_user_search_cancel"
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.message(AdminState.add_days)
async def process_user_search(message: Message, state: FSMContext):
    if message.from_user.id not in ADMIN_IDS:
        return

    search_term = message.text.strip()

    # Определяем, ID или username
    if search_term.startswith("@"):
        username = search_term[1:]
        # Ищем по username (примерный поиск)
        users = await db.get_all_users(limit=1000)
        found_users = [
            u
            for u in users
            if u["username"] and username.lower() in u["username"].lower()
        ]
    else:
        try:
            user_id = int(search_term)
            user = await db.get_user(user_id)
            found_users = [user] if user else []
        except ValueError:
            found_users = []

    if not found_users:
        await message.answer(
            "❌ Пользователь не найден", reply_markup=get_admin_users_menu()
        )
        await state.clear()
        return

    # Показываем найденных пользователей
    text = "🔍 <b>Результаты поиска:</b>\n\n"

    for user in found_users[:5]:  # Ограничение 5 результатов
        sub_info = await db.get_user_subscription_details(user["user_id"])
        text += f"👤 @{user['username'] or 'N/A'} (ID: {user['user_id']})\n"
        text += f"💰 Баланс: {user['balance']}₽\n"

        if sub_info:
            status = (
                "✅ Активна" if sub_info["expiry_date"] > datetime.now() else "❌ Истекла"
            )
            text += f"📅 Подписка: {status} до {sub_info['expiry_date'].strftime('%d.%m.%Y')}\n"
            text += f"🔑 Конфиг: <code>{sub_info['config_link'][:50]}...</code>\n"
        else:
            text += "📅 Подписка: Нет\n"

        text += "\n"

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"➕ Добавить подписку {user['user_id']}",
                    callback_data=f"admin_add_sub_{user['user_id']}",
                )
            ],
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_users")],
        ]
    )

    await message.answer(text, reply_markup=keyboard, parse_mode="HTML")
    await state.clear()


@dp.callback_query(F.data == "admin_user_search_cancel")
async def admin_user_search_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ Поиск отменён", reply_markup=get_admin_users_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_add_sub")
async def admin_add_sub_menu(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.set_state(AdminState.add_days)
    await callback.message.edit_text(
        "➕ <b>Добавление подписки</b>\n\n" "Отправьте ID пользователя:",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="❌ Отмена", callback_data="admin_add_sub_cancel"
                    )
                ]
            ]
        ),
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_add_sub_"))
async def admin_add_sub_specific(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    user_id = int(callback.data.split("_")[3])

    # Показываем опции для добавления подписки
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="1 месяц", callback_data=f"admin_confirm_add_{user_id}_1"
                )
            ],
            [
                InlineKeyboardButton(
                    text="3 месяца", callback_data=f"admin_confirm_add_{user_id}_3"
                )
            ],
            [
                InlineKeyboardButton(
                    text="6 месяцев", callback_data=f"admin_confirm_add_{user_id}_6"
                )
            ],
            [
                InlineKeyboardButton(
                    text="12 месяцев", callback_data=f"admin_confirm_add_{user_id}_12"
                )
            ],
            [InlineKeyboardButton(text="❌ Отмена", callback_data="admin_users")],
        ]
    )

    await callback.message.edit_text(
        f"➕ <b>Добавление подписки</b>\n\n"
        f"Пользователь ID: {user_id}\n\n"
        f"Выберите период:",
        reply_markup=keyboard,
        parse_mode="HTML",
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin_confirm_add_"))
async def admin_confirm_add_subscription(callback: CallbackQuery):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    _, _, user_id, months = callback.data.split("_")
    user_id = int(user_id)
    months = int(months)

    # Проверяем пользователя
    user = await db.get_user(user_id)
    if not user:
        await callback.answer("❌ Пользователь не найден!", show_alert=True)
        return

    # Создаем подписку через XrayManager
    days = months * 30
    expiry = datetime.now() + timedelta(days=days)

    existing = await db.get_user_config(user_id)

    if existing:
        # Продлеваем существующую
        client_id = existing["client_id"]
        current_expiry = existing["expiry_date"]
        if current_expiry and current_expiry > datetime.now():
            new_expiry = current_expiry + timedelta(days=days)
        else:
            new_expiry = expiry

        success = await xray.update_client_expiry(client_id, new_expiry, enable=True)

        if success:
            await db.update_subscription(
                user_id, client_id, new_expiry, status="active"
            )
            result_text = (
                f"✅ <b>Подписка продлена!</b>\n\n"
                f"👤 Пользователь: @{user['username'] or 'N/A'} (ID: {user_id})\n"
                f"📅 Новый срок: до {new_expiry.strftime('%d.%m.%Y')}\n"
                f"⏳ Добавлено: {days} дней"
            )
        else:
            result_text = "❌ Ошибка продления подписки"
    else:
        # Создаем новую
        email = f"user_{user_id}_{int(datetime.now().timestamp())}"
        client = await xray.create_client(email, expiry)

        if client:
            await db.create_subscription(
                user_id, client["id"], client["config_link"], expiry
            )
            result_text = (
                f"✅ <b>Подписка создана!</b>\n\n"
                f"👤 Пользователь: @{user['username'] or 'N/A'} (ID: {user_id})\n"
                f"📅 Срок: до {expiry.strftime('%d.%m.%Y')}\n"
                f"🔑 Конфиг создан"
            )
        else:
            result_text = "❌ Ошибка создания подписки"

    await callback.message.edit_text(
        result_text, reply_markup=get_admin_menu(), parse_mode="HTML"
    )
    await callback.answer()


@dp.callback_query(F.data == "admin_cancel_add_sub")
async def admin_add_sub_cancel(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMIN_IDS:
        await callback.answer("❌ Нет доступа!", show_alert=True)
        return

    await state.clear()
    await callback.message.edit_text(
        "❌ Добавление подписки отменено",
        reply_markup=get_admin_menu(),
        parse_mode="HTML",
    )
    await callback.answer()


# ==================== ФОНОВЫЕ ЗАДАЧИ ====================


async def check_expired_subscriptions():
    """Проверка и отключение истёкших подписок"""
    while True:
        try:
            expired = await db.get_expired_subscriptions()
            for sub in expired:
                # Отключаем в 3X-UI
                await xray.disable_client(sub["client_id"])
                await db.update_subscription_status(sub["user_id"], "expired")
                logging.info(f"Disabled expired subscription for user {sub['user_id']}")

            await asyncio.sleep(3600)  # Проверка каждый час
        except Exception as e:
            logging.error(f"Error in check_expired_subscriptions: {e}")
            await asyncio.sleep(3600)


# ==================== WEBHOOK ====================


async def on_webhook(request):
    """Обработка webhook запросов от Telegram"""
    update = await request.json()
    await dp.feed_update(bot=bot, update=types.Update(**update))
    return web.Response(text="OK")


async def set_webhook():
    """Установка webhook"""
    webhook_url = f"{WEBHOOK_URL}{WEBHOOK_PATH}"
    await bot.set_webhook(webhook_url)
    logging.info(f"Webhook установлен: {webhook_url}")


async def delete_webhook():
    """Удаление webhook"""
    await bot.delete_webhook()
    logging.info("Webhook удалён")


# ==================== ЗАПУСК ====================


async def main():
    # Инициализация БД
    await db.init()

    # Удаляем webhook, если он установлен
    await delete_webhook()

    # Запуск фоновой задачи проверки подписок
    asyncio.create_task(check_expired_subscriptions())

    # Используем long polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
