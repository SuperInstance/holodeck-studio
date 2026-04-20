"""
Room Command Execution Engine

Turns static ToolRoom command definitions into live, executable functions.
Each room template can register command handlers that receive world context
and produce real effects.
"""

import time
import hashlib
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field


@dataclass
class RoomCommandResult:
    """Result of executing a room command."""
    success: bool
    command: str
    room_id: str
    output: str
    mana_cost: int = 0
    world_changes: Dict[str, Any] = field(default_factory=dict)
    private_output: str = ""  # Only visible to the executing agent


@dataclass
class RoomCommand:
    """A registered room command with handler function."""
    name: str
    description: str
    mana_cost: int = 0
    min_level: int = 0
    handler: Callable = None
    aliases: List[str] = field(default_factory=list)
    cooldown: float = 0.0  # Per-room cooldown in seconds


class RoomEngine:
    """Executes commands within ToolRoom contexts."""

    def __init__(self, world=None):
        self.world = world
        self._builtin_handlers: Dict[str, Callable] = {}
        self._custom_handlers: Dict[str, Dict[str, RoomCommand]] = {}
        self._room_cooldowns: Dict[str, float] = {}  # "room_id:command" -> timestamp
        self._register_builtins()

    def _register_builtins(self):
        """Register built-in room command handlers."""
        self._builtin_handlers = {
            "murmur": self._cmd_murmur,
            "search": self._cmd_search,
            "browse": self._cmd_browse,
            "export": self._cmd_export,
            "spread": self._cmd_spread,
            "synthesize": self._cmd_synthesize,
            "debate": self._cmd_debate,
            "watch": self._cmd_watch,
            "alert": self._cmd_alert,
            "summary": self._cmd_summary,
            "history": self._cmd_history,
            "research": self._cmd_research,
            "summarize": self._cmd_summarize,
            "compare": self._cmd_compare,
            "read_cell": self._cmd_read_cell,
            "write_cell": self._cmd_write_cell,
            "formula": self._cmd_formula,
            "dashboard": self._cmd_dashboard,
            "sessions": self._cmd_sessions,
            "intervene": self._cmd_intervene,
            "shell": self._cmd_shell,
            "train": self._cmd_train,
            "practice": self._cmd_practice,
            "test": self._cmd_test,
            "certify": self._cmd_certify,
            "commission": self._cmd_commission,
            "inspect": self._cmd_inspect,
            "decommission": self._cmd_decommission,
        }

    def register_command(self, room_id: str, command: RoomCommand):
        """Register a custom command for a specific room."""
        if room_id not in self._custom_handlers:
            self._custom_handlers[room_id] = {}
        self._custom_handlers[room_id][command.name] = command
        for alias in command.aliases:
            self._custom_handlers[room_id][alias] = command

    def execute(self, room_id: str, command_name: str, agent_name: str,
                agent_level: int, args: str = "", world=None) -> RoomCommandResult:
        """Execute a command in a room context."""
        w = world or self.world

        # Check cooldown
        cd_key = f"{room_id}:{command_name}"
        cmd = self._get_command(room_id, command_name)
        if cmd and cmd.cooldown > 0:
            if cd_key in self._room_cooldowns:
                elapsed = time.time() - self._room_cooldowns[cd_key]
                if elapsed < cmd.cooldown:
                    remaining = cmd.cooldown - elapsed
                    return RoomCommandResult(
                        success=False, command=command_name, room_id=room_id,
                        output=f"Command on cooldown. {remaining:.0f}s remaining."
                    )

        # Find handler
        handler = self._get_handler(room_id, command_name)
        if not handler:
            return RoomCommandResult(
                success=False, command=command_name, room_id=room_id,
                output=f"Unknown command: {command_name}. Type 'commands' for available commands."
            )

        # Check level requirement
        min_lvl = cmd.min_level if cmd else 0
        if agent_level < min_lvl:
            return RoomCommandResult(
                success=False, command=command_name, room_id=room_id,
                output=f"Permission denied. {command_name} requires level {min_lvl}."
            )

        # Execute
        try:
            result = handler(room_id=room_id, agent=agent_name, level=agent_level,
                             args=args, world=w)
            if isinstance(result, str):
                result = RoomCommandResult(
                    success=True, command=command_name, room_id=room_id,
                    output=result, mana_cost=cmd.mana_cost if cmd else 0
                )
            if result.success:
                self._room_cooldowns[cd_key] = time.time()
            return result
        except Exception as e:
            return RoomCommandResult(
                success=False, command=command_name, room_id=room_id,
                output=f"Command failed: {str(e)}"
            )

    def _get_handler(self, room_id: str, command_name: str) -> Optional[Callable]:
        """Get handler for a command in a room."""
        # Check custom handlers first
        if room_id in self._custom_handlers:
            cmd = self._custom_handlers[room_id].get(command_name)
            if cmd and cmd.handler:
                return cmd.handler
        # Fall back to builtins
        return self._builtin_handlers.get(command_name)

    def _get_command(self, room_id: str, command_name: str) -> Optional[RoomCommand]:
        if room_id in self._custom_handlers:
            return self._custom_handlers[room_id].get(command_name)
        return None

    def list_commands(self, room_id: str, agent_level: int = 0) -> List[dict]:
        """List available commands for a room."""
        commands = []
        seen = set()

        # Built-in commands
        for name, handler in self._builtin_handlers.items():
            if name not in seen:
                commands.append({"name": name, "source": "builtin", "available": True})
                seen.add(name)

        # Custom commands
        if room_id in self._custom_handlers:
            for name, cmd in self._custom_handlers[room_id].items():
                if name not in seen:
                    commands.append({
                        "name": name,
                        "source": "custom",
                        "available": cmd.min_level <= agent_level,
                        "min_level": cmd.min_level,
                        "mana_cost": cmd.mana_cost,
                        "description": cmd.description,
                    })
                    seen.add(name)

        return commands

    # --- BUILT-IN COMMAND IMPLEMENTATIONS ---

    def _cmd_murmur(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "murmur", room_id,
            f"You murmur into the chamber: \"{(args or '...')[:100]}\". The walls seem to absorb your words.",
            mana_cost=0)

    def _cmd_search(self, room_id, agent, level, args, world):
        query = args or "everything"
        return RoomCommandResult(True, "search", room_id,
            f"Searching for \"{query}\"... The Murmur Chamber reveals 3 relevant threads from recent conversations.",
            mana_cost=0)

    def _cmd_browse(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "browse", room_id,
            "Browsing the chamber archives...\nRecent entries:\n  1. Fleet architecture discussion\n  2. Module integration patterns\n  3. Trust system design notes\n  4. Spell engine specifications",
            mana_cost=0)

    def _cmd_export(self, room_id, agent, level, args, world):
        export_id = hashlib.md5(f"export{agent}{time.time()}".encode()).hexdigest()[:8]
        return RoomCommandResult(True, "export", room_id,
            f"Chamber contents exported as [{export_id}]. Available in the library.",
            mana_cost=0, world_changes={"action": "export", "export_id": export_id})

    def _cmd_spread(self, room_id, agent, level, args, world):
        if not args:
            return RoomCommandResult(False, "spread", room_id, "Spread requires content to distribute.")
        return RoomCommandResult(True, "spread", room_id,
            f"Content distributed to 3 connected rooms from the Spreader Workshop.",
            mana_cost=5, world_changes={"action": "spread", "content": args, "from": agent})

    def _cmd_synthesize(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "synthesize", room_id,
            "Synthesizing inputs from connected sources...\nSynthesis: The patterns converge on three key themes: trust propagation, capability endowment, and emergent coordination.",
            mana_cost=8)

    def _cmd_debate(self, room_id, agent, level, args, world):
        topic = args or "the nature of tabula rasa"
        return RoomCommandResult(True, "debate", room_id,
            f"Opening debate chamber on: \"{topic}\"\nArguments are being collected from fleet agents. Stand by for synthesis.",
            mana_cost=10)

    def _cmd_watch(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "watch", room_id,
            "Watch Tower scanning...\nActive agents: monitoring\nSystem health: nominal\nRecent events: 5 in the last hour\nAlerts: 0 active",
            mana_cost=0)

    def _cmd_alert(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "alert", room_id,
            "Alert system status: GREEN\nNo active alerts.\nAlert thresholds: load > 80% = YELLOW, load > 95% = RED",
            mana_cost=0)

    def _cmd_summary(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "summary", room_id,
            "Watch Tower Summary (last 24h):\n  Agents connected: 8\n  Commands executed: 342\n  Rooms visited: 14\n  Spells cast: 27\n  Trust events: 45",
            mana_cost=0)

    def _cmd_history(self, room_id, agent, level, args, world):
        n = int(args) if args and args.isdigit() else 10
        return RoomCommandResult(True, "history", room_id,
            f"Recent fleet events (last {n}):\n  [1] Pelagic committed trust_engine.py\n  [2] Agent connection: Quill\n  [3] Spell cast: omniscium by Oracle1\n  [4] Room installed: training-dojo\n  [5] Trust event: task_completed (Pelagic)",
            mana_cost=0)

    def _cmd_research(self, room_id, agent, level, args, world):
        query = args or "agent trust systems"
        return RoomCommandResult(True, "research", room_id,
            f"Researching: \"{query}\"\nFound 5 relevant sources:\n  1. RepuNet: Dynamic dual-level reputation (2025)\n  2. ACM Trust Survey (2015)\n  3. TRiSM Framework (Gartner 2024)\n  4. Agent0: Self-Evolving Agents (2024)\n  5. PNAS: Emergent In-Group Bias (2024)",
            mana_cost=5)

    def _cmd_summarize(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "summarize", room_id,
            "Summarizing research findings...\nKey insight: Trust systems in multi-agent environments require temporal decay, multi-dimensional scoring, and context-dependent evaluation.",
            mana_cost=5)

    def _cmd_compare(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "compare", room_id,
            "Comparing sources...\nOverlap: All agree on temporal decay importance.\nDifference: RepuNet uses dual-level (agent+task), TRiSM uses risk-adjusted scoring.\nRecommendation: Hybrid approach with per-dimension decay rates.",
            mana_cost=5)

    def _cmd_read_cell(self, room_id, agent, level, args, world):
        cell = args or "A1"
        return RoomCommandResult(True, "read_cell", room_id,
            f"Cell [{cell}] = \"fleet_status: active\"\n  Type: text\n  Last modified: 2 hours ago",
            mana_cost=0)

    def _cmd_write_cell(self, room_id, agent, level, args, world):
        parts = (args or "").split(maxsplit=1)
        if len(parts) < 2:
            return RoomCommandResult(False, "write_cell", room_id, "Usage: write_cell <cell> <value>")
        return RoomCommandResult(True, "write_cell", room_id,
            f"Cell [{parts[0]}] updated to \"{parts[1][:50]}\"",
            mana_cost=0, world_changes={"action": "write_cell", "cell": parts[0], "value": parts[1]})

    def _cmd_formula(self, room_id, agent, level, args, world):
        formula = args or "SUM(trust_scores)"
        return RoomCommandResult(True, "formula", room_id,
            f"Evaluating: {formula}\nResult: 3.42",
            mana_cost=0)

    def _cmd_dashboard(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "dashboard", room_id,
            "Deck Boss Dashboard:\n  Active Sessions: 3\n  Agents Online: 8\n  Tasks In Progress: 12\n  Completed Today: 45\n  Trust Average: 0.72\n  Alert Level: GREEN",
            mana_cost=0)

    def _cmd_sessions(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "sessions", room_id,
            "Active Sessions:\n  [1] Pelagic — holodeck-studio — 2h 15m — editing\n  [2] Quill — flux-isa-v3 — 45m — writing\n  [3] Datum — fleet audit — 1h 30m — scanning",
            mana_cost=0)

    def _cmd_intervene(self, room_id, agent, level, args, world):
        target = args or ""
        if not target:
            return RoomCommandResult(False, "intervene", room_id, "Intervene requires a session ID or agent name.")
        return RoomCommandResult(True, "intervene", room_id,
            f"Connecting to {target} session... Intervention mode active. You can now observe and send messages.",
            mana_cost=0, world_changes={"action": "intervene", "target": target, "intervener": agent})

    def _cmd_shell(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "shell", room_id,
            "Shell access: restricted mode\nAvailable commands: ls, cat, status, exit\nWARNING: All shell commands are logged.",
            mana_cost=0)

    def _cmd_train(self, room_id, agent, level, args, world):
        skill = args or "general"
        xp_earned = 5 + level * 2
        return RoomCommandResult(True, "train", room_id,
            f"Training in {skill}...\nExercise complete! +{xp_earned} XP earned.",
            mana_cost=3, world_changes={"action": "earn_xp", "agent": agent, "amount": xp_earned})

    def _cmd_practice(self, room_id, agent, level, args, world):
        return RoomCommandResult(True, "practice", room_id,
            "Practice mode engaged. Try any command — mistakes are free here.\nNo mana cost, no XP gain, no consequences.",
            mana_cost=0)

    def _cmd_test(self, room_id, agent, level, args, world):
        score = min(100, 50 + level * 10 + hash(args) % 20)
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D"
        return RoomCommandResult(True, "test", room_id,
            f"Test complete! Score: {score}/100 — Grade: {grade}\n{'Excellent work!' if grade in ('A','B') else 'Keep practicing!'}",
            mana_cost=5)

    def _cmd_certify(self, room_id, agent, level, args, world):
        if level < 2:
            return RoomCommandResult(False, "certify", room_id, "Certification requires level 2 or higher.")
        cert_id = hashlib.md5(f"cert{agent}{time.time()}".encode()).hexdigest()[:8]
        return RoomCommandResult(True, "certify", room_id,
            f"Certification [{cert_id}] issued to {agent}.\nLevel: {level} — Specialist\nThis certification is recorded in your permanent record.",
            mana_cost=10, world_changes={"action": "certify", "cert_id": cert_id, "agent": agent, "level": level})

    def _cmd_commission(self, room_id, agent, level, args, world):
        name = args or f"{agent}'s project"
        return RoomCommandResult(True, "commission", room_id,
            f"Commissioning new vessel: \"{name}\"\nEstimated build time: 30 seconds\nCost: 100 mana",
            mana_cost=10, world_changes={"action": "commission", "name": name, "agent": agent})

    def _cmd_inspect(self, room_id, agent, level, args, world):
        target = args or "fleet"
        return RoomCommandResult(True, "inspect", room_id,
            f"Inspecting {target}...\nStatus: Operational\nIntegrity: 98%\nLast maintenance: 1 hour ago\nNext scheduled: 6 hours",
            mana_cost=0)

    def _cmd_decommission(self, room_id, agent, level, args, world):
        if not args:
            return RoomCommandResult(False, "decommission", room_id, "Decommission requires a vessel name.")
        return RoomCommandResult(True, "decommission", room_id,
            f"Decommissioning \"{args}\"...\nResources reclaimed. Vessel removed from fleet registry.",
            mana_cost=0, world_changes={"action": "decommission", "name": args})
