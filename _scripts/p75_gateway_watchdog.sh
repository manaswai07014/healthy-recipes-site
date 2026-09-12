#!/bin/bash
# scripts/p75_gateway_watchdog.sh
# P75: WSL-aware Hermes gateway watchdog
#
# Problem: WSL2 session suspend/resume can leave hermes-gateway in a
# broken state where systemd thinks it's dead but the process is alive,
# causing restart loops. After resume, gateway sometimes won't recover
# on its own and needs manual intervention.
#
# Solution: This watchdog runs every 5 minutes. If gateway is in
# "restart loop" state (multiple systemd restarts within 5 min) OR
# if the process exists but is not responding to systemd, this
# script performs a hard kill + manual restart.
#
# Cron schedule: every 5 min (manual add)

set -uo pipefail

LOG_FILE="/home/hermes/healthy-recipes-logs/gateway-watchdog.log"
MAX_RESTARTS_IN_WINDOW=5
WINDOW_MIN=5
SERVICE_NAME="hermes-gateway.service"

# Check systemd service state
# P77: systemctl --user fails in cron context ("No medium found" - no user bus).
# Workaround: parse systemctl output more carefully, or use direct PID check.
SERVICE_ACTIVE="unknown"
SERVICE_SUB_STATE="unknown"
if systemctl --user is-active "$SERVICE_NAME" 2>/dev/null; then
    SERVICE_ACTIVE="active"
else
    RC=$?
    if [ $RC -eq 0 ]; then
        SERVICE_ACTIVE="active"
    elif [ $RC -eq 3 ]; then
        SERVICE_ACTIVE="inactive"
    fi
fi
if systemctl --user show "$SERVICE_NAME" -p SubState --value 2>/dev/null; then
    SERVICE_SUB_STATE=$(systemctl --user show "$SERVICE_NAME" -p SubState --value 2>/dev/null || echo "unknown")
fi

# Count recent start attempts (last 5 min) via journalctl
RECENT_STARTS=$(journalctl --user -u "$SERVICE_NAME" --since "-${WINDOW_MIN} minutes" --no-pager 2>&1 | grep -c "Started.*$SERVICE_NAME")
RECENT_FAILED=$(journalctl --user -u "$SERVICE_NAME" --since "-${WINDOW_MIN} minutes" --no-pager 2>&1 | grep -c "Failed.*$SERVICE_NAME")

echo "[$(date '+%Y-%m-%d %H:%M:%S')] active=$SERVICE_ACTIVE sub=$SERVICE_SUB_STATE recent_starts=$RECENT_STARTS failed=$RECENT_FAILED" >> "$LOG_FILE"

# Case 1: Service in restart loop (more than 5 starts in 5 min)
if [ "$RECENT_STARTS" -gt "$MAX_RESTARTS_IN_WINDOW" ]; then
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT: Restart loop detected ($RECENT_STARTS starts in ${WINDOW_MIN}min). Forcing manual restart." >> "$LOG_FILE"

    # Stop the service (this kills any active process)
    systemctl --user stop "$SERVICE_NAME" 2>&1 >> "$LOG_FILE"
    sleep 3

    # Kill any lingering python processes
    pkill -9 -f "hermes_cli.main gateway" 2>&1 >> "$LOG_FILE" || true
    sleep 2

    # Start fresh
    systemctl --user start "$SERVICE_NAME" 2>&1 >> "$LOG_FILE"
    sleep 5

    # Verify it's up
    if systemctl --user is-active "$SERVICE_NAME" | grep -q "active"; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] RECOVERED: gateway is active after manual restart" >> "$LOG_FILE"
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] CRITICAL: gateway STILL DOWN after manual restart" >> "$LOG_FILE"
    fi

    exit 0
fi

# Case 2: Service "active" but gateway process not responding (zombie state)
# Check if main PID is actually alive and responsive
MAIN_PID=$(systemctl --user show "$SERVICE_NAME" -p MainPID --value 2>/dev/null)
if [ -n "$MAIN_PID" ] && [ "$MAIN_PID" != "0" ]; then
    if ! kill -0 "$MAIN_PID" 2>/dev/null; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT: Service active but PID $MAIN_PID dead. Forcing restart." >> "$LOG_FILE"
        systemctl --user restart "$SERVICE_NAME" 2>&1 >> "$LOG_FILE"
    fi
fi

# P78: Direct process check (works in cron context when systemctl --user fails).
# If hermes_cli.main gateway process exists but systemd doesn't see it,
# that's the classic WSL suspend state where the process is alive but
# systemd lost track. Force-restart to recover.
GATEWAY_PROCS=$(pgrep -f "hermes_cli.main gateway" 2>/dev/null | wc -l)
if [ "$GATEWAY_PROCS" -eq 0 ]; then
    # No gateway process found at all, definitely needs restart
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] ALERT: No gateway process found via pgrep. Forcing restart." >> "$LOG_FILE"
    systemctl --user start "$SERVICE_NAME" 2>&1 >> "$LOG_FILE" || \
    /home/hermes/apps/hermes-agent/venv/bin/python -m hermes_cli.main gateway run &
fi

# Case 3: All good, silent
exit 0
