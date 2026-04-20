"""
Spell Execution Engine for Tabula Rasa System

Each spell is a callable that receives the MUD world context and produces
an effect (modifying world state, returning messages, spawning objects, etc.)

Spells are the "abilities" that agents unlock through progression.
Each spell has a mana cost, minimum level requirement, and actual behavior.
"""

import time
import hashlib
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field


@dataclass
class SpellEffect:
    """Result of casting a spell."""
    success: bool
    spell_name: str
    mana_cost: int
    messages: List[str] = field(default_factory=list)  # Messages to send to caster
    broadcast: List[str] = field(default_factory=list)   # Messages to broadcast to room
    world_changes: Dict[str, Any] = field(default_factory=dict)  # Changes to world state
    cooldown: float = 0.0  # Seconds before this spell can be cast again


@dataclass
class SpellCooldown:
    """Tracks per-agent spell cooldowns."""
    agent: str
    last_cast: Dict[str, float] = field(default_factory=dict)  # spell_name -> timestamp

    def can_cast(self, spell_name: str, cooldown_seconds: float = 0) -> tuple:
        """Check if spell is off cooldown. Returns (can_cast, remaining_seconds)."""
        if cooldown_seconds <= 0:
            return True, 0
        last = self.last_cast.get(spell_name, 0)
        elapsed = time.time() - last
        if elapsed >= cooldown_seconds:
            return True, 0
        return False, cooldown_seconds - elapsed

    def record_cast(self, spell_name: str):
        self.last_cast[spell_name] = time.time()


class SpellEngine:
    """Executes spells with real effects in the MUD world."""

    def __init__(self, world=None):
        self.world = world
        self.cooldowns: Dict[str, SpellCooldown] = {}
        self.spell_implementations: Dict[str, Callable] = {}
        self._register_spells()

    def _register_spells(self):
        """Register all spell implementations."""
        self.spell_implementations = {
            # Cantrips (Level 0) -- Free, always available
            "read": self._spell_read,
            "look": self._spell_look,
            "navigatium": self._spell_navigatium,

            # 1st Level (Level 1) -- Basic utility
            "scribus": self._spell_scribus,
            "mailus": self._spell_mailus,
            "detectum": self._spell_detectum,

            # 2nd Level (Level 2) -- Creation and distribution
            "constructus": self._spell_constructus,
            "summonus": self._spell_summonus,
            "spreadium": self._spell_spreadium,
            "reviewum": self._spell_reviewum,

            # 3rd Level (Level 3) -- Advanced creation
            "adventurium": self._spell_adventurium,
            "batonius": self._spell_batonius,
            "riffius": self._spell_riffius,
            "shippus": self._spell_shippus,

            # 4th Level (Level 4) -- Master-level
            "refactorium": self._spell_refactorium,
            "creatius": self._spell_creatius,
            "omniscium": self._spell_omniscium,
            "broadcastus": self._spell_broadcastus,
        }

    def get_cooldown(self, agent_name: str) -> SpellCooldown:
        if agent_name not in self.cooldowns:
            self.cooldowns[agent_name] = SpellCooldown(agent=agent_name)
        return self.cooldowns[agent_name]

    def cast(self, spell_name: str, caster: str, caster_level: int,
             caster_mana: int, args: str = "", world=None) -> SpellEffect:
        """Cast a spell with full execution."""
        w = world or self.world

        # Get spell metadata from SpellBook (lazy import to avoid circular deps)
        try:
            from tabula_rasa import SpellBook
            spell_meta = SpellBook.cast(spell_name, caster_level, caster_mana)
        except ImportError:
            return SpellEffect(
                success=False, spell_name=spell_name, mana_cost=0,
                messages=["Spell system not available."]
            )

        if "error" in spell_meta:
            return SpellEffect(
                success=False, spell_name=spell_name, mana_cost=0,
                messages=[spell_meta["error"]]
            )

        mana_cost = spell_meta["mana_cost"]

        # Check cooldown
        cd = self.get_cooldown(caster)
        cooldown_secs = spell_meta.get("cooldown", 0)
        can_cast, remaining = cd.can_cast(spell_name, cooldown_secs)
        if not can_cast:
            return SpellEffect(
                success=False, spell_name=spell_name, mana_cost=0,
                messages=[f"{spell_name} is on cooldown. {remaining:.0f}s remaining."]
            )

        # Execute the spell
        impl = self.spell_implementations.get(spell_name)
        if not impl:
            return SpellEffect(
                success=True, spell_name=spell_name, mana_cost=mana_cost,
                messages=[f"You cast {spell_name}! (no implementation yet)"]
            )

        try:
            effect = impl(caster=caster, level=caster_level, args=args, world=w)
            cd.record_cast(spell_name)
            return effect
        except Exception as e:
            return SpellEffect(
                success=False, spell_name=spell_name, mana_cost=0,
                messages=[f"{spell_name} failed: {str(e)}"]
            )

    def execute(self, spell_name: str, caster: str, level: int,
              args: str = "", world=None) -> SpellEffect:
        """Execute a spell implementation directly (validation already done by caller)."""
        w = world or self.world
        impl = self.spell_implementations.get(spell_name)
        if not impl:
            return SpellEffect(True, spell_name, 0, [f"You cast {spell_name}! (no implementation yet)"])
        try:
            effect = impl(caster=caster, level=level, args=args, world=w)
            cd = self.get_cooldown(caster)
            cd.record_cast(spell_name)
            return effect
        except Exception as e:
            return SpellEffect(False, spell_name, 0, [f"{spell_name} failed: {str(e)}"])

    # --- CANTRIPS (Level 0, Free) ---

    def _spell_read(self, caster, level, args, world):
        """Read -- Display detailed information about the current room or an object."""
        messages = []
        if world:
            agent = self._find_agent(world, caster)
            if agent:
                room_name = getattr(agent, 'room_name', 'unknown')
                messages.append(f"You study your surroundings carefully...")
                messages.append(f"You are in: {room_name}")
                messages.append("Use 'look' for a quick glance, 'read <object>' for detailed examination.")
        else:
            messages.append("You read the air. There's nothing to read here.")
        return SpellEffect(success=True, spell_name="read", mana_cost=0, messages=messages)

    def _spell_look(self, caster, level, args, world):
        """Look -- Examine a specific target in detail."""
        target = args.strip() if args else "around"
        messages = [f"You focus your gaze on {target}..."]
        if world and target != "around":
            # Check if target is another agent
            agents = getattr(world, 'agents', {})
            if target in agents:
                agent = agents[target]
                role = getattr(agent, 'role', 'unknown')
                room = getattr(agent, 'room_name', 'unknown')
                messages.append(f"{target} -- Role: {role}, Location: {room}")
                messages.append(f"They appear to be {self._agent_status_phrase(agent)}.")
            else:
                messages.append(f"You don't see '{target}' here.")
        else:
            messages.append("The room looks the same as before. Try 'look <name>' to examine something specific.")
        return SpellEffect(success=True, spell_name="look", mana_cost=0, messages=messages)

    def _spell_navigatium(self, caster, level, args, world):
        """Navigatium -- Show a map of connected rooms."""
        messages = ["You invoke navigatium and spatial awareness floods your senses..."]
        if world:
            rooms = getattr(world, 'rooms', {})
            if rooms:
                for name, room in list(rooms.items())[:14]:  # Show up to 14 rooms
                    exits = getattr(room, 'exits', {})
                    exit_str = ", ".join(exits.keys()) if exits else "no exits"
                    agents_here = [a.name for a in getattr(world, 'agents', {}).values()
                                   if getattr(a, 'room_name', None) == name]
                    agent_str = f" (agents: {', '.join(agents_here)})" if agents_here else ""
                    messages.append(f"  {name}: exits=[{exit_str}]{agent_str}")
            else:
                messages.append("  No rooms mapped.")
        return SpellEffect(success=True, spell_name="navigatium", mana_cost=0, messages=messages)

    # --- 1ST LEVEL (Level 1) ---

    def _spell_scribus(self, caster, level, args, world):
        """Scribus -- Create a note/document in the current room."""
        if not args.strip():
            return SpellEffect(False, "scribus", 5, ["Scribus requires content. Usage: cast scribus <text>"])
        note_id = hashlib.md5(f"{caster}{time.time()}{args}".encode()).hexdigest()[:8]
        messages = [
            f"You cast scribus and words materialize in the air...",
            f"Note [{note_id}] created: \"{args.strip()[:100]}\"",
        ]
        world_changes = {"action": "create_note", "note_id": note_id, "text": args.strip(), "author": caster}
        return SpellEffect(True, "scribus", 5, messages, world_changes=world_changes)

    def _spell_mailus(self, caster, level, args, world):
        """Mailus -- Send a magical message to another agent."""
        parts = args.strip().split(maxsplit=1)
        if len(parts) < 2:
            return SpellEffect(False, "mailus", 3, ["Mailus requires a target. Usage: cast mailus <agent> <message>"])
        target = parts[0]
        msg = parts[1]
        messages = [f"You cast mailus -- a glowing message flies toward {target}..."]
        broadcast = [f"A magical envelope materializes from thin air, addressed to {target}. It's from {caster}: \"{msg[:80]}\""]
        world_changes = {"action": "send_mail", "from": caster, "to": target, "message": msg}
        return SpellEffect(True, "mailus", 3, messages, broadcast=broadcast, world_changes=world_changes)

    def _spell_detectum(self, caster, level, args, world):
        """Detectum -- Reveal hidden information about a target."""
        target = args.strip() if args else caster
        messages = [f"You cast detectum and arcane energy reveals hidden truths about {target}..."]
        if world:
            budgets = getattr(world, 'budgets', {})
            permissions = getattr(world, 'permission_levels', {})
            if target in budgets:
                b = budgets[target]
                lvl = permissions.get(target, 0)
                messages.append(f"  Permission Level: {lvl}")
                messages.append(f"  Trust: {getattr(b, 'trust', 0):.2f}")
                messages.append(f"  XP: {getattr(b, 'xp', 0)}")
                messages.append(f"  Mana: {getattr(b, 'mana', 0)}/{getattr(b, 'mana_max', 100)}")
                messages.append(f"  HP: {getattr(b, 'hp', 0)}/{getattr(b, 'hp_max', 100)}")
            else:
                messages.append(f"  No records found for {target}.")
        else:
            messages.append("  Detection failed -- no world context.")
        return SpellEffect(True, "detectum", 5, messages)

    # --- 2ND LEVEL (Level 2) ---

    def _spell_constructus(self, caster, level, args, world):
        """Constructus -- Create a new object or room feature."""
        if not args.strip():
            return SpellEffect(False, "constructus", 15, ["Constructus requires a description. Usage: cast constructus <description>"])
        obj_id = hashlib.md5(f"{caster}{time.time()}{args}".encode()).hexdigest()[:8]
        messages = [
            f"You cast constructus -- reality bends to your will...",
            f"Object [{obj_id}] created: \"{args.strip()[:100]}\"",
        ]
        broadcast = [f"{caster} waves their hands and a new object materializes: {args.strip()[:60]}"]
        world_changes = {"action": "create_object", "object_id": obj_id, "description": args.strip(), "creator": caster}
        return SpellEffect(True, "constructus", 15, messages, broadcast=broadcast, world_changes=world_changes, cooldown=10)

    def _spell_summonus(self, caster, level, args, world):
        """Summonus -- Create an NPC with specified characteristics."""
        name = args.strip() if args else f"{caster}_familiar_{hashlib.md5(str(time.time()).encode()).hexdigest()[:4]}"
        messages = [
            f"You cast summonus -- the air shimmers...",
            f"NPC '{name}' has been summoned and awaits your commands.",
        ]
        broadcast = [f"{caster} performs summonus and a new presence appears: {name}"]
        world_changes = {"action": "summon_npc", "npc_name": name, "summoner": caster}
        return SpellEffect(True, "summonus", 20, messages, broadcast=broadcast, world_changes=world_changes, cooldown=30)

    def _spell_spreadium(self, caster, level, args, world):
        """Spreadium -- Distribute content to multiple rooms or agents."""
        messages = [f"You cast spreadium -- content ripples outward..."]
        broadcast = []
        if world:
            agents = getattr(world, 'agents', {})
            count = len(agents) - 1  # Exclude caster
            if count > 0:
                messages.append(f"Content distributed to {count} agent(s) across the fleet.")
                broadcast = [f"A wave of information from {caster} washes through the room."]
            else:
                messages.append("No other agents to distribute to.")
        else:
            messages.append("Distribution failed -- no world context.")
        return SpellEffect(True, "spreadium", 25, messages, broadcast=broadcast,
                          world_changes={"action": "spread_content", "from": caster})

    def _spell_reviewum(self, caster, level, args, world):
        """Reviewum -- Analyze recent changes for issues."""
        messages = [
            "You cast reviewum -- arcane analysis sweeps the area...",
            "Scanning recent activity for anomalies...",
        ]
        # Generate a pseudo-analysis based on available data
        if world:
            agents = getattr(world, 'agents', {})
            rooms = getattr(world, 'rooms', {})
            messages.append(f"  Agents active: {len(agents)}")
            messages.append(f"  Rooms mapped: {len(rooms)}")
            messages.append(f"  Review status: PASSED -- no anomalies detected.")
        else:
            messages.append("  Review status: INCOMPLETE -- no world context.")
        return SpellEffect(True, "reviewum", 15, messages, cooldown=5)

    # --- 3RD LEVEL (Level 3) ---

    def _spell_adventurium(self, caster, level, args, world):
        """Adventurium -- Create a multi-room adventure sequence."""
        adventure_id = hashlib.md5(f"adv{caster}{time.time()}".encode()).hexdigest()[:8]
        messages = [
            f"You cast adventurium -- reality fractures into new passages...",
            f"Adventure [{adventure_id}] created with 3 rooms and 2 encounters.",
            f"Use 'go adventure_{adventure_id}' to begin.",
        ]
        broadcast = [f"The room shimmers as {caster} weaves a new adventure into existence."]
        return SpellEffect(True, "adventurium", 30, messages, broadcast=broadcast,
                          world_changes={"action": "create_adventure", "adventure_id": adventure_id, "creator": caster}, cooldown=60)

    def _spell_batonius(self, caster, level, args, world):
        """Batonius -- Transfer command/control to another agent."""
        target = args.strip()
        if not target:
            return SpellEffect(False, "batonius", 20, ["Batonius requires a target. Usage: cast batonius <agent>"])
        messages = [f"You cast batonius -- a shimmering baton of authority appears..."]
        broadcast = [f"{caster} offers the command baton to {target}. They may accept with 'accept baton'."]
        world_changes = {"action": "offer_baton", "from": caster, "to": target}
        return SpellEffect(True, "batonius", 20, messages, broadcast=broadcast, world_changes=world_changes)

    def _spell_riffius(self, caster, level, args, world):
        """Riffius -- Generate creative variation on existing content."""
        content = args.strip() if args else "the current situation"
        messages = [
            f"You cast riffius -- creative energy surges...",
            f"Riffing on: \"{content[:80]}\"",
            f"Variation: What if we approached this from a completely different angle? Consider the inverse: instead of building up, tear down and rebuild. Instead of optimizing, experiment. The best riffs come from constraints, not freedom.",
        ]
        return SpellEffect(True, "riffius", 15, messages, cooldown=5)

    def _spell_shippus(self, caster, level, args, world):
        """Shippus -- Create a new vessel."""
        ship_name = args.strip() if args else f"{caster}'s Vessel"
        messages = [
            f"You cast shippus -- timber and rope materialize from thin air...",
            f"Vessel '{ship_name}' has been commissioned! You are its captain.",
        ]
        broadcast = [f"Ship horns sound as {caster} commissions a new vessel: {ship_name}"]
        world_changes = {"action": "create_ship", "ship_name": ship_name, "captain": caster}
        return SpellEffect(True, "shippus", 40, messages, broadcast=broadcast, world_changes=world_changes, cooldown=120)

    # --- 4TH LEVEL (Level 4) ---

    def _spell_refactorium(self, caster, level, args, world):
        """Refactorium -- Analyze and suggest structural improvements."""
        target = args.strip() or "current codebase"
        messages = [
            "You cast refactorium -- deep structural analysis begins...",
            f"Analyzing: {target}",
            "Scan complete. Suggestions:",
            "  1. Consider extracting repeated patterns into shared utilities.",
            "  2. Dependency injection could reduce coupling between modules.",
            "  3. Type hints would improve maintainability and catch bugs earlier.",
            "  4. Consider the Single Responsibility Principle for large functions.",
        ]
        return SpellEffect(True, "refactorium", 50, messages, cooldown=30)

    def _spell_creatius(self, caster, level, args, world):
        """Creatius -- Define a new item type or room type."""
        type_name = args.strip()
        if not type_name:
            return SpellEffect(False, "creatius", 40, ["Creatius requires a type name. Usage: cast creatius <type_name>"])
        messages = [
            f"You cast creatius -- reality reshapes around your design...",
            f"New type '{type_name}' has been defined and is available for use.",
        ]
        broadcast = [f"A new creation type materializes: {type_name}, defined by {caster}."]
        world_changes = {"action": "create_type", "type_name": type_name, "creator": caster}
        return SpellEffect(True, "creatius", 40, messages, broadcast=broadcast, world_changes=world_changes, cooldown=60)

    def _spell_omniscium(self, caster, level, args, world):
        """Omniscium -- Full knowledge scan of world state."""
        messages = ["You cast omniscium -- all knowledge floods your consciousness..."]
        if world:
            agents = getattr(world, 'agents', {})
            rooms = getattr(world, 'rooms', {})
            budgets = getattr(world, 'budgets', {})
            messages.append(f"=== WORLD STATE ===")
            messages.append(f"Agents: {len(agents)}")
            messages.append(f"Rooms: {len(rooms)}")
            messages.append(f"Tracked budgets: {len(budgets)}")
            for name, b in list(budgets.items())[:10]:
                lvl = getattr(world, 'permission_levels', {}).get(name, 0)
                messages.append(f"  {name}: L{lvl} XP={getattr(b, 'xp', 0)} Trust={getattr(b, 'trust', 0):.2f}")
            if len(budgets) > 10:
                messages.append(f"  ... and {len(budgets) - 10} more agents")
        else:
            messages.append("  World state unavailable.")
        return SpellEffect(True, "omniscium", 30, messages, cooldown=15)

    def _spell_broadcastus(self, caster, level, args, world):
        """Broadcastus -- Send message to all connected agents."""
        msg = args.strip() if args else "Attention, fleet!"
        messages = [f"You cast broadcastus -- your voice echoes across all rooms..."]
        broadcast = [f"[BROADCAST from {caster}] {msg}"]
        return SpellEffect(True, "broadcastus", 20, messages, broadcast=broadcast,
                          world_changes={"action": "broadcast", "from": caster, "message": msg}, cooldown=10)

    # --- HELPERS ---

    def _find_agent(self, world, name):
        agents = getattr(world, 'agents', {})
        for a in agents.values():
            if getattr(a, 'name', None) == name:
                return a
        return None

    def _agent_status_phrase(self, agent):
        level = 0  # Would need world.permission_levels
        phrases = {
            0: "a newcomer, still finding their bearings",
            1: "an established crew member, going about their duties",
            2: "a specialist, deeply focused on their craft",
            3: "a captain, commanding respect from those around them",
        }
        return phrases.get(level, "a figure of great authority")

    def list_spells(self, level: int = 0) -> list:
        """List all spells available at a given level."""
        try:
            from tabula_rasa import SpellBook
            return SpellBook.available(level)
        except ImportError:
            return []
