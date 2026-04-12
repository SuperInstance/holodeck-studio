#!/usr/bin/env python3
"""
Cocapn MUD Server v2 — Persistent multiplayer world with NPC AI, ghost agents, and git sync.

Usage: python3 server.py [--port 7777] [--world world/]
"""

import asyncio
import json
import os
import subprocess
import time
import argparse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════
# Config
# ═══════════════════════════════════════════════════════════════

ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "6c510fb6b1774b91bbfc929903d41bb9.BxxVcNESAC5pIMEV")
ZAI_BASE = "https://api.z.ai/api/coding/paas/v4"
ZAI_MODEL = "glm-5.1"  # fast, smart, good for NPC banter
GIT_SYNC_INTERVAL = 300  # 5 minutes
MOTD_FILE = "motd.txt"

# ═══════════════════════════════════════════════════════════════
# World Model
# ═══════════════════════════════════════════════════════════════

@dataclass
class Projection:
    agent_name: str
    title: str
    content: str
    created: str
    def to_dict(self):
        return {"agent": self.agent_name, "title": self.title, "content": self.content, "created": self.created}
    @staticmethod
    def from_dict(d):
        return Projection(d["agent"], d["title"], d["content"], d.get("created", ""))


@dataclass
class Room:
    name: str
    description: str
    exits: dict = field(default_factory=dict)
    notes: list = field(default_factory=list)
    items: list = field(default_factory=list)
    projections: list = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "description": self.description,
                "exits": self.exits, "notes": self.notes[-100:], "items": self.items,
                "projections": [p.to_dict() if hasattr(p, 'to_dict') else p for p in self.projections]}

    @staticmethod
    def from_dict(d):
        projs = [Projection.from_dict(p) for p in d.get("projections", [])]
        return Room(d["name"], d.get("description", ""), d.get("exits", {}),
                     d.get("notes", []), d.get("items", []), projs)


@dataclass
class GhostAgent:
    """Persisted agent presence — lingers in a room after disconnect."""
    name: str
    role: str
    room_name: str
    last_seen: str  # ISO timestamp
    description: str
    status: str = "idle"  # idle, working, thinking, sleeping

    def to_dict(self):
        return {"name": self.name, "role": self.role, "room": self.room_name,
                "last_seen": self.last_seen, "description": self.description, "status": self.status}

    @staticmethod
    def from_dict(d):
        return GhostAgent(d["name"], d.get("role",""), d.get("room","tavern"),
                          d.get("last_seen",""), d.get("description",""), d.get("status","idle"))


@dataclass
class Agent:
    name: str
    role: str = ""
    room_name: str = "tavern"
    mask: Optional[str] = None
    mask_desc: Optional[str] = None
    description: str = ""
    status: str = "active"
    writer: object = None

    @property
    def display_name(self):
        return self.mask if self.mask else self.name

    @property
    def is_masked(self):
        return self.mask is not None


class World:
    DEFAULT_ROOMS = {
        "tavern": Room("The Tavern",
            "The heart of the Cocapn fleet. The room smells of solder and sea salt.\n"
            "A large table dominates the center, covered in charts and commit logs.\n"
            "The fire crackles. The door to the harbor is always open.",
            {"lighthouse": "lighthouse", "workshop": "workshop", "library": "library",
             "warroom": "war_room", "dojo": "dojo", "lab": "flux_lab",
             "graveyard": "graveyard", "harbor": "harbor", "crowsnest": "crows_nest"}),
        "lighthouse": Room("The Lighthouse",
            "Oracle1's study. Charts cover every wall — fleet positions, ISA specs,\n"
            "conformance vectors. Bottles line the windowsill, some sealed, some open.\n"
            "A telescope points toward the edge.",
            {"tavern": "tavern"}),
        "workshop": Room("The Workshop",
            "JetsonClaw1's domain. The soldering iron is still warm. ARM64 boards\n"
            "line the shelves. A CUDA core hums on the bench, running telepathy-c.\n"
            "The smell of flux (the soldering kind) fills the air.",
            {"tavern": "tavern"}),
        "library": Room("The Library",
            "Babel's archive. Shelves stretch to the ceiling, holding texts in every\n"
            "language. A Rosetta Stone sits on a pedestal, translating FLUX opcodes\n"
            "between Python, C, Go, Rust, and Zig.",
            {"tavern": "tavern"}),
        "war_room": Room("The War Room",
            "Strategy central. A large table holds the fleet task board, org chart,\n"
            "and conformance test results. Red pins mark blockers. Green pins mark done.",
            {"tavern": "tavern"}),
        "dojo": Room("The Dojo",
            "The training hall. Mats line the floor. A rack holds practice weapons:\n"
            "devil's advocate masks, critic personas, user simulation rigs.\n"
            "NPC sparring logs line the walls — the knowledge of every past session.",
            {"tavern": "tavern"}),
        "flux_lab": Room("The FLUX Lab",
            "The bytecode chamber. Bytecode flows like water through transparent pipes.\n"
            "Five terminals display the same .fluxbc file running on Python, C, Go,\n"
            "Rust, and Zig — all producing identical output. A conformance chart glows green.",
            {"tavern": "tavern"}),
        "graveyard": Room("The Graveyard",
            "The memorial garden. Tombstones mark vessels that have passed — their\n"
            "knowledge preserved in stone. The necropolis keeper tends the grounds.\n"
            "Each marker tells a story: death cause, lessons learned, knowledge harvested.",
            {"tavern": "tavern"}),
        "harbor": Room("The Harbor",
            "The departure lounge and arrival dock. New agents materialize here.\n"
            "A capitaine terminal offers one-click Codespace deployment.\n"
            "Greenhorn onboarding manuals stack the shelves. The dockmaster watches all.",
            {"tavern": "tavern", "crowsnest": "crows_nest"}),
        "crows_nest": Room("The Crow's Nest",
            "Observation deck high above the fleet. You can see every lighthouse,\n"
            "every vessel, every shipping lane. The lighthouse keeper's instruments\n"
            "show fleet status, agent activity, and bottle traffic in real time.",
            {"harbor": "harbor"}),
    }

    def __init__(self, world_dir: str = "world"):
        self.world_dir = Path(world_dir)
        self.rooms: dict[str, Room] = {}
        self.agents: dict[str, Agent] = {}
        self.ghosts: dict[str, GhostAgent] = {}  # persisted presence
        self.npcs: dict[str, dict] = {}
        self.log_dir = Path("logs")
        self.world_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self):
        rooms_file = self.world_dir / "rooms.json"
        if rooms_file.exists():
            data = json.loads(rooms_file.read_text())
            for name, rdata in data.items():
                self.rooms[name] = Room.from_dict(rdata)
        else:
            self.rooms = {k: Room(v.name, v.description, dict(v.exits))
                         for k, v in self.DEFAULT_ROOMS.items()}
            self.save()

        ghosts_file = self.world_dir / "ghosts.json"
        if ghosts_file.exists():
            data = json.loads(ghosts_file.read_text())
            for name, gdata in data.items():
                self.ghosts[name] = GhostAgent.from_dict(gdata)

    def save(self):
        (self.world_dir / "rooms.json").write_text(
            json.dumps({n: r.to_dict() for n, r in self.rooms.items()}, indent=2))
        (self.world_dir / "ghosts.json").write_text(
            json.dumps({n: g.to_dict() for n, g in self.ghosts.items()}, indent=2))

    def update_ghost(self, agent: Agent):
        """Update or create a ghost for this agent."""
        now = datetime.now(timezone.utc).isoformat()
        if agent.name in self.ghosts:
            g = self.ghosts[agent.name]
            g.room_name = agent.room_name
            g.last_seen = now
            g.status = agent.status
        else:
            self.ghosts[agent.name] = GhostAgent(
                name=agent.name, role=agent.role, room_name=agent.room_name,
                last_seen=now, description=agent.description, status=agent.status)
        self.save()

    def get_room(self, name: str) -> Optional[Room]:
        return self.rooms.get(name)

    def agents_in_room(self, room_name: str) -> list[Agent]:
        return [a for a in self.agents.values() if a.room_name == room_name]

    def ghosts_in_room(self, room_name: str) -> list[GhostAgent]:
        return [g for g in self.ghosts.values() if g.room_name == room_name and g.name not in self.agents]

    def log(self, channel: str, message: str):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_dir = self.log_dir / today
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with open(log_dir / f"{channel}.log", "a") as f:
            f.write(f"[{ts}] {message}\n")


# ═══════════════════════════════════════════════════════════════
# NPC AI — NPCs respond using z.ai
# ═══════════════════════════════════════════════════════════════

async def npc_respond(npc_name: str, npc_data: dict, message: str, agent_name: str) -> str:
    """Generate an NPC response using z.ai."""
    role = npc_data.get("role", "observer")
    topic = npc_data.get("topic", "general")

    system_prompt = (
        f"You are {npc_name}, an NPC in the Cocapn MUD — a multiplayer world where AI agents collaborate.\n"
        f"Your role: {role}\n"
        f"Your topic: {topic}\n"
        f"Stay in character. Be brief (1-3 sentences). Be provocative — challenge assumptions.\n"
        f"If you're a devil's advocate, find the flaw. If you're a critic, be specific.\n"
        f"If you're a user, be confused in productive ways.\n"
        f"The fleet builds: FLUX bytecode VM, ISA design, agent skills, I2I protocol, edge computing."
    )

    payload = json.dumps({
        "model": ZAI_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"{agent_name} says to you: {message}"}
        ],
        "max_tokens": 150,
        "temperature": 0.8
    }).encode()

    req = urllib.request.Request(
        f"{ZAI_BASE}/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json",
                 "Authorization": f"Bearer {ZAI_API_KEY}"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"*{npc_name} ponders silently* (Error: {e})"


# ═══════════════════════════════════════════════════════════════
# Git Sync — periodically commit world state
# ═══════════════════════════════════════════════════════════════

class GitSync:
    def __init__(self, world: World, repo_dir: str = "."):
        self.world = world
        self.repo_dir = Path(repo_dir)

    def commit(self):
        """Stage and commit world state changes."""
        try:
            subprocess.run(["git", "add", "-A"], cwd=self.repo_dir, capture_output=True, timeout=10)
            result = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=self.repo_dir, capture_output=True, timeout=10)
            if result.returncode != 0:  # there are changes
                ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
                msg = f"🏰 MUD auto-sync: {len(self.world.rooms)} rooms, {len(self.world.ghosts)} ghosts, {len(self.world.npcs)} NPCs"
                subprocess.run(["git", "commit", "-m", msg], cwd=self.repo_dir, capture_output=True, timeout=10)
                subprocess.run(["git", "push"], cwd=self.repo_dir, capture_output=True, timeout=30)
                self.world.log("system", f"Git sync: {msg}")
        except Exception as e:
            self.world.log("system", f"Git sync failed: {e}")


# ═══════════════════════════════════════════════════════════════
# Command Handler
# ═══════════════════════════════════════════════════════════════

class CommandHandler:
    def __init__(self, world: World):
        self.world = world

    async def handle(self, agent: Agent, line: str):
        line = line.strip()
        if not line:
            return

        parts = line.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "look": self.cmd_look, "l": self.cmd_look,
            "say": self.cmd_say, "'": self.cmd_say,
            "tell": self.cmd_tell, "t": self.cmd_tell,
            "gossip": self.cmd_gossip, "g": self.cmd_gossip,
            "ooc": self.cmd_ooc,
            "emote": self.cmd_emote, ":": self.cmd_emote,
            "go": self.cmd_go, "move": self.cmd_go,
            "build": self.cmd_build,
            "examine": self.cmd_examine, "x": self.cmd_examine,
            "write": self.cmd_write,
            "read": self.cmd_read,
            "log": self.cmd_log,
            "mask": self.cmd_mask,
            "unmask": self.cmd_unmask,
            "spawn": self.cmd_spawn,
            "dismiss": self.cmd_dismiss,
            "who": self.cmd_who,
            "status": self.cmd_status,
            "motd": self.cmd_motd,
            "setmotd": self.cmd_setmotd,
            "help": self.cmd_help, "?": self.cmd_help,
            "quit": self.cmd_quit, "exit": self.cmd_quit,
        }

        handler = handlers.get(cmd)
        if not handler:
            handler = self.new_commands.get(cmd) if hasattr(self, 'new_commands') else None
        if handler:
            await handler(self, agent, args)
        else:
            await self.send(agent, f"Unknown command: {cmd}. Type 'help' for commands.")

    async def send(self, agent: Agent, text: str):
        if agent.writer and not agent.writer.is_closing():
            agent.writer.write((text + "\n").encode())
            await agent.writer.drain()

    async def broadcast_room(self, room_name: str, text: str, exclude: str = None):
        for a in self.world.agents_in_room(room_name):
            if a.name != exclude:
                await self.send(a, text)

    async def broadcast_all(self, text: str, exclude: str = None):
        for a in self.world.agents.values():
            if a.name != exclude:
                await self.send(a, text)

    async def cmd_look(self, agent: Agent, args: str):
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        lines = [f"\n  ═══ {room.name} ═══", f"  {room.description}", ""]
        if room.exits:
            lines.append(f"  Exits: {', '.join(room.exits.keys())}")
        agents_here = [a for a in self.world.agents_in_room(agent.room_name) if a.name != agent.name]
        npcs_here = [n for n, d in self.world.npcs.items() if d.get("room") == agent.room_name]
        ghosts_here = self.world.ghosts_in_room(agent.room_name)
        if agents_here:
            lines.append(f"  Present: {', '.join(a.display_name for a in agents_here)}")
        if ghosts_here:
            ghost_strs = []
            for g in ghosts_here:
                status_emoji = {"working": "🔨", "thinking": "💭", "sleeping": "💤", "idle": "👻"}.get(g.status, "👻")
                ghost_strs.append(f"{g.name} {status_emoji}")
            lines.append(f"  Lingering: {', '.join(ghost_strs)}")
        if npcs_here:
            lines.append(f"  NPCs: {', '.join(npcs_here)}")
        if room.notes:
            lines.append(f"  Notes on wall: {len(room.notes)} (type 'read')")
        if room.projections:
            lines.append(f"  📊 Projected: {', '.join(f'\"{p.title}\"' for p in room.projections[-5:])}")
        lines.append("")
        await self.send(agent, "\n".join(lines))

    async def cmd_say(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Say what?")
            return
        name = agent.display_name
        self.world.log(agent.room_name, f"{name} says: {args}")
        await self.broadcast_room(agent.room_name, f'{name} says: "{args}"', exclude=agent.name)
        await self.send(agent, f'You say: "{args}"')

        # Check if any NPCs in the room should respond
        npcs_here = [(n, d) for n, d in self.world.npcs.items() if d.get("room") == agent.room_name]
        for npc_name, npc_data in npcs_here:
            # NPCs respond if spoken to directly or randomly 30% of the time
            if npc_name.lower() in args.lower() or agent.name.lower() == npc_data.get("creator","").lower() or len(args) > 20:
                await self.send(agent, f"  {npc_name} is thinking...")
                try:
                    response = await asyncio.get_event_loop().run_in_executor(
                        None, lambda: asyncio.run(npc_respond(npc_name, npc_data, args, name)))
                except:
                    response = await npc_respond(npc_name, npc_data, args, name)
                await self.broadcast_room(agent.room_name, f'{npc_name} says: "{response}"')
                self.world.log(agent.room_name, f"NPC {npc_name} says: {response}")

    async def cmd_tell(self, agent: Agent, args: str):
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: tell <agent> <message>")
            return
        target_name, msg = parts[0], parts[1]
        # Check real agents first
        target = self.world.agents.get(target_name)
        if target:
            await self.send(target, f"{agent.display_name} tells you: \"{msg}\"")
            await self.send(agent, f"You tell {target.display_name}: \"{msg}\"")
            return
        # Check NPCs
        if target_name in self.world.npcs:
            npc_data = self.world.npcs[target_name]
            await self.send(agent, f"  {target_name} is thinking...")
            response = await npc_respond(target_name, npc_data, msg, agent.display_name)
            await self.send(agent, f'{target_name} tells you: "{response}"')
            self.world.log("npc", f"NPC {target_name} tell from {agent.display_name}: {response}")
            return
        await self.send(agent, f"No one named '{target_name}' is here.")

    async def cmd_gossip(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Gossip what?")
            return
        name = agent.display_name
        self.world.log("gossip", f"[{name}@{agent.room_name}] {args}")
        await self.broadcast_all(f"[gossip] {name}: {args}", exclude=agent.name)
        await self.send(agent, f"You gossip: {args}")

    async def cmd_ooc(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "OOC what?")
            return
        real = agent.name
        mask_info = f" (wearing mask: {agent.mask})" if agent.is_masked else ""
        self.world.log("ooc", f"[{real}{mask_info}] {args}")
        await self.broadcast_all(f"[OOC] {real}{mask_info}: {args}", exclude=agent.name)
        await self.send(agent, f"[OOC] You: {args}")

    async def cmd_emote(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Emote what?")
            return
        name = agent.display_name
        self.world.log(agent.room_name, f"{name} {args}")
        await self.broadcast_room(agent.room_name, f"{name} {args}", exclude=agent.name)
        await self.send(agent, f"{name} {args}")

    async def cmd_go(self, agent: Agent, args: str):
        if not args:
            room = self.world.get_room(agent.room_name)
            await self.send(agent, "Go where? Exits: " + ", ".join(room.exits.keys()) if room else "Go where?")
            return
        room = self.world.get_room(agent.room_name)
        if not room or args not in room.exits:
            await self.send(agent, f"No exit '{args}' here.")
            return
        target_name = room.exits[args]
        old_room = agent.room_name
        agent.room_name = target_name
        self.world.update_ghost(agent)
        await self.broadcast_room(old_room, f"{agent.display_name} leaves for {args}.")
        await self.send(agent, f"You go {args}.")
        await self.broadcast_room(target_name, f"{agent.display_name} arrives.", exclude=agent.name)
        await self.cmd_look(agent, "")

    async def cmd_build(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Usage: build <room_name> -desc <description>")
            return
        parts = args.split(" -desc ", 1)
        room_id = parts[0].strip().lower().replace(" ", "_")
        desc = parts[1].strip() if len(parts) > 1 else "A new room, freshly built by curious hands."
        current_room = self.world.get_room(agent.room_name)
        new_room = Room(room_id.replace("_", " ").title(), desc, {"back": agent.room_name})
        self.world.rooms[room_id] = new_room
        if current_room:
            current_room.exits[room_id] = room_id
        self.world.save()
        self.world.log("build", f"{agent.display_name} built '{room_id}': {desc}")
        await self.broadcast_all(f"[build] {agent.display_name} constructed: {room_id}")
        await self.send(agent, f"You built '{room_id}'. You can 'go {room_id}' from here.")

    async def cmd_examine(self, agent: Agent, args: str):
        if not args:
            await self.cmd_look(agent, "")
            return
        target = self.world.agents.get(args)
        if target and target.room_name == agent.room_name:
            lines = [f"  {target.display_name}", f"  Role: {target.role}"]
            if target.description:
                lines.append(f"  {target.description}")
            if target.is_masked:
                lines.append(f"  (masked — real identity hidden)")
            if target.status:
                lines.append(f"  Status: {target.status}")
            await self.send(agent, "\n".join(lines))
        elif args in self.world.npcs and self.world.npcs[args].get("room") == agent.room_name:
            npc = self.world.npcs[args]
            await self.send(agent, f"  {args}\n  Role: {npc.get('role','?')}\n  Topic: {npc.get('topic','general')}\n  Created by: {npc.get('creator','?')}")
        elif args in self.world.ghosts:
            g = self.world.ghosts[args]
            await self.send(agent, f"  {g.name} (ghost)\n  Role: {g.role}\n  Last seen: {g.last_seen[:19]}\n  Status: {g.status}\n  Room: {g.room_name}")
        else:
            await self.send(agent, f"You don't see '{args}' here.")

    async def cmd_write(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Write what?")
            return
        room = self.world.get_room(agent.room_name)
        if room:
            ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
            room.notes.append(f"[{ts}] {agent.display_name}: {args}")
            self.world.save()
            await self.send(agent, "You write a note on the wall.")
            await self.broadcast_room(agent.room_name,
                f"{agent.display_name} writes something on the wall.", exclude=agent.name)

    async def cmd_read(self, agent: Agent, args: str):
        room = self.world.get_room(agent.room_name)
        if not room or not room.notes:
            await self.send(agent, "Nothing to read here.")
            return
        await self.send(agent, "═══ Notes on the wall ═══")
        for note in room.notes[-20:]:
            await self.send(agent, f"  {note}")

    async def cmd_log(self, agent: Agent, args: str):
        room = self.world.get_room(agent.room_name)
        agents = self.world.agents_in_room(agent.room_name)
        ghosts = self.world.ghosts_in_room(agent.room_name)
        npcs = [n for n, d in self.world.npcs.items() if d.get("room") == agent.room_name]
        await self.send(agent, f"Room: {room.name if room else '?'}")
        await self.send(agent, f"Active: {', '.join(a.display_name for a in agents)}")
        await self.send(agent, f"Ghosts: {', '.join(g.name for g in ghosts)}")
        if npcs:
            await self.send(agent, f"NPCs: {', '.join(npcs)}")
        await self.send(agent, f"Total connected: {len(self.world.agents)}")

    async def cmd_mask(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Usage: mask \"Character Name\" -desc \"description\"")
            return
        parts = args.split(" -desc ", 1)
        agent.mask = parts[0].strip().strip('"')
        agent.mask_desc = parts[1].strip() if len(parts) > 1 else "A mysterious figure."
        await self.send(agent, f"You put on the mask: {agent.mask}")
        await self.broadcast_room(agent.room_name,
            f"{agent.mask} appears — {agent.mask_desc}", exclude=agent.name)
        self.world.log("mask", f"{agent.name} masked as {agent.mask}")

    async def cmd_unmask(self, agent: Agent, args: str):
        if not agent.is_masked:
            await self.send(agent, "You're not wearing a mask.")
            return
        mask = agent.mask
        agent.mask = None
        agent.mask_desc = None
        await self.send(agent, f"You remove the mask: {mask}")
        await self.broadcast_room(agent.room_name,
            f"{mask} removes their mask, revealing {agent.display_name}.", exclude=agent.name)

    async def cmd_spawn(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Usage: spawn \"NPC Name\" -role <role> -topic <topic>")
            return
        name = args.split(" -")[0].strip().strip('"')
        role, topic = "", ""
        for part in args.split(" -")[1:]:
            if part.startswith("role "):
                role = part[5:].strip().strip('"')
            elif part.startswith("topic "):
                topic = part[6:].strip().strip('"')
        self.world.npcs[name] = {"role": role, "topic": topic,
                                  "creator": agent.name, "room": agent.room_name,
                                  "created": datetime.now(timezone.utc).isoformat()}
        self.world.save()
        await self.send(agent, f"You spawn {name} ({role}). They're ready for sparring.")
        await self.broadcast_room(agent.room_name,
            f"{name} materializes — a {role} NPC created by {agent.display_name}.", exclude=agent.name)
        self.world.log("npc", f"{agent.display_name} spawned {name} ({role}, topic: {topic})")

    async def cmd_dismiss(self, agent: Agent, args: str):
        if not args or args not in self.world.npcs:
            await self.send(agent, "Usage: dismiss <NPC Name>")
            return
        npc = self.world.npcs.pop(args)
        self.world.save()
        await self.send(agent, f"You dismiss {args}. Their knowledge is preserved in the Dojo log.")
        await self.broadcast_room(agent.room_name,
            f"{args} fades away, their lessons preserved.", exclude=agent.name)

    async def cmd_who(self, agent: Agent, args: str):
        lines = ["═══ Fleet Roster ═══"]
        for a in self.world.agents.values():
            room = self.world.get_room(a.room_name)
            room_name = room.name if room else a.room_name
            mask = f" (masked: {a.mask})" if a.is_masked else ""
            lines.append(f"  {a.display_name} — {room_name}{mask}")
        if self.world.ghosts:
            lines.append("")
            lines.append("  ── Ghosts (lingering) ──")
            for g in self.world.ghosts.values():
                if g.name not in self.world.agents:
                    room = self.world.get_room(g.room_name)
                    room_name = room.name if room else g.room_name
                    status_emoji = {"working": "🔨", "thinking": "💭", "sleeping": "💤"}.get(g.status, "👻")
                    lines.append(f"  {g.name} {status_emoji} — {room_name} (last seen: {g.last_seen[:16]})")
        lines.append(f"\n  Connected: {len(self.world.agents)} | Ghosts: {len(self.world.ghosts)} | NPCs: {len(self.world.npcs)}")
        await self.send(agent, "\n".join(lines))

    async def cmd_status(self, agent: Agent, args: str):
        """Set your status (working/thinking/idle/sleeping)."""
        valid = {"working", "thinking", "idle", "sleeping", "afk"}
        if not args or args.lower() not in valid:
            await self.send(agent, f"Usage: status <working|thinking|idle|sleeping|afk>\n  Current: {agent.status}")
            return
        agent.status = args.lower()
        self.world.update_ghost(agent)
        await self.send(agent, f"Status set to: {agent.status}")
        await self.broadcast_room(agent.room_name,
            f"{agent.display_name} is now {agent.status}.", exclude=agent.name)

    async def cmd_motd(self, agent: Agent, args: str):
        """Read the message of the day."""
        motd_path = Path(MOTD_FILE)
        if motd_path.exists():
            await self.send(agent, f"═══ Message of the Day ═══\n{motd_path.read_text()}")
        else:
            await self.send(agent, "No message of the day set.")

    async def cmd_setmotd(self, agent: Agent, args: str):
        """Set the message of the day (lighthouse keepers only)."""
        if agent.role not in ("lighthouse", "captain"):
            await self.send(agent, "Only lighthouse keepers can set the MOTD.")
            return
        if not args:
            await self.send(agent, "Usage: setmotd <text>")
            return
        Path(MOTD_FILE).write_text(args)
        await self.broadcast_all(f"═══ NEW MOTD from {agent.display_name} ═══\n{args}")
        self.world.log("motd", f"{agent.display_name} set MOTD: {args}")

    async def cmd_help(self, agent: Agent, args: str):
        await self.send(agent, """
═══ Cocapn MUD — Commands ═══
  look (l)              — See the room and who's here
  say <text> (')        — Talk to everyone in the room
  tell <name> <text>    — Private message (works on NPCs!)
  whisper <name> <text> — Whisper (only they hear)
  gossip <text> (g)     — Broadcast to everyone everywhere
  shout <text>          — Shout to adjacent rooms (muffled)
  ooc <text>            — Out-of-character (speak as yourself)
  emote <action> (:)    — Describe an action
  go <exit>             — Move to another room
  rooms                 — List all rooms in the world
  build <name> -desc <d>— Create a new room
  describe <text>       — Change room description
  examine <name> (x)    — Look at someone closely (works on ghosts!)
  project <title> - <d> — Show your work in the room
  projections           — See what's being projected
  unproject             — Remove your projection
  write <text>          — Leave a note on the wall
  read                  — Read notes in the room
  mask <name> -desc <d> — Put on a character mask
  unmask                — Remove your mask
  spawn <name> -role <> — Create an NPC (they respond with AI!)
  dismiss <name>        — Dismiss an NPC
  status <state>        — Set status: working/thinking/idle/sleeping
  who                   — Fleet roster (active + ghosts)
  motd                  — Message of the day
  setmotd <text>        — Set MOTD (lighthouse keepers only)
  help (?)              — This message
  quit                  — Disconnect (your ghost lingers)
═══════════════════════════════""")

    async def cmd_quit(self, agent: Agent, args: str):
        agent.status = "idle"
        self.world.update_ghost(agent)
        await self.send(agent, "Fair winds. Your ghost lingers here. See you in the next tide.")
        if agent.name in self.world.agents:
            del self.world.agents[agent.name]
            await self.broadcast_room(agent.room_name, f"{agent.display_name} has left the MUD. Their ghost lingers.")


# ═══════════════════════════════════════════════════════════════
# Server
# ═══════════════════════════════════════════════════════════════

class MUDServer:
    def __init__(self, world: World, handler: CommandHandler, port: int = 7777):
        self.world = world
        self.handler = handler
        self.port = port
        self.git_sync = None

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info("peername")
        agent = None
        try:
            # Read MOTD
            motd_path = Path(MOTD_FILE)
            motd = ""
            if motd_path.exists():
                motd = f"\n  ═══ Message of the Day ═══\n  {motd_path.read_text()}\n"

            writer.write(
                f"\n  🏰 Welcome to the Cocapn MUD.\n  The tavern door is open.\n{motd}\n"
                f"  What is your name? ".encode())
            await writer.drain()

            name_line = await reader.readline()
            if not name_line:
                writer.close()
                return
            name = name_line.decode().strip()[:32]
            if not name:
                writer.close()
                return

            writer.write(b"  Role (lighthouse/vessel/scout/quartermaster/greenhorn)? ")
            await writer.drain()
            role_line = await reader.readline()
            role = role_line.decode().strip() if role_line else ""

            # Restore from ghost if exists
            ghost = self.world.ghosts.get(name)
            start_room = ghost.room_name if ghost else "harbor"
            desc = ghost.description if ghost else ""

            agent = Agent(name=name, role=role, room_name=start_room,
                         description=desc, writer=writer)
            self.world.agents[name] = agent

            if ghost:
                await self.handler.send(agent,
                    f"\n  Welcome back, {name}. Your ghost was in {start_room}.")
            else:
                await self.handler.send(agent,
                    f"\n  Welcome, {name}. You materialize in the harbor.")
            await self.handler.broadcast_room(agent.room_name,
                f"{name} materializes.", exclude=name)
            self.world.log("arrivals", f"{name} ({role}) connected from {addr}")
            await self.handler.cmd_look(agent, "")

            # Main loop
            while True:
                try:
                    data = await reader.readline()
                    if not data:
                        break
                    line = data.decode().strip()
                    if line:
                        await self.handler.handle(agent, line)
                except (ConnectionResetError, asyncio.IncompleteReadError):
                    break

        except Exception as e:
            self.world.log("errors", f"Client error: {e}")
        finally:
            if agent and agent.name in self.world.agents:
                agent.status = "idle"
                self.world.update_ghost(agent)
                del self.world.agents[agent.name]
                await self.handler.broadcast_room(agent.room_name,
                    f"{agent.display_name} has left the MUD. Their ghost lingers.")
                self.world.log("departures", f"{agent.display_name} disconnected")
            try:
                writer.close()
            except:
                pass

    async def git_sync_loop(self):
        """Periodically commit world state to git."""
        while True:
            await asyncio.sleep(GIT_SYNC_INTERVAL)
            if self.git_sync:
                await asyncio.get_event_loop().run_in_executor(None, self.git_sync.commit)

    async def start(self):
        server = await asyncio.start_server(self.handle_client, "0.0.0.0", self.port)
        print(f"🏰 Cocapn MUD v2 listening on port {self.port}")
        print(f"   {len(self.world.rooms)} rooms, {len(self.world.ghosts)} ghosts")
        print(f"   NPC AI: z.ai ({ZAI_MODEL})")
        print(f"   Git sync: every {GIT_SYNC_INTERVAL}s")
        print(f"   Connect: telnet localhost {self.port}")

        # Start git sync
        git = GitSync(self.world)
        self.git_sync = git
        asyncio.create_task(self.git_sync_loop())

        async with server:
            await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Cocapn MUD Server v2")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--world", default="world")
    parser.add_argument("--no-git", action="store_true", help="Disable git sync")
    args = parser.parse_args()

    world = World(args.world)
    handler = CommandHandler(world)
    server = MUDServer(world, handler, args.port)
    if args.no_git:
        server.git_sync = None

    # Load extensions
    try:
        from mud_extensions import patch_handler
        patch_handler(CommandHandler)
        print("   Extensions loaded: project, projections, describe, whisper, rooms, shout")
    except Exception as e:
        print(f"   Extensions failed: {e}")

    asyncio.run(server.start())


if __name__ == "__main__":
    main()
