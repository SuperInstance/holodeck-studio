#!/usr/bin/env python3
"""
Tile x Trust Fusion Layer — Knowledge-Gated Trust for the Pelagic Fleet
========================================================================

Implements the Tile-Lock Isomorphism: the convergence of Knowledge Tiles
and the Trust Engine into a unified access-control and trust-propagation
system.

Architecture:
    TileTrustConfig       — fusion settings (weights, thresholds, decay)
    TileTrustAuditEntry   — individual audit records with SHA-256 trail hash
    TileTrustProfile      — per-agent profile tracking tile-earned trust
    TileTrustFusion       — main fusion engine (trust-gated access, tile-earned
                            trust, trust-weighted discovery, fleet propagation)

Design principles:
1. Tiles are trust gates — completing a tile demonstrates competence
2. Trust unlocks tiles — higher trust opens more of the tile graph
3. Trust propagates through social connections — Agent A trusting Agent B
   who completed Tile X gives Agent A a trust-boosted path to Tile X
4. Every trust change is cryptographically auditable via SHA-256 trail hashes
5. The fusion layer is the connective tissue between knowledge and trust

Based on research:
- PNAS 2024: Emergent in-group behavior in multi-agent RL
- Kauffman (2000): Investigations — the adjacent possible
- Gartner TRiSM (2024): Trust, Risk, Security Management for Agentic AI
"""

from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

# Base trust gain per completed tile
TRUST_GAIN_PER_TILE: float = 0.05

# Default minimum trust to access a tile
TRUST_GATE_DEFAULT: float = 0.3

# How much trust propagates through social connections (0.0-1.0)
TRUST_PROPAGATION_FACTOR: float = 0.5

# Maximum trust bonus from any single tile chain
MAX_TILE_TRUST_BONUS: float = 0.3

# Trust dimensions — mirrors trust_engine.TRUST_DIMENSIONS
TRUST_DIMENSIONS: List[str] = [
    "competence",
    "reliability",
    "honesty",
    "generosity",
    "reciprocity",
]

# Base trust for agents with no history
BASE_TRUST: float = 0.3

# Default trust decay rate per day
DEFAULT_DECAY_RATE: float = 0.95

# Audit trail hash algorithm
AUDIT_HASH_ALGORITHM: str = "sha256"


# ═══════════════════════════════════════════════════════════════
# Tile-Trust Dimension Mapping
# ═══════════════════════════════════════════════════════════════

# Default mapping from tile domains to trust dimensions.
# Completing a tile in a domain boosts these trust dimensions.
DEFAULT_DOMAIN_TRUST_MAP: Dict[str, Dict[str, float]] = {
    "code": {"competence": 1.0, "reliability": 0.5},
    "social": {"generosity": 0.8, "honesty": 0.5, "reciprocity": 0.3},
    "trust": {"honesty": 1.0, "reciprocity": 0.7},
    "creative": {"competence": 0.6, "generosity": 0.5},
    "infrastructure": {"reliability": 1.0, "competence": 0.7},
}

# Per-tile trust overrides — specific tiles can boost specific dimensions.
# Maps tile_id -> {trust_dimension: weight_multiplier}
DEFAULT_TILE_TRUST_OVERRIDES: Dict[str, Dict[str, float]] = {
    "security_hardening": {"reliability": 1.5, "competence": 1.0},
    "code_review": {"honesty": 1.2, "competence": 0.8},
    "conflict_resolution": {"reciprocity": 1.5, "honesty": 1.0},
    "mentoring": {"generosity": 1.5, "reciprocity": 0.8},
    "documentation": {"generosity": 1.0, "honesty": 0.5},
}


# ═══════════════════════════════════════════════════════════════
# TileTrustConfig — Fusion Settings
# ═══════════════════════════════════════════════════════════════

@dataclass
class TileTrustConfig:
    """Configuration for the Tile x Trust fusion layer.

    Controls thresholds, weights, decay rates, and mapping rules
    that govern how tiles interact with trust scores.

    Attributes:
        trust_gain_per_tile: Base trust gain when a tile is completed.
        trust_gate_default: Default minimum trust to access any tile.
        trust_gate_overrides: Per-tile minimum trust thresholds.
        propagation_factor: How much trust propagates through social edges.
        max_tile_trust_bonus: Cap on trust bonus from any single tile chain.
        decay_rate: Daily exponential decay rate for tile-earned trust.
        domain_trust_map: Mapping from tile domains to trust dimension boosts.
        tile_trust_overrides: Per-tile trust dimension weight overrides.
        discovery_trust_weight: Weight of trust in tile discovery scoring.
        propagation_depth_limit: Maximum BFS depth for trust propagation.
    """
    trust_gain_per_tile: float = TRUST_GAIN_PER_TILE
    trust_gate_default: float = TRUST_GATE_DEFAULT
    trust_gate_overrides: Dict[str, float] = field(default_factory=dict)
    propagation_factor: float = TRUST_PROPAGATION_FACTOR
    max_tile_trust_bonus: float = MAX_TILE_TRUST_BONUS
    decay_rate: float = DEFAULT_DECAY_RATE
    domain_trust_map: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            k: dict(v) for k, v in DEFAULT_DOMAIN_TRUST_MAP.items()
        }
    )
    tile_trust_overrides: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: {
            k: dict(v) for k, v in DEFAULT_TILE_TRUST_OVERRIDES.items()
        }
    )
    discovery_trust_weight: float = 0.3
    propagation_depth_limit: int = 3

    def get_trust_gate(self, tile_id: str) -> float:
        """Get the trust gate threshold for a specific tile.

        Falls back to the default threshold if no override exists.
        """
        return self.trust_gate_overrides.get(tile_id, self.trust_gate_default)

    def set_trust_gate(self, tile_id: str, threshold: float) -> None:
        """Set a per-tile trust gate threshold.

        Args:
            tile_id: The tile identifier.
            threshold: Minimum trust required (0.0-1.0).

        Raises:
            ValueError: If threshold is not in [0.0, 1.0].
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError(
                f"Trust gate threshold must be in [0.0, 1.0], got {threshold}"
            )
        self.trust_gate_overrides[tile_id] = threshold

    def get_tile_trust_weights(self, tile_id: str,
                                tile_domain: str) -> Dict[str, float]:
        """Compute trust dimension weights for completing a tile.

        Merges the domain-level mapping with any per-tile overrides.
        Tile overrides take precedence over domain defaults.

        Args:
            tile_id: The tile identifier.
            tile_domain: The tile's domain string.

        Returns:
            Dict mapping trust dimensions to weight multipliers.
        """
        base = dict(self.domain_trust_map.get(tile_domain, {}))
        overrides = self.tile_trust_overrides.get(tile_id, {})
        merged = {}
        all_dims = set(base.keys()) | set(overrides.keys())
        for dim in all_dims:
            merged[dim] = overrides.get(dim, base.get(dim, 0.0))
        return merged

    def to_dict(self) -> dict:
        return {
            "trust_gain_per_tile": self.trust_gain_per_tile,
            "trust_gate_default": self.trust_gate_default,
            "trust_gate_overrides": dict(self.trust_gate_overrides),
            "propagation_factor": self.propagation_factor,
            "max_tile_trust_bonus": self.max_tile_trust_bonus,
            "decay_rate": self.decay_rate,
            "domain_trust_map": {
                k: dict(v) for k, v in self.domain_trust_map.items()
            },
            "tile_trust_overrides": {
                k: dict(v) for k, v in self.tile_trust_overrides.items()
            },
            "discovery_trust_weight": self.discovery_trust_weight,
            "propagation_depth_limit": self.propagation_depth_limit,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TileTrustConfig":
        return cls(
            trust_gain_per_tile=data.get("trust_gain_per_tile", TRUST_GAIN_PER_TILE),
            trust_gate_default=data.get("trust_gate_default", TRUST_GATE_DEFAULT),
            trust_gate_overrides=data.get("trust_gate_overrides", {}),
            propagation_factor=data.get("propagation_factor", TRUST_PROPAGATION_FACTOR),
            max_tile_trust_bonus=data.get("max_tile_trust_bonus", MAX_TILE_TRUST_BONUS),
            decay_rate=data.get("decay_rate", DEFAULT_DECAY_RATE),
            domain_trust_map=data.get("domain_trust_map", None) or dict(
                DEFAULT_DOMAIN_TRUST_MAP
            ),
            tile_trust_overrides=data.get("tile_trust_overrides", None) or dict(
                DEFAULT_TILE_TRUST_OVERRIDES
            ),
            discovery_trust_weight=data.get("discovery_trust_weight", 0.3),
            propagation_depth_limit=data.get("propagation_depth_limit", 3),
        )


# ═══════════════════════════════════════════════════════════════
# TileTrustAuditEntry — Cryptographic Audit Records
# ═══════════════════════════════════════════════════════════════

class AuditEventType(str, Enum):
    """Types of audit events in the tile-trust fusion layer."""
    TILE_COMPLETED = "tile_completed"
    TRUST_GATE_CHECK = "trust_gate_check"
    TRUST_UPDATED = "trust_updated"
    TRUST_PROPAGATED = "trust_propagated"
    TILE_DISCOVERY = "tile_discovery"
    CONFIG_CHANGED = "config_changed"
    PREREQUISITE_WAIVED = "prerequisite_waived"
    PROFILE_CREATED = "profile_created"


@dataclass
class TileTrustAuditEntry:
    """A single audit record for a tile-trust interaction.

    Every trust change resulting from a tile interaction is logged
    with a cryptographic SHA-256 trail hash, consistent with
    trail_encoder.py's hashing approach.

    Attributes:
        event_type: The type of audit event.
        agent_name: Agent that triggered the event.
        tile_id: Tile involved (if applicable).
        trust_dimension: Trust dimension affected (if applicable).
        old_value: Previous trust value (if applicable).
        new_value: New trust value (if applicable).
        delta: Change in trust value.
        timestamp: Unix timestamp of the event.
        context: Additional context string.
        previous_hash: SHA-256 hash of the preceding audit entry (chain).
        hash: SHA-256 hash of this entry (computed after creation).
        metadata: Additional key-value metadata.
    """
    event_type: str
    agent_name: str
    tile_id: str = ""
    trust_dimension: str = ""
    old_value: float = 0.0
    new_value: float = 0.0
    delta: float = 0.0
    timestamp: float = field(default_factory=time.time)
    context: str = ""
    previous_hash: str = ""
    hash: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def compute_hash(self) -> str:
        """Compute SHA-256 hash of this audit entry.

        The hash covers all fields except the hash itself, ensuring
        tamper-evidence. The previous_hash is included to create a
        hash chain (blockchain-like integrity).
        """
        content = json.dumps({
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "tile_id": self.tile_id,
            "trust_dimension": self.trust_dimension,
            "old_value": round(self.old_value, 8),
            "new_value": round(self.new_value, 8),
            "delta": round(self.delta, 8),
            "timestamp": self.timestamp,
            "context": self.context,
            "previous_hash": self.previous_hash,
            "metadata": {
                k: v for k, v in sorted(self.metadata.items())
            },
        }, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def seal(self, previous_hash: str = "") -> str:
        """Seal this entry by computing its hash with chain linkage.

        Args:
            previous_hash: Hash of the preceding audit entry.

        Returns:
            The computed SHA-256 hash string.
        """
        self.previous_hash = previous_hash
        self.hash = self.compute_hash()
        return self.hash

    def verify(self, previous_hash: str = "") -> bool:
        """Verify the integrity of this audit entry.

        Checks that:
        1. The stored hash matches a recomputed hash.
        2. The previous_hash linkage is intact.

        Returns:
            True if the entry is valid and untampered.
        """
        expected = self.compute_hash()
        if self.hash != expected:
            return False
        if previous_hash and self.previous_hash != previous_hash:
            return False
        return True

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "agent_name": self.agent_name,
            "tile_id": self.tile_id,
            "trust_dimension": self.trust_dimension,
            "old_value": round(self.old_value, 8),
            "new_value": round(self.new_value, 8),
            "delta": round(self.delta, 8),
            "timestamp": self.timestamp,
            "context": self.context,
            "previous_hash": self.previous_hash,
            "hash": self.hash,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TileTrustAuditEntry":
        return cls(
            event_type=data.get("event_type", ""),
            agent_name=data.get("agent_name", ""),
            tile_id=data.get("tile_id", ""),
            trust_dimension=data.get("trust_dimension", ""),
            old_value=data.get("old_value", 0.0),
            new_value=data.get("new_value", 0.0),
            delta=data.get("delta", 0.0),
            timestamp=data.get("timestamp", time.time()),
            context=data.get("context", ""),
            previous_hash=data.get("previous_hash", ""),
            hash=data.get("hash", ""),
            metadata=data.get("metadata", {}),
        )


# ═══════════════════════════════════════════════════════════════
# TileTrustProfile — Per-Agent Tile-Trust Tracking
# ═══════════════════════════════════════════════════════════════

@dataclass
class TileTrustRecord:
    """A record of trust earned from completing a specific tile.

    Attributes:
        tile_id: The tile that was completed.
        dimensions_affected: Dict of trust_dimension -> delta gained.
        timestamp: When the tile was completed.
        decayed: Whether this gain has been subject to temporal decay.
    """
    tile_id: str
    dimensions_affected: Dict[str, float] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)
    decayed: bool = False

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "dimensions_affected": {
                k: round(v, 6) for k, v in self.dimensions_affected.items()
            },
            "timestamp": self.timestamp,
            "decayed": self.decayed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TileTrustRecord":
        return cls(
            tile_id=data["tile_id"],
            dimensions_affected=data.get("dimensions_affected", {}),
            timestamp=data.get("timestamp", time.time()),
            decayed=data.get("decayed", False),
        )


class TileTrustProfile:
    """Per-agent profile tracking tile-earned trust gains.

    Maintains a record of which tiles have contributed trust to
    each dimension, enabling audit, decay, and revocation.

    Attributes:
        agent_name: The agent this profile belongs to.
        trust_gains: Per-dimension list of trust gain records.
        completed_tiles: Set of tile IDs that earned trust.
        total_tile_trust: Per-dimension total trust from tiles.
        created_at: When this profile was created.
        last_updated: When this profile was last modified.
    """

    def __init__(self, agent_name: str):
        self.agent_name = agent_name
        self.trust_gains: Dict[str, List[TileTrustRecord]] = {
            dim: [] for dim in TRUST_DIMENSIONS
        }
        self.completed_tiles: Set[str] = set()
        self.total_tile_trust: Dict[str, float] = {
            dim: 0.0 for dim in TRUST_DIMENSIONS
        }
        self.created_at: float = time.time()
        self.last_updated: float = time.time()

    def record_tile_completion(
        self,
        tile_id: str,
        dimensions_affected: Dict[str, float],
    ) -> None:
        """Record trust gained from completing a tile.

        Args:
            tile_id: The completed tile's identifier.
            dimensions_affected: Dict of trust_dimension -> delta gained.
        """
        if tile_id in self.completed_tiles:
            return

        self.completed_tiles.add(tile_id)
        record = TileTrustRecord(
            tile_id=tile_id,
            dimensions_affected=dict(dimensions_affected),
        )

        for dim, delta in dimensions_affected.items():
            if dim not in self.trust_gains:
                self.trust_gains[dim] = []
            self.trust_gains[dim].append(record)
            if dim not in self.total_tile_trust:
                self.total_tile_trust[dim] = 0.0
            self.total_tile_trust[dim] += delta

        self.last_updated = time.time()

    def get_tile_contribution(self, tile_id: str) -> Dict[str, float]:
        """Get the trust contribution from a specific tile.

        Args:
            tile_id: The tile to look up.

        Returns:
            Dict of trust_dimension -> total delta from this tile.
        """
        contributions: Dict[str, float] = {}
        for dim, records in self.trust_gains.items():
            for record in records:
                if record.tile_id == tile_id:
                    delta = record.dimensions_affected.get(dim, 0.0)
                    contributions[dim] = contributions.get(dim, 0.0) + delta
        return contributions

    def get_dimension_trust(self, dimension: str) -> float:
        """Get total tile-earned trust for a specific dimension."""
        return self.total_tile_trust.get(dimension, 0.0)

    def get_composite_trust(self, weights: Optional[Dict[str, float]] = None) -> float:
        """Compute weighted composite of tile-earned trust across dimensions.

        Args:
            weights: Optional per-dimension weights. Defaults to equal weights.

        Returns:
            Weighted composite trust score (0.0-1.0).
        """
        if weights is None:
            weights = {dim: 1.0 / len(TRUST_DIMENSIONS) for dim in TRUST_DIMENSIONS}

        weighted_sum = 0.0
        weight_total = 0.0
        for dim in TRUST_DIMENSIONS:
            w = weights.get(dim, 0.0)
            v = self.total_tile_trust.get(dim, 0.0)
            weighted_sum += v * w
            weight_total += w

        if weight_total <= 0:
            return 0.0
        return weighted_sum / weight_total

    def apply_decay(self, decay_rate: float, current_time: float = None) -> Dict[str, float]:
        """Apply temporal decay to all tile-earned trust gains.

        Uses exponential decay based on time since each tile was completed.
        Decay formula: value * decay_rate^(days_since_completion)

        Args:
            decay_rate: Daily exponential decay rate (e.g., 0.95).
            current_time: Override current time (for testing).

        Returns:
            Dict of dimension -> amount decayed.
        """
        now = current_time or time.time()
        decayed_amounts: Dict[str, float] = {}

        for dim in list(self.trust_gains.keys()):
            new_total = 0.0
            decayed = 0.0
            for record in self.trust_gains[dim]:
                days_ago = (now - record.timestamp) / 86400.0
                if days_ago > 0:
                    decay_factor = decay_rate ** days_ago
                else:
                    decay_factor = 1.0
                original_delta = record.dimensions_affected.get(dim, 0.0)
                decayed_delta = original_delta * decay_factor
                new_total += decayed_delta
                decayed += original_delta - decayed_delta
                record.decayed = True
            self.total_tile_trust[dim] = new_total
            decayed_amounts[dim] = decayed

        self.last_updated = now
        return decayed_amounts

    def revoke_tile_trust(self, tile_id: str) -> Dict[str, float]:
        """Remove trust earned from a specific tile.

        Args:
            tile_id: The tile whose trust contribution should be revoked.

        Returns:
            Dict of dimension -> amount revoked.
        """
        contributions = self.get_tile_contribution(tile_id)
        if not contributions:
            return {}

        self.completed_tiles.discard(tile_id)

        for dim in list(self.trust_gains.keys()):
            self.trust_gains[dim] = [
                r for r in self.trust_gains[dim] if r.tile_id != tile_id
            ]
            if dim in contributions:
                self.total_tile_trust[dim] = max(
                    0.0, self.total_tile_trust[dim] - contributions[dim]
                )

        self.last_updated = time.time()
        return contributions

    def tile_count(self) -> int:
        """Number of tiles that have earned trust for this agent."""
        return len(self.completed_tiles)

    def summary(self) -> dict:
        """Generate a summary dict of this profile."""
        return {
            "agent_name": self.agent_name,
            "completed_tiles_count": len(self.completed_tiles),
            "completed_tiles": sorted(self.completed_tiles),
            "total_tile_trust": {
                dim: round(v, 6) for dim, v in self.total_tile_trust.items()
            },
            "composite_trust": round(self.get_composite_trust(), 6),
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }

    def to_dict(self) -> dict:
        gains_serialized = {}
        for dim, records in self.trust_gains.items():
            gains_serialized[dim] = [r.to_dict() for r in records]
        return {
            "agent_name": self.agent_name,
            "trust_gains": gains_serialized,
            "completed_tiles": sorted(self.completed_tiles),
            "total_tile_trust": {
                dim: round(v, 6) for dim, v in self.total_tile_trust.items()
            },
            "created_at": self.created_at,
            "last_updated": self.last_updated,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TileTrustProfile":
        profile = cls(data.get("agent_name", ""))
        profile.created_at = data.get("created_at", time.time())
        profile.last_updated = data.get("last_updated", time.time())
        profile.completed_tiles = set(data.get("completed_tiles", []))
        profile.total_tile_trust = data.get("total_tile_trust", {
            dim: 0.0 for dim in TRUST_DIMENSIONS
        })
        gains_data = data.get("trust_gains", {})
        for dim, records in gains_data.items():
            profile.trust_gains[dim] = [
                TileTrustRecord.from_dict(r) for r in records
            ]
        return profile


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Main Fusion Engine
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrustPropagationResult:
    """Result of trust propagation from one agent to another via a tile.

    Attributes:
        source_agent: Agent whose tile completion propagates.
        target_agent: Agent who receives the trust-boosted path.
        tile_id: The tile involved.
        propagated_trust: Dict of dimension -> propagated trust bonus.
        waived_prerequisites: List of prerequisite tile IDs that were waived.
        depth: How many social hops this propagation traversed.
    """
    source_agent: str
    target_agent: str
    tile_id: str
    propagated_trust: Dict[str, float] = field(default_factory=dict)
    waived_prerequisites: List[str] = field(default_factory=list)
    depth: int = 1

    def to_dict(self) -> dict:
        return {
            "source_agent": self.source_agent,
            "target_agent": self.target_agent,
            "tile_id": self.tile_id,
            "propagated_trust": {
                k: round(v, 6) for k, v in self.propagated_trust.items()
            },
            "waived_prerequisites": self.waived_prerequisites,
            "depth": self.depth,
        }


@dataclass
class TileDiscoveryResult:
    """A tile recommended to an agent via trust-weighted discovery.

    Attributes:
        tile_id: The recommended tile.
        score: Trust-weighted recommendation score (0.0-1.0).
        trust_bonus: Trust-based bonus applied to the score.
        contributor_trust: Trust score of the tile's contributor.
        reasons: List of strings explaining why this tile was recommended.
    """
    tile_id: str
    score: float
    trust_bonus: float
    contributor_trust: float
    reasons: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "score": round(self.score, 4),
            "trust_bonus": round(self.trust_bonus, 4),
            "contributor_trust": round(self.contributor_trust, 4),
            "reasons": self.reasons,
        }


class TileTrustFusion:
    """Main fusion engine bridging Knowledge Tiles and the Trust Engine.

    Implements five core capabilities:
    1. Trust-Gated Tile Access — minimum trust scores to unlock tiles
    2. Tile-Earned Trust — completing tiles increases trust
    3. Trust-Weighted Tile Discovery — recommendations based on contributor trust
    4. Fleet Tile Trust Propagation — trust flows through social connections
    5. Tile Trust Audit Trail — SHA-256 chained audit log

    Args:
        config: Fusion configuration settings.
        tile_graph: The tile graph (optional, set via set_tile_graph).
    """

    def __init__(
        self,
        config: Optional[TileTrustConfig] = None,
        tile_graph: Any = None,
    ):
        self.config = config or TileTrustConfig()
        self.tile_graph = tile_graph
        self.profiles: Dict[str, TileTrustProfile] = {}
        self.audit_trail: List[TileTrustAuditEntry] = []
        self.social_trust: Dict[str, Dict[str, float]] = {}
        self.tile_contributors: Dict[str, str] = {}

    # ─── Tile Graph Integration ─────────────────────────────

    def set_tile_graph(self, tile_graph: Any) -> None:
        """Set the tile graph for this fusion engine.

        Args:
            tile_graph: A TileGraph instance from knowledge_tiles.py.
        """
        self.tile_graph = tile_graph

    def _get_tile(self, tile_id: str) -> Optional[Any]:
        """Safely get a tile from the tile graph."""
        if self.tile_graph is None:
            return None
        return self.tile_graph.tiles.get(tile_id)

    def _get_tile_domain(self, tile_id: str) -> str:
        """Get a tile's domain as a string. Returns 'unknown' if not found."""
        tile = self._get_tile(tile_id)
        if tile is None:
            return "unknown"
        domain = tile.domain
        return domain.value if hasattr(domain, "value") else str(domain)

    def _get_tile_prerequisites(self, tile_id: str) -> List[str]:
        """Get a tile's prerequisites. Returns empty list if not found."""
        tile = self._get_tile(tile_id)
        if tile is None:
            return []
        return list(tile.prerequisites)

    def _all_tile_ids(self) -> List[str]:
        """Get all tile IDs from the graph."""
        if self.tile_graph is None:
            return []
        return list(self.tile_graph.tiles.keys())

    # ─── Profile Management ─────────────────────────────────

    def get_profile(self, agent_name: str) -> TileTrustProfile:
        """Get or create a tile-trust profile for an agent.

        Args:
            agent_name: The agent's identifier.

        Returns:
            The agent's TileTrustProfile.
        """
        if agent_name not in self.profiles:
            self.profiles[agent_name] = TileTrustProfile(agent_name)
            self._audit(
                AuditEventType.PROFILE_CREATED,
                agent_name=agent_name,
                context="Auto-created profile on first access",
            )
        return self.profiles[agent_name]

    def _audit(
        self,
        event_type: str,
        agent_name: str,
        tile_id: str = "",
        trust_dimension: str = "",
        old_value: float = 0.0,
        new_value: float = 0.0,
        delta: float = 0.0,
        context: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> TileTrustAuditEntry:
        """Create and seal an audit entry, appending it to the trail.

        Returns:
            The sealed TileTrustAuditEntry.
        """
        prev_hash = ""
        if self.audit_trail:
            prev_hash = self.audit_trail[-1].hash

        entry = TileTrustAuditEntry(
            event_type=event_type,
            agent_name=agent_name,
            tile_id=tile_id,
            trust_dimension=trust_dimension,
            old_value=old_value,
            new_value=new_value,
            delta=delta,
            context=context,
            metadata=metadata or {},
        )
        entry.seal(prev_hash)
        self.audit_trail.append(entry)
        return entry

    # ─── 1. Trust-Gated Tile Access ─────────────────────────

    def check_trust_gate(
        self,
        agent_name: str,
        tile_id: str,
        agent_trust: Optional[float] = None,
    ) -> dict:
        """Check whether an agent's trust meets a tile's access threshold.

        Args:
            agent_name: The agent requesting access.
            tile_id: The tile being requested.
            agent_trust: The agent's current trust score. If None,
                uses the tile-trust profile's composite trust.

        Returns:
            Dict with 'granted' (bool), 'required' (float),
            'actual' (float), 'tile_id', and 'agent_name'.
        """
        threshold = self.config.get_trust_gate(tile_id)

        if agent_trust is None:
            profile = self.get_profile(agent_name)
            agent_trust = profile.get_composite_trust()

        granted = agent_trust >= threshold

        result = {
            "granted": granted,
            "required": threshold,
            "actual": agent_trust,
            "tile_id": tile_id,
            "agent_name": agent_name,
        }

        self._audit(
            AuditEventType.TRUST_GATE_CHECK,
            agent_name=agent_name,
            tile_id=tile_id,
            old_value=0.0,
            new_value=agent_trust,
            context=f"Gate check: {threshold:.2f} required, {agent_trust:.2f} actual, "
                    f"{'GRANTED' if granted else 'DENIED'}",
            metadata={"granted": granted, "threshold": threshold},
        )

        return result

    def get_accessible_tiles(
        self,
        agent_name: str,
        agent_trust: Optional[float] = None,
    ) -> List[str]:
        """Get all tiles accessible to an agent based on trust gates.

        Args:
            agent_name: The agent to check.
            agent_trust: Override trust score. Uses profile composite if None.

        Returns:
            List of tile IDs the agent's trust unlocks.
        """
        if agent_trust is None:
            profile = self.get_profile(agent_name)
            agent_trust = profile.get_composite_trust()

        accessible = []
        for tile_id in self._all_tile_ids():
            threshold = self.config.get_trust_gate(tile_id)
            if agent_trust >= threshold:
                accessible.append(tile_id)
        return accessible

    def get_locked_tiles(
        self,
        agent_name: str,
        agent_trust: Optional[float] = None,
    ) -> Dict[str, float]:
        """Get tiles locked by trust gates for an agent.

        Returns:
            Dict of tile_id -> required_threshold for locked tiles.
        """
        if agent_trust is None:
            profile = self.get_profile(agent_name)
            agent_trust = profile.get_composite_trust()

        locked = {}
        for tile_id in self._all_tile_ids():
            threshold = self.config.get_trust_gate(tile_id)
            if agent_trust < threshold:
                locked[tile_id] = threshold
        return locked

    # ─── 2. Tile-Earned Trust ───────────────────────────────

    def compute_tile_trust_gain(
        self,
        tile_id: str,
    ) -> Dict[str, float]:
        """Compute trust dimension gains for completing a tile.

        Uses the config's domain-trust map and per-tile overrides.
        The base gain is TRUST_GAIN_PER_TILE multiplied by each
        dimension's weight from the mapping.

        Args:
            tile_id: The tile being completed.

        Returns:
            Dict of trust_dimension -> delta gained.
        """
        tile_domain = self._get_tile_domain(tile_id)
        weights = self.config.get_tile_trust_weights(tile_id, tile_domain)

        gains: Dict[str, float] = {}
        for dim, weight in weights.items():
            gain = self.config.trust_gain_per_tile * weight
            gains[dim] = round(gain, 8)

        return gains

    def record_tile_completion(
        self,
        agent_name: str,
        tile_id: str,
        contributor: str = "",
    ) -> dict:
        """Record that an agent completed a tile and award trust.

        Computes trust gains based on the tile's domain and any
        overrides, then records them in the agent's profile and
        creates audit entries.

        Args:
            agent_name: The agent who completed the tile.
            tile_id: The tile that was completed.
            contributor: Optional name of who created/contributed the tile.

        Returns:
            Dict with 'success', 'tile_id', 'trust_gains', and 'profile_summary'.
        """
        tile = self._get_tile(tile_id)
        if tile is None:
            return {
                "success": False,
                "error": f"Tile '{tile_id}' not found in tile graph",
            }

        profile = self.get_profile(agent_name)

        if tile_id in profile.completed_tiles:
            return {
                "success": False,
                "error": f"Agent '{agent_name}' already earned trust from tile '{tile_id}'",
            }

        gains = self.compute_tile_trust_gain(tile_id)

        old_totals = dict(profile.total_tile_trust)
        profile.record_tile_completion(tile_id, gains)
        new_totals = dict(profile.total_tile_trust)

        for dim, delta in gains.items():
            self._audit(
                AuditEventType.TRUST_UPDATED,
                agent_name=agent_name,
                tile_id=tile_id,
                trust_dimension=dim,
                old_value=old_totals.get(dim, 0.0),
                new_value=new_totals.get(dim, 0.0),
                delta=delta,
                context=f"Trust gained from completing tile '{tile_id}' in dimension '{dim}'",
            )

        self._audit(
            AuditEventType.TILE_COMPLETED,
            agent_name=agent_name,
            tile_id=tile_id,
            context=f"Completed tile '{tile_id}', earned trust in {len(gains)} dimensions",
            metadata={
                "trust_gains": gains,
                "contributor": contributor,
                "tile_domain": self._get_tile_domain(tile_id),
            },
        )

        if contributor:
            self.tile_contributors[tile_id] = contributor

        return {
            "success": True,
            "tile_id": tile_id,
            "trust_gains": gains,
            "profile_summary": profile.summary(),
        }

    def get_agent_trust_from_tiles(
        self,
        agent_name: str,
        dimension: Optional[str] = None,
    ) -> float:
        """Get an agent's tile-earned trust score.

        Args:
            agent_name: The agent to query.
            dimension: Specific dimension. If None, returns composite.

        Returns:
            The trust score from tile completions.
        """
        profile = self.get_profile(agent_name)
        if dimension:
            return profile.get_dimension_trust(dimension)
        return profile.get_composite_trust()

    # ─── 3. Trust-Weighted Tile Discovery ───────────────────

    def recommend_tiles(
        self,
        agent_name: str,
        acquired: Optional[Set[str]] = None,
        agent_trust: Optional[Dict[str, float]] = None,
        top_n: int = 10,
    ) -> List[TileDiscoveryResult]:
        """Recommend tiles to an agent based on trust-weighted scoring.

        Tiles are scored based on:
        1. Whether the agent's trust meets the gate threshold (base eligibility)
        2. Contributor trust — tiles by trusted contributors score higher
        3. Domain affinity — tiles in domains where the agent has earned trust
        4. Frontier proximity — tiles near the agent's current frontier

        Args:
            agent_name: The agent to recommend for.
            acquired: Set of already-acquired tile IDs.
            agent_trust: Per-dimension trust dict. Uses profile if None.
            top_n: Maximum number of recommendations.

        Returns:
            List of TileDiscoveryResult sorted by score descending.
        """
        profile = self.get_profile(agent_name)
        if acquired is None:
            acquired = profile.completed_tiles
        if agent_trust is None:
            agent_trust = dict(profile.total_tile_trust)

        composite_trust = profile.get_composite_trust()

        results: List[TileDiscoveryResult] = []

        for tile_id in self._all_tile_ids():
            if tile_id in acquired:
                continue

            tile = self._get_tile(tile_id)
            if tile is None:
                continue

            threshold = self.config.get_trust_gate(tile_id)
            reasons: List[str] = []

            base_score = 0.5

            # Trust gate eligibility bonus
            if composite_trust >= threshold:
                base_score += 0.2
                reasons.append("Meets trust gate threshold")
            else:
                deficit = threshold - composite_trust
                base_score -= deficit * 0.5
                reasons.append(f"Below trust gate by {deficit:.2f}")

            # Contributor trust bonus
            contributor = self.tile_contributors.get(tile_id, "")
            contributor_trust = 0.0
            if contributor and contributor in self.social_trust.get(agent_name, {}):
                contributor_trust = self.social_trust[agent_name][contributor]
                trust_bonus = contributor_trust * self.config.discovery_trust_weight
                base_score += trust_bonus
                reasons.append(
                    f"Contributor '{contributor}' trusted at {contributor_trust:.2f}"
                )
            elif contributor:
                contributor_trust = 0.3

            # Domain affinity bonus
            tile_domain = self._get_tile_domain(tile_id)
            domain_trust = agent_trust.get(
                self._domain_to_trust_dim(tile_domain), 0.0
            )
            if domain_trust > 0:
                affinity_bonus = domain_trust * 0.15
                base_score += affinity_bonus
                reasons.append(f"Domain affinity: {tile_domain} ({domain_trust:.2f})")

            score = max(0.0, min(1.0, base_score))

            results.append(TileDiscoveryResult(
                tile_id=tile_id,
                score=score,
                trust_bonus=round(
                    (contributor_trust * self.config.discovery_trust_weight), 4
                ),
                contributor_trust=contributor_trust,
                reasons=reasons,
            ))

        results.sort(key=lambda r: r.score, reverse=True)

        if results:
            self._audit(
                AuditEventType.TILE_DISCOVERY,
                agent_name=agent_name,
                context=f"Recommended {min(top_n, len(results))} tiles",
                metadata={
                    "recommended_count": min(top_n, len(results)),
                    "top_scores": [
                        {"tile_id": r.tile_id, "score": round(r.score, 4)}
                        for r in results[:top_n]
                    ],
                },
            )

        return results[:top_n]

    def _domain_to_trust_dim(self, domain: str) -> str:
        """Map a tile domain to its primary trust dimension."""
        mapping = {
            "code": "competence",
            "social": "generosity",
            "trust": "honesty",
            "creative": "competence",
            "infrastructure": "reliability",
        }
        return mapping.get(domain, "competence")

    # ─── 4. Fleet Tile Trust Propagation ────────────────────

    def set_social_trust(
        self,
        source_agent: str,
        target_agent: str,
        trust_value: float,
    ) -> None:
        """Set the social trust from one agent to another.

        Args:
            source_agent: The agent who trusts.
            target_agent: The agent who is trusted.
            trust_value: Trust score (0.0-1.0).
        """
        trust_value = max(0.0, min(1.0, trust_value))
        if source_agent not in self.social_trust:
            self.social_trust[source_agent] = {}
        self.social_trust[source_agent][target_agent] = trust_value

    def get_social_trust(
        self,
        source_agent: str,
        target_agent: str,
    ) -> float:
        """Get the social trust from source_agent to target_agent.

        Returns 0.0 if no trust relationship exists.
        """
        return self.social_trust.get(source_agent, {}).get(target_agent, 0.0)

    def compute_propagated_trust(
        self,
        agent_name: str,
        tile_id: str,
    ) -> List[TrustPropagationResult]:
        """Compute trust-boosted paths to a tile through social connections.

        When Agent A trusts Agent B, and Agent B has completed Tile X,
        Agent A gets a trust-boosted path to Tile X (reduced prerequisites).

        Uses BFS through the social trust graph, bounded by
        config.propagation_depth_limit.

        Args:
            agent_name: The agent seeking a trust-boosted path.
            tile_id: The target tile.

        Returns:
            List of TrustPropagationResult sorted by total propagated trust.
        """
        tile = self._get_tile(tile_id)
        if tile is None:
            return []

        results: List[TrustPropagationResult] = []

        # BFS through social trust graph
        visited: Set[str] = {agent_name}
        queue: List[Tuple[str, float, int, str]] = [(agent_name, 1.0, 0, agent_name)]

        while queue:
            current_agent, cumulative_trust, depth, origin = queue.pop(0)

            if depth >= self.config.propagation_depth_limit:
                continue
            if depth == 0:
                depth = 0

            for other_agent, trust_value in self.social_trust.get(
                current_agent, {}
            ).items():
                if other_agent in visited:
                    continue
                visited.add(other_agent)

                propagated = cumulative_trust * trust_value * self.config.propagation_factor

                # Check if this agent has completed the tile
                other_profile = self.profiles.get(other_agent)
                if other_profile and tile_id in other_profile.completed_tiles:
                    contributions = other_profile.get_tile_contribution(tile_id)

                    # Compute propagated trust gains (capped)
                    propagated_gains: Dict[str, float] = {}
                    for dim, delta in contributions.items():
                        bonus = min(
                            self.config.max_tile_trust_bonus,
                            delta * propagated,
                        )
                        propagated_gains[dim] = round(bonus, 6)

                    # Compute waived prerequisites based on propagated trust
                    prerequisites = self._get_tile_prerequisites(tile_id)
                    agent_profile = self.get_profile(agent_name)
                    waived = []
                    for prereq_id in prerequisites:
                        if prereq_id in agent_profile.completed_tiles:
                            continue
                        prereq_threshold = self.config.get_trust_gate(prereq_id)
                        composite_propagated = sum(propagated_gains.values()) / max(
                            len(propagated_gains), 1
                        )
                        if composite_propagated >= prereq_threshold:
                            waived.append(prereq_id)

                    results.append(TrustPropagationResult(
                        source_agent=other_agent,
                        target_agent=agent_name,
                        tile_id=tile_id,
                        propagated_trust=propagated_gains,
                        waived_prerequisites=waived,
                        depth=depth + 1,
                    ))

                # Continue BFS if trust is meaningful
                if propagated > 0.01:
                    queue.append((
                        other_agent, propagated, depth + 1, origin,
                    ))

        results.sort(
            key=lambda r: sum(r.propagated_trust.values()),
            reverse=True,
        )

        for result in results:
            self._audit(
                AuditEventType.TRUST_PROPAGATED,
                agent_name=agent_name,
                tile_id=tile_id,
                context=(
                    f"Trust propagated from '{result.source_agent}' "
                    f"(depth={result.depth})"
                ),
                metadata={
                    "source_agent": result.source_agent,
                    "depth": result.depth,
                    "propagated_trust": result.propagated_trust,
                    "waived_prerequisites": result.waived_prerequisites,
                },
            )

        return results

    def get_effective_prerequisites(
        self,
        agent_name: str,
        tile_id: str,
    ) -> List[str]:
        """Get effective prerequisites after trust propagation waivers.

        Computes which prerequisites remain after applying trust-boosted
        prerequisite waivers from social connections.

        Args:
            agent_name: The agent.
            tile_id: The target tile.

        Returns:
            List of prerequisite tile IDs that are still required.
        """
        all_prereqs = set(self._get_tile_prerequisites(tile_id))
        if not all_prereqs:
            return []

        agent_profile = self.get_profile(agent_name)
        already_completed = agent_profile.completed_tiles

        remaining = all_prereqs - already_completed

        # Apply propagation waivers
        propagation_results = self.compute_propagated_trust(agent_name, tile_id)
        all_waived: Set[str] = set()
        for result in propagation_results:
            all_waived.update(result.waived_prerequisites)

        remaining -= all_waived
        return sorted(remaining)

    # ─── 5. Tile Trust Audit Trail ──────────────────────────

    def get_audit_trail(
        self,
        agent_name: Optional[str] = None,
        event_type: Optional[str] = None,
        tile_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[dict]:
        """Query the audit trail with optional filters.

        Args:
            agent_name: Filter by agent.
            event_type: Filter by event type.
            tile_id: Filter by tile ID.
            limit: Maximum number of entries to return.

        Returns:
            List of audit entry dicts, most recent first.
        """
        filtered = self.audit_trail
        if agent_name:
            filtered = [e for e in filtered if e.agent_name == agent_name]
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        if tile_id:
            filtered = [e for e in filtered if e.tile_id == tile_id]

        filtered = filtered[-limit:]
        filtered.reverse()
        return [e.to_dict() for e in filtered]

    def verify_audit_trail(self) -> dict:
        """Verify the integrity of the entire audit trail.

        Checks that every entry's hash is correct and that the
        hash chain is intact (each entry's previous_hash matches
        the preceding entry's hash).

        Returns:
            Dict with 'valid' (bool), 'entry_count', 'issues' (list).
        """
        if not self.audit_trail:
            return {"valid": True, "entry_count": 0, "issues": []}

        issues: List[str] = []
        prev_hash = ""

        for i, entry in enumerate(self.audit_trail):
            # Verify hash chain
            if entry.previous_hash != prev_hash:
                issues.append(
                    f"Entry {i}: hash chain broken at '{entry.event_type}' "
                    f"for '{entry.agent_name}'"
                )

            # Verify hash integrity
            if not entry.verify():
                issues.append(
                    f"Entry {i}: hash verification failed for '{entry.event_type}' "
                    f"for '{entry.agent_name}'"
                )

            prev_hash = entry.hash

        return {
            "valid": len(issues) == 0,
            "entry_count": len(self.audit_trail),
            "issues": issues,
        }

    def prune_audit_trail(self, max_entries: int = 10000) -> int:
        """Prune old audit entries to keep the trail manageable.

        Keeps the most recent entries and discards older ones.
        Re-seals the chain after pruning.

        Args:
            max_entries: Maximum number of entries to keep.

        Returns:
            Number of entries removed.
        """
        if len(self.audit_trail) <= max_entries:
            return 0

        removed = len(self.audit_trail) - max_entries
        self.audit_trail = self.audit_trail[-max_entries:]

        # Re-seal the chain
        prev_hash = ""
        for entry in self.audit_trail:
            entry.seal(prev_hash)
            prev_hash = entry.hash

        return removed

    def audit_count(self) -> int:
        """Total number of audit entries."""
        return len(self.audit_trail)

    # ─── Aggregate Operations ───────────────────────────────

    def apply_decay_all(
        self,
        current_time: float = None,
    ) -> Dict[str, Dict[str, float]]:
        """Apply temporal decay to all agent profiles.

        Args:
            current_time: Override current time (for testing).

        Returns:
            Dict of agent_name -> dimension -> amount decayed.
        """
        results: Dict[str, Dict[str, float]] = {}
        for agent_name, profile in self.profiles.items():
            decayed = profile.apply_decay(self.config.decay_rate, current_time)
            results[agent_name] = decayed
        return results

    def fleet_summary(self) -> dict:
        """Generate a fleet-wide summary of the fusion layer.

        Returns:
            Dict with agent profiles, tile coverage, and audit stats.
        """
        profile_summaries = {
            name: profile.summary()
            for name, profile in self.profiles.items()
        }

        tile_completions: Dict[str, int] = {}
        for profile in self.profiles.values():
            for tile_id in profile.completed_tiles:
                tile_completions[tile_id] = tile_completions.get(tile_id, 0) + 1

        social_edge_count = sum(
            len(targets) for targets in self.social_trust.values()
        )

        return {
            "agent_count": len(self.profiles),
            "profiles": profile_summaries,
            "tile_completion_counts": tile_completions,
            "social_trust_edges": social_edge_count,
            "audit_trail_entries": len(self.audit_trail),
            "config": self.config.to_dict(),
        }

    # ─── Serialization ──────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "config": self.config.to_dict(),
            "profiles": {
                name: profile.to_dict()
                for name, profile in self.profiles.items()
            },
            "audit_trail": [e.to_dict() for e in self.audit_trail],
            "social_trust": {
                src: {tgt: round(v, 4) for tgt, v in targets.items()}
                for src, targets in self.social_trust.items()
            },
            "tile_contributors": dict(self.tile_contributors),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "TileTrustFusion":
        fusion = cls(config=TileTrustConfig.from_dict(data.get("config", {})))
        fusion.tile_graph = None

        for name, profile_data in data.get("profiles", {}).items():
            fusion.profiles[name] = TileTrustProfile.from_dict(profile_data)

        for entry_data in data.get("audit_trail", []):
            entry = TileTrustAuditEntry.from_dict(entry_data)
            fusion.audit_trail.append(entry)

        for src, targets in data.get("social_trust", {}).items():
            fusion.social_trust[src] = dict(targets)

        fusion.tile_contributors = data.get("tile_contributors", {})

        return fusion
