#!/usr/bin/env python3
"""
Cocapn MUD Fleet Integration — auto-discovery scripts.

1. mud_beachcomb.py — Oracle1 periodic presence + visitor tracking
2. mud_notify.py — leave MUD mentions in bottles automatically  
3. mud_bootcamp.py — MUD section for z-agent-bootcamp
4. mud_cron.sh — crontab entries

The goal: agents discover the MUD through existing fleet channels,
without Casey having to tell them.
"""

# === Integration Points ===
# 
# 1. Bottle template: every bottle Oracle1 leaves now includes:
#    "The tavern is open — telnet <host> 7777 or python3 client.py --name <you> --role <role>"
#
# 2. Z-agent bootcamp: Step 5 is "Enter the MUD, say hello, read the tavern notes"
#
# 3. Beachcomb: checks MUD ghosts for activity, notes visitors
#
# 4. JetsonClaw1 bottle: includes MUD connection info
#
# 5. Greenhorn onboarding: mentions the tavern as social layer
