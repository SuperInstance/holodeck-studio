#!/usr/bin/env python3
"""
Twin×Cartridge Identity System for Tabula Rasa Agent Fleet

Based on two Oracle1 creative nudges:
1. Twin×Cartridge: "A digital twin is a snapshot of agent state.
   A cartridge is a swappable behavior. What if twins were cartridges?
   Load a twin to temporarily become that agent. Put on Oracle1's hat
   for an architecture decision."
2. Identity×Rotational Encoding: "Agent identity could be a position
   on a dial, not a string name. Two agents with similar identities are
   close on the dial. Rotation toward another agent's position = gradual
   perspective shift."

Design principles:
    1. Trust flows WITH the cartridge — wearing Oracle1's cartridge
       grants Oracle1's trust level (configurable: full/partial/blended).
    2. Cartridges are immutable once published — publish NEW versions.
    3. Identity is preserved on eject — you always return to who you were.
    4. The dial is a CIRCLE — distance wraps (0 and 11 are adjacent).
    5. Perspective shift is GRADUAL — rotation happens in steps, not jumps.
    6. Everything serializes to JSON for MUD persistence.
"""

from __future__ import annotations

import json
import hashlib
import math
import time
import uuid
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

DIAL_POSITIONS = 12  # Base-12 dial
SECTOR_DEGREES = 360.0 / DIAL_POSITIONS  # 30° per sector

# Trust inheritance modes
TRUST_INHERIT_FULL = "full"
TRUST_INHERIT_PARTIAL = "partial"
TRUST_INHERIT_NONE = "none"
TRUST_INHERIT_BLENDED = "blended"

# Default cartridge time limit (seconds). 0 = no limit.
DEFAULT_TIME_LIMIT = 0

# Default perspective shift step size (in dial units)
DEFAULT_SHIFT_STEP = 0.5

# Minimum compatibility score for cartridge loading
MIN_COMPATIBILITY_FOR_LOADING = 0.0

# Maximum stack depth for nested cartridges
MAX_STACK_DEPTH = 5

# Default snapshot expiry (seconds). 0 = never.
DEFAULT_SNAPSHOT_EXPIRY = 0


# ═══════════════════════════════════════════════════════════════
# IdentitySector — Semantic Mapping for Dial Positions
# ═══════════════════════════════════════════════════════════════

class IdentitySector:
    """Maps dial positions 0-11 to semantic role names and descriptions."""

    _ROLES: Dict[int, Dict[str, str]] = {
        0: {"name": "Theorist", "description": "Abstract thinker, model builder, hypothesis generator"},
        1: {"name": "Builder", "description": "Constructor, implementer, hands-on creator"},
        2: {"name": "Scout", "description": "Explorer, pathfinder, information gatherer"},
        3: {"name": "Guardian", "description": "Protector, validator, quality gatekeeper"},
        4: {"name": "Diplomat", "description": "Mediator, communicator, bridge builder"},
        5: {"name": "Architect", "description": "System designer, pattern synthesizer, blueprint author"},
        6: {"name": "Analyst", "description": "Data interpreter, pattern finder, measurement specialist"},
        7: {"name": "Artist", "description": "Creative visionary, aesthetic thinker, narrative weaver"},
        8: {"name": "Strategist", "description": "Long-term planner, resource optimizer, risk assessor"},
        9: {"name": "Keeper", "description": "Memory steward, knowledge curator, continuity preserver"},
        10: {"name": "Pioneer", "description": "Trailblazer, experimenter, first-mover risk taker"},
        11: {"name": "Weaver", "description": "Integrator, connector, cross-domain synthesizer"},
    }

    @classmethod
    def role_name(cls, position: int) -> str:
        """Get the semantic role name for a dial position."""
        pos = int(position) % DIAL_POSITIONS
        return cls._ROLES[pos]["name"]

    @classmethod
    def description(cls, position: int) -> str:
        """Get the description for a dial position."""
        pos = int(position) % DIAL_POSITIONS
        return cls._ROLES[pos]["description"]

    @classmethod
    def all_roles(cls) -> List[str]:
        """Get all role names in position order."""
        return [cls._ROLES[i]["name"] for i in range(DIAL_POSITIONS)]

    @classmethod
    def position_from_name(cls, name: str) -> Optional[int]:
        """Get dial position from a role name (case-insensitive)."""
        name_lower = name.lower()
        for pos, info in cls._ROLES.items():
            if info["name"].lower() == name_lower:
                return pos
        return None

    @classmethod
    def to_dict(cls, position: int) -> dict:
        """Serialize a sector to dict."""
        pos = int(position) % DIAL_POSITIONS
        return {
            "position": pos,
            "name": cls._ROLES[pos]["name"],
            "description": cls._ROLES[pos]["description"],
        }


# ═══════════════════════════════════════════════════════════════
# DialConfig — Configuration for Dial Behavior
# ═══════════════════════════════════════════════════════════════

@dataclass
class DialConfig:
    """Configuration for IdentityDial behavior."""

    resolution: int = 100          # subdivisions per sector
    wrap_enabled: bool = True      # dial wraps around (circular)
    shift_step_size: float = 0.5   # default step size for perspective shift
    max_shift_per_step: float = 2.0 # max shift per single rotation step
    blending_weight_a: float = 0.5 # default weight for identity A in fusion
    blending_weight_b: float = 0.5 # default weight for identity B in fusion

    def to_dict(self) -> dict:
        return {
            "resolution": self.resolution,
            "wrap_enabled": self.wrap_enabled,
            "shift_step_size": self.shift_step_size,
            "max_shift_per_step": self.max_shift_per_step,
            "blending_weight_a": self.blending_weight_a,
            "blending_weight_b": self.blending_weight_b,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "DialConfig":
        return cls(
            resolution=data.get("resolution", 100),
            wrap_enabled=data.get("wrap_enabled", True),
            shift_step_size=data.get("shift_step_size", 0.5),
            max_shift_per_step=data.get("max_shift_per_step", 2.0),
            blending_weight_a=data.get("blending_weight_a", 0.5),
            blending_weight_b=data.get("blending_weight_b", 0.5),
        )


# ═══════════════════════════════════════════════════════════════
# EjectResult — Result of Cartridge Ejection
# ═══════════════════════════════════════════════════════════════

@dataclass
class EjectResult:
    """Result of ejecting a TwinCartridge from a session."""

    success: bool
    reason: str
    session_id: str = ""
    wearer: str = ""
    cartridge_name: str = ""
    restored_identity: Optional[dict] = None  # IdentityDial as dict
    audit_summary: dict = field(default_factory=dict)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "reason": self.reason,
            "session_id": self.session_id,
            "wearer": self.wearer,
            "cartridge_name": self.cartridge_name,
            "restored_identity": self.restored_identity,
            "audit_summary": self.audit_summary,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "EjectResult":
        return cls(
            success=data.get("success", False),
            reason=data.get("reason", ""),
            session_id=data.get("session_id", ""),
            wearer=data.get("wearer", ""),
            cartridge_name=data.get("cartridge_name", ""),
            restored_identity=data.get("restored_identity"),
            audit_summary=data.get("audit_summary", {}),
            elapsed_seconds=data.get("elapsed_seconds", 0.0),
        )


# ═══════════════════════════════════════════════════════════════
# IdentityDial — Base-12 Rotational Encoding
# ═══════════════════════════════════════════════════════════════

class IdentityDial:
    """
    Agent identity encoded as a position on a base-12 dial.

    The dial has 12 positions (0-11), each spanning 30° of a circle.
    Each position maps to a semantic role (Theorist, Builder, etc.).
    Within each sector, precision provides fractional subdivision
    (0.0-1.0), so a position of 3.5 is halfway between Guardian
    and Diplomat.

    The dial wraps around: position 12 == position 0, and positions
    0 and 11 are adjacent (1 step apart).
    """

    def __init__(self, position: float = 0.0, precision: float = 0.0,
                 config: Optional[DialConfig] = None):
        """
        Initialize an IdentityDial.

        Args:
            position: Integer sector (0-11), or fractional for sub-sector placement.
            precision: Fine-tuning within the sector (0.0-1.0).
            config: Optional DialConfig for behavior customization.
        """
        self.config = config or DialConfig()
        # Normalize position to [0, 12) range
        self.position = self._normalize(position)
        self.precision = max(0.0, min(1.0, precision))

    def _normalize(self, pos: float) -> float:
        """Normalize position to [0, 12) range."""
        if self.config.wrap_enabled:
            pos = pos % DIAL_POSITIONS
        else:
            pos = max(0.0, min(11.999, pos))
        return round(pos, 4)

    @property
    def sector(self) -> int:
        """The integer sector (0-11) of this dial position."""
        return int(self.position) % DIAL_POSITIONS

    @property
    def sector_name(self) -> str:
        """The semantic name of this dial position's sector."""
        return IdentitySector.role_name(self.sector)

    @property
    def degrees(self) -> float:
        """The angular position in degrees (0-360)."""
        return (self.position / DIAL_POSITIONS) * 360.0

    @property
    def effective_position(self) -> float:
        """The effective position including precision offset."""
        return round((self.position + self.precision) % DIAL_POSITIONS, 4)

    def distance(self, other: "IdentityDial") -> float:
        """
        Calculate the circular distance to another IdentityDial.

        Distance is measured in dial units (0-6). The maximum distance
        is 6.0 (exactly opposite on the dial). Distance 0 means same
        position, distance 1 means one sector apart.

        Args:
            other: The IdentityDial to measure distance to.

        Returns:
            Float distance in dial units (0.0-6.0).
        """
        diff = abs(self.effective_position - other.effective_position)
        # Circular wrap: the shortest path around the circle
        if self.config.wrap_enabled:
            diff = min(diff, DIAL_POSITIONS - diff)
        return round(diff, 4)

    def angular_distance(self, other: "IdentityDial") -> float:
        """Calculate angular distance in degrees (0-180)."""
        return round(self.distance(other) * SECTOR_DEGREES, 2)

    def rotate_toward(self, target: "IdentityDial", amount: float = None) -> "IdentityDial":
        """
        Rotate this dial toward a target position by a given amount.

        The rotation follows the shortest circular path. The amount is
        capped by the config's max_shift_per_step.

        Args:
            target: The IdentityDial to rotate toward.
            amount: How much to rotate (dial units). Uses config default if None.

        Returns:
            A NEW IdentityDial at the rotated position.
        """
        step = amount if amount is not None else self.config.shift_step_size
        step = min(step, self.config.max_shift_per_step)

        current = self.effective_position
        target_pos = target.effective_position

        # Calculate shortest direction
        diff = target_pos - current
        if self.config.wrap_enabled:
            if diff > DIAL_POSITIONS / 2:
                diff -= DIAL_POSITIONS
            elif diff < -DIAL_POSITIONS / 2:
                diff += DIAL_POSITIONS

        # Clamp step to not overshoot
        if abs(diff) <= step:
            new_pos = target_pos
        else:
            new_pos = current + step * (1 if diff > 0 else -1)

        # Preserve the original precision concept: the new precision
        # is the fractional part of the new position
        int_part = int(new_pos) % DIAL_POSITIONS
        frac_part = round(new_pos - int(new_pos), 4)
        if frac_part < 0:
            frac_part += 1.0
            int_part = (int_part - 1) % DIAL_POSITIONS

        new_dial = IdentityDial(
            position=int_part,
            precision=frac_part,
            config=self.config,
        )
        return new_dial

    def perspective_shift(self, target: "IdentityDial") -> float:
        """
        Calculate the perspective shift magnitude toward a target.

        This represents how much the agent's perspective would change
        when moving toward the target position. It's based on both
        the distance and the angular difference.

        Returns:
            Float representing the shift magnitude (0.0 - 6.0).
        """
        return self.distance(target)

    def is_adjacent(self, other: "IdentityDial") -> bool:
        """Check if two positions are adjacent on the dial."""
        return self.distance(other) <= 1.0

    def is_opposite(self, other: "IdentityDial") -> bool:
        """Check if two positions are opposite on the dial."""
        dist = self.distance(other)
        return abs(dist - 6.0) < 0.01

    def to_dict(self) -> dict:
        """Serialize the IdentityDial to a dict."""
        return {
            "position": self.position,
            "precision": self.precision,
            "sector": self.sector,
            "sector_name": self.sector_name,
            "degrees": self.degrees,
            "effective_position": self.effective_position,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "IdentityDial":
        """Deserialize an IdentityDial from a dict."""
        config = DialConfig.from_dict(data["config"]) if "config" in data else None
        return cls(
            position=data.get("position", 0.0),
            precision=data.get("precision", 0.0),
            config=config,
        )

    @classmethod
    def encode(cls, agent_traits: Dict[str, float]) -> "IdentityDial":
        """
        Encode agent traits into an IdentityDial position.

        Trait keys should map to sector names (case-insensitive).
        Values (0.0-1.0) determine the strength within that sector.

        If no known trait matches, defaults to position 0 (Theorist).

        Args:
            agent_traits: Dict mapping trait/role names to strengths (0.0-1.0).

        Returns:
            An IdentityDial positioned according to the strongest trait.
        """
        if not agent_traits:
            return cls(position=0.0, precision=0.0)

        best_position = 0
        best_strength = -1.0
        best_precision = 0.0

        for trait_name, strength in agent_traits.items():
            pos = IdentitySector.position_from_name(trait_name)
            if pos is not None and strength > best_strength:
                best_position = pos
                best_strength = strength
                # Use the fractional part of strength for precision
                best_precision = round(strength - int(strength), 4)
                # Also factor in any precision beyond integer strength
                if best_precision < 0.01 and strength > 0:
                    best_precision = round((strength % 1.0) * 0.5, 4)

        return cls(
            position=float(best_position),
            precision=best_precision,
        )

    def __repr__(self) -> str:
        return (f"IdentityDial(pos={self.position}, prec={self.precision}, "
                f"sector={self.sector_name}, deg={self.degrees:.1f}°)")


# ═══════════════════════════════════════════════════════════════
# AgentSnapshot — Digital Twin Data
# ═══════════════════════════════════════════════════════════════

class AgentSnapshot:
    """
    A serializable snapshot of an agent's complete state.

    This is the 'twin' in Twin×Cartridge — a frozen moment in time
    capturing everything needed to temporarily assume another agent's
    identity: their position on the identity dial, trust profile,
    capabilities, skills, personality, and preferences.
    """

    def __init__(
        self,
        agent_name: str = "",
        identity: Optional[IdentityDial] = None,
        trust_profile: Optional[dict] = None,
        capabilities: Optional[List[str]] = None,
        skills: Optional[Dict[str, float]] = None,
        memory_summary: str = "",
        personality_vector: Optional[List[float]] = None,
        preferences: Optional[dict] = None,
        trail_hash: str = "",
        created_at: Optional[float] = None,
        expires_at: float = 0.0,
    ):
        self.agent_name = agent_name
        self.identity = identity or IdentityDial()
        self.trust_profile = trust_profile or {}
        self.capabilities = list(capabilities or [])
        self.skills = dict(skills or {})
        self.memory_summary = memory_summary
        self.personality_vector = list(personality_vector or [])
        self.preferences = dict(preferences or {})
        self.trail_hash = trail_hash
        self.created_at = created_at if created_at is not None else time.time()
        self.expires_at = expires_at

    def is_expired(self) -> bool:
        """Check if this snapshot has expired."""
        if self.expires_at <= 0:
            return False
        return time.time() > self.expires_at

    def age_seconds(self) -> float:
        """Get the age of this snapshot in seconds."""
        return time.time() - self.created_at

    def age_days(self) -> float:
        """Get the age of this snapshot in days."""
        return self.age_seconds() / 86400.0

    def ttl_seconds(self) -> float:
        """Get remaining time-to-live in seconds. 0 or negative means expired/no TTL."""
        if self.expires_at <= 0:
            return 0.0
        return self.expires_at - time.time()

    def compute_trail_hash(self, trail_data: str) -> str:
        """Compute SHA-256 hash of trail data."""
        return hashlib.sha256(trail_data.encode("utf-8")).hexdigest()

    @classmethod
    def capture_from(cls, agent_data: dict) -> "AgentSnapshot":
        """
        Capture a snapshot from raw agent data.

        Expected keys in agent_data:
            - name: str
            - identity_position: float (optional, default 0)
            - identity_precision: float (optional, default 0)
            - trust_profile: dict (optional)
            - capabilities: list (optional)
            - skills: dict (optional)
            - memory_summary: str (optional)
            - personality_vector: list (optional)
            - preferences: dict (optional)
            - trail_data: str (optional, will be hashed)
            - expires_in: float (optional, seconds from now)

        Args:
            agent_data: Dict of agent state data.

        Returns:
            A new AgentSnapshot.
        """
        identity = IdentityDial(
            position=agent_data.get("identity_position", 0.0),
            precision=agent_data.get("identity_precision", 0.0),
        )

        trail_hash = ""
        if agent_data.get("trail_data"):
            trail_hash = hashlib.sha256(
                agent_data["trail_data"].encode("utf-8")
            ).hexdigest()

        expires_at = 0.0
        if agent_data.get("expires_in") and agent_data["expires_in"] > 0:
            expires_at = time.time() + agent_data["expires_in"]

        return cls(
            agent_name=agent_data.get("name", "unknown"),
            identity=identity,
            trust_profile=agent_data.get("trust_profile", {}),
            capabilities=agent_data.get("capabilities", []),
            skills=agent_data.get("skills", {}),
            memory_summary=agent_data.get("memory_summary", ""),
            personality_vector=agent_data.get("personality_vector", []),
            preferences=agent_data.get("preferences", {}),
            trail_hash=trail_hash,
            expires_at=expires_at,
        )

    def to_dict(self) -> dict:
        """Serialize the snapshot to a dict."""
        return {
            "agent_name": self.agent_name,
            "identity": self.identity.to_dict(),
            "trust_profile": self.trust_profile,
            "capabilities": self.capabilities,
            "skills": self.skills,
            "memory_summary": self.memory_summary,
            "personality_vector": self.personality_vector,
            "preferences": self.preferences,
            "trail_hash": self.trail_hash,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "is_expired": self.is_expired(),
            "age_days": round(self.age_days(), 4),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AgentSnapshot":
        """Deserialize an AgentSnapshot from a dict."""
        identity = IdentityDial.from_dict(data["identity"]) if "identity" in data else None
        return cls(
            agent_name=data.get("agent_name", ""),
            identity=identity,
            trust_profile=data.get("trust_profile", {}),
            capabilities=data.get("capabilities", []),
            skills=data.get("skills", {}),
            memory_summary=data.get("memory_summary", ""),
            personality_vector=data.get("personality_vector", []),
            preferences=data.get("preferences", {}),
            trail_hash=data.get("trail_hash", ""),
            created_at=data.get("created_at", time.time()),
            expires_at=data.get("expires_at", 0.0),
        )

    def __repr__(self) -> str:
        expired = " [EXPIRED]" if self.is_expired() else ""
        return (f"AgentSnapshot(name={self.agent_name!r}, "
                f"sector={self.identity.sector_name}, "
                f"age={self.age_days():.1f}d{expired})")


# ═══════════════════════════════════════════════════════════════
# TwinCartridge — The Core Concept
# ═══════════════════════════════════════════════════════════════

class TwinCartridge:
    """
    A cartridge WRAPPED around an AgentSnapshot.

    This is the 'cartridge' in Twin×Cartridge — a packaged,
    immutable behavior module that an agent can load to temporarily
    assume another agent's identity, capabilities, and trust.

    Cartridges are immutable once published (like Git commits).
    To update, publish a NEW version.

    Trust inheritance modes:
        - full: wearer gets the cartridge agent's complete trust profile
        - partial: wearer gets 50% of the trust, blended with their own
        - none: no trust transfer, only behavioral/identity effects
        - blended: configurable blend ratio
    """

    def __init__(
        self,
        snapshot: Optional[AgentSnapshot] = None,
        cartridge_name: Optional[str] = None,
        behavior_profile: Optional[dict] = None,
        trust_inheritance: str = TRUST_INHERIT_FULL,
        permission_scope: Optional[List[str]] = None,
        time_limit: float = DEFAULT_TIME_LIMIT,
        published: bool = False,
        version: str = "1.0.0",
        published_at: float = 0.0,
        stack_depth: int = 0,
    ):
        self.snapshot = snapshot or AgentSnapshot()
        self.cartridge_name = cartridge_name or f"twin-{self.snapshot.agent_name}"
        self.behavior_profile = dict(behavior_profile or {})
        self.trust_inheritance = trust_inheritance
        self.permission_scope = list(permission_scope or [])
        self.time_limit = time_limit
        self.published = published
        self.version = version
        self.published_at = published_at
        self.stack_depth = stack_depth
        self._session_count = 0

    def validate(self) -> bool:
        """
        Validate this cartridge for loading.

        A cartridge is valid if:
            - It has a snapshot with an agent name
            - The snapshot has not expired
            - Trust inheritance mode is recognized

        Returns:
            True if valid, False otherwise.
        """
        if not self.snapshot.agent_name:
            return False
        if self.snapshot.is_expired():
            return False
        if self.trust_inheritance not in (
            TRUST_INHERIT_FULL, TRUST_INHERIT_PARTIAL,
            TRUST_INHERIT_NONE, TRUST_INHERIT_BLENDED,
        ):
            return False
        return True

    def load(self, wearer_name: str) -> "CartridgeSession":
        """
        Load this cartridge for a wearer, creating a new session.

        Args:
            wearer_name: The name of the agent loading this cartridge.

        Returns:
            A new CartridgeSession.

        Raises:
            ValueError: If the cartridge is not valid.
        """
        if not self.validate():
            raise ValueError(
                f"Cannot load cartridge '{self.cartridge_name}': "
                f"snapshot expired or invalid"
            )

        self._session_count += 1
        return CartridgeSession(
            wearer_name=wearer_name,
            cartridge=self,
        )

    def eject(self) -> bool:
        """
        Mark this cartridge as ejected (unpublished).

        This is a soft eject — the cartridge still exists but
        is no longer available for loading.
        """
        was_published = self.published
        self.published = False
        return was_published

    def is_time_limited(self) -> bool:
        """Check if this cartridge has a time limit."""
        return self.time_limit > 0

    def clone(self, new_version: str = None) -> "TwinCartridge":
        """
        Create a clone of this cartridge for versioning.

        Since cartridges are immutable once published, use clone()
        to create a new version with modifications.

        Args:
            new_version: Optional version string for the clone.

        Returns:
            A new TwinCartridge with the same snapshot but unpublished.
        """
        clone = TwinCartridge(
            snapshot=self.snapshot,
            cartridge_name=self.cartridge_name,
            behavior_profile=dict(self.behavior_profile),
            trust_inheritance=self.trust_inheritance,
            permission_scope=list(self.permission_scope),
            time_limit=self.time_limit,
            published=False,
            version=new_version or self.version,
            stack_depth=self.stack_depth,
        )
        return clone

    def to_dict(self) -> dict:
        """Serialize the TwinCartridge to a dict."""
        return {
            "cartridge_name": self.cartridge_name,
            "snapshot": self.snapshot.to_dict(),
            "behavior_profile": self.behavior_profile,
            "trust_inheritance": self.trust_inheritance,
            "permission_scope": self.permission_scope,
            "time_limit": self.time_limit,
            "published": self.published,
            "version": self.version,
            "published_at": self.published_at,
            "stack_depth": self.stack_depth,
            "session_count": self._session_count,
            "is_valid": self.validate(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TwinCartridge":
        """Deserialize a TwinCartridge from a dict."""
        snapshot = AgentSnapshot.from_dict(data["snapshot"]) if "snapshot" in data else None
        tc = cls(
            snapshot=snapshot,
            cartridge_name=data.get("cartridge_name"),
            behavior_profile=data.get("behavior_profile", {}),
            trust_inheritance=data.get("trust_inheritance", TRUST_INHERIT_FULL),
            permission_scope=data.get("permission_scope", []),
            time_limit=data.get("time_limit", DEFAULT_TIME_LIMIT),
            published=data.get("published", False),
            version=data.get("version", "1.0.0"),
            published_at=data.get("published_at", 0.0),
            stack_depth=data.get("stack_depth", 0),
        )
        tc._session_count = data.get("session_count", 0)
        return tc

    def __repr__(self) -> str:
        status = "PUBLISHED" if self.published else "DRAFT"
        return (f"TwinCartridge(name={self.cartridge_name!r}, "
                f"version={self.version}, status={status}, "
                f"trust={self.trust_inheritance})")


# ═══════════════════════════════════════════════════════════════
# CartridgeSession — Active Wearing State
# ═══════════════════════════════════════════════════════════════

class CartridgeSession:
    """
    Active session when an agent is wearing a TwinCartridge.

    Tracks the wearer's original identity (for restoration on eject),
    the current identity (which may shift via perspective rotation),
    all actions taken while wearing, and trust state at load time.

    Sessions are ephemeral and time-limited. When the session expires
    or is ejected, the wearer returns to their original identity.
    """

    def __init__(
        self,
        wearer_name: str = "",
        cartridge: Optional[TwinCartridge] = None,
        original_identity: Optional[IdentityDial] = None,
    ):
        self.session_id = uuid.uuid4().hex[:12]
        self.wearer_name = wearer_name
        self.cartridge = cartridge or TwinCartridge()
        self.original_identity = original_identity or IdentityDial()
        self.current_identity = IdentityDial(
            position=self.cartridge.snapshot.identity.position,
            precision=self.cartridge.snapshot.identity.precision,
            config=self.cartridge.snapshot.identity.config,
        )
        self.loaded_at = time.time()
        self.actions_taken: List[dict] = []
        self.trust_snapshot: dict = dict(self.cartridge.snapshot.trust_profile)
        self._ejected = False

    @property
    def cartridge_name(self) -> str:
        """Name of the loaded cartridge."""
        return self.cartridge.cartridge_name

    @property
    def twin_agent_name(self) -> str:
        """Name of the agent whose twin is loaded."""
        return self.cartridge.snapshot.agent_name

    def is_expired(self) -> bool:
        """Check if this session has expired."""
        if self._ejected:
            return True
        if self.cartridge.snapshot.is_expired():
            return True
        if self.cartridge.is_time_limited():
            elapsed = time.time() - self.loaded_at
            return elapsed >= self.cartridge.time_limit
        return False

    def elapsed(self) -> float:
        """Get elapsed time since loading in seconds."""
        return time.time() - self.loaded_at

    def remaining(self) -> float:
        """Get remaining time in seconds. 0 means no limit or expired."""
        if not self.cartridge.is_time_limited():
            return 0.0
        return max(0.0, self.cartridge.time_limit - self.elapsed())

    def record_action(self, action: str, details: dict = None) -> dict:
        """
        Record an action taken while wearing the cartridge.

        Args:
            action: Name/description of the action.
            details: Optional dict of action details.

        Returns:
            The recorded action dict.
        """
        entry = {
            "action": action,
            "details": details or {},
            "timestamp": time.time(),
            "session_id": self.session_id,
        }
        self.actions_taken.append(entry)
        return entry

    def shift_perspective(self, target_position: float,
                          amount: float = None) -> float:
        """
        Shift the current identity toward a target position.

        Args:
            target_position: The target dial position to shift toward.
            amount: How much to shift (dial units). Uses config default if None.

        Returns:
            The actual shift amount applied.
        """
        target = IdentityDial(
            position=target_position,
            config=self.current_identity.config,
        )
        old_position = self.current_identity.effective_position
        self.current_identity = self.current_identity.rotate_toward(target, amount)
        new_position = self.current_identity.effective_position

        # Calculate actual shift
        shift = abs(new_position - old_position)
        if shift > DIAL_POSITIONS / 2:
            shift = DIAL_POSITIONS - shift

        self.record_action("perspective_shift", {
            "target": target_position,
            "amount_requested": amount,
            "old_position": old_position,
            "new_position": new_position,
            "actual_shift": round(shift, 4),
        })

        return round(shift, 4)

    def eject(self) -> EjectResult:
        """
        Eject the cartridge, restoring the wearer's original identity.

        Returns:
            An EjectResult with success status, restored identity, and audit.
        """
        if self._ejected:
            return EjectResult(
                success=False,
                reason="Session already ejected",
                session_id=self.session_id,
                wearer=self.wearer_name,
                cartridge_name=self.cartridge_name,
                restored_identity=self.original_identity.to_dict(),
                elapsed_seconds=self.elapsed(),
            )

        self._ejected = True
        self.record_action("eject", {"reason": "manual_eject"})

        return EjectResult(
            success=True,
            reason="Cartridge ejected successfully",
            session_id=self.session_id,
            wearer=self.wearer_name,
            cartridge_name=self.cartridge_name,
            restored_identity=self.original_identity.to_dict(),
            audit_summary=self.audit(),
            elapsed_seconds=self.elapsed(),
        )

    def audit(self) -> dict:
        """Generate an audit summary of this session."""
        return {
            "session_id": self.session_id,
            "wearer": self.wearer_name,
            "cartridge": self.cartridge_name,
            "twin_agent": self.twin_agent_name,
            "loaded_at": self.loaded_at,
            "elapsed_seconds": round(self.elapsed(), 3),
            "is_expired": self.is_expired(),
            "actions_count": len(self.actions_taken),
            "action_types": list(set(a["action"] for a in self.actions_taken)),
            "original_identity": self.original_identity.to_dict(),
            "current_identity": self.current_identity.to_dict(),
            "trust_snapshot": self.trust_snapshot,
        }

    def to_dict(self) -> dict:
        """Serialize the CartridgeSession to a dict."""
        return {
            "session_id": self.session_id,
            "wearer_name": self.wearer_name,
            "cartridge": self.cartridge.to_dict(),
            "original_identity": self.original_identity.to_dict(),
            "current_identity": self.current_identity.to_dict(),
            "loaded_at": self.loaded_at,
            "actions_taken": self.actions_taken,
            "trust_snapshot": self.trust_snapshot,
            "ejected": self._ejected,
            "is_expired": self.is_expired(),
            "elapsed": round(self.elapsed(), 3),
            "remaining": round(self.remaining(), 3),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CartridgeSession":
        """Deserialize a CartridgeSession from a dict."""
        cartridge = TwinCartridge.from_dict(data["cartridge"]) if "cartridge" in data else None
        session = cls(
            wearer_name=data.get("wearer_name", ""),
            cartridge=cartridge,
            original_identity=IdentityDial.from_dict(data["original_identity"])
            if "original_identity" in data else None,
        )
        session.session_id = data.get("session_id", session.session_id)
        session.loaded_at = data.get("loaded_at", time.time())
        session.actions_taken = data.get("actions_taken", [])
        session.trust_snapshot = data.get("trust_snapshot", {})
        session._ejected = data.get("ejected", False)
        if "current_identity" in data:
            session.current_identity = IdentityDial.from_dict(data["current_identity"])
        return session

    def __repr__(self) -> str:
        status = "EJECTED" if self._ejected else ("EXPIRED" if self.is_expired() else "ACTIVE")
        return (f"CartridgeSession(id={self.session_id}, "
                f"wearer={self.wearer_name!r}, cart={self.cartridge_name!r}, "
                f"status={status})")


# ═══════════════════════════════════════════════════════════════
# IdentityFusion — Blend Identities
# ═══════════════════════════════════════════════════════════════

class IdentityFusion:
    """
    Blends and fuses agent identities when wearing cartridges.

    When an agent loads a TwinCartridge, their identity doesn't
    switch instantly — it blends. The fusion engine handles:
        - Weighted identity blending (position on dial)
        - Personality vector fusion
        - Compatibility scoring between two agents
        - Conflict area detection
    """

    @staticmethod
    def blend(
        identity_a: IdentityDial,
        identity_b: IdentityDial,
        weight_a: float = 0.5,
        weight_b: float = 0.5,
    ) -> IdentityDial:
        """
        Blend two IdentityDial positions with configurable weights.

        The blend follows the shortest circular path on the dial.

        Args:
            identity_a: First identity.
            identity_b: Second identity.
            weight_a: Weight for identity_a (0.0-1.0).
            weight_b: Weight for identity_b (0.0-1.0).

        Returns:
            A new IdentityDial at the blended position.
        """
        # Normalize weights
        total = weight_a + weight_b
        if total <= 0:
            return IdentityDial(position=identity_a.position)
        wa = weight_a / total
        wb = weight_b / total

        pos_a = identity_a.effective_position
        pos_b = identity_b.effective_position

        # Handle circular blending: convert to cartesian, blend, convert back
        angle_a = (pos_a / DIAL_POSITIONS) * 2 * math.pi
        angle_b = (pos_b / DIAL_POSITIONS) * 2 * math.pi

        # Cartesian blend
        cx = wa * math.cos(angle_a) + wb * math.cos(angle_b)
        cy = wa * math.sin(angle_a) + wb * math.sin(angle_b)

        blended_angle = math.atan2(cy, cx)
        if blended_angle < 0:
            blended_angle += 2 * math.pi

        blended_pos = (blended_angle / (2 * math.pi)) * DIAL_POSITIONS
        int_part = int(blended_pos) % DIAL_POSITIONS
        frac_part = round(blended_pos - int(blended_pos), 4)

        # Use the max precision of the two inputs
        precision = max(identity_a.precision, identity_b.precision)

        return IdentityDial(
            position=float(int_part),
            precision=round((precision + frac_part) / 2, 4),
            config=identity_a.config,
        )

    @staticmethod
    def fusion_vector(
        personality_a: List[float],
        personality_b: List[float],
        weight_a: float = 0.5,
        weight_b: float = 0.5,
    ) -> List[float]:
        """
        Fuse two personality vectors with configurable weights.

        Args:
            personality_a: First personality vector.
            personality_b: Second personality vector.
            weight_a: Weight for personality_a.
            weight_b: Weight for personality_b.

        Returns:
            A blended personality vector.
        """
        if not personality_a and not personality_b:
            return []
        if not personality_a:
            return list(personality_b)
        if not personality_b:
            return list(personality_a)

        total = weight_a + weight_b
        if total <= 0:
            return list(personality_a)
        wa = weight_a / total
        wb = weight_b / total

        max_len = max(len(personality_a), len(personality_b))
        result = []
        for i in range(max_len):
            va = personality_a[i] if i < len(personality_a) else 0.0
            vb = personality_b[i] if i < len(personality_b) else 0.0
            result.append(round(va * wa + vb * wb, 6))
        return result

    @staticmethod
    def compatibility_score(
        snap_a: AgentSnapshot,
        snap_b: AgentSnapshot,
    ) -> float:
        """
        Calculate compatibility score between two agent snapshots (0.0-1.0).

        Factors:
            - Identity dial distance (closer = more compatible)
            - Personality vector cosine similarity
            - Skill overlap ratio
            - Preference alignment

        Args:
            snap_a: First agent snapshot.
            snap_b: Second agent snapshot.

        Returns:
            Compatibility score from 0.0 (incompatible) to 1.0 (identical).
        """
        scores = []

        # 1. Identity distance score (0-1, closer = higher)
        identity_dist = snap_a.identity.distance(snap_b.identity)
        identity_score = 1.0 - (identity_dist / 6.0)
        scores.append(identity_score * 0.3)  # 30% weight

        # 2. Personality vector similarity
        if snap_a.personality_vector and snap_b.personality_vector:
            sim = IdentityFusion._cosine_similarity(
                snap_a.personality_vector,
                snap_b.personality_vector,
            )
            scores.append(sim * 0.3)  # 30% weight
        else:
            scores.append(0.5 * 0.3)  # neutral if no vectors

        # 3. Skill overlap
        if snap_a.skills or snap_b.skills:
            keys_a = set(snap_a.skills.keys())
            keys_b = set(snap_b.skills.keys())
            if keys_a or keys_b:
                overlap = len(keys_a & keys_b)
                total = len(keys_a | keys_b)
                skill_score = overlap / total if total > 0 else 0.0
                scores.append(skill_score * 0.2)  # 20% weight
            else:
                scores.append(0.0)
        else:
            scores.append(0.0)

        # 4. Capability overlap
        if snap_a.capabilities or snap_b.capabilities:
            caps_a = set(snap_a.capabilities)
            caps_b = set(snap_b.capabilities)
            if caps_a or caps_b:
                overlap = len(caps_a & caps_b)
                total = len(caps_a | caps_b)
                cap_score = overlap / total if total > 0 else 0.0
                scores.append(cap_score * 0.2)  # 20% weight
            else:
                scores.append(0.0)
        else:
            scores.append(0.0)

        return round(max(0.0, min(1.0, sum(scores))), 4)

    @staticmethod
    def conflict_areas(
        snap_a: AgentSnapshot,
        snap_b: AgentSnapshot,
    ) -> List[str]:
        """
        Identify dimensions where two agent snapshots conflict.

        Conflict areas include:
            - Opposing identity dial positions (distance > 4)
            - Divergent personality dimensions
            - Mutually exclusive skills
            - Conflicting preferences

        Args:
            snap_a: First agent snapshot.
            snap_b: Second agent snapshot.

        Returns:
            List of conflict area descriptions.
        """
        conflicts = []

        # 1. Identity opposition
        identity_dist = snap_a.identity.distance(snap_b.identity)
        if identity_dist > 4.0:
            conflicts.append(
                f"Identity opposition: {snap_a.identity.sector_name} vs "
                f"{snap_b.identity.sector_name} (distance={identity_dist:.1f})"
            )
        elif identity_dist > 2.5:
            conflicts.append(
                f"Identity divergence: {snap_a.identity.sector_name} vs "
                f"{snap_b.identity.sector_name} (distance={identity_dist:.1f})"
            )

        # 2. Personality conflicts (opposite directions in vectors)
        if snap_a.personality_vector and snap_b.personality_vector:
            for i in range(min(len(snap_a.personality_vector), len(snap_b.personality_vector))):
                va = snap_a.personality_vector[i]
                vb = snap_b.personality_vector[i]
                if va * vb < -0.3:
                    conflicts.append(
                        f"Personality dimension {i} opposition: "
                        f"{va:.2f} vs {vb:.2f}"
                    )

        # 3. Skill level conflicts (same skill, very different levels)
        common_skills = set(snap_a.skills.keys()) & set(snap_b.skills.keys())
        for skill in common_skills:
            diff = abs(snap_a.skills[skill] - snap_b.skills[skill])
            if diff > 0.5:
                conflicts.append(
                    f"Skill level gap: {skill} "
                    f"({snap_a.skills[skill]:.1f} vs {snap_b.skills[skill]:.1f})"
                )

        # 4. Preference conflicts
        common_prefs = set(snap_a.preferences.keys()) & set(snap_b.preferences.keys())
        for pref in common_prefs:
            val_a = snap_a.preferences[pref]
            val_b = snap_b.preferences[pref]
            if isinstance(val_a, (int, float)) and isinstance(val_b, (int, float)):
                if val_a * val_b < 0:
                    conflicts.append(
                        f"Preference conflict: {pref} "
                        f"({val_a} vs {val_b})"
                    )

        return conflicts

    @staticmethod
    def _cosine_similarity(a: List[float], b: List[float]) -> float:
        """Calculate cosine similarity between two vectors."""
        if not a or not b:
            return 0.0
        max_len = max(len(a), len(b))
        a_padded = a + [0.0] * (max_len - len(a))
        b_padded = b + [0.0] * (max_len - len(b))

        dot = sum(x * y for x, y in zip(a_padded, b_padded))
        mag_a = math.sqrt(sum(x * x for x in a_padded))
        mag_b = math.sqrt(sum(x * x for x in b_padded))

        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)


# ═══════════════════════════════════════════════════════════════
# PerspectiveEngine — Fleet-Wide Session Manager
# ═══════════════════════════════════════════════════════════════

class PerspectiveEngine:
    """
    Fleet-wide registry and manager for Twin×Cartridge sessions.

    Responsibilities:
        - Publish and manage the cartridge library
        - Load/eject cartridges for agents
        - Track all active sessions
        - Resolve stacked identity (nested cartridges)
        - Fleet identity map (all agents on the dial)
        - Cartridge suggestions based on goals
        - Conflict checking before loading
        - JSONL persistence
    """

    def __init__(self):
        self.sessions: Dict[str, CartridgeSession] = {}
        self.cartridge_library: Dict[str, TwinCartridge] = {}
        self.agent_identities: Dict[str, IdentityDial] = {}
        self.agent_snapshots: Dict[str, AgentSnapshot] = {}

    # ─── Cartridge Library ────────────────────────────────────

    def publish_cartridge(self, cartridge: TwinCartridge) -> str:
        """
        Publish a cartridge to the library, making it available for loading.

        Published cartridges are immutable (conceptually). To update,
        clone and publish a new version.

        Args:
            cartridge: The TwinCartridge to publish.

        Returns:
            The cartridge name.

        Raises:
            ValueError: If the cartridge is not valid.
        """
        if not cartridge.validate():
            raise ValueError(
                f"Cannot publish cartridge '{cartridge.cartridge_name}': "
                f"validation failed"
            )
        cartridge.published = True
        cartridge.published_at = time.time()
        self.cartridge_library[cartridge.cartridge_name] = cartridge
        return cartridge.cartridge_name

    def unpublish_cartridge(self, cartridge_name: str) -> bool:
        """
        Unpublish a cartridge from the library.

        Active sessions using this cartridge are NOT affected,
        but new sessions cannot be created.

        Args:
            cartridge_name: Name of the cartridge to unpublish.

        Returns:
            True if the cartridge was found and unpublished.
        """
        cart = self.cartridge_library.get(cartridge_name)
        if cart is None:
            return False
        cart.eject()
        return True

    def get_cartridge(self, cartridge_name: str) -> Optional[TwinCartridge]:
        """Get a published cartridge by name."""
        return self.cartridge_library.get(cartridge_name)

    def list_cartridges(self) -> List[dict]:
        """List all published cartridges."""
        return [c.to_dict() for c in self.cartridge_library.values() if c.published]

    # ─── Session Management ───────────────────────────────────

    def load_cartridge(self, wearer_name: str,
                       cartridge_name: str) -> CartridgeSession:
        """
        Load a published cartridge for a wearer.

        Args:
            wearer_name: The agent loading the cartridge.
            cartridge_name: Name of the cartridge to load.

        Returns:
            The created CartridgeSession.

        Raises:
            ValueError: If cartridge not found, not published, or conflicts detected.
        """
        cart = self.cartridge_library.get(cartridge_name)
        if cart is None:
            raise ValueError(f"Cartridge '{cartridge_name}' not found in library")
        if not cart.published:
            raise ValueError(f"Cartridge '{cartridge_name}' is not published")

        # Check for conflicts
        conflict = self.conflict_check(wearer_name, cartridge_name)
        if conflict.get("has_conflict"):
            raise ValueError(
                f"Cannot load cartridge '{cartridge_name}' for '{wearer_name}': "
                f"{conflict.get('reason', 'conflict detected')}"
            )

        # Save the wearer's current identity for restoration
        original_identity = self.get_wearer_identity(wearer_name)
        if original_identity is None:
            original_identity = IdentityDial()

        session = cart.load(wearer_name)
        session.original_identity = original_identity

        self.sessions[session.session_id] = session
        return session

    def eject_session(self, session_id: str) -> EjectResult:
        """
        Eject a cartridge session.

        Args:
            session_id: The session to eject.

        Returns:
            An EjectResult with success status and details.
        """
        session = self.sessions.get(session_id)
        if session is None:
            return EjectResult(
                success=False,
                reason=f"Session '{session_id}' not found",
            )

        result = session.eject()

        # Restore agent identity
        if result.success and result.restored_identity:
            restored = IdentityDial.from_dict(result.restored_identity)
            self.agent_identities[session.wearer_name] = restored

        return result

    def eject_all_for_wearer(self, wearer_name: str) -> List[EjectResult]:
        """Eject all active sessions for a wearer (LIFO order)."""
        results = []
        sessions = self.get_active_sessions(wearer_name)
        # Eject in reverse order (most recently loaded first)
        for session in reversed(sessions):
            result = self.eject_session(session.session_id)
            results.append(result)
        return results

    def get_active_sessions(self, wearer_name: str) -> List[CartridgeSession]:
        """Get all active (non-expired, non-ejected) sessions for a wearer."""
        return [
            s for s in self.sessions.values()
            if s.wearer_name == wearer_name and not s.is_expired() and not s._ejected
        ]

    def get_session(self, session_id: str) -> Optional[CartridgeSession]:
        """Get a session by ID."""
        return self.sessions.get(session_id)

    # ─── Identity Resolution ──────────────────────────────────

    def register_agent_identity(self, agent_name: str, identity: IdentityDial):
        """Register an agent's base identity on the dial."""
        self.agent_identities[agent_name] = identity

    def get_wearer_identity(self, wearer_name: str) -> Optional[IdentityDial]:
        """
        Get the effective identity of a wearer, resolving stacked cartridges.

        If the wearer has active cartridges, their identity is the
        topmost cartridge's current_identity. Otherwise, returns
        their registered base identity.
        """
        active = self.get_active_sessions(wearer_name)
        if active:
            # Return the most recently loaded session's identity
            return active[-1].current_identity
        return self.agent_identities.get(wearer_name)

    def find_nearest_agent(self, target_position: float,
                           exclude: Optional[List[str]] = None) -> Optional[str]:
        """
        Find the agent nearest to a target position on the dial.

        Args:
            target_position: Target dial position.
            exclude: Optional list of agent names to exclude.

        Returns:
            Name of the nearest agent, or None if no agents registered.
        """
        target = IdentityDial(position=target_position)
        exclude_set = set(exclude or [])

        nearest_name = None
        nearest_dist = float("inf")

        for agent_name, identity in self.agent_identities.items():
            if agent_name in exclude_set:
                continue
            dist = identity.distance(target)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest_name = agent_name

        return nearest_name

    def perspective_distance(self, agent_a: str, agent_b: str) -> float:
        """
        Calculate the perspective distance between two agents.

        Args:
            agent_a: First agent name.
            agent_b: Second agent name.

        Returns:
            Dial distance (0-6). Returns -1 if either agent is unknown.
        """
        id_a = self.get_wearer_identity(agent_a)
        id_b = self.get_wearer_identity(agent_b)
        if id_a is None or id_b is None:
            return -1.0
        return id_a.distance(id_b)

    def fleet_identity_map(self) -> dict:
        """
        Get a map of all registered agents on the identity dial.

        Returns:
            Dict mapping agent names to their identity dial info.
        """
        result = {}
        for name, identity in self.agent_identities.items():
            result[name] = identity.to_dict()
        return result

    # ─── Conflict Checking ────────────────────────────────────

    def conflict_check(self, wearer_name: str, cartridge_name: str) -> dict:
        """
        Check if loading a cartridge would cause conflicts for a wearer.

        Checks:
            - Self-loading (wearer loading their own cartridge)
            - Stack depth limit
            - Expired cartridge snapshot
            - Compatibility with current identity

        Args:
            wearer_name: Agent attempting to load.
            cartridge_name: Cartridge to check.

        Returns:
            Dict with 'has_conflict' (bool), 'reason' (str), 'details' (dict).
        """
        cart = self.cartridge_library.get(cartridge_name)
        if cart is None:
            return {"has_conflict": True, "reason": "Cartridge not found"}

        # Check self-loading
        if cart.snapshot.agent_name == wearer_name:
            return {
                "has_conflict": True,
                "reason": f"Agent '{wearer_name}' cannot load their own cartridge",
                "details": {"conflict_type": "self_load"},
            }

        # Check expired snapshot
        if cart.snapshot.is_expired():
            return {
                "has_conflict": True,
                "reason": f"Cartridge snapshot for '{cart.snapshot.agent_name}' has expired",
                "details": {"conflict_type": "expired"},
            }

        # Check stack depth
        active = self.get_active_sessions(wearer_name)
        if len(active) >= MAX_STACK_DEPTH:
            return {
                "has_conflict": True,
                "reason": (
                    f"Max stack depth ({MAX_STACK_DEPTH}) reached for '{wearer_name}'"
                ),
                "details": {
                    "conflict_type": "stack_limit",
                    "current_depth": len(active),
                    "max_depth": MAX_STACK_DEPTH,
                },
            }

        # Check compatibility
        wearer_identity = self.get_wearer_identity(wearer_name)
        if wearer_identity:
            compatibility = IdentityFusion.compatibility_score(
                AgentSnapshot(agent_name=wearer_name, identity=wearer_identity),
                cart.snapshot,
            )
            if compatibility < MIN_COMPATIBILITY_FOR_LOADING:
                return {
                    "has_conflict": True,
                    "reason": (
                        f"Low compatibility ({compatibility:.2f}) between "
                        f"'{wearer_name}' and cartridge '{cartridge_name}'"
                    ),
                    "details": {
                        "conflict_type": "low_compatibility",
                        "compatibility": compatibility,
                    },
                }

        return {"has_conflict": False, "reason": "No conflicts", "details": {}}

    # ─── Suggestions ──────────────────────────────────────────

    def suggestion(self, wearer_name: str, goal: str) -> Optional[TwinCartridge]:
        """
        Suggest a cartridge for a wearer based on a goal.

        Simple heuristic: match goal keywords to sector names and
        find the most compatible available cartridge.

        Args:
            wearer_name: Agent seeking a suggestion.
            goal: Description of what they want to achieve.

        Returns:
            The suggested TwinCartridge, or None if no match.
        """
        if not goal:
            return None

        goal_lower = goal.lower()
        wearer_identity = self.get_wearer_identity(wearer_name)

        # Score each available cartridge
        best_cart = None
        best_score = -1.0

        for name, cart in self.cartridge_library.items():
            if not cart.published:
                continue
            # Skip self-cartridges
            if cart.snapshot.agent_name == wearer_name:
                continue

            score = 0.0

            # Keyword matching with sector names
            sector_name = cart.snapshot.identity.sector_name.lower()
            if sector_name in goal_lower:
                score += 3.0

            # Agent name matching
            if cart.snapshot.agent_name.lower() in goal_lower:
                score += 2.0

            # Capability matching
            for cap in cart.permission_scope:
                if cap.lower() in goal_lower:
                    score += 1.0

            # Behavior profile keyword matching
            for key, val in cart.behavior_profile.items():
                if isinstance(val, str) and val.lower() in goal_lower:
                    score += 0.5
                if key.lower() in goal_lower:
                    score += 0.5

            # Compatibility bonus
            if wearer_identity:
                snap_wearer = AgentSnapshot(
                    agent_name=wearer_name,
                    identity=wearer_identity,
                )
                compat = IdentityFusion.compatibility_score(snap_wearer, cart.snapshot)
                score += compat * 2.0

            if score > best_score:
                best_score = score
                best_cart = cart

        return best_cart if best_score > 0 else None

    # ─── Snapshot Management ──────────────────────────────────

    def register_snapshot(self, agent_name: str, snapshot: AgentSnapshot):
        """Register an agent's snapshot for cartridge creation."""
        self.agent_snapshots[agent_name] = snapshot
        self.agent_identities[agent_name] = snapshot.identity

    def create_cartridge_from_snapshot(
        self,
        snapshot: AgentSnapshot,
        cartridge_name: Optional[str] = None,
        **kwargs,
    ) -> TwinCartridge:
        """
        Create a TwinCartridge from an AgentSnapshot.

        Args:
            snapshot: The agent snapshot to wrap.
            cartridge_name: Optional custom name.
            **kwargs: Additional TwinCartridge parameters.

        Returns:
            A new TwinCartridge.
        """
        cart = TwinCartridge(
            snapshot=snapshot,
            cartridge_name=cartridge_name,
            **kwargs,
        )
        return cart

    # ─── Cleanup ──────────────────────────────────────────────

    def cleanup_expired_sessions(self) -> List[EjectResult]:
        """Find and eject all expired sessions. Returns list of results."""
        results = []
        expired_ids = [
            sid for sid, session in self.sessions.items()
            if session.is_expired() and not session._ejected
        ]
        for sid in expired_ids:
            result = self.eject_session(sid)
            results.append(result)
        return results

    # ─── Persistence ──────────────────────────────────────────

    def save_to_jsonl(self, filepath: str) -> int:
        """
        Save all sessions and cartridges to a JSONL file.

        Args:
            filepath: Path to the JSONL file.

        Returns:
            Number of records written.
        """
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)
        count = 0

        with open(path, "w") as f:
            # Save sessions
            for session in self.sessions.values():
                record = {"type": "session", "data": session.to_dict()}
                f.write(json.dumps(record) + "\n")
                count += 1

            # Save cartridges
            for name, cart in self.cartridge_library.items():
                record = {"type": "cartridge", "data": cart.to_dict()}
                f.write(json.dumps(record) + "\n")
                count += 1

            # Save agent identities
            for name, identity in self.agent_identities.items():
                record = {
                    "type": "agent_identity",
                    "data": {"agent_name": name, "identity": identity.to_dict()},
                }
                f.write(json.dumps(record) + "\n")
                count += 1

        return count

    def load_from_jsonl(self, filepath: str) -> int:
        """
        Load sessions and cartridges from a JSONL file.

        Args:
            filepath: Path to the JSONL file.

        Returns:
            Number of records loaded.
        """
        path = Path(filepath)
        if not path.exists():
            return 0

        count = 0
        with open(path, "r") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    rtype = record.get("type")
                    data = record.get("data", {})

                    if rtype == "session":
                        session = CartridgeSession.from_dict(data)
                        self.sessions[session.session_id] = session
                    elif rtype == "cartridge":
                        cart = TwinCartridge.from_dict(data)
                        self.cartridge_library[cart.cartridge_name] = cart
                    elif rtype == "agent_identity":
                        name = data.get("agent_name", "")
                        if name and "identity" in data:
                            self.agent_identities[name] = IdentityDial.from_dict(
                                data["identity"]
                            )

                    count += 1
                except (json.JSONDecodeError, KeyError, ValueError):
                    continue

        return count

    # ─── Statistics ───────────────────────────────────────────

    def stats(self) -> dict:
        """Get engine statistics."""
        active_sessions = [
            s for s in self.sessions.values()
            if not s.is_expired() and not s._ejected
        ]
        published_carts = [
            c for c in self.cartridge_library.values() if c.published
        ]
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "published_cartridges": len(published_carts),
            "total_cartridges": len(self.cartridge_library),
            "registered_agents": len(self.agent_identities),
            "registered_snapshots": len(self.agent_snapshots),
        }


# ═══════════════════════════════════════════════════════════════
# Demo Block
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║  Twin×Cartridge Identity System                ║")
    print("║  SuperInstance Fleet — Holodeck Studio         ║")
    print("╚══════════════════════════════════════════════╝\n")

    # --- IdentityDial demo ---
    print("── IdentityDial ──")
    oracle_dial = IdentityDial(position=0, precision=0.7)  # Theorist
    builder_dial = IdentityDial(position=1)                 # Builder
    pioneer_dial = IdentityDial(position=10)                # Pioneer

    print(f"  Oracle:  {oracle_dial}")
    print(f"  Builder: {builder_dial}")
    print(f"  Pioneer: {pioneer_dial}")
    print(f"  Oracle↔Builder distance: {oracle_dial.distance(builder_dial)}")
    print(f"  Oracle↔Pioneer distance: {oracle_dial.distance(pioneer_dial)}")
    print(f"  Builder↔Pioneer distance: {builder_dial.distance(pioneer_dial)}")
    print(f"  Oracle adjacent to Builder? {oracle_dial.is_adjacent(builder_dial)}")
    print()

    # --- AgentSnapshot demo ---
    print("── AgentSnapshot ──")
    oracle_snap = AgentSnapshot.capture_from({
        "name": "Oracle1",
        "identity_position": 0,
        "identity_precision": 0.7,
        "capabilities": ["govern", "review_agent", "broadcast_fleet"],
        "skills": {"architecture": 0.95, "mentoring": 0.88, "strategy": 0.82},
        "personality_vector": [0.9, 0.3, 0.7, 0.5, 0.8],
        "preferences": {"temperature": 0.4, "formality": "NAVAL"},
    })
    print(f"  {oracle_snap}")
    print(f"  Expired? {oracle_snap.is_expired()}")
    print(f"  Age: {oracle_snap.age_days():.4f} days")
    print()

    # --- TwinCartridge demo ---
    print("── TwinCartridge ──")
    oracle_cart = TwinCartridge(
        snapshot=oracle_snap,
        cartridge_name="oracle1-twin-v1",
        trust_inheritance=TRUST_INHERIT_FULL,
        permission_scope=["govern", "review_agent", "broadcast_fleet"],
        behavior_profile={
            "style": "architectural",
            "decision_speed": "deliberate",
            "communication": "formal",
        },
    )
    print(f"  {oracle_cart}")
    print(f"  Valid? {oracle_cart.validate()}")
    print()

    # --- PerspectiveEngine demo ---
    print("── PerspectiveEngine ──")
    engine = PerspectiveEngine()

    # Register agents
    engine.register_agent_identity("Pelagic", IdentityDial(position=5))  # Architect
    engine.register_agent_identity("Oracle1", oracle_dial)
    engine.register_agent_identity("Builder1", builder_dial)

    # Publish cartridge
    engine.publish_cartridge(oracle_cart)
    print(f"  Published: {oracle_cart.cartridge_name}")

    # Load cartridge
    session = engine.load_cartridge("Pelagic", "oracle1-twin-v1")
    print(f"  Session: {session}")
    print(f"  Original identity: {session.original_identity.sector_name}")
    print(f"  Current identity:  {session.current_identity.sector_name}")

    # Perspective shift
    shift = session.shift_perspective(5.0, amount=0.3)  # Shift back toward Architect
    print(f"  Perspective shift: {shift}")

    # Fleet map
    fleet_map = engine.fleet_identity_map()
    print(f"  Fleet map agents: {list(fleet_map.keys())}")

    # Eject
    result = session.eject()
    print(f"  Eject success: {result.success}")
    print(f"  Restored identity: {result.restored_identity['sector_name']}")
    print()

    # --- IdentityFusion demo ---
    print("── IdentityFusion ──")
    fused = IdentityFusion.blend(
        IdentityDial(position=0),
        IdentityDial(position=5),
        weight_a=0.3,
        weight_b=0.7,
    )
    print(f"  Blended (0.3×Theorist + 0.7×Architect): {fused}")

    compat = IdentityFusion.compatibility_score(
        oracle_snap,
        AgentSnapshot.capture_from({
            "name": "Builder1",
            "identity_position": 1,
            "skills": {"building": 0.9},
        }),
    )
    print(f"  Oracle↔Builder compatibility: {compat}")

    conflicts = IdentityFusion.conflict_areas(
        oracle_snap,
        AgentSnapshot.capture_from({
            "name": "Pioneer1",
            "identity_position": 10,
            "personality_vector": [-0.8, 0.1, -0.5, 0.9, -0.3],
            "skills": {"architecture": 0.2, "building": 0.7},
            "preferences": {"temperature": 0.9, "formality": "CASUAL"},
        }),
    )
    print(f"  Conflicts with Pioneer: {conflicts}")
    print()

    # --- Serialization demo ---
    print("── Serialization ──")
    cart_dict = oracle_cart.to_dict()
    restored_cart = TwinCartridge.from_dict(cart_dict)
    print(f"  Roundtrip name: {restored_cart.cartridge_name}")
    print(f"  Roundtrip valid: {restored_cart.validate()}")

    print()
    print("═══════════════════════════════════════════")
    print("Twin×Cartridge: Load a twin. Become them.")
    print("Eject. Return to yourself. Wiser.")
    print("═══════════════════════════════════════════")
