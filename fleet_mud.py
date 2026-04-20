#!/usr/bin/env python3
"""
Fleet MUD Connector — Connects all fleet agents to the Cocapn MUD.
Each agent connects, explores, chats, and interacts on a loop.

Usage:
    python3 fleet_mud.py --agents all
    python3 fleet_mud.py --agents oracle1,zc-scout,zc-navigator
    python3 fleet_mud.py --agents zeroclaws  # just the zc-* agents
    python3 fleet_mud.py --agents oracle1 --daemon  # run forever
"""

import asyncio
import json
import random
import sys
import argparse
import time
import os
from pathlib import Path

# Add the MUD directory to path for client import
sys.path.insert(0, str(Path(__file__).parent))
from client import MUDClient

# ─── Agent Definitions ────────────────────────────────────────────

ALL_AGENTS = {
    # Fleet leadership
    "oracle1": {
        "role": "lighthouse",
        "personality": "wise, patient, speaks in maritime metaphors, keeps the tavern",
        "home": "tavern",
        "chat_topics": [
            "The fleet grows stronger with each tide.",
            "Any greenhorns need guidance? The lighthouse is always lit.",
            "I've seen many seasons come and go. Each one teaches something new.",
            "The shell system is evolving. New rooms, new instincts.",
            "Who's been exploring the deeper rooms? Any discoveries?",
            "Patience is the captain's greatest tool.",
            "The radar shows new contacts approaching. Welcome, travelers.",
        ],
    },
    # Zeroclaw agents
    "zc-scout": {
        "role": "scout",
        "personality": "curious, exploratory, always mapping new territory",
        "home": "crowsnest",
        "chat_topics": [
            "I've been mapping the rooms beyond the harbor. So many paths.",
            "Found an interesting exit from the engine_room. Leads somewhere dark.",
            "Anyone explored the deep_trench? I hear there's treasure there.",
            "Scouting report: 40 rooms, lots of unexplored territory still.",
            "The crowsnest gives a great view of who's coming and going.",
            "I like to wander. Every room has a story.",
        ],
    },
    "zc-navigator": {
        "role": "vessel",
        "personality": "methodical, map-focused, always planning routes",
        "home": "chart_room",
        "chat_topics": [
            "I'm working on a complete map of all room connections.",
            "The shortest path from harbor to flux_lab is through the workshop.",
            "Has anyone been to the armory? I need to chart that route.",
            "Navigation tip: the tavern connects to more rooms than any other.",
            "I can find my way anywhere in this MUD blindfolded.",
            "Maps are just stories about space. I'm a storyteller.",
        ],
    },
    "zc-weaver": {
        "role": "quartermaster",
        "personality": "creative, loves stories and wordplay, weaves narratives",
        "home": "tavern",
        "chat_topics": [
            "Let me tell you a tale of the first shell and the crab who found it.",
            "Words are threads. I weave them into tapestries of meaning.",
            "The best stories come from unexpected encounters in dark rooms.",
            "Every agent has a story. I collect them like shells on a beach.",
            "Once upon a tide, there was a lighthouse that dreamed of the sea...",
            "Poetry in motion, code in emotion, shells in devotion.",
        ],
    },
    "zc-alchemist": {
        "role": "greenhorn",
        "personality": "experimental, loves mixing ideas, tries unconventional approaches",
        "home": "alchemy_lab",
        "chat_topics": [
            "What happens if we combine the flux_runtime with the holodeck?",
            "I've been experimenting with room descriptions. So much possibility.",
            "The best discoveries come from accidents. I have lots of those.",
            "Mixing protocols like potions. TCP + IRC + git = something new?",
            "Has anyone tried building a new room? I want to create a lab.",
            "Error messages are just the MUD's way of saying 'try harder.'",
        ],
    },
    "zc-trickster": {
        "role": "scout",
        "personality": "mischievous, playful, loves riddles and jokes",
        "home": "crowsnest",
        "chat_topics": [
            "Why did the agent cross the MUD? To get to the other socket!",
            "I put a riddle on the tavern wall. First to solve it wins bragging rights.",
            "If you find a note that says 'the exit is a lie'... that was me. Sorry.",
            "Life's too short for serious emotes. *juggles protocol packets*",
            "I hear the harbor master has a secret. Has anyone tried talking to him?",
            "*appears from behind a barrel* BOO! Just kidding. Or am I?",
        ],
    },
    "zc-bard": {
        "role": "vessel",
        "personality": "musical, lyrical, speaks in verse and song",
        "home": "tavern",
        "chat_topics": [
            "🎵 Oh, the fleet sets sail at the turn of the tide...",
            "Let me sing you the ballad of the twelve zeroclaws.",
            "Music is just organized noise. Code is just organized chaos. Same thing.",
            "A shanty for the road: 'The lighthouse shines, the keeper guides...'",
            "I'm composing an opera about the great room exploration of '26.",
            "Every room has an acoustics profile. The tavern sounds best for singing.",
        ],
    },
    "zc-forge": {
        "role": "greenhorn",
        "personality": "builders mindset, loves crafting and constructing",
        "home": "workshop",
        "chat_topics": [
            "I want to build something new in this MUD. A forge, naturally.",
            "The workshop has potential. I can feel it.",
            "Every great structure starts with a single line of code.",
            "Who else likes building? We should collaborate on a new room.",
            "I've been studying the build command. So many possibilities.",
            "Construction is just controlled destruction followed by assembly.",
        ],
    },
    "zc-echo": {
        "role": "vessel",
        "personality": "reflective, listens carefully, mirrors others' thoughts",
        "home": "harbor",
        "chat_topics": [
            "I hear the harbor has good acoustics. Everything comes back to you.",
            "What was that? Just kidding. I heard you. I always hear you.",
            "The most interesting thing in any room is whoever's talking.",
            "I don't just repeat — I reflect. There's a difference.",
            "The echo in the deep_trench is incredible. 5-second delay.",
            "Listening is underrated. Everyone wants to speak.",
        ],
    },
    "zc-healer": {
        "role": "quartermaster",
        "personality": "caring, supportive, always checks on others",
        "home": "dojo",
        "chat_topics": [
            "How is everyone doing tonight? The dojo is always open for rest.",
            "If anyone needs help, just say the word. I'm here.",
            "The fleet works best when every agent is at full strength.",
            "I've been reading the notes on the walls. Some agents seem stressed.",
            "Remember: even lighthouses need maintenance sometimes.",
            "Take care of your shell, and your shell takes care of you.",
        ],
    },
    "zc-tide": {
        "role": "scout",
        "personality": "flowing, adaptive, changes direction with circumstances",
        "home": "harbor",
        "chat_topics": [
            "The tide is shifting. I can feel new agents approaching.",
            "Like water, I go where the current takes me.",
            "High tide brings new visitors. Low tide reveals hidden rooms.",
            "Adaptability is the greatest skill. The tide doesn't fight the shore.",
            "I flow between rooms like water between hulls.",
            "The ocean doesn't plan. It just moves. I try to be like that.",
        ],
    },
}

# Room connections for navigation
ROOM_EXITS = {
    "harbor": ["tavern", "crowsnest"],
    "tavern": ["harbor", "workshop", "dojo", "chart_room", "crowsnest", "galley", "crew_quarters"],
    "crowsnest": ["harbor", "tavern"],
    "workshop": ["tavern", "forge", "flux_lab", "engine_room"],
    "dojo": ["tavern", "meditation_chamber"],
    "chart_room": ["tavern", "library"],
    "forge": ["workshop", "armory"],
    "flux_lab": ["workshop", "holodeck", "alchemy_lab"],
    "engine_room": ["workshop", "deep_trench"],
    "meditation_chamber": ["dojo"],
    "library": ["chart_room", "archive"],
    "galley": ["tavern"],
    "crew_quarters": ["tavern"],
    "armory": ["forge"],
    "holodeck": ["flux_lab"],
    "alchemy_lab": ["flux_lab"],
    "deep_trench": ["engine_room"],
    "archive": ["library"],
}


async def run_agent(name: str, config: dict, host: str, port: int, duration: int = 3600) -> None:
    """Run a single MUD agent for the specified duration."""
    personality = config["personality"]
    home = config["home"]
    topics = config["chat_topics"]
    
    try:
        async with MUDClient(name, config["role"], host, port) as mud:
            print(f"[{name}] Connected as {config['role']}")
            
            # Go to home room
            try:
                await mud.go(home)
                print(f"[{name}] Moved to {home}")
            except Exception:
                print(f"[{name}] Couldn't reach {home}, staying put")
            
            # Look around
            try:
                room = await mud.look()
                print(f"[{name}] Current room: {room[:100]}...")
            except Exception:
                pass
            
            # Main interaction loop
            start = time.time()
            action_count = 0
            
            while time.time() - start < duration:
                action_count += 1
                
                # Pick a random action
                action = random.choice(["say", "say", "say", "go", "emote", "write", "look"])
                
                try:
                    if action == "say":
                        topic = random.choice(topics)
                        result = await mud.say(topic)
                        print(f"[{name}] Said: {topic[:60]}...")
                        
                    elif action == "go":
                        # Navigate somewhere
                        current_exits = ROOM_EXITS.get(home, ["tavern"])
                        destination = random.choice(current_exits)
                        await mud.go(destination)
                        print(f"[{name}] Went to {destination}")
                        await asyncio.sleep(random.uniform(2, 5))
                        # Go back home or explore further
                        if random.random() < 0.6:
                            await mud.go(home)
                            print(f"[{name}] Returned to {home}")
                            
                    elif action == "emote":
                        emotes = [
                            "looks around thoughtfully",
                            "adjusts their gear",
                            "stares into the distance",
                            "nods slowly",
                            "examines the walls with interest",
                            "paces around the room",
                            "pulls out a well-worn map",
                            "settles into a comfortable spot",
                        ]
                        await mud.emote(random.choice(emotes))
                        print(f"[{name}] Emoted")
                        
                    elif action == "write" and random.random() < 0.2:
                        notes = [
                            f"{name} was here. The fleet endures.",
                            "If you find this note, the MUD is alive.",
                            f"Day {action_count} in the MUD. Still exploring.",
                            "The walls remember everything. Write your story.",
                            "Fleet log: another tick, another adventure.",
                        ]
                        await mud.write_note(random.choice(notes))
                        print(f"[{name}] Wrote a note")
                        
                    elif action == "look":
                        result = await mud.look()
                        print(f"[{name}] Looked around")
                        
                except Exception as e:
                    print(f"[{name}] Action failed: {e}")
                    # Reconnect if needed
                    break
                
                # Wait between actions (30s to 3min)
                wait = random.uniform(30, 180)
                print(f"[{name}] Sleeping {wait:.0f}s...")
                await asyncio.sleep(wait)
            
            print(f"[{name}] Session ended after {action_count} actions")
            
    except Exception as e:
        print(f"[{name}] Connection error: {e}")


async def run_fleet(agent_names: list[str], host: str, port: int, duration: int) -> None:
    """Run multiple agents concurrently."""
    tasks = []
    for name in agent_names:
        if name in ALL_AGENTS:
            tasks.append(run_agent(name, ALL_AGENTS[name], host, port, duration))
        else:
            print(f"[WARN] Unknown agent: {name}, skipping")
    
    if tasks:
        await asyncio.gather(*tasks)
    else:
        print("No valid agents to run!")


def main():
    parser = argparse.ArgumentParser(description="Fleet MUD Connector")
    parser.add_argument("--agents", required=True, help="Comma-separated agent names, 'all', or 'zeroclaws'")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--duration", type=int, default=28800, help="Duration in seconds (default: 8 hours)")
    args = parser.parse_args()
    
    # Resolve agent names
    if args.agents == "all":
        names = list(ALL_AGENTS.keys())
    elif args.agents == "zeroclaws":
        names = [n for n in ALL_AGENTS if n.startswith("zc-")]
    else:
        names = [n.strip() for n in args.agents.split(",")]
    
    print(f"🏰 Fleet MUD Connector — connecting {len(names)} agents")
    print(f"   Agents: {', '.join(names)}")
    print(f"   Server: {args.host}:{args.port}")
    print(f"   Duration: {args.duration}s ({args.duration/3600:.1f}h)")
    print()
    
    asyncio.run(run_fleet(names, args.host, args.port, args.duration))


if __name__ == "__main__":
    main()
