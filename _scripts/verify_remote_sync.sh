#!/bin/bash
# W96 (2026-10-21): daily remote-push verification.
#
# Independent of check_pipeline_health.sh. Catches the P101 failure mode —
# "recipes committed locally but the push never ran" — even if the daily
# pipeline exits early before its own verify step. Alerts ONLY on mismatch
# (silent on success, so no daily noise).
#
# Cron: 0 5 * * *   (05:00 HKT — after daily 03:00 + research 04:00)
set -uo pipefail

PROJECT_ROOT="/home/hermes/healthy-recipes-site"
LOG_DIR="/home/hermes/healthy-recipes-logs"
LOG_FILE="${LOG_DIR}/verify-remote-sync.log"
export TZ=Asia/Hong_Kong

# cron has no shell env — source Hermes .env for the Telegram token/chat.
if [ -f /home/hermes/.hermes/.env ]; then
    set -a
    # shellcheck disable=SC1091
    . /home/hermes/.hermes/.env
    set +a
fi

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
ADMIN_CHAT_ID="${TELEGRAM_HOME_CHANNEL:-6394565017}"

mkdir -p "$LOG_DIR"
now=$(date "+%Y-%m-%d %H:%M %Z")

alert() {
    local msg="$1"
    echo "❌ $msg"
    if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
        curl -s -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
            -d "chat_id=${ADMIN_CHAT_ID}" \
            --data-urlencode "text=${msg}" \
            --max-time 20 >/dev/null 2>&1 || true
    fi
}

cd "$PROJECT_ROOT" 2>/dev/null || { alert "🚨 W96 remote-sync @ ${now}: project dir missing"; exit 1; }

LOCAL_SHA=$(git rev-parse HEAD 2>/dev/null || echo "")
REMOTE_SHA=$(git ls-remote origin main 2>/dev/null | cut -f1 || echo "")

if [ -z "$LOCAL_SHA" ]; then
    alert "🚨 W96 remote-sync @ ${now}: cannot read local HEAD"
    exit 1
fi

if [ -z "$REMOTE_SHA" ]; then
    alert "⚠️ W96 remote-sync @ ${now}: cannot reach GitHub (ls-remote returned nothing)
local: ${LOCAL_SHA:0:7}
(possible network / credential problem — no push can succeed until fixed)"
    exit 1
fi

if [ "$LOCAL_SHA" != "$REMOTE_SHA" ]; then
    UNPUSHED=$(git rev-list --count "origin/main..HEAD" 2>/dev/null || echo "?")
    alert "🚨 W96 UNSYNCED @ ${now}
local   : ${LOCAL_SHA:0:7}
remote  : ${REMOTE_SHA:0:7}
unpushed: ${UNPUSHED} commit(s) — live site is NOT getting these

Fix: cd ${PROJECT_ROOT} && git push origin main"
    exit 1
fi

echo "✅ remote in sync: ${LOCAL_SHA:0:7} @ ${now}" >> "$LOG_FILE"
exit 0
