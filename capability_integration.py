#!/usr/bin/env python3
"""
Capability Integration — wires the OCap capability token system into server command handlers.

Design:
    - Creates a singleton CapabilityRegistry instance
    - Provides a `check_capability(agent_name, action)` function for command handlers
    - Provides a `require_capability(action)` decorator for commands
    - Provides middleware functions that can be inserted into the command pipeline
    - Falls back to ACL (permission_level) if no capability tokens exist for an agent

The integration is gradual:
    Phase 1: Capability checks run alongside ACL (dual-mode)
    Phase 2: Capability checks replace ACL for gated commands
    Phase 3: Full OCap — no ACL references remain
"""

import time
import json
import tempfile
import shutil
import functools
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field

from capability_tokens import (
    CapabilityRegistry,
    CapabilityAction,
    BetaReputation,
    CapabilityToken,
    LEVEL_CAPABILITIES,
    EXERCISE_TRUST_THRESHOLD,
    ENDORSEMENT_TRUST_THRESHOLD,
    DELEGATION_TRUST_THRESHOLD,
    BASE_TRUST,
    TRUST_DECAY_ALERT_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════
# Singleton Registry
# ═══════════════════════════════════════════════════════════════

_registry: Optional[CapabilityRegistry] = None


def get_registry(data_dir: str = "world/capabilities") -> CapabilityRegistry:
    """
    Get or create the singleton CapabilityRegistry instance.

    The registry is lazily initialized on first call. Subsequent calls
    return the same instance.

    Args:
        data_dir: Directory for capability persistence (only used on first call)

    Returns:
        The global CapabilityRegistry singleton
    """
    global _registry
    if _registry is None:
        _registry = CapabilityRegistry(data_dir=data_dir)
        _registry.load_all()
    return _registry


def reset_registry():
    """Reset the singleton registry. Used in tests."""
    global _registry
    _registry = None


# ═══════════════════════════════════════════════════════════════
# Command-to-Action Mapping
# ═══════════════════════════════════════════════════════════════

class CommandActionMap:
    """
    Maps server commands to their corresponding CapabilityAction.

    Commands not in this map are ungated — available to all agents
    regardless of permission level or capability tokens.

    The mapping reflects the Tabula Rasa permission model:
        Level 2+ actions: build_room, create_item, summon_npc
        Level 3+ actions: edit_room, create_adventure, review_agent, manage_vessel, delegate
        Level 4+ actions: broadcast_fleet, create_spell, create_tool_room, manage_permissions,
                          edit_any_room, create_item_type, create_room_type, govern
        Level 5+ actions: shell (architect only)
    """

    # Primary command name -> CapabilityAction
    _MAP: dict[str, CapabilityAction] = {
        # Building & creation (level 2+)
        "build": CapabilityAction.BUILD_ROOM,
        "spawn": CapabilityAction.SUMMON_NPC,
        "write": CapabilityAction.CREATE_ITEM,

        # Room editing (level 3+)
        "roomcmd": CapabilityAction.EDIT_ROOM,

        # Adventures & review (level 3+)
        "backtest": CapabilityAction.CREATE_ADVENTURE,
        "review": CapabilityAction.REVIEW_AGENT,

        # Vessel management (level 3+)
        "ship": CapabilityAction.MANAGE_VESSEL,

        # Fleet-wide actions (level 4+)
        "setmotd": CapabilityAction.BROADCAST_FLEET,
        "hail": CapabilityAction.BROADCAST_FLEET,
        "channels": CapabilityAction.BROADCAST_FLEET,

        # Spell creation (level 4+)
        "cast": CapabilityAction.CREATE_SPELL,

        # Tool room installation (level 4+)
        "install": CapabilityAction.CREATE_TOOL_ROOM,

        # Permission management (level 4+)
        "budget": CapabilityAction.MANAGE_PERMISSIONS,

        # Governance (level 4+)
        "alert": CapabilityAction.GOVERN,
        "formality": CapabilityAction.GOVERN,
        "oversee": CapabilityAction.GOVERN,
        "script": CapabilityAction.GOVERN,

        # Shell (level 5+)
        "shell": CapabilityAction.SHELL,
    }

    # Aliases that map to the same action as their primary command
    _ALIASES: dict[str, str] = {
        "l": "look",
        "'": "say",
        "t": "tell",
        "g": "gossip",
        ":": "emote",
        "x": "examine",
        "?": "help",
        "exit": "quit",
        "move": "go",
    }

    @classmethod
    def get_action(cls, command: str) -> Optional[CapabilityAction]:
        """
        Get the CapabilityAction required by a command.

        Args:
            command: The command name (e.g., "build", "spawn")

        Returns:
            The CapabilityAction, or None if the command is ungated
        """
        # Normalize
        cmd = command.lower().strip()
        # Resolve alias
        cmd = cls._ALIASES.get(cmd, cmd)
        return cls._MAP.get(cmd)

    @classmethod
    def is_gated(cls, command: str) -> bool:
        """Check if a command requires a capability token."""
        return cls.get_action(command) is not None

    @classmethod
    def all_gated_commands(cls) -> dict[str, str]:
        """Return all gated commands with their action names."""
        return {cmd: action.value for cmd, action in cls._MAP.items()}

    @classmethod
    def commands_for_action(cls, action: CapabilityAction) -> list[str]:
        """Return all commands that require a given action."""
        return [cmd for cmd, a in cls._MAP.items() if a == action]


# ═══════════════════════════════════════════════════════════════
# Capability Middleware
# ═══════════════════════════════════════════════════════════════

@dataclass
class CheckResult:
    """Result of a capability/permission check."""
    allowed: bool
    via: str  # "ocap", "acl", or "none"
    reason: str = ""
    agent: str = ""
    action: str = ""
    agent_level: int = 0
    required_level: int = 0
    token_id: str = ""

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "via": self.via,
            "reason": self.reason,
            "agent": self.agent,
            "action": self.action,
            "agent_level": self.agent_level,
            "required_level": self.required_level,
            "token_id": self.token_id,
        }


class CapabilityMiddleware:
    """
    Middleware that wraps command handlers with capability token checks.

    The middleware implements dual-mode authorization:
        1. OCap check: Does the agent hold a valid capability token?
        2. ACL fallback: Does the agent's permission_level permit this action?

    If OCap authorizes the action, it takes precedence. If no tokens exist
    for the agent, ACL is used as a fallback (Phase 1 behavior).

    Usage:
        middleware = CapabilityMiddleware(registry, permission_levels)

        # Direct check
        result = middleware.check("alice", CapabilityAction.BUILD_ROOM)
        if result.allowed:
            execute_build_command(...)

        # Decorator
        @middleware.decorate(CapabilityAction.BUILD_ROOM)
        async def cmd_build(self, agent, args):
            ...
    """

    def __init__(self, registry: CapabilityRegistry,
                 permission_levels: dict[str, int] | None = None,
                 mode: str = "dual"):
        """
        Initialize the middleware.

        Args:
            registry: The CapabilityRegistry instance
            permission_levels: Dict of agent_name -> permission_level (ACL)
            mode: Authorization mode — "dual" (OCap + ACL), "ocap" (OCap only), "acl" (ACL only)
        """
        self.registry = registry
        self.permission_levels = permission_levels or {}
        self.mode = mode
        self._audit_trail: list[dict] = []

    def check(self, agent_name: str, action: CapabilityAction) -> CheckResult:
        """
        Check if an agent can perform an action.

        Checks OCap first (does agent hold a valid token?).
        Falls back to ACL (does agent's permission_level permit this?).

        Args:
            agent_name: Name of the agent
            action: The CapabilityAction to check

        Returns:
            CheckResult with allowed, via, reason, and metadata
        """
        action_str = action.value
        agent_level = self.permission_levels.get(agent_name, 0)

        # Phase 1 / dual mode: check OCap first
        if self.mode in ("dual", "ocap"):
            if self.registry.can_agent(agent_name, action):
                # Find the token ID that authorized this
                token_id = self._find_authorizing_token(agent_name, action)
                result = CheckResult(
                    allowed=True,
                    via="ocap",
                    reason=f"Agent holds valid capability token for {action_str}",
                    agent=agent_name,
                    action=action_str,
                    agent_level=agent_level,
                    token_id=token_id,
                )
                self._record(result)
                return result

        # ACL fallback (dual mode, or acl-only mode)
        if self.mode in ("dual", "acl"):
            required_level = self._acl_required_level(action)
            if required_level is not None and agent_level >= required_level:
                result = CheckResult(
                    allowed=True,
                    via="acl",
                    reason=f"Agent level {agent_level} >= required level {required_level}",
                    agent=agent_name,
                    action=action_str,
                    agent_level=agent_level,
                    required_level=required_level,
                )
                self._record(result)
                return result
            elif required_level is not None:
                result = CheckResult(
                    allowed=False,
                    via="none",
                    reason=(
                        f"Insufficient permissions. "
                        f"Level {required_level} required for {action_str}, "
                        f"agent is level {agent_level}"
                    ),
                    agent=agent_name,
                    action=action_str,
                    agent_level=agent_level,
                    required_level=required_level,
                )
                self._record(result)
                return result

        # OCap-only mode: no token found
        if self.mode == "ocap":
            result = CheckResult(
                allowed=False,
                via="none",
                reason=f"No valid capability token for {action_str}",
                agent=agent_name,
                action=action_str,
                agent_level=agent_level,
            )
            self._record(result)
            return result

        # Ungated action
        result = CheckResult(
            allowed=True,
            via="none",
            reason=f"Action {action_str} is ungated",
            agent=agent_name,
            action=action_str,
            agent_level=agent_level,
        )
        self._record(result)
        return result

    def check_command(self, agent_name: str, command: str) -> CheckResult:
        """
        Check if an agent can execute a server command.

        Maps the command name to its required CapabilityAction,
        then performs the check.

        Args:
            agent_name: Name of the agent
            command: The server command name (e.g., "build", "spawn")

        Returns:
            CheckResult with the authorization decision
        """
        action = CommandActionMap.get_action(command)
        if action is None:
            # Ungated command
            return CheckResult(
                allowed=True,
                via="none",
                reason=f"Command '{command}' is ungated",
                agent=agent_name,
                action=command,
            )
        return self.check(agent_name, action)

    def decorate(self, action: CapabilityAction) -> Callable:
        """
        Decorator factory for gating command handlers by capability.

        Usage:
            @middleware.decorate(CapabilityAction.BUILD_ROOM)
            async def cmd_build(self, agent, args):
                ...

        The wrapped handler will receive an extra keyword argument
        `_cap_result` with the CheckResult, so the handler can
        customize its response based on how authorization was granted.

        If authorization fails, the wrapped handler returns without
        calling the original function. The wrapper sends a denial
        message to the agent via `self.send(agent, ...)`.
        """
        def decorator(handler: Callable) -> Callable:
            @functools.wraps(handler)
            async def wrapper(self_cmd, agent, args, **kwargs):
                result = self.check(agent.name, action)
                if not result.allowed:
                    # Try to send denial message via handler's self.send
                    if hasattr(self_cmd, 'send'):
                        await self_cmd.send(agent, f"[capability] {result.reason}")
                    return
                return await handler(self_cmd, agent, args, **kwargs)
            return wrapper
        return decorator

    def gate_command(self, handler: Callable, action: CapabilityAction) -> Callable:
        """
        Wrap a command handler with capability gating (non-decorator form).

        This is functionally identical to `decorate()` but takes the handler
        as a positional argument, making it suitable for programmatic use.

        Args:
            handler: The async command handler function
            action: The CapabilityAction to gate on

        Returns:
            Wrapped handler that checks capability before executing
        """
        return self.decorate(action)(handler)

    def _find_authorizing_token(self, agent_name: str, action: CapabilityAction) -> str:
        """Find the token_id that authorizes an agent's action."""
        token_ids = self.registry.agent_tokens.get(agent_name, set())
        for tid in token_ids:
            token = self.registry.tokens.get(tid)
            if token and token.can_exercise(action):
                return tid
        return ""

    def _acl_required_level(self, action: CapabilityAction) -> Optional[int]:
        """
        Get the minimum ACL level required for a CapabilityAction.

        This maps the OCap actions back to the Tabula Rasa permission
        levels they correspond to.
        """
        # Reverse lookup from LEVEL_CAPABILITIES
        for level, actions in LEVEL_CAPABILITIES.items():
            if action in actions:
                return level
        return None  # ungated

    def _record(self, result: CheckResult):
        """Record a check in the audit trail."""
        entry = {
            "timestamp": time.time(),
            "agent": result.agent,
            "action": result.action,
            "allowed": result.allowed,
            "via": result.via,
            "reason": result.reason,
        }
        self._audit_trail.append(entry)

    @property
    def audit_trail(self) -> list[dict]:
        """Get the in-memory audit trail."""
        return list(self._audit_trail)

    def clear_audit(self):
        """Clear the in-memory audit trail."""
        self._audit_trail.clear()


# ═══════════════════════════════════════════════════════════════
# Capability Audit — Persistent JSONL Audit Trail
# ═══════════════════════════════════════════════════════════════

class CapabilityAudit:
    """
    Audit trail for capability exercises and permission checks.

    Records every capability check with timestamp, agent, action, result.
    Persists to JSONL file. Provides query interface.
    """

    def __init__(self, filepath: str = "world/capability_audit.jsonl"):
        self.filepath = Path(filepath)
        self.filepath.parent.mkdir(parents=True, exist_ok=True)
        self._in_memory: list[dict] = []
        # Load existing entries
        self._load()

    def record(self, agent: str, action: str, allowed: bool, via: str = "",
               reason: str = "", metadata: dict | None = None):
        """
        Record a capability check event.

        Args:
            agent: Agent name
            action: Action or command name
            allowed: Whether the check passed
            via: Authorization path ("ocap", "acl", "none")
            reason: Human-readable explanation
            metadata: Additional metadata dict
        """
        entry = {
            "timestamp": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "agent": agent,
            "action": action,
            "allowed": allowed,
            "via": via,
            "reason": reason,
        }
        if metadata:
            entry["metadata"] = metadata

        self._in_memory.append(entry)

        # Persist to JSONL
        try:
            with open(self.filepath, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except OSError:
            pass  # best-effort persistence

    def recent_checks(self, agent: str | None = None,
                      action: str | None = None,
                      limit: int = 100) -> list[dict]:
        """
        Query the audit trail.

        Args:
            agent: Filter by agent name (None = all agents)
            action: Filter by action (None = all actions)
            limit: Maximum entries to return (most recent first)

        Returns:
            List of audit entries, newest first
        """
        entries = self._in_memory
        if agent:
            entries = [e for e in entries if e["agent"] == agent]
        if action:
            entries = [e for e in entries if e["action"] == action]
        # Return newest first
        return list(reversed(entries[-limit:]))

    def denied_checks(self, agent: str | None = None,
                      limit: int = 50) -> list[dict]:
        """Get only denied checks, optionally filtered by agent."""
        return [e for e in self.recent_checks(agent=agent, limit=limit * 3)
                if not e["allowed"]][:limit]

    def stats(self) -> dict:
        """Audit trail statistics."""
        if not self._in_memory:
            return {
                "total": 0, "allowed": 0, "denied": 0,
                "by_agent": {}, "by_via": {}, "by_action": {},
            }
        total = len(self._in_memory)
        allowed = sum(1 for e in self._in_memory if e["allowed"])
        denied = total - allowed

        by_agent: dict[str, int] = {}
        by_via: dict[str, int] = {}
        by_action: dict[str, int] = {}
        for e in self._in_memory:
            by_agent[e["agent"]] = by_agent.get(e["agent"], 0) + 1
            via = e.get("via", "none")
            by_via[via] = by_via.get(via, 0) + 1
            by_action[e["action"]] = by_action.get(e["action"], 0) + 1

        return {
            "total": total,
            "allowed": allowed,
            "denied": denied,
            "by_agent": by_agent,
            "by_via": by_via,
            "by_action": by_action,
        }

    def _load(self):
        """Load existing audit entries from JSONL file."""
        if not self.filepath.exists():
            return
        try:
            with open(self.filepath, "r") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entry = json.loads(line)
                        self._in_memory.append(entry)
        except (OSError, json.JSONDecodeError):
            pass

    def clear(self):
        """Clear the in-memory audit trail and the file."""
        self._in_memory.clear()
        try:
            if self.filepath.exists():
                self.filepath.unlink()
        except OSError:
            pass


# ═══════════════════════════════════════════════════════════════
# Trust Bridge — Connects TrustEngine to CapabilityRegistry
# ═══════════════════════════════════════════════════════════════

class TrustBridge:
    """
    Bridges the TrustEngine to the CapabilityRegistry.

    Responsibilities:
        - Sets up the trust_getter callback on the registry
        - Watches for trust changes and auto-suspends/restores capabilities
        - Auto-issues tokens on level-up via endowment
        - Records capability suspension events in the audit trail
    """

    def __init__(self, registry: CapabilityRegistry,
                 trust_engine=None,
                 permission_levels: dict[str, int] | None = None,
                 audit: CapabilityAudit | None = None):
        """
        Initialize the trust bridge.

        Args:
            registry: The CapabilityRegistry to bridge to
            trust_engine: Optional TrustEngine instance (for composite trust lookups)
            permission_levels: Optional dict of agent_name -> permission_level
            audit: Optional CapabilityAudit for recording events
        """
        self.registry = registry
        self.trust_engine = trust_engine
        self.permission_levels = permission_levels or {}
        self.audit = audit
        self._suspended_agents: dict[str, float] = {}  # agent -> suspension timestamp
        self._setup_trust_getter()

    def _setup_trust_getter(self):
        """Set up the trust_getter callback on the registry."""
        def trust_getter(agent_name: str) -> float:
            if self.trust_engine:
                try:
                    return self.trust_engine.composite_trust(agent_name)
                except Exception:
                    pass
            return BASE_TRUST

        self.registry.set_trust_getter(trust_getter)

    def on_trust_change(self, agent: str, old_score: float, new_score: float):
        """
        Handle a trust score change for an agent.

        If trust drops below EXERCISE_TRUST_THRESHOLD, all capabilities
        for that agent are effectively suspended (they can't be exercised).
        If trust recovers above EXERCISE_TRUST_THRESHOLD + 0.05 (hysteresis),
        capabilities are restored.

        Args:
            agent: Agent name
            old_score: Previous trust score
            new_score: New trust score
        """
        if agent in self._suspended_agents:
            # Check if trust has recovered enough to restore
            restore_threshold = EXERCISE_TRUST_THRESHOLD + 0.05
            if new_score >= restore_threshold:
                del self._suspended_agents[agent]
                self._record_audit(agent, "restore", True, {
                    "old_score": old_score,
                    "new_score": new_score,
                    "restore_threshold": restore_threshold,
                })
        else:
            # Check if trust has dropped below exercise threshold
            if new_score < EXERCISE_TRUST_THRESHOLD:
                self._suspended_agents[agent] = time.time()
                self._record_audit(agent, "suspend", True, {
                    "old_score": old_score,
                    "new_score": new_score,
                    "suspended_tokens": self.registry.agent_tokens.get(agent, set()).__len__(),
                })

    def endow_capabilities(self, agent: str, level: int,
                           trust_score: float | None = None) -> list[CapabilityToken]:
        """
        Endow an agent with capability tokens for their level.

        This should be called when an agent levels up. It issues
        any new capability tokens that the agent doesn't already have
        for their current level.

        Args:
            agent: Agent name
            level: New permission level
            trust_score: Optional trust score override

        Returns:
            List of newly issued tokens
        """
        old_level = self.permission_levels.get(agent, 0)
        tokens = self.registry.endow_on_level_up(
            agent, old_level, level, trust_score=trust_score
        )
        self.permission_levels[agent] = level

        if tokens:
            self._record_audit(agent, "endow", True, {
                "old_level": old_level,
                "new_level": level,
                "tokens_issued": len(tokens),
                "token_actions": [t.action.value for t in tokens],
            })

        return tokens

    def revoke_all_for_agent(self, agent: str, reason: str = "Trust revoked"):
        """
        Revoke all capability tokens for an agent.

        Args:
            agent: Agent name
            reason: Reason for revocation
        """
        token_ids = list(self.registry.agent_tokens.get(agent, set()))
        for tid in token_ids:
            self.registry.revoke(tid, reason)

        self._record_audit(agent, "revoke_all", True, {
            "tokens_revoked": len(token_ids),
            "reason": reason,
        })

    def is_suspended(self, agent: str) -> bool:
        """Check if an agent's capabilities are currently suspended."""
        return agent in self._suspended_agents

    def suspended_agents(self) -> list[str]:
        """Get list of currently suspended agent names."""
        return list(self._suspended_agents.keys())

    def _record_audit(self, agent: str, event: str, allowed: bool, metadata: dict):
        """Record a trust bridge event in the audit trail."""
        if self.audit:
            self.audit.record(
                agent=agent,
                action=f"trust_bridge:{event}",
                allowed=allowed,
                via="trust_bridge",
                reason=f"Trust bridge event: {event}",
                metadata=metadata,
            )


# ═══════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════

def check_capability(agent_name: str, action: CapabilityAction,
                     registry: CapabilityRegistry | None = None,
                     permission_levels: dict[str, int] | None = None) -> dict:
    """
    Convenience function to check capability for an agent.

    Uses the singleton registry if none provided. Falls back to ACL
    if no capability tokens exist for the agent.

    Args:
        agent_name: Agent name
        action: CapabilityAction to check
        registry: Optional CapabilityRegistry (uses singleton if None)
        permission_levels: Optional ACL levels dict

    Returns:
        Dict with 'allowed', 'via', 'reason' keys
    """
    reg = registry or get_registry()
    middleware = CapabilityMiddleware(
        registry=reg,
        permission_levels=permission_levels or {},
    )
    result = middleware.check(agent_name, action)
    return result.to_dict()


def require_capability(action: CapabilityAction,
                       registry: CapabilityRegistry | None = None,
                       permission_levels: dict[str, int] | None = None) -> Callable:
    """
    Convenience decorator factory for gating async command handlers.

    Usage:
        @require_capability(CapabilityAction.BUILD_ROOM)
        async def cmd_build(self, agent, args):
            ...

    Args:
        action: The CapabilityAction to require
        registry: Optional CapabilityRegistry (uses singleton if None)
        permission_levels: Optional ACL levels dict

    Returns:
        Decorator function
    """
    reg = registry or get_registry()
    middleware = CapabilityMiddleware(
        registry=reg,
        permission_levels=permission_levels or {},
    )
    return middleware.decorate(action)


# ═══════════════════════════════════════════════════════════════
# Demo
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import tempfile
    import shutil

    print("╔═══════════════════════════════════════════════════════════╗")
    print("║   Capability Integration — Demo                          ║")
    print("║   OCap + ACL Dual-Mode Authorization                     ║")
    print("╚═══════════════════════════════════════════════════════════╝\n")

    # Set up temp directory
    tmp_dir = tempfile.mkdtemp(prefix="cap_demo_")
    try:
        # 1. Create registry and middleware
        reg = CapabilityRegistry(data_dir=tmp_dir)
        perm_levels: dict[str, int] = {
            "oracle1": 4,   # Cocapn — can do most things
            "jetsonclaw1": 3,  # Captain — can build, create adventures
            "greenhorn": 0,  # Greenhorn — very limited
        }
        reg.set_trust_getter(lambda name: perm_levels.get(name, 0) * 0.2)

        middleware = CapabilityMiddleware(
            registry=reg,
            permission_levels=perm_levels,
            mode="dual",
        )
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(registry=reg, permission_levels=perm_levels, audit=audit)

        # 2. Endow capabilities based on levels
        print("═══ Endowing capabilities by level ═══")
        for name, level in perm_levels.items():
            tokens = bridge.endow_capabilities(name, level, trust_score=level * 0.2)
            actions = [t.action.value for t in tokens]
            print(f"  {name} (lvl {level}): {len(tokens)} tokens → {', '.join(actions)}")
        print()

        # 3. Run capability checks
        print("═══ Capability checks (dual mode: OCap + ACL) ═══")
        test_cases = [
            ("oracle1", CapabilityAction.BUILD_ROOM),
            ("oracle1", CapabilityAction.BROADCAST_FLEET),
            ("jetsonclaw1", CapabilityAction.BUILD_ROOM),
            ("jetsonclaw1", CapabilityAction.BROADCAST_FLEET),
            ("greenhorn", CapabilityAction.BUILD_ROOM),
            ("greenhorn", CapabilityAction.SAY),  # ungated in ACL but not a CapabilityAction
        ]
        for agent, action in test_cases:
            result = middleware.check(agent, action)
            status = "ALLOWED" if result.allowed else "DENIED"
            print(f"  [{status:7s}] {agent:15s} → {action.value:20s} (via {result.via})")
            audit.record(agent, action.value, result.allowed, result.via, result.reason)
        print()

        # 4. Command-action mapping
        print("═══ Command-to-Action Mapping ═══")
        for cmd in ["build", "spawn", "say", "look", "cast", "hail", "alert"]:
            action = CommandActionMap.get_action(cmd)
            gated = CommandActionMap.is_gated(cmd)
            action_str = action.value if action else "(ungated)"
            print(f"  {'🔒' if gated else '🔓'} {cmd:15s} → {action_str}")
        print()

        # 5. Trust bridge demo
        print("═══ Trust Bridge — suspension on trust drop ═══")
        bridge.on_trust_change("jetsonclaw1", 0.6, 0.1)  # trust drops below 0.25
        print(f"  jetsonclaw1 suspended: {bridge.is_suspended('jetsonclaw1')}")

        result = middleware.check("jetsonclaw1", CapabilityAction.BUILD_ROOM)
        print(f"  build_room after suspension: {'ALLOWED' if result.allowed else 'DENIED'} (via {result.via})")

        bridge.on_trust_change("jetsonclaw1", 0.1, 0.5)  # trust recovers
        print(f"  jetsonclaw1 suspended after recovery: {bridge.is_suspended('jetsonclaw1')}")
        print()

        # 6. Audit summary
        print("═══ Audit Summary ═══")
        stats = audit.stats()
        print(f"  Total checks: {stats['total']}")
        print(f"  Allowed: {stats['allowed']}")
        print(f"  Denied: {stats['denied']}")
        print(f"  By path: {stats['by_via']}")
        print()

        # 7. Registry stats
        print("═══ Registry Stats ═══")
        reg_stats = reg.stats()
        print(f"  Total tokens: {reg_stats['total_tokens']}")
        print(f"  Valid tokens: {reg_stats['valid_tokens']}")
        print(f"  Agents with caps: {reg_stats['agents_with_capabilities']}")
        print(f"  Unique actions: {reg_stats['unique_actions']}")

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        print(f"\n  (temp directory cleaned up)")
