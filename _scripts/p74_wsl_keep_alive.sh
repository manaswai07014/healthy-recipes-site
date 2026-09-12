#!/bin/bash
# scripts/p74_wsl_keep_alive.sh
# P74: WSL Keep-Alive
# Prevents Windows host from entering deep sleep which would suspend WSL2 VM
# and pause all cron jobs.
#
# Mechanism: ping localhost every 5 minutes (network activity keeps
# Windows awake IF configured to "stay awake on network activity" in
# Power Options. 老闆 must enable this in Windows settings.)
#
# Alternative (cross-platform): a simple HTTP request to a public endpoint
# every 5 minutes keeps the network adapter active.

# Run forever, pinging every 5 minutes
while true; do
    # Ping localhost (always succeeds, no external dep)
    ping -c 1 -W 2 localhost > /dev/null 2>&1
    
    # Light HTTP request (also keeps network active)
    curl -s -o /dev/null --max-time 5 https://www.google.com/generate_204 2>/dev/null || true
    
    # Log periodically (not every iteration to avoid log spam)
    if [ $(($(date +%s) % 3600)) -lt 300 ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] P74 WSL keep-alive ping" >> /home/hermes/healthy-recipes-logs/wsl-keep-alive.log
    fi
    
    sleep 300  # 5 minutes
done
