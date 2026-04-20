#!/usr/bin/env python3
"""
Cross-Project Trust Portability Layer for Tabula Rasa SuperInstance Fleet
==========================================================================

Enables trust earned in one SuperInstance repository to carry weight in another.
This module bridges trust across the fleet, making reputation a portable asset.

Based on research from:
- Jøsang (2001): A Logic for Uncertain Probabilities — Subjective Logic
- Jøsang, Hayward & Pope (2006): Trust Network Analysis with Subjective Logic
- Ding et al. (2009): Computing Reputation in Online Social Networks
- Gartner TRiSM (2024): Trust, Risk, Security Management for Agentic AI
- RepuNet (2025): Dynamic Dual-Level Reputation for LLM-based MAS

Design principles:
1. Trust is portable — earned in one repo, recognized in others
2. Attestations are signed — tamper-proof via HMAC-SHA256
3. Foreign trust decays — older attestations count less
4. Inconsistency is detectable — conflicting repo reports are flagged
5. Trust propagates — transitivity via Subjective Logic discount operator
6. Replay attacks prevented — each attestation has a unique fingerprint
7. Anchors of trust — designated repos whose attestations are auto-accepted

Architecture:
    Repo A (local)                      Repo B (foreign)
    ┌──────────────┐                    ┌──────────────┐
    │ TrustEngine  │──export──>│  TrustAttestation  │──import──>│ FleetTrustBridge │
    │              │                    │ (signed proof)    │            │ (blended trust)  │
    └──────────────┘                    └──────────────┘            └──────────────────┘
                                                                              │
                                                    ┌─────────────────────────┘
                                                    v
                                          TrustPropagationGraph
                                          (cross-fleet trust paths)
"""

import json
import time
import math
import hashlib
import hmac
from typing import (
    Optional, Dict, List, Tuple, Set, Any,
    Callable, NamedTuple
)
from dataclasses import dataclass, field
from collections import deque


# ═══════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════

# Shared fleet key for HMAC-SHA256 attestation signing.
# In production, this would be injected from environment or KMS.
FLEET_TRUST_KEY: str = "superinstance-fleet-trust-v1"

# Default weight for foreign trust when blending with local trust.
# 0.0 = ignore foreign, 1.0 = only foreign. 0.3 means 30% foreign, 70% local.
DEFAULT_IMPORT_FACTOR: float = 0.3

# How many seconds before a foreign attestation is considered stale.
ATTESTATION_STALENESS_SECONDS: float = 30 * 86400  # 30 days

# Exponential decay rate for foreign attestations (per day).
# After 7 days, weight is multiplied by FOREIGN_DECAY_RATE^7 ≈ 0.72
FOREIGN_DECAY_RATE: float = 0.96

# Maximum BFS depth for trust path finding.
MAX_PATH_DEPTH: int = 3

# Threshold for flagging trust inconsistency between repos.
# If two repos differ by more than this on composite trust, flag it.
INCONSISTENCY_THRESHOLD: float = 0.4

# Minimum number of sources required for consensus computation.
MIN_CONSENSUS_SOURCES: int = 2

# Maximum age in seconds for an attestation to be considered valid.
ATTESTATION_MAX_AGE: float = 90 * 86400  # 90 days

# Echo chamber detection threshold: if all edges point inward, it's a chamber.
ECHO_CHAMBER_INWARD_RATIO: float = 0.8


# ═══════════════════════════════════════════════════════════════
# Trust Dimensions — mirrors trust_engine.TRUST_DIMENSIONS
# ═══════════════════════════════════════════════════════════════

TRUST_DIMENSIONS: List[str] = [
    "code_quality",
    "task_completion",
    "collaboration",
    "reliability",
    "innovation",
]

BASE_TRUST: float = 0.3


# ═══════════════════════════════════════════════════════════════
# Cross-Repo Trust Event Presets
# ═══════════════════════════════════════════════════════════════

CROSS_REPO_TRUST_EVENTS: Dict[str, Dict[str, Any]] = {
    "cross_repo_code_review": {
        "dimension": "code_quality",
        "value": 0.85,
        "weight": 1.2,
        "description": "Agent submitted code reviewed and approved by another repo",
    },
    "foreign_task_completed": {
        "dimension": "task_completion",
        "value": 0.8,
        "weight": 1.0,
        "description": "Agent successfully completed a task assigned by a foreign repo",
    },
    "fleet_collaboration": {
        "dimension": "collaboration",
        "value": 0.9,
        "weight": 1.3,
        "description": "Agent demonstrated effective cross-repo collaboration",
    },
    "cross_repo_bug_found": {
        "dimension": "code_quality",
        "value": 0.8,
        "weight": 0.9,
        "description": "Agent found a bug in code from another repo",
    },
    "foreign_dependency_shipped": {
        "dimension": "reliability",
        "value": 0.85,
        "weight": 1.1,
        "description": "Agent delivered a dependency that was used by another repo",
    },
    "fleet_knowledge_shared": {
        "dimension": "collaboration",
        "value": 0.8,
        "weight": 0.8,
        "description": "Agent shared useful knowledge across the fleet",
    },
    "cross_repo_innovation": {
        "dimension": "innovation",
        "value": 0.9,
        "weight": 1.2,
        "description": "Agent introduced a novel approach adopted by another repo",
    },
    "fleet_conflict_resolved": {
        "dimension": "collaboration",
        "value": 0.85,
        "weight": 1.0,
        "description": "Agent helped resolve a cross-repo conflict",
    },
    "foreign_integration_success": {
        "dimension": "reliability",
        "value": 0.8,
        "weight": 1.0,
        "description": "Agent's work integrated successfully into another repo",
    },
    "cross_repo_mentorship": {
        "dimension": "collaboration",
        "value": 0.9,
        "weight": 1.1,
        "description": "Agent mentored someone from another repo effectively",
    },
}


# ═══════════════════════════════════════════════════════════════
# 1. TrustAttestation — Signed Trust Proof
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrustAttestation:
    """
    A cryptographically signed trust proof that can be exported from one
    SuperInstance repo and imported into another.

    The attestation contains:
    - Agent identity (who the trust is about)
    - Trust dimensions (per-dimension scores)
    - Composite score (weighted aggregate)
    - Issuer info (which repo issued this)
    - Timestamp (when it was created)
    - HMAC-SHA256 signature (tamper-proof)
    - Trust vector fingerprint (for replay detection)

    The attestation is the unit of cross-repo trust portability.
    It is immutable once signed — any modification invalidates the signature.
    """

    # Identity
    agent_name: str = ""
    issuer_repo: str = ""
    issuer_id: str = ""

    # Trust data
    dimensions: Dict[str, float] = field(default_factory=dict)
    composite: float = BASE_TRUST

    # Evidence metadata
    event_count: int = 0
    is_meaningful: bool = False
    cross_repo_events: List[str] = field(default_factory=list)

    # Timing
    issued_at: float = field(default_factory=time.time)
    expires_at: float = 0.0  # 0 = never expires

    # Cryptographic
    signature: str = ""
    fingerprint: str = ""

    def __post_init__(self):
        """Ensure dimensions dict has all trust dimensions populated."""
        for dim in TRUST_DIMENSIONS:
            if dim not in self.dimensions:
                self.dimensions[dim] = BASE_TRUST

    def compute_fingerprint(self) -> str:
        """
        Compute a unique fingerprint for this attestation.

        The fingerprint is a SHA-256 hash of the attestation's content
        (excluding the signature itself). Used for replay detection:
        if the same fingerprint is imported twice, it's a replay attack.
        """
        content = self._content_hash_input()
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _content_hash_input(self) -> str:
        """
        Build the canonical string used for signing and fingerprinting.

        Fields are sorted to ensure deterministic ordering regardless
        of how the dict was constructed.
        """
        sorted_dims = json.dumps(
            {k: self.dimensions[k] for k in sorted(self.dimensions)},
            separators=(",", ":")
        )
        sorted_events = json.dumps(sorted(self.cross_repo_events), separators=(",", ":"))
        return (
            f"{self.agent_name}|{self.issuer_repo}|{self.issuer_id}|"
            f"{sorted_dims}|{self.composite}|{self.event_count}|"
            f"{self.is_meaningful}|{sorted_events}|{self.issued_at}|{self.expires_at}"
        )

    def sign(self, key: str = FLEET_TRUST_KEY):
        """
        Sign this attestation using HMAC-SHA256 with the fleet key.

        The signature covers all trust data plus metadata, making it
        tamper-proof. Any modification to the attestation after signing
        will cause verification to fail.
        """
        self.fingerprint = self.compute_fingerprint()
        message = self._content_hash_input()
        self.signature = hmac.new(
            key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def verify(self, key: str = FLEET_TRUST_KEY) -> bool:
        """
        Verify the attestation's HMAC-SHA256 signature.

        Returns True if:
        1. The signature is non-empty
        2. The fingerprint matches the current content
        3. The HMAC verification succeeds

        This ensures the attestation has not been tampered with
        since it was signed by the issuing repo.
        """
        if not self.signature:
            return False

        # Check fingerprint integrity
        current_fingerprint = self.compute_fingerprint()
        if self.fingerprint and self.fingerprint != current_fingerprint:
            return False

        # Verify HMAC
        message = self._content_hash_input()
        expected = hmac.new(
            key.encode("utf-8"),
            message.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(self.signature, expected)

    def is_expired(self, current_time: float = None) -> bool:
        """Check if this attestation has expired."""
        if self.expires_at <= 0:
            return False
        now = current_time or time.time()
        return now > self.expires_at

    def age_seconds(self, current_time: float = None) -> float:
        """How old this attestation is in seconds."""
        now = current_time or time.time()
        return now - self.issued_at

    def age_days(self, current_time: float = None) -> float:
        """How old this attestation is in days."""
        return self.age_seconds(current_time) / 86400.0

    def decayed_weight(self, current_time: float = None) -> float:
        """
        Compute a decay factor based on attestation age.

        Uses exponential decay: weight = FOREIGN_DECAY_RATE^days.
        A fresh attestation (0 days old) returns 1.0.
        After 30 days, returns ~0.29.
        """
        days = self.age_days(current_time)
        return FOREIGN_DECAY_RATE ** days

    def to_dict(self) -> dict:
        """Serialize this attestation to a dictionary."""
        return {
            "agent_name": self.agent_name,
            "issuer_repo": self.issuer_repo,
            "issuer_id": self.issuer_id,
            "dimensions": dict(self.dimensions),
            "composite": round(self.composite, 6),
            "event_count": self.event_count,
            "is_meaningful": self.is_meaningful,
            "cross_repo_events": list(self.cross_repo_events),
            "issued_at": self.issued_at,
            "expires_at": self.expires_at,
            "signature": self.signature,
            "fingerprint": self.fingerprint,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TrustAttestation':
        """Deserialize an attestation from a dictionary."""
        att = cls(
            agent_name=data.get("agent_name", ""),
            issuer_repo=data.get("issuer_repo", ""),
            issuer_id=data.get("issuer_id", ""),
            dimensions=data.get("dimensions", {}),
            composite=data.get("composite", BASE_TRUST),
            event_count=data.get("event_count", 0),
            is_meaningful=data.get("is_meaningful", False),
            cross_repo_events=data.get("cross_repo_events", []),
            issued_at=data.get("issued_at", time.time()),
            expires_at=data.get("expires_at", 0.0),
            signature=data.get("signature", ""),
            fingerprint=data.get("fingerprint", ""),
        )
        return att

    def to_json(self, indent: int = 2) -> str:
        """Serialize to a JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, json_str: str) -> 'TrustAttestation':
        """Deserialize from a JSON string."""
        return cls.from_dict(json.loads(json_str))


# ═══════════════════════════════════════════════════════════════
# 2. FleetTrustBridge — Main Bridge Class
# ═══════════════════════════════════════════════════════════════

@dataclass
class InconsistencyReport:
    """A report of trust inconsistency between repos for an agent."""
    agent_name: str
    repo_scores: Dict[str, float]  # repo -> composite score
    max_difference: float
    flagged: bool
    description: str

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name,
            "repo_scores": {k: round(v, 4) for k, v in self.repo_scores.items()},
            "max_difference": round(self.max_difference, 4),
            "flagged": self.flagged,
            "description": self.description,
        }


class FleetTrustBridge:
    """
    The main bridge between local and foreign trust.

    Maintains a cache of foreign trust attestations and blends them with
    local trust scores. Provides unified fleet-wide trust computation.

    Key responsibilities:
    - Import and validate foreign attestations
    - Blend local trust with foreign attestations using configurable weights
    - Compute trust consensus when multiple repos report on the same agent
    - Detect trust inconsistency across repos
    - Auto-decay foreign attestations based on age
    """

    def __init__(
        self,
        local_repo: str = "local",
        import_factor: float = DEFAULT_IMPORT_FACTOR,
        fleet_key: str = FLEET_TRUST_KEY,
        trust_getter: Optional[Callable[[str], float]] = None,
    ):
        """
        Initialize the FleetTrustBridge.

        Args:
            local_repo: Name/identifier of this local repository
            import_factor: Weight given to foreign trust (0.0-1.0)
            fleet_key: HMAC key for attestation verification
            trust_getter: Callback to get local trust: fn(agent_name) -> float
        """
        self.local_repo = local_repo
        self.import_factor = max(0.0, min(1.0, import_factor))
        self.fleet_key = fleet_key
        self.trust_getter = trust_getter

        # Foreign attestation cache: agent_name -> [TrustAttestation, ...]
        self._foreign_attestations: Dict[str, List[TrustAttestation]] = {}

        # Fingerprint registry for replay detection: fingerprint -> import timestamp
        self._seen_fingerprints: Dict[str, float] = {}

        # Inconsistency cache: agent_name -> InconsistencyReport
        self._inconsistencies: Dict[str, InconsistencyReport] = {}

        # Import statistics
        self._import_count: int = 0
        self._replay_count: int = 0
        self._invalid_count: int = 0

    def _get_local_trust(self, agent_name: str) -> float:
        """Get local trust score for an agent."""
        if self.trust_getter:
            try:
                return max(0.0, min(1.0, self.trust_getter(agent_name)))
            except Exception:
                pass
        return BASE_TRUST

    # ─── Import / Export ────────────────────────────────────

    def import_attestation(
        self,
        attestation: TrustAttestation,
        current_time: float = None
    ) -> dict:
        """
        Import and validate a foreign trust attestation.

        Validation checks:
        1. Signature verification (HMAC-SHA256)
        2. Replay detection (fingerprint uniqueness)
        3. Expiration check
        4. Maximum age check

        Args:
            attestation: The attestation to import
            current_time: Override current time (for testing)

        Returns:
            dict with 'accepted', 'reason', and 'agent_name'
        """
        now = current_time or time.time()

        # 1. Verify signature
        if not attestation.verify(self.fleet_key):
            self._invalid_count += 1
            return {
                "accepted": False,
                "reason": "invalid_signature",
                "agent_name": attestation.agent_name,
            }

        # 2. Replay detection
        fp = attestation.fingerprint or attestation.compute_fingerprint()
        if fp in self._seen_fingerprints:
            self._replay_count += 1
            return {
                "accepted": False,
                "reason": "replay_detected",
                "agent_name": attestation.agent_name,
                "fingerprint": fp,
            }

        # 3. Expiration check
        if attestation.is_expired(now):
            self._invalid_count += 1
            return {
                "accepted": False,
                "reason": "expired",
                "agent_name": attestation.agent_name,
            }

        # 4. Maximum age check
        if attestation.age_seconds(now) > ATTESTATION_MAX_AGE:
            self._invalid_count += 1
            return {
                "accepted": False,
                "reason": "too_old",
                "agent_name": attestation.agent_name,
                "age_days": round(attestation.age_days(now), 1),
            }

        # All checks passed — register the attestation
        self._seen_fingerprints[fp] = now
        agent = attestation.agent_name

        if agent not in self._foreign_attestations:
            self._foreign_attestations[agent] = []

        # Keep only the most recent attestation from each issuer
        existing = self._foreign_attestations[agent]
        existing = [
            a for a in existing
            if a.issuer_repo != attestation.issuer_repo
        ]
        existing.append(attestation)
        self._foreign_attestations[agent] = existing

        self._import_count += 1

        return {
            "accepted": True,
            "reason": "valid",
            "agent_name": agent,
            "issuer_repo": attestation.issuer_repo,
            "composite": attestation.composite,
        }

    def import_attestations(
        self,
        attestations: List[TrustAttestation],
        current_time: float = None
    ) -> dict:
        """
        Import a batch of attestations.

        Returns:
            dict with 'accepted_count', 'rejected_count', and 'results'
        """
        accepted = 0
        rejected = 0
        results = []

        for att in attestations:
            result = self.import_attestation(att, current_time)
            if result["accepted"]:
                accepted += 1
            else:
                rejected += 1
            results.append(result)

        return {
            "accepted_count": accepted,
            "rejected_count": rejected,
            "results": results,
        }

    def export_attestation(
        self,
        agent_name: str,
        trust_getter: Callable[[str], float],
        composite_getter: Callable[[str], float],
        event_count_getter: Callable[[str], int] = None,
        meaningful_getter: Callable[[str], bool] = None,
        cross_repo_events: List[str] = None,
    ) -> TrustAttestation:
        """
        Create a signed attestation for a local agent's trust.

        This is used when exporting trust from this repo to others.

        Args:
            agent_name: Name of the agent
            trust_getter: fn(dimension) -> float for per-dimension trust
            composite_getter: fn() -> float for composite trust
            event_count_getter: optional fn() -> int for total events
            meaningful_getter: optional fn() -> bool for meaningful check
            cross_repo_events: list of cross-repo event names

        Returns:
            Signed TrustAttestation ready for export
        """
        dimensions = {}
        for dim in TRUST_DIMENSIONS:
            try:
                dimensions[dim] = max(0.0, min(1.0, trust_getter(dim)))
            except Exception:
                dimensions[dim] = BASE_TRUST

        composite = composite_getter()
        composite = max(0.0, min(1.0, composite))

        event_count = 0
        if event_count_getter:
            try:
                event_count = event_count_getter()
            except Exception:
                pass

        is_meaningful = False
        if meaningful_getter:
            try:
                is_meaningful = meaningful_getter()
            except Exception:
                pass

        att = TrustAttestation(
            agent_name=agent_name,
            issuer_repo=self.local_repo,
            issuer_id=self.local_repo,
            dimensions=dimensions,
            composite=composite,
            event_count=event_count,
            is_meaningful=is_meaningful,
            cross_repo_events=cross_repo_events or [],
        )
        att.sign(self.fleet_key)
        return att

    # ─── Trust Blending ─────────────────────────────────────

    def foreign_trust(self, agent_name: str, current_time: float = None) -> float:
        """
        Compute the weighted consensus of foreign trust for an agent.

        If multiple repos have attested for this agent, compute a weighted
        consensus where:
        - Each attestation is weighted by its decay factor (recency)
        - More meaningful attestations get higher weight
        - The final score is the weighted average across all sources

        Returns BASE_TRUST if no foreign attestations exist.
        """
        attestations = self._foreign_attestations.get(agent_name, [])
        if not attestations:
            return BASE_TRUST

        now = current_time or time.time()
        weighted_sum = 0.0
        weight_total = 0.0

        for att in attestations:
            # Skip expired attestations
            if att.is_expired(now):
                continue

            # Decay weight based on age
            decay = att.decayed_weight(now)

            # Meaningful attestations get 2x weight
            meaningful_bonus = 1.5 if att.is_meaningful else 1.0

            # Event count bonus (logarithmic, capped at 2x)
            event_bonus = min(2.0, 1.0 + math.log1p(att.event_count) / math.log1p(20))

            total_weight = decay * meaningful_bonus * event_bonus
            weighted_sum += att.composite * total_weight
            weight_total += total_weight

        if weight_total <= 0:
            return BASE_TRUST

        return max(0.0, min(1.0, weighted_sum / weight_total))

    def fleet_composite_trust(self, agent_name: str, current_time: float = None) -> float:
        """
        Compute a unified trust score blending local and foreign trust.

        Formula: fleet_trust = (1 - α) * local_trust + α * foreign_trust
        where α is the import_factor.

        If no local trust getter is configured, returns BASE_TRUST.
        If no foreign attestations exist, returns local_trust (no foreign
        influence can pull the score down from local-only).
        """
        local = self._get_local_trust(agent_name)
        foreign = self.foreign_trust(agent_name, current_time)

        # If no foreign data, return local only
        attestations = self._foreign_attestations.get(agent_name, [])
        now = current_time or time.time()
        active_attestations = [
            a for a in attestations if not a.is_expired(now)
        ]
        if not active_attestations:
            return local

        blended = (1.0 - self.import_factor) * local + self.import_factor * foreign
        return max(0.0, min(1.0, blended))

    def fleet_dimension_trust(
        self, agent_name: str, dimension: str, current_time: float = None
    ) -> float:
        """
        Get blended trust for a specific dimension.

        Averages the local dimension score with foreign attestations'
        dimension scores, weighted by import_factor.
        """
        attestations = self._foreign_attestations.get(agent_name, [])
        now = current_time or time.time()

        # Get foreign dimension scores (weighted by decay)
        foreign_weighted = 0.0
        foreign_total_weight = 0.0
        for att in attestations:
            if att.is_expired(now):
                continue
            decay = att.decayed_weight(now)
            dim_score = att.dimensions.get(dimension, BASE_TRUST)
            foreign_weighted += dim_score * decay
            foreign_total_weight += decay

        if foreign_total_weight <= 0:
            return self._get_local_trust(agent_name)

        foreign_dim = foreign_weighted / foreign_total_weight
        # Use composite-based local trust as proxy for dimension-specific
        local = self._get_local_trust(agent_name)
        blended = (1.0 - self.import_factor) * local + self.import_factor * foreign_dim
        return max(0.0, min(1.0, blended))

    # ─── Inconsistency Detection ────────────────────────────

    def detect_inconsistencies(self, current_time: float = None) -> List[InconsistencyReport]:
        """
        Detect trust inconsistency across repos for all agents.

        If repo A reports trust 0.8 and repo B reports 0.2 for the same agent,
        this signals a potential issue (sybil attack, context mismatch, etc.).

        Returns list of InconsistencyReports for all flagged agents.
        """
        now = current_time or time.time()
        reports = []

        for agent_name, attestations in self._foreign_attestations.items():
            active = [a for a in attestations if not a.is_expired(now)]
            if len(active) < MIN_CONSENSUS_SOURCES:
                continue

            repo_scores = {}
            for att in active:
                repo_scores[att.issuer_repo] = att.composite

            # Add local score
            local = self._get_local_trust(agent_name)
            repo_scores[self.local_repo] = local

            scores = list(repo_scores.values())
            max_diff = max(scores) - min(scores)

            flagged = max_diff > INCONSISTENCY_THRESHOLD

            report = InconsistencyReport(
                agent_name=agent_name,
                repo_scores=repo_scores,
                max_difference=max_diff,
                flagged=flagged,
                description=(
                    f"Trust for '{agent_name}' varies from "
                    f"{min(scores):.2f} to {max(scores):.2f} across "
                    f"{len(repo_scores)} sources"
                    + (" — INCONSISTENT" if flagged else "")
                ),
            )
            reports.append(report)
            self._inconsistencies[agent_name] = report

        return sorted(reports, key=lambda r: r.max_difference, reverse=True)

    def get_inconsistency(self, agent_name: str) -> Optional[InconsistencyReport]:
        """Get the cached inconsistency report for a specific agent."""
        return self._inconsistencies.get(agent_name)

    # ─── Consensus ──────────────────────────────────────────

    def trust_consensus(self, agent_name: str, current_time: float = None) -> dict:
        """
        Compute trust consensus across all repos for an agent.

        Returns:
            dict with 'local', 'foreign', 'fleet', 'sources', 'consensus_score'
        """
        local = self._get_local_trust(agent_name)
        foreign = self.foreign_trust(agent_name, current_time)
        fleet = self.fleet_composite_trust(agent_name, current_time)

        attestations = self._foreign_attestations.get(agent_name, [])
        now = current_time or time.time()
        sources = {
            att.issuer_repo: {
                "composite": round(att.composite, 4),
                "age_days": round(att.age_days(now), 1),
                "decayed_weight": round(att.decayed_weight(now), 4),
                "meaningful": att.is_meaningful,
            }
            for att in attestations
            if not att.is_expired(now)
        }
        sources[self.local_repo] = {
            "composite": round(local, 4),
            "age_days": 0.0,
            "decayed_weight": 1.0,
            "meaningful": True,
        }

        # Consensus score: how much agreement is there between sources?
        all_scores = [s["composite"] for s in sources.values()]
        if len(all_scores) >= 2:
            mean = sum(all_scores) / len(all_scores)
            variance = sum((s - mean) ** 2 for s in all_scores) / len(all_scores)
            std_dev = math.sqrt(variance)
            # Consensus is inverse of normalized std dev (1 = perfect agreement)
            consensus_score = max(0.0, 1.0 - std_dev / 0.5)  # 0.5 = moderate disagreement
        else:
            consensus_score = 1.0  # No disagreement possible with one source

        return {
            "agent_name": agent_name,
            "local_trust": round(local, 4),
            "foreign_trust": round(foreign, 4),
            "fleet_trust": round(fleet, 4),
            "source_count": len(sources),
            "sources": sources,
            "consensus_score": round(consensus_score, 4),
        }

    # ─── Maintenance ───────────────────────────────────────

    def prune_stale_attestations(self, current_time: float = None) -> int:
        """Remove expired attestations from the cache. Returns count removed."""
        now = current_time or time.time()
        removed = 0

        for agent_name in list(self._foreign_attestations.keys()):
            before = len(self._foreign_attestations[agent_name])
            self._foreign_attestations[agent_name] = [
                a for a in self._foreign_attestations[agent_name]
                if not a.is_expired(now) and a.age_seconds(now) <= ATTESTATION_MAX_AGE
            ]
            after = len(self._foreign_attestations[agent_name])
            removed += before - after

            # Clean up empty entries
            if not self._foreign_attestations[agent_name]:
                del self._foreign_attestations[agent_name]

        # Prune old fingerprints (keep for ATTESTATION_MAX_AGE + buffer)
        fp_cutoff = now - ATTESTATION_MAX_AGE - (7 * 86400)
        stale_fps = [fp for fp, ts in self._seen_fingerprints.items() if ts < fp_cutoff]
        for fp in stale_fps:
            del self._seen_fingerprints[fp]

        return removed

    def agents_with_foreign_trust(self) -> List[str]:
        """Get list of agents that have foreign attestations."""
        return list(self._foreign_attestations.keys())

    def stats(self) -> dict:
        """Bridge statistics."""
        total_attestations = sum(
            len(atts) for atts in self._foreign_attestations.values()
        )
        return {
            "local_repo": self.local_repo,
            "import_factor": self.import_factor,
            "agents_with_foreign_trust": len(self._foreign_attestations),
            "total_foreign_attestations": total_attestations,
            "total_imports": self._import_count,
            "replays_detected": self._replay_count,
            "invalid_attestations": self._invalid_count,
            "unique_fingerprints_tracked": len(self._seen_fingerprints),
            "inconsistencies_detected": len(self._inconsistencies),
            "inconsistencies_flagged": sum(
                1 for r in self._inconsistencies.values() if r.flagged
            ),
        }

    # ─── Serialization ─────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the bridge state to a dictionary."""
        return {
            "local_repo": self.local_repo,
            "import_factor": self.import_factor,
            "foreign_attestations": {
                agent: [att.to_dict() for att in atts]
                for agent, atts in self._foreign_attestations.items()
            },
            "stats": self.stats(),
        }

    @classmethod
    def from_dict(cls, data: dict, trust_getter: Callable = None) -> 'FleetTrustBridge':
        """Deserialize a bridge from a dictionary."""
        bridge = cls(
            local_repo=data.get("local_repo", "local"),
            import_factor=data.get("import_factor", DEFAULT_IMPORT_FACTOR),
            trust_getter=trust_getter,
        )
        for agent, att_list in data.get("foreign_attestations", {}).items():
            bridge._foreign_attestations[agent] = [
                TrustAttestation.from_dict(att_data) for att_data in att_list
            ]
        # Rebuild fingerprint registry
        for att_list in bridge._foreign_attestations.values():
            for att in att_list:
                if att.fingerprint:
                    bridge._seen_fingerprints[att.fingerprint] = att.issued_at
        return bridge


# ═══════════════════════════════════════════════════════════════
# 3. TrustPropagationGraph — Cross-Fleet Trust Network
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrustEdge:
    """
    A directed trust relationship between two agents.

    trust_value is the source agent's trust in the target agent.
    This uses Subjective Logic: the trust value is the belief component
    of the opinion triplet (b, d, u) where b + d + u = 1.

    For simplification, we store a single trust value [0, 1] which
    represents the belief. Disbelief and uncertainty are derived:
        d = (1 - b) * 0.5
        u = (1 - b) * 0.5
    """
    source: str
    target: str
    trust_value: float
    weight: float = 1.0  # edge weight for path finding
    repo: str = ""       # which repo this edge originates from
    created_at: float = field(default_factory=time.time)

    @property
    def belief(self) -> float:
        """Subjective Logic belief component."""
        return max(0.0, min(1.0, self.trust_value))

    @property
    def disbelief(self) -> float:
        """Subjective Logic disbelief component (derived)."""
        return (1.0 - self.belief) * 0.5

    @property
    def uncertainty(self) -> float:
        """Subjective Logic uncertainty component (derived)."""
        return (1.0 - self.belief) * 0.5

    @property
    def opinion(self) -> Tuple[float, float, float]:
        """Subjective Logic triplet (belief, disbelief, uncertainty)."""
        return (self.belief, self.disbelief, self.uncertainty)

    def to_dict(self) -> dict:
        return {
            "source": self.source,
            "target": self.target,
            "trust_value": round(self.trust_value, 4),
            "weight": round(self.weight, 4),
            "repo": self.repo,
            "created_at": self.created_at,
            "opinion": {
                "belief": round(self.belief, 4),
                "disbelief": round(self.disbelief, 4),
                "uncertainty": round(self.uncertainty, 4),
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TrustEdge':
        return cls(
            source=data["source"],
            target=data["target"],
            trust_value=data.get("trust_value", BASE_TRUST),
            weight=data.get("weight", 1.0),
            repo=data.get("repo", ""),
            created_at=data.get("created_at", time.time()),
        )


class TrustPropagationGraph:
    """
    Models trust relationships between agents across the fleet.

    Implements a directed graph where:
    - Nodes = agents
    - Edges = trust relationships with weights (Subjective Logic beliefs)

    Key capabilities:
    - Trust transitivity via Subjective Logic discount operator
    - Trust path finding between any two agents (BFS, depth-limited)
    - Cycle detection and echo chamber identification
    - Fleet-wide trust metrics (density, clustering coefficient)
    """

    def __init__(self):
        # Adjacency list: source -> {target: TrustEdge}
        self._edges: Dict[str, Dict[str, TrustEdge]] = {}
        # All known agents (nodes)
        self._agents: Set[str] = set()

    # ─── Graph Construction ────────────────────────────────

    def add_edge(
        self,
        source: str,
        target: str,
        trust_value: float,
        weight: float = 1.0,
        repo: str = "",
    ) -> TrustEdge:
        """
        Add a trust edge from source to target.

        Args:
            source: Agent who trusts
            target: Agent who is trusted
            trust_value: Trust score [0.0, 1.0]
            weight: Edge weight for path computation
            repo: Source repo identifier

        Returns:
            The created TrustEdge
        """
        trust_value = max(0.0, min(1.0, trust_value))
        edge = TrustEdge(
            source=source,
            target=target,
            trust_value=trust_value,
            weight=weight,
            repo=repo,
        )

        if source not in self._edges:
            self._edges[source] = {}
        self._edges[source][target] = edge

        self._agents.add(source)
        self._agents.add(target)

        return edge

    def remove_edge(self, source: str, target: str) -> bool:
        """Remove a trust edge. Returns True if the edge existed."""
        if source in self._edges and target in self._edges[source]:
            del self._edges[source][target]
            if not self._edges[source]:
                del self._edges[source]
            return True
        return False

    def get_edge(self, source: str, target: str) -> Optional[TrustEdge]:
        """Get a trust edge, or None if it doesn't exist."""
        if source in self._edges:
            return self._edges[source].get(target)
        return None

    def get_outgoing(self, agent: str) -> Dict[str, TrustEdge]:
        """Get all trust edges from an agent (who they trust)."""
        return dict(self._edges.get(agent, {}))

    def get_incoming(self, agent: str) -> Dict[str, TrustEdge]:
        """Get all trust edges to an agent (who trusts them)."""
        incoming = {}
        for source, targets in self._edges.items():
            if agent in targets:
                incoming[source] = targets[agent]
        return incoming

    def agents(self) -> Set[str]:
        """Get all agents in the graph."""
        return set(self._agents)

    def edge_count(self) -> int:
        """Get total number of edges."""
        return sum(len(targets) for targets in self._edges.values())

    def has_agent(self, agent: str) -> bool:
        """Check if an agent exists in the graph."""
        return agent in self._agents

    # ─── Trust Transitivity (Subjective Logic) ─────────────

    @staticmethod
    def discount(trust_ab: float, trust_bc: float) -> float:
        """
        Subjective Logic discount operator for trust transitivity.

        If A trusts B with belief b_AB, and B trusts C with belief b_BC,
        then A's derived trust in C is:

            b_AC = b_AB * b_BC

        This captures the intuition that trust attenuates through
        intermediaries: you can't trust C more than B allows, and
        if A barely trusts B, then A can't strongly trust anyone
        that B vouches for.

        Args:
            trust_ab: A's trust in B [0.0, 1.0]
            trust_bc: B's trust in C [0.0, 1.0]

        Returns:
            A's derived trust in C [0.0, 1.0]
        """
        return max(0.0, min(1.0, trust_ab * trust_bc))

    @staticmethod
    def fuse(trusts: List[float]) -> float:
        """
        Subjective Logic cumulative fusion operator.

        Combines multiple independent trust reports about the same
        agent. If multiple agents all trust target T, the fused
        trust is the weighted average with an evidence bonus:

            fused = 1 - Π(1 - t_i) for each trust t_i

        This is more robust than simple averaging because it
        rewards unanimous positive opinions.

        Args:
            trusts: List of trust values [0.0, 1.0]

        Returns:
            Fused trust value [0.0, 1.0]
        """
        if not trusts:
            return BASE_TRUST

        # Cumulative fusion: probability at least one report is positive
        fused = 1.0 - math.prod(1.0 - t for t in trusts)
        return max(0.0, min(1.0, fused))

    def derived_trust(self, source: str, target: str) -> float:
        """
        Compute derived trust from source to target via all known paths.

        Uses BFS to find paths up to MAX_PATH_DEPTH, applies discount
        operator along each path, then fuses results.

        Returns:
            Derived trust [0.0, 1.0] or BASE_TRUST if no path found
        """
        paths = self.find_trust_paths(source, target, max_depth=MAX_PATH_DEPTH)
        if not paths:
            return BASE_TRUST

        path_trusts = []
        for path in paths:
            # Apply discount operator along the path
            current_trust = 1.0
            for i in range(len(path) - 1):
                edge = self.get_edge(path[i], path[i + 1])
                if edge is None:
                    current_trust = 0.0
                    break
                current_trust = self.discount(current_trust, edge.trust_value)
            if current_trust > 0:
                path_trusts.append(current_trust)

        if not path_trusts:
            return BASE_TRUST

        return self.fuse(path_trusts)

    # ─── Path Finding ──────────────────────────────────────

    def find_trust_paths(
        self,
        source: str,
        target: str,
        max_depth: int = MAX_PATH_DEPTH
    ) -> List[List[str]]:
        """
        Find trust paths between two agents using BFS.

        A trust path is a sequence of agents [A, B, C, ...] where each
        consecutive pair has a trust edge.

        Args:
            source: Starting agent
            target: Target agent
            max_depth: Maximum path length (number of edges)

        Returns:
            List of paths, where each path is a list of agent names
        """
        if source == target:
            return [[source]]

        if source not in self._agents or target not in self._agents:
            return []

        # BFS with path tracking
        queue: deque = deque()
        queue.append([source])
        paths: List[List[str]] = []

        while queue:
            path = queue.popleft()
            current = path[-1]

            if len(path) - 1 >= max_depth:
                continue

            for next_agent in self.get_outgoing(current):
                if next_agent in path:
                    continue  # No cycles in simple paths

                new_path = path + [next_agent]

                if next_agent == target:
                    paths.append(new_path)
                else:
                    queue.append(new_path)

        return paths

    def shortest_trust_path(
        self,
        source: str,
        target: str,
        max_depth: int = MAX_PATH_DEPTH
    ) -> Optional[List[str]]:
        """Find the shortest trust path between two agents."""
        paths = self.find_trust_paths(source, target, max_depth)
        if not paths:
            return None
        return min(paths, key=len)

    # ─── Cycle Detection ───────────────────────────────────

    def detect_cycles(self) -> List[List[str]]:
        """
        Detect all trust cycles in the graph.

        A trust cycle is a sequence of agents [A, B, C, A] where
        each consecutive pair (and the last-to-first) has a trust edge.

        Returns:
            List of cycles, where each cycle is a list of agent names
        """
        cycles: List[List[str]] = []
        visited_global: Set[str] = set()

        for start in self._agents:
            if start in visited_global:
                continue

            # DFS-based cycle detection
            stack: List[Tuple[str, List[str], Set[str]]] = [
                (start, [start], {start})
            ]

            while stack:
                node, path, path_set = stack.pop()

                for neighbor in self.get_outgoing(node):
                    if neighbor == start and len(path) >= 2:
                        # Found a cycle back to start
                        cycles.append(list(path))
                    elif neighbor not in path_set and neighbor not in visited_global:
                        new_path = path + [neighbor]
                        new_set = path_set | {neighbor}
                        if len(new_path) <= max(len(self._agents), 10):
                            stack.append((neighbor, new_path, new_set))

            visited_global.add(start)

        # Deduplicate cycles (same cycle, different starting point)
        unique: List[List[str]] = []
        seen: Set[str] = set()
        for cycle in cycles:
            # Normalize: sort the cycle and use smallest as start
            normalized = tuple(sorted(cycle))
            if normalized not in seen:
                seen.add(normalized)
                unique.append(cycle)

        return unique

    def detect_echo_chambers(
        self, inward_ratio: float = ECHO_CHAMBER_INWARD_RATIO
    ) -> List[Dict[str, Any]]:
        """
        Detect echo chambers — groups of agents that primarily trust
        each other and have few outgoing trust edges to outsiders.

        An echo chamber is detected when:
        1. A group of agents has high mutual trust
        2. The ratio of inward edges to total edges exceeds the threshold
        3. The group is somewhat isolated from the rest of the fleet

        Returns:
            List of echo chamber reports
        """
        chambers: List[Dict[str, Any]] = []

        # Find strongly connected components (simple approach)
        for agent in self._agents:
            outgoing = set(self.get_outgoing(agent).keys())
            incoming = set(self.get_incoming(agent).keys())
            mutual = outgoing & incoming

            if len(mutual) < 2:
                continue  # Need at least 2 mutual trust relationships

            # Check if edges are mostly inward (self-referential)
            total_edges = len(outgoing) + len(incoming)
            if total_edges == 0:
                continue

            inward = len(mutual)
            ratio = inward / total_edges

            if ratio >= inward_ratio:
                # Check average trust within the group
                group_trusts = []
                for other in mutual:
                    edge = self.get_edge(agent, other)
                    if edge:
                        group_trusts.append(edge.trust_value)

                avg_trust = (
                    sum(group_trusts) / len(group_trusts)
                    if group_trusts else 0.0
                )

                chambers.append({
                    "agent": agent,
                    "mutual_connections": sorted(mutual),
                    "mutual_count": len(mutual),
                    "inward_ratio": round(ratio, 4),
                    "avg_mutual_trust": round(avg_trust, 4),
                    "group": sorted(mutual | {agent}),
                })

        return chambers

    # ─── Fleet Metrics ─────────────────────────────────────

    def density(self) -> float:
        """
        Compute graph density: ratio of actual edges to maximum possible edges.

        density = |E| / (|V| * (|V| - 1))

        A fully connected graph has density 1.0.
        An empty graph has density 0.0.
        """
        n = len(self._agents)
        if n < 2:
            return 0.0
        max_edges = n * (n - 1)
        actual_edges = self.edge_count()
        return actual_edges / max_edges

    def average_path_length(self) -> float:
        """
        Compute the average shortest trust path length across all
        reachable agent pairs.

        Returns 0.0 if no paths exist.
        """
        agents = list(self._agents)
        if len(agents) < 2:
            return 0.0

        total_length = 0
        pair_count = 0

        for source in agents:
            for target in agents:
                if source == target:
                    continue
                path = self.shortest_trust_path(source, target)
                if path:
                    total_length += len(path) - 1  # edges, not nodes
                    pair_count += 1

        return total_length / pair_count if pair_count > 0 else 0.0

    def clustering_coefficient(self, agent: str) -> float:
        """
        Compute the local clustering coefficient for an agent.

        Measures how connected an agent's trust neighborhood is.
        If A trusts B and C, and B also trusts C, that's a triangle.

        C(A) = (triangles connected to A) / (possible triangles at A)

        For directed graphs, we check if any two of A's outgoing
        targets also have trust edges between them.
        """
        outgoing = self.get_outgoing(agent)
        targets = list(outgoing.keys())

        if len(targets) < 2:
            return 0.0

        possible_triangles = len(targets) * (len(targets) - 1) / 2
        actual_triangles = 0

        for i in range(len(targets)):
            for j in range(i + 1, len(targets)):
                # Check if targets[i] trusts targets[j] or vice versa
                if self.get_edge(targets[i], targets[j]) or self.get_edge(targets[j], targets[i]):
                    actual_triangles += 1

        return actual_triangles / possible_triangles if possible_triangles > 0 else 0.0

    def average_clustering(self) -> float:
        """Compute the average clustering coefficient across all agents."""
        agents = list(self._agents)
        if not agents:
            return 0.0
        coefficients = [self.clustering_coefficient(a) for a in agents]
        return sum(coefficients) / len(coefficients)

    def trust_hub_score(self, agent: str) -> float:
        """
        Compute a hub score for an agent based on how many agents
        trust them and the strength of those trust relationships.

        hub = Σ(incoming_trust_values) * incoming_count_factor

        Agents trusted by many others with high trust values are hubs.
        """
        incoming = self.get_incoming(agent)
        if not incoming:
            return 0.0

        total_trust = sum(edge.trust_value for edge in incoming.values())
        count_factor = math.log1p(len(incoming)) / math.log1p(10)

        return total_trust * count_factor

    def trust_authority_score(self, agent: str) -> float:
        """
        Compute an authority score based on who an agent trusts.

        authority = Σ(trust_values * target_hub_scores)

        Agents who trust high-hub agents are authorities.
        """
        outgoing = self.get_outgoing(agent)
        if not outgoing:
            return 0.0

        total = 0.0
        for target, edge in outgoing.items():
            hub = self.trust_hub_score(target)
            total += edge.trust_value * hub

        return total

    def fleet_metrics(self) -> dict:
        """
        Compute comprehensive fleet trust graph metrics.

        Returns:
            dict with density, avg_path_length, avg_clustering,
            agent_count, edge_count, cycle_count, echo_chamber_count
        """
        cycles = self.detect_cycles()
        chambers = self.detect_echo_chambers()

        return {
            "agent_count": len(self._agents),
            "edge_count": self.edge_count(),
            "density": round(self.density(), 4),
            "average_path_length": round(self.average_path_length(), 4),
            "average_clustering": round(self.average_clustering(), 4),
            "cycle_count": len(cycles),
            "echo_chamber_count": len(chambers),
            "cycles": [c for c in cycles[:5]],  # Limit to 5 for readability
            "echo_chambers": chambers[:5],
        }

    def agent_trust_summary(self, agent: str) -> dict:
        """Get a trust summary for a specific agent in the graph."""
        outgoing = self.get_outgoing(agent)
        incoming = self.get_incoming(agent)

        outgoing_trusts = {t: e.trust_value for t, e in outgoing.items()}
        incoming_trusts = {s: e.trust_value for s, e in incoming.items()}

        return {
            "agent": agent,
            "trusts": outgoing_trusts,
            "trusted_by": incoming_trusts,
            "outgoing_count": len(outgoing),
            "incoming_count": len(incoming),
            "avg_trust_given": round(
                sum(outgoing_trusts.values()) / len(outgoing_trusts), 4
            ) if outgoing_trusts else 0.0,
            "avg_trust_received": round(
                sum(incoming_trusts.values()) / len(incoming_trusts), 4
            ) if incoming_trusts else 0.0,
            "hub_score": round(self.trust_hub_score(agent), 4),
            "authority_score": round(self.trust_authority_score(agent), 4),
            "clustering_coefficient": round(self.clustering_coefficient(agent), 4),
        }

    # ─── Serialization ─────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the graph to a dictionary."""
        edges = []
        for source, targets in self._edges.items():
            for target, edge in targets.items():
                edges.append(edge.to_dict())
        return {
            "agents": sorted(self._agents),
            "edges": edges,
            "metrics": self.fleet_metrics(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TrustPropagationGraph':
        """Deserialize a graph from a dictionary."""
        graph = cls()
        for edge_data in data.get("edges", []):
            edge = TrustEdge.from_dict(edge_data)
            graph.add_edge(
                source=edge.source,
                target=edge.target,
                trust_value=edge.trust_value,
                weight=edge.weight,
                repo=edge.repo,
            )
        return graph


# ═══════════════════════════════════════════════════════════════
# 4. CrossRepoTrustSync — Trust Data Exchange Handler
# ═══════════════════════════════════════════════════════════════

@dataclass
class SyncResult:
    """Result of a sync operation."""
    total_sent: int = 0
    total_received: int = 0
    accepted: int = 0
    rejected: int = 0
    rejection_reasons: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "total_sent": self.total_sent,
            "total_received": self.total_received,
            "accepted": self.accepted,
            "rejected": self.rejected,
            "rejection_reasons": dict(self.rejection_reasons),
        }


class CrossRepoTrustSync:
    """
    Handles trust data exchange between SuperInstance repositories.

    This is the orchestration layer that:
    - Exports local trust profiles as signed attestations
    - Imports and validates foreign attestations
    - Manages the trust anchor system (repos whose attestations are auto-accepted)
    - Tracks replay attacks and maintains security
    - Syncs trust propagation graph data across repos

    The sync protocol works like this:
    1. Local repo creates attestations for its agents
    2. Attestations are transmitted (out of band — file, API, message queue)
    3. Receiving repo validates signatures, checks for replays, and imports
    4. Bridge blends foreign trust with local trust
    """

    def __init__(
        self,
        local_repo: str = "local",
        fleet_key: str = FLEET_TRUST_KEY,
        bridge: Optional[FleetTrustBridge] = None,
        graph: Optional[TrustPropagationGraph] = None,
    ):
        """
        Initialize CrossRepoTrustSync.

        Args:
            local_repo: Name/identifier of this local repository
            fleet_key: HMAC key for signing/verification
            bridge: Optional pre-configured FleetTrustBridge
            graph: Optional pre-configured TrustPropagationGraph
        """
        self.local_repo = local_repo
        self.fleet_key = fleet_key

        self.bridge = bridge or FleetTrustBridge(
            local_repo=local_repo,
            fleet_key=fleet_key,
        )
        self.graph = graph or TrustPropagationGraph()

        # Trust anchors: repos whose attestations are auto-accepted
        # (bypass some validation checks like staleness)
        self.trust_anchors: Set[str] = set()

        # Sync history: track what we've synced with each repo
        self._sync_history: Dict[str, List[dict]] = {}

        # Replay attack log
        self._replay_log: List[dict] = []

    # ─── Trust Anchor Management ───────────────────────────

    def add_trust_anchor(self, repo_name: str):
        """
        Designate a repo as a trust anchor.

        Trust anchors are repos whose attestations are auto-accepted
        with relaxed validation. Use this for repos that are known-good
        and have established reputation.
        """
        self.trust_anchors.add(repo_name)

    def remove_trust_anchor(self, repo_name: str):
        """Remove a repo from the trust anchor list."""
        self.trust_anchors.discard(repo_name)

    def is_trust_anchor(self, repo_name: str) -> bool:
        """Check if a repo is a trust anchor."""
        return repo_name in self.trust_anchors

    def get_trust_anchors(self) -> List[str]:
        """Get the list of trust anchor repos."""
        return sorted(self.trust_anchors)

    # ─── Export ────────────────────────────────────────────

    def export_trust(
        self,
        agent_name: str,
        trust_getter: Callable[[str], float],
        composite_getter: Callable[[str], float],
        event_count_getter: Callable[[], int] = None,
        meaningful_getter: Callable[[], bool] = None,
        cross_repo_events: List[str] = None,
        expires_in_seconds: float = ATTESTATION_MAX_AGE,
    ) -> TrustAttestation:
        """
        Export a signed trust attestation for an agent.

        This creates a portable trust proof that can be sent to other repos.

        Args:
            agent_name: Agent to export trust for
            trust_getter: fn(dimension) -> float
            composite_getter: fn() -> float
            event_count_getter: fn() -> int (optional)
            meaningful_getter: fn() -> bool (optional)
            cross_repo_events: List of cross-repo event names
            expires_in_seconds: How long until attestation expires

        Returns:
            Signed TrustAttestation
        """
        att = self.bridge.export_attestation(
            agent_name=agent_name,
            trust_getter=trust_getter,
            composite_getter=composite_getter,
            event_count_getter=event_count_getter,
            meaningful_getter=meaningful_getter,
            cross_repo_events=cross_repo_events or [],
        )

        if expires_in_seconds > 0:
            att.expires_at = att.issued_at + expires_in_seconds

        # Re-sign after setting expiration
        att.sign(self.fleet_key)

        # Record in sync history
        self._record_sync("export", agent_name, att.issuer_repo, att)

        return att

    def export_batch(
        self,
        agents: List[Tuple[str, Callable[[str], float], Callable[[str], float]]],
        expires_in_seconds: float = ATTESTATION_MAX_AGE,
    ) -> List[TrustAttestation]:
        """
        Export trust attestations for multiple agents.

        Args:
            agents: List of (agent_name, trust_getter, composite_getter) tuples
            expires_in_seconds: Expiration window

        Returns:
            List of signed attestations
        """
        attestations = []
        for agent_name, trust_getter, composite_getter in agents:
            att = self.export_trust(
                agent_name=agent_name,
                trust_getter=trust_getter,
                composite_getter=composite_getter,
                expires_in_seconds=expires_in_seconds,
            )
            attestations.append(att)
        return attestations

    # ─── Import ────────────────────────────────────────────

    def import_trust(self, attestation: TrustAttestation) -> dict:
        """
        Import a foreign trust attestation.

        For trust anchors: relaxed validation (skip staleness check).
        For regular repos: full validation including staleness.

        Args:
            attestation: The attestation to import

        Returns:
            dict with 'accepted', 'reason', and metadata
        """
        is_anchor = self.is_trust_anchor(attestation.issuer_repo)

        # Verify signature first (always required)
        if not attestation.verify(self.fleet_key):
            self._replay_log.append({
                "type": "invalid_signature",
                "agent": attestation.agent_name,
                "issuer": attestation.issuer_repo,
                "fingerprint": attestation.fingerprint,
                "timestamp": time.time(),
            })
            return {
                "accepted": False,
                "reason": "invalid_signature",
                "agent_name": attestation.agent_name,
            }

        # For trust anchors, do a relaxed import
        if is_anchor:
            result = self._import_anchor_attestation(attestation)
        else:
            result = self.bridge.import_attestation(attestation)

        # Record in sync history
        self._record_sync(
            "import" if result["accepted"] else "import_rejected",
            attestation.agent_name,
            attestation.issuer_repo,
            attestation,
        )

        # Track rejection reasons
        if not result["accepted"]:
            reason = result.get("reason", "unknown")
            # Will be tracked in replay_log if needed
            if reason == "replay_detected":
                self._replay_log.append({
                    "type": "replay",
                    "agent": attestation.agent_name,
                    "issuer": attestation.issuer_repo,
                    "fingerprint": attestation.fingerprint,
                    "timestamp": time.time(),
                })

        # Update propagation graph with the trust relationship
        if result["accepted"]:
            # Add edge from issuer_repo (as an entity) to agent
            self.graph.add_edge(
                source=attestation.issuer_repo,
                target=attestation.agent_name,
                trust_value=attestation.composite,
                weight=attestation.decayed_weight(),
                repo=attestation.issuer_repo,
            )

        return result

    def import_batch(self, attestations: List[TrustAttestation]) -> SyncResult:
        """
        Import a batch of foreign trust attestations.

        Args:
            attestations: List of attestations to import

        Returns:
            SyncResult with counts and rejection reasons
        """
        result = SyncResult(total_received=len(attestations))

        for att in attestations:
            imp_result = self.import_trust(att)
            if imp_result["accepted"]:
                result.accepted += 1
            else:
                result.rejected += 1
                reason = imp_result.get("reason", "unknown")
                result.rejection_reasons[reason] = (
                    result.rejection_reasons.get(reason, 0) + 1
                )

        return result

    def _import_anchor_attestation(self, attestation: TrustAttestation) -> dict:
        """
        Import an attestation from a trust anchor with relaxed validation.

        Trust anchor attestations skip:
        - Staleness check (they're always fresh)
        - Max age check

        They still require:
        - Valid signature
        - No replay
        """
        now = time.time()

        # Signature already verified by caller

        # Replay detection (still required)
        fp = attestation.fingerprint or attestation.compute_fingerprint()
        if fp in self.bridge._seen_fingerprints:
            return {
                "accepted": False,
                "reason": "replay_detected",
                "agent_name": attestation.agent_name,
                "fingerprint": fp,
            }

        # Register
        self.bridge._seen_fingerprints[fp] = now
        agent = attestation.agent_name

        if agent not in self.bridge._foreign_attestations:
            self.bridge._foreign_attestations[agent] = []

        # Keep only the most recent attestation from each issuer
        existing = self.bridge._foreign_attestations[agent]
        existing = [
            a for a in existing
            if a.issuer_repo != attestation.issuer_repo
        ]
        existing.append(attestation)
        self.bridge._foreign_attestations[agent] = existing

        self.bridge._import_count += 1

        return {
            "accepted": True,
            "reason": "trust_anchor_accepted",
            "agent_name": agent,
            "issuer_repo": attestation.issuer_repo,
            "composite": attestation.composite,
        }

    # ─── Sync History ──────────────────────────────────────

    def _record_sync(
        self,
        action: str,
        agent_name: str,
        counterparty: str,
        attestation: TrustAttestation,
    ):
        """Record a sync event in history."""
        if counterparty not in self._sync_history:
            self._sync_history[counterparty] = []

        self._sync_history[counterparty].append({
            "action": action,
            "agent_name": agent_name,
            "fingerprint": attestation.fingerprint,
            "timestamp": time.time(),
        })

        # Keep last 100 entries per counterparty
        if len(self._sync_history[counterparty]) > 100:
            self._sync_history[counterparty] = self._sync_history[counterparty][-100:]

    def get_sync_history(self, repo_name: str = None) -> List[dict]:
        """Get sync history, optionally filtered by repo."""
        if repo_name:
            return list(self._sync_history.get(repo_name, []))
        all_entries = []
        for repo, entries in self._sync_history.items():
            for entry in entries:
                entry_with_repo = dict(entry)
                entry_with_repo["counterparty"] = repo
                all_entries.append(entry_with_repo)
        return sorted(all_entries, key=lambda x: x["timestamp"], reverse=True)

    def get_replay_log(self) -> List[dict]:
        """Get the replay attack detection log."""
        return list(self._replay_log)

    # ─── Graph Sync ────────────────────────────────────────

    def sync_graph_edges(self, edges: List[Dict[str, Any]]) -> int:
        """
        Import trust edges from another repo into the propagation graph.

        Args:
            edges: List of edge dicts with source, target, trust_value

        Returns:
            Number of edges added
        """
        added = 0
        for edge_data in edges:
            self.graph.add_edge(
                source=edge_data["source"],
                target=edge_data["target"],
                trust_value=edge_data.get("trust_value", BASE_TRUST),
                weight=edge_data.get("weight", 1.0),
                repo=edge_data.get("repo", "unknown"),
            )
            added += 1
        return added

    def export_graph_edges(self, repo_filter: str = None) -> List[Dict[str, Any]]:
        """
        Export trust edges from the propagation graph.

        Args:
            repo_filter: If set, only export edges from this repo

        Returns:
            List of edge dicts
        """
        data = self.graph.to_dict()
        edges = data.get("edges", [])

        if repo_filter:
            edges = [e for e in edges if e.get("repo") == repo_filter]

        return edges

    # ─── Full Sync Protocol ────────────────────────────────

    def perform_sync(
        self,
        remote_attestations: List[TrustAttestation],
        remote_edges: List[Dict[str, Any]] = None,
    ) -> SyncResult:
        """
        Perform a full sync with a remote repo.

        This is the main entry point for the sync protocol:
        1. Import all foreign attestations
        2. Import trust graph edges
        3. Run inconsistency detection
        4. Return comprehensive result

        Args:
            remote_attestations: Attestations from the remote repo
            remote_edges: Optional trust edges from the remote repo

        Returns:
            SyncResult with all sync statistics
        """
        # Import attestations
        result = self.import_batch(remote_attestations)
        result.total_sent = 0  # We don't send anything in this method

        # Import graph edges if provided
        if remote_edges:
            edge_count = self.sync_graph_edges(remote_edges)
            result.total_received += edge_count

        # Run inconsistency detection
        inconsistencies = self.bridge.detect_inconsistencies()
        result.inconsistencies = len(inconsistencies)
        result.flagged_inconsistencies = sum(
            1 for i in inconsistencies if i.flagged
        )

        return result

    # ─── Statistics ────────────────────────────────────────

    def stats(self) -> dict:
        """Comprehensive sync statistics."""
        bridge_stats = self.bridge.stats()
        graph_metrics = self.graph.fleet_metrics()

        return {
            "local_repo": self.local_repo,
            "trust_anchors": sorted(self.trust_anchors),
            "bridge": bridge_stats,
            "graph_metrics": graph_metrics,
            "sync_partners": list(self._sync_history.keys()),
            "total_sync_events": sum(
                len(entries) for entries in self._sync_history.values()
            ),
            "replay_attacks_detected": len(self._replay_log),
        }

    # ─── Serialization ─────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the sync state to a dictionary."""
        return {
            "local_repo": self.local_repo,
            "trust_anchors": sorted(self.trust_anchors),
            "bridge": self.bridge.to_dict(),
            "graph": self.graph.to_dict(),
            "replay_log": self._replay_log[-50:],
        }

    @classmethod
    def from_dict(
        cls,
        data: dict,
        trust_getter: Callable = None,
    ) -> 'CrossRepoTrustSync':
        """Deserialize a sync state from a dictionary."""
        sync = cls(
            local_repo=data.get("local_repo", "local"),
            bridge=FleetTrustBridge.from_dict(
                data.get("bridge", {}), trust_getter=trust_getter
            ),
            graph=TrustPropagationGraph.from_dict(data.get("graph", {})),
        )
        sync.trust_anchors = set(data.get("trust_anchors", []))
        sync._replay_log = data.get("replay_log", [])
        return sync
