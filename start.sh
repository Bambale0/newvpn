#!/bin/bash

# VPN Bot Start Script
# Usage: ./start.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== VPN Bot Start Script ===${NC}"

# Check if running in Docker environment
if [ -f "/.dockerenv" ]; then
    echo -e "${YELLOW}Running inside Docker container${NC}"
    echo -e "${GREEN}Starting VPN Bot...${NC}"
    python3 bot.py
    exit 0
fi

# Start bot directly with Python
if command -v python3 &> /dev/null; then
    echo -e "${YELLOW}Starting bot directly with Python...${NC}"

    # Check if virtual environment exists
    if [ -d "venv" ]; then
        echo -e "${BLUE}Activating virtual environment...${NC}"
        source venv/bin/activate
    fi

    # Check if required packages are installed
    if ! python3 -c "import aiogram, aiosqlite, aiohttp" 2>/dev/null; then
        echo -e "${YELLOW}Installing dependencies...${NC}"
        pip install -r requirements.txt
    fi

    echo -e "${GREEN}Starting VPN Bot...${NC}"
    python3 bot.py

else
    echo -e "${RED}Error: Python3 not found!${NC}"
    echo -e "${YELLOW}Please install Python3${NC}"
    exit 1
fi

echo -e "${GREEN}=== Bot started successfully! ===${NC}"