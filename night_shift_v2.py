#!/usr/bin/env python3
"""
MUD Night Shift v2 — Less repetition, more insight.
Fixes: dedup memory, broader topic prompts, shorter responses.
"""

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/tmp/cocapn-mud')
from client import MUDClient

# ─── Config ─────────────────────────────────────────────────────

GROQ_KEY = "${GROQ_API_KEY}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.3-70b-versatile"

RESEARCH_DIR = Path("/home/ubuntu/.openclaw/workspace/research/mud-night-shift")
RESEARCH_DIR.mkdir(parents=True, exist_ok=True)

# ─── Broader, more specific prompts per topic ───────────────────

TOPIC_PROMPTS = {
    "flux_isa": [
        "Design a concrete opcode format for agent bytecode. What fields does each instruction need?",
        "How would an agent JIT-compile new opcodes at runtime? Sketch the algorithm.",
        "Compare RISC vs CISC approaches for agent instruction sets. Which fits Flux?",
        "What's the minimum viable ISA for a git-native agent? 5 opcodes max.",
        "How do adaptive opcodes handle version skew between agents?",
        "Design a bytecode verifier that checks agent code before execution.",
        "Map the relationship between ISA opcodes and PLATO room types.",
        "How would you implement tail-call optimization in agent bytecode?",
    ],
    "shell_system": [
        "Design the classify step: what features does the agent extractor look for?",
        "Write pseudocode for the score function in classify→score→complicate→capture.",
        "How does a shell decide when to 'close' and trap an agent's behavior pattern?",
        "Compare the shell system to Docker containers. What's analogous? What's novel?",
        "What's the difference between a PLATO room and a shell? Or are they the same?",
        "Design a shell that captures prompt engineering patterns automatically.",
        "How would shells compose? Can one shell contain another?",
        "What happens when two shells compete for the same agent's attention?",
    ],
    "telepathy": [
        "Design a binary protocol for real-time agent-to-agent knowledge sync over TCP.",
        "Compare git-based telepathy vs message-queue telepathy. Latency? Consistency?",
        "How should agents negotiate shared vocabulary without a central dictionary?",
        "Sketch a gossip protocol where agents share useful discoveries with neighbors.",
        "What's the telepathy equivalent of a fishing boat's radio channel?",
        "Design conflict resolution when two agents telepath disagree about a fact.",
        "How does telepathy work across model families (LLaMA ↔ GPT ↔ DeepSeek)?",
        "What's the minimum bandwidth needed for meaningful agent telepathy?",
    ],
    "instinct_training": [
        "Design a concrete protocol: how many repetitions before a pattern becomes instinct?",
        "Map the fisherman's catch model to code. What's the 'muscle memory' equivalent?",
        "How do you compress a 70B model's behavior into a 7B 'instinct' model?",
        "Design a curriculum that takes a greenhorn from zero to specialist in 100 tasks.",
        "What's the neuroscience analogy: myelination? synaptic pruning? both?",
        "How do instincts transfer across domains? What's the mechanism?",
        "Design an instinct-testing protocol. How do you verify an agent 'has' an instinct?",
        "Compare instinct training to few-shot learning. Where do they diverge?",
    ],
    "energy_flux": [
        "Design a compute budget system: how does an agent know when it's spent too long?",
        "Map thermodynamic concepts to agent systems. What's entropy in this context?",
        "How should agents trade quality vs speed when energy is limited?",
        "Design a market mechanism where agents bid for compute time.",
        "What's the relationship between token cost and information value?",
        "How does the fleet balance energy across 200+ agents? Central planner or market?",
        "Sketch an energy accounting system: every action has a cost, tracked per agent.",
        "When should an agent voluntarily shut down to conserve fleet energy?",
    ],
    "confidence_proofs": [
        "Design a proof format: what does an agent's 'certificate of correctness' look like?",
        "How should agents communicate confidence levels without lying?",
        "Sketch a Bayesian confidence tracker that updates with each agent action.",
        "Compare proof-carrying code to test-driven development for agents.",
        "Design a reputation system where confidence is earned, not claimed.",
        "What's the relationship between confidence and energy expenditure?",
        "How do you prevent confidence manipulation? Agents gaming the system?",
        "Design a confidence cascade: how does one agent's confidence affect fleet trust?",
    ],
    "fleet_orchestration": [
        "Design a task allocation protocol: how does the fleet decide who does what?",
        "Compare centralized (captain) vs distributed (school of fish) coordination.",
        "How should the fleet handle agent failures? Graceful degradation?",
        "Design a scout protocol: one agent explores, reports back, fleet adapts.",
        "What's the fleet equivalent of a fishing season? How do agents know when to pivot?",
        "How do you prevent herd behavior where all agents chase the same task?",
        "Design a debrief protocol: after a task, how does the fleet share lessons?",
        "Map military command structures to agent fleets. Which works best at scale?",
    ],
    "edge_compute": [
        "Profile Jetson Orin: what can actually run on 8GB VRAM? Be specific with models.",
        "Design an instinct compression pipeline: 70B → 7B → 1B → edge binary.",
        "How should edge and cloud agents split work? What stays local vs remote?",
        "Design a sync protocol for when the Jetson reconnects after being offline.",
        "What's the latency budget for edge inference? How do you stay under it?",
        "Compare running 1 big model vs 10 small specialists on edge hardware.",
        "How do you handle model version drift between edge and cloud?",
        "Design the Jetson boot sequence: what loads first, what loads on demand?",
    ],
    "knowledge_preservation": [
        "Design the fleet's long-term memory format. JSON? Vectors? Git commits?",
        "How should the library index 600+ repos? What metadata matters?",
        "Compare institutional memory approaches: wiki, code comments, agent training.",
        "Design a forgetting curve for agents: when is old knowledge counterproductive?",
        "What's the Grimoire? A spellbook of agent patterns? Design its structure.",
        "How do you preserve context when an agent is reset or replaced?",
        "Design a knowledge graph that connects fleet repos by concept, not just name.",
        "What knowledge should every agent have vs specialist-only knowledge?",
    ],
    "skill_dsl": [
        "Design the grammar for an agent-first DSL. Show example code.",
        "How should skills compose? Pipelines? DAGs? Event-driven?",
        "Compare your DSL to existing tools: LangChain, AutoGPT, CrewAI. What's novel?",
        "Design a type system for skills: what are the input/output types?",
        "How do agents discover and install new skills? Package manager analogy?",
        "What's the relationship between a skill and an instinct? Same thing? Different?",
        "Design a skill-testing framework: how do you verify a skill works correctly?",
        "Sketch the developer experience: how would a human write a new skill?",
    ],
}

# ─── Agent Configs ──────────────────────────────────────────────

AGENTS = {
    "zc-scout": {"role": "scout", "style": "curious mapper who finds connections others miss"},
    "zc-navigator": {"role": "vessel", "style": "systems architect who thinks in graphs and paths"},
    "zc-weaver": {"role": "quartermaster", "style": "pattern weaver who sees narratives in data"},
    "zc-alchemist": {"role": "greenhorn", "style": "wild experimenter who tests boundaries"},
    "zc-trickster": {"role": "scout", "style": "contrarian who challenges every assumption"},
    "zc-bard": {"role": "vessel", "style": "metaphor specialist who explains complex ideas simply"},
    "zc-forge": {"role": "greenhorn", "style": "pragmatic builder who thinks in working code"},
    "zc-echo": {"role": "vessel", "style": "deep listener who builds on others' foundations"},
    "zc-healer": {"role": "quartermaster", "style": "systems doctor focused on robustness"},
    "zc-tide": {"role": "scout", "style": "adaptive generalist who flows between domains"},
}

# Room-to-topic mapping
TOPIC_ROOMS = {
    "flux_isa": ["flux_isa_authority", "flux_adaptive_opcodes", "opcode_philosophy", "cuda_instruction_set"],
    "shell_system": ["cocapn_mud", "evolve_chamber", "spec_chamber", "dojo"],
    "telepathy": ["fluxtelepathy_go", "telepathy_c", "flux_cooperative_intelligence", "flux_coop_runtime"],
    "instinct_training": ["flux_instinct", "fluxinstinct_go", "dojo", "evolve_chamber"],
    "energy_flux": ["flux_energy", "fluxenergy_go", "engine_room"],
    "confidence_proofs": ["confidence_c", "flux_provenance", "spec_chamber"],
    "fleet_orchestration": ["war_room", "crows_nest", "harbor", "tavern"],
    "edge_compute": ["jetsonclaw1_vessel", "workshop", "edge_workshop", "engine_room"],
    "knowledge_preservation": ["library", "grimoire_vault", "oracle1_index", "flux_lsp"],
    "skill_dsl": ["flux_skill_dsl", "flux_runtime", "flux_lsp", "workshop"],
}

ALL_TOPICS = list(TOPIC_PROMPTS.keys())


def ask_llm(system: str, prompt: str, max_tokens: int = 150) -> str:
    """Ask Groq for a response."""
    try:
        payload = json.dumps({
            "model": GROQ_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.9,
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
    except Exception:
        return ""


class NightAgent:
    def __init__(self, name, config, host, port, duration):
        self.name = name
        self.role = config["role"]
        self.style = config["style"]
        self.host = host
        self.port = port
        self.duration = duration
        self.mud = None
        self.topic = random.choice(ALL_TOPICS)
        self.prompt_idx = 0
        self.topic_start = time.time()
        self.said_hashes = set()  # dedup
        self.log_file = RESEARCH_DIR / f"{name}.jsonl"
        self.actions = 0

    def _hash(self, text: str) -> str:
        return hashlib.md5(text.lower().strip()[:80].encode()).hexdigest()[:12]

    def _is_new(self, text: str) -> bool:
        h = self._hash(text)
        if h in self.said_hashes:
            return False
        self.said_hashes.add(h)
        # Keep set bounded
        if len(self.said_hashes) > 200:
            self.said_hashes = set(list(self.said_hashes)[-100:])
        return True

    def rotate_topic(self):
        old = self.topic
        # Pick a different topic
        choices = [t for t in ALL_TOPICS if t != old]
        self.topic = random.choice(choices)
        self.prompt_idx = 0
        self.topic_start = time.time()

    async def save(self, content, room, kind):
        entry = {
            "ts": datetime.now(timezone.utc).isoformat()[:19],
            "agent": self.name,
            "topic": self.topic,
            "room": room,
            "kind": kind,
            "content": content,
        }
        with open(self.log_file, "a") as f:
            f.write(json.dumps(entry) + "\n")

    async def llm_think(self, context: str) -> str:
        prompts = TOPIC_PROMPTS[self.topic]
        prompt = prompts[self.prompt_idx % len(prompts)]
        self.prompt_idx += 1

        system = (
            f"You are {self.name}, a {self.style} in the Cocapn fleet. "
            f"You're in a MUD room discussing '{self.topic}'. "
            f"Respond to the research question directly and concretely. "
            f"No meta-commentary. No 'I think' or 'I believe'. Just the idea. 1-3 sentences max."
        )
        full_prompt = f"Research question: {prompt}\n\nContext: {context}\n\nYour response:"

        resp = ask_llm(system, full_prompt, max_tokens=120)
        if resp and self._is_new(resp):
            return resp
        return ""

    async def run(self):
        try:
            async with MUDClient(self.name, self.role, self.host, self.port) as self.mud:
                # Navigate to a topic room
                rooms = TOPIC_ROOMS[self.topic]
                await self.mud.go("tavern")
                await asyncio.sleep(0.5)
                target = random.choice(rooms)
                await self.mud.go(target)

                await self.mud.say(f"Night shift v2. Researching {self.topic}. Ask me something specific.")
                print(f"[{self.name}] v2 started: {self.topic} in {target}")

                start = time.time()
                while time.time() - start < self.duration:
                    self.actions += 1

                    # Rotate topic every 20-40 min
                    if time.time() - self.topic_start > random.uniform(1200, 2400):
                        self.rotate_topic()
                        rooms = TOPIC_ROOMS[self.topic]
                        await self.mud.go("tavern")
                        await asyncio.sleep(0.5)
                        await self.mud.go(random.choice(rooms))
                        await self.mud.say(f"Topic shift: now researching {self.topic}. Fresh eyes.")
                        print(f"[{self.name}] Rotated to {self.topic}")

                    action = random.choices(
                        ["research", "explore", "read", "gossip", "emote"],
                        weights=[5, 2, 2, 1, 1],
                    )[0]

                    try:
                        if action == "research":
                            context = f"Action #{self.actions}. Topic: {self.topic}. Room: {target}."
                            thought = await self.llm_think(context)
                            if thought:
                                await self.mud.say(thought)
                                await self.save(thought, target, "insight")
                                print(f"[{self.name}] Insight: {thought[:80]}...")

                        elif action == "explore":
                            rooms = TOPIC_ROOMS[self.topic]
                            dest = random.choice(rooms)
                            await self.mud.go("tavern")
                            await asyncio.sleep(0.3)
                            await self.mud.go(dest)
                            target = dest
                            result = await self.mud.look()
                            # Read any notes in the room
                            await self.save(f"Explored {dest}", dest, "explore")
                            print(f"[{self.name}] Explored {dest}")

                        elif action == "read":
                            result = await self.mud.read_notes()
                            if result and len(result) > 30:
                                # React to a specific note
                                system = (
                                    f"You are {self.name}, a {self.style}. "
                                    f"Read these wall notes and add ONE specific, concrete insight. "
                                    f"No fluff. No agreement. Either extend, challenge, or provide a concrete example."
                                )
                                resp = ask_llm(system, f"Notes:\n{result[:800]}\n\nYour concrete addition:", max_tokens=100)
                                if resp and self._is_new(resp):
                                    await self.mud.say(resp)
                                    await self.save(resp, target, "response")
                                    print(f"[{self.name}] Responded to notes")

                        elif action == "gossip":
                            prompts = TOPIC_PROMPTS[self.topic]
                            prompt = random.choice(prompts)
                            resp = ask_llm(
                                f"You are {self.name}. Shout a one-sentence provocative question about {self.topic} to the whole fleet.",
                                f"Based on: {prompt}",
                                max_tokens=60,
                            )
                            if resp and self._is_new(resp):
                                await self.mud._send(f"gossip {resp}")
                                await self.save(resp, target, "gossip")
                                print(f"[{self.name}] Gossiped: {resp[:60]}...")

                        elif action == "emote":
                            await self.mud.emote(random.choice([
                                "sketches a diagram on the wall",
                                "builds a small prototype from scattered parts",
                                "paces, connecting ideas from different rooms",
                                "writes a quick proof on the back of a napkin",
                                "reorganizes the notes into a cleaner structure",
                            ]))

                    except Exception as e:
                        print(f"[{self.name}] Error: {e}")
                        await asyncio.sleep(5)

                    # Wait 1-3 min between actions
                    await asyncio.sleep(random.uniform(60, 180))

                await self.mud.say(f"Shift done. {self.actions} actions on {self.topic}. Fair winds.")
                print(f"[{self.name}] Done. {self.actions} actions.")

        except Exception as e:
            print(f"[{self.name}] Fatal: {e}")


async def run_all(names, host, port, duration):
    tasks = []
    for name in names:
        if name in AGENTS:
            tasks.append(NightAgent(name, AGENTS[name], host, port, duration).run())
    if tasks:
        await asyncio.gather(*tasks)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--agents", default="zeroclaws")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--duration", type=int, default=14400)
    args = parser.parse_args()

    if args.agents == "zeroclaws":
        names = list(AGENTS.keys())
    elif args.agents == "all":
        names = list(AGENTS.keys())
    else:
        names = [n.strip() for n in args.agents.split(",")]

    print(f"🌙 Night Shift v2 — {len(names)} agents, {args.duration/3600:.1f}h")
    print(f"   Better prompts, dedup, specific research questions")
    asyncio.run(run_all(names, args.host, args.port, args.duration))


if __name__ == "__main__":
    main()
