#!/bin/bash

# VPN Bot Stop Script
# Usage: ./stop.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=== VPN Bot Stop Script ===${NC}"

# Check if running in Docker environment
if [ -f "/.dockerenv" ]; then
    echo -e "${YELLOW}Running inside Docker container${NC}"
    echo -e "${YELLOW}Please use 'docker stop <container_name>' from host${NC}"
    exit 1
fi

# Check for running Python bot process
if pgrep -f "python.*bot.py" > /dev/null; then
    echo -e "${YELLOW}Found running Python bot process${NC}"

    # Get process IDs
    PIDS=$(pgrep -f "python.*bot.py")

    echo -e "${GREEN}Stopping bot processes: ${PIDS}${NC}"

    # Send SIGTERM first
    kill -TERM $PIDS 2>/dev/null || true

    # Wait for graceful shutdown
    for i in {1..10}; do
        if ! pgrep -f "python.*bot.py" > /dev/null; then
            echo -e "${GREEN}Bot stopped gracefully${NC}"
            exit 0
        fi
        echo -e "${YELLOW}Waiting for bot to stop... (${i}/10)${NC}"
        sleep 1
    done

    # Force kill if still running
    if pgrep -f "python.*bot.py" > /dev/null; then
        echo -e "${RED}Force stopping bot...${NC}"
        kill -KILL $PIDS 2>/dev/null || true
        sleep 1
    fi

    if pgrep -f "python.*bot.py" > /dev/null; then
        echo -e "${RED}Failed to stop bot process${NC}"
        exit 1
    else
        echo -e "${GREEN}Bot stopped successfully${NC}"
    fi

else
    echo -e "${YELLOW}No running bot processes found${NC}"
fi

echo -e "${GREEN}=== Bot stop operation completed ===${NC}"