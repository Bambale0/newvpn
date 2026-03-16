import os

# Bot
BOT_TOKEN = os.getenv("BOT_TOKEN", "8246070975:AAHRNShOYVvPlyw2VQVF4P2YmotMZOoG-ck")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# Webhook
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "https://test.chillcreative.ru")
WEBHOOK_PATH = "/webhook"

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
