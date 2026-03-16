from datetime import datetime, timedelta
from typing import Dict, List, Optional

import aiosqlite


class Database:
    def __init__(self, db_path: str = "vpn_bot.db"):
        self.db_path = db_path

    async def init(self):
        async with aiosqlite.connect(self.db_path) as db:
            # Пользователи
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    balance INTEGER DEFAULT 0,
                    language TEXT DEFAULT 'ru',
                    referred_by INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            # Подписки (связь с client_id в 3X-UI)
            await db.execute(
                """
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
            """
            )

            # Платежи
            await db.execute(
                """
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
            """
            )

            # Рефералы
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS referrals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    referrer_id INTEGER,
                    referred_id INTEGER,
                    reward INTEGER DEFAULT 50,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """
            )

            await db.commit()

    async def add_user(
        self, user_id: int, username: str, referred_by: Optional[int] = None
    ):
        async with aiosqlite.connect(self.db_path) as db:
            try:
                await db.execute(
                    "INSERT OR IGNORE INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
                    (user_id, username, referred_by),
                )
                if referred_by:
                    await db.execute(
                        "INSERT INTO referrals (referrer_id, referred_id) VALUES (?, ?)",
                        (referred_by, user_id),
                    )
                    # Начисляем бонус
                    await db.execute(
                        "UPDATE users SET balance = balance + 50 WHERE user_id = ?",
                        (referred_by,),
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

    async def create_subscription(
        self, user_id: int, client_id: str, config_link: str, expiry_date: datetime
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                """INSERT OR REPLACE INTO subscriptions 
                   (user_id, client_id, config_link, expiry_date, status) 
                   VALUES (?, ?, ?, ?, 'active')""",
                (user_id, client_id, config_link, expiry_date),
            )
            await db.commit()

    async def get_user_config(self, user_id: int) -> Optional[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM subscriptions WHERE user_id = ? ORDER BY id DESC LIMIT 1",
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def update_subscription(
        self,
        user_id: int,
        client_id: str,
        expiry_date: datetime,
        status: str = "active",
    ):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subscriptions SET expiry_date = ?, status = ? WHERE user_id = ? AND client_id = ?",
                (expiry_date, status, user_id, client_id),
            )
            await db.commit()

    async def update_subscription_status(self, user_id: int, status: str):
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "UPDATE subscriptions SET status = ? WHERE user_id = ?",
                (status, user_id),
            )
            await db.commit()

    async def get_expired_subscriptions(self) -> List[Dict]:
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """SELECT * FROM subscriptions 
                   WHERE expiry_date < ? AND status = 'active'""",
                (datetime.now(),),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def create_payment(
        self, user_id: int, amount: int, months: int, method: str
    ) -> int:
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "INSERT INTO payments (user_id, amount, months, method) VALUES (?, ?, ?, ?)",
                (user_id, amount, months, method),
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
                "UPDATE payments SET status = ? WHERE id = ?", (status, payment_id)
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
                (user_id,),
            ) as cursor:
                earned = (await cursor.fetchone())[0]

            return {"count": count, "earned": earned}

    async def get_stats(self) -> Dict:
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as cursor:
                total_users = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status = 'active' AND expiry_date > ?",
                (datetime.now(),),
            ) as cursor:
                active_subs = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM subscriptions WHERE status != 'active' OR expiry_date <= ?",
                (datetime.now(),),
            ) as cursor:
                inactive_subs = (await cursor.fetchone())[0]

            async with db.execute("SELECT COUNT(*) FROM subscriptions") as cursor:
                total_configs = (await cursor.fetchone())[0]

            today = datetime.now().replace(hour=0, minute=0, second=0)
            yesterday = today - timedelta(days=1)

            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'completed' AND created_at > ?",
                (today,),
            ) as cursor:
                today_sales = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'completed' AND created_at > ? AND created_at <= ?",
                (yesterday, today),
            ) as cursor:
                yesterday_sales = (await cursor.fetchone())[0]

            async with db.execute(
                "SELECT COALESCE(SUM(amount), 0) FROM payments WHERE status = 'completed'"
            ) as cursor:
                total_sales = (await cursor.fetchone())[0]

            return {
                "total_users": total_users,
                "active_subs": active_subs,
                "inactive_subs": inactive_subs,
                "total_configs": total_configs,
                "today_sales": today_sales,
                "yesterday_sales": yesterday_sales,
                "total_sales": total_sales,
            }

    async def get_recent_users(self, limit: int = 5) -> List[Dict]:
        """Получить последних зарегистрированных пользователей"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ?", (limit,)
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_recent_payments(self, limit: int = 5) -> List[Dict]:
        """Получить последние платежи"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM payments WHERE status = 'completed' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_all_users(self, limit: int = 50, offset: int = 0) -> List[Dict]:
        """Получить всех пользователей с пагинацией"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM users ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (limit, offset),
            ) as cursor:
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]

    async def get_user_subscription_details(self, user_id: int) -> Optional[Dict]:
        """Получить детальную информацию о подписке пользователя"""
        async with aiosqlite.connect(self.db_path) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                """
                SELECT s.*, u.username, u.balance
                FROM subscriptions s
                JOIN users u ON s.user_id = u.user_id
                WHERE s.user_id = ?
                ORDER BY s.id DESC LIMIT 1
                """,
                (user_id,),
            ) as cursor:
                row = await cursor.fetchone()
                return dict(row) if row else None

    async def admin_create_subscription(self, user_id: int, months: int) -> bool:
        """Админ: создать или продлить подписку для пользователя"""
        days = months * 30
        expiry = datetime.now() + timedelta(days=days)

        # Проверяем существующую подписку
        existing = await self.get_user_config(user_id)

        if existing:
            # Продлеваем существующую
            client_id = existing["client_id"]
            current_expiry = existing["expiry_date"]
            if current_expiry and current_expiry > datetime.now():
                new_expiry = current_expiry + timedelta(days=days)
            else:
                new_expiry = expiry

            await self.update_subscription(
                user_id, client_id, new_expiry, status="active"
            )
            return True
        else:
            # Создаем новую (нужен XrayManager, но для админ-функции вернем True)
            # Реальная логика должна быть в bot.py с XrayManager
            return False

    async def get_traffic_stats(self) -> Dict:
        """Получить статистику трафика (заглушка, нужна интеграция с XrayManager)"""
        # В реальности нужно получать данные из XrayManager
        return {"total_up_gb": 0.0, "total_down_gb": 0.0, "total_gb": 0.0}
