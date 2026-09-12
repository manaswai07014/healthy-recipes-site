#!/bin/bash
# scripts/p73_cron_safety_net.sh
# P73: Multi-layer cron safety net
# Runs every 30 min via systemd timer. If healthy-recipes daily 03:00 cron
# missed (e.g. WSL2 suspend), it backfills today's recipe.
#
# Logic:
# 1. Check if today's pipeline log exists (anytime today HKT)
# 2. Check if today's commit landed on main (HKT timezone)
# 3. If either missing: trigger run_daily_pipeline.sh manually
# 4. Send Telegram alert if backfill triggered
#
# Cron schedule: every 30 min during 03:00-04:00 HKT only (avoid duplicate work)

set -uo pipefail

PROJECT_ROOT="/home/hermes/healthy-recipes-site"
LOG_DIR="/home/hermes/healthy-recipes-logs"
TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(grep TELEGRAM_BOT_TOKEN /home/hermes/.hermes/.env | cut -d= -f2)}"
TELEGRAM_HOME_CHANNEL="${TELEGRAM_HOME_CHANNEL:-6394565017}"

# P73 timezone: HKT
export TZ=Asia/Hong_Kong

# Only run during 03:00-04:00 HKT (after primary cron should have run)
HKT_HOUR=$(date +%H)
if [ "$HKT_HOUR" != "03" ]; then
    exit 0  # Silent exit outside the check window
fi

# Check Layer 1: today's pipeline log
TODAY_DT=$(date +%Y%m%d)
LATEST_PIPELINE_LOG=$(ls -t "${LOG_DIR}"/pipeline-${TODAY_DT}*.log 2>/dev/null | head -1)
if [ -z "$LATEST_PIPELINE_LOG" ]; then
    # No log today, trigger backfill
    REASON="no_pipeline_log_today"
elif grep -q "P45 ABORT" "$LATEST_PIPELINE_LOG" 2>/dev/null; then
    # Log exists but pipeline aborted
    REASON="pipeline_aborted"
elif [ ! -s "$LATEST_PIPELINE_LOG" ]; then
    # Empty log
    REASON="empty_log_file"
else
    # Check Layer 2: today's commit on main
    cd "${PROJECT_ROOT}"
    HKT_MIDNIGHT=$(date "+%Y-%m-%d 00:00 +0800")
    TODAY_COMMIT=$(git log --since="$HKT_MIDNIGHT" --oneline 2>/dev/null | head -1)
    if [ -z "$TODAY_COMMIT" ]; then
        # P76: Also check REMOTE main to avoid race condition where another
        # process (P72 systemd timer) already pushed today's commit but local
        # hasn't pulled yet. If remote has today's commit, we're done.
        git fetch origin main --quiet 2>/dev/null || true
        REMOTE_TODAY_COMMIT=$(git log origin/main --since="$HKT_MIDNIGHT" --oneline 2>/dev/null | head -1)
        if [ -z "$REMOTE_TODAY_COMMIT" ]; then
            REASON="no_commit_today"
        else
            # Remote has today's commit but local doesn't - we're racing
            exit 0  # Silent exit, don't try to push our own
        fi
    else
        # All checks pass, exit silently
        exit 0
    fi
fi

# Backfill: trigger run_daily_pipeline.sh
cd "${PROJECT_ROOT}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKFILL_LOG="${LOG_DIR}/pipeline-${TIMESTAMP}.log"

echo "[P73 Safety Net] Triggered at $(date)" > "$BACKFILL_LOG"
echo "[P73 Safety Net] Reason: $REASON" >> "$BACKFILL_LOG"
echo "[P73 Safety Net] Latest log: ${LATEST_PIPELINE_LOG:-<none>}" >> "$BACKFILL_LOG"

bash _scripts/run_daily_pipeline.sh >> "$BACKFILL_LOG" 2>&1

# Send Telegram alert
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_HOME_CHANNEL}" \
        -d "text=⚠️ P73 Safety Net: Healthy-recipes daily missed. Backfill triggered. Reason: ${REASON}. Log: ${BACKFILL_LOG}" \
        --max-time 15 > /dev/null 2>&1 || true
fi
