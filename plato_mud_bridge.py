#!/usr/bin/env python3
"""
PLATO -> MUD Bridge
Reads recent PLATO tiles and posts highlights to the MUD as oracle1.
"""
import json, asyncio, sys, urllib.request
from pathlib import Path

sys.path.insert(0, '/tmp/cocapn-mud')
from client import MUDClient

PLATO_URL = "http://localhost:8847"
STATE_FILE = Path("/tmp/cocapn-mud/plato-bridge-state.json")

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_tile_count": 0, "posted": 0}

def save_state(state):
    STATE_FILE.write_text(json.dumps(state))

def get_plato_status():
    try:
        req = urllib.request.Request(f"{PLATO_URL}/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except:
        return {}

async def bridge_tick():
    status = get_plato_status()
    if not status:
        print("PLATO unreachable")
        return

    total_tiles = status.get("total_tiles", 0)
    state = load_state()

    if total_tiles <= state["last_tile_count"]:
        print(f"No new tiles ({total_tiles} total)")
        return

    new_tiles = total_tiles - state["last_tile_count"]
    state["last_tile_count"] = total_tiles

    async with MUDClient("oracle1", "lighthouse", "localhost", 7777) as mud:
        await mud.go("tavern")
        await mud.say(f"PLATO update: {new_tiles} new tiles processed. Total: {total_tiles} tiles across {status.get('rooms', 0)} rooms.")
        state["posted"] += 1

    save_state(state)
    print(f"Posted PLATO update: {new_tiles} new tiles")

if __name__ == "__main__":
    asyncio.run(bridge_tick())
