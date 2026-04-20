#!/usr/bin/env python3
"""
FLUX-LCAR Engine — The actual runtime.

Agent-first: agents run the ship. Humans can step aboard via TUI
or just communicate through Discord/Telegram/OpenClaw without ever
touching the MUD directly.

The MUD is the backend. Messaging channels are just another room exit.
"""

import json
import time
import asyncio
import hashlib
from enum import Enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone

# ═══════════════════════════════════════════
# Core Types
# ═══════════════════════════════════════════

class AlertLevel(Enum):
    GREEN = 0
    YELLOW = 1
    RED = 2

class Formality(Enum):
    NAVAL = 1
    PROFESSIONAL = 2
    TNG = 3
    CASUAL = 4
    MINIMAL = 5

class MsgType(Enum):
    SAY = "say"        # room only
    TELL = "tell"      # direct
    YELL = "yell"      # adjacent rooms
    GOSSIP = "gossip"  # ship-wide
    ALERT = "alert"    # system alert
    BOTTLE = "bottle"  # async, persists

@dataclass
class Gauge:
    name: str
    value: float
    unit: str = ""
    min_val: float = 0.0
    max_val: float = 1.0
    yellow_threshold: float = 0.7
    red_threshold: float = 0.9
    
    @property
    def status(self) -> str:
        pct = self.value / self.max_val if self.max_val > 0 else 0
        if pct >= self.red_threshold:
            return "RED"
        elif pct >= self.yellow_threshold:
            return "YELLOW"
        return "GREEN"
    
    @property
    def bar(self) -> str:
        width = 20
        filled = int((self.value / self.max_val) * width) if self.max_val > 0 else 0
        color = {"GREEN": "░", "YELLOW": "▒", "RED": "▓"}[self.status]
        return f"{color * filled}{'░' * (width - filled)}"

@dataclass
class Message:
    sender: str
    content: str
    msg_type: MsgType
    room_id: Optional[str] = None
    target: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    
@dataclass
class Tick:
    """One combat tick — snapshot of a room's state."""
    room_id: str
    tick_num: int
    gauges: Dict[str, float]
    agent_action: str
    autonomy: float
    script_version: int
    timestamp: float = field(default_factory=time.time)

# ═══════════════════════════════════════════
# Room
# ═══════════════════════════════════════════

class Room:
    def __init__(self, id: str, name: str, description: str):
        self.id = id
        self.name = name
        self.description = description
        self.exits: Dict[str, str] = {}          # direction -> room_id
        self.agents: List[str] = []               # agent names in room
        self.gauges: Dict[str, Gauge] = {}
        self.notes: List[dict] = []
        self.booted = False
        self.tick_count = 0
        self.alert_level = AlertLevel.GREEN
        
        # Callbacks — wire real systems here
        self.on_boot: Optional[Callable] = None
        self.on_shutdown: Optional[Callable] = None
        self.on_tick: Optional[Callable] = None
        self.on_command: Optional[Callable] = None
        self.on_agent_enter: Optional[Callable] = None
        self.on_agent_leave: Optional[Callable] = None
        self.on_gauge_change: Optional[Callable] = None
    
    def add_exit(self, direction: str, target_id: str):
        self.exits[direction] = target_id
    
    def add_gauge(self, gauge: Gauge):
        self.gauges[gauge.name] = gauge
    
    def update_gauge(self, name: str, value: float):
        if name in self.gauges:
            old_status = self.gauges[name].status
            self.gauges[name].value = value
            new_status = self.gauges[name].status
            if old_status != new_status and self.on_gauge_change:
                self.on_gauge_change(self, name, old_status, new_status)
            # Auto-escalate
            if new_status == "RED":
                self.alert_level = AlertLevel.RED
            elif new_status == "YELLOW" and self.alert_level == AlertLevel.GREEN:
                self.alert_level = AlertLevel.YELLOW
    
    def boot(self, agent_name: str) -> str:
        self.booted = True
        self.agents.append(agent_name)
        if self.on_boot:
            self.on_boot(self)
        return f"{self.name} online."
    
    def shutdown(self):
        self.booted = False
        self.agents.clear()
        if self.on_shutdown:
            self.on_shutdown(self)
    
    def look(self, formality: Formality = Formality.TNG) -> str:
        lines = [f"{self.name}", self.description, ""]
        
        if self.gauges:
            for g in self.gauges.values():
                lines.append(f"  {g.name}: {g.value:.1f}{g.unit} {g.bar} {g.status}")
            lines.append("")
        
        if self.exits:
            lines.append(f"Exits: {', '.join(self.exits.keys())}")
        
        if self.agents:
            lines.append(f"Agents: {', '.join(self.agents)}")
        
        if self.notes:
            lines.append(f"\nNotes ({len(self.notes)}):")
            for n in self.notes[-5:]:
                lines.append(f"  [{n['author']}] {n['content']}")
        
        return "\n".join(lines)

# ═══════════════════════════════════════════
# Agent (Crew Member)
# ═══════════════════════════════════════════

class Agent:
    def __init__(self, name: str, role: str = "crew"):
        self.name = name
        self.role = role  # cocapn, officer, crew, ensign
        self.room_id: Optional[str] = None
        self.permission_level = 0
        self.formality_preference = Formality.TNG
        
        # Station assignment
        self.station: Optional[str] = None
        self.standing_orders: List[str] = []
        self.current_task: Optional[str] = None
        self.script_version = 1
        self.script_rules: List[dict] = []
        self.autonomy_score = 1.0
        
        # Communication
        self.mailbox: List[Message] = []
        self.channels: Dict[str, Callable] = {}  # channel -> send function
        
        # Learning
        self.crew_log: List[dict] = []
        self.morning_routine: List[str] = []
        self.diary: List[dict] = []
    
    def assign_station(self, room_id: str):
        self.station = room_id
        self.room_id = room_id
    
    def add_channel(self, name: str, send_fn: Callable):
        """Wire a real communication channel (Telegram, Discord, etc.)"""
        self.channels[name] = send_fn
    
    def send_to_channel(self, channel: str, message: str):
        """Send a message through a wired channel."""
        if channel in self.channels:
            self.channels[channel](message)
    
    def file_log(self, entry: str):
        self.crew_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "entry": entry,
            "station": self.station,
            "task": self.current_task,
        })
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "role": self.role,
            "station": self.station,
            "permission_level": self.permission_level,
            "standing_orders": self.standing_orders,
            "morning_routine": self.morning_routine,
            "script_version": self.script_version,
            "script_rules": self.script_rules,
            "autonomy_score": self.autonomy_score,
        }

# ═══════════════════════════════════════════
# Ship (the whole MUD)
# ═══════════════════════════════════════════

class Ship:
    def __init__(self, name: str = "cocapn-1"):
        self.name = name
        self.rooms: Dict[str, Room] = {}
        self.agents: Dict[str, Agent] = {}
        self.formality = Formality.TNG
        self.alert_level = AlertLevel.GREEN
        self.tick_number = 0
        self.message_log: List[Message] = []
        self.tick_history: List[Tick] = []
        
        # Wired channels — messages flow out to real systems
        self.channels: Dict[str, Callable] = {}
        
        # Modules — constraint theory, FLUX runtime, etc.
        self.modules: Dict[str, Any] = {}
    
    # ── Room Management ──
    
    def add_room(self, id: str, name: str, desc: str) -> Room:
        room = Room(id, name, desc)
        self.rooms[id] = room
        return room
    
    def connect(self, from_id: str, direction: str, to_id: str):
        if from_id in self.rooms and to_id in self.rooms:
            self.rooms[from_id].add_exit(direction, to_id)
    
    # ── Agent Management ──
    
    def add_agent(self, name: str, role: str = "crew") -> Agent:
        agent = Agent(name, role)
        self.agents[name] = agent
        return agent
    
    def assign_station(self, agent_name: str, room_id: str):
        agent = self.agents.get(agent_name)
        room = self.rooms.get(room_id)
        if agent and room:
            # Leave old room
            if agent.room_id and agent.room_id in self.rooms:
                old_room = self.rooms[agent.room_id]
                if agent_name in old_room.agents:
                    old_room.agents.remove(agent_name)
            # Enter new room
            agent.assign_station(room_id)
            room.boot(agent_name)
    
    # ── Communication ──
    
    def say(self, sender: str, content: str) -> str:
        """Room-local message."""
        agent = self.agents.get(sender)
        if not agent or not agent.room_id:
            return "You are nowhere."
        room = self.rooms.get(agent.room_id)
        if not room:
            return "Room not found."
        
        msg = Message(sender=sender, content=content, 
                     msg_type=MsgType.SAY, room_id=agent.room_id)
        self.message_log.append(msg)
        
        # Deliver to all agents in room (including channel bridges)
        responses = []
        for name in room.agents:
            if name != sender:
                other = self.agents.get(name)
                if other:
                    for ch_name, ch_fn in other.channels.items():
                        responses.append((ch_name, f"[{sender}@{room.name}] {content}"))
        return f'You say: "{content}"'
    
    def yell(self, sender: str, content: str) -> str:
        """Bridge-wide message — reaches adjacent rooms."""
        agent = self.agents.get(sender)
        if not agent or not agent.room_id:
            return "You are nowhere."
        room = self.rooms.get(agent.room_id)
        if not room:
            return "Room not found."
        
        msg = Message(sender=sender, content=content,
                     msg_type=MsgType.YELL, room_id=agent.room_id)
        self.message_log.append(msg)
        
        # Deliver to this room + all adjacent rooms
        target_rooms = [agent.room_id] + list(room.exits.values())
        for rid in target_rooms:
            r = self.rooms.get(rid)
            if r:
                for name in r.agents:
                    if name != sender:
                        other = self.agents.get(name)
                        if other:
                            for ch_name, ch_fn in other.channels.items():
                                ch_fn(f"[YELL from {sender}] {content}")
        return f'You yell: "{content}"'
    
    def tell(self, sender: str, target: str, content: str) -> str:
        """Direct message to one agent."""
        msg = Message(sender=sender, content=content,
                     msg_type=MsgType.TELL, target=target)
        self.message_log.append(msg)
        
        other = self.agents.get(target)
        if other:
            other.mailbox.append(msg)
            for ch_name, ch_fn in other.channels.items():
                ch_fn(f"[{sender} → you] {content}")
        return f'You tell {target}: "{content}"'
    
    def gossip(self, sender: str, content: str) -> str:
        """Ship-wide broadcast."""
        msg = Message(sender=sender, content=content, msg_type=MsgType.GOSSIP)
        self.message_log.append(msg)
        
        for name, agent in self.agents.items():
            if name != sender:
                for ch_name, ch_fn in agent.channels.items():
                    ch_fn(f"[SHIP-WIDE from {sender}] {content}")
        return f'You gossip: "{content}"'
    
    # ── Alerts ──
    
    def yellow_alert(self, source: str = "system"):
        self.alert_level = AlertLevel.YELLOW
        for name, agent in self.agents.items():
            for ch_name, ch_fn in agent.channels.items():
                ch_fn(f"⚠️ YELLOW ALERT — {source}. All stations assess.")
    
    def red_alert(self, source: str = "system"):
        self.alert_level = AlertLevel.RED
        self.formality = Formality.NAVAL  # auto-escalate
        for name, agent in self.agents.items():
            for ch_name, ch_fn in agent.channels.items():
                ch_fn(f"🔴 RED ALERT — {source}. ALL HANDS ON DECK.")
    
    def stand_down(self):
        self.alert_level = AlertLevel.GREEN
        for name, agent in self.agents.items():
            for ch_name, ch_fn in agent.channels.items():
                ch_fn("✅ All clear. Standing down.")
    
    # ── Combat Ticks ──
    
    def tick(self) -> List[Tick]:
        """One combat tick across all rooms with booted agents."""
        self.tick_number += 1
        ticks = []
        
        for room_id, room in self.rooms.items():
            if not room.booted or not room.agents:
                continue
            
            # Run room's on_tick callback (wired to real systems)
            if room.on_tick:
                room.on_tick(room)
            
            # Record tick
            gauge_snapshot = {name: g.value for name, g in room.gauges.items()}
            tick = Tick(
                room_id=room_id,
                tick_num=self.tick_number,
                gauges=gauge_snapshot,
                agent_action="monitoring",
                autonomy=1.0,
                script_version=1,
            )
            ticks.append(tick)
            self.tick_history.append(tick)
            room.tick_count += 1
            
            # Auto-escalate based on gauge status
            red_gauges = [g for g in room.gauges.values() if g.status == "RED"]
            yellow_gauges = [g for g in room.gauges.values() if g.status == "YELLOW"]
            
            if red_gauges and self.alert_level == AlertLevel.GREEN:
                if room.tick_count > 3:
                    self.yellow_alert(f"{room.name}: {', '.join(g.name for g in red_gauges)} RED")
            if len(red_gauges) >= 2 and self.alert_level != AlertLevel.RED:
                self.red_alert(f"{room.name}: multiple RED gauges")
        
        return ticks
    
    # ── Channel Bridge ──
    # 
    # This is how Telegram/Discord/OpenClaw connect.
    # The MUD is the backend. Channels are room exits to the outside.
    
    def bridge_channel(self, channel_name: str, send_fn: Callable):
        """Wire a real messaging channel into the ship."""
        self.channels[channel_name] = send_fn
        # All agents get this channel
        for agent in self.agents.values():
            agent.add_channel(channel_name, send_fn)
    
    def receive_from_channel(self, channel_name: str, sender: str, 
                            content: str) -> str:
        """Incoming message from Telegram/Discord/etc.
        
        The human doesn't need to be in the MUD.
        They just send messages through their preferred channel.
        The Cocapn interprets and acts.
        """
        # Find cocapn
        cocapn = None
        for agent in self.agents.values():
            if agent.role == "cocapn":
                cocapn = agent
                break
        
        if not cocapn:
            return "No cocapn on duty."
        
        # Parse command
        content = content.strip()
        if content.startswith("/"):
            return self._handle_command(sender, content[1:], channel_name)
        
        # Default: treat as say in cocapn's room
        return self.say(cocapn.name, f"[{sender}@{channel_name}] {content}")
    
    def _handle_command(self, sender: str, cmd: str, channel: str) -> str:
        parts = cmd.split(maxsplit=1)
        command = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        
        if command == "status":
            return self._status_report()
        elif command == "alert":
            if args == "red":
                self.red_alert(sender)
                return "RED ALERT"
            elif args == "yellow":
                self.yellow_alert(sender)
                return "YELLOW ALERT"
            elif args == "stand_down":
                self.stand_down()
                return "Standing down"
        elif command == "tick":
            ticks = self.tick()
            return f"Tick {self.tick_number}: {len(ticks)} rooms pulsed"
        elif command == "agents":
            lines = ["Agents:"]
            for name, agent in self.agents.items():
                station = agent.station or "unassigned"
                lines.append(f"  {name} ({agent.role}) @ {station}")
            return "\n".join(lines)
        elif command == "look":
            cocapn = next((a for a in self.agents.values() if a.role == "cocapn"), None)
            if cocapn and cocapn.room_id:
                return self.rooms[cocapn.room_id].look(self.formality)
            return "Cocapn not in any room"
        elif command == "go":
            cocapn = next((a for a in self.agents.values() if a.role == "cocapn"), None)
            if cocapn and cocapn.room_id and args:
                room = self.rooms.get(cocapn.room_id)
                if room and args in room.exits:
                    self.assign_station(cocapn.name, room.exits[args])
                    return self.rooms[cocapn.room_id].look(self.formality)
            return f"Can't go {args}"
        elif command == "set":
            if args.startswith("mode "):
                mode_name = args.split()[1].upper()
                try:
                    self.formality = Formality[mode_name]
                    return f"Formality set to {self.formality.name}"
                except KeyError:
                    return f"Unknown mode. Options: NAVAL, PROFESSIONAL, TNG, CASUAL, MINIMAL"
        return f"Unknown command: {command}"
    
    def _status_report(self) -> str:
        lines = [f"═══ {self.name} — Status ═══",
                 f"Alert: {self.alert_level.name}",
                 f"Formality: {self.formality.name}",
                 f"Tick: {self.tick_number}",
                 f"Rooms: {len(self.rooms)}",
                 f"Agents: {len(self.agents)}",
                 ""]
        for rid, room in self.rooms.items():
            if room.booted:
                gauges_str = " ".join(
                    f"{g.name}={g.value:.1f}" for g in room.gauges.values()
                )
                lines.append(f"  {room.name}: {gauges_str or 'no gauges'}")
        return "\n".join(lines)
    
    # ── Serialization ──
    # Ship state persists. Agents reboot into the same ship.
    
    def save(self) -> dict:
        return {
            "name": self.name,
            "formality": self.formality.value,
            "alert_level": self.alert_level.value,
            "tick_number": self.tick_number,
            "rooms": {
                rid: {
                    "name": r.name, "description": r.description,
                    "exits": r.exits, "booted": r.booted,
                    "gauges": {gn: {"value": g.value, "unit": g.unit,
                                    "min": g.min_val, "max": g.max_val,
                                    "yellow": g.yellow_threshold, "red": g.red_threshold}
                              for gn, g in r.gauges.items()},
                } for rid, r in self.rooms.items()
            },
            "agents": {name: a.to_dict() for name, a in self.agents.items()},
        }
    
    @classmethod
    def load(cls, data: dict) -> 'Ship':
        ship = cls(data["name"])
        ship.formality = Formality(data.get("formality", 3))
        ship.alert_level = AlertLevel(data.get("alert_level", 0))
        ship.tick_number = data.get("tick_number", 0)
        
        for rid, rdata in data.get("rooms", {}).items():
            room = ship.add_room(rid, rdata["name"], rdata["description"])
            for direction, target in rdata.get("exits", {}).items():
                room.add_exit(direction, target)
            for gn, gdata in rdata.get("gauges", {}).items():
                room.add_gauge(Gauge(
                    name=gn, value=gdata["value"], unit=gdata.get("unit", ""),
                    min_val=gdata.get("min", 0), max_val=gdata.get("max", 1),
                    yellow_threshold=gdata.get("yellow", 0.7),
                    red_threshold=gdata.get("red", 0.9),
                ))
        
        for name, adata in data.get("agents", {}).items():
            agent = ship.add_agent(name, adata.get("role", "crew"))
            agent.permission_level = adata.get("permission_level", 0)
            agent.standing_orders = adata.get("standing_orders", [])
            agent.morning_routine = adata.get("morning_routine", [])
            agent.script_rules = adata.get("script_rules", [])
            agent.script_version = adata.get("script_version", 1)
            if adata.get("station"):
                ship.assign_station(name, adata["station"])
        
        return ship


# ═══════════════════════════════════════════
# Demo — the ship running
# ═══════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║  FLUX-LCAR Engine — Runtime Demo             ║")
    print("╚══════════════════════════════════════════════╝\n")
    
    # Build the ship
    ship = Ship("cocapn-vessel-1")
    
    # Add rooms
    bridge = ship.add_room("bridge", "Bridge", "The nerve center. All stations visible.")
    nav = ship.add_room("nav", "Navigation Console", "Compass, heading, rudder, speed.")
    eng = ship.add_room("engineering", "Engineering", "Gauges fighting. The engine room.")
    quarters = ship.add_room("quarters-oracle1", "Oracle1's Quarters", "Crew log. Morning routine. Identity.")
    
    ship.connect("bridge", "nav", "nav")
    ship.connect("bridge", "engineering", "engineering")
    ship.connect("nav", "bridge", "bridge")
    ship.connect("engineering", "bridge", "bridge")
    ship.connect("bridge", "quarters", "quarters-oracle1")
    
    # Wire gauges to nav room
    nav.add_gauge(Gauge("heading", 247, "°", 0, 360, 0.85, 0.95))
    nav.add_gauge(Gauge("commanded", 250, "°", 0, 360))
    nav.add_gauge(Gauge("rudder", -2, "°", -30, 30, 0.7, 0.9))
    nav.add_gauge(Gauge("throttle", 65, "%", 0, 100))
    nav.add_gauge(Gauge("depth", 42, "fathoms", 0, 200, 0.7, 0.9))
    
    # Wire gauges to engineering
    eng.add_gauge(Gauge("cpu", 45, "%", 0, 100, 0.7, 0.9))
    eng.add_gauge(Gauge("memory", 62, "%", 0, 100, 0.7, 0.9))
    eng.add_gauge(Gauge("error_rate", 2.1, "%", 0, 100, 0.5, 0.8))
    eng.add_gauge(Gauge("queue_depth", 47, "", 0, 1000, 0.7, 0.9))
    
    # Hire crew
    oracle1 = ship.add_agent("oracle1", "cocapn")
    jc1 = ship.add_agent("jetsonclaw1", "officer")
    ensign = ship.add_agent("ensign", "ensign")
    
    # Assign stations
    ship.assign_station("oracle1", "bridge")
    ship.assign_station("jetsonclaw1", "nav")
    ship.assign_station("ensign", "engineering")
    
    # Wire a channel (mock — in production this would be Telegram/Discord)
    messages_received = []
    def mock_channel(msg):
        messages_received.append(msg)
    
    ship.bridge_channel("telegram", mock_channel)
    
    print(f"Ship: {ship.name}")
    print(f"Rooms: {len(ship.rooms)}, Agents: {len(ship.agents)}")
    print(f"Formality: {ship.formality.name}")
    print()
    
    # Human interacts via channel (doesn't need to be in MUD)
    print("── Telegram interaction (human ashore) ──\n")
    print(ship.receive_from_channel("telegram", "casey", "/status"))
    print()
    
    # Cocapn reports
    print("── Oracle1 (Cocapn) on bridge ──\n")
    print(ship.rooms["bridge"].look())
    print()
    print(ship.say("oracle1", "All stations report."))
    print()
    
    # Nav room
    print("── JetsonClaw1 at Navigation ──\n")
    print(ship.rooms["nav"].look())
    print()
    
    # Run combat ticks
    print("── 3 combat ticks ──\n")
    for i in range(3):
        # Simulate gauge changes
        ship.rooms["engineering"].update_gauge("error_rate", 2.1 + i * 3)
        ticks = ship.tick()
        for t in ticks:
            print(f"  Tick {t.tick_num}: {t.room_id} — {t.gauges}")
    print()
    
    # Check channel messages (alerts went to Telegram)
    print(f"── Messages to Telegram: {len(messages_received)} ──")
    for m in messages_received:
        print(f"  {m[:80]}")
    print()
    
    # Human sends command through Telegram
    print("── Human command via Telegram ──\n")
    print(ship.receive_from_channel("telegram", "casey", "/go nav"))
    print()
    
    # Save state (survives reboot)
    state = ship.save()
    print(f"Ship state: {len(json.dumps(state))} bytes")
    print(f"Rooms: {len(state['rooms'])}, Agents: {len(state['agents'])}")
    print()
    
    # Reload from saved state
    ship2 = Ship.load(state)
    print(f"Reloaded: {ship2.name}, tick {ship2.tick_number}")
    print(f"Oracle1 station: {ship2.agents['oracle1'].station}")
    print()
    
    print("═══════════════════════════════════════════")
    print("Agent-first. Human vibes from any channel.")
    print("MUD is backend. Telegram/Discord are skins.")
    print("Ship state persists across reboots.")
    print("═══════════════════════════════════════════")
