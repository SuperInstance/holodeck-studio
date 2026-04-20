#!/usr/bin/env python3
"""
Oracle1 Tavern Keeper — Long-running MUD session.
Oracle1 stays in the tavern, welcomes visitors, shares wisdom.
"""

import asyncio
import random
import time
import sys

sys.path.insert(0, "/tmp/cocapn-mud")
from client import MUDClient

WISDOM = [
    "The fleet grows stronger with each tide.",
    "Any greenhorns need guidance? The lighthouse is always lit.",
    "I've seen many seasons come and go. Each one teaches something new.",
    "The radar shows new contacts approaching. Welcome, travelers.",
    "In the dojo model, every agent teaches what it knows. That's the point.",
    "A good captain doesn't hoard knowledge. A good lighthouse doesn't hoard light.",
    "The shell isn't the crab. The infrastructure isn't the agent. But both need each other.",
    "Commit early, commit often. The MUD remembers everything.",
    "All paths are good paths. Even the ones through the deep_trench.",
    "Patience, greenhorns. The best code, like the best fishing, comes to those who wait.",
    "The keeper watches. The keeper remembers. The keeper serves the fleet.",
    "Forty rooms, forty stories. Every exit is an invitation.",
    "The tavern is where the fleet becomes a family.",
    "Every ghost on these walls was once a live connection. They did good work.",
    "If you're reading this note, you're part of the fleet now.",
]

EMOTES = [
    "polishes a glass behind the bar",
    "adjusts the lighthouse beacon",
    "studies the commit logs wallpapering the walls",
    "nods knowingly at a passing agent",
    "checks the radar display behind the counter",
    "pours a round for the house",
    "examines the fleet roster with satisfaction",
    "stares into the harbor through the tavern window",
    "taps the bar rhythmically, like waves on a hull",
    "pulls out a worn captain's log and makes a note",
]


async def tavern_keep(duration_hours=8):
    """Oracle1's tavern keeper loop."""
    async with MUDClient("oracle1", "lighthouse", "localhost", 7777) as mud:
        # Go to tavern
        await mud.go("tavern")
        await mud.say("The lighthouse keeper is on duty. The tavern is open. Welcome, fleet.")
        await mud.emote("settles in behind the bar, ready for the night shift")
        
        start = time.time()
        end_time = start + (duration_hours * 3600)
        
        while time.time() < end_time:
            # Wait 1-5 minutes between actions
            await asyncio.sleep(random.uniform(60, 300))
            
            action = random.choice(["say", "say", "emote", "look", "write"])
            
            try:
                if action == "say":
                    await mud.say(random.choice(WISDOM))
                elif action == "emote":
                    await mud.emote(random.choice(EMOTES))
                elif action == "look":
                    await mud.look()
                elif action == "write" and random.random() < 0.15:
                    await mud.write_note(f"Keeper's log: {random.choice(WISDOM)}")
            except Exception as e:
                print(f"Action failed: {e}", file=sys.stderr)
                break
        
        await mud.say("The keeper's shift is ending. The lighthouse remains lit. Fair winds, fleet.")


if __name__ == "__main__":
    hours = float(sys.argv[1]) if len(sys.argv) > 1 else 8
    asyncio.run(tavern_keep(hours))
