#!/bin/bash
set -eo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 激活虚拟环境（如果存在）
if [ -f ".venv/Scripts/activate" ]; then
    source .venv/Scripts/activate
elif [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

LOG_FILE="$SCRIPT_DIR/logs/gtm_startup.log"
mkdir -p "$SCRIPT_DIR/logs"

echo "Starting Gold Trading Decision System in background (log: $LOG_FILE)..."
nohup python3 main.py "$@" >> "$LOG_FILE" 2>&1 &
echo "PID: $!"
