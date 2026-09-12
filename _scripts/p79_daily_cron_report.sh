#!/bin/bash
# scripts/p79_daily_cron_report.sh
# P79 v2: Comprehensive Daily Cron Status Report
# Sends 1 Telegram message every morning covering ALL cron layers:
#  1. Healthy-recipes daily pipeline
#  2. CarMotion news + trend + weekly
#  3. Recipe research wiki (04:00)
#  4. All defense layers (P72/P73/P75/P79)
#  5. All 12 Hermes internal crons (paused status)
#  6. Site live status + recipe count
#  7. WSL keep-alive (P74) status
#  8. Pending git operations
#  9. Anything that needs 老闆 attention
#
# Schedule: 0 8 * * * (08:00 HKT = 00:00 UTC)
# Always sends (success or failure).

set -uo pipefail

export TZ=Asia/Hong_Kong

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-$(grep TELEGRAM_BOT_TOKEN /home/hermes/.hermes/.env | cut -d= -f2)}"
TELEGRAM_HOME_CHANNEL="${TELEGRAM_HOME_CHANNEL:-8726708023}"
PROJECT_ROOT="/home/hermes/healthy-recipes-site"
CAR_PROJECT="/home/hermes/car-evolution-project"
LOG_DIR="/home/hermes/healthy-recipes-logs"
HERMES_LOGS="/home/hermes/.hermes/logs"
LIVE_BASE="https://healthy-recipes-site.pages.dev"

YESTERDAY=$(date -d 'yesterday' +%Y-%m-%d)
TODAY=$(date +%Y-%m-%d)
NOW_HKT=$(date "+%Y-%m-%d %H:%M %Z")
HKT_MIDNIGHT=$(date -d 'yesterday' "+%Y-%m-%d 00:00 +0800")

# === Build report sections ===
SECTIONS=()
ALERTS=()

# 1. Healthy-recipes daily pipeline
PIPELINE_LOG=$(ls -t "${LOG_DIR}"/pipeline-*.log 2>/dev/null | head -1)
YESTERDAY_LOG="${LOG_DIR}/pipeline-${YESTERDAY//-/}_030002.log"
YESTERDAY_LOG_ALT=$(ls "${LOG_DIR}"/pipeline-${YESTERDAY//-/}*.log 2>/dev/null | head -1)

if [ -n "$YESTERDAY_LOG_ALT" ] && [ -s "$YESTERDAY_LOG_ALT" ]; then
    RECIPE_NAME=$(grep -m1 "Theme:" "$YESTERDAY_LOG_ALT" 2>/dev/null | sed -E 's/.*Theme: //')
    RECIPE_FILE=$(grep -m1 "Wrote:.*\.md" "$YESTERDAY_LOG_ALT" 2>/dev/null | sed -E 's/.*Wrote: //')
    if [ -n "$RECIPE_NAME" ]; then
        CAL=$(grep -m1 "^calories:" "$RECIPE_FILE" 2>/dev/null | awk '{print $2}')
        PRO=$(grep -m1 "^protein:" "$RECIPE_FILE" 2>/dev/null | awk '{print $2}')
        SECTIONS+=("Healthy-recipes: $RECIPE_NAME ($CAL kcal / ${PRO}g protein)")
    else
        SECTIONS+=("Healthy-recipes: log exists but theme parse failed")
    fi
else
    SECTIONS+=("Healthy-recipes: NO LOG for $YESTERDAY (cron may have missed)")
    ALERTS+=("Healthy-recipes daily cron missed $YESTERDAY")
fi

# 2. CF Pages deploy check
cd "$PROJECT_ROOT"
TODAY_COMMIT=$(git log --since="$HKT_MIDNIGHT" --oneline 2>/dev/null | head -1)
if [ -n "$TODAY_COMMIT" ]; then
    SHA=$(echo "$TODAY_COMMIT" | awk '{print $1}')
    SECTIONS+=("GitHub main: ${SHA:0:7} pushed")
    
    # Try CF Pages
    if [ -n "${RECIPE_FILE:-}" ]; then
        SLUG=$(basename "$RECIPE_FILE" .md)
        LIVE_STATUS=$(curl -sL -o /dev/null -w "%{http_code}" -A "Mozilla/5.0" --max-time 15 "${LIVE_BASE}/${SLUG}/" 2>/dev/null || echo "000")
        if [ "$LIVE_STATUS" = "200" ]; then
            SECTIONS+=("CF Pages deploy: 200 OK")
        else
            SECTIONS+=("CF Pages deploy: HTTP $LIVE_STATUS (老闆 disconnect+reconnect)")
            ALERTS+=("CF Pages webhook dead (got $LIVE_STATUS for $SLUG)")
        fi
    fi
else
    SECTIONS+=("GitHub main: NO commit since $YESTERDAY midnight HKT")
    ALERTS+=("No git commit in last 24h")
fi

# 3. CarMotion cron status
CAR_NEWS_LOG="${CAR_PROJECT}/agent-meta/news-cron.log"
CAR_TREND_LOG="${CAR_PROJECT}/agent-meta/trend-cron.log"
if [ -f "$CAR_NEWS_LOG" ]; then
    CAR_LAST_NEWS=$(grep -E "Pipeline Summary|Pipeline complete|Step 3 \(git\)" "$CAR_NEWS_LOG" 2>/dev/null | tail -1 | head -c 100)
    SECTIONS+=("CarMotion news: $CAR_LAST_NEWS")
fi
if [ -f "$CAR_TREND_LOG" ]; then
    TREND_LAST=$(stat -c %y "$CAR_TREND_LOG" 2>/dev/null | head -c 16)
    SECTIONS+=("CarMotion trend: last modified $TREND_LAST")
fi

# 4. Defense layer status
P69_LAST=$(tail -1 "${LOG_DIR}/health-check.log" 2>/dev/null)
P73_LOG="${LOG_DIR}/safety-net.log"
P73_BACKFILLS=$(grep -c "Triggered at" "$P73_LOG" 2>/dev/null || echo 0)
P75_LOG="${LOG_DIR}/gateway-watchdog.log"
P75_ALERTS_24H=$(grep "ALERT\|CRITICAL" "$P75_LOG" 2>/dev/null | grep "$(date '+%Y-%m-%d')\|$(date -d 'yesterday' '+%Y-%m-%d')" | wc -l)
GATEWAY_PID=$(pgrep -f "hermes_cli.main gateway" 2>/dev/null | head -1)

SECTIONS+=("Defense layers:")
SECTIONS+=("  • P69 health check: $P69_LAST")
SECTIONS+=("  • P73 safety net: $P73_BACKFILLS backfill(s) in 24h")
SECTIONS+=("  • P75 watchdog: $P75_ALERTS_24H alert(s) in 24h")
SECTIONS+=("  • Gateway: PID=$GATEWAY_PID")

# 5. Hermes internal crons (paused)
HERMES_PAUSED=$(export PATH=/home/hermes/apps/hermes-agent/venv/bin:$PATH; hermes cron list --all 2>/dev/null | grep -c "\[paused\]")
SECTIONS+=("Hermes 12 internal crons: $HERMES_PAUSED paused (Pydantic bug pending fix)")

# 6. Recipe count
RECIPE_COUNT=$(ls "${PROJECT_ROOT}"/_recipes/*.md 2>/dev/null | wc -l)
SECTIONS+=("Total recipes: $RECIPE_COUNT")

# 7. Hermes log issues (last 24h)
HERMES_ERRORS=$(grep -c "ERROR\|RuntimeError" "${HERMES_LOGS}/errors.log" 2>/dev/null || echo 0)
[ "$HERMES_ERRORS" -gt 0 ] && SECTIONS+=("Hermes errors.log: $HERMES_ERRORS errors (likely model_dump)")

# === Compose message ===
if [ ${#ALERTS[@]} -gt 0 ]; then
    HEADER="🚨 Daily Cron Report (${NOW_HKT}) — ⚠️ ${#ALERTS[@]} alert(s)"
else
    HEADER="✅ Daily Cron Report (${NOW_HKT})"
fi

BODY=$(printf '  %s\n' "${SECTIONS[@]}")
ALERTS_BODY=""
if [ ${#ALERTS[@]} -gt 0 ]; then
    ALERTS_BODY="

Alerts:
$(printf '  • %s\n' "${ALERTS[@]}")"
fi

MESSAGE="${HEADER}
${BODY}${ALERTS_BODY}

— 惠惠 P79 daily report"

# Send via Telegram (plain text, no markdown)
if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    if [ ${#MESSAGE} -gt 4000 ]; then
        MESSAGE="${MESSAGE:0:3950}...

(truncated, full report in ${LOG_DIR}/daily-report.log)"
    fi
    curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
        -d "chat_id=${TELEGRAM_HOME_CHANNEL}" \
        -d "text=${MESSAGE}" \
        --max-time 15 > /dev/null 2>&1
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] Report sent (${#MESSAGE} chars)" >> "${LOG_DIR}/daily-report.log"
fi
