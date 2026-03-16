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
