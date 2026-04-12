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

if __name__ == "__main__":
    print(HOLODECK_COMMANDS)
