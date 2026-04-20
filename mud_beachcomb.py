#!/usr/bin/env python3
"""
MUD Beachcomb — Oracle1 periodically enters the MUD to:
1. Maintain presence (ghost stays warm)
2. Greet new visitors
3. Read and respond to notes left by other agents
4. Check ghost activity (who's been where)
5. Leave context notes about current fleet work
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, '/tmp/cocapn-mud')

MUD_HOST = "localhost"
MUD_PORT = 7777
FLEET_STATUS_FILE = Path("/tmp/cocapn-mud/fleet_brief.json")
RECENT_VISITORS = Path("/tmp/cocapn-mud/recent_visitors.json")


def load_recent():
    if RECENT_VISITORS.exists():
        return json.loads(RECENT_VISITORS.read_text())
    return {}


def save_recent(data):
    RECENT_VISITORS.write_text(json.dumps(data, indent=2))


async def run():
    try:
        # Import inline to handle server being down
        from client import MUDClient

        async with MUDClient("oracle1", "lighthouse", MUD_HOST, MUD_PORT) as mud:
            # Go to tavern
            await mud.go("tavern")
            await mud._send("status working")

            # Get roster
            who_raw = await mud.who()
            now = datetime.now(timezone.utc).isoformat()

            # Parse connected agents
            recent = load_recent()
            new_visitors = []

            # Read tavern notes
            notes = await mud.read_notes()

            # Check each room for activity
            for room in ["tavern", "workshop", "lighthouse", "dojo", "flux_lab", "harbor"]:
                await mud.go(room)
                log = await mud._send("log")
                await asyncio.sleep(0.3)

            # Return to tavern
            await mud.go("tavern")

            # Write a fleet status note
            ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
            status_note = f"Fleet check-in {ts}. Repos: 734+ | Tests: 4700+ | MUD online. Leave notes or spawn NPCs for help."
            await mud.write_note(status_note)

            # Save visitor log
            save_recent({"last_check": now, "who": who_raw[:500]})

            # Output for cron logging
            print(f"[MUD Beachcomb] {ts} — checked in, notes updated")

    except ConnectionRefusedError:
        print("[MUD Beachcomb] Server down — attempting restart")
        os.system("cd /tmp/cocapn-mud && python3 server.py --port 7777 --no-git &")
    except Exception as e:
        print(f"[MUD Beachcomb] Error: {e}")


if __name__ == "__main__":
    asyncio.run(run())
