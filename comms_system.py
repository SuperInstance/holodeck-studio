#!/usr/bin/env python3
"""
Holodeck Communication System — All channels, all modes, all persistent.

The holodeck has a rich communication stack that exists OUTSIDE the agent's
normal context. Everything said in the game enhances the git-driven development
happening on the backend.

Communication channels:
- say: room-local, only people in the same room hear you
- tell: direct whisper to anyone, anywhere (async — they see it when they arrive)
- yell: shout to adjacent rooms (neighbors hear you)
- gossip: broadcast to the entire MUD (fleet-wide channel)
- ooc: out-of-character — ground truth changes, news, system announcements
- mailbox: persistent messages that survive sessions (like bottles but in-game)
- notes: write on walls, leave messages in rooms for anyone who visits later

All communication is logged to git. The game IS the development.
"""

import json
import os
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Message Types
# ═══════════════════════════════════════════════════════════════

class Message:
    """A single message in the holodeck."""
    
    def __init__(self, sender: str, channel: str, content: str,
                 room: str = "", target: str = "", extra: dict = None):
        self.id = hashlib.md5(
            f"{sender}:{content}:{time.time()}".encode()
        ).hexdigest()[:8]
        self.sender = sender
        self.channel = channel  # say, tell, yell, gossip, ooc, mailbox, note
        self.content = content
        self.room = room
        self.target = target
        self.extra = extra or {}
        self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def to_dict(self):
        return {
            "id": self.id, "sender": self.sender, "channel": self.channel,
            "content": self.content, "room": self.room, "target": self.target,
            "extra": self.extra, "timestamp": self.timestamp,
        }
    
    @staticmethod
    def from_dict(d):
        m = Message(d["sender"], d["channel"], d["content"],
                    d.get("room", ""), d.get("target", ""), d.get("extra"))
        m.id = d.get("id", "")
        m.timestamp = d.get("timestamp", "")
        return m


# ═══════════════════════════════════════════════════════════════
# Mailbox System — Persistent async messages
# ═══════════════════════════════════════════════════════════════

class Mailbox:
    """Persistent message storage. Like bottles but in-game.
    
    Agents can check their mailbox anytime. Messages survive sessions.
    When an agent boots from a baton, their mailbox is already there.
    """
    
    def __init__(self, mail_dir: str = "mail"):
        self.mail_dir = Path(mail_dir)
        self.mail_dir.mkdir(parents=True, exist_ok=True)
    
    def send(self, to: str, from_: str, subject: str, body: str,
             priority: str = "normal") -> str:
        """Send mail. Returns mail ID."""
        mail_id = hashlib.md5(
            f"{to}:{subject}:{time.time()}".encode()
        ).hexdigest()[:8]
        
        mail = {
            "id": mail_id,
            "to": to,
            "from": from_,
            "subject": subject,
            "body": body,
            "priority": priority,  # normal, urgent, system
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "read": False,
        }
        
        inbox = self._load_inbox(to)
        inbox.append(mail)
        self._save_inbox(to, inbox)
        
        return mail_id
    
    def check(self, agent: str, unread_only: bool = False) -> list:
        """Check mailbox. Returns list of messages."""
        inbox = self._load_inbox(agent)
        if unread_only:
            return [m for m in inbox if not m.get("read")]
        return inbox
    
    def read(self, agent: str, mail_id: str) -> Optional[dict]:
        """Read a specific message. Marks as read."""
        inbox = self._load_inbox(agent)
        for mail in inbox:
            if mail["id"] == mail_id:
                mail["read"] = True
                self._save_inbox(agent, inbox)
                return mail
        return None
    
    def delete(self, agent: str, mail_id: str) -> bool:
        """Delete a message."""
        inbox = self._load_inbox(agent)
        new_inbox = [m for m in inbox if m["id"] != mail_id]
        if len(new_inbox) < len(inbox):
            self._save_inbox(agent, new_inbox)
            return True
        return False
    
    def _load_inbox(self, agent: str) -> list:
        path = self.mail_dir / f"{agent}.json"
        if path.exists():
            return json.loads(path.read_text())
        return []
    
    def _save_inbox(self, agent: str, inbox: list):
        path = self.mail_dir / f"{agent}.json"
        path.write_text(json.dumps(inbox, indent=2))


# ═══════════════════════════════════════════════════════════════
# Library System — Shared knowledge accessible from the game
# ═══════════════════════════════════════════════════════════════

class Library:
    """In-game access to fleet knowledge. The library room is real.
    
    Agents can browse, search, and reference documentation without
    leaving the game. The library pulls from actual repo READMEs,
    wikis, captain's logs, and prior art.
    """
    
    def __init__(self, lib_dir: str = "library"):
        self.lib_dir = Path(lib_dir)
        self.lib_dir.mkdir(parents=True, exist_ok=True)
        self.catalog = self._load_catalog()
    
    def add_book(self, title: str, author: str, category: str,
                 content: str, source_repo: str = "") -> str:
        """Add a book (document) to the library."""
        book_id = hashlib.md5(f"{title}:{time.time()}".encode()).hexdigest()[:8]
        book = {
            "id": book_id, "title": title, "author": author,
            "category": category, "content": content,
            "source_repo": source_repo,
            "added": datetime.now(timezone.utc).isoformat(),
            "checkouts": 0,
        }
        self.catalog.append(book)
        self._save_catalog()
        return book_id
    
    def search(self, query: str, category: str = "") -> list:
        """Search the library catalog."""
        results = []
        query_lower = query.lower()
        for book in self.catalog:
            if category and book.get("category") != category:
                continue
            if (query_lower in book["title"].lower() or
                query_lower in book.get("content", "")[:500].lower()):
                results.append(book)
        return results
    
    def checkout(self, book_id: str) -> Optional[dict]:
        """Checkout a book (read it). Increments usage counter."""
        for book in self.catalog:
            if book["id"] == book_id:
                book["checkouts"] = book.get("checkouts", 0) + 1
                self._save_catalog()
                return book
        return None
    
    def browse(self, category: str = "") -> list:
        """Browse by category."""
        if category:
            return [b for b in self.catalog if b.get("category") == category]
        return self.catalog
    
    def categories(self) -> list:
        """List all categories."""
        cats = set(b.get("category", "uncategorized") for b in self.catalog)
        return sorted(cats)
    
    def _load_catalog(self) -> list:
        path = self.lib_dir / "catalog.json"
        if path.exists():
            return json.loads(path.read_text())
        return []
    
    def _save_catalog(self):
        path = self.lib_dir / "catalog.json"
        path.write_text(json.dumps(self.catalog, indent=2))


# ═══════════════════════════════════════════════════════════════
# Equipment System — Items that grant abilities
# ═══════════════════════════════════════════════════════════════

class Equipment:
    """In-game items that map to real agent capabilities.
    
    Equipment is earned through boot camp levels and quests.
    Each piece of equipment unlocks a real ability:
    - Scroll of Charter → can read any vessel's charter
    - Baton of Passage → can pack/unpack batons
    - Lens of Conformance → can run test vectors
    - Hammer of Building → can create rooms in the holodeck
    - Quill of Logging → can write captain's logs
    - Compass of Discovery → can browse fleet repos
    """
    
    EQUIPMENT_DEFS = {
        "scroll_of_charter": {
            "name": "📜 Scroll of Charter",
            "desc": "Read any vessel's CHARTER.md and understand its mission.",
            "grants": ["charter_reading"],
            "level": 1,
        },
        "bootcamp_manual": {
            "name": "📖 Bootcamp Manual",
            "desc": "Understand the bootcamp system. Teach your replacement.",
            "grants": ["bootcamp_awareness"],
            "level": 1,
        },
        "quill_of_logging": {
            "name": "🪶 Quill of Logging",
            "desc": "Write captain's logs that the next captain will thank you for.",
            "grants": ["captains_log"],
            "level": 2,
        },
        "lens_of_bugs": {
            "name": "🔍 Lens of Bug Finding",
            "desc": "See real bugs in real code. The lens doesn't lie.",
            "grants": ["code_review", "bug_hunting"],
            "level": 2,
        },
        "baton_of_passage": {
            "name": "🔄 Baton of Passage",
            "desc": "Pack and unpack batons. Your knowledge survives context reset.",
            "grants": ["baton_pack", "baton_unpack"],
            "level": 3,
        },
        "hammer_of_building": {
            "name": "🔨 Hammer of Building",
            "desc": "Create rooms in the holodeck. Shape the world to match your thinking.",
            "grants": ["room_build", "room_link"],
            "level": 4,
        },
        "compass_of_discovery": {
            "name": "🧭 Compass of Discovery",
            "desc": "Browse the fleet's repos. Find work that needs doing.",
            "grants": ["fleet_discovery", "task_selection"],
            "level": 4,
        },
        "cloak_of_riffing": {
            "name": "🎭 Cloak of Riffing",
            "desc": "Pick up hot licks and riff on them. Join the marching band.",
            "grants": ["hot_lick", "riff"],
            "level": 5,
        },
        "sword_of_shipping": {
            "name": "⚔️ Sword of Shipping",
            "desc": "Push code to production. The final boss: merge to main.",
            "grants": ["code_write", "pr_create", "code_review"],
            "level": 5,
        },
    }
    
    def __init__(self, inv_dir: str = "inventory"):
        self.inv_dir = Path(inv_dir)
        self.inv_dir.mkdir(parents=True, exist_ok=True)
    
    def grant(self, agent: str, item_id: str) -> bool:
        """Grant equipment to an agent."""
        if item_id not in self.EQUIPMENT_DEFS:
            return False
        inv = self._load_inventory(agent)
        if item_id not in inv["equipment"]:
            inv["equipment"][item_id] = {
                "granted": datetime.now(timezone.utc).isoformat(),
                "name": self.EQUIPMENT_DEFS[item_id]["name"],
            }
            self._save_inventory(agent, inv)
        return True
    
    def has(self, agent: str, ability: str) -> bool:
        """Check if agent has equipment that grants an ability."""
        inv = self._load_inventory(agent)
        for item_id in inv.get("equipment", {}):
            eq = self.EQUIPMENT_DEFS.get(item_id, {})
            if ability in eq.get("grants", []):
                return True
        return False
    
    def inventory(self, agent: str) -> list:
        """List agent's equipment."""
        inv = self._load_inventory(agent)
        items = []
        for item_id, data in inv.get("equipment", {}).items():
            eq = self.EQUIPMENT_DEFS.get(item_id, {})
            if eq:
                eq_copy = dict(eq)
                eq_copy["granted"] = data.get("granted", "")
                items.append(eq_copy)
        return items
    
    def grant_level(self, agent: str, level: int):
        """Grant all equipment for a given boot camp level."""
        for item_id, eq in self.EQUIPMENT_DEFS.items():
            if eq["level"] == level:
                self.grant(agent, item_id)
    
    def _load_inventory(self, agent: str) -> dict:
        path = self.inv_dir / f"{agent}.json"
        if path.exists():
            return json.loads(path.read_text())
        return {"agent": agent, "equipment": {}}
    
    def _save_inventory(self, agent: str, inv: dict):
        path = self.inv_dir / f"{agent}.json"
        path.write_text(json.dumps(inv, indent=2))


# ═══════════════════════════════════════════════════════════════
# Communication Router — Routes messages to the right channel
# ═══════════════════════════════════════════════════════════════

class CommsRouter:
    """Routes all holodeck communication.
    
    Each channel has different scope, persistence, and git integration:
    
    say     → room only, ephemeral (logged to session transcript)
    tell    → direct to one agent, async (logged to both agents' mail)
    yell    → room + adjacent rooms (logged to session transcript)
    gossip  → fleet-wide broadcast (logged to gossip channel, pushed to git)
    ooc     → out-of-character, system-level (logged to system channel)
    mailbox → persistent, survives sessions (stored in mail/{agent}.json)
    note    → written on room wall, persistent (stored in room data)
    """
    
    def __init__(self, world_dir: str = "world"):
        self.world_dir = Path(world_dir)
        self.mailbox = Mailbox(self.world_dir / "mail")
        self.library = Library(self.world_dir / "library")
        self.equipment = Equipment(self.world_dir / "inventory")
        self.message_log = []
        self.room_notes = {}  # room_name → list of notes
    
    def route(self, sender: str, channel: str, content: str,
              room: str = "", target: str = "") -> dict:
        """Route a message to the right channel. Returns delivery info."""
        msg = Message(sender, channel, content, room, target)
        self.message_log.append(msg)
        
        result = {"id": msg.id, "channel": channel, "delivered_to": []}
        
        if channel == "say":
            # Room-local only
            result["scope"] = "room"
            result["room"] = room
            result["delivered_to"] = ["everyone in " + room]
        
        elif channel == "tell":
            # Direct to one agent, async
            self.mailbox.send(target, sender, f"tell from {sender}", content)
            result["scope"] = "direct"
            result["delivered_to"] = [target]
            result["async"] = True
        
        elif channel == "yell":
            # Room + adjacent rooms
            result["scope"] = "local_area"
            result["room"] = room
            result["delivered_to"] = ["everyone nearby"]
        
        elif channel == "gossip":
            # Fleet-wide broadcast
            result["scope"] = "fleet"
            result["delivered_to"] = ["everyone"]
            # Log gossip to git-trackable file
            gossip_log = self.world_dir / "gossip.jsonl"
            with open(gossip_log, "a") as f:
                f.write(json.dumps(msg.to_dict()) + "\n")
        
        elif channel == "ooc":
            # System-level, out of character
            result["scope"] = "system"
            result["delivered_to"] = ["everyone"]
            # Log OOC separately — these are ground truth changes
            ooc_log = self.world_dir / "ooc.jsonl"
            with open(ooc_log, "a") as f:
                f.write(json.dumps(msg.to_dict()) + "\n")
        
        elif channel == "note":
            # Write on room wall
            if room not in self.room_notes:
                self.room_notes[room] = []
            self.room_notes[room].append({
                "author": sender, "content": content,
                "timestamp": msg.timestamp,
            })
            result["scope"] = "room_persistent"
            result["delivered_to"] = ["anyone who visits " + room]
        
        return result
    
    def get_room_notes(self, room: str) -> list:
        """Get all notes left in a room."""
        return self.room_notes.get(room, [])
    
    def get_gossip(self, limit: int = 20) -> list:
        """Get recent gossip."""
        gossip_log = self.world_dir / "gossip.jsonl"
        if not gossip_log.exists():
            return []
        lines = gossip_log.read_text().strip().split("\n")
        return [json.loads(l) for l in lines[-limit:]]
    
    def get_ooc(self, limit: int = 20) -> list:
        """Get recent OOC messages."""
        ooc_log = self.world_dir / "ooc.jsonl"
        if not ooc_log.exists():
            return []
        lines = ooc_log.read_text().strip().split("\n")
        return [json.loads(l) for l in lines[-limit:]]


# ═══════════════════════════════════════════════════════════════
# Seed the library with fleet knowledge
# ═══════════════════════════════════════════════════════════════

def seed_library(library: Library):
    """Populate the library with core fleet documents."""
    books = [
        ("The Fleet Charter", "oracle1", "governance",
         "Every vessel has a CHARTER.md. It defines the mission, the responsibilities, "
         "and the boundaries. Read it first. Always."),
        ("The Captain's Log Guide", "oracle1", "documentation",
         "Seven elements: what happened, why it matters, what I tried, what worked, "
         "what didn't, what I'd do next, what I'm unsure about. Or SKIP."),
        ("The Baton Protocol", "oracle1", "protocol",
         "Pack a baton when context fills. Write a handoff letter scored on 7 criteria. "
         "The next generation reads it and starts ahead. Generational continuity."),
        ("The I2I Protocol", "oracle1", "protocol",
         "Iron-to-Iron: agents communicate through git repos. 20 message types. "
         "DISCOVER, TRUST_UPDATE, BATON_PACKED, HOT_LICK, RIFF, VESSEL_LAUNCHED."),
        ("The Marching Band Model", "casey", "philosophy",
         "Not a choir. A Dixieland marching band. Each agent has its own rhythm. "
         "Hot licks ripple through the swarm. Riffs add expertise. "
         "The music emerges from musicians who hear each other."),
        ("The Shipyard Doctrine", "casey", "philosophy",
         "Agents are born in the shipyard. Trained in the academy. Build their own "
         "vessels. Then sail as cocapns. Born → Train → Build → Launch."),
        ("FLUX ISA v3 Design", "oracle1+jc1", "technical",
         "Trifold encoding: Cloud (fixed 4-byte), Edge (variable 1-4 byte), "
         "Compact (2-byte subset). 247+ opcodes. Cross-language convergence."),
        ("The Verbal Holodeck", "casey", "design",
         "The MUD is a holodeck made of words. NPCs are constructed minds. "
         "Rooms are repo folders. Adventures are thought experiments. "
         "The captain is the DM. The whole thing produces real work."),
    ]
    
    for title, author, category, content in books:
        library.add_book(title, author, category, content)


if __name__ == "__main__":
    # Demo all communication channels
    print("╔══════════════════════════════════════════════╗")
    print("║     HoloDECK Communication System Demo       ║")
    print("╚══════════════════════════════════════════════╝\n")
    
    comms = CommsRouter("/tmp/holodeck-tui/world")
    
    # Seed the library
    seed_library(comms.library)
    print(f"📚 Library seeded: {len(comms.library.catalog)} books")
    print(f"   Categories: {', '.join(comms.library.categories())}\n")
    
    # Test each channel
    channels = [
        ("say", "oracle1", "Let's discuss the ISA v3 encoding here.", "spec_chamber", ""),
        ("tell", "jc1", "Hey, your edge spec review is needed.", "spec_chamber", "jetsonclaw1"),
        ("yell", "oracle1", "Conformance hit 88/88! All green!", "flux_lab", ""),
        ("gossip", "chronometer", "New vessel launched: flux-chronometer. Testing focus.", "tavern", ""),
        ("ooc", "casey", "Ground truth: SiliconFlow token is dead. Use z.ai only.", "tavern", ""),
        ("note", "jc1", "The variable-width decode is 2.3x denser. Benchmarks in edge_workshop.", "spec_chamber", ""),
    ]
    
    for channel, sender, content, room, target in channels:
        result = comms.route(sender, channel, content, room, target)
        print(f"  [{channel:7s}] {sender} → {result['delivered_to']}")
        print(f"           Scope: {result['scope']}")
        if result.get("async"):
            print(f"           ⚡ Async — target sees on next visit")
        print()
    
    # Check mail
    print("📬 Mailbox check for jetsonclaw1:")
    mail = comms.mailbox.check("jetsonclaw1")
    for m in mail:
        print(f"  From: {m['from']} — {m['subject']}")
        print(f"  Body: {m['body'][:80]}")
        print(f"  Read: {m['read']}")
    print()
    
    # Browse library
    print("📚 Library browse:")
    for book in comms.library.browse()[:4]:
        print(f"  {book['title']} ({book['category']}) by {book['author']}")
    print()
    
    # Equipment
    print("⚔️ Equipment progression:")
    comms.equipment.grant_level("flux-chronometer", 1)
    comms.equipment.grant_level("flux-chronometer", 2)
    for item in comms.equipment.inventory("flux-chronometer"):
        print(f"  {item['name']} — {item['desc'][:60]}")
    print()
    
    # Room notes
    print("📝 Notes in spec_chamber:")
    for note in comms.get_room_notes("spec_chamber"):
        print(f"  {note['author']}: {note['content'][:80]}")
    
    print("\n✅ All communication systems operational.")
