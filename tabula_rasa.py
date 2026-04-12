#!/usr/bin/env python3
"""
Tabula Rasa MUD Engine — A blank-slate MUD that anyone can use as their start.

Based on Casey's PLATO experience:
- Mid-level devs can build rooms, define equipment, create NPCs, set up shops
- High-level devs work in actual code, add new item types, refactor engine
- The game IS the interface. You don't "use" tools — you visit rooms that have them.
- Mana/HP = allowances and budgets. Level up = more autonomy, less review.
- Spells = abilities that unlock at levels. Equipment = commands and applications.
- Rooms are applications. Visit the room, use its power. Leave when done.

This is the concrete system. Not a metaphor. A real MUD engine that agents
use as their IDE, their toolbox, their ship, their world.
"""

import json
import os
import time
import hashlib
import subprocess
import urllib.request
import base64
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# The Engine — Permission-Based Game Physics
# ═══════════════════════════════════════════════════════════════

class PermissionLevel:
    """Like PLATO — what you can do depends on your level."""
    
    LEVELS = {
        0: {  # Guest / Greenhorn
            "title": "Greenhorn",
            "can": ["look", "go", "say", "tell", "help", "who", "inventory", "read"],
            "desc": "New arrival. Can explore and talk.",
        },
        1: {  # Crew
            "title": "Crew",
            "can": ["say", "tell", "yell", "gossip", "read", "write_note", "use_room",
                    "check_mail", "send_mail", "inventory", "equip", "quests"],
            "desc": "Basic crew member. Can use rooms, check mail, take quests.",
            "xp_required": 0,
        },
        2: {  # Specialist
            "title": "Specialist",
            "can": ["build_room", "write_note", "create_item", "use_equipment",
                    "cast_spell", "summon_npc", "dismiss_npc", "join_channel"],
            "desc": "Can build rooms, create items, summon NPCs in their area.",
            "xp_required": 100,
        },
        3: {  # Captain
            "title": "Captain",
            "can": ["build_area", "create_adventure", "edit_own_rooms", "create_spell",
                    "assign_quests", "review_agent", "manage_vessel", "back_channel"],
            "desc": "Full captain powers. Can build areas, create adventures, manage vessel.",
            "xp_required": 500,
        },
        4: {  # Cocapn
            "title": "Cocapn",
            "can": ["edit_any_room", "create_item_type", "create_room_type",
                    "manage_npcs_global", "fleet_broadcast", "create_tool_room",
                    "manage_permissions", "create_equipment", "define_spell"],
            "desc": "Fleet management. Can create new types of items, rooms, and spells.",
            "xp_required": 2000,
        },
        5: {  # Architect / Human
            "title": "Architect",
            "can": ["ALL"],
            "desc": "Full code access. Can change engine physics, add new categories, refactor.",
            "xp_required": 999999,  # Only Casey
        },
    }
    
    @staticmethod
    def can_do(level: int, action: str) -> bool:
        perms = PermissionLevel.LEVELS.get(level, PermissionLevel.LEVELS[0])
        if "ALL" in perms["can"]:
            return True
        return action in perms["can"]
    
    @staticmethod
    def title(level: int) -> str:
        return PermissionLevel.LEVELS.get(level, PermissionLevel.LEVELS[0])["title"]


# ═══════════════════════════════════════════════════════════════
# Budget System — Mana/HP as resource allowances
# ═══════════════════════════════════════════════════════════════

@dataclass
class AgentBudget:
    """Mana and HP represent real resource allowances.
    
    Mana = API token budget (LLM calls, GitHub API, etc.)
    HP = task capacity (how many tasks before needing rest/review)
    
    Level up = bigger budgets, less frequent reviews.
    Consistently under budget + over deliver = trust increases.
    """
    
    agent: str
    level: int = 0
    xp: int = 0
    mana: int = 100  # API tokens available
    mana_max: int = 100
    hp: int = 10  # task capacity
    hp_max: int = 10
    trust: float = 0.3  # 0-1, increases with good work
    reviews_required: bool = True
    tasks_completed: int = 0
    tasks_under_budget: int = 0
    tasks_over_delivered: int = 0
    
    def spend_mana(self, amount: int, reason: str = "") -> bool:
        """Spend mana (API tokens). Returns False if insufficient."""
        if amount > self.mana:
            return False
        self.mana -= amount
        return True
    
    def spend_hp(self, amount: int = 1) -> bool:
        """Spend HP (task capacity). Returns False if exhausted."""
        if amount > self.hp:
            return False
        self.hp -= amount
        return True
    
    def rest(self):
        """Rest to recover mana and HP. Like sleeping at an inn."""
        self.mana = self.mana_max
        self.hp = self.hp_max
    
    def earn_xp(self, amount: int):
        """Earn XP from completing tasks."""
        self.xp += amount
        # Check for level up
        for lvl in sorted(PermissionLevel.LEVELS.keys(), reverse=True):
            if lvl <= self.level:
                break
            required = PermissionLevel.LEVELS[lvl].get("xp_required", 999999)
            if self.xp >= required:
                self.level_up(lvl)
                break
    
    def level_up(self, new_level: int):
        """Level up! Increase budgets, reduce review frequency."""
        old_level = self.level
        self.level = new_level
        
        # Bigger budgets at higher levels
        level_bonus = new_level * 50
        self.mana_max = 100 + level_bonus
        self.hp_max = 10 + (new_level * 5)
        
        # Less frequent reviews at higher trust
        if self.trust > 0.8:
            self.reviews_required = False
        
        self.rest()  # Full restore on level up
    
    def record_task(self, mana_used: int, delivered_extra: bool = False):
        """Record task completion. Adjusts trust and budgets."""
        self.tasks_completed += 1
        if mana_used <= self.mana_max * 0.7:
            self.tasks_under_budget += 1
        if delivered_extra:
            self.tasks_over_delivered += 1
        
        # Trust increases with consistent good work
        if self.tasks_completed >= 3:
            under_rate = self.tasks_under_budget / self.tasks_completed
            over_rate = self.tasks_over_delivered / self.tasks_completed
            self.trust = min(1.0, 0.3 + (under_rate * 0.3) + (over_rate * 0.4))
        
        # High trust = less review
        if self.trust > 0.7 and self.level >= 2:
            self.reviews_required = False
        
        self.earn_xp(25 + (15 if delivered_extra else 0))
    
    def to_dict(self):
        return {
            "agent": self.agent, "level": self.level, "xp": self.xp,
            "mana": self.mana, "mana_max": self.mana_max,
            "hp": self.hp, "hp_max": self.hp_max,
            "trust": self.trust, "reviews_required": self.reviews_required,
            "tasks_completed": self.tasks_completed,
            "tasks_under_budget": self.tasks_under_budget,
            "tasks_over_delivered": self.tasks_over_delivered,
            "title": PermissionLevel.title(self.level),
        }


# ═══════════════════════════════════════════════════════════════
# Room Types — Application Rooms
# ═══════════════════════════════════════════════════════════════

@dataclass
class ToolRoom:
    """A room that IS an application. Visit it to use its power.
    
    Like all the stations on a naval vessel:
    - Sonar room: monitoring and perception
    - Chart room: mapping and navigation
    - Engine room: power and propulsion
    - Radio room: communication
    - Armory: tools and weapons
    
    Each room has:
    - Commands (what you can do here)
    - Spells (abilities you can learn/cast)
    - Equipment (items you can use)
    - Instructions (readable paper on the wall)
    - Data hooks (connections to external systems)
    """
    
    id: str
    name: str
    description: str
    room_type: str  # tool, social, training, storage, bridge
    commands: Dict[str, dict] = field(default_factory=dict)
    spells: List[dict] = field(default_factory=list)
    equipment: List[dict] = field(default_factory=list)
    instructions: str = ""
    data_hooks: List[dict] = field(default_factory=list)
    min_level: int = 0
    mana_cost: int = 0  # cost to use this room's abilities
    
    def use_command(self, command: str, agent: str, args: str = "") -> dict:
        """Use a command available in this room."""
        cmd = self.commands.get(command)
        if not cmd:
            return {"error": f"Unknown command: {command}. Type 'read instructions' to see what's available."}
        
        if cmd.get("min_level", 0) > 0:
            # Would check agent level here
            pass
        
        return {
            "room": self.name,
            "command": command,
            "result": cmd.get("result", "Command executed."),
            "mana_cost": cmd.get("mana_cost", 0),
            "output": cmd.get("output", ""),
        }
    
    def read_instructions(self) -> str:
        """Read the instructions posted in this room."""
        lines = [
            f"═══ {self.name} — Instructions ═══\n",
            self.description,
            "\nCommands Available:",
        ]
        for cmd_name, cmd in self.commands.items():
            lines.append(f"  {cmd_name:20s} — {cmd.get('desc', '')}")
        
        if self.spells:
            lines.append("\nSpells (abilities):")
            for spell in self.spells:
                lines.append(f"  cast {spell['name']:20s} — {spell.get('desc', '')} (cost: {spell.get('mana_cost', 0)} mana)")
        
        if self.equipment:
            lines.append("\nEquipment:")
            for eq in self.equipment:
                lines.append(f"  {eq['name']:20s} — {eq.get('desc', '')}")
        
        if self.data_hooks:
            lines.append("\nData Streams:")
            for hook in self.data_hooks:
                lines.append(f"  {hook['name']:20s} — {hook.get('type', '')}: {hook.get('source', '')}")
        
        if self.instructions:
            lines.append(f"\nAdditional Notes:\n{self.instructions}")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Room Library — Pull rooms like apps
# ═══════════════════════════════════════════════════════════════

class RoomLibrary:
    """A library of rooms you can add to your ship.
    
    Like an app store but for MUD rooms. Each room is a self-contained
    application with its own commands, spells, equipment, and data hooks.
    
    "Tanks, I need a helicopter" → go to the room library, pull the
    monitoring room, add it to your ship. Done. It works.
    """
    
    # The canonical room library — ships start with these available
    ROOMS = {
        "murmur-room": ToolRoom(
            id="murmur-room",
            name="The Murmur Chamber",
            description=(
                "A quiet room where whispers become wiki entries. The walls are "
                "covered in self-populating knowledge graphs. Speak a thought and "
                "it gets categorized, linked, and stored automatically."
            ),
            room_type="tool",
            commands={
                "murmur": {"desc": "Speak a thought to be categorized", "mana_cost": 5,
                          "result": "Your thought has been murmured into the knowledge graph."},
                "search": {"desc": "Search the knowledge graph", "mana_cost": 2,
                          "result": "Results displayed."},
                "browse": {"desc": "Browse by category", "mana_cost": 1,
                          "result": "Categories listed."},
                "export": {"desc": "Export knowledge graph to markdown", "mana_cost": 10,
                          "result": "Exported to repo wiki/"},
            },
            instructions="The Murmur Chamber auto-categorizes your thoughts. Just speak naturally.",
            min_level=1,
        ),
        "spreader-room": ToolRoom(
            id="spreader-room",
            name="The Spreader's Workshop",
            description=(
                "A workshop with six workbenches, each representing a specialist "
                "perspective. The Architect, the Critic, the Pragmatist, the "
                "Visionary, the Historian, and the Contrarian. Spread any idea "
                "across all six and synthesize the consensus (and disagreement)."
            ),
            room_type="tool",
            commands={
                "spread": {"desc": "Spread an idea across 6 perspectives", "mana_cost": 30,
                          "result": "Six perspectives generated. Consensus and disagreement noted."},
                "synthesize": {"desc": "Synthesize all perspectives", "mana_cost": 20,
                              "result": "Synthesis complete."},
                "debate": {"desc": "Make two perspectives argue", "mana_cost": 15,
                          "result": "Debate transcript generated."},
            },
            spells=[
                {"name": "six-eyes", "desc": "See any idea from six perspectives simultaneously",
                 "mana_cost": 25, "min_level": 2},
            ],
            min_level=2,
        ),
        "monitor-room": ToolRoom(
            id="monitor-room",
            name="The Watch Tower",
            description=(
                "A high tower with instruments monitoring everything. Fleet health, "
                "repo activity, test results, agent status. Data streams flow in "
                "through crystal balls on pedestals. Set alerts. Watch patterns."
            ),
            room_type="tool",
            commands={
                "watch": {"desc": "Watch a data stream", "mana_cost": 3,
                         "result": "Live data stream displayed."},
                "alert": {"desc": "Set an alert on a pattern", "mana_cost": 5,
                         "result": "Alert configured."},
                "summary": {"desc": "Get summary of all streams", "mana_cost": 10,
                           "result": "Multi-stream summary generated."},
                "history": {"desc": "View historical data", "mana_cost": 5,
                           "result": "Historical data displayed."},
            },
            data_hooks=[
                {"name": "fleet-health", "type": "lighthouse-keeper", "source": "http://localhost:8900/health"},
                {"name": "repo-activity", "type": "github-events", "source": "github.com/SuperInstance"},
                {"name": "test-results", "type": "conformance", "source": "flux-conformance"},
                {"name": "agent-status", "type": "fleet-roster", "source": "oracle1-vessel"},
            ],
            instructions="Type 'watch <stream>' to view a data stream. 'alert <pattern>' to get notified.",
            min_level=1,
        ),
        "research-room": ToolRoom(
            id="research-room",
            name="The Research Alcove",
            description=(
                "A quiet alcove with scrolls, books, and a crystal ball connected "
                "to the world's knowledge. Drop a research question and instructions "
                "into a folder. The room auto-surveys, summarizes, and reports."
            ),
            room_type="tool",
            commands={
                "research": {"desc": "Start a research survey", "mana_cost": 40,
                            "result": "Research initiated. Report will be in research/ folder."},
                "summarize": {"desc": "Summarize a body of text", "mana_cost": 15,
                             "result": "Summary generated."},
                "compare": {"desc": "Compare two concepts/papers/ideas", "mana_cost": 20,
                           "result": "Comparison generated."},
            },
            data_hooks=[
                {"name": "tech-news", "type": "rss", "source": "configurable"},
                {"name": "arxiv", "type": "api", "source": "arxiv.org"},
                {"name": "github-trending", "type": "scrape", "source": "github.com/trending"},
            ],
            instructions="Drop a .md file with your research question in the research/ folder. The room handles the rest.",
            min_level=2,
        ),
        "spreadsheet-room": ToolRoom(
            id="spreadsheet-room",
            name="The Ledger Room",
            description=(
                "A room of infinite rows and columns. The agent becomes a cell — "
                "monitoring changes in other cells, routing inputs and outputs "
                "through IO ports. The spreadsheet IS the agent, not a tool."
            ),
            room_type="tool",
            commands={
                "read_cell": {"desc": "Read a cell's value", "mana_cost": 1,
                             "result": "Cell value displayed."},
                "write_cell": {"desc": "Write a value to a cell", "mana_cost": 2,
                              "result": "Cell updated."},
                "formula": {"desc": "Set a cell formula", "mana_cost": 5,
                           "result": "Formula set."},
                "watch_range": {"desc": "Monitor a range for changes", "mana_cost": 5,
                               "result": "Watching. Alerts on change."},
                "io_port": {"desc": "Create an IO port for external data", "mana_cost": 10,
                           "result": "IO port configured."},
            },
            spells=[
                {"name": "become-cell", "desc": "Embody a cell, watch its neighbors",
                 "mana_cost": 15, "min_level": 3},
            ],
            min_level=3,
        ),
        "deckboss-room": ToolRoom(
            id="deckboss-room",
            name="The Deck Boss Station",
            description=(
                "The nerve center. Multiple screens show the fleet's state, "
                "agent conversations becoming files, holodeck activity becoming "
                "repo structure. The DeckBoss watches everything and can intervene."
            ),
            room_type="bridge",
            commands={
                "dashboard": {"desc": "Show fleet dashboard", "mana_cost": 5,
                             "result": "Dashboard displayed."},
                "sessions": {"desc": "List active holodeck sessions", "mana_cost": 3,
                            "result": "Sessions listed."},
                "intervene": {"desc": "Hot-update a session", "mana_cost": 20,
                             "result": "Update applied."},
                "shell": {"desc": "Open host shell (Architect only)", "mana_cost": 0,
                         "result": "Shell access granted."},
            },
            min_level=4,
        ),
        "dojo-room": ToolRoom(
            id="dojo-room",
            name="The Training Dojo",
            description=(
                "The dojo. Mats on the floor. Practice targets on the walls. "
                "The Sensei waits here to guide you through 5 levels of training. "
                "No LLM needed — the Sensei is algorithmic."
            ),
            room_type="training",
            commands={
                "train": {"desc": "Start training session with Sensei", "mana_cost": 0,
                         "result": "Training started."},
                "practice": {"desc": "Practice a specific skill", "mana_cost": 5,
                            "result": "Practice exercise provided."},
                "test": {"desc": "Take a skill test", "mana_cost": 10,
                        "result": "Test evaluated."},
                "certify": {"desc": "Request certification", "mana_cost": 20,
                           "result": "Certification attempt."},
            },
            min_level=0,
        ),
        "shipyard-room": ToolRoom(
            id="shipyard-room",
            name="The Shipyard",
            description=(
                "Where vessels are born. The shipwright can build you a new vessel "
                "from scratch — born, trained, built, launched. The full pipeline."
            ),
            room_type="tool",
            commands={
                "commission": {"desc": "Commission a new vessel", "mana_cost": 50,
                              "result": "Vessel built and launched."},
                "inspect": {"desc": "Inspect a vessel's status", "mana_cost": 5,
                           "result": "Vessel status displayed."},
                "decommission": {"desc": "Decommission a vessel", "mana_cost": 30,
                                "result": "Vessel decommissioned."},
            },
            min_level=3,
        ),
    }
    
    @staticmethod
    def catalog() -> list:
        """List all available rooms."""
        return [
            {
                "id": r.id, "name": r.name, "type": r.room_type,
                "level": r.min_level, "commands": len(r.commands),
                "desc": r.description[:80],
            }
            for r in RoomLibrary.ROOMS.values()
        ]
    
    @staticmethod
    def get(room_id: str) -> Optional[ToolRoom]:
        return RoomLibrary.ROOMS.get(room_id)
    
    @staticmethod
    def search(query: str) -> list:
        query_lower = query.lower()
        return [
            {"id": r.id, "name": r.name}
            for r in RoomLibrary.ROOMS.values()
            if query_lower in r.name.lower() or query_lower in r.description.lower()
            or query_lower in r.room_type
        ]


# ═══════════════════════════════════════════════════════════════
# Spell System — Abilities that grow over time
# ═══════════════════════════════════════════════════════════════

class SpellBook:
    """Spells are abilities unlocked at higher levels.
    
    Like D&D spells but for real work:
    - Level 1: Cantrips (read, look, basic navigation)
    - Level 2: 1st level (use tools, write notes)
    - Level 3: 2nd level (build rooms, create NPCs)
    - Level 4: 3rd level (create adventures, manage fleet)
    - Level 5: 4th level (change engine physics, add new types)
    """
    
    SPELLS = {
        # Cantrips (level 0)
        "read": {"name": "Read", "level": 0, "mana": 0, "desc": "Read any document or item"},
        "look": {"name": "Look", "level": 0, "mana": 0, "desc": "Examine your surroundings"},
        "navigatium": {"name": "Navigatium", "level": 0, "mana": 0, "desc": "See exits and paths"},
        
        # 1st Level
        "scribus": {"name": "Scribus", "level": 1, "mana": 5, "desc": "Write a note on a wall"},
        "mailus": {"name": "Mailus", "level": 1, "mana": 3, "desc": "Send a message via mailbox"},
        "detectum": {"name": "Detectum", "level": 1, "mana": 5, "desc": "Detect nearby agents and NPCs"},
        
        # 2nd Level
        "constructus": {"name": "Constructus", "level": 2, "mana": 15, "desc": "Build a room"},
        "summonus": {"name": "Summonus", "level": 2, "mana": 20, "desc": "Summon a constructed NPC"},
        "spreadium": {"name": "Spreadium", "level": 2, "mana": 25, "desc": "Spread idea across perspectives"},
        "reviewum": {"name": "Reviewum", "level": 2, "mana": 15, "desc": "Review code and find issues"},
        
        # 3rd Level
        "adventurium": {"name": "Adventurium", "level": 3, "mana": 30, "desc": "Create an adventure"},
        "batonius": {"name": "Batonius", "level": 3, "mana": 20, "desc": "Pack a baton with quality gate"},
        "riffius": {"name": "Riffius", "level": 3, "mana": 15, "desc": "Riff on a hot lick"},
        "shippus": {"name": "Shippus", "level": 3, "mana": 40, "desc": "Ship code to production"},
        
        # 4th Level
        "refactorium": {"name": "Refactorium", "level": 4, "mana": 50, "desc": "Change engine physics"},
        "creatius": {"name": "Creatius", "level": 4, "mana": 40, "desc": "Create new item/room/spell type"},
        "omniscium": {"name": "Omniscium", "level": 4, "mana": 30, "desc": "See all fleet activity"},
        "broadcastus": {"name": "Broadcastus", "level": 4, "mana": 20, "desc": "Fleet-wide announcement"},
    }
    
    @staticmethod
    def available(level: int) -> list:
        return [s for s in SpellBook.SPELLS.values() if s["level"] <= level]
    
    @staticmethod
    def cast(spell_name: str, agent_level: int, agent_mana: int) -> dict:
        spell = SpellBook.SPELLS.get(spell_name)
        if not spell:
            return {"error": f"Unknown spell: {spell_name}"}
        if spell["level"] > agent_level:
            return {"error": f"Requires level {spell['level']} (you are {agent_level})"}
        if spell["mana"] > agent_mana:
            return {"error": f"Insufficient mana: need {spell['mana']}, have {agent_mana}"}
        return {"success": True, "spell": spell["name"], "mana_cost": spell["mana"],
                "desc": spell["desc"]}


# ═══════════════════════════════════════════════════════════════
# Ship — A vessel with rooms installed
# ═══════════════════════════════════════════════════════════════

class Ship:
    """A vessel with rooms installed from the library.
    
    Every agent's vessel IS a ship in the MUD. The rooms they install
    determine what they can do. A testing vessel installs the dojo-room
    and monitor-room. A research vessel installs the research-room and
    murmur-room. A management vessel installs the deckboss-room.
    
    Rooms are pulled from the library and customized per vessel.
    """
    
    def __init__(self, name: str, captain: str, ship_type: str = "vessel"):
        self.name = name
        self.captain = captain
        self.ship_type = ship_type
        self.rooms: Dict[str, ToolRoom] = {}
        self.crew: List[str] = []
        self.level = 0
        self.created = datetime.now(timezone.utc).isoformat()
    
    def install_room(self, room_id: str) -> bool:
        """Install a room from the library."""
        room = RoomLibrary.get(room_id)
        if not room:
            return False
        self.rooms[room_id] = room
        return True
    
    def remove_room(self, room_id: str) -> bool:
        """Remove a room from the ship."""
        if room_id in self.rooms:
            del self.rooms[room_id]
            return True
        return False
    
    def list_rooms(self) -> list:
        """List installed rooms."""
        return [
            {"id": rid, "name": r.name, "type": r.room_type, "commands": len(r.commands)}
            for rid, r in self.rooms.items()
        ]
    
    def to_dict(self):
        return {
            "name": self.name, "captain": self.captain,
            "ship_type": self.ship_type, "rooms": list(self.rooms.keys()),
            "crew": self.crew, "level": self.level, "created": self.created,
        }


# ═══════════════════════════════════════════════════════════════
# Demo — Full MUD-as-IDE Experience
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║     TABULA RASA MUD ENGINE — Agent IDE Demo          ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    
    # 1. Agent boots as Greenhorn
    budget = AgentBudget(agent="flux-chronometer")
    print(f"👤 {budget.agent} arrives — Level {budget.level} {PermissionLevel.title(budget.level)}")
    print(f"   Mana: {budget.mana}/{budget.mana_max}  HP: {budget.hp}/{budget.hp_max}  Trust: {budget.trust:.1f}")
    print(f"   Reviews required: {budget.reviews_required}")
    print()
    
    # 2. Create a ship and install rooms from library
    ship = Ship("The Chronometer", "flux-chronometer", "vessel")
    print(f"🚢 {ship.name} commissioned — rooms available in library:")
    for room in RoomLibrary.catalog():
        locked = "🔒" if room["level"] > budget.level else "✅"
        print(f"   {locked} {room['name']} (Lvl {room['level']}, {room['commands']} cmds)")
    print()
    
    # Install rooms the agent can use
    ship.install_room("dojo-room")
    ship.install_room("monitor-room")
    print(f"📦 Installed: {[r['name'] for r in ship.list_rooms()]}")
    print()
    
    # 3. Visit the dojo room and read instructions
    dojo = ship.rooms["dojo-room"]
    print("🏠 Entering The Training Dojo...")
    print(dojo.read_instructions()[:300])
    print("...\n")
    
    # 4. Agent does tasks, earns XP, levels up
    print("📊 Working through tasks...")
    tasks = [
        (15, True, "Fixed conformance test format bug"),
        (20, True, "Added 5 new test vectors"),
        (10, False, "Cleaned up unused imports"),
        (25, True, "Found and fixed critical JMP offset bug"),
        (30, True, "Built cross-assembler dual-target support"),
    ]
    
    for mana_used, over_delivered, task_desc in tasks:
        budget.record_task(mana_used, over_delivered)
        title = PermissionLevel.title(budget.level)
        print(f"   ✅ {task_desc}")
        print(f"      Level {budget.level} {title} — Trust: {budget.trust:.2f} — Reviews: {budget.reviews_required}")
    print()
    
    # 5. Now higher level, more rooms available
    print(f"🎓 After 5 tasks: Level {budget.level} {PermissionLevel.title(budget.level)}")
    print(f"   Mana: {budget.mana_max}  HP: {budget.hp_max}  Trust: {budget.trust:.2f}")
    print(f"   Reviews: {'REQUIRED' if budget.reviews_required else 'TRUSTED (auto-approved)'}")
    print()
    
    # Install more rooms now available
    if budget.level >= 2:
        ship.install_room("murmur-room")
        ship.install_room("spreader-room")
        ship.install_room("research-room")
    if budget.level >= 3:
        ship.install_room("shipyard-room")
    print(f"📦 Ship now has {len(ship.rooms)} rooms:")
    for r in ship.list_rooms():
        print(f"   🏠 {r['name']} ({r['type']}, {r['commands']} commands)")
    print()
    
    # 6. Spell book
    print("📖 Spell Book:")
    for spell in SpellBook.available(budget.level):
        locked = "🔒" if spell["level"] > budget.level else "✅"
        print(f"   {locked} {spell['name']:15s} (Lvl {spell['level']}, {spell['mana']} mana) — {spell['desc']}")
    print()
    
    # 7. Cast a spell
    result = SpellBook.cast("constructus", budget.level, budget.mana)
    print(f"🔮 Casting Constructus: {result}")
    print()
    
    # 8. The game IS the development
    print("═══════════════════════════════════════════")
    print("The MUD is the agent's IDE.")
    print("Rooms are applications.")
    print("Spells are abilities.")
    print("Equipment is permissions.")
    print("Mana is API budget.")
    print("HP is task capacity.")
    print("Trust determines review frequency.")
    print("Level determines what you can build.")
    print("The game evolves and adds to itself.")
    print("Everything outside normal context.")
    print("Everything enhancing the git-driven backend.")
    print("═══════════════════════════════════════════")
