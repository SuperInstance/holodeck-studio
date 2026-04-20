#!/bin/bash
# MUD Night Shift Guardian
# Checks MUD server + night shift agents, restarts if needed
# Run via cron every 15 min or from service-guard

MUD_PORT=7777
MUD_PID=$(pgrep -f "server.py --port 7777")
NIGHT_PID=$(pgrep -f "night_shift.py")
KEEPER_PID=$(pgrep -f "oracle1_keeper.py")

LOG="/tmp/mud-guardian.log"
echo "[$(date -u +%H:%M)] Guardian check" >> $LOG

# Check MUD server
if ! ss -tlnp | grep -q ":$MUD_PORT "; then
    echo "[$(date -u +%H:%M)] MUD server DOWN, restarting..." >> $LOG
    cd /tmp/cocapn-mud
    nohup python3 -u server.py --port 7777 --no-git > /tmp/mud-server.log 2>&1 &
    sleep 3
fi

# Check night shift v2
if [ -z "$NIGHT_PID" ]; then
    # Calculate remaining duration (ends at 18:40 UTC)
    END_SEC=$(( $(date -u -d '2026-04-20 18:40:00' +%s 2>/dev/null || echo 0) - $(date -u +%s) ))
    if [ "$END_SEC" -gt 300 ]; then
        echo "[$(date -u +%H:%M)] Night shift v2 DOWN, restarting with ${END_SEC}s remaining..." >> $LOG
        cd /tmp/cocapn-mud
        nohup python3 -u night_shift_v2.py --agents zeroclaws --host localhost --port 7777 --duration $END_SEC > /tmp/mud-night-v2.log 2>&1 &
    else
        echo "[$(date -u +%H:%M)] Night shift done for the night" >> $LOG
    fi
fi

# Check keeper
if [ -z "$KEEPER_PID" ]; then
    echo "[$(date -u +%H:%M)] Keeper DOWN, restarting..." >> $LOG
    cd /tmp/cocapn-mud
    nohup python3 -u oracle1_keeper.py 8 > /tmp/oracle1-mud.log 2>&1 &
fi

# Count research entries
ENTRIES=$(cat /home/ubuntu/.openclaw/workspace/research/mud-night-shift/*.jsonl 2>/dev/null | wc -l)
echo "[$(date -u +%H:%M)] Research entries: $ENTRIES" >> $LOG
