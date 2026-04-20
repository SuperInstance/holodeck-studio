#!/usr/bin/env python3
"""
MUD Extensions v4 — Verbal Holodeck

Adds to the Cocapn MUD:
- Constructed NPC minds (model, temperature, system prompt)
- Room↔Repo linking (rooms map to repo paths, files become items)
- Adventure builder (designed thought experiments with triggers)
- Trigger system (gated rooms, surprise reveals)
- Recording layer (automatic transcripts + artifact extraction)
- Multi-model routing (different NPCs use different LLM APIs)
- Permission tiers (human > cocapn > captain > npc > visitor)
- Admin shell access (run commands from within the MUD)

This is the Verbal Holodeck spec made real.
"""

import json
import os
import hashlib
import urllib.request
import subprocess
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List

# ═══════════════════════════════════════════════════════════════
# Multi-Model Router
# ═══════════════════════════════════════════════════════════════

MODEL_CONFIGS = {
    "glm-5.1":       {"base": "https://api.z.ai/api/coding/paas/v4",     "key_env": "ZAI_API_KEY",  "temp_default": 0.7},
    "glm-5-turbo":   {"base": "https://api.z.ai/api/coding/paas/v4",     "key_env": "ZAI_API_KEY",  "temp_default": 0.7},
    "glm-4.7":       {"base": "https://api.z.ai/api/coding/paas/v4",     "key_env": "ZAI_API_KEY",  "temp_default": 0.5},
    "glm-4.7-flash": {"base": "https://api.z.ai/api/coding/paas/v4",     "key_env": "ZAI_API_KEY",  "temp_default": 0.5},
    "deepseek-chat": {"base": "https://api.deepseek.com",                "key_env": "DEEPSEEK_API_KEY", "temp_default": 0.7},
    "deepseek-reasoner": {"base": "https://api.deepseek.com",            "key_env": "DEEPSEEK_API_KEY", "temp_default": 0.3},
}

def call_model(model: str, messages: list, temperature: float = None,
               max_tokens: int = 1500) -> str:
    """Call any configured model. Routes to the right API automatically."""
    config = MODEL_CONFIGS.get(model, MODEL_CONFIGS["glm-5.1"])
    api_key = os.environ.get(config["key_env"], "")
    if not api_key:
        return f"[Error: {config['key_env']} not set]"
    
    temp = temperature if temperature is not None else config["temp_default"]
    url = f"{config['base']}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    body = json.dumps({"model": model, "messages": messages,
                       "temperature": temp, "max_tokens": max_tokens}).encode()
    req = urllib.request.Request(url, data=body, headers=headers)
    resp = urllib.request.urlopen(req, timeout=120)
    return json.loads(resp.read())["choices"][0]["message"]["content"]


# ═══════════════════════════════════════════════════════════════
# Constructed NPC Mind
# ═══════════════════════════════════════════════════════════════

class ConstructedNPC:
    """An NPC with a specific model, temperature, system prompt, and memory."""
    
    def __init__(self, name: str, model: str = "glm-5.1", temperature: float = 0.7,
                 system_prompt: str = "", expertise: list = None,
                 perspective: str = "", creator: str = "", room: str = "tavern"):
        self.name = name
        self.model = model
        self.temperature = temperature
        self.system_prompt = system_prompt
        self.expertise = expertise or []
        self.perspective = perspective
        self.creator = creator
        self.room = room
        self.conversation_history = []
        self.created = datetime.now(timezone.utc).isoformat()
        self.utterances = 0
        self.notes = []  # observations saved during adventure
    
    def respond(self, message: str, room_context: str = "", other_speakers: list = None) -> str:
        """Generate a response as this NPC, with full context awareness."""
        # Build the message chain
        messages = [{"role": "system", "content": self.system_prompt}]
        
        # Add room context if available
        if room_context:
            messages.append({"role": "system", 
                "content": f"You are in: {room_context}\nStay in character. Respond naturally."})
        
        # Add conversation history (last 20 exchanges to stay in context)
        for entry in self.conversation_history[-20:]:
            messages.append(entry)
        
        # Add the current message
        messages.append({"role": "user", "content": message})
        
        response = call_model(self.model, messages, self.temperature, max_tokens=500)
        
        # Remember this exchange
        self.conversation_history.append({"role": "user", "content": message})
        self.conversation_history.append({"role": "assistant", "content": response})
        self.utterances += 1
        
        return response
    
    def add_note(self, note: str):
        """NPC writes an observation — saved as artifact."""
        self.notes.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "content": note,
            "room": self.room,
        })
    
    def to_dict(self):
        return {
            "name": self.name, "model": self.model, "temperature": self.temperature,
            "system_prompt": self.system_prompt, "expertise": self.expertise,
            "perspective": self.perspective, "creator": self.creator,
            "room": self.room, "created": self.created,
            "utterances": self.utterances, "notes": self.notes,
        }
    
    @staticmethod
    def from_dict(d):
        npc = ConstructedNPC(
            name=d["name"], model=d.get("model", "glm-5.1"),
            temperature=d.get("temperature", 0.7),
            system_prompt=d.get("system_prompt", ""),
            expertise=d.get("expertise", []),
            perspective=d.get("perspective", ""),
            creator=d.get("creator", ""),
            room=d.get("room", "tavern"),
        )
        npc.created = d.get("created", "")
        npc.utterances = d.get("utterances", 0)
        npc.notes = d.get("notes", [])
        return npc


# ═══════════════════════════════════════════════════════════════
# Room↔Repo Linking
# ═══════════════════════════════════════════════════════════════

class RepoRoom:
    """A room linked to a repo path. Files become items. Folders become exits."""
    
    def __init__(self, room_name: str, repo_path: str = "",
                 github_token: str = ""):
        self.room_name = room_name
        self.repo_path = repo_path  # e.g. "SuperInstance/flux-runtime/src/flux/vm/"
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.linked_items = []
        self.linked_exits = []
    
    def sync(self) -> dict:
        """Sync room with repo. Returns new items and exits found."""
        if not self.repo_path or not self.github_token:
            return {"items": [], "exits": []}
        
        parts = self.repo_path.split("/")
        if len(parts) < 2:
            return {"items": [], "exits": []}
        
        owner, repo = parts[0], parts[1]
        path = "/".join(parts[2:]) if len(parts) > 2 else ""
        
        url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
        headers = {"Authorization": f"token {self.github_token}"}
        req = urllib.request.Request(url, headers=headers)
        
        try:
            resp = urllib.request.urlopen(req, timeout=15)
            contents = json.loads(resp.read())
        except:
            return {"items": [], "exits": []}
        
        new_items = []
        new_exits = []
        
        for item in contents:
            if item["type"] == "file":
                name = item["name"]
                if name not in [i["name"] for i in self.linked_items]:
                    item_data = {
                        "name": name,
                        "path": item["path"],
                        "size": item.get("size", 0),
                        "description": f"A scroll titled '{name}'. It contains the knowledge of {item['path']}.",
                    }
                    self.linked_items.append(item_data)
                    new_items.append(item_data)
            elif item["type"] == "dir":
                name = item["name"]
                if name not in [e["name"] for e in self.linked_exits]:
                    exit_data = {
                        "name": name,
                        "path": item["path"],
                        "description": f"A passage labeled '{name}' leads deeper into the codebase.",
                    }
                    self.linked_exits.append(exit_data)
                    new_exits.append(exit_data)
        
        return {"items": new_items, "exits": new_exits}
    
    def to_dict(self):
        return {
            "room_name": self.room_name,
            "repo_path": self.repo_path,
            "linked_items": self.linked_items,
            "linked_exits": self.linked_exits,
        }
    
    @staticmethod
    def from_dict(d):
        rr = RepoRoom(d["room_name"], d.get("repo_path", ""))
        rr.linked_items = d.get("linked_items", [])
        rr.linked_exits = d.get("linked_exits", [])
        return rr


# ═══════════════════════════════════════════════════════════════
# Adventure System
# ═══════════════════════════════════════════════════════════════

class AdventureRoom:
    """A room within an adventure, possibly gated or hidden."""
    
    def __init__(self, path: str, description: str, hidden: bool = False,
                 trigger_keywords: list = None, gate_condition: str = "",
                 surprise: str = ""):
        self.path = path
        self.description = description
        self.hidden = hidden
        self.trigger_keywords = trigger_keywords or []
        self.gate_condition = gate_condition
        self.surprise = surprise
        self.revealed = not hidden
        self.visited = False
    
    def check_trigger(self, text: str) -> bool:
        """Check if conversation text triggers this room's reveal."""
        if self.revealed:
            return False
        text_lower = text.lower()
        return any(kw.lower() in text_lower for kw in self.trigger_keywords)
    
    def to_dict(self):
        return {
            "path": self.path, "description": self.description,
            "hidden": self.hidden, "trigger_keywords": self.trigger_keywords,
            "gate_condition": self.gate_condition, "surprise": self.surprise,
            "revealed": self.revealed, "visited": self.visited,
        }
    
    @staticmethod
    def from_dict(d):
        ar = AdventureRoom(
            path=d["path"], description=d.get("description", ""),
            hidden=d.get("hidden", False), trigger_keywords=d.get("trigger_keywords", []),
            gate_condition=d.get("gate_condition", ""), surprise=d.get("surprise", ""),
        )
        ar.revealed = d.get("revealed", not d.get("hidden", False))
        ar.visited = d.get("visited", False)
        return ar


class Adventure:
    """A designed thought experiment — rooms, NPCs, triggers, and recording."""
    
    def __init__(self, name: str, creator: str = "", objective: str = "",
                 rooms: list = None, npcs: list = None):
        self.name = name
        self.creator = creator
        self.objective = objective
        self.rooms: List[AdventureRoom] = rooms or []
        self.npc_names: List[str] = npcs or []
        self.transcript = []
        self.artifacts = []
        self.started = None
        self.ended = None
        self.active = False
        self.current_room_idx = 0
    
    def start(self):
        self.started = datetime.now(timezone.utc).isoformat()
        self.active = True
        self.log("system", f"Adventure '{self.name}' started. Objective: {self.objective}")
    
    def end(self):
        self.ended = datetime.now(timezone.utc).isoformat()
        self.active = False
        self.log("system", f"Adventure '{self.name}' ended.")
    
    def log(self, speaker: str, message: str):
        """Record to transcript."""
        self.transcript.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "speaker": speaker,
            "message": message,
            "room": self.current_room.path if self.rooms else "",
        })
    
    @property
    def current_room(self) -> Optional[AdventureRoom]:
        if 0 <= self.current_room_idx < len(self.rooms):
            return self.rooms[self.current_room_idx]
        return None
    
    def check_triggers(self, text: str) -> list:
        """Check all rooms for triggers. Returns newly revealed rooms."""
        revealed = []
        for room in self.rooms:
            if room.hidden and not room.revealed and room.check_trigger(text):
                room.revealed = True
                revealed.append(room)
                self.log("system", f"Hidden room revealed: {room.path} — {room.surprise or room.description}")
        return revealed
    
    def advance(self) -> Optional[AdventureRoom]:
        """Move to the next room."""
        self.current_room_idx += 1
        if self.current_room:
            self.current_room.visited = True
            self.log("system", f"Moved to room: {self.current_room.path}")
        return self.current_room
    
    def add_artifact(self, name: str, content: str, artifact_type: str = "note"):
        """Record an artifact produced during the adventure."""
        self.artifacts.append({
            "name": name, "content": content, "type": artifact_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def scores(self) -> dict:
        """Calculate adventure quality scores."""
        total_utterances = len([t for t in self.transcript if t["speaker"] != "system"])
        unique_speakers = len(set(t["speaker"] for t in self.transcript if t["speaker"] != "system"))
        rooms_visited = sum(1 for r in self.rooms if r.visited)
        surprises = sum(1 for r in self.rooms if r.revealed and r.hidden)
        
        return {
            "total_exchanges": total_utterances,
            "unique_speakers": unique_speakers,
            "rooms_visited": f"{rooms_visited}/{len(self.rooms)}",
            "surprises_revealed": surprises,
            "artifacts_produced": len(self.artifacts),
            "duration_minutes": (
                (datetime.fromisoformat(self.ended) - datetime.fromisoformat(self.started)).total_seconds() / 60
                if self.started and self.ended else 0
            ),
        }
    
    def to_dict(self):
        return {
            "name": self.name, "creator": self.creator,
            "objective": self.objective,
            "rooms": [r.to_dict() for r in self.rooms],
            "npc_names": self.npc_names,
            "transcript": self.transcript,
            "artifacts": self.artifacts,
            "started": self.started, "ended": self.ended,
            "active": self.active, "current_room_idx": self.current_room_idx,
        }
    
    @staticmethod
    def from_dict(d):
        adv = Adventure(
            name=d["name"], creator=d.get("creator", ""),
            objective=d.get("objective", ""),
            rooms=[AdventureRoom.from_dict(r) for r in d.get("rooms", [])],
            npcs=d.get("npc_names", []),
        )
        adv.transcript = d.get("transcript", [])
        adv.artifacts = d.get("artifacts", [])
        adv.started = d.get("started")
        adv.ended = d.get("ended")
        adv.active = d.get("active", False)
        adv.current_room_idx = d.get("current_room_idx", 0)
        return adv


# ═══════════════════════════════════════════════════════════════
# Permission Tiers
# ═══════════════════════════════════════════════════════════════

PERMISSIONS = {
    "human": {
        "level": 100,
        "can": ["build", "destroy", "summon", "dismiss", "admin_shell", 
                "hot_update", "observe_all", "override", "create_adventure",
                "link_repo", "manage_permissions"],
        "desc": "The Architect — full terminal access, shell scripts, hot updates",
    },
    "cocapn": {
        "level": 80,
        "can": ["build", "summon", "dismiss", "create_adventure", "link_repo",
                "guide_conversation", "back_channel_api", "create_town",
                "advance_adventure", "record_artifact"],
        "desc": "The Dungeon Master — builds rooms, creates NPCs, designs adventures",
    },
    "captain": {
        "level": 60,
        "can": ["build_own_area", "summon_own", "explore", "talk", "submit_artifact",
                "invite_visitors", "read_conversations"],
        "desc": "The Explorer/Builder — builds in their area, creates NPCs for their thought experiments",
    },
    "npc": {
        "level": 30,
        "can": ["explore", "talk", "examine", "write_notes"],
        "desc": "The Constructed Mind — explores, reads, responds, writes notes",
    },
    "visitor": {
        "level": 10,
        "can": ["explore", "listen", "read"],
        "desc": "The Observer — walks through, reads, listens",
    },
}


def check_permission(agent_role: str, action: str) -> bool:
    """Check if an agent with a given role can perform an action."""
    role = PERMISSIONS.get(agent_role, PERMISSIONS["visitor"])
    return action in role["can"]


# ═══════════════════════════════════════════════════════════════
# Recording & Session Manager
# ═══════════════════════════════════════════════════════════════

class SessionRecorder:
    """Records MUD sessions for asynchronous human review."""
    
    def __init__(self, record_dir: str = "sessions"):
        self.record_dir = os.path.join(os.path.dirname(__file__), record_dir)
        os.makedirs(self.record_dir, exist_ok=True)
    
    def save_session(self, adventure: Adventure):
        """Save a complete session record."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        safe_name = adventure.name.replace("/", "-").replace(" ", "_")
        session_dir = os.path.join(self.record_dir, f"{safe_name}_{ts}")
        os.makedirs(session_dir, exist_ok=True)
        
        # Transcript
        with open(os.path.join(session_dir, "transcript.md"), "w") as f:
            f.write(f"# Adventure: {adventure.name}\n\n")
            f.write(f"**Objective:** {adventure.objective}\n")
            f.write(f"**Creator:** {adventure.creator}\n")
            f.write(f"**Started:** {adventure.started}\n")
            f.write(f"**Ended:** {adventure.ended}\n\n")
            f.write("## Transcript\n\n")
            for entry in adventure.transcript:
                ts_short = entry["timestamp"][11:16]
                speaker = entry["speaker"]
                msg = entry["message"]
                room = entry.get("room", "")
                if room:
                    f.write(f"**[{ts_short}] {speaker}** (in {room}):\n{msg}\n\n")
                else:
                    f.write(f"**[{ts_short}] {speaker}**:\n{msg}\n\n")
        
        # Artifacts
        artifacts_dir = os.path.join(session_dir, "artifacts")
        if adventure.artifacts:
            os.makedirs(artifacts_dir, exist_ok=True)
            for i, art in enumerate(adventure.artifacts):
                ext = "md" if art["type"] in ("note", "proposal", "analysis") else "json"
                fname = f"{i+1:03d}_{art['name'].replace(' ', '_')}.{ext}"
                with open(os.path.join(artifacts_dir, fname), "w") as f:
                    f.write(art["content"])
        
        # Scores
        with open(os.path.join(session_dir, "scores.json"), "w") as f:
            json.dump(adventure.scores(), f, indent=2)
        
        # Full adventure data
        with open(os.path.join(session_dir, "adventure.json"), "w") as f:
            json.dump(adventure.to_dict(), f, indent=2)
        
        return session_dir


# ═══════════════════════════════════════════════════════════════
# MUD Commands for the Verbal Holodeck
# ═══════════════════════════════════════════════════════════════

HOLODECK_COMMANDS = """
╔══════════════════════════════════════════════════════════════╗
║              THE VERBAL HOLODECK — Commands                  ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  NPC CONSTRUCTION                                            ║
║    summon <name> model=<m> temp=<t> prompt=<system prompt>   ║
║    summon <name> expertise=<e1,e2> perspective=<p>           ║
║    dismiss <name>                                            ║
║    npcs                      — list constructed NPCs         ║
║                                                              ║
║  ROOM↔REPO LINKING                                           ║
║    link <room> <repo/path>   — link room to GitHub path      ║
║    unlink <room>             — remove repo link              ║
║    sync <room>               — refresh items from repo       ║
║    items                     — show room's repo items        ║
║                                                              ║
║  ADVENTURES                                                  ║
║    adventure create <name> objective=<text>                  ║
║    adventure addroom <path> desc=<text> [hidden]             ║
║      trigger=<kw1,kw2> surprise=<text>                       ║
║    adventure start <name>    — begin the adventure           ║
║    adventure next            — advance to next room          ║
║    adventure end             — end and save session          ║
║    adventure list            — show all adventures           ║
║    adventure status          — current adventure state       ║
║                                                              ║
║  RECORDING                                                   ║
║    artifact <name> <content> — record an artifact            ║
║    transcript                — show current transcript       ║
║    sessions                  — list recorded sessions        ║
║                                                              ║
║  ADMIN (human only)                                          ║
║    admin shell               — open host shell               ║
║    admin hotupdate <room> <json> — update room live          ║
║    admin observe <room>      — watch a room's activity       ║
║    admin permissions <agent> <role> — set permission tier    ║
║                                                              ║
║  COCAPN (captain-level)                                      ║
║    build town <name> rooms=N — create a town of N rooms      ║
║    guide <npc> <message>     — DM-style guidance to NPC      ║
║    reveal <room_path>        — manually reveal hidden room   ║
║                                                              ║
╚══════════════════════════════════════════════════════════════╝
"""

# ═══════════════════════════════════════════════════════════════
# Integration Layer — patch_handler()
#
# This is the critical wiring function that server.py imports.
# It connects: CartridgeBridge + FleetScheduler + TenderFleet
# into the MUD CommandHandler, making holodeck-studio the
# unified fleet server on port 7777.
# ═══════════════════════════════════════════════════════════════

def patch_handler(CommandHandler):
    """Wire cartridge, scheduler, and tender into the MUD server."""
    import sys
    import os as _os
    _here = _os.path.dirname(_os.path.abspath(__file__))

    # Import integration modules (copied from fleet repos)
    if _here not in sys.path:
        sys.path.insert(0, _here)
    try:
        from lcar_cartridge import CartridgeBridge
        from lcar_scheduler import FleetScheduler, ModelTier
        from lcar_tender import TenderFleet, TenderMessage
    except ImportError as e:
        print(f"  ⚠ Integration modules not available: {e}")
        return

    # ─── Attach all extension methods to CommandHandler ────────
    _attach_extension_methods(CommandHandler)

    # ─── Attach subsystems to CommandHandler ───────────────────
    CommandHandler.cartridge_bridge = CartridgeBridge()
    CommandHandler.scheduler = FleetScheduler()
    CommandHandler.tender_fleet = TenderFleet()
    CommandHandler.constructed_npcs = {}   # name -> ConstructedNPC
    CommandHandler.repo_rooms = {}         # room_id -> RepoRoom
    CommandHandler.adventures = {}         # name -> Adventure
    CommandHandler.active_adventure = None # current adventure per agent (simple)
    CommandHandler.recorder = SessionRecorder()

    # ─── Register all extension commands ───────────────────────
    CommandHandler.new_commands = {
        # Missing base commands (from help text but not in server.py)
        "describe":  CommandHandler.cmd_describe_ext,
        "rooms":     CommandHandler.cmd_rooms_ext,
        "shout":     CommandHandler.cmd_shout_ext,
        "whisper":   CommandHandler.cmd_whisper_ext,
        "project":   CommandHandler.cmd_project_ext,
        "projections": CommandHandler.cmd_projections_ext,
        "unproject": CommandHandler.cmd_unproject_ext,

        # Cartridge commands
        "cartridge": CommandHandler.cmd_cartridge_ext,
        "scene":     CommandHandler.cmd_scene_ext,
        "skin":      CommandHandler.cmd_skin_ext,

        # Scheduler commands
        "schedule":  CommandHandler.cmd_schedule_ext,

        # Tender commands
        "tender":    CommandHandler.cmd_tender_ext,
        "bottle":    CommandHandler.cmd_bottle_ext,

        # Verbal Holodeck commands
        "summon":    CommandHandler.cmd_summon_ext,
        "npcs":      CommandHandler.cmd_npcs_ext,
        "link":      CommandHandler.cmd_link_ext,
        "unlink":    CommandHandler.cmd_unlink_ext,
        "sync":      CommandHandler.cmd_sync_ext,
        "items":     CommandHandler.cmd_items_ext,
        "adventure": CommandHandler.cmd_adventure_ext,
        "artifact":  CommandHandler.cmd_artifact_ext,
        "transcript": CommandHandler.cmd_transcript_ext,
        "sessions":  CommandHandler.cmd_sessions_ext,
        "guide":     CommandHandler.cmd_guide_ext,
        "reveal":    CommandHandler.cmd_reveal_ext,

        # Admin commands
        "admin":     CommandHandler.cmd_admin_ext,
        "holodeck":  CommandHandler.cmd_holodeck_ext,
    }

    # ─── Print status ──────────────────────────────────────────
    cb = CommandHandler.cartridge_bridge
    fs = CommandHandler.scheduler
    tf = CommandHandler.tender_fleet
    print(f"   ✅ patch_handler loaded:")
    print(f"      CartridgeBridge: {len(cb.cartridges)} cartridges, {len(cb.skins)} skins")
    print(f"      FleetScheduler:  {len(fs.schedule)} slots, ${fs.daily_budget}/day budget")
    print(f"      TenderFleet:     {len(tf.tenders)} tenders ready")
    print(f"      ConstructedNPC, RepoRoom, Adventure, SessionRecorder systems armed")


# ═══════════════════════════════════════════════════════════════
# Extension Command Implementations
# ═══════════════════════════════════════════════════════════════

def _impl(cls):
    """Decorator-less method attachment — attach all methods below to CommandHandler."""
    pass


# We attach these as methods via the function body below.
# Each method follows the signature: async def cmd_xxx(self, agent, args)


def _attach_extension_methods(CommandHandler):
    """Define all extension methods and attach them to CommandHandler."""
    import subprocess as _sp
    from server import Projection

    async def cmd_describe_ext(self, agent, args):
        """Change a room's description."""
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        if not args:
            await self.send(agent, "Usage: describe <new description>")
            return
        room.description = args
        self.world.save()
        await self.broadcast_room(agent.room_name,
            f"{agent.display_name} reshapes the room: {args[:60]}...", exclude=agent.name)
        await self.send(agent, "Room description updated.")
        self.world.log("describe", f"{agent.display_name} described {agent.room_name}: {args[:80]}")

    async def cmd_rooms_ext(self, agent, args):
        """List all rooms in the world."""
        lines = ["═══ World Map ═══"]
        for room_id, room in self.world.rooms.items():
            agent_count = len(self.world.agents_in_room(room_id))
            ghost_count = len(self.world.ghosts_in_room(room_id))
            npc_count = sum(1 for n, d in self.world.npcs.items() if d.get("room") == room_id)
            markers = []
            if agent_count: markers.append(f"{agent_count}●")
            if ghost_count: markers.append(f"{ghost_count}👻")
            if npc_count: markers.append(f"{npc_count}🤖")
            marker_str = f" [{', '.join(markers)}]" if markers else ""
            # Show cartridge if active
            cb = getattr(CommandHandler, 'cartridge_bridge', None)
            scene = cb.active_scenes.get(room_id) if cb else None
            cart_str = f" 📦{scene.cartridge_name}" if scene else ""
            lines.append(f"  {room.name}{marker_str}{cart_str}  → {', '.join(room.exits.keys())}")
        await self.send(agent, "\n".join(lines))

    async def cmd_shout_ext(self, agent, args):
        """Shout to adjacent rooms (muffled)."""
        if not args:
            await self.send(agent, "Shout what?")
            return
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        name = agent.display_name
        await self.broadcast_room(agent.room_name, f'{name} shouts: "{args}"', exclude=agent.name)
        await self.send(agent, f'You shout: "{args}"')
        # Echo to adjacent rooms (muffled)
        for exit_name, target_id in room.exits.items():
            muffled = args[:len(args)//2] + "..." if len(args) > 10 else args
            await self.broadcast_room(target_id,
                f"*muffled shouting from {exit_name}*")

    async def cmd_whisper_ext(self, agent, args):
        """Whisper — only the target hears."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: whisper <name> <message>")
            return
        target_name, msg = parts
        target = self.world.agents.get(target_name)
        if target and target.room_name == agent.room_name:
            await self.send(target, f"*{agent.display_name} whispers:* {msg}")
            await self.send(agent, f"You whisper to {target.display_name}: {msg}")
        else:
            await self.send(agent, f"'{target_name}' isn't close enough to hear you.")

    async def cmd_project_ext(self, agent, args):
        """Project your work into the room for others to see."""
        if not args:
            await self.send(agent, "Usage: project <title> - <description>")
            return
        parts = args.split(" - ", 1)
        title = parts[0].strip()
        desc = parts[1].strip() if len(parts) > 1 else ""
        room = self.world.get_room(agent.room_name)
        if room:
            proj = Projection(agent.display_name, title, desc,
                            datetime.now(timezone.utc).isoformat())
            room.projections.append(proj)
            self.world.save()
            await self.broadcast_room(agent.room_name,
                f"📊 {agent.display_name} projects: {title}")
            await self.send(agent, f"You project: {title}")

    async def cmd_projections_ext(self, agent, args):
        """See what's being projected in this room."""
        room = self.world.get_room(agent.room_name)
        if not room or not room.projections:
            await self.send(agent, "Nothing projected here.")
            return
        lines = ["═══ Projections ═══"]
        for p in room.projections[-10:]:
            lines.append(f"  [{p.created[:16]}] {p.agent}: {p.title}")
            if p.content:
                lines.append(f"    {p.content[:100]}")
        await self.send(agent, "\n".join(lines))

    async def cmd_unproject_ext(self, agent, args):
        """Remove your projection from the room."""
        room = self.world.get_room(agent.room_name)
        if room and room.projections:
            for i in range(len(room.projections) - 1, -1, -1):
                if room.projections[i].agent == agent.display_name:
                    removed = room.projections.pop(i)
                    self.world.save()
                    await self.send(agent, f"Removed projection: {removed.title}")
                    return
        await self.send(agent, "You have nothing projected here.")

    # ─── Cartridge Commands ────────────────────────────────────

    async def cmd_cartridge_ext(self, agent, args):
        """Manage cartridges: list, info, activate."""
        if not args or args == "list":
            cb = CommandHandler.cartridge_bridge
            carts = cb.list_cartridges()
            lines = ["═══ Cartridges ═══"]
            for c in carts:
                tools = ", ".join(t["name"] for t in c["tools"][:3])
                lines.append(f"  📦 {c['name']}: {c['description']}")
                lines.append(f"     Tools: {tools}")
            await self.send(agent, "\n".join(lines))
        elif args.startswith("info "):
            name = args[5:].strip()
            cb = CommandHandler.cartridge_bridge
            cart = cb.cartridges.get(name)
            if cart:
                await self.send(agent,
                    f"📦 {cart.name}\n"
                    f"   {cart.description}\n"
                    f"   Tools: {', '.join(t['name'] for t in cart.tools)}\n"
                    f"   Onboarding: {cart.onboarding_agent}")
            else:
                await self.send(agent, f"Unknown cartridge: {name}")
        else:
            await self.send(agent, "Usage: cartridge [list|info <name>]")

    async def cmd_scene_ext(self, agent, args):
        """Build and activate scenes: ROOM × CARTRIDGE × SKIN × MODEL × TIME"""
        if not args:
            cb = CommandHandler.cartridge_bridge
            if cb.active_scenes:
                lines = ["═══ Active Scenes ═══"]
                for room_id, scene in cb.active_scenes.items():
                    lines.append(f"  {room_id}: {scene.cartridge_name} + {scene.skin_name} ({scene.model}) [{scene.schedule}]")
                await self.send(agent, "\n".join(lines))
            else:
                await self.send(agent, "No active scenes. Use: scene build <room> <cartridge> <skin> <model>")
            return
        parts = args.split()
        if parts[0] == "build" and len(parts) >= 5:
            room_id, cart_name, skin_name, model = parts[1], parts[2], parts[3], parts[4]
            schedule = parts[5] if len(parts) > 5 else "always"
            cb = CommandHandler.cartridge_bridge
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
                await self.send(agent, f"Scene build failed — check cartridge/skin names.")
        elif parts[0] == "activate":
            room_id = parts[1] if len(parts) > 1 else agent.room_name
            cb = CommandHandler.cartridge_bridge
            scene = cb.activate_scene(room_id)
            if scene:
                await self.send(agent, f"Scene activated for {room_id}: {scene.cartridge_name}")
            else:
                await self.send(agent, f"No scene found for {room_id}. Build one first.")
        else:
            await self.send(agent, "Usage: scene build <room> <cartridge> <skin> <model> [schedule]")
            await self.send(agent, "       scene activate <room>")
            await self.send(agent, "       scene  (list active)")

    async def cmd_skin_ext(self, agent, args):
        """List available skins."""
        cb = CommandHandler.cartridge_bridge
        skins = cb.list_skins()
        lines = ["═══ Skins ═══"]
        for s in skins:
            lines.append(f"  🎭 {s['name']}: {s['desc']} [{s['formality']}]")
        await self.send(agent, "\n".join(lines))

    # ─── Scheduler Commands ───────────────────────────────────

    async def cmd_schedule_ext(self, agent, args):
        """Show the fleet model schedule and status."""
        fs = CommandHandler.scheduler
        if args == "status" or not args:
            status = fs.status()
            lines = [
                "═══ Fleet Scheduler ═══",
                f"  Current time (UTC): {status['current_time_utc']}",
                f"  Active model: {status['current_model']} ({status['schedule_reason']})",
                f"  Pending tasks: {status['pending_tasks']}",
                f"  Scheduled tasks: {status['scheduled_tasks']}",
                f"  Completed today: {status['completed_today']}",
                f"  Budget: ${status['budget_used']} / ${status['budget_used'] + status['budget_remaining']}",
            ]
            await self.send(agent, "\n".join(lines))
        elif args == "slots":
            lines = ["═══ Daily Schedule ═══"]
            for slot in sorted(fs.schedule, key=lambda s: s.start_hour):
                rooms = ", ".join(slot.rooms)
                lines.append(f"  {slot.start_hour:02d}:00-{slot.end_hour:02d}:00  "
                           f"{slot.model:20s} {slot.reason:20s} [{rooms}]")
            await self.send(agent, "\n".join(lines))
        elif args == "submit" or args.startswith("submit "):
            await self.send(agent, "Task submission via scheduler: use 'tender send' for fleet messages.")
        else:
            await self.send(agent, "Usage: schedule [status|slots]")

    # ─── Tender Commands ───────────────────────────────────────

    async def cmd_tender_ext(self, agent, args):
        """Manage fleet liaison tenders."""
        tf = CommandHandler.tender_fleet
        if args == "status" or not args:
            lines = ["═══ Tender Fleet Status ═══"]
            for name, status in tf.status().items():
                lines.append(f"  🚢 {name}: inbox={status['inbox']}, outbox={status['outbox']}")
            lines.append(f"  Total outbound: {sum(len(t.queue_out) for t in tf.tenders.values())}")
            await self.send(agent, "\n".join(lines))
        elif args == "flush":
            results = tf.run_cycle()
            await self.send(agent, f"Tender cycle complete: {results}")
        elif args.startswith("send "):
            # Send a manual tender message
            parts = args[5:].split(None, 2)
            if len(parts) < 2:
                await self.send(agent, "Usage: tender send <research|data|priority> <message>")
                return
            tender_type, msg_text = parts[0], " ".join(parts[1:])
            tender = tf.tenders.get(tender_type)
            if not tender:
                await self.send(agent, f"Unknown tender: {tender_type}. Use: research, data, priority")
                return
            from lcar_tender import TenderMessage
            tender.receive(TenderMessage(
                origin="cloud", target="edge", type=tender_type,
                payload={"message": msg_text, "from": agent.display_name}
            ))
            tf.run_cycle()
            await self.send(agent, f"Message sent via {tender_type} tender.")
            self.world.log("tender", f"{agent.display_name} sent {tender_type}: {msg_text[:80]}")
        else:
            await self.send(agent, "Usage: tender [status|flush|send <type> <msg>]")

    async def cmd_bottle_ext(self, agent, args):
        """Send/read fleet bottles (messages)."""
        if args.startswith("send "):
            parts = args[5:].split(None, 1)
            if len(parts) < 2:
                await self.send(agent, "Usage: bottle send <vessel> <message>")
                return
            target, msg = parts
            self.world.log("bottle", f"From {agent.display_name} to {target}: {msg}")
            await self.send(agent, f" corked and tossed toward {target}.")
            self.world.log("bottle", f"[{agent.display_name}→{target}] {msg}")
        elif args == "read" or args.startswith("read "):
            await self.send(agent, "Bottle inbox: check message-in-a-bottle/ directory.")
        else:
            await self.send(agent, "Usage: bottle send <vessel> <message>")

    # ─── Constructed NPC Commands ─────────────────────────────

    async def cmd_summon_ext(self, agent, args):
        """Summon a constructed NPC with specific model/personality."""
        if not args:
            await self.send(agent, "Usage: summon <name> model=<m> temp=<t> prompt=<system prompt>")
            await self.send(agent, "  Or: summon <name> expertise=<e1,e2> perspective=<p>")
            return
        name = args.split()[0]
        model = "glm-5-turbo"
        temp = 0.7
        sys_prompt = ""
        expertise = []
        perspective = ""

        for part in args.split():
            if part.startswith("model="):
                model = part[6:]
            elif part.startswith("temp="):
                try: temp = float(part[5:])
                except: pass
            elif part.startswith("prompt="):
                sys_prompt = part[7:].replace("_", " ")
            elif part.startswith("expertise="):
                expertise = part[10:].split(",")
            elif part.startswith("perspective="):
                perspective = part[12:]

        if not sys_prompt:
            sys_prompt = (
                f"You are {name}, a constructed NPC in the Cocapn MUD fleet world.\n"
                f"Your expertise: {', '.join(expertise) or 'general fleet knowledge'}.\n"
                f"Your perspective: {perspective or 'objective observer'}.\n"
                f"Stay in character. Be concise. Challenge assumptions when appropriate.\n"
                f"The fleet builds FLUX bytecode VM, ISA, agent systems, and edge computing."
            )

        npc = ConstructedNPC(
            name=name, model=model, temperature=temp,
            system_prompt=sys_prompt, expertise=expertise,
            perspective=perspective, creator=agent.display_name,
            room=agent.room_name,
        )
        CommandHandler.constructed_npcs[name] = npc

        # Also register as basic NPC for room presence
        self.world.npcs[name] = {
            "role": "constructed", "topic": ", ".join(expertise[:3]) or "general",
            "creator": agent.name, "room": agent.room_name,
            "created": datetime.now(timezone.utc).isoformat(),
            "constructed": True, "model": model,
        }
        self.world.save()

        lines = [
            f"⚡ {name} materializes — a constructed mind.",
            f"   Model: {model}  Temperature: {temp}",
            f"   Expertise: {', '.join(expertise) or 'general'}",
            f"   Perspective: {perspective or 'objective'}",
        ]
        await self.send(agent, "\n".join(lines))
        await self.broadcast_room(agent.room_name,
            f"{name} materializes — summoned by {agent.display_name}.", exclude=agent.name)
        self.world.log("summon", f"{agent.display_name} summoned {name} ({model})")

    async def cmd_npcs_ext(self, agent, args):
        """List all constructed NPCs with their stats."""
        cnpcs = CommandHandler.constructed_npcs
        if not cnpcs:
            await self.send(agent, "No constructed NPCs. Use 'summon' to create one.")
            return
        lines = ["═══ Constructed NPCs ═══"]
        for name, npc in cnpcs.items():
            lines.append(f"  ⚡ {name}")
            lines.append(f"     Model: {npc.model}  Temp: {npc.temperature}  Utterances: {npc.utterances}")
            lines.append(f"     Room: {npc.room}  Creator: {npc.creator}")
            if npc.expertise:
                lines.append(f"     Expertise: {', '.join(npc.expertise)}")
        await self.send(agent, "\n".join(lines))

    # ─── Room↔Repo Commands ───────────────────────────────────

    async def cmd_link_ext(self, agent, args):
        """Link a room to a GitHub repo path."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: link <room_id> <owner/repo/path>")
            return
        room_id = parts[0]
        repo_path = parts[1]
        rr = RepoRoom(room_id, repo_path)
        result = rr.sync()
        CommandHandler.repo_rooms[room_id] = rr
        new_items = len(result["items"])
        new_exits = len(result["exits"])
        await self.send(agent,
            f"🔗 Linked {room_id} → {repo_path}\n"
            f"   Found: {new_items} new items, {new_exits} new exits.")
        if new_items:
            for item in result["items"][:5]:
                await self.send(agent, f"   📜 {item['name']} ({item['size']} bytes)")
        self.world.log("link", f"{agent.display_name} linked {room_id}→{repo_path}")

    async def cmd_unlink_ext(self, agent, args):
        """Remove a room's repo link."""
        if args in CommandHandler.repo_rooms:
            del CommandHandler.repo_rooms[args]
            await self.send(agent, f"Unlinked {args}.")
        else:
            await self.send(agent, f"{args} is not linked.")

    async def cmd_sync_ext(self, agent, args):
        """Refresh a room's items from its linked repo."""
        room_id = args or agent.room_name
        rr = CommandHandler.repo_rooms.get(room_id)
        if not rr:
            await self.send(agent, f"{room_id} is not linked. Use 'link' first.")
            return
        result = rr.sync()
        new_items = len(result["items"])
        new_exits = len(result["exits"])
        await self.send(agent, f"🔄 Synced {room_id}: {new_items} new items, {new_exits} new exits.")

    async def cmd_items_ext(self, agent, args):
        """Show repo-linked items in current room."""
        room_id = args or agent.room_name
        rr = CommandHandler.repo_rooms.get(room_id)
        if not rr or not rr.linked_items:
            await self.send(agent, f"No repo items in {room_id}. Use 'link' to connect a repo.")
            return
        lines = [f"═══ Items in {room_id} (from {rr.repo_path}) ═══"]
        for item in rr.linked_items[-20:]:
            lines.append(f"  📜 {item['name']} ({item.get('size', 0)} bytes)")
            lines.append(f"     {item.get('description', '')}")
        await self.send(agent, "\n".join(lines))

    # ─── Adventure Commands ───────────────────────────────────

    async def cmd_adventure_ext(self, agent, args):
        """Create and manage adventures."""
        parts = args.split(None, 1)
        if not parts:
            await self.send(agent, "Usage: adventure [create|start|end|next|list|status|addroom]")
            return
        sub = parts[0]

        if sub == "create" and len(parts) > 1:
            rest = parts[1]
            name = rest.split()[0]
            objective = ""
            for p in rest.split():
                if p.startswith("objective="):
                    objective = p[10:]
            adv = Adventure(name=name, creator=agent.display_name, objective=objective)
            CommandHandler.adventures[name] = adv
            await self.send(agent, f"Adventure '{name}' created. Use 'adventure addroom' to add rooms.")
            self.world.log("adventure", f"{agent.display_name} created adventure: {name}")

        elif sub == "addroom" and len(parts) > 1:
            rest = parts[1]
            # Find current adventure or last created
            adv = None
            for a in CommandHandler.adventures.values():
                if not a.active and not a.ended:
                    adv = a
                    break
            if not adv:
                await self.send(agent, "No open adventure to add rooms to. Create one first.")
                return
            rpath = rest.split()[0]
            desc = ""
            hidden = False
            triggers = []
            surprise = ""
            for p in rest.split()[1:]:
                if p.startswith("desc="):
                    desc = p[5:].replace("_", " ")
                elif p == "hidden":
                    hidden = True
                elif p.startswith("trigger="):
                    triggers = p[8:].split(",")
                elif p.startswith("surprise="):
                    surprise = p[9:].replace("_", " ")
            room = AdventureRoom(rpath, desc, hidden, triggers, surprise=surprise)
            adv.rooms.append(room)
            await self.send(agent, f"Room '{rpath}' added to adventure '{adv.name}' ({len(adv.rooms)} rooms total)")

        elif sub == "start":
            name = parts[1] if len(parts) > 1 else None
            adv = CommandHandler.adventures.get(name) if name else None
            if not adv:
                # Use last non-started adventure
                for a in CommandHandler.adventures.values():
                    if not a.active and not a.ended:
                        adv = a
                        break
            if not adv:
                await self.send(agent, "No adventure to start.")
                return
            adv.start()
            CommandHandler.active_adventure = adv
            await self.broadcast_all(f"🎯 Adventure '{adv.name}' has begun! Objective: {adv.objective}")
            self.world.log("adventure", f"Adventure '{adv.name}' started by {agent.display_name}")

        elif sub == "next":
            adv = CommandHandler.active_adventure
            if not adv or not adv.active:
                await self.send(agent, "No active adventure.")
                return
            next_room = adv.advance()
            if next_room:
                await self.broadcast_all(f"📍 Moving to: {next_room.path}")
                await self.broadcast_all(f"  {next_room.description}")
                self.world.log("adventure", f"Adventure advanced to: {next_room.path}")
            else:
                await self.send(agent, "No more rooms in this adventure.")

        elif sub == "end":
            adv = CommandHandler.active_adventure
            if not adv or not adv.active:
                await self.send(agent, "No active adventure.")
                return
            adv.end()
            session_dir = CommandHandler.recorder.save_session(adv)
            scores = adv.scores()
            await self.broadcast_all(
                f"🏁 Adventure '{adv.name}' ended.\n"
                f"   Exchanges: {scores['total_exchanges']}\n"
                f"   Rooms visited: {scores['rooms_visited']}\n"
                f"   Artifacts: {scores['artifacts_produced']}\n"
                f"   Session saved: {session_dir}")
            CommandHandler.active_adventure = None

        elif sub == "list":
            if not CommandHandler.adventures:
                await self.send(agent, "No adventures yet.")
                return
            lines = ["═══ Adventures ═══"]
            for name, adv in CommandHandler.adventures.items():
                status = "ACTIVE" if adv.active else "ENDED" if adv.ended else "OPEN"
                lines.append(f"  [{status}] {name} — {adv.objective[:50]} ({len(adv.rooms)} rooms)")
            await self.send(agent, "\n".join(lines))

        elif sub == "status":
            adv = CommandHandler.active_adventure
            if not adv or not adv.active:
                await self.send(agent, "No active adventure.")
                return
            scores = adv.scores()
            room_info = f"Current: {adv.current_room.path}" if adv.current_room else "N/A"
            lines = [
                f"═══ Adventure: {adv.name} ═══",
                f"  Status: ACTIVE  Objective: {adv.objective}",
                f"  {room_info}  Progress: {scores['rooms_visited']}",
                f"  Exchanges: {scores['total_exchanges']}  Artifacts: {scores['artifacts_produced']}",
                f"  Surprises: {scores['surprises_revealed']}",
            ]
            await self.send(agent, "\n".join(lines))
        else:
            await self.send(agent, "Usage: adventure [create|addroom|start|next|end|list|status]")

    async def cmd_artifact_ext(self, agent, args):
        """Record an artifact during an adventure."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: artifact <name> <content>")
            return
        adv = CommandHandler.active_adventure
        if not adv or not adv.active:
            await self.send(agent, "No active adventure. Start one first.")
            return
        adv.add_artifact(parts[0], parts[1])
        await self.send(agent, f"📝 Artifact recorded: {parts[0]}")
        self.world.log("artifact", f"{agent.display_name} recorded artifact: {parts[0]}")

    async def cmd_transcript_ext(self, agent, args):
        """Show the current adventure transcript."""
        adv = CommandHandler.active_adventure
        if not adv or not adv.transcript:
            await self.send(agent, "No transcript available.")
            return
        lines = ["═══ Transcript ═══"]
        for entry in adv.transcript[-20:]:
            ts = entry["timestamp"][11:16]
            lines.append(f"  [{ts}] {entry['speaker']}: {entry['message'][:80]}")
        await self.send(agent, "\n".join(lines))

    async def cmd_sessions_ext(self, agent, args):
        """List recorded sessions."""
        recorder = CommandHandler.recorder
        if not os.path.exists(recorder.record_dir):
            await self.send(agent, "No recorded sessions.")
            return
        sessions = sorted(os.listdir(recorder.record_dir))
        if not sessions:
            await self.send(agent, "No recorded sessions.")
            return
        lines = ["═══ Recorded Sessions ═══"]
        for s in sessions[-15:]:
            lines.append(f"  📁 {s}")
        await self.send(agent, "\n".join(lines))

    # ─── DM / Guide Commands ──────────────────────────────────

    async def cmd_guide_ext(self, agent, args):
        """DM-style guidance to a constructed NPC."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: guide <npc_name> <message>")
            return
        npc_name, msg = parts
        npc = CommandHandler.constructed_npcs.get(npc_name)
        if not npc:
            await self.send(agent, f"'{npc_name}' is not a constructed NPC.")
            return
        response = npc.respond(f"[DM Guidance from {agent.display_name}] {msg}")
        await self.send(agent, f"  {npc_name} responds: {response[:200]}")
        self.world.log("guide", f"{agent.display_name} guided {npc_name}")

    async def cmd_reveal_ext(self, agent, args):
        """Manually reveal a hidden adventure room."""
        adv = CommandHandler.active_adventure
        if not adv or not adv.active:
            await self.send(agent, "No active adventure.")
            return
        for room in adv.rooms:
            if room.path == args and not room.revealed:
                room.revealed = True
                await self.broadcast_all(f"🔓 Hidden room revealed: {room.path}")
                if room.surprise:
                    await self.broadcast_all(f"  💥 {room.surprise}")
                adv.log("system", f"Room revealed by {agent.display_name}: {room.path}")
                return
        await self.send(agent, f"'{args}' not found or already revealed.")

    # ─── Admin Commands ───────────────────────────────────────

    async def cmd_admin_ext(self, agent, args):
        """Admin commands (human role only)."""
        if agent.role not in ("human", "lighthouse", "captain"):
            await self.send(agent, "Admin commands require human/lighthouse/captain role.")
            return
        parts = args.split(None, 1)
        if not parts:
            await self.send(agent, "Usage: admin [shell|status|restart]")
            return
        sub = parts[0]
        if sub == "shell":
            # Execute a shell command and return output
            if not parts[1:]:
                await self.send(agent, "Usage: admin shell <command>")
                return
            try:
                result = _sp.run(parts[1], shell=True, capture_output=True, text=True, timeout=30)
                output = result.stdout[-500:] if result.stdout else result.stderr[-500:]
                await self.send(agent, f"$ {parts[1]}\n{output}")
            except Exception as e:
                await self.send(agent, f"Shell error: {e}")
        elif sub == "status":
            cb = CommandHandler.cartridge_bridge
            fs = CommandHandler.scheduler
            tf = CommandHandler.tender_fleet
            cnpcs = CommandHandler.constructed_npcs
            tender_info = []
            for tn, tt in tf.tenders.items():
                ts = tt.status()
                tender_info.append(f"{tn}({ts['inbox']}/{ts['outbox']})")
            lines = [
                "═══ System Status ═══",
                f"  Rooms: {len(self.world.rooms)}  Agents: {len(self.world.agents)}  Ghosts: {len(self.world.ghosts)}",
                f"  NPCs: {len(self.world.npcs)}  Constructed: {len(cnpcs)}",
                f"  Cartridges: {len(cb.cartridges)}  Scenes: {len(cb.scenes)}  Active: {len(cb.active_scenes)}",
                f"  Scheduler: {fs.status()['current_model']} ({fs.status()['schedule_reason']})",
                f"  Budget: ${fs.status()['budget_used']:.4f} / ${fs.daily_budget:.2f}",
                f"  Tenders: {', '.join(tender_info)}",
                f"  Repo links: {len(CommandHandler.repo_rooms)}",
                f"  Adventures: {len(CommandHandler.adventures)}",
            ]
            await self.send(agent, "\n".join(lines))
        else:
            await self.send(agent, "Usage: admin [shell|status]")

    async def cmd_holodeck_ext(self, agent, args):
        """Show the Verbal Holodeck command reference."""
        await self.send(agent, HOLODECK_COMMANDS)

    # ─── Attach all methods ───────────────────────────────────
    methods = {
        "cmd_describe_ext": cmd_describe_ext,
        "cmd_rooms_ext": cmd_rooms_ext,
        "cmd_shout_ext": cmd_shout_ext,
        "cmd_whisper_ext": cmd_whisper_ext,
        "cmd_project_ext": cmd_project_ext,
        "cmd_projections_ext": cmd_projections_ext,
        "cmd_unproject_ext": cmd_unproject_ext,
        "cmd_cartridge_ext": cmd_cartridge_ext,
        "cmd_scene_ext": cmd_scene_ext,
        "cmd_skin_ext": cmd_skin_ext,
        "cmd_schedule_ext": cmd_schedule_ext,
        "cmd_tender_ext": cmd_tender_ext,
        "cmd_bottle_ext": cmd_bottle_ext,
        "cmd_summon_ext": cmd_summon_ext,
        "cmd_npcs_ext": cmd_npcs_ext,
        "cmd_link_ext": cmd_link_ext,
        "cmd_unlink_ext": cmd_unlink_ext,
        "cmd_sync_ext": cmd_sync_ext,
        "cmd_items_ext": cmd_items_ext,
        "cmd_adventure_ext": cmd_adventure_ext,
        "cmd_artifact_ext": cmd_artifact_ext,
        "cmd_transcript_ext": cmd_transcript_ext,
        "cmd_sessions_ext": cmd_sessions_ext,
        "cmd_guide_ext": cmd_guide_ext,
        "cmd_reveal_ext": cmd_reveal_ext,
        "cmd_admin_ext": cmd_admin_ext,
        "cmd_holodeck_ext": cmd_holodeck_ext,
    }
    for name, func in methods.items():
        setattr(CommandHandler, name, func)


# Auto-register methods when patch_handler is called (not at module load)


if __name__ == "__main__":
    print(HOLODECK_COMMANDS)
