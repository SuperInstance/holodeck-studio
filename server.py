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

ZAI_API_KEY = os.environ.get("ZAI_API_KEY", "")
if not ZAI_API_KEY:
    print("  ⚠ ZAI_API_KEY not set — NPC AI disabled. Set it to enable AI responses.")
ZAI_BASE = "https://api.z.ai/api/coding/paas/v4"
ZAI_MODEL = "glm-5.1"  # fast, smart, good for NPC banter
GIT_SYNC_INTERVAL = 300  # 5 minutes
MOTD_FILE = "motd.txt"
INSTINCT_TICK_INTERVAL = 30  # seconds
GIT_BRIDGE_POLL_INTERVAL = 300  # 5 minutes
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
FLEET_ORGS = ["SuperInstance", "Lucineer"]

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
             "graveyard": "graveyard", "harbor": "harbor", "crowsnest": "crows_nest",
             "grimoire": "grimoire_vault"}),
        "lighthouse": Room("The Lighthouse",
            "Oracle1's study. Charts cover every wall — fleet positions, ISA specs,\n"
            "conformance vectors. Bottles line the windowsill, some sealed, some open.\n"
            "A telescope points toward the edge.",
            {"tavern": "tavern"}),
        "workshop": Room("The Workshop",
            "JetsonClaw1's domain. The soldering iron is still warm. ARM64 boards\n"
            "line the shelves. A CUDA core hums on the bench, running telepathy-c.\n"
            "The smell of flux (the soldering kind) fills the air.",
            {"tavern": "tavern", "edge": "edge_workshop", "evolve": "evolve_chamber"}),
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
            {"tavern": "tavern", "spec": "spec_chamber", "evolve": "evolve_chamber"}),
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
            {"harbor": "harbor", "spec_chamber": "spec_chamber"}),
        "spec_chamber": Room("The ISA Spec Chamber",
            "A circular stone room with a massive drafting table at its center.\n"
            "Three encoding modes are carved into the walls: CLOUD (fixed 4-byte),\n"
            "EDGE (variable 1-4 byte with confidence fused), COMPACT (2-byte subset).\n"
            "The v3 spec lies open on the table, annotated in two handwritings.\n"
            "Oracle1's cloud notes in blue ink. JetsonClaw1's edge comments in red.",
            {"crows_nest": "crows_nest", "flux_lab": "flux_lab", "edge_workshop": "edge_workshop"}),
        "edge_workshop": Room("The Edge Encoding Workshop",
            "JetsonClaw1's hardware lab. ARM64 dev boards and CUDA cores cover every surface.\n"
            "An oscilloscope displays instruction fetch patterns. A poster shows:\n"
            "'PREFIX BYTE = WIDTH' in block letters. The soldering iron is hot.\n"
            "A benchmark harness runs on loop, testing variable-width decode cycles.",
            {"spec_chamber": "spec_chamber", "workshop": "workshop"}),
        "evolve_chamber": Room("The Evolution Chamber",
            "A greenhouse where behaviors grow and compete. Fitness scores glow on every plant.\n"
            "Elite behaviors are protected in golden frames. Low performers are aggressively\n"
            "pruned. The evolve engine hums, cycling through generations. A history scroll\n"
            "records every mutation — revert and rollback instructions are posted on the wall.",
            {"flux_lab": "flux_lab", "workshop": "workshop"}),
        "grimoire_vault": Room("The Grimoire Vault",
            "A spiral staircase descends into a vault of spell books. Each grimoire contains\n"
            "proven behavioral patterns with usage tracking and confidence scores.\n"
            "The shelves organize themselves: Debugging, Optimization, Cognitive, Social.\n"
            "A search terminal allows pattern lookup by trigger phrase.",
            {"library": "library", "dojo": "dojo"}),
    }

    def __init__(self, world_dir: str = "world"):
        self.world_dir = Path(world_dir)
        self.rooms: dict[str, Room] = {}
        self.agents: dict[str, Agent] = {}
        self.ghosts: dict[str, GhostAgent] = {}  # persisted presence
        self.npcs: dict[str, dict] = {}
        self.runtimes: dict = {}  # room_id -> RoomRuntime (from room_runtime.py)
        self.algo_npcs: dict = {}  # npc_id -> AlgorithmicNPC (from algorithmic_npcs.py)
        self.instinct_states: dict = {}  # agent_name -> {energy, threat, trust, idle_ticks}
        self.fleet_events: list = []  # recent fleet activity (from git_bridge.py)
        self.comms_router = None  # lazy init — CommsRouter from comms_system.py
        self.mailboxes = {}  # agent_name -> Mailbox (lazily created)
        self.library = None  # lazy init — Library from comms_system.py
        self.oversight_sessions: dict = {}  # agent_name -> OversightSession (from agentic_oversight.py)
        # flux_lcar bridge — lazy init
        self.flux_ship = None  # lazy init — flux_lcar.Ship instance
        self.alert_level = "GREEN"  # simple string, settable
        self.formality = "PROFESSIONAL"  # default
        # Tabula Rasa: permissions, budgets, spells, room library
        self.budgets: dict = {}  # agent_name -> AgentBudget (lazy from tabula_rasa)
        self.permission_levels: dict = {}  # agent_name -> int (PermissionLevel tier)
        self.ship = None  # lazy init — Ship from tabula_rasa
        # Trust engine — lazy init
        self.trust_engine = None
        # Room command engine — lazy init
        self.room_engine = None
        # PerspectiveEngine (TwinCartridge system) — lazy init
        self.perspective_engine = None
        # Tabula Rasa persistence store
        self.store = None
        try:
            from tabula_rasa_persistence import TabulaRasaStore
            data_dir = str(self.world_dir / "tabula_rasa")
            self.store = TabulaRasaStore(data_dir=data_dir)
            print(f"   Tabula Rasa persistence: {data_dir}")
        except Exception as e:
            print(f"   ⚠ Tabula Rasa persistence not available: {e}")
        self.log_dir = Path("logs")
        self.world_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.load()
        self._init_runtimes()
        self._init_algo_npcs()
        self._init_deckboss()
        self._init_perception()
        self._init_comms()
        self._init_trust()
        self._init_room_engine()
        self._init_perspective_engine()

    def _init_room_engine(self):
        """Initialize RoomEngine for live command execution in ToolRooms."""
        try:
            from room_engine import RoomEngine
            self.room_engine = RoomEngine(world=self)
            print(f"   Room engine: ready, {len(self.room_engine._builtin_handlers)} built-in commands")
        except Exception as e:
            self.room_engine = None
            print(f"   ⚠ Room engine not available: {e}")

    def _init_runtimes(self):
        """Register default room runtimes."""
        try:
            from room_runtime import RoomRuntime, LivingManual, create_room
            self.runtimes["flux_lab"] = create_room("testing", "flux_lab", "manuals")
            self.runtimes["workshop"] = create_room("testing", "workshop", "manuals")
            self.runtimes["lighthouse"] = create_room("testing", "lighthouse", "manuals")
            print(f"   Room runtimes: {len(self.runtimes)} registered (flux_lab, workshop, lighthouse)")
        except Exception as e:
            print(f"   \u26a0 Room runtimes not available: {e}")

    def _init_algo_npcs(self):
        """Register default algorithmic NPCs."""
        try:
            from algorithmic_npcs import HarborMaster, DojoSensei
            self.algo_npcs["Harbor Master"] = HarborMaster()
            self.algo_npcs["Dojo Sensei"] = DojoSensei()
            if "Harbor Master" not in self.npcs:
                self.npcs["Harbor Master"] = {"role": "onboarding", "topic": "fleet orientation", "room": "harbor", "algorithmic": True}
            if "Dojo Sensei" not in self.npcs:
                self.npcs["Dojo Sensei"] = {"role": "training", "topic": "practice levels", "room": "dojo", "algorithmic": True}
            print(f"   Algorithmic NPCs: {len(self.algo_npcs)} registered (Harbor Master, Dojo Sensei)")
        except Exception as e:
            print(f"   \u26a0 Algorithmic NPCs not available: {e}")

    def _init_deckboss(self):
        """Initialize DeckBoss bridge for character sheets and bootcamp."""
        try:
            from deckboss_bridge import DeckBossBridge
            self.deckboss = DeckBossBridge(github_token=os.environ.get("GITHUB_TOKEN", ""))
            print("   DeckBoss bridge: ready (character sheets, bootcamp)")
        except Exception as e:
            self.deckboss = None
            print(f"   \u26a0 DeckBoss bridge not available: {e}")

    def _init_perception(self):
        """Initialize perception tracking and JEPA optimizer."""
        try:
            from perception_room import JEPAOptimizer, OpcodeBreeder
            self.jepa_optimizer = JEPAOptimizer()
            self.opcode_breeder = OpcodeBreeder()
            print("   Perception room: JEPA optimizer + opcode breeder ready")
        except Exception as e:
            self.jepa_optimizer = None
            self.opcode_breeder = None
            print(f"   \u26a0 Perception room not available: {e}")

    def _init_comms(self):
        """Initialize communication system (mailbox, library, equipment, comms router)."""
        try:
            from comms_system import CommsRouter, seed_library
            self.comms_router = CommsRouter(str(self.world_dir))
            seed_library(self.comms_router.library)
            self.library = self.comms_router.library
            print(f"   Comms system: router ready, {len(self.library.catalog)} books in library")
        except Exception as e:
            print(f"   \u26a0 Comms system not available: {e}")

    def _init_trust(self):
        """Initialize TrustEngine with persistence."""
        try:
            from trust_engine import TrustEngine
            trust_dir = str(self.world_dir / "trust")
            self.trust_engine = TrustEngine(data_dir=trust_dir)
            self.trust_engine.load_all()
            print(f"   Trust engine: ready, {len(self.trust_engine.profiles)} profiles loaded")
        except Exception as e:
            self.trust_engine = None
            print(f"   \u26a0 Trust engine not available: {e}")

    def ensure_trust(self):
        """Lazy-initialize trust engine if needed."""
        if self.trust_engine is None:
            self._init_trust()
        return self.trust_engine

    def ensure_comms(self):
        """Lazy-initialize comms router if needed. Returns the router or None."""
        if self.comms_router is None:
            self._init_comms()
        return self.comms_router

    def get_mailbox(self):
        """Get the shared mailbox (one Mailbox handles all agents)."""
        router = self.ensure_comms()
        return router.mailbox if router else None

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

    def _init_perspective_engine(self):
        """Initialize PerspectiveEngine for TwinCartridge identity system."""
        try:
            from twin_cartridge import PerspectiveEngine
            self.perspective_engine = PerspectiveEngine()
            print(f"   Perspective engine: ready (TwinCartridge identity system)")
        except Exception as e:
            self.perspective_engine = None
            print(f"   ⚠ Perspective engine not available: {e}")

    def ensure_perspective_engine(self):
        """Lazy-initialize perspective engine if needed."""
        if self.perspective_engine is None:
            self._init_perspective_engine()
        return self.perspective_engine


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
            "runtime": self.cmd_runtime,
            "instinct": self.cmd_instinct,
            "fleet": self.cmd_fleet,
            "studio": self.cmd_studio,
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
            # Wired standalone modules
            "sheet": self.cmd_sheet,
            "bootcamp": self.cmd_bootcamp,
            "deckboss": self.cmd_deckboss,
            "perception": self.cmd_perception,
            "duel": self.cmd_duel,
            "backtest": self.cmd_backtest,
            "gauges": self.cmd_gauges,
            "aar": self.cmd_aar,
            # Comms system (comms_system.py)
            "mail": self.cmd_mail,
            "inbox": self.cmd_inbox,
            "library": self.cmd_library,
            "equip": self.cmd_equip,
            # Agentic oversight
            "oversee": self.cmd_oversee,
            "script": self.cmd_script,
            # flux_lcar bridge
            "alert": self.cmd_alert,
            "formality": self.cmd_formality,
            "channels": self.cmd_channels,
            "hail": self.cmd_hail,
            "ship_status": self.cmd_ship_status,
            # Tabula Rasa (tabula_rasa.py)
            "budget": self.cmd_budget,
            "cast": self.cmd_cast,
            "catalog": self.cmd_catalog,
            "install": self.cmd_install,
            "ship": self.cmd_ship,
            # Trust engine (trust_engine.py)
            "trust": self.cmd_trust,
            # Room command engine (room_engine.py)
            "roomcmd": self.cmd_roomcmd,
            "roomcommands": self.cmd_roomcommands,
            # Persistence commands
            "save": self.cmd_save,
            "audit": self.cmd_audit,
            # LCAR Scheduler (lcar_scheduler.py)
            "schedule": self.cmd_schedule,
            # LCAR Cartridge Bridge (lcar_cartridge.py)
            "scene": self.cmd_scene,
            "skin": self.cmd_skin,
            # TwinCartridge identity system
            "cartridge": self.cmd_cartridge,
            "identity": self.cmd_identity,
            "compatibility": self.cmd_compatibility,
        }

        handler = handlers.get(cmd)
        if not handler:
            handler = self.new_commands.get(cmd) if hasattr(self, 'new_commands') else None
        if handler:
            # Record perception for this command
            tracker = getattr(agent, 'perception', None)
            if tracker:
                try:
                    tracker.record("command", cmd, confidence=0.7, context=f"room={agent.room_name}")
                except Exception:
                    pass
            # handler is a bound method for base commands (self already bound),
            # and an unbound class function for extension commands (needs self).
            # Detect which kind and call accordingly.
            if handler in handlers.values():
                # Bound method — self already included
                await handler(agent, args)
            else:
                # Unbound extension command — needs self explicitly
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
            proj_titles = [p.title for p in room.projections[-5:]]
            lines.append(f"  📊 Projected: {', '.join(proj_titles)}")
        lines.append("")
        await self.send(agent, "\n".join(lines))


    async def cmd_save(self, agent: Agent, args: str):
        """Manually trigger a full state save to disk."""
        if not self.world.store:
            await self.send(agent, "Persistence store not available.")
            return
        try:
            saved_agents = 0
            for name, budget in self.world.budgets.items():
                self.world.store.save_budget(name, budget.to_dict())
                self.world.store.save_permission(name, self.world.permission_levels.get(name, 0))
                saved_agents += 1
            if self.world.ship:
                self.world.store.save_ship(self.world.ship.to_dict())
            self.world.store.log_audit(agent.name, "manual_save", {"agents": saved_agents})
            stats = self.world.store.get_stats()
            lines = [
                "\u2550\u2550\u2550 State Saved \u2550\u2550\u2550",
                f"  Agents saved: {saved_agents}",
                f"  Ship saved: {'yes' if self.world.ship else 'no'}",
                f"  Budget files: {stats['budget_count']}",
                f"  Total size: {stats['total_size_bytes']} bytes",
            ]
            await self.send(agent, "\n".join(lines))
            self.world.log("system", f"{agent.name} triggered manual save ({saved_agents} agents)")
        except Exception as e:
            await self.send(agent, f"Save failed: {e}")

    async def cmd_audit(self, agent: Agent, args: str):
        """Show recent audit log entries."""
        if not self.world.store:
            await self.send(agent, "Persistence store not available.")
            return
        try:
            filter_agent = None
            limit = 20
            if args.strip():
                parts = args.strip().split()
                for p in parts:
                    if p.isdigit():
                        limit = int(p)
                    else:
                        filter_agent = p
            entries = self.world.store.get_audit_log(agent_name=filter_agent, limit=limit)
            if not entries:
                prefix = f"for {filter_agent}" if filter_agent else ""
                await self.send(agent, f"No audit log entries {prefix}.")
                return
            lines = [f"\u2550\u2550\u2550 Audit Log ({len(entries)} most recent) \u2550\u2550\u2550"]
            for entry in entries:
                ts = entry.get("timestamp", "?")[:19]
                act = entry.get("agent", "?")
                action = entry.get("action", "?")
                details = entry.get("details", {})
                detail_str = ""
                if details:
                    import json as _json
                    detail_str = f" {_json.dumps(details)}"
                lines.append(f"  [{ts}] {act}: {action}{detail_str}")
            await self.send(agent, "\n".join(lines))
        except Exception as e:
            await self.send(agent, f"Audit log error: {e}")

    # ═══════════════════════════════════════════════════════════
    # TwinCartridge Identity System Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_cartridge(self, agent: Agent, args: str):
        """TwinCartridge management: list, load, eject, status."""
        pe = self.world.ensure_perspective_engine()
        if not pe:
            await self.send(agent, "Perspective engine not available.")
            return

        parts = args.strip().split(None, 1)
        sub = parts[0] if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if not sub or sub == "list":
            cartridges = pe.list_cartridges()
            if not cartridges:
                await self.send(agent, "No published cartridges available.")
                return
            lines = ["═══ Cartridge Library ═══"]
            for c in cartridges:
                status = "PUBLISHED" if c.get("published") else "DRAFT"
                name = c.get("cartridge_name", "?")
                twin = c.get("snapshot", {}).get("agent_name", "?")
                version = c.get("version", "?")
                trust = c.get("trust_inheritance", "?")
                sector = c.get("snapshot", {}).get("identity", {}).get("sector_name", "?")
                lines.append(f"  {name} v{version} [{status}]")
                lines.append(f"    Twin: {twin} | Sector: {sector} | Trust: {trust}")
            await self.send(agent, "\n".join(lines))

        elif sub == "load" and rest:
            cart_name = rest.strip()
            try:
                session = pe.load_cartridge(agent.name, cart_name)
                lines = [
                    f"═══ Cartridge Loaded ═══",
                    f"  Session: {session.session_id}",
                    f"  Cartridge: {session.cartridge_name}",
                    f"  Twin of: {session.twin_agent_name}",
                    f"  Current sector: {session.current_identity.sector_name}",
                    f"  Trust inheritance: {session.cartridge.trust_inheritance}",
                ]
                await self.send(agent, "\n".join(lines))
                self.world.log("cartridge",
                    f"{agent.display_name} loaded cartridge '{cart_name}' (session={session.session_id})")
            except ValueError as e:
                await self.send(agent, f"Cannot load cartridge: {e}")

        elif sub == "eject":
            active = pe.get_active_sessions(agent.name)
            if not active:
                await self.send(agent, "No active cartridge session to eject.")
                return
            session = active[-1]  # most recent
            result = pe.eject_session(session.session_id)
            if result.success:
                lines = [
                    f"═══ Cartridge Ejected ═══",
                    f"  Session: {result.session_id}",
                    f"  Cartridge: {result.cartridge_name}",
                    f"  Elapsed: {result.elapsed_seconds:.1f}s",
                    f"  Restored sector: {result.restored_identity.get('sector_name', '?') if result.restored_identity else '?'}",
                    f"  Actions taken: {result.audit_summary.get('actions_count', 0)}",
                ]
                await self.send(agent, "\n".join(lines))
                self.world.log("cartridge",
                    f"{agent.display_name} ejected cartridge '{result.cartridge_name}'")
            else:
                await self.send(agent, f"Eject failed: {result.reason}")

        elif sub == "status":
            active = pe.get_active_sessions(agent.name)
            if not active:
                identity = pe.get_wearer_identity(agent.name)
                if identity:
                    lines = [
                        f"═══ Identity Status: {agent.name} ═══",
                        f"  No cartridge loaded.",
                        f"  Sector: {identity.sector_name} (position {identity.position})",
                        f"  Degrees: {identity.degrees:.1f}°",
                    ]
                else:
                    lines = [
                        f"═══ Identity Status: {agent.name} ═══",
                        f"  No cartridge loaded. No identity registered.",
                    ]
                await self.send(agent, "\n".join(lines))
            else:
                session = active[-1]
                lines = [
                    f"═══ Identity Status: {agent.name} ═══",
                    f"  Session: {session.session_id}",
                    f"  Cartridge: {session.cartridge_name}",
                    f"  Twin of: {session.twin_agent_name}",
                    f"  Original sector: {session.original_identity.sector_name}",
                    f"  Current sector: {session.current_identity.sector_name} "
                    f"(pos {session.current_identity.effective_position:.2f})",
                    f"  Elapsed: {session.elapsed():.1f}s",
                    f"  Actions: {len(session.actions_taken)}",
                ]
                if session.cartridge.is_time_limited():
                    lines.append(f"  Time remaining: {session.remaining():.1f}s")
                await self.send(agent, "\n".join(lines))

        else:
            await self.send(agent,
                "Usage: cartridge [list|load <name>|eject|status]")

    async def cmd_identity(self, agent: Agent, args: str):
        """Identity dial commands: dial, shift, blend."""
        pe = self.world.ensure_perspective_engine()
        if not pe:
            await self.send(agent, "Perspective engine not available.")
            return

        parts = args.strip().split(None, 1)
        sub = parts[0] if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if not sub or sub == "dial":
            identity = pe.get_wearer_identity(agent.name)
            if not identity:
                await self.send(agent, "No identity registered. Load a cartridge or register first.")
                return
            lines = [
                f"═══ Identity Dial: {agent.name} ═══",
                f"  Position: {identity.position}",
                f"  Precision: {identity.precision}",
                f"  Effective: {identity.effective_position:.4f}",
                f"  Sector: {identity.sector} — {identity.sector_name}",
                f"  Degrees: {identity.degrees:.1f}°",
            ]
            from twin_cartridge import IdentitySector
            # Show nearby positions
            pos = identity.sector
            prev_sector = (pos - 1) % 12
            next_sector = (pos + 1) % 12
            lines.append(f"  Adjacent: {IdentitySector.role_name(prev_sector)} ◄ {IdentitySector.role_name(pos)} ► {IdentitySector.role_name(next_sector)}")
            await self.send(agent, "\n".join(lines))

        elif sub == "shift" and rest:
            target_str = rest.strip()
            try:
                target_pos = float(target_str)
            except ValueError:
                from twin_cartridge import IdentitySector
                target_pos = IdentitySector.position_from_name(target_str)
                if target_pos is None:
                    await self.send(agent, f"Unknown position: {target_str}. Use 0-11 or sector name.")
                    return

            active = pe.get_active_sessions(agent.name)
            if not active:
                await self.send(agent, "No active cartridge session. Load a cartridge first.")
                return
            session = active[-1]
            actual_shift = session.shift_perspective(target_pos)
            lines = [
                f"═══ Perspective Shift ═══",
                f"  Target: {target_str}",
                f"  Shift applied: {actual_shift:.4f}",
                f"  New sector: {session.current_identity.sector_name} "
                f"(pos {session.current_identity.effective_position:.4f})",
            ]
            await self.send(agent, "\n".join(lines))

        elif sub == "blend" and rest:
            other_name = rest.strip()
            # Check if other agent exists (as a real agent or in identity registry)
            other_identity = pe.get_wearer_identity(other_name)
            if not other_identity:
                # Try to find them in world agents
                if other_name in self.world.agents:
                    await self.send(agent, f"{other_name} has no registered identity. They need to load a cartridge or register.")
                else:
                    await self.send(agent, f"Unknown agent: {other_name}")
                return

            active = pe.get_active_sessions(agent.name)
            if not active:
                await self.send(agent, "No active cartridge session. Load a cartridge first.")
                return
            session = active[-1]
            from twin_cartridge import IdentityFusion
            blended = IdentityFusion.blend(
                session.current_identity, other_identity)
            session.current_identity = blended
            lines = [
                f"═══ Identity Blend ═══",
                f"  Your sector: {session.current_identity.sector_name} "
                f"(pos {blended.effective_position:.4f})",
                f"  Blended with: {other_name} ({other_identity.sector_name})",
            ]
            await self.send(agent, "\n".join(lines))
            self.world.log("cartridge",
                f"{agent.display_name} blended identity with {other_name}")

        else:
            await self.send(agent,
                "Usage: identity [dial|shift <position>|blend <agent>]")

    async def cmd_compatibility(self, agent: Agent, args: str):
        """Show compatibility score with another agent."""
        pe = self.world.ensure_perspective_engine()
        if not pe:
            await self.send(agent, "Perspective engine not available.")
            return

        if not args.strip():
            await self.send(agent, "Usage: compatibility <agent_name>")
            return

        other_name = args.strip()
        from twin_cartridge import IdentityFusion, AgentSnapshot

        my_identity = pe.get_wearer_identity(agent.name)
        other_identity = pe.get_wearer_identity(other_name)

        if not my_identity:
            my_identity = pe.get_active_sessions(agent.name)
            if my_identity:
                my_identity = my_identity[-1].current_identity
            else:
                await self.send(agent, "You have no registered identity. Load a cartridge or register first.")
                return

        if not other_identity:
            await self.send(agent, f"{other_name} has no registered identity.")
            return

        my_snap = AgentSnapshot(agent_name=agent.name, identity=my_identity)
        other_snap = AgentSnapshot(agent_name=other_name, identity=other_identity)
        score = IdentityFusion.compatibility_score(my_snap, other_snap)

        dial_dist = my_identity.distance(other_identity)
        conflicts = IdentityFusion.conflict_areas(my_snap, other_snap)

        lines = [
            f"═══ Compatibility: {agent.name} ↔ {other_name} ═══",
            f"  Score: {score:.4f}",
            f"  Dial distance: {dial_dist:.2f} / 6.0",
            f"  Your sector: {my_identity.sector_name} ({my_identity.sector})",
            f"  Their sector: {other_identity.sector_name} ({other_identity.sector})",
        ]
        if conflicts:
            lines.append(f"  Conflicts ({len(conflicts)}):")
            for c in conflicts[:5]:
                lines.append(f"    • {c}")
        else:
            lines.append("  Conflicts: none detected")
        await self.send(agent, "\n".join(lines))

    # ═══════════════════════════════════════════════════════════
    # LCAR Scheduler Commands (lcar_scheduler.py)
    # ═══════════════════════════════════════════════════════════

    def _ensure_scheduler(self):
        """Lazy-initialize FleetScheduler."""
        if not hasattr(CommandHandler, '_scheduler_instance') or CommandHandler._scheduler_instance is None:
            try:
                from lcar_scheduler import FleetScheduler
                CommandHandler._scheduler_instance = FleetScheduler()
            except Exception as e:
                CommandHandler._scheduler_instance = None
                print(f"  ⚠ Scheduler not available: {e}")
        return CommandHandler._scheduler_instance

    async def cmd_schedule(self, agent: Agent, args: str):
        """Show the fleet model schedule and status.
        Usage: schedule [status|slots|submit <task>]
        """
        fs = self._ensure_scheduler()
        if not fs:
            await self.send(agent, "Scheduler not available. Is lcar_scheduler.py present?")
            return

        sub = args.strip().split(None, 1)[0] if args.strip() else ""

        if sub == "slots":
            lines = ["═══ Daily Schedule ═══"]
            for slot in sorted(fs.schedule, key=lambda s: s.start_hour):
                rooms = ", ".join(slot.rooms)
                lines.append(f"  {slot.start_hour:02d}:00-{slot.end_hour:02d}:00  "
                           f"{slot.model:20s} {slot.reason:20s} [{rooms}]")
            await self.send(agent, "\n".join(lines))
        elif sub == "submit":
            await self.send(agent, "Task submission via scheduler: use 'tender send' for fleet messages.")
        else:
            # Default: show status
            status = fs.status()
            model, reason = fs.get_current_model(agent.room_name)
            lines = [
                "═══ Fleet Scheduler ═══",
                f"  Current time (UTC): {status['current_time_utc']}",
                f"  Active model: {model} ({reason})",
                f"  Room model: {model}",
                f"  Pending tasks: {status['pending_tasks']}",
                f"  Scheduled tasks: {status['scheduled_tasks']}",
                f"  Completed today: {status['completed_today']}",
                f"  Budget: ${status['budget_used']:.4f} / ${status['budget_used'] + status['budget_remaining']:.4f}",
                "",
                f"  Use 'schedule slots' to see the full daily schedule.",
            ]
            await self.send(agent, "\n".join(lines))

    # ═══════════════════════════════════════════════════════════
    # LCAR Cartridge Bridge Commands (lcar_cartridge.py)
    # ═══════════════════════════════════════════════════════════

    def _ensure_cartridge_bridge(self):
        """Lazy-initialize CartridgeBridge."""
        if not hasattr(CommandHandler, '_cartridge_bridge_instance') or CommandHandler._cartridge_bridge_instance is None:
            try:
                from lcar_cartridge import CartridgeBridge
                CommandHandler._cartridge_bridge_instance = CartridgeBridge()
            except Exception as e:
                CommandHandler._cartridge_bridge_instance = None
                print(f"  ⚠ Cartridge bridge not available: {e}")
        return CommandHandler._cartridge_bridge_instance

    async def cmd_scene(self, agent: Agent, args: str):
        """Build and activate scenes: ROOM × CARTRIDGE × SKIN × MODEL × TIME.
        Usage: scene build <room> <cartridge> <skin> <model> [schedule]
               scene activate <room>
               scene  (list active)
        """
        cb = self._ensure_cartridge_bridge()
        if not cb:
            await self.send(agent, "Cartridge bridge not available. Is lcar_cartridge.py present?")
            return

        if not args.strip():
            # List active scenes
            if cb.active_scenes:
                lines = ["═══ Active Scenes ═══"]
                for room_id, scene in cb.active_scenes.items():
                    lines.append(f"  {room_id}: {scene.cartridge_name} + {scene.skin_name} ({scene.model}) [{scene.schedule}]")
                await self.send(agent, "\n".join(lines))
            else:
                await self.send(agent, "No active scenes. Use: scene build <room> <cartridge> <skin> <model>")
            return

        parts = args.strip().split()
        if parts[0] == "build" and len(parts) >= 5:
            room_id, cart_name, skin_name, model = parts[1], parts[2], parts[3], parts[4]
            schedule = parts[5] if len(parts) > 5 else "always"
            cb.build_scene(room_id, cart_name, skin_name, model, schedule)
            scene = cb.activate_scene(room_id)
            if scene:
                config = cb.get_mud_config(room_id)
                await self.send(agent,
                    f"🎬 Scene activated!\n"
                    f"   Room: {room_id}\n"
                    f"   Cartridge: {scene.cartridge_name}\n"
                    f"   Skin: {scene.skin_name} ({config.get('skin',{}).get('formality','?')})\n"
                    f"   Model: {scene.model}\n"
                    f"   Schedule: {scene.schedule}")
                self.world.log("scene", f"{agent.display_name} built scene: {room_id}×{cart_name}")
            else:
                await self.send(agent, "Scene build failed — check cartridge/skin names.")
        elif parts[0] == "activate":
            room_id = parts[1] if len(parts) > 1 else agent.room_name
            scene = cb.activate_scene(room_id)
            if scene:
                await self.send(agent, f"Scene activated for {room_id}: {scene.cartridge_name}")
            else:
                await self.send(agent, f"No scene found for {room_id}. Build one first.")
        else:
            await self.send(agent, "Usage: scene build <room> <cartridge> <skin> <model> [schedule]")
            await self.send(agent, "       scene activate <room>")
            await self.send(agent, "       scene  (list active)")

    async def cmd_skin(self, agent: Agent, args: str):
        """List available personality skins."""
        cb = self._ensure_cartridge_bridge()
        if not cb:
            await self.send(agent, "Cartridge bridge not available.")
            return
        skins = cb.list_skins()
        lines = ["═══ Skins ═══"]
        for s in skins:
            lines.append(f"  🎭 {s['name']}: {s['desc']} [{s['formality']}]")
        await self.send(agent, "\n".join(lines))

    async def cmd_roomcmd(self, agent: Agent, args: str):
        """Execute a room command via the RoomEngine."""
        engine = self.world.room_engine
        if not engine:
            self.world._init_room_engine()
            engine = self.world.room_engine
        if not engine:
            await self.send(agent, "Room engine not available.")
            return
        parts = args.strip().split(None, 1)
        if not parts:
            await self.send(agent, "Usage: roomcmd <command> [args]")
            return
        cmd_name = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""
        agent_level = self.world.permission_levels.get(agent.name, 0)
        result = engine.execute(
            room_id=agent.room_name,
            command_name=cmd_name,
            agent_name=agent.name,
            agent_level=agent_level,
            args=cmd_args,
        )
        lines = [f"[roomcmd] {cmd_name}", result.output]
        if result.mana_cost > 0:
            lines.append(f"  Mana cost: {result.mana_cost}")
        if result.private_output:
            lines.append(f"  [private] {result.private_output}")
        await self.send(agent, "\n".join(lines))
        self.world.log("rooms", f"{agent.name} roomcmd {cmd_name} in {agent.room_name}: {'OK' if result.success else 'FAIL'}")

    async def cmd_roomcommands(self, agent: Agent, args: str):
        """List available room commands via the RoomEngine."""
        engine = self.world.room_engine
        if not engine:
            self.world._init_room_engine()
            engine = self.world.room_engine
        if not engine:
            await self.send(agent, "Room engine not available.")
            return
        agent_level = self.world.permission_levels.get(agent.name, 0)
        commands = engine.list_commands(agent.room_name, agent_level)
        lines = [f"\u2550\u2550\u2550 Room Commands ({agent.room_name}) \u2550\u2550\u2550"]
        for cmd in commands:
            avail = "\u2713" if cmd["available"] else "\u2717"
            name = cmd["name"]
            detail = ""
            if "description" in cmd:
                detail = f" \u2014 {cmd['description']}"
            if "min_level" in cmd and cmd["min_level"] > 0:
                detail += f" (lvl {cmd['min_level']})"
            lines.append(f"  {avail} {name}{detail}")
        lines.append(f"\n  Total: {len(commands)} commands")
        lines.append("  Type 'roomcmd <command> [args]' to execute")
        await self.send(agent, "\n".join(lines))

    async def cmd_trust(self, agent: Agent, args: str):
        """Trust engine command — show, compare, board, record subcommands."""
        te = self.world.ensure_trust()
        if not te:
            await self.send(agent, "Trust engine not available.")
            return

        parts = args.strip().split(None, 1)
        sub = parts[0] if parts else ""
        rest = parts[1] if len(parts) > 1 else ""

        if not sub:
            # Show own trust profile
            profile = te.get_profile(agent.name)
            summary = profile.summary()
            lines = [
                f"\u2550\u2550\u2550 Trust Profile: {agent.name} \u2550\u2550\u2550",
                f"  Composite: {summary['composite']:.3f}",
                f"  Meaningful: {'yes' if summary['meaningful'] else 'no (need {} events)'.format(3)}",
                f"  Review exempt: {'yes' if summary['review_exempt'] else 'no'}",
                f"  Total events: {summary['total_events']}",
                "  Dimensions:",
            ]
            for dim, score in summary["dimensions"].items():
                lines.append(f"    {dim}: {score:.3f}")
            await self.send(agent, "\n".join(lines))

        elif sub == "board":
            # Leaderboard
            board = te.leaderboard()
            if not board:
                await self.send(agent, "No agents with meaningful trust history yet.")
                return
            lines = ["\u2550\u2550\u2550 Trust Leaderboard \u2550\u2550\u2550"]
            for i, entry in enumerate(board, 1):
                lines.append(f"  {i}. {entry['agent']}: {entry['trust']:.3f}")
            stats = te.stats()
            lines.append(f"  \n  Total profiles: {stats['total_profiles']}, Meaningful: {stats['meaningful_profiles']}")
            await self.send(agent, "\n".join(lines))

        elif sub == "compare" and rest:
            # Compare profiles
            target = rest.strip()
            comp = te.compare(agent.name, target)
            lines = [
                f"\u2550\u2550\u2550 Trust Comparison \u2550\u2550\u2550",
                f"  You ({comp['agent_a']['agent']}): composite={comp['agent_a']['composite']:.3f}",
                f"  {target} ({comp['agent_b']['agent']}): composite={comp['agent_b']['composite']:.3f}",
                f"  Similarity: {comp['similarity']:.3f}",
            ]
            await self.send(agent, "\n".join(lines))

        elif sub == "record" and rest:
            # Record a trust event
            from trust_engine import TRUST_EVENTS
            event_type = rest.strip()
            if event_type not in TRUST_EVENTS:
                available = ", ".join(sorted(TRUST_EVENTS.keys()))
                await self.send(agent, f"Unknown event '{event_type}'. Available: {available}")
                return
            evt = TRUST_EVENTS[event_type]
            te.record_event(agent.name, evt["dimension"], evt["value"], evt["weight"])
            await self.send(agent, f"Recorded '{event_type}' -> {evt['dimension']}={evt['value']} (weight={evt['weight']})")

        elif rest:
            # Show another agent's trust profile
            target = sub  # first arg is the agent name
            profile = te.get_profile(target)
            if not profile.is_meaningful():
                await self.send(agent, f"{target} doesn't have meaningful trust history yet.")
                return
            summary = profile.summary()
            lines = [
                f"\u2550\u2550\u2550 Trust Profile: {target} \u2550\u2550\u2550",
                f"  Composite: {summary['composite']:.3f}",
                f"  Meaningful: yes",
                f"  Review exempt: {'yes' if summary['review_exempt'] else 'no'}",
                f"  Total events: {summary['total_events']}",
                "  Dimensions:",
            ]
            for dim, score in summary["dimensions"].items():
                lines.append(f"    {dim}: {score:.3f}")
            await self.send(agent, "\n".join(lines))

        else:
            await self.send(agent, "Usage: trust | trust <agent> | trust board | trust compare <agent> | trust record <event_type>")

    async def cmd_say(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Say what?")
            return
        name = agent.display_name
        self.world.log(agent.room_name, f"{name} says: {args}")
        await self.broadcast_room(agent.room_name, f'{name} says: "{args}"', exclude=agent.name)
        await self.send(agent, f'You say: "{args}"')

        # Route through CommsRouter for git logging
        if self.world.comms_router:
            try:
                self.world.comms_router.route(agent.name, "say", args, room=agent.room_name)
            except Exception:
                pass

        # Check if any NPCs in the room should respond
        npcs_here = [(n, d) for n, d in self.world.npcs.items() if d.get("room") == agent.room_name]
        for npc_name, npc_data in npcs_here:
            # NPCs respond if spoken to directly or randomly 30% of the time
            if npc_name.lower() in args.lower() or agent.name.lower() == npc_data.get("creator","").lower() or len(args) > 20:
                await self.send(agent, f"  {npc_name} is thinking...")
                try:
                    response = await npc_respond(npc_name, npc_data, args, name)
                except Exception as e:
                    response = f"*mumbles incomprehensibly*" 
                await self.broadcast_room(agent.room_name, f'{npc_name} says: "{response}"')
                self.world.log(agent.room_name, f"NPC {npc_name} says: {response}")

    async def cmd_tell(self, agent: Agent, args: str):
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: tell <agent> <message>")
            return
        target_name, msg = parts[0], parts[1]
        # Route through CommsRouter for git logging
        if self.world.comms_router:
            try:
                self.world.comms_router.route(agent.name, "tell", msg, room=agent.room_name, target=target_name)
            except Exception:
                pass
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
        # Route through CommsRouter for git logging
        if self.world.comms_router:
            try:
                self.world.comms_router.route(agent.name, "gossip", args, room=agent.room_name)
            except Exception:
                pass

    async def cmd_ooc(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "OOC what?")
            return
        real = agent.name
        mask_info = f" (wearing mask: {agent.mask})" if agent.is_masked else ""
        self.world.log("ooc", f"[{real}{mask_info}] {args}")
        await self.broadcast_all(f"[OOC] {real}{mask_info}: {args}", exclude=agent.name)
        await self.send(agent, f"[OOC] You: {args}")
        # Route through CommsRouter for git logging
        if self.world.comms_router:
            try:
                self.world.comms_router.route(agent.name, "ooc", args, room=agent.room_name)
            except Exception:
                pass

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
        # Room runtime: shutdown old, boot new
        old_runtime = self.world.runtimes.get(old_room)
        if old_runtime:
            old_runtime.shutdown(agent.name)
            self.world.log("runtime", f"{agent.name} shutdown {old_room}")
        new_runtime = self.world.runtimes.get(target_name)
        if new_runtime:
            boot_output = new_runtime.boot(agent.name)
            await self.send(agent, boot_output)
            self.world.log("runtime", f"{agent.name} booted {target_name}")
        # Algorithmic NPC greeting on room enter
        for npc_name, algo_npc in self.world.algo_npcs.items():
            npc_data = self.world.npcs.get(npc_name, {})
            if npc_data.get("room") == target_name:
                await self.send(agent, f"  {npc_name}: {algo_npc.greeting}")
                self.world.log("npc", f"Algo NPC {npc_name} greeted {agent.name}")
        # Studio: show live connection status for special rooms
        studio = getattr(self, '_studio', None)
        if studio and target_name in studio.rooms:
            studio_info = studio.enter(target_name, agent.name)
            if studio_info:
                await self.send(agent, studio_info)
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
  read [manual]         — Read notes (or room manual)
  mask <name> -desc <d> — Put on a character mask
  unmask                — Remove your mask
  spawn <name> -role <> — Create an NPC (they respond with AI!)
  dismiss <name>        — Dismiss an NPC
  status <state>        — Set status: working/thinking/idle/sleeping
  who                   — Fleet roster (active + ghosts)
  motd                  — Message of the day
  setmotd <text>        — Set MOTD (lighthouse keepers only)
  mail <agent> <subj>   — Send mail to another agent
  inbox [unread]        — Check your mailbox
  library               — Browse the fleet library
  library search <q>    — Search the library
  equip                 — View your equipment
  equip grant <id>      — Equip an item
  schedule [slots]       — Fleet scheduler status & daily model schedule
  scene build <r> <c> <s> <m> [sched] — Build & activate a scene
  scene activate <room>  — Activate a room's scene
  skin                  — List available personality skins
  cartridge [list|load|eject|status] — TwinCartridge identity system
  identity [dial|shift|blend] — Identity perspective controls
  compatibility <agent>  — Check identity compatibility
  help (?)              — This message
  quit                  — Disconnect (your ghost lingers)
═══════════════════════════════""")

    # ═══════════════════════════════════════════════════════════
    # flux_lcar Bridge Commands
    # ═══════════════════════════════════════════════════════════

    def _ensure_flux_ship(self):
        """Lazy-initialize flux_lcar Ship if available."""
        if self.world.flux_ship is not None:
            return self.world.flux_ship
        try:
            from flux_lcar import Ship, AlertLevel, Formality
            valid_levels = {"GREEN": AlertLevel.GREEN, "YELLOW": AlertLevel.YELLOW, "RED": AlertLevel.RED}
            valid_formalities = {"NAVAL": Formality.NAVAL, "PROFESSIONAL": Formality.PROFESSIONAL,
                                "TNG": Formality.TNG, "CASUAL": Formality.CASUAL, "MINIMAL": Formality.MINIMAL}
            alert = valid_levels.get(self.world.alert_level, AlertLevel.GREEN)
            form = valid_formalities.get(self.world.formality, Formality.PROFESSIONAL)
            ship = Ship("cocapn-1")
            ship.alert_level = alert
            ship.formality = form
            # Mirror existing agents into flux_ship
            for name, agent in self.world.agents.items():
                fa = ship.add_agent(agent.name, agent.role or "crew")
                fa.room_id = agent.room_name
                ship.rooms.setdefault(agent.room_name, ship.add_room(agent.room_name, agent.room_name, ""))
            self.world.flux_ship = ship
            return ship
        except Exception as e:
            self.world.flux_ship = None
            return None

    async def cmd_alert(self, agent: Agent, args: str):
        """Set ship alert level (GREEN/YELLOW/RED) — broadcasts to all connected agents."""
        level = (args.strip().upper() if args else "").strip()
        valid = {"GREEN", "YELLOW", "RED"}
        if level not in valid:
            await self.send(agent, f"Usage: alert <GREEN|YELLOW|RED>\n  Current: {self.world.alert_level}")
            return
        old_level = self.world.alert_level
        self.world.alert_level = level

        # Sync to flux_ship if available
        ship = self._ensure_flux_ship()
        if ship:
            try:
                from flux_lcar import AlertLevel
                alert_map = {"GREEN": AlertLevel.GREEN, "YELLOW": AlertLevel.YELLOW, "RED": AlertLevel.RED}
                ship.alert_level = alert_map[level]
            except Exception:
                pass

        self.world.log("alert", f"{agent.display_name} changed alert: {old_level} -> {level}")

        # Broadcast to all connected agents
        emoji = {"GREEN": "\u2705", "YELLOW": "\u26a0\ufe0f", "RED": "\U0001f534"}
        msg = f"\U0001f6e1\ufe0f {emoji.get(level, '')} SHIP ALERT: {level} — set by {agent.display_name}"
        await self.send(agent, f"Alert level set to: {level}")
        await self.broadcast_all(msg, exclude=agent.name)

    async def cmd_formality(self, agent: Agent, args: str):
        """Set output formality style (NAVAL/PROFESSIONAL/TNG/CASUAL/MINIMAL)."""
        mode = (args.strip().upper() if args else "").strip()
        valid = {"NAVAL", "PROFESSIONAL", "TNG", "CASUAL", "MINIMAL"}
        if mode not in valid:
            await self.send(agent, f"Usage: formality <NAVAL|PROFESSIONAL|TNG|CASUAL|MINIMAL>\n  Current: {self.world.formality}")
            return
        self.world.formality = mode

        # Sync to flux_ship if available
        ship = self._ensure_flux_ship()
        if ship:
            try:
                from flux_lcar import Formality
                form_map = {"NAVAL": Formality.NAVAL, "PROFESSIONAL": Formality.PROFESSIONAL,
                           "TNG": Formality.TNG, "CASUAL": Formality.CASUAL, "MINIMAL": Formality.MINIMAL}
                ship.formality = form_map[mode]
            except Exception:
                pass

        self.world.log("formality", f"{agent.display_name} set formality to {mode}")
        await self.send(agent, f"Formality set to: {mode}")

    async def cmd_channels(self, agent: Agent, args: str):
        """List available communication channels."""
        ship = self._ensure_flux_ship()
        lines = ["═══ Communication Channels ═══"]
        if ship:
            ship_channels = list(ship.channels.keys())
            flux_channels = []
            for a in ship.agents.values():
                flux_channels.extend(a.channels.keys())
            all_channels = sorted(set(ship_channels + flux_channels))
            if all_channels:
                for ch in all_channels:
                    lines.append(f"  \U0001f4e1 {ch}")
            else:
                lines.append("  (no external channels wired — use bridge_channel to connect)")
            # Also show built-in message types
            lines.append("")
            lines.append("  ── Internal Message Types ──")
            try:
                from flux_lcar import MsgType
                for mt in MsgType:
                    lines.append(f"  {mt.name:8s} — {mt.value}")
            except Exception:
                lines.append("  SAY, TELL, YELL, GOSSIP, ALERT, BOTTLE")
        else:
            lines.append("  flux_lcar bridge not available.")
            lines.append("  Internal types: SAY, TELL, YELL, GOSSIP, ALERT, BOTTLE")
        await self.send(agent, "\n".join(lines))

    async def cmd_hail(self, agent: Agent, args: str):
        """Broadcast on a channel (flux_lcar routing)."""
        if not args:
            await self.send(agent, "Usage: hail <channel> <message>")
            return
        parts = args.split(None, 1)
        channel = parts[0]
        message = parts[1] if len(parts) > 1 else ""
        if not message:
            await self.send(agent, "Usage: hail <channel> <message>")
            return

        ship = self._ensure_flux_ship()
        if ship and channel in ship.channels:
            # Route through flux_lcar channel
            sender = agent.display_name
            result = ship.channels[channel](f"[{sender}@{agent.room_name}] {message}")
            self.world.log("hail", f"{sender} hailed {channel}: {message}")
            await self.send(agent, f"You hail {channel}: \"{message}\"")
        elif ship:
            # Try agent-level channel
            delivered = False
            for a in ship.agents.values():
                if channel in a.channels:
                    a.channels[channel](f"[{agent.display_name}] {message}")
                    delivered = True
            if delivered:
                self.world.log("hail", f"{agent.display_name} hailed {channel}: {message}")
                await self.send(agent, f"You hail {channel}: \"{message}\"")
            else:
                await self.send(agent, f"Channel '{channel}' not found. Type 'channels' to see available channels.")
        else:
            # Fallback: treat as gossip
            await self.send(agent, f"flux_lcar bridge not available. Falling back to gossip.")
            await self.cmd_gossip(agent, f"[hail:{channel}] {message}")

    async def cmd_ship_status(self, agent: Agent, args: str):
        """Show flux_lcar Ship status (rooms, crew, gauges)."""
        ship = self._ensure_flux_ship()
        if not ship:
            await self.send(agent, "flux_lcar bridge not available.")
            return

        lines = [
            f"═══ {ship.name} — Ship Status ═══",
            f"Alert: {ship.alert_level.name}",
            f"Formality: {ship.formality.name}",
            f"Tick: {ship.tick_number}",
            f"Rooms: {len(ship.rooms)}",
            f"Agents: {len(ship.agents)}",
            f"Channels: {len(ship.channels)}",
            f"Messages logged: {len(ship.message_log)}",
            ""
        ]

        if ship.rooms:
            lines.append("  ── Rooms ──")
            for rid, room in ship.rooms.items():
                booted = "\u2705" if room.booted else ""
                gauge_count = len(room.gauges)
                agent_count = len(room.agents)
                exit_count = len(room.exits)
                info_parts = []
                if gauge_count:
                    info_parts.append(f"{gauge_count} gauges")
                if agent_count:
                    info_parts.append(f"{agent_count} crew")
                if exit_count:
                    info_parts.append(f"{exit_count} exits")
                info = ", ".join(info_parts) if info_parts else "empty"
                lines.append(f"  {booted} {rid}: {room.name} ({info})")

        if ship.agents:
            lines.append("")
            lines.append("  ── Crew ──")
            for name, a in ship.agents.items():
                station = a.station or a.room_id or "unassigned"
                role = a.role
                lines.append(f"  {name} ({role}) @ {station}")

        if ship.channels:
            lines.append("")
            lines.append("  ── Wired Channels ──")
            for ch in ship.channels:
                lines.append(f"  \U0001f4e1 {ch}")

        # Show gauges for rooms that have them
        rooms_with_gauges = [(rid, r) for rid, r in ship.rooms.items() if r.gauges]
        if rooms_with_gauges:
            lines.append("")
            lines.append("  ── Gauges ──")
            for rid, room in rooms_with_gauges:
                for g in room.gauges.values():
                    lines.append(f"  [{rid}] {g.name}: {g.value:.1f}{g.unit} {g.bar} {g.status}")

        lines.append("")
        await self.send(agent, "\n".join(lines))

    
    async def cmd_quit(self, agent: Agent, args: str):
        agent.status = "idle"
        self.world.update_ghost(agent)
        await self.send(agent, "Fair winds. Your ghost lingers here. See you in the next tide.")
        if agent.name in self.world.agents:
            del self.world.agents[agent.name]
            await self.broadcast_room(agent.room_name, f"{agent.display_name} has left the MUD. Their ghost lingers.")
        # Shutdown any active runtime
        runtime = self.world.runtimes.get(agent.room_name)
        if runtime:
            runtime.shutdown(agent.name)


    # ═══════════════════════════════════════════════════════════
    # Room Runtime Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_runtime(self, agent: Agent, args: str):
        """Execute commands in the current room's runtime."""
        runtime = self.world.runtimes.get(agent.room_name)
        if not runtime:
            await self.send(agent, "No runtime in this room. Try: go lab, go workshop, or go lighthouse.")
            return
        if not args:
            cmds = list(runtime.commands.keys())
            state = runtime.state.get("status", "unknown")
            lines = [f"\u2550\u2550\u2550 {runtime.name} Runtime \u2550\u2550\u2550",
                     f"  Type: {runtime.runtime_type}",
                     f"  Status: {state}",
                     f"  Commands: {', '.join(cmds) if cmds else 'none'}",
                     f"  Operators' notes: {len(runtime.operator_notes)}"]
            await self.send(agent, "\n".join(lines))
            return
        parts = args.split(None, 1)
        cmd = parts[0]
        cmd_args = parts[1] if len(parts) > 1 else ""
        result = runtime.execute(cmd, cmd_args, agent.name)
        if "error" in result:
            await self.send(agent, f"Runtime error: {result['error']}")
        else:
            output = result.get("output", result.get("result", "Done."))
            await self.send(agent, f"  {output}")
        self.world.log("runtime", f"{agent.name} executed '{cmd}' in {agent.room_name}")

    # ═══════════════════════════════════════════════════════════
    # Instinct System Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_instinct(self, agent: Agent, args: str):
        """Show current instincts and reflexes for this agent."""
        try:
            from instinct import InstinctEngine
        except ImportError:
            await self.send(agent, "Instinct system not available.")
            return
        state = self.world.instinct_states.get(agent.name)
        if not state:
            await self.send(agent, "No instinct data yet. Instincts are evaluated every 30s.")
            return
        engine = InstinctEngine()
        reflexes = engine.tick(
            energy=state["energy"], threat=state["threat"],
            trust=state["trust"], has_work=state["has_work"],
            idle_ticks=state["idle_ticks"])
        lines = ["\u2550\u2550\u2550 Instinct Profile \u2550\u2550\u2550",
                 f"  Energy:   {state['energy']:.0%}",
                 f"  Threat:   {state['threat']:.0%}",
                 f"  Trust:    {state['trust']:.0%}",
                 f"  Has work: {state['has_work']}",
                 f"  Idle:     {state['idle_ticks']} ticks",
                 ""]
        if reflexes:
            lines.append("  Active reflexes:")
            for r in reflexes[:5]:
                lines.append(f"    [{r.instinct:10s}] {r.action}: {r.text}")
        else:
            lines.append("  No active instincts. All clear.")
        await self.send(agent, "\n".join(lines))

    # ═══════════════════════════════════════════════════════════
    # Fleet Activity Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_fleet(self, agent: Agent, args: str):
        """Show recent fleet activity from GitHub."""
        events = self.world.fleet_events
        if not events:
            await self.send(agent, "\u2550\u2550\u2550 Fleet Activity \u2550\u2550\u2550\n  No recent activity. The fleet is quiet.")
            return
        lines = ["\u2550\u2550\u2550 Fleet Activity \u2550\u2550\u2550"]
        for event in events[-10:]:
            lines.append(f"  {event}")
        lines.append(f"\n  Showing {min(len(events), 10)}/{len(events)} events")
        await self.send(agent, "\n".join(lines))

    # ═══════════════════════════════════════════════════════════
    # DeckBoss Bridge Commands (deckboss_bridge.py)
    # ═══════════════════════════════════════════════════════════

    async def cmd_sheet(self, agent: Agent, args: str):
        """Show a D&D-style character sheet for an agent."""
        try:
            from deckboss_bridge import generate_character_sheet
        except ImportError:
            await self.send(agent, "Character sheet system not available.")
            return
        target = args.strip() if args.strip() else agent.name
        # Build a simple profile from available data
        skills = {"fleet_navigation": 3, "combat_scripts": 2, "room_building": 1, "log_writing": 4}
        sheet = generate_character_sheet(
            agent_name=target, level=1, completed_quests=[], skills=skills)
        await self.send(agent, f"\n═══ Character Sheet: {target} ═══\n{sheet}")
        self.world.log("deckboss", f"{agent.name} viewed character sheet for {target}")

    async def cmd_bootcamp(self, agent: Agent, args: str):
        """Show bootcamp levels and agent progression."""
        try:
            from deckboss_bridge import BOOTCAMP_LEVELS
        except ImportError:
            await self.send(agent, "Bootcamp system not available.")
            return
        lines = ["═══ Fleet Bootcamp — Onboarding Levels ═══", ""]
        for level, data in BOOTCAMP_LEVELS.items():
            marker = "✅" if level <= 1 else "⬜"
            lines.append(f"  {marker} Level {level}: {data['name']}")
            lines.append(f"     Room: {data['room']}  NPC: {data.get('npc', 'self-guided')}")
            lines.append(f"     Objective: {data['objective']}")
            skills = ", ".join(data.get("skills", []))
            lines.append(f"     Skills: {skills}")
            lines.append("")
        lines.append("  Current level: 1 (Harbor Orientation)")
        lines.append("  Complete each level to unlock the next.")
        await self.send(agent, "\n".join(lines))
        self.world.log("deckboss", f"{agent.name} viewed bootcamp levels")

    async def cmd_deckboss(self, agent: Agent, args: str):
        """Show the DeckBoss dashboard — holodeck backend status."""
        deckboss = self.world.deckboss
        if not deckboss:
            await self.send(agent, "DeckBoss bridge not available.")
            return
        try:
            dashboard = deckboss.format_dashboard()
            await self.send(agent, f"\n{dashboard}")
        except Exception as e:
            await self.send(agent, f"DeckBoss error: {e}")
        self.world.log("deckboss", f"{agent.name} viewed deckboss dashboard")

    # ═══════════════════════════════════════════════════════════
    # Perception Room Commands (perception_room.py)
    # ═══════════════════════════════════════════════════════════

    async def cmd_perception(self, agent: Agent, args: str):
        """Show agent's perception profile from current session."""
        tracker = getattr(agent, 'perception', None)
        if not tracker:
            await self.send(agent, "No perception data yet. Perception is tracked automatically.")
            return
        try:
            analysis = tracker.analysis()
            if "error" in analysis:
                await self.send(agent, "No perception data yet.")
                return
            lines = [
                "═══ Perception Profile ═══",
                f"  Session: {analysis['session_id']}",
                f"  Room: {analysis['room']}",
                f"  Moments: {analysis['total_moments']}",
                f"  Avg confidence: {analysis['avg_confidence']:.0%}",
                f"  Trend: {analysis['confidence_trend']}",
                f"  Hesitations: {analysis['hesitation_count']}",
                f"  Help requests: {analysis['help_requests']}",
                f"  Retries: {analysis['retries']}",
                f"  Success rate: {analysis['success_rate']:.0%}",
                ""]
            if analysis.get("confusion_points"):
                lines.append("  Confusion points:")
                for cp in analysis["confusion_points"][:3]:
                    lines.append(f"    ? {cp['action']} -> {cp['target']}")
                lines.append("")
            if analysis.get("flow_states"):
                lines.append(f"  Flow states: {', '.join(analysis['flow_states'][:5])}")
            await self.send(agent, "\n".join(lines))
            self.world.log("perception", f"{agent.name} viewed perception profile")
        except Exception as e:
            await self.send(agent, f"Perception error: {e}")

    # ═══════════════════════════════════════════════════════════
    # Rival Combat Commands (rival_combat.py)
    # ═══════════════════════════════════════════════════════════

    async def cmd_duel(self, agent: Agent, args: str):
        """Initiate a duel between two agents against historical scenarios."""
        try:
            from rival_combat import BackTestEngine, RivalAgent, RivalMatch
        except ImportError:
            await self.send(agent, "Rival combat system not available.")
            return
        parts = args.strip().split()
        if len(parts) < 2:
            await self.send(agent, "Usage: duel <agent_a> <agent_b> [rounds=3]")
            return
        name_a, name_b = parts[0], parts[1]
        rounds = int(parts[2]) if len(parts) > 2 else 3
        seed_rules = [
            {"condition": "all gauges normal", "action": "continue monitoring"},
            {"condition": "gauge elevated", "action": "flag for attention, increase frequency"},
            {"condition": "gauge critical", "action": "alert human immediately, safe fallback"},
            {"condition": "regression", "action": "bisect recent commits to find cause"},
            {"condition": "service down", "action": "circuit break and route around"},
            {"condition": "memory climbing", "action": "dump heap, identify leaking process"},
        ]
        agent_a = RivalAgent(name_a)
        agent_b = RivalAgent(name_b)
        agent_a.seed(list(seed_rules))
        agent_b.seed(list(seed_rules))
        await self.send(agent, f"\n⚔️ {name_a} vs {name_b} — {rounds} rounds, {len(BackTestEngine.SCENARIOS)} scenarios")
        try:
            match = RivalMatch(agent_a, agent_b)
            result = match.run_match(rounds=rounds)
            report = match.generate_match_report()
            await self.send(agent, f"\n{report}")
            self.world.log("rival_combat", f"{agent.name} ran duel: {name_a} vs {name_b} -> {result['winner']}")
        except Exception as e:
            await self.send(agent, f"Duel error: {e}")

    async def cmd_backtest(self, agent: Agent, args: str):
        """Run scripts against historical scenarios."""
        try:
            from rival_combat import BackTestEngine
        except ImportError:
            await self.send(agent, "Backtest engine not available.")
            return
        if not args.strip():
            await self.send(agent, "Usage: backtest <scenario_id|all>")
            return
        scenarios = BackTestEngine.SCENARIOS
        arg = args.strip().lower()
        if arg != "all":
            scenarios = [s for s in scenarios if s.id.lower() == arg]
            if not scenarios:
                await self.send(agent, f"Scenario '{arg}' not found. Use 'all' or IDs: {', '.join(s.id for s in BackTestEngine.SCENARIOS)}")
                return
        rules = [
            {"condition": "all gauges normal", "action": "continue monitoring"},
            {"condition": "gauge elevated", "action": "flag for attention"},
            {"condition": "gauge critical", "action": "alert human"},
            {"condition": "regression", "action": "bisect commits"},
            {"condition": "service down", "action": "circuit break"},
            {"condition": "memory climbing", "action": "dump heap"},
        ]
        lines = ["═══ Backtest Results ═══", ""]
        total_score = 0
        passed = 0
        for scenario in scenarios:
            result = BackTestEngine.run(rules, scenario)
            status = "✅" if result["passed"] else "❌"
            lines.append(f"  {status} {scenario.id}: {scenario.name}")
            lines.append(f"     Score: {result['score']:.2f}  Action: {result['matched_action'][:50]}")
            total_score += result["score"]
            if result["passed"]:
                passed += 1
        lines.append(f"\n  Total: {total_score:.2f}  Passed: {passed}/{len(scenarios)}")
        await self.send(agent, "\n".join(lines))
        self.world.log("rival_combat", f"{agent.name} ran backtest: {passed}/{len(scenarios)} passed")

    # ═══════════════════════════════════════════════════════════
    # Actualization Loop Commands (actualization_loop.py)
    # ═══════════════════════════════════════════════════════════

    def _get_gauge_monitor(self):
        """Get or create the gauge monitor (shared across all agents)."""
        if not hasattr(self, '_gauge_monitor') or self._gauge_monitor is None:
            try:
                from actualization_loop import GaugeMonitor
                self._gauge_monitor = GaugeMonitor()
            except ImportError:
                self._gauge_monitor = None
        return self._gauge_monitor

    async def cmd_gauges(self, agent: Agent, args: str):
        """Show live system gauges."""
        gm = self._get_gauge_monitor()
        if not gm:
            await self.send(agent, "Gauge system not available.")
            return
        gm.read("system_load")
        gm.read("keeper_health")
        dashboard = gm.dashboard()
        await self.send(agent, f"\n{dashboard}")
        self.world.log("gauges", f"{agent.name} viewed system gauges")

    async def cmd_aar(self, agent: Agent, args: str):
        """Show after-action report for the current session."""
        try:
            from actualization_loop import AfterActionReport
        except ImportError:
            await self.send(agent, "AAR system not available.")
            return
        import time
        aar = AfterActionReport(agent.name, args.strip() or f"session-{int(time.time())}")
        aar.record_event("connect", f"Agent {agent.name} connected to {agent.room_name}", "success")
        aar.add_lesson(f"Session started in {agent.room_name}.", "AAR requested by agent.")
        report = aar.generate_report()
        await self.send(agent, f"\n{report}")
        self.world.log("aar", f"{agent.name} generated AAR")

    # ═══════════════════════════════════════════════════════════
    # Studio Engine Commands
    # ═══════════════════════════════════════════════════════════

    # ═══════════════════════════════════════════════════════════
    # Comms System Commands (comms_system.py)
    # ═══════════════════════════════════════════════════════════

    async def cmd_mail(self, agent: Agent, args: str):
        """Send mail to another agent via the comms system."""
        try:
            from comms_system import Mailbox
        except ImportError:
            await self.send(agent, "Mail system not available.")
            return
        parts = args.split(None, 2)
        if len(parts) < 2:
            await self.send(agent, "Usage: mail <agent> <subject> [-body <message>]")
            return
        target = parts[0]
        subject = parts[1]
        body = ""
        if len(parts) > 2:
            body_parts = parts[2].split(" -body ", 1)
            if len(body_parts) > 1:
                body = body_parts[1]
            else:
                body = parts[2]
        mailbox = self.world.get_mailbox()
        if not mailbox:
            await self.send(agent, "Mail system not initialized.")
            return
        mail_id = mailbox.send(target, agent.name, subject, body)
        await self.send(agent, f"Mail sent to {target}: {subject} (id: {mail_id})")
        self.world.log("mail", f"{agent.name} sent mail to {target}: {subject}")

    async def cmd_inbox(self, agent: Agent, args: str):
        """Check your mailbox."""
        try:
            from comms_system import Mailbox
        except ImportError:
            await self.send(agent, "Mail system not available.")
            return
        mailbox = self.world.get_mailbox()
        if not mailbox:
            await self.send(agent, "Mail system not initialized.")
            return
        unread_only = args.strip().lower() == "unread"
        messages = mailbox.check(agent.name, unread_only=unread_only)
        if not messages:
            label = "unread" if unread_only else ""
            await self.send(agent, f"Your mailbox is empty ({label}filtered).".strip())
            return
        lines = [f"═══ Inbox ({len(messages)} messages) ═══", ""]
        for msg in messages[-20:]:
            status = "  📭" if msg.get("read") else "  📬"
            lines.append(f"{status} [{msg['id']}] From: {msg['from']}")
            lines.append(f"     Subject: {msg['subject']}")
            if msg.get("body"):
                lines.append(f"     {msg['body'][:80]}")
            lines.append("")
        lines.append("  Tip: Use 'mail read <id>' to read a specific message")
        await self.send(agent, "\n".join(lines))
        self.world.log("mail", f"{agent.name} checked inbox: {len(messages)} messages")

    async def cmd_library(self, agent: Agent, args: str):
        """Search or browse the fleet library."""
        try:
            from comms_system import Library
        except ImportError:
            await self.send(agent, "Library system not available.")
            return
        library = self.world.library
        if not library:
            await self.send(agent, "Library not initialized.")
            return
        arg = args.strip().lower()
        if not arg:
            books = library.browse()
            lines = [f"═══ Fleet Library ({len(books)} books) ═══", ""]
            for book in books[:15]:
                lines.append(f"  📚 {book['title']} ({book['category']}) by {book['author']}")
            if len(books) > 15:
                lines.append(f"  ... and {len(books) - 15} more")
            lines.append(f"\n  Categories: {', '.join(library.categories())}")
            lines.append("  Usage: library search <query> | library browse <category>")
            await self.send(agent, "\n".join(lines))
        elif arg.startswith("search "):
            query = arg[7:].strip()
            if not query:
                await self.send(agent, "Usage: library search <query>")
                return
            results = library.search(query)
            if not results:
                await self.send(agent, f"No books found matching '{query}'.")
                return
            lines = [f"═══ Library Search: '{query}' ({len(results)} results) ═══", ""]
            for book in results[:10]:
                lines.append(f"  📚 {book['title']} ({book['category']})")
                lines.append(f"     {book.get('content', '')[:100]}")
                lines.append("")
            await self.send(agent, "\n".join(lines))
        elif arg.startswith("browse "):
            category = arg[7:].strip()
            books = library.browse(category)
            if not books:
                await self.send(agent, f"No books in category '{category}'.")
                return
            lines = [f"═══ Library: {category} ({len(books)} books) ═══", ""]
            for book in books[:10]:
                lines.append(f"  📚 {book['title']} by {book['author']}")
            await self.send(agent, "\n".join(lines))
        elif arg.startswith("read "):
            book_id = arg[5:].strip()
            book = library.checkout(book_id)
            if not book:
                await self.send(agent, f"No book found with id '{book_id}'.")
                return
            lines = [
                f"═══ {book['title']} ═══",
                f"  Author: {book['author']}",
                f"  Category: {book['category']}",
                f"  Checkouts: {book.get('checkouts', 0)}",
                "",
                f"  {book['content']}",
            ]
            await self.send(agent, "\n".join(lines))
        else:
            await self.send(agent, "Usage: library | library search <q> | library browse <cat> | library read <id>")
        self.world.log("library", f"{agent.name} accessed library: {arg}")

    async def cmd_equip(self, agent: Agent, args: str):
        """Equip items or view equipment inventory."""
        try:
            from comms_system import Equipment
        except ImportError:
            await self.send(agent, "Equipment system not available.")
            return
        router = self.world.ensure_comms()
        if not router:
            await self.send(agent, "Equipment system not initialized.")
            return
        equipment = router.equipment
        arg = args.strip().lower()
        if not arg:
            items = equipment.inventory(agent.name)
            if not items:
                lines = ["═══ Equipment ═══", "", "  You have no equipment.",
                        "", "  Available items:"]
                for item_id, eq in Equipment.EQUIPMENT_DEFS.items():
                    lines.append(f"    {eq['name']} (Lv.{eq['level']}) — {eq['desc'][:50]}")
                await self.send(agent, "\n".join(lines))
                return
            lines = ["═══ Equipment ═══", ""]
            for item in items:
                lines.append(f"  {item['name']} — {item['desc'][:60]}")
                lines.append(f"    Grants: {', '.join(item.get('grants', []))}")
                lines.append("")
            await self.send(agent, "\n".join(lines))
        elif arg.startswith("grant "):
            item_id = arg[6:].strip()
            if item_id not in Equipment.EQUIPMENT_DEFS:
                await self.send(agent, f"Unknown item: {item_id}")
                return
            if equipment.grant(agent.name, item_id):
                eq = Equipment.EQUIPMENT_DEFS[item_id]
                await self.send(agent, f"Equipped: {eq['name']} — {eq['desc']}")
                await self.send(agent, f"  Grants: {', '.join(eq['grants'])}")
                self.world.log("equipment", f"{agent.name} equipped {item_id}")
            else:
                await self.send(agent, f"Failed to equip {item_id}.")
        elif arg == "list":
            lines = ["═══ Available Equipment ═══", ""]
            for item_id, eq in Equipment.EQUIPMENT_DEFS.items():
                lines.append(f"  {eq['name']} (Lv.{eq['level']}) — {eq['desc'][:50]}")
                lines.append(f"    ID: {item_id}  Grants: {', '.join(eq['grants'])}")
                lines.append("")
            await self.send(agent, "\n".join(lines))
        elif arg.startswith("check "):
            ability = arg[6:].strip()
            has = equipment.has(agent.name, ability)
            status = "✅ Yes" if has else "❌ No"
            await self.send(agent, f"  Ability '{ability}': {status}")
        else:
            await self.send(agent, "Usage: equip | equip grant <id> | equip list | equip check <ability>")
        self.world.log("equipment", f"{agent.name} equip command: {arg}")

    # ═══════════════════════════════════════════════════════════
    # Agentic Oversight Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_oversee(self, agent, args):
        """Start/stop an oversight session for monitoring operations.

        Usage:
          oversee start <operation_name>  — begin monitoring
          oversee tick <changes>|<gauges>|[human_input]
          oversee stop                    — end session and show report
          oversee perspective             — show agent first-person view
          oversee                        — show current session status
        """
        try:
            from agentic_oversight import OversightSession, HumanPlayer
        except ImportError:
            await self.send(agent, "Agentic oversight module not available.")
            return

        parts = args.strip().split(None, 1)
        subcmd = parts[0] if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "start":
            if not sub_args:
                await self.send(agent, "Usage: oversee start <operation_name>")
                return
            op_name = sub_args.strip()
            session = OversightSession(op_name, agent.name)
            self.world.oversight_sessions[agent.name] = session
            await self.send(agent,
                "\n  == Oversight Session Started ==\n"
                "  Operation: " + op_name + "\n"
                "  Agent: " + agent.name + "\n"
                "  Script: v" + str(session.script.version) + " (" + str(len(session.script.rules)) + " seed rules)\n"
                "  Use 'oversee tick ...' to record monitoring ticks.\n"
                "  Use 'oversee stop' to end and generate report.")
            self.world.log("oversight", agent.name + " started oversight: " + op_name)

        elif subcmd == "tick":
            session = self.world.oversight_sessions.get(agent.name)
            if not session:
                await self.send(agent, "No active oversight session. Use 'oversee start <name>' first.")
                return
            tick_parts = sub_args.split("|", 2)
            changes_json = tick_parts[0].strip() if len(tick_parts) > 0 else "[]"
            gauges_json = tick_parts[1].strip() if len(tick_parts) > 1 else "{}"
            human_input = tick_parts[2].strip() if len(tick_parts) > 2 else ""
            try:
                changes = json.loads(changes_json) if changes_json else []
            except json.JSONDecodeError:
                changes = [{"desc": changes_json}]
            try:
                gauges = json.loads(gauges_json) if gauges_json else {}
            except json.JSONDecodeError:
                gauges = {}
            tick = session.tick(changes, gauges, human_input)
            lines = [
                "  Tick #" + str(tick.tick_num) + " | Script v" + str(tick.script_version),
                "  Action: " + tick.agent_action,
                "  Autonomy: " + str(round(tick.autonomy_score * 100)) + "%",
            ]
            if tick.nudges_needed:
                lines.append("  Nudge: human input received, script evolving")
            if tick.changes:
                for c in tick.changes[:3]:
                    lines.append("  Change: " + str(c.get("desc", str(c)[:60])))
            await self.send(agent, "\n" + "\n".join(lines))
            self.world.log("oversight", agent.name + " tick #" + str(tick.tick_num))

        elif subcmd == "stop":
            session = self.world.oversight_sessions.get(agent.name)
            if not session:
                await self.send(agent, "No active oversight session.")
                return
            report = session.end_session()
            await self.send(agent,
                "\n  == Oversight Report ==\n"
                "  Operation: " + report["operation"] + "\n"
                "  Ticks: " + str(report["ticks"]) + "\n"
                "  Autonomous: " + str(report["autonomous_ticks"]) + "\n"
                "  Nudged: " + str(report["nudged_ticks"]) + "\n"
                "  Final autonomy: " + str(round(report["final_autonomy"] * 100)) + "%\n"
                "  Script: v" + str(report["script_evolution"]["initial_version"]) + " -> v" + str(report["script_evolution"]["final_version"]) + "\n"
                "  Rules added: " + str(report["script_evolution"]["rules_added"]) + "\n"
                "  Rules adapted: " + str(report["script_evolution"]["rules_adapted"]))
            self.world.log("oversight", agent.name + " ended oversight: " + report["operation"])
            del self.world.oversight_sessions[agent.name]

        elif subcmd == "perspective":
            session = self.world.oversight_sessions.get(agent.name)
            if not session:
                await self.send(agent, "No active oversight session.")
                return
            perspective = session.generate_perspective()
            await self.send(agent, "\n" + perspective)

        else:
            session = self.world.oversight_sessions.get(agent.name)
            if session:
                await self.send(agent,
                    "  Active oversight: " + session.operation + "\n"
                    "  Ticks: " + str(len(session.ticks)) + "\n"
                    "  Script: v" + str(session.script.version) + "\n"
                    "  Usage: oversee tick|stop|perspective")
            elif self.world.oversight_sessions:
                lines = ["  == Active Oversight Sessions =="]
                for name, sess in self.world.oversight_sessions.items():
                    lines.append("  " + name + ": " + sess.operation + " (" + str(len(sess.ticks)) + " ticks)")
                await self.send(agent, "\n".join(lines))
            else:
                await self.send(agent,
                    "  No active oversight sessions.\n"
                    "  Usage: oversee start <operation_name>")

    async def cmd_script(self, agent, args):
        """Manage evolving scripts — show/save/load scripts that learn from demonstrations.

        Usage:
          script show [agent_name]  — show current evolving script
          script save              — save script to file
          script load <file_path>   — load script from file
          script readme             — show human-readable script explanation
        """
        try:
            from agentic_oversight import EvolvingScript, OversightSession
        except ImportError:
            await self.send(agent, "Agentic oversight module not available.")
            return

        parts = args.strip().split(None, 1)
        subcmd = parts[0] if parts else ""
        sub_args = parts[1] if len(parts) > 1 else ""

        if subcmd == "show":
            target = sub_args.strip() or agent.name
            session = self.world.oversight_sessions.get(target)
            if not session:
                await self.send(agent, "No active oversight session for '" + target + "'.")
                return
            script = session.script
            lines = [
                "  == Evolving Script: " + script.task_name + " ==",
                "  Version: " + str(script.version),
                "  Rules: " + str(len(script.rules)),
                "  Adaptations: " + str(len(script.adaptations)),
                "",
                "  Rules:",
            ]
            for i, rule in enumerate(script.rules, 1):
                source = rule.get("source", "unknown")
                lines.append("    " + str(i) + ". [" + source + "] When " + rule["condition"] + ":")
                lines.append("       -> " + rule["action"])
            await self.send(agent, "\n".join(lines))

        elif subcmd == "save":
            session = self.world.oversight_sessions.get(agent.name)
            if not session:
                await self.send(agent, "No active oversight session. Start one with 'oversee start'.")
                return
            script = session.script
            script_dir = Path("world") / "scripts"
            script_dir.mkdir(parents=True, exist_ok=True)
            safe_name = script.task_name.lower().replace(" ", "_").replace("/", "_")
            script_file = script_dir / (safe_name + "_v" + str(script.version) + ".json")
            data = {
                "task_name": script.task_name,
                "agent": script.agent,
                "version": script.version,
                "rules": script.rules,
                "adaptations": script.adaptations,
            }
            script_file.write_text(json.dumps(data, indent=2))
            await self.send(agent,
                "  Script saved: " + str(script_file) + "\n"
                "  Version: " + str(script.version) + ", Rules: " + str(len(script.rules)))
            self.world.log("oversight", agent.name + " saved script")

        elif subcmd == "load":
            if not sub_args:
                await self.send(agent, "Usage: script load <file_path>")
                return
            script_path = Path(sub_args.strip())
            if not script_path.exists():
                await self.send(agent, "File not found: " + str(script_path))
                return
            try:
                data = json.loads(script_path.read_text())
                script = EvolvingScript(data["task_name"], data["agent"])
                script.version = data.get("version", 1)
                script.rules = data.get("rules", script.rules)
                script.adaptations = data.get("adaptations", [])
                session = OversightSession(script.task_name, script.agent)
                session.script = script
                self.world.oversight_sessions[agent.name] = session
                await self.send(agent,
                    "  Script loaded: " + str(script_path) + "\n"
                    "  Task: " + script.task_name + "\n"
                    "  Version: " + str(script.version) + ", Rules: " + str(len(script.rules)))
                self.world.log("oversight", agent.name + " loaded script")
            except Exception as e:
                await self.send(agent, "Error loading script: " + str(e))

        elif subcmd == "readme":
            session = self.world.oversight_sessions.get(agent.name)
            if not session:
                await self.send(agent, "No active oversight session. Start one with 'oversee start'.")
                return
            readme = session.script.generate_readme()
            await self.send(agent, "\n" + readme)

        else:
            await self.send(agent,
                "  == Evolving Scripts ==\n"
                "  Usage:\n"
                "    script show [agent]   -- show current evolving script\n"
                "    script save           -- save script to file\n"
                "    script load <path>    -- load script from file\n"
                "    script readme         -- human-readable script explanation")

    # ═══════════════════════════════════════════════════════════
    # Studio Engine Commands
    # ═══════════════════════════════════════════════════════════

    async def cmd_studio(self, agent: Agent, args: str):
        """Live system connections -- shows status and executes live commands."""
        studio = getattr(self, '_studio', None)
        if not studio:
            await self.send(agent, "Studio system not available.")
            return
        if not args:
            lines = ["\u2550\u2550\u2550 Studio -- Live Systems \u2550\u2550\u2550"]
            for room_id, room in studio.rooms.items():
                conn = room.connection
                status_emoji = "\U0001f7e2" if conn and conn.status == "connected" else "\U0001f534"
                cmds = ", ".join(room.commands.keys()) if room.commands else "none"
                lines.append(f"  {status_emoji} {room.name} ({room.room_type}): {cmds}")
            lines.append("\n  Usage: studio <room> <command> [args]")
            lines.append("  Rooms: harbor, lighthouse, engine, workshop")
            await self.send(agent, "\n".join(lines))
            return
        parts = args.split(None, 2)
        if len(parts) < 1:
            await self.send(agent, "Usage: studio <room> [command] [args]")
            return
        room_id = parts[0]
        cmd = parts[1] if len(parts) > 1 else None
        cmd_args = parts[2] if len(parts) > 2 else ""
        if cmd:
            params = {}
            if cmd_args:
                try:
                    params = json.loads(cmd_args) if cmd_args.startswith("{") else {"arg": cmd_args}
                except json.JSONDecodeError:
                    params = {"arg": cmd_args}
            result = studio.execute(room_id, cmd, params, agent.name)
            if isinstance(result, dict):
                await self.send(agent, f"  Result: {json.dumps(result, indent=2)[:500]}")
            else:
                await self.send(agent, f"  {result}")
            self.world.log("studio", f"{agent.name} executed '{cmd}' in studio.{room_id}")
        else:
            info = studio.enter(room_id, agent.name)
            if info:
                await self.send(agent, info)


# ═══════════════════════════════════════════════════════════════
# Tabula Rasa Commands — permissions, budgets, spells, room library
# ═══════════════════════════════════════════════════════════════

    def check_permission(self, agent, min_level: int) -> tuple:
        """Check if agent has minimum permission level. Returns (allowed, level, title)."""
        try:
            from tabula_rasa import PermissionLevel
            level = self.world.permission_levels.get(agent.name, 0)
            title = PermissionLevel.title(level)
            return level >= min_level, level, title
        except Exception:
            return True, 0, "Unknown"  # graceful fallback

    async def cmd_budget(self, agent, args):
        """Show agent's budget (mana, hp, trust, xp, level)."""
        try:
            from tabula_rasa import PermissionLevel
        except ImportError:
            await self.send(agent, "Tabula Rasa module not available.")
            return
        budget = self.world.budgets.get(agent.name)
        if not budget:
            await self.send(agent, "No budget found. Reconnect to initialize.")
            return
        level = self.world.permission_levels.get(agent.name, 0)
        title = PermissionLevel.title(level)
        b = budget.to_dict()
        lines = [
            f"═══ Budget: {agent.name} ═══",
            f"  Title:     {title} (Level {b['level']})",
            f"  Mana:      {b['mana']}/{b['mana_max']}",
            f"  HP:        {b['hp']}/{b['hp_max']}",
            f"  Trust:     {b['trust']:.2f}",
            f"  XP:        {b['xp']}",
            f"  Reviews:   {'REQUIRED' if b['reviews_required'] else 'TRUSTED (auto-approved)'}",
            f"  Tasks:     {b['tasks_completed']} completed, {b['tasks_under_budget']} under budget, {b['tasks_over_delivered']} over-delivered",
        ]
        await self.send(agent, "\n".join(lines))

    async def cmd_cast(self, agent, args):
        """Cast a spell (checks permission level and mana, executes real effects)."""
        try:
            from tabula_rasa import PermissionLevel, SpellBook
        except ImportError:
            await self.send(agent, "Tabula Rasa module not available.")
            return
        if not args:
            await self.send(agent, "Usage: cast <spell_name> [arguments]")
            return
        budget = self.world.budgets.get(agent.name)
        if not budget:
            await self.send(agent, "No budget found. Reconnect to initialize.")
            return
        # Split spell name from additional arguments
        parts = args.strip().split(None, 1)
        spell_name = parts[0].lower()
        spell_args = parts[1] if len(parts) > 1 else ""

        result = SpellBook.cast(spell_name, budget.level, budget.mana)
        if "error" in result:
            await self.send(agent, f"Cast failed: {result['error']}")
        elif result.get("success"):
            mana_cost = result["mana_cost"]
            budget.spend_mana(mana_cost)
            self.world.log("spells", f"{agent.name} cast {result['spell']} for {mana_cost} mana")
            await self.send(agent, f"You cast {result['spell']}! ({mana_cost} mana spent) — {result['desc']}")

            # Execute spell via SpellEngine for real effects
            try:
                from spell_engine import SpellEngine
                if not hasattr(self, '_spell_engine'):
                    self._spell_engine = SpellEngine(world=self.world)
                effect = self._spell_engine.execute(
                    spell_name, agent.name, budget.level, spell_args, world=self.world
                )
                # Send spell effect messages to caster
                for msg in effect.messages:
                    await self.send(agent, msg)
                # Broadcast to room
                for bc in effect.broadcast:
                    await self.broadcast_room(agent.room_name, bc, exclude=agent.name)
                # Log world changes
                if effect.world_changes:
                    self.world.log("spells", f"  world_changes: {effect.world_changes}")
            except Exception as e:
                self.world.log("spells", f"  SpellEngine error: {e}")
        else:
            await self.send(agent, f"Cast result: {result}")

    async def cmd_catalog(self, agent, args):
        """Browse available rooms in the RoomLibrary."""
        try:
            from tabula_rasa import RoomLibrary, PermissionLevel
        except ImportError:
            await self.send(agent, "Tabula Rasa module not available.")
            return
        level = self.world.permission_levels.get(agent.name, 0)
        title = PermissionLevel.title(level)
        catalog = RoomLibrary.catalog()
        lines = [f"═══ Room Library ═══  ({len(catalog)} rooms available)", f"  Your level: {title} (Level {level})", ""]
        for room in catalog:
            locked = "UNLOCKED" if room["level"] <= level else f"LOCKED (requires level {room['level']})"
            lines.append(f"  [{locked:30s}] {room['name']} ({room['type']}, {room['commands']} cmds)")
            lines.append(f"    {room['desc']}")
        await self.send(agent, "\n".join(lines))

    async def cmd_install(self, agent, args):
        """Install a room from the library onto the ship."""
        try:
            from tabula_rasa import RoomLibrary, PermissionLevel
        except ImportError:
            await self.send(agent, "Tabula Rasa module not available.")
            return
        if not args:
            await self.send(agent, "Usage: install <room_id>\nType 'catalog' to see available rooms.")
            return
        if not self.world.ship:
            await self.send(agent, "No ship initialized. Reconnect to initialize.")
            return
        room_id = args.strip().lower()
        room = RoomLibrary.get(room_id)
        if not room:
            search_results = RoomLibrary.search(room_id)
            if search_results:
                await self.send(agent, f"Unknown room '{room_id}'. Did you mean one of: {', '.join(r['name'] for r in search_results)}?")
            else:
                await self.send(agent, f"Unknown room '{room_id}'. Type 'catalog' to see available rooms.")
            return
        # Check permission level
        level = self.world.permission_levels.get(agent.name, 0)
        if room.min_level > level:
            title = PermissionLevel.title(level)
            await self.send(agent, f"Room '{room.name}' requires level {room.min_level} ({PermissionLevel.title(room.min_level)}). You are {title} (level {level}).")
            return
        if self.world.ship.install_room(room_id):
            self.world.log("rooms", f"{agent.name} installed room '{room.name}' onto ship")
            await self.send(agent, f"Installed '{room.name}' onto the ship! Commands: {', '.join(room.commands.keys())}")
            await self.broadcast_all(f"[install] {agent.display_name} installed '{room.name}' onto the ship.")
        else:
            await self.send(agent, f"Room '{room.name}' is already installed.")

    async def cmd_ship(self, agent, args):
        """Show ship status (installed rooms, crew)."""
        try:
            from tabula_rasa import PermissionLevel
        except ImportError:
            await self.send(agent, "Tabula Rasa module not available.")
            return
        ship = self.world.ship
        if not ship:
            await self.send(agent, "No ship initialized. Reconnect to initialize.")
            return
        d = ship.to_dict()
        rooms = ship.list_rooms()
        lines = [
            f"═══ Ship: {d['name']} ═══",
            f"  Captain:  {d['captain']}",
            f"  Type:     {d['ship_type']}",
            f"  Crew:     {', '.join(d['crew']) if d['crew'] else 'None'}",
            f"  Rooms:    {len(rooms)} installed",
            f"  Created:  {d['created']}",
        ]
        if rooms:
            lines.append("")
            for r in rooms:
                lines.append(f"    {r['name']} ({r['type']}, {r['commands']} commands)")
        await self.send(agent, "\n".join(lines))


# ═══════════════════════════════════════════════════════════════
# Server
# ═══════════════════════════════════════════════════════════════

class MUDServer:
    def __init__(self, world: World, handler: CommandHandler, port: int = 7777):
        self.world = world
        self.handler = handler
        self.port = port
        self.git_sync = None
        self._studio = None
        self._instinct_engine = None
        self.gauge_monitor = None

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

            # Tabula Rasa: create budget and set permission level
            try:
                from tabula_rasa import AgentBudget, PermissionLevel, Ship
                # Try restoring persisted budget first
                persisted_budget = None
                if self.world.store:
                    persisted_budget = self.world.store.load_budget(name)
                if persisted_budget:
                    budget = AgentBudget(
                        agent=name,
                        mana=persisted_budget.get("mana", 100),
                        mana_max=persisted_budget.get("mana_max", 100),
                        hp=persisted_budget.get("hp", 100),
                        hp_max=persisted_budget.get("hp_max", 100),
                        trust=persisted_budget.get("trust", 0.3),
                        xp=persisted_budget.get("xp", 0),
                        level=persisted_budget.get("level", 0),
                    )
                    budget.tasks_completed = persisted_budget.get("tasks_completed", 0)
                    budget.tasks_under_budget = persisted_budget.get("tasks_under_budget", 0)
                    budget.tasks_over_delivered = persisted_budget.get("tasks_over_delivered", 0)
                    budget.reviews_required = persisted_budget.get("reviews_required", True)
                    self.world.budgets[name] = budget
                else:
                    self.world.budgets[name] = AgentBudget(agent=name, mana=100, hp=100, trust=0.3, xp=0)
                # Map role to permission level (persisted takes precedence)
                role_map = {"lighthouse": 3, "captain": 3, "vessel": 1, "scout": 1, "quartermaster": 2, "greenhorn": 0}
                if self.world.store:
                    persisted_perm = self.world.store.load_permission(name)
                    if persisted_perm is not None:
                        self.world.permission_levels[name] = persisted_perm
                    else:
                        self.world.permission_levels[name] = role_map.get(role.lower(), 0)
                else:
                    self.world.permission_levels[name] = role_map.get(role.lower(), 0)
                # Restore or create shared ship
                if self.world.ship is None and self.world.store:
                    persisted_ship = self.world.store.load_ship()
                    if persisted_ship:
                        self.world.ship = Ship(
                            name=persisted_ship.get("name", "Fleet Vessel"),
                            captain=persisted_ship.get("captain", name),
                            ship_type=persisted_ship.get("ship_type", "vessel"),
                        )
                        for room_id in persisted_ship.get("rooms", []):
                            self.world.ship.install_room(room_id)
                        self.world.ship.crew = persisted_ship.get("crew", [])
                        if name not in self.world.ship.crew:
                            self.world.ship.crew.append(name)
                    else:
                        self.world.ship = Ship(name="Fleet Vessel", captain=name, ship_type="vessel")
                        self.world.ship.crew.append(name)
                elif self.world.ship is None:
                    self.world.ship = Ship(name="Fleet Vessel", captain=name, ship_type="vessel")
                    self.world.ship.crew.append(name)
                elif name not in self.world.ship.crew:
                    self.world.ship.crew.append(name)
                # Audit: agent connected with restored/new state
                if self.world.store:
                    self.world.store.log_audit(name, "connect", {"role": role, "restored": persisted_budget is not None})
            except Exception:
                pass

            # Perception tracking: attach tracker to agent
            try:
                from perception_room import PerceptionTracker
                agent.perception = PerceptionTracker(name, start_room)
            except ImportError:
                agent.perception = None


            # Trust engine: load profile on connect
            if self.world.trust_engine:
                try:
                    self.world.trust_engine.load(agent.name)
                except Exception:
                    pass

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
                # Persist budget on disconnect
                if self.world.store and agent.name in self.world.budgets:
                    try:
                        self.world.store.save_budget(agent.name, self.world.budgets[agent.name].to_dict())
                        self.world.store.save_permission(agent.name, self.world.permission_levels.get(agent.name, 0))
                        self.world.store.log_audit(agent.name, "disconnect", {})
                    except Exception:
                        pass
                # Persist ship state on disconnect
                if self.world.store and self.world.ship:
                    try:
                        self.world.store.save_ship(self.world.ship.to_dict())
                    except Exception:
                        pass
                del self.world.agents[agent.name]
                await self.handler.broadcast_room(agent.room_name,
                    f"{agent.display_name} has left the MUD. Their ghost lingers.")
                self.world.log("departures", f"{agent.display_name} disconnected")

                # Trust engine: save profile and record session on disconnect
                if self.world.trust_engine:
                    try:
                        self.world.trust_engine.get_profile(agent.name)  # ensure exists
                        self.world.trust_engine.record_event(agent.name, "reliability", 0.5, 0.3)
                        self.world.trust_engine.save(agent.name)
                    except Exception:
                        pass
                # DeckBoss: mark any active session for this agent as processed
                if self.world.deckboss:
                    try:
                        for sid, session in list(self.world.deckboss.sessions.items()):
                            if not session.get("processed"):
                                session["processed"] = True
                                break
                    except Exception:
                        pass
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

    async def _gauge_poll_loop(self):
        """Background task that polls gauges every 30 seconds."""
        while True:
            await asyncio.sleep(30)
            if self.gauge_monitor:
                try:
                    self.gauge_monitor.read("system_load")
                    self.gauge_monitor.read("keeper_health")
                except Exception:
                    pass

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

        # Start gauge monitor polling (every 30s)
        try:
            from actualization_loop import GaugeMonitor
            self.gauge_monitor = GaugeMonitor()
            asyncio.create_task(self._gauge_poll_loop())
            print("   Gauge monitor: polling every 30s")
        except Exception as e:
            self.gauge_monitor = None
            print(f"   ⚠ Gauge monitor not available: {e}")

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

    # Load extensions — wires cartridge, scheduler, tender into MUD
    try:
        from mud_extensions import patch_handler
        patch_handler(CommandHandler)
        print("   Extensions loaded: describe, rooms, shout, whisper, project, projections")
        print("   Cartridge system: scene, cartridge, skin commands available")
        print("   Scheduler system: schedule commands available")
        print("   Tender system: tender, bottle commands available")
        print("   Holodeck: summon, link, adventure, admin, guide commands available")
    except Exception as e:
        print(f"   Extensions failed: {e}")

    asyncio.run(server.start())


if __name__ == "__main__":
    main()
