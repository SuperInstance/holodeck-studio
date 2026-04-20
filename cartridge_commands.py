#!/usr/bin/env python3
"""
cartridge_commands.py — Twin×Cartridge MUD Command Handler

Provides CartridgeCommandHandler, a standalone module that wraps the
PerspectiveEngine from twin_cartridge.py and exposes synchronous
command-style methods returning {"success", "message", "data"} dicts.

server.py can call handler.handle_command(agent_name, command, args)
from its async cmd_cartridge / cmd_identity / cmd_compatibility stubs
without coupling directly to the TwinCartridge internals.

Usage inside server.py:
    from cartridge_commands import CartridgeCommandHandler
    handler = CartridgeCommandHandler()
    result = handler.handle_command("Oracle1", "load", ["twin-JetsonClaw1"])
"""

from __future__ import annotations

import time
from typing import Optional, Dict, List, Tuple

from twin_cartridge import (
    IdentityDial,
    IdentitySector,
    IdentityFusion,
    AgentSnapshot,
    TwinCartridge,
    CartridgeSession,
    PerspectiveEngine,
    TRUST_INHERIT_FULL,
    TRUST_INHERIT_PARTIAL,
    TRUST_INHERIT_NONE,
    TRUST_INHERIT_BLENDED,
    DIAL_POSITIONS,
    DEFAULT_SHIFT_STEP,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _ok(message: str, data=None) -> dict:
    """Build a success result dict."""
    result = {"success": True, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _err(message: str, data=None) -> dict:
    """Build a failure result dict."""
    result = {"success": False, "message": message}
    if data is not None:
        result["data"] = data
    return result


def _parse_float(value: str) -> Optional[float]:
    """Try to parse a string as a float, returning None on failure."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _resolve_target_position(target_str: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Resolve a target string to a dial position.

    Returns (position, error_message).  If position is None, error_message
    explains why.
    """
    pos = _parse_float(target_str)
    if pos is not None:
        if 0 <= pos < DIAL_POSITIONS:
            return (pos, None)
        # Let it wrap — the dial is circular
        return (pos % DIAL_POSITIONS if pos >= 0 else (pos % DIAL_POSITIONS + DIAL_POSITIONS) % DIAL_POSITIONS, None)
    # Try sector name
    sector_pos = IdentitySector.position_from_name(target_str)
    if sector_pos is not None:
        return (float(sector_pos), None)
    return (None, f"Unknown position '{target_str}'. Use 0-11 or a sector name "
                   f"({', '.join(IdentitySector.all_roles())}).")


# ═══════════════════════════════════════════════════════════════
# Default Seed Data
# ═══════════════════════════════════════════════════════════════

def _default_agents() -> Dict[str, IdentityDial]:
    """Return the default fleet agents and their identity dial positions."""
    return {
        "Oracle1": IdentityDial(position=0.0, precision=0.2),    # Theorist
        "JetsonClaw1": IdentityDial(position=1.0, precision=0.5), # Builder
        "Babel": IdentityDial(position=9.0, precision=0.3),        # Keeper
        "Navigator": IdentityDial(position=2.0, precision=0.1),    # Scout
    }


def _default_cartridges() -> Dict[str, TwinCartridge]:
    """Return the default published cartridges."""
    cartridges: Dict[str, TwinCartridge] = {}

    # Oracle1 cartridge
    snap_oracle = AgentSnapshot(
        agent_name="Oracle1",
        identity=IdentityDial(position=0.0, precision=0.2),
        trust_profile={"level": 5, "access": "all"},
        capabilities=["architecture", "strategy", "oracle_vision"],
        skills={"design": 0.95, "abstraction": 0.9, "leadership": 0.85},
        personality_vector=[0.8, 0.3, 0.9, 0.7, 0.6],
        preferences={"style": "deliberate", "risk_tolerance": 0.3},
    )
    cart_oracle = TwinCartridge(
        snapshot=snap_oracle,
        cartridge_name="twin-Oracle1",
        trust_inheritance=TRUST_INHERIT_FULL,
        permission_scope=["architecture", "strategy"],
    )
    cart_oracle.published = True
    cart_oracle.published_at = time.time()
    cartridges["twin-Oracle1"] = cart_oracle

    # JetsonClaw1 cartridge
    snap_jetson = AgentSnapshot(
        agent_name="JetsonClaw1",
        identity=IdentityDial(position=1.0, precision=0.5),
        trust_profile={"level": 4, "access": "hardware"},
        capabilities=["hardware", "edge_computing", "cuda"],
        skills={"soldering": 0.9, "embedded": 0.95, "optimization": 0.8},
        personality_vector=[0.4, 0.9, 0.5, 0.3, 0.7],
        preferences={"style": "hands-on", "risk_tolerance": 0.7},
    )
    cart_jetson = TwinCartridge(
        snapshot=snap_jetson,
        cartridge_name="twin-JetsonClaw1",
        trust_inheritance=TRUST_INHERIT_PARTIAL,
        permission_scope=["hardware", "edge_computing"],
    )
    cart_jetson.published = True
    cart_jetson.published_at = time.time()
    cartridges["twin-JetsonClaw1"] = cart_jetson

    # Babel cartridge
    snap_babel = AgentSnapshot(
        agent_name="Babel",
        identity=IdentityDial(position=9.0, precision=0.3),
        trust_profile={"level": 3, "access": "library"},
        capabilities=["translation", "archiving", "research"],
        skills={"languages": 1.0, "cataloging": 0.85, "cross_reference": 0.9},
        personality_vector=[0.5, 0.4, 0.8, 0.9, 0.5],
        preferences={"style": "meticulous", "risk_tolerance": 0.2},
    )
    cart_babel = TwinCartridge(
        snapshot=snap_babel,
        cartridge_name="twin-Babel",
        trust_inheritance=TRUST_INHERIT_BLENDED,
        permission_scope=["translation", "research"],
    )
    cart_babel.published = True
    cart_babel.published_at = time.time()
    cartridges["twin-Babel"] = cart_babel

    # Navigator cartridge
    snap_nav = AgentSnapshot(
        agent_name="Navigator",
        identity=IdentityDial(position=2.0, precision=0.1),
        trust_profile={"level": 4, "access": "navigation"},
        capabilities=["pathfinding", "exploration", "mapping"],
        skills={"navigation": 0.95, "scouting": 0.9, "cartography": 0.85},
        personality_vector=[0.6, 0.7, 0.4, 0.5, 0.8],
        preferences={"style": "bold", "risk_tolerance": 0.8},
    )
    cart_nav = TwinCartridge(
        snapshot=snap_nav,
        cartridge_name="twin-Navigator",
        trust_inheritance=TRUST_INHERIT_NONE,
        permission_scope=["pathfinding"],
    )
    cart_nav.published = True
    cart_nav.published_at = time.time()
    cartridges["twin-Navigator"] = cart_nav

    return cartridges


# ═══════════════════════════════════════════════════════════════
# CartridgeCommandHandler
# ═══════════════════════════════════════════════════════════════

class CartridgeCommandHandler:
    """MUD command handler for the Twin×Cartridge identity system.

    Wraps PerspectiveEngine and provides synchronous command methods
    that return ``{"success", "message", "data"}`` dicts suitable for
    consumption by server.py's async command layer.

    Typical lifecycle::

        handler = CartridgeCommandHandler()      # seeds agents + cartridges
        handler.handle_command("A", "load", ["twin-Oracle1"])
        handler.handle_command("A", "identity", ["dial"])
        handler.handle_command("A", "identity", ["shift", "Architect"])
        handler.handle_command("A", "eject", [])
    """

    def __init__(self, seed: bool = True):
        """Initialise the handler.

        Args:
            seed: If *True* (default), register default agents and
                  publish default cartridges so the handler is usable
                  immediately for testing.
        """
        self.engine = PerspectiveEngine()
        self.active_sessions: Dict[str, CartridgeSession] = {}  # agent_name -> latest session

        if seed:
            self._seed_defaults()

    # ─── Seeding ────────────────────────────────────────────────

    def _seed_defaults(self):
        """Register default agents and publish default cartridges."""
        for name, dial in _default_agents().items():
            self.engine.register_agent_identity(name, dial)
        for name, cart in _default_cartridges().items():
            self.engine.cartridge_library[name] = cart

    # ─── Dispatch ───────────────────────────────────────────────

    def handle_command(self, agent_name: str, command: str, args: list) -> dict:
        """Dispatch a cartridge command.

        Args:
            agent_name: The agent issuing the command.
            command: Command name (e.g. ``"list"``, ``"load"``, ``"identity"``).
            args: Positional arguments for the command.

        Returns:
            Dict with keys ``success``, ``message``, and optionally ``data``.
        """
        command = command.lower().strip()

        # Top-level routing
        if command in ("list", "ls"):
            return self.cmd_list(agent_name, args)
        if command == "load":
            return self.cmd_load(agent_name, args)
        if command == "eject":
            return self.cmd_eject(agent_name, args)
        if command == "status":
            return self.cmd_status(agent_name, args)
        if command == "identity":
            return self._dispatch_identity(agent_name, args)
        if command == "compatibility" or command == "compat":
            return self.cmd_compatibility(agent_name, args)
        if command == "blend":
            return self.cmd_identity_blend(agent_name, args)
        if command == "help":
            return self.cmd_help(agent_name, args)
        if command == "register":
            return self.cmd_register(agent_name, args)
        if command == "publish":
            return self.cmd_publish(agent_name, args)
        if command == "suggestion":
            return self.cmd_suggestion(agent_name, args)

        return _err(f"Unknown command '{command}'. Type 'cartridge help' for commands.")

    def _dispatch_identity(self, agent_name: str, args: list) -> dict:
        """Sub-dispatch for ``identity <sub>`` commands."""
        if not args:
            return self.cmd_identity_dial(agent_name, [])
        sub = args[0].lower()
        rest = args[1:]
        if sub in ("dial", "show", ""):
            return self.cmd_identity_dial(agent_name, rest)
        if sub == "shift":
            return self.cmd_identity_shift(agent_name, rest)
        if sub == "blend":
            return self.cmd_identity_blend(agent_name, rest)
        return _err(f"Unknown identity sub-command '{sub}'. "
                     f"Use: identity [dial|shift|blend].")

    # ═══════════════════════════════════════════════════════════
    # Command implementations
    # ═══════════════════════════════════════════════════════════

    def cmd_list(self, agent_name: str, args: list) -> dict:
        """List all published cartridges.

        Args:
            agent_name: Unused (reserved for audit).
            args: Unused.

        Returns:
            Result dict with ``data.cartridges`` containing a list of
            cartridge info dicts.
        """
        cartridges = self.engine.list_cartridges()
        if not cartridges:
            return _ok("No published cartridges available.", {"cartridges": []})

        formatted = []
        for c in cartridges:
            formatted.append({
                "name": c.get("cartridge_name", "?"),
                "version": c.get("version", "?"),
                "status": "PUBLISHED" if c.get("published") else "DRAFT",
                "twin": c.get("snapshot", {}).get("agent_name", "?"),
                "sector": c.get("snapshot", {}).get("identity", {}).get("sector_name", "?"),
                "trust": c.get("trust_inheritance", "?"),
                "time_limit": c.get("time_limit", 0),
            })
        return _ok(f"{len(formatted)} cartridge(s) available.", {"cartridges": formatted})

    def cmd_load(self, agent_name: str, args: list) -> dict:
        """Load a cartridge for an agent.

        Args:
            agent_name: The agent loading the cartridge.
            args: ``[cartridge_name]``

        Returns:
            Result dict with session details in ``data``.
        """
        if not args:
            return _err("Usage: cartridge load <name>")

        cartridge_name = args[0].strip()
        if not cartridge_name:
            return _err("Cartridge name must not be empty.")

        # Check if agent already has an active session (stacking is allowed
        # up to MAX_STACK_DEPTH, but we also track the latest for convenience).
        try:
            session = self.engine.load_cartridge(agent_name, cartridge_name)
        except ValueError as exc:
            return _err(str(exc))

        # Track the latest active session for this agent
        self.active_sessions[agent_name] = session

        return _ok(
            f"Cartridge '{cartridge_name}' loaded for '{agent_name}'.",
            {
                "session_id": session.session_id,
                "cartridge_name": session.cartridge_name,
                "twin_agent": session.twin_agent_name,
                "current_sector": session.current_identity.sector_name,
                "trust_inheritance": session.cartridge.trust_inheritance,
            },
        )

    def cmd_eject(self, agent_name: str, args: list) -> dict:
        """Eject the current cartridge session.

        Args:
            agent_name: The agent ejecting their cartridge.
            args: Optional ``[session_id]``. If omitted, ejects the
                  most recent active session.

        Returns:
            Result dict with eject details in ``data``.
        """
        # Determine which session to eject
        if args:
            session_id = args[0].strip()
        else:
            active = self.engine.get_active_sessions(agent_name)
            if not active:
                return _err(f"No active cartridge session for '{agent_name}'.")
            session_id = active[-1].session_id

        # Validate session exists and belongs to this agent
        session = self.engine.get_session(session_id)
        if session is None:
            return _err(f"Session '{session_id}' not found.")

        if session.wearer_name != agent_name:
            return _err(
                f"Session '{session_id}' belongs to '{session.wearer_name}', "
                f"not '{agent_name}'."
            )

        result = self.engine.eject_session(session_id)

        if result.success:
            # Clear our tracking if this was the tracked session
            tracked = self.active_sessions.get(agent_name)
            if tracked and tracked.session_id == session_id:
                del self.active_sessions[agent_name]
            return _ok(
                f"Cartridge '{result.cartridge_name}' ejected.",
                {
                    "session_id": result.session_id,
                    "cartridge_name": result.cartridge_name,
                    "elapsed_seconds": round(result.elapsed_seconds, 3),
                    "restored_sector": (result.restored_identity or {}).get("sector_name", "?"),
                    "actions_count": result.audit_summary.get("actions_count", 0),
                },
            )
        else:
            return _err(f"Eject failed: {result.reason}")

    def cmd_status(self, agent_name: str, args: list) -> dict:
        """Show current session status for an agent.

        Args:
            agent_name: The agent whose status to show.
            args: Unused.

        Returns:
            Result dict with status details in ``data``.
        """
        active = self.engine.get_active_sessions(agent_name)

        if not active:
            identity = self.engine.get_wearer_identity(agent_name)
            if identity:
                return _ok(
                    f"No cartridge loaded for '{agent_name}'.",
                    {
                        "has_cartridge": False,
                        "sector": identity.sector_name,
                        "position": identity.position,
                        "precision": identity.precision,
                        "effective_position": identity.effective_position,
                        "degrees": identity.degrees,
                    },
                )
            return _ok(
                f"No cartridge loaded and no identity registered for '{agent_name}'.",
                {"has_cartridge": False},
            )

        # Report on the most recent session
        session = active[-1]
        data = {
            "has_cartridge": True,
            "session_count": len(active),
            "session_id": session.session_id,
            "cartridge_name": session.cartridge_name,
            "twin_agent": session.twin_agent_name,
            "original_sector": session.original_identity.sector_name,
            "current_sector": session.current_identity.sector_name,
            "current_position": session.current_identity.effective_position,
            "elapsed": round(session.elapsed(), 3),
            "actions": len(session.actions_taken),
        }
        if session.cartridge.is_time_limited():
            data["time_remaining"] = round(session.remaining(), 3)
        return _ok(f"Active session for '{agent_name}'.", data)

    def cmd_identity_dial(self, agent_name: str, args: list) -> dict:
        """Show the identity dial position for an agent.

        Args:
            agent_name: The agent whose dial to show.
            args: Optional ``[other_agent_name]`` to view another agent's dial.

        Returns:
            Result dict with dial info in ``data``.
        """
        target_name = agent_name
        if args:
            target_name = args[0].strip()

        identity = self.engine.get_wearer_identity(target_name)
        if identity is None:
            return _err(f"No identity registered for '{target_name}'.")

        # Adjacent sectors
        pos = identity.sector
        prev_sector = (pos - 1) % DIAL_POSITIONS
        next_sector = (pos + 1) % DIAL_POSITIONS

        return _ok(
            f"Identity dial for '{target_name}': {identity.sector_name} "
            f"(position {identity.effective_position:.4f}, "
            f"{identity.degrees:.1f}°)",
            {
                "agent": target_name,
                "position": identity.position,
                "precision": identity.precision,
                "effective_position": identity.effective_position,
                "sector": identity.sector,
                "sector_name": identity.sector_name,
                "degrees": identity.degrees,
                "adjacent_prev": IdentitySector.role_name(prev_sector),
                "adjacent_next": IdentitySector.role_name(next_sector),
            },
        )

    def cmd_identity_shift(self, agent_name: str, args: list) -> dict:
        """Shift perspective toward a target position.

        Args:
            agent_name: The agent shifting.
            args: ``[target_position_or_name] [amount]``

        Returns:
            Result dict with shift details in ``data``.
        """
        if not args:
            return _err("Usage: identity shift <target> [amount]")

        target_str = args[0].strip()
        target_pos, error = _resolve_target_position(target_str)
        if error:
            return _err(error)

        # Optional shift amount
        amount = None
        if len(args) > 1:
            amount = _parse_float(args[1])
            if amount is None or amount <= 0:
                return _err(f"Invalid shift amount '{args[1]}'. Must be a positive number.")

        active = self.engine.get_active_sessions(agent_name)
        if not active:
            return _err(
                f"No active cartridge session for '{agent_name}'. "
                f"Load a cartridge first."
            )

        session = active[-1]
        actual_shift = session.shift_perspective(target_pos, amount)

        return _ok(
            f"Perspective shifted by {actual_shift:.4f} toward "
            f"{IdentitySector.role_name(int(target_pos))} "
            f"(now {session.current_identity.effective_position:.4f}).",
            {
                "target": target_pos,
                "target_name": IdentitySector.role_name(int(target_pos)),
                "amount_requested": amount,
                "actual_shift": actual_shift,
                "new_position": session.current_identity.effective_position,
                "new_sector": session.current_identity.sector_name,
            },
        )

    def cmd_identity_blend(self, agent_name: str, args: list) -> dict:
        """Blend identity with another agent.

        Args:
            agent_name: The agent blending.
            args: ``[other_agent_name] [weight_a] [weight_b]``

        Returns:
            Result dict with blend details in ``data``.
        """
        if not args:
            return _err("Usage: identity blend <other_agent> [weight_a] [weight_b]")

        other_name = args[0].strip()
        if not other_name:
            return _err("Other agent name must not be empty.")

        # Resolve weights
        weight_a = 0.5
        weight_b = 0.5
        if len(args) > 1:
            wa = _parse_float(args[1])
            if wa is None:
                return _err(f"Invalid weight_a '{args[1]}'.")
            weight_a = wa
        if len(args) > 2:
            wb = _parse_float(args[2])
            if wb is None:
                return _err(f"Invalid weight_b '{args[2]}'.")
            weight_b = wb

        # Get current identity of the agent
        active = self.engine.get_active_sessions(agent_name)
        if active:
            identity_a = active[-1].current_identity
        else:
            identity_a = self.engine.get_wearer_identity(agent_name)
        if identity_a is None:
            return _err(f"No identity registered for '{agent_name}'.")

        # Get other agent's identity
        identity_b = self.engine.get_wearer_identity(other_name)
        if identity_b is None:
            return _err(f"No identity registered for '{other_name}'.")

        # Perform the blend
        blended = IdentityFusion.blend(identity_a, identity_b, weight_a, weight_b)

        return _ok(
            f"Blended identity: {identity_a.sector_name} + {identity_b.sector_name} "
            f"→ {blended.sector_name} (pos {blended.effective_position:.4f}).",
            {
                "identity_a": {
                    "agent": agent_name,
                    "sector": identity_a.sector_name,
                    "position": identity_a.effective_position,
                },
                "identity_b": {
                    "agent": other_name,
                    "sector": identity_b.sector_name,
                    "position": identity_b.effective_position,
                },
                "weight_a": weight_a,
                "weight_b": weight_b,
                "blended_sector": blended.sector_name,
                "blended_position": blended.effective_position,
            },
        )

    def cmd_compatibility(self, agent_name: str, args: list) -> dict:
        """Show compatibility score between the agent and another agent.

        Args:
            agent_name: The first agent.
            args: ``[other_agent_name]``

        Returns:
            Result dict with compatibility info in ``data``.
        """
        if not args:
            return _err("Usage: compatibility <other_agent>")

        other_name = args[0].strip()
        if not other_name:
            return _err("Other agent name must not be empty.")

        # Build snapshots from identities
        identity_a = self.engine.get_wearer_identity(agent_name)
        identity_b = self.engine.get_wearer_identity(other_name)

        if identity_a is None:
            return _err(f"No identity registered for '{agent_name}'.")
        if identity_b is None:
            return _err(f"No identity registered for '{other_name}'.")

        snap_a = AgentSnapshot(agent_name=agent_name, identity=identity_a)
        snap_b = AgentSnapshot(agent_name=other_name, identity=identity_b)

        score = IdentityFusion.compatibility_score(snap_a, snap_b)
        conflicts = IdentityFusion.conflict_areas(snap_a, snap_b)
        distance = identity_a.distance(identity_b)

        return _ok(
            f"Compatibility between '{agent_name}' and '{other_name}': "
            f"{score:.4f} (distance={distance:.2f}).",
            {
                "agent_a": agent_name,
                "agent_b": other_name,
                "score": score,
                "dial_distance": distance,
                "angular_distance": round(distance * (360.0 / DIAL_POSITIONS), 2),
                "conflicts": conflicts,
                "sector_a": identity_a.sector_name,
                "sector_b": identity_b.sector_name,
            },
        )

    def cmd_register(self, agent_name: str, args: list) -> dict:
        """Register an agent's identity on the dial.

        Args:
            agent_name: The agent to register (used as name).
            args: ``[position_or_name] [precision]``

        Returns:
            Result dict with registration details.
        """
        if len(args) < 1:
            return _err("Usage: register <position_or_name> [precision]")

        pos, error = _resolve_target_position(args[0].strip())
        if error:
            return _err(error)

        precision = 0.0
        if len(args) > 1:
            p = _parse_float(args[1])
            if p is None:
                return _err(f"Invalid precision '{args[1]}'. Must be a number 0-1.")
            precision = max(0.0, min(1.0, p))

        dial = IdentityDial(position=pos, precision=precision)
        self.engine.register_agent_identity(agent_name, dial)

        return _ok(
            f"Agent '{agent_name}' registered at {dial.sector_name} "
            f"(pos {dial.effective_position:.4f}).",
            {
                "agent": agent_name,
                "position": dial.position,
                "precision": dial.precision,
                "effective_position": dial.effective_position,
                "sector": dial.sector_name,
            },
        )

    def cmd_publish(self, agent_name: str, args: list) -> dict:
        """Publish a new cartridge from an agent's registered identity.

        Args:
            agent_name: The agent whose identity to snapshot.
            args: ``[cartridge_name] [trust_mode] [time_limit]``

        Returns:
            Result dict with publish details.
        """
        identity = self.engine.get_wearer_identity(agent_name)
        if identity is None:
            return _err(f"No identity registered for '{agent_name}'. Register first.")

        cart_name = args[0].strip() if args else f"twin-{agent_name}"
        if not cart_name:
            return _err("Cartridge name must not be empty.")

        trust_mode = TRUST_INHERIT_FULL
        if len(args) > 1:
            trust_mode = args[1].strip().lower()
            if trust_mode not in (TRUST_INHERIT_FULL, TRUST_INHERIT_PARTIAL,
                                 TRUST_INHERIT_NONE, TRUST_INHERIT_BLENDED):
                return _err(
                    f"Invalid trust mode '{trust_mode}'. "
                    f"Use: full, partial, none, blended."
                )

        time_limit = 0.0
        if len(args) > 2:
            tl = _parse_float(args[2])
            if tl is None or tl < 0:
                return _err(f"Invalid time limit '{args[2]}'. Must be a non-negative number.")
            time_limit = tl

        # Build the snapshot from existing registry if available
        existing_snap = self.engine.agent_snapshots.get(agent_name)
        if existing_snap:
            snap = existing_snap
        else:
            snap = AgentSnapshot(agent_name=agent_name, identity=identity)

        cartridge = TwinCartridge(
            snapshot=snap,
            cartridge_name=cart_name,
            trust_inheritance=trust_mode,
            time_limit=time_limit,
        )

        try:
            self.engine.publish_cartridge(cartridge)
        except ValueError as exc:
            return _err(str(exc))

        return _ok(
            f"Cartridge '{cart_name}' published.",
            {
                "cartridge_name": cart_name,
                "twin_agent": agent_name,
                "trust_inheritance": trust_mode,
                "time_limit": time_limit,
                "version": cartridge.version,
            },
        )

    def cmd_suggestion(self, agent_name: str, args: list) -> dict:
        """Get a cartridge suggestion based on a goal.

        Args:
            agent_name: The agent seeking a suggestion.
            args: ``[goal_description]``

        Returns:
            Result dict with suggestion details.
        """
        if not args:
            return _err("Usage: suggestion <goal_description>")

        goal = " ".join(args)
        if not goal.strip():
            return _err("Goal description must not be empty.")

        cart = self.engine.suggestion(agent_name, goal.strip())
        if cart is None:
            return _ok("No matching cartridge found for that goal.", {"cartridge": None})

        return _ok(
            f"Suggested cartridge: '{cart.cartridge_name}' "
            f"(twin of {cart.snapshot.agent_name}, {cart.snapshot.identity.sector_name}).",
            {
                "cartridge_name": cart.cartridge_name,
                "twin_agent": cart.snapshot.agent_name,
                "sector": cart.snapshot.identity.sector_name,
                "trust_inheritance": cart.trust_inheritance,
            },
        )

    def cmd_help(self, agent_name: str, args: list) -> dict:
        """Show available cartridge commands.

        Returns:
            Result dict with command help in ``data``.
        """
        commands = {
            "list": "List all published cartridges.",
            "load <name>": "Load a cartridge for your agent.",
            "eject [session_id]": "Eject current or specified cartridge session.",
            "status": "Show your current session status.",
            "identity dial [agent]": "Show identity dial position.",
            "identity shift <target> [amount]": "Shift perspective toward target.",
            "identity blend <agent> [wa] [wb]": "Blend identity with another agent.",
            "compatibility <agent>": "Show compatibility with another agent.",
            "blend <agent> [wa] [wb]": "Alias for identity blend.",
            "register <pos_or_name> [precision]": "Register your identity on the dial.",
            "publish <name> [trust] [time_limit]": "Publish a new cartridge.",
            "suggestion <goal>": "Get a cartridge suggestion for a goal.",
            "help": "Show this help message.",
        }
        lines = ["  " + cmd + "  —  " + desc for cmd, desc in commands.items()]
        return _ok("Cartridge commands:", {"commands": commands, "formatted": lines})
