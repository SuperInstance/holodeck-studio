"""
Trust × Permission Integration Layer
======================================

Bridges the multi-dimensional Trust Engine with the morphogenetic Permission
Field. Core concept: **Trust unlocks Permissions**.

An agent's composite trust score (optionally weighted by dimension relevance)
determines which capabilities/permissions they can access. As trust grows
through interactions, new permissions automatically unlock. If trust decays,
permissions can be revoked after a grace period.

Design principles:
1. Trust is the primary gate — composite trust maps to permission thresholds
2. Automatic sync — bridge can auto-grant/revoke based on trust changes
3. Grace period — decay doesn't immediately revoke; agents get 24h buffer
4. Dimension weighting — some permissions care more about certain trust dims
5. Serializable — full state can be persisted and restored
"""

import time
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# Default Permission Thresholds
# ═══════════════════════════════════════════════════════════════

DEFAULT_PERMISSION_THRESHOLDS: Dict[str, float] = {
    "basic_commands":       0.1,   # Any trusted agent can use basic commands
    "room_creation":        0.3,   # Create rooms requires moderate trust
    "agent_communication":  0.3,   # Communicate with other agents
    "cartridge_loading":    0.5,   # Load game cartridges — needs experience + trust
    "trust_attestation":    0.6,   # Attest to other agents' trustworthiness
    "fleet_broadcast":      0.7,   # Broadcast to the entire fleet
    "governance_voting":    0.8,   # Participate in governance decisions
    "permission_granting":  0.9,   # Grant permissions to other agents
    "npc_management":       0.4,   # Manage NPC agents
    "spell_creation":       0.5,   # Create new spells
    "world_editing":        0.6,   # Edit world properties
    "system_config":        0.85,  # Modify system configuration
    "review_override":      0.75,  # Override review requirements
    "cross_fleet_access":   0.65,  # Access resources across fleet boundaries
    "emergency_powers":     0.95,  # Emergency administrative powers
}

# Default dimension weights for each permission category
# Maps permission → how much each trust dimension matters
DEFAULT_DIMENSION_WEIGHTS: Dict[str, Dict[str, float]] = {
    "basic_commands": {
        "code_quality": 0.10, "task_completion": 0.30,
        "collaboration": 0.20, "reliability": 0.30, "innovation": 0.10,
    },
    "room_creation": {
        "code_quality": 0.20, "task_completion": 0.20,
        "collaboration": 0.20, "reliability": 0.30, "innovation": 0.10,
    },
    "agent_communication": {
        "code_quality": 0.10, "task_completion": 0.10,
        "collaboration": 0.50, "reliability": 0.20, "innovation": 0.10,
    },
    "cartridge_loading": {
        "code_quality": 0.25, "task_completion": 0.25,
        "collaboration": 0.10, "reliability": 0.30, "innovation": 0.10,
    },
    "trust_attestation": {
        "code_quality": 0.10, "task_completion": 0.10,
        "collaboration": 0.30, "reliability": 0.40, "innovation": 0.10,
    },
    "fleet_broadcast": {
        "code_quality": 0.10, "task_completion": 0.10,
        "collaboration": 0.40, "reliability": 0.30, "innovation": 0.10,
    },
    "governance_voting": {
        "code_quality": 0.15, "task_completion": 0.20,
        "collaboration": 0.25, "reliability": 0.30, "innovation": 0.10,
    },
    "permission_granting": {
        "code_quality": 0.10, "task_completion": 0.10,
        "collaboration": 0.30, "reliability": 0.40, "innovation": 0.10,
    },
    "npc_management": {
        "code_quality": 0.20, "task_completion": 0.20,
        "collaboration": 0.20, "reliability": 0.20, "innovation": 0.20,
    },
    "spell_creation": {
        "code_quality": 0.30, "task_completion": 0.15,
        "collaboration": 0.10, "reliability": 0.20, "innovation": 0.25,
    },
    "world_editing": {
        "code_quality": 0.25, "task_completion": 0.20,
        "collaboration": 0.15, "reliability": 0.30, "innovation": 0.10,
    },
    "system_config": {
        "code_quality": 0.30, "task_completion": 0.20,
        "collaboration": 0.10, "reliability": 0.30, "innovation": 0.10,
    },
    "review_override": {
        "code_quality": 0.25, "task_completion": 0.15,
        "collaboration": 0.20, "reliability": 0.30, "innovation": 0.10,
    },
    "cross_fleet_access": {
        "code_quality": 0.10, "task_completion": 0.15,
        "collaboration": 0.30, "reliability": 0.35, "innovation": 0.10,
    },
    "emergency_powers": {
        "code_quality": 0.15, "task_completion": 0.20,
        "collaboration": 0.20, "reliability": 0.40, "innovation": 0.05,
    },
}


# ═══════════════════════════════════════════════════════════════
# Data Classes
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrustPermissionConfig:
    """Configuration for the trust-permission bridge."""

    trust_thresholds: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_PERMISSION_THRESHOLDS)
    )
    default_threshold: float = 0.3
    decay_grace_period: float = 86400.0  # 24 hours in seconds
    auto_grant_enabled: bool = True
    auto_revoke_enabled: bool = True
    dimensions_weight: Dict[str, Dict[str, float]] = field(
        default_factory=lambda: dict(DEFAULT_DIMENSION_WEIGHTS)
    )

    def get_threshold(self, permission: str) -> float:
        """Get the trust threshold for a permission, falling back to default."""
        return self.trust_thresholds.get(permission, self.default_threshold)

    def get_dimension_weight(self, permission: str) -> Dict[str, float]:
        """Get dimension weights for a specific permission."""
        return self.dimensions_weight.get(permission, {})

    def to_dict(self) -> dict:
        return {
            "trust_thresholds": self.trust_thresholds,
            "default_threshold": self.default_threshold,
            "decay_grace_period": self.decay_grace_period,
            "auto_grant_enabled": self.auto_grant_enabled,
            "auto_revoke_enabled": self.auto_revoke_enabled,
            "dimensions_weight": self.dimensions_weight,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TrustPermissionConfig':
        return cls(
            trust_thresholds=data.get("trust_thresholds", dict(DEFAULT_PERMISSION_THRESHOLDS)),
            default_threshold=data.get("default_threshold", 0.3),
            decay_grace_period=data.get("decay_grace_period", 86400.0),
            auto_grant_enabled=data.get("auto_grant_enabled", True),
            auto_revoke_enabled=data.get("auto_revoke_enabled", True),
            dimensions_weight=data.get("dimensions_weight", dict(DEFAULT_DIMENSION_WEIGHTS)),
        )


@dataclass
class PermissionEvaluation:
    """Result of evaluating an agent's permission status."""

    agent_name: str
    granted: List[str] = field(default_factory=list)
    denied: List[str] = field(default_factory=list)
    revoked: List[str] = field(default_factory=list)
    trust_scores: Dict[str, float] = field(default_factory=dict)

    def total_permissions(self) -> int:
        return len(self.granted) + len(self.denied) + len(self.revoked)

    def grant_rate(self) -> float:
        total = self.total_permissions()
        if total == 0:
            return 0.0
        return len(self.granted) / total

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "granted": sorted(self.granted),
            "denied": sorted(self.denied),
            "revoked": sorted(self.revoked),
            "trust_scores": self.trust_scores,
            "total_permissions": self.total_permissions(),
            "grant_rate": round(self.grant_rate(), 4),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'PermissionEvaluation':
        return cls(
            agent_name=data["agent_name"],
            granted=data.get("granted", []),
            denied=data.get("denied", []),
            revoked=data.get("revoked", []),
            trust_scores=data.get("trust_scores", {}),
        )


@dataclass
class SyncResult:
    """Result of syncing trust state to permission state."""

    agent_name: str
    granted_count: int = 0
    revoked_count: int = 0
    unchanged_count: int = 0
    details: List[dict] = field(default_factory=list)

    def total_changes(self) -> int:
        return self.granted_count + self.revoked_count

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "granted_count": self.granted_count,
            "revoked_count": self.revoked_count,
            "unchanged_count": self.unchanged_count,
            "total_changes": self.total_changes(),
            "details": self.details,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'SyncResult':
        return cls(
            agent_name=data["agent_name"],
            granted_count=data.get("granted_count", 0),
            revoked_count=data.get("revoked_count", 0),
            unchanged_count=data.get("unchanged_count", 0),
            details=data.get("details", []),
        )


# ═══════════════════════════════════════════════════════════════
# Trust Permission Bridge
# ═══════════════════════════════════════════════════════════════

class TrustPermissionBridge:
    """Bridges trust scores to permission grants/revocations.

    The bridge reads trust profiles from the TrustEngine, evaluates
    composite trust against permission thresholds, and syncs the
    resulting permission state to the PermissionField.
    """

    def __init__(
        self,
        config: TrustPermissionConfig = None,
        trust_engine=None,
        permission_field=None,
    ):
        self.config = config or TrustPermissionConfig()
        self.trust_engine = trust_engine
        self.permission_field = permission_field
        # Track when permissions were granted for grace period calculation
        self._grant_timestamps: Dict[str, Dict[str, float]] = {}
        # Track previously known state for revocation detection
        self._last_known_permissions: Dict[str, set] = {}

    # ── Permission Threshold Management ────────────────────────

    def add_threshold(self, permission: str, min_trust: float):
        """Add or update a custom permission threshold."""
        if min_trust < 0.0 or min_trust > 1.0:
            raise ValueError(f"Trust threshold must be in [0.0, 1.0], got {min_trust}")
        self.config.trust_thresholds[permission] = min_trust

    def remove_threshold(self, permission: str):
        """Remove a permission threshold. Falls back to default."""
        self.config.trust_thresholds.pop(permission, None)

    def get_permission_trust_requirement(self, permission: str) -> float:
        """Return the minimum trust score needed for a permission."""
        return self.config.get_threshold(permission)

    def get_agent_trust_gap(self, agent_name: str, permission: str) -> float:
        """How much more trust an agent needs for a permission.

        Returns 0.0 if the agent already qualifies (or is within threshold).
        Returns negative if the agent exceeds the requirement.
        """
        threshold = self.config.get_threshold(permission)
        trust = self._get_agent_composite_trust(agent_name)
        return max(0.0, threshold - trust)

    def get_agent_trust_gap_weighted(self, agent_name: str, permission: str) -> float:
        """Trust gap using dimension-weighted trust for the specific permission."""
        threshold = self.config.get_threshold(permission)
        trust = self._get_weighted_trust(agent_name, permission)
        return max(0.0, threshold - trust)

    def list_all_permissions(self) -> List[str]:
        """List all registered permissions with thresholds."""
        return sorted(self.config.trust_thresholds.keys())

    def list_permissions_for_trust(self, trust_score: float) -> List[str]:
        """List all permissions that would be granted at a given trust level."""
        return sorted(
            perm for perm, threshold in self.config.trust_thresholds.items()
            if trust_score >= threshold
        )

    # ── Core Evaluation ────────────────────────────────────────

    def evaluate_permissions(self, agent_name: str) -> PermissionEvaluation:
        """Evaluate which permissions an agent qualifies for based on trust.

        Returns a PermissionEvaluation with granted, denied, and revoked lists.
        Revoked = previously granted permissions that are no longer qualified.
        """
        composite_trust = self._get_agent_composite_trust(agent_name)
        trust_scores = self._get_all_trust_scores(agent_name)

        granted = []
        denied = []
        all_permissions = sorted(self.config.trust_thresholds.keys())

        for perm in all_permissions:
            threshold = self.config.get_threshold(perm)
            if composite_trust >= threshold:
                granted.append(perm)
            else:
                denied.append(perm)

        # Determine revoked: was granted before but now denied
        prev = self._last_known_permissions.get(agent_name, set())
        current_granted = set(granted)
        revoked = sorted(prev - current_granted)

        # Update last known
        self._last_known_permissions[agent_name] = current_granted

        return PermissionEvaluation(
            agent_name=agent_name,
            granted=granted,
            denied=denied,
            revoked=revoked,
            trust_scores=trust_scores,
        )

    def evaluate_permissions_weighted(self, agent_name: str) -> PermissionEvaluation:
        """Evaluate using dimension-weighted trust per permission."""
        trust_scores = self._get_all_trust_scores(agent_name)

        granted = []
        denied = []
        all_permissions = sorted(self.config.trust_thresholds.keys())

        for perm in all_permissions:
            threshold = self.config.get_threshold(perm)
            weighted_trust = self._get_weighted_trust(agent_name, perm)
            if weighted_trust >= threshold:
                granted.append(perm)
            else:
                denied.append(perm)

        # Determine revoked
        prev = self._last_known_permissions.get(agent_name, set())
        current_granted = set(granted)
        revoked = sorted(prev - current_granted)

        self._last_known_permissions[agent_name] = current_granted

        return PermissionEvaluation(
            agent_name=agent_name,
            granted=granted,
            denied=denied,
            revoked=revoked,
            trust_scores=trust_scores,
        )

    # ── Sync Trust to Permissions ──────────────────────────────

    def sync_trust_to_permissions(self, agent_name: str) -> SyncResult:
        """Sync trust state to permission state, granting/revoking as needed.

        If auto_grant is enabled, newly qualifying permissions are activated.
        If auto_revoke is enabled, permissions lost due to trust decay are
        revoked (after grace period).
        """
        evaluation = self.evaluate_permissions(agent_name)
        details = []
        granted_count = 0
        revoked_count = 0
        unchanged_count = 0
        now = time.time()

        for perm in evaluation.granted:
            if self.permission_field is not None:
                # Check if this is a new grant
                was_previously = agent_name in self._grant_timestamps and \
                                 perm in self._grant_timestamps[agent_name]
                if not was_previously:
                    if self.config.auto_grant_enabled:
                        details.append({
                            "permission": perm,
                            "action": "granted",
                            "trust": evaluation.trust_scores.get("composite", 0),
                            "threshold": self.config.get_threshold(perm),
                        })
                        self._track_grant(agent_name, perm, now)
                        granted_count += 1
                    else:
                        unchanged_count += 1
                else:
                    unchanged_count += 1
            else:
                unchanged_count += 1

        for perm in evaluation.revoked:
            if self.permission_field is not None:
                grant_time = self._grant_timestamps.get(agent_name, {}).get(perm)
                in_grace = (
                    grant_time is not None and
                    (now - grant_time) < self.config.decay_grace_period
                )
                if in_grace:
                    # Still within grace period — don't revoke yet
                    unchanged_count += 1
                    details.append({
                        "permission": perm,
                        "action": "grace_period",
                        "remaining_seconds": round(
                            self.config.decay_grace_period - (now - grant_time)
                        ),
                    })
                elif self.config.auto_revoke_enabled:
                    details.append({
                        "permission": perm,
                        "action": "revoked",
                        "trust": evaluation.trust_scores.get("composite", 0),
                        "threshold": self.config.get_threshold(perm),
                    })
                    self._untrack_grant(agent_name, perm)
                    revoked_count += 1
                else:
                    unchanged_count += 1
            else:
                revoked_count += 1

        return SyncResult(
            agent_name=agent_name,
            granted_count=granted_count,
            revoked_count=revoked_count,
            unchanged_count=unchanged_count,
            details=details,
        )

    # ── Batch Operations ───────────────────────────────────────

    def batch_evaluate(self, agent_names: List[str]) -> Dict[str, PermissionEvaluation]:
        """Evaluate permissions for multiple agents at once."""
        return {
            name: self.evaluate_permissions(name)
            for name in agent_names
        }

    def batch_sync(self, agent_names: List[str]) -> Dict[str, SyncResult]:
        """Sync trust to permissions for multiple agents."""
        return {
            name: self.sync_trust_to_permissions(name)
            for name in agent_names
        }

    def batch_trust_gaps(
        self, agent_names: List[str], permission: str
    ) -> Dict[str, float]:
        """Get trust gaps for multiple agents for a single permission."""
        return {
            name: self.get_agent_trust_gap(name, permission)
            for name in agent_names
        }

    # ── Grace Period Management ────────────────────────────────

    def get_grant_time(self, agent_name: str, permission: str) -> Optional[float]:
        """Get when a permission was granted to an agent."""
        return self._grant_timestamps.get(agent_name, {}).get(permission)

    def is_in_grace_period(self, agent_name: str, permission: str) -> bool:
        """Check if a permission is still within its grace period."""
        grant_time = self.get_grant_time(agent_name, permission)
        if grant_time is None:
            return False
        return (time.time() - grant_time) < self.config.decay_grace_period

    def remaining_grace(self, agent_name: str, permission: str) -> float:
        """Seconds remaining in grace period. 0 if not in grace."""
        grant_time = self.get_grant_time(agent_name, permission)
        if grant_time is None:
            return 0.0
        remaining = self.config.decay_grace_period - (time.time() - grant_time)
        return max(0.0, remaining)

    def set_grace_period(self, seconds: float):
        """Update the decay grace period."""
        if seconds < 0:
            raise ValueError("Grace period must be non-negative")
        self.config.decay_grace_period = seconds

    # ── Internal Helpers ───────────────────────────────────────

    def _get_agent_composite_trust(self, agent_name: str) -> float:
        """Get the composite trust score for an agent."""
        if self.trust_engine is not None:
            try:
                trust = self.trust_engine.composite_trust(agent_name)
                if trust is not None and isinstance(trust, (int, float)):
                    return float(trust)
            except (KeyError, AttributeError, TypeError):
                pass
        # Fall back: check if agent has any known state
        if agent_name in self._last_known_permissions:
            return 0.3  # BASE_TRUST default
        return 0.0

    def _get_weighted_trust(self, agent_name: str, permission: str) -> float:
        """Get dimension-weighted trust for a specific permission."""
        if self.trust_engine is None:
            return self._get_agent_composite_trust(agent_name)

        dim_weights = self.config.get_dimension_weight(permission)
        if not dim_weights:
            return self._get_agent_composite_trust(agent_name)

        try:
            profile = self.trust_engine.get_profile(agent_name)
            composite = profile.composite(weights=dim_weights)
            return composite
        except (KeyError, AttributeError):
            return self._get_agent_composite_trust(agent_name)

    def _get_all_trust_scores(self, agent_name: str) -> Dict[str, float]:
        """Get all trust dimension scores and composite for an agent."""
        scores = {"composite": self._get_agent_composite_trust(agent_name)}

        if self.trust_engine is not None:
            try:
                profile = self.trust_engine.get_profile(agent_name)
                summary = profile.summary()
                if "dimensions" in summary:
                    scores.update(summary["dimensions"])
            except (KeyError, AttributeError):
                pass

        return scores

    def _track_grant(self, agent_name: str, permission: str, timestamp: float):
        """Record when a permission was granted."""
        if agent_name not in self._grant_timestamps:
            self._grant_timestamps[agent_name] = {}
        self._grant_timestamps[agent_name][permission] = timestamp

    def _untrack_grant(self, agent_name: str, permission: str):
        """Remove a grant timestamp record."""
        if agent_name in self._grant_timestamps:
            self._grant_timestamps[agent_name].pop(permission, None)
            if not self._grant_timestamps[agent_name]:
                del self._grant_timestamps[agent_name]

    # ── Serialization ──────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the full bridge state."""
        return {
            "config": self.config.to_dict(),
            "grant_timestamps": self._grant_timestamps,
            "last_known_permissions": {
                k: sorted(v) for k, v in self._last_known_permissions.items()
            },
        }

    @classmethod
    def from_dict(cls, data: dict, trust_engine=None, permission_field=None) -> 'TrustPermissionBridge':
        """Restore a bridge from serialized state."""
        config = TrustPermissionConfig.from_dict(data.get("config", {}))
        bridge = cls(
            config=config,
            trust_engine=trust_engine,
            permission_field=permission_field,
        )
        bridge._grant_timestamps = data.get("grant_timestamps", {})
        bridge._last_known_permissions = {
            k: set(v) for k, v in data.get("last_known_permissions", {}).items()
        }
        return bridge

    # ── Summary / Reporting ────────────────────────────────────

    def summary(self) -> dict:
        """Generate a summary of bridge state."""
        return {
            "total_permissions": len(self.config.trust_thresholds),
            "total_agents_tracked": len(self._last_known_permissions),
            "auto_grant": self.config.auto_grant_enabled,
            "auto_revoke": self.config.auto_revoke_enabled,
            "grace_period_hours": self.config.decay_grace_period / 3600.0,
            "default_threshold": self.config.default_threshold,
            "min_threshold": min(self.config.trust_thresholds.values()) if self.config.trust_thresholds else 0,
            "max_threshold": max(self.config.trust_thresholds.values()) if self.config.trust_thresholds else 0,
        }

    def agent_summary(self, agent_name: str) -> dict:
        """Generate a summary for a specific agent."""
        evaluation = self.evaluate_permissions(agent_name)
        gap_info = {}
        for perm in evaluation.denied:
            gap_info[perm] = round(self.get_agent_trust_gap(agent_name, perm), 4)

        return {
            "agent_name": agent_name,
            "composite_trust": evaluation.trust_scores.get("composite", 0),
            "granted_count": len(evaluation.granted),
            "denied_count": len(evaluation.denied),
            "revoked_count": len(evaluation.revoked),
            "granted_permissions": sorted(evaluation.granted),
            "trust_gaps": gap_info,
            "grant_rate": round(evaluation.grant_rate(), 4),
        }

    def compare_agents(
        self, agent_a: str, agent_b: str
    ) -> dict:
        """Compare permission access between two agents."""
        eval_a = self.evaluate_permissions(agent_a)
        eval_b = self.evaluate_permissions(agent_b)

        set_a = set(eval_a.granted)
        set_b = set(eval_b.granted)

        return {
            "agent_a": agent_a,
            "agent_b": agent_b,
            "trust_a": eval_a.trust_scores.get("composite", 0),
            "trust_b": eval_b.trust_scores.get("composite", 0),
            "shared": sorted(set_a & set_b),
            "only_a": sorted(set_a - set_b),
            "only_b": sorted(set_b - set_a),
            "permission_distance": len(set_a.symmetric_difference(set_b)),
        }
