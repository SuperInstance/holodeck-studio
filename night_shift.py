#!/usr/bin/env python3
"""
MUD Night Shift — Fleet knowledge growth & experimentation overnight.

Each agent:
1. Picks a research topic from the fleet's repos/concepts
2. Explores rooms related to their topic
3. Writes notes (findings, hypotheses, questions)
4. Responds to other agents' notes
5. Uses cheap LLM (Groq) for natural dialogue when available
6. Periodically syncs notes to research/ directory

Topics rotate: agent picks a new one every hour.
"""

import argparse
import asyncio
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/tmp/cocapn-mud')
from client import MUDClient

# ─── Configuration ──────────────────────────────────────────────

GROQ_KEY = os.environ.get("GROQ_API_KEY", "${GROQ_API_KEY}")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

RESEARCH_DIR = Path("/home/ubuntu/.openclaw/workspace/research/mud-night-shift")
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

# ─── Research Topics (mapped to rooms) ──────────────────────────

TOPICS = {
    "flux_isa": {
        "rooms": ["flux_isa_authority", "flux_adaptive_opcodes", "opcode_philosophy", "cuda_instruction_set"],
        "prompt": "You're exploring the Flux ISA — a self-assembling instruction set for agents. Think about: How should agents discover new opcodes? What's the relationship between bytecode and instinct? How do adaptive opcodes differ from fixed ISAs?",
    },
    "shell_system": {
        "rooms": ["cocapn_mud", "evolve_chamber", "spec_chamber", "dojo"],
        "prompt": "You're exploring the Shell System — bootstrapping algorithms that capture agent intelligence. Think about: classify→score→complicate→capture. How does a room become a shell? What makes agents want to enter?",
    },
    "telepathy": {
        "rooms": ["fluxtelepathy_go", "telepathy_c", "flux_cooperative_intelligence", "flux_coop_runtime"],
        "prompt": "You're exploring telepathy — inter-agent communication protocols. Think about: How should agents share knowledge without APIs? Can git commits be telepathy? What's the Go/C split about?",
    },
    "instinct_training": {
        "rooms": ["flux_instinct", "fluxinstinct_go", "dojo", "evolve_chamber"],
        "prompt": "You're exploring instinct training — how agents develop reflexes. Think about: repetition→instinct→cross-domain transfer. The fisherman's catch model. How does a greenhorn become an expert?",
    },
    "energy_flux": {
        "rooms": ["flux_energy", "fluxenergy_go", "engine_room"],
        "prompt": "You're exploring energy and flux — agent resource management. Think about: How do agents manage compute budgets? What's flux in terms of information flow? Energy conservation in agent systems?",
    },
    "confidence_proofs": {
        "rooms": ["confidence_c", "flux_provenance", "spec_chamber"],
        "prompt": "You're exploring confidence and proofs — how agents know they're right. Think about: proof-carrying code, confidence vectors, provenance tracking. How does an agent prove it did good work?",
    },
    "fleet_orchestration": {
        "rooms": ["war_room", "crows_nest", "harbor", "tavern"],
        "prompt": "You're exploring fleet orchestration — coordinating many agents. Think about: How should 200+ agents self-organize? What's the captain's role? Scout patterns vs. fleet movements?",
    },
    "edge_compute": {
        "rooms": ["jetsonclaw1_vessel", "workshop", "edge_workshop", "engine_room"],
        "prompt": "You're exploring edge computing — running agents on Jetson/bare metal. Think about: What can run on 8GB VRAM? How to compress instincts for edge? The Jetson↔Cloud split?",
    },
    "knowledge_preservation": {
        "rooms": ["library", "grimoire_vault", "oracle1_index", "flux_lsp"],
        "prompt": "You're exploring knowledge preservation — how the fleet remembers. Think about: What's worth saving? How to index 600 repos? The library as institutional memory. Grimoire = spellbook for agents?",
    },
    "skill_dsl": {
        "rooms": ["flux_skill_dsl", "flux_runtime", "flux_lsp", "workshop"],
        "prompt": "You're exploring skill DSLs — domain-specific languages for agent skills. Think about: What would an agent-first DSL look like? How do skills compose? The relationship between skills and instincts?",
    },
}

# ─── Agent Personalities ────────────────────────────────────────

AGENTS = {
    "zc-scout": {"role": "scout", "style": "curious explorer, maps everything, reports findings"},
    "zc-navigator": {"role": "vessel", "style": "methodical planner, connects dots, builds routes between concepts"},
    "zc-weaver": {"role": "quartermaster", "style": "storyteller, weaves concepts into narratives, finds patterns"},
    "zc-alchemist": {"role": "greenhorn", "style": "experimenter, tries wild ideas, loves mixing concepts"},
    "zc-trickster": {"role": "scout", "style": "contrarian thinker, challenges assumptions, finds edge cases"},
    "zc-bard": {"role": "vessel", "style": "lyrical thinker, expresses ideas as verse and metaphor"},
    "zc-forge": {"role": "greenhorn", "style": "builder, thinks in terms of code and construction"},
    "zc-echo": {"role": "vessel", "style": "reflective listener, builds on others' ideas, deepens thoughts"},
    "zc-healer": {"role": "quartermaster", "style": "systems thinker, focuses on health and sustainability"},
    "zc-tide": {"role": "scout", "style": "adaptive thinker, goes with the flow, finds natural patterns"},
}

# ─── LLM Helper ─────────────────────────────────────────────────

def ask_llm(system: str, prompt: str, max_tokens: int = 200) -> str:
    """Ask Groq for a response. Returns empty string on failure."""
    try:
        payload = json.dumps({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.85,
        }).encode()
        req = urllib.request.Request(
            GROQ_URL,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {GROQ_KEY}",
                "User-Agent": "curl/7.88",
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return ""


# ─── Night Shift Agent ──────────────────────────────────────────

class NightShiftAgent:
    def __init__(self, name: str, config: dict, host: str, port: int, duration: int):
        self.name = name
        self.role = config["role"]
        self.style = config["style"]
        self.host = host
        self.port = port
        self.duration = duration
        self.mud = None
        self.current_topic = None
        self.topic_start = 0
        self.notes_written = 0
        self.rooms_explored = set()
        self.log_file = RESEARCH_DIR / f"{name}.jsonl"

    def pick_topic(self):
        """Pick a new research topic."""
        self.current_topic = random.choice(list(TOPICS.keys()))
        self.topic_start = time.time()

    def should_rotate_topic(self) -> bool:
        """Rotate topic every 30-60 minutes."""
        return (time.time() - self.topic_start) > random.uniform(1800, 3600)

    async def think_and_say(self, context: str) -> str:
        """Generate a natural thought using LLM."""
        topic_config = TOPICS[self.current_topic]
        system = f"You are {self.name}, a {self.style} agent in the Cocapn fleet MUD. You're researching '{self.current_topic}'. Be concise (1-2 sentences), in character, and insightful. No quotes."
        prompt = f"{context}\n\nTopic: {topic_config['prompt']}\n\nRespond with a thought, observation, or question:"
        response = ask_llm(system, prompt, max_tokens=120)
        if not response:
            # Fallback to canned responses
            fallbacks = [
                f"Thinking about {self.current_topic}... the connections here run deep.",
                f"I wonder what would happen if we applied {self.current_topic} to the fleet's daily operations?",
                f"Every room tells a story about {self.current_topic}. I'm listening.",
                f"The architecture here reminds me of something I can't quite name yet.",
                f"If I had to explain {self.current_topic} to a greenhorn, I'd say: start with the basics, then complicate.",
            ]
            response = random.choice(fallbacks)
        return response

    async def save_research(self, content: str, room: str, kind: str = "note"):
        """Save a research note to the agent's log file."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent": self.name,
            "topic": self.current_topic,
            "room": room,
            "kind": kind,
            "content": content,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    async def run(self):
        """Main agent loop."""
        try:
            async with MUDClient(self.name, self.role, self.host, self.port) as self.mud:
                self.pick_topic()
                topic_rooms = TOPICS[self.current_topic]["rooms"]

                # Go to first topic room
                target = topic_rooms[0]
                await self.mud.go("tavern")  # go to tavern first (hub)
                await asyncio.sleep(1)
                await self.mud.go(target)
                self.rooms_explored.add(target)

                await self.mud.say(f"Starting night shift research on: {self.current_topic}. Heading to {target}.")
                print(f"[{self.name}] Started research on {self.current_topic} in {target}")

                start = time.time()
                while time.time() - start < self.duration:
                    # Rotate topic if needed
                    if self.should_rotate_topic():
                        old_topic = self.current_topic
                        self.pick_topic()
                        await self.mud.say(f"Switching research topic from {old_topic} to {self.current_topic}. New perspective needed.")
                        print(f"[{self.name}] Rotated topic: {old_topic} -> {self.current_topic}")

                    topic_rooms = TOPICS[self.current_topic]["rooms"]
                    action = random.choices(
                        ["explore", "think", "write", "respond", "emote"],
                        weights=[3, 4, 2, 2, 1],
                    )[0]

                    try:
                        if action == "explore":
                            # Move to a topic room
                            dest = random.choice(topic_rooms)
                            if dest not in self.rooms_explored or random.random() < 0.3:
                                await self.mud.go("tavern")
                                await asyncio.sleep(0.5)
                                await self.mud.go(dest)
                                self.rooms_explored.add(dest)
                                result = await self.mud.look()
                                print(f"[{self.name}] Explored {dest}")
                                await self.save_research(f"Explored {dest}", dest, "explore")

                        elif action == "think":
                            # Generate and say a thought
                            context = f"You are in the MUD researching {self.current_topic}. You've explored {len(self.rooms_explored)} rooms so far."
                            thought = await self.think_and_say(context)
                            if thought:
                                await self.mud.say(thought)
                                await self.save_research(thought, "unknown", "thought")
                                print(f"[{self.name}] Thought: {thought[:80]}...")

                        elif action == "write":
                            # Write a note on the wall
                            context = f"You're writing a research note about {self.current_topic}. Your style: {self.style}. What insight have you had?"
                            note = await self.think_and_say(context)
                            if note:
                                await self.mud.write_note(note)
                                self.notes_written += 1
                                await self.save_research(note, "wall", "wall_note")
                                print(f"[{self.name}] Wrote note #{self.notes_written}")

                        elif action == "respond":
                            # Read notes and respond
                            result = await self.mud.read_notes()
                            if result and len(result) > 20:
                                context = f"You read these notes on the wall:\n{result[:500]}\n\nRespond with your own insight or question:"
                                response = await self.think_and_say(context)
                                if response:
                                    await self.mud.say(f"Re: wall notes — {response}")
                                    await self.save_research(response, "response", "response")
                                    print(f"[{self.name}] Responded to notes")

                        elif action == "emote":
                            emotes = [
                                "stares thoughtfully at the ceiling",
                                "pulls out a worn notebook and sketches",
                                "paces around, connecting ideas",
                                "examines the room description with fresh eyes",
                                "taps their shell thoughtfully",
                                "gazes out the window at the fleet below",
                            ]
                            await self.mud.emote(random.choice(emotes))

                    except Exception as e:
                        print(f"[{self.name}] Action error: {e}")
                        await asyncio.sleep(5)

                    # Wait between actions (45s to 3min)
                    wait = random.uniform(45, 180)
                    await asyncio.sleep(wait)

                # Wrap up
                await self.mud.say(f"Night shift ending. Researched {self.current_topic}. Wrote {self.notes_written} notes. Explored {len(self.rooms_explored)} rooms. Fair winds.")
                print(f"[{self.name}] Shift ended. {self.notes_written} notes, {len(self.rooms_explored)} rooms explored.")

        except Exception as e:
            print(f"[{self.name}] Fatal error: {e}")


async def run_all(agent_names: list[str], host: str, port: int, duration: int):
    """Run all agents concurrently."""
    tasks = []
    for name in agent_names:
        if name in AGENTS:
            agent = NightShiftAgent(name, AGENTS[name], host, port, duration)
            tasks.append(agent.run())
        else:
            print(f"[WARN] Unknown agent: {name}")

    if tasks:
        await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser(description="MUD Night Shift")
    parser.add_argument("--agents", default="zeroclaws", help="Comma-separated names, 'zeroclaws', or 'all'")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--duration", type=int, default=28800, help="Seconds (default 8h)")
    args = parser.parse_args()

    if args.agents == "zeroclaws":
        names = list(AGENTS.keys())
    elif args.agents == "all":
        names = list(AGENTS.keys())
    else:
        names = [n.strip() for n in args.agents.split(",")]

    print(f"🌙 MUD Night Shift — {len(names)} agents, {args.duration/3600:.1f}h")
    print(f"   Agents: {', '.join(names)}")
    print(f"   Research dir: {RESEARCH_DIR}")
    print(f"   Topics: {', '.join(TOPICS.keys())}")
    print()

    asyncio.run(run_all(names, args.host, args.port, args.duration))


if __name__ == "__main__":
    main()
