#!/bin/bash
# Zeta-Agent Warmup Scheduler Launcher
# This script starts the warmup scheduler in the background

cd "$(dirname "$0")"

echo "Starting Zeta-Agent Warmup Scheduler..."
echo "Schedule: 09:00 and 18:00 daily"
echo "Max runs per day: 2"
echo ""

# Load environment variables
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Check if credentials are set
if [ -z "$REDDIT_USERNAME" ] || [ -z "$REDDIT_PASSWORD" ]; then
    echo "ERROR: REDDIT_USERNAME and REDDIT_PASSWORD must be set in .env file"
    exit 1
fi

# Start the scheduler in background
nohup python3 warmup_scheduler.py --start > logs/scheduler_output.log 2>&1 &
SCHEDULER_PID=$!

echo "Scheduler started with PID: $SCHEDULER_PID"
echo "Logs: logs/scheduler_output.log"
echo ""

# Show status
python3 warmup_scheduler.py --status
