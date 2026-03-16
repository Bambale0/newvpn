#!/bin/bash

# VPN Bot Restart Script
# Usage: ./restart.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== VPN Bot Restart Script ===${NC}"

# Stop the bot
echo -e "${YELLOW}Stopping bot...${NC}"
if [ -f "stop.sh" ]; then
    bash stop.sh
else
    echo -e "${RED}stop.sh not found!${NC}"
    exit 1
fi

# Wait a moment
sleep 2

# Start the bot
echo -e "${YELLOW}Starting bot...${NC}"
if [ -f "start.sh" ]; then
    bash start.sh
else
    echo -e "${RED}start.sh not found!${NC}"
    exit 1
fi

echo -e "${GREEN}=== Bot restarted successfully! ===${NC}"