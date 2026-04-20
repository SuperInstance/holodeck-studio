#!/usr/bin/env python3
"""
Morphogenetic Permission Field — Continuous Permission Gradients
===============================================================

Implements Theory 5 from Pelagic's Tabula Rasa Deep Theory:
Capabilities are not binary switches but continuous gradients generated
by the interaction of multiple "morphogens" (trust, experience, budget,
recency, social context).

Also implements Theory 1 (Permission Crystal Detection): discovering
emergent coherent capability bundles from the intersection of level
filters and room compositions.

Design principles:
1. Permissions fade in smoothly based on morphogenetic signals
2. Binary permission levels are a quantization of the continuous field
3. Emergent capability combinations (spandrels) are detectable
4. The field is self-referential: can model and modify its own parameters
5. Downward causation: higher-level structures influence lower-level behavior

Based on research:
- Morphogenetic gradients (Turing 1952, reaction-diffusion)
- Gärdenfors' conceptual spaces (2000) — capabilities as convex regions
- Kauffman's autocatalytic sets (1986) — emergent self-sustaining structures
- Gould & Lewontin's spandrels (1979) — structural byproducts of composition
- The Permission Gradient in AI governance (2025)
"""

from __future__ import annotations

import math
import json
import time
from typing import Dict, List, Optional, Tuple, Set, Iterator
from dataclasses import dataclass, field
from enum import IntEnum


# ═══════════════════════════════════════════════════════════════
# Morphogen Types — The continuous signals that generate permissions
# ═══════════════════════════════════════════════════════════════

class MorphogenType(IntEnum):
    """The five morphogens that generate the permission field."""
    TRUST = 0       # Trust score (0.0-1.0) — ethical reliability
    EXPERIENCE = 1  # Normalized XP (0.0-1.0) — accumulated skill
    BUDGET = 2      # Resource availability (0.0-1.0) — current capacity
    RECENCY = 3     # Temporal freshness (0.0-1.0) — recent activity
    SOCIAL = 4      # Fleet context (0.0-1.0) — peer trust average


MORPHOGEN_NAMES = {
    MorphogenType.TRUST: "trust",
    MorphogenType.EXPERIENCE: "experience",
    MorphogenType.BUDGET: "budget",
    MorphogenType.RECENCY: "recency",
    MorphogenType.SOCIAL: "social",
}


# ═══════════════════════════════════════════════════════════════
# Morphogen Profile — Continuous signal values for an agent
# ═══════════════════════════════════════════════════════════════

@dataclass
class MorphogenProfile:
    """The instantaneous state of all five morphogens for an agent.
    
    Each morphogen is a real-valued signal in [0, 1]. The combined
    weighted sum determines the activation strength for each capability.
    """
    trust: float = 0.3
    experience: float = 0.0
    budget: float = 1.0
    recency: float = 1.0
    social: float = 0.3
    
    # Timestamps for recency computation
    created_at: float = field(default_factory=time.time)
    last_action_at: float = field(default_factory=time.time)
    
    @property
    def vector(self) -> List[float]:
        """Return morphogen values as a 5-dimensional vector."""
        return [self.trust, self.experience, self.budget, self.recency, self.social]
    
    @staticmethod
    def distance(a: 'MorphogenProfile', b: 'MorphogenProfile') -> float:
        """Euclidean distance between two morphogen profiles.
        
        This measures how different two agents' operational states are
        in the continuous permission field. Agents with similar profiles
        will have similar capability access patterns.
        """
        va, vb = a.vector, b.vector
        return math.sqrt(sum((va[i] - vb[i]) ** 2 for i in range(5)))
    
    @staticmethod
    def similarity(a: 'MorphogenProfile', b: 'MorphogenProfile') -> float:
        """Cosine similarity between two profiles (1.0 = identical direction)."""
        va, vb = a.vector, b.vector
        dot = sum(va[i] * vb[i] for i in range(5))
        mag_a = math.sqrt(sum(x * x for x in va))
        mag_b = math.sqrt(sum(x * x for x in vb))
        if mag_a == 0 or mag_b == 0:
            return 0.0
        return dot / (mag_a * mag_b)
    
    def update_recency(self, half_life_hours: float = 72.0) -> float:
        """Decay recency morphogen based on time since last action.
        
        Uses exponential decay with configurable half-life. Default 72 hours
        means recency halves every 3 days of inactivity.
        """
        now = time.time()
        hours_since = (now - self.last_action_at) / 3600.0
        if hours_since <= 0:
            self.recency = 1.0
        else:
            decay_constant = math.log(2) / half_life_hours
            self.recency = math.exp(-decay_constant * hours_since)
        return self.recency
    
    def record_action(self):
        """Record an action, resetting recency to 1.0."""
        self.last_action_at = time.time()
        self.recency = 1.0
    
    def composite_score(self, weights: Dict[MorphogenType, float] = None) -> float:
        """Weighted composite of all morphogens."""
        w = weights or DEFAULT_CAPABILITY_WEIGHTS
        values = self.vector
        morphogen_types = list(MorphogenType)
        total_w = sum(w.get(mt, 0) for mt in morphogen_types)
        if total_w <= 0:
            return 0.0
        return max(0.0, min(1.0,
            sum(values[mt.value] * w.get(mt, 0) for mt in morphogen_types) / total_w
        ))
    
    def to_dict(self) -> dict:
        return {
            "trust": self.trust, "experience": self.experience,
            "budget": self.budget, "recency": self.recency,
            "social": self.social,
            "created_at": self.created_at,
            "last_action_at": self.last_action_at,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'MorphogenProfile':
        return cls(
            trust=data.get("trust", 0.3),
            experience=data.get("experience", 0.0),
            budget=data.get("budget", 1.0),
            recency=data.get("recency", 1.0),
            social=data.get("social", 0.3),
            created_at=data.get("created_at", time.time()),
            last_action_at=data.get("last_action_at", time.time()),
        )


# ═══════════════════════════════════════════════════════════════
# Capability Morphogen Weights — How much each signal matters
# ═══════════════════════════════════════════════════════════════

# Default weights: trust and experience matter most
DEFAULT_CAPABILITY_WEIGHTS: Dict[MorphogenType, float] = {
    MorphogenType.TRUST: 0.30,
    MorphogenType.EXPERIENCE: 0.30,
    MorphogenType.BUDGET: 0.15,
    MorphogenType.RECENCY: 0.10,
    MorphogenType.SOCIAL: 0.15,
}

# Trust-sensitive capabilities (review, manage permissions, fleet broadcast)
TRUST_HEAVY_WEIGHTS: Dict[MorphogenType, float] = {
    MorphogenType.TRUST: 0.50,
    MorphogenType.EXPERIENCE: 0.15,
    MorphogenType.BUDGET: 0.10,
    MorphogenType.RECENCY: 0.05,
    MorphogenType.SOCIAL: 0.20,
}

# Skill-sensitive capabilities (build, create, summon)
EXPERIENCE_HEAVY_WEIGHTS: Dict[MorphogenType, float] = {
    MorphogenType.TRUST: 0.15,
    MorphogenType.EXPERIENCE: 0.50,
    MorphogenType.BUDGET: 0.15,
    MorphogenType.RECENCY: 0.10,
    MorphogenType.SOCIAL: 0.10,
}

# Resource-sensitive capabilities (mana-heavy operations)
BUDGET_HEAVY_WEIGHTS: Dict[MorphogenType, float] = {
    MorphogenType.TRUST: 0.10,
    MorphogenType.EXPERIENCE: 0.20,
    MorphogenType.BUDGET: 0.45,
    MorphogenType.RECENCY: 0.15,
    MorphogenType.SOCIAL: 0.10,
}

# Social capabilities (fleet broadcast, gossip, channels)
SOCIAL_HEAVY_WEIGHTS: Dict[MorphogenType, float] = {
    MorphogenType.TRUST: 0.15,
    MorphogenType.EXPERIENCE: 0.10,
    MorphogenType.BUDGET: 0.10,
    MorphogenType.RECENCY: 0.15,
    MorphogenType.SOCIAL: 0.50,
}


# ═══════════════════════════════════════════════════════════════
# Capability Definition — An entry in the permission field
# ═══════════════════════════════════════════════════════════════

@dataclass
class CapabilityDef:
    """A capability with its activation threshold and morphogen weights.
    
    The activation field value for this capability is:
        φ(agent, capability) = Σ weight[m] * profile[m]  for each morphogen m
    
    The capability is accessible when φ > threshold.
    """
    name: str
    description: str = ""
    threshold: float = 0.5
    weights: Dict[MorphogenType, float] = field(
        default_factory=lambda: dict(DEFAULT_CAPABILITY_WEIGHTS)
    )
    category: str = "general"  # general, trust, skill, resource, social
    level_hint: int = 0  # which traditional level this maps to
    
    # Morphogen sensitivity analysis
    def sensitivity(self, morphogen: MorphogenType) -> float:
        """How much a unit change in this morphogen affects activation."""
        return self.weights.get(morphogen, 0)
    
    def dominant_morphogen(self) -> MorphogenType:
        """Which morphogen has the strongest influence on this capability."""
        return max(self.weights.keys(), key=lambda m: self.weights.get(m, 0))
    
    def to_dict(self) -> dict:
        return {
            "name": self.name, "description": self.description,
            "threshold": self.threshold,
            "weights": {MORPHOGEN_NAMES.get(k, str(k)): v for k, v in self.weights.items()},
            "category": self.category, "level_hint": self.level_hint,
        }


# ═══════════════════════════════════════════════════════════════
# Permission Crystal — Emergent coherent capability bundle
# ═══════════════════════════════════════════════════════════════

@dataclass
class PermissionCrystal:
    """An emergent sublattice of the permission space.
    
    A crystal is a set of capabilities that naturally co-occur because
    their activation conditions are highly correlated. When an agent's
    morphogen profile activates one capability in the crystal, it tends
    to activate all of them.
    
    Crystals are NOT designed — they emerge from the interaction of
    capability thresholds and morphogen weight distributions.
    """
    crystal_id: str
    capabilities: Set[str]
    coherence_score: float  # 0-1, how tightly correlated the capabilities are
    dominant_morphogen: MorphogenType  # the morphogen that most defines this crystal
    level_range: Tuple[int, int]  # (min_level, max_level) that typically activates this
    discoverer: str = "system"  # which agent (or "system") discovered this crystal
    discovered_at: float = field(default_factory=time.time)
    
    def contains(self, capability_name: str) -> bool:
        return capability_name in self.capabilities
    
    def size(self) -> int:
        return len(self.capabilities)
    
    def overlap(self, other: 'PermissionCrystal') -> Set[str]:
        return self.capabilities & other.capabilities
    
    def overlap_ratio(self, other: 'PermissionCrystal') -> float:
        if not self.capabilities or not other.capabilities:
            return 0.0
        intersection = len(self.overlap(other))
        union = len(self.capabilities | other.capabilities)
        return intersection / union if union > 0 else 0.0
    
    def to_dict(self) -> dict:
        return {
            "crystal_id": self.crystal_id,
            "capabilities": sorted(self.capabilities),
            "coherence_score": self.coherence_score,
            "dominant_morphogen": MORPHOGEN_NAMES.get(self.dominant_morphogen, str(self.dominant_morphogen)),
            "level_range": list(self.level_range),
            "discoverer": self.discoverer,
            "discovered_at": self.discovered_at,
        }


# ═══════════════════════════════════════════════════════════════
# Permission Field — The continuous permission surface
# ═══════════════════════════════════════════════════════════════

class PermissionField:
    """The morphogenetic permission field.
    
    Maps (agent_profile, capability) → activation_strength in [0, 1].
    Replaces binary permission checks with continuous gradient evaluation.
    
    The field can:
    1. Evaluate any (agent, capability) pair's activation strength
    2. Detect emergent permission crystals (coherent capability bundles)
    3. Compute distances between agents in permission space
    4. Identify "flicker zones" where capabilities are borderline
    5. Simulate the effect of morphogen changes on capability access
    """
    
    def __init__(self):
        self.capabilities: Dict[str, CapabilityDef] = {}
        self.crystals: List[PermissionCrystal] = []
        self.profiles: Dict[str, MorphogenProfile] = {}
        self.threshold_history: Dict[str, List[Tuple[float, float]]] = {}  # cap → [(timestamp, field_value)]
        self._crystal_cache_valid = False
    
    def register_capability(self, cap: CapabilityDef):
        """Register a capability in the field."""
        self.capabilities[cap.name] = cap
        self.threshold_history[cap.name] = []
        self._crystal_cache_valid = False
    
    def register_capabilities(self, caps: List[CapabilityDef]):
        for c in caps:
            self.register_capability(c)
    
    def set_profile(self, agent_name: str, profile: MorphogenProfile):
        """Set an agent's morphogen profile."""
        self.profiles[agent_name] = profile
    
    def get_profile(self, agent_name: str) -> Optional[MorphogenProfile]:
        return self.profiles.get(agent_name)
    
    def update_recency(self, agent_name: str, half_life_hours: float = 72.0) -> Optional[float]:
        """Update an agent's recency morphogen and return new value."""
        profile = self.profiles.get(agent_name)
        if not profile:
            return None
        return profile.update_recency(half_life_hours)
    
    def record_action(self, agent_name: str):
        """Record an agent action, resetting recency."""
        profile = self.profiles.get(agent_name)
        if profile:
            profile.record_action()
    
    # ── Core Field Evaluation ──────────────────────────────────
    
    def evaluate(self, agent_name: str, capability_name: str) -> float:
        """Evaluate the permission field for a specific (agent, capability) pair.
        
        Returns a value in [0, 1] representing the activation strength.
        Values near 0 = strongly denied. Values near 1 = strongly permitted.
        Values near threshold = "flicker zone" — borderline access.
        """
        profile = self.profiles.get(agent_name)
        cap = self.capabilities.get(capability_name)
        
        if not profile or not cap:
            return 0.0
        
        values = profile.vector
        morphogen_types = list(MorphogenType)
        
        weighted_sum = 0.0
        total_weight = 0.0
        for mt in morphogen_types:
            w = cap.weights.get(mt, 0)
            weighted_sum += values[mt.value] * w
            total_weight += w
        
        if total_weight <= 0:
            return 0.0
        
        field_value = weighted_sum / total_weight
        
        # Record in history
        if capability_name in self.threshold_history:
            self.threshold_history[capability_name].append((time.time(), field_value))
            # Keep last 1000 entries
            if len(self.threshold_history[capability_name]) > 1000:
                self.threshold_history[capability_name] = self.threshold_history[capability_name][-500:]
        
        return max(0.0, min(1.0, field_value))
    
    def is_accessible(self, agent_name: str, capability_name: str) -> bool:
        """Binary check: is the capability above its threshold?"""
        return self.evaluate(agent_name, capability_name) >= self.capabilities[capability_name].threshold
    
    def accessibility_vector(self, agent_name: str) -> Dict[str, float]:
        """Get activation strengths for ALL capabilities for an agent.
        
        This vector IS the agent's position in permission space.
        """
        return {
            name: self.evaluate(agent_name, name)
            for name in self.capabilities
        }
    
    def accessible_set(self, agent_name: str, threshold_override: float = None) -> Set[str]:
        """Get the set of capabilities accessible to an agent."""
        accessible = set()
        for name, cap in self.capabilities.items():
            t = threshold_override if threshold_override is not None else cap.threshold
            if self.evaluate(agent_name, name) >= t:
                accessible.add(name)
        return accessible
    
    # ── Flicker Zone Detection ─────────────────────────────────
    
    def flicker_zone(self, agent_name: str, margin: float = 0.05) -> List[dict]:
        """Find capabilities in the flicker zone (near the threshold).
        
        The flicker zone is where capabilities are borderline — small
        changes in morphogen values could flip access on or off.
        These are the "Turing-unstable" regions of the permission field.
        """
        flickering = []
        for name, cap in self.capabilities.items():
            field_val = self.evaluate(agent_name, name)
            distance_to_threshold = abs(field_val - cap.threshold)
            if distance_to_threshold < margin:
                flickering.append({
                    "capability": name,
                    "field_value": round(field_val, 4),
                    "threshold": cap.threshold,
                    "gap": round(distance_to_threshold, 4),
                    "direction": "above" if field_val >= cap.threshold else "below",
                })
        return sorted(flickering, key=lambda x: x["gap"])
    
    # ── Morphogen Sensitivity Analysis ─────────────────────────
    
    def sensitivity_analysis(self, agent_name: str, capability_name: str) -> Dict[str, float]:
        """Compute how much each morphogen contributes to the field value.
        
        Returns the partial contribution of each morphogen to the
        capability's activation strength. This reveals which signals
        are most important for accessing this capability.
        """
        profile = self.profiles.get(agent_name)
        cap = self.capabilities.get(capability_name)
        
        if not profile or not cap:
            return {}
        
        values = profile.vector
        total_weight = sum(cap.weights.get(mt, 0) for mt in MorphogenType)
        if total_weight <= 0:
            return {}
        
        contributions = {}
        for mt in MorphogenType:
            w = cap.weights.get(mt, 0)
            contribution = (values[mt.value] * w) / total_weight
            contributions[MORPHOGEN_NAMES[mt]] = round(contribution, 4)
        
        return contributions
    
    def what_if(self, agent_name: str, capability_name: str,
                morphogen: MorphogenType, new_value: float) -> dict:
        """Simulate the effect of changing one morphogen's value.
        
        Returns the current and projected field values, showing how
        the change would affect access to the capability.
        """
        profile = self.profiles.get(agent_name)
        if not profile:
            return {"error": "Agent not found"}
        
        current_value = self.evaluate(agent_name, capability_name)
        old_morphogen_value = profile.vector[morphogen.value]
        
        # Temporarily modify profile
        setattr(profile, MORPHOGEN_NAMES[morphogen], new_value)
        projected_value = self.evaluate(agent_name, capability_name)
        
        # Restore
        setattr(profile, MORPHOGEN_NAMES[morphogen], old_morphogen_value)
        
        cap = self.capabilities.get(capability_name, CapabilityDef(name=capability_name))
        
        return {
            "capability": capability_name,
            "morphogen": MORPHOGEN_NAMES[morphogen],
            "old_value": round(old_morphogen_value, 4),
            "new_value": round(new_value, 4),
            "current_field": round(current_value, 4),
            "projected_field": round(projected_value, 4),
            "current_access": current_value >= cap.threshold,
            "projected_access": projected_value >= cap.threshold,
            "access_change": "gain" if (current_value < cap.threshold and projected_value >= cap.threshold) else
                           "lose" if (current_value >= cap.threshold and projected_value < cap.threshold) else
                           "none",
        }
    
    # ── Distance Metrics ───────────────────────────────────────
    
    def permission_distance(self, agent_a: str, agent_b: str) -> float:
        """Euclidean distance between two agents in permission space.
        
        Measures how different two agents' capability access patterns are.
        Small distance = similar capabilities. Large distance = different roles.
        """
        vec_a = self.accessibility_vector(agent_a)
        vec_b = self.accessibility_vector(agent_b)
        all_caps = set(vec_a.keys()) | set(vec_b.keys())
        if not all_caps:
            return 0.0
        return math.sqrt(
            sum((vec_a.get(c, 0) - vec_b.get(c, 0)) ** 2 for c in all_caps)
        )
    
    def nearest_agents(self, target_agent: str, n: int = 5,
                       required_capability: str = None) -> List[Tuple[str, float]]:
        """Find the agents nearest to a target in permission space.
        
        Optionally filter to agents who have a specific capability.
        """
        results = []
        for other in self.profiles:
            if other == target_agent:
                continue
            if required_capability and not self.is_accessible(other, required_capability):
                continue
            dist = self.permission_distance(target_agent, other)
            results.append((other, round(dist, 4)))
        results.sort(key=lambda x: x[1])
        return results[:n]
    
    # ── Permission Crystal Detection ───────────────────────────
    
    def detect_crystals(self, coherence_threshold: float = 0.7,
                        min_size: int = 3) -> List[PermissionCrystal]:
        """Detect emergent permission crystals.
        
        A crystal is a set of capabilities whose activation patterns
        are highly correlated across all agents. When one is accessible,
        the others tend to be too.
        
        Algorithm:
        1. Build a capability co-occurrence matrix
        2. Identify cliques in the co-occurrence graph
        3. Score each clique for coherence
        4. Return cliques above the coherence threshold
        """
        if self._crystal_cache_valid and self.crystals:
            return self.crystals
        
        cap_names = sorted(self.capabilities.keys())
        if len(cap_names) < 2 or len(self.profiles) < 2:
            self._crystal_cache_valid = True
            return []
        
        # Build co-occurrence matrix
        # For each pair of capabilities, count how often they're both accessible
        cooccurrence: Dict[Tuple[str, str], int] = {}
        single_counts: Dict[str, int] = {}
        total_agents = len(self.profiles)
        
        for agent_name in self.profiles:
            accessible = self.accessible_set(agent_name)
            for cap in cap_names:
                single_counts[cap] = single_counts.get(cap, 0) + (1 if cap in accessible else 0)
            for i, c1 in enumerate(cap_names):
                for c2 in cap_names[i+1:]:
                    both = (c1 in accessible and c2 in accessible)
                    key = (c1, c2)
                    cooccurrence[key] = cooccurrence.get(key, 0) + (1 if both else 0)
        
        # Compute correlation for each pair
        correlation: Dict[Tuple[str, str], float] = {}
        for (c1, c2), cooc_count in cooccurrence.items():
            count_1 = single_counts.get(c1, 0)
            count_2 = single_counts.get(c2, 0)
            if count_1 == 0 or count_2 == 0 or total_agents == 0:
                correlation[(c1, c2)] = 0.0
                continue
            # Jaccard-like correlation: P(both) / P(either)
            either = count_1 + count_2 - cooc_count
            correlation[(c1, c2)] = cooc_count / either if either > 0 else 0.0
        
        # Greedy clique finding: start with most correlated pair, expand
        crystals = []
        used_caps: Set[str] = set()
        
        # Sort pairs by correlation (descending)
        sorted_pairs = sorted(correlation.items(), key=lambda x: x[1], reverse=True)
        
        for (c1, c2), corr in sorted_pairs:
            if corr < coherence_threshold:
                break
            if c1 in used_caps or c2 in used_caps:
                continue
            
            # Try to expand this pair into a larger crystal
            crystal_caps = {c1, c2}
            
            for candidate in cap_names:
                if candidate in crystal_caps:
                    continue
                # Check if candidate correlates well with ALL crystal members
                min_member_corr = float('inf')
                for member in crystal_caps:
                    key = (min(candidate, member), max(candidate, member))
                    pair_corr = correlation.get(key, 0.0)
                    min_member_corr = min(min_member_corr, pair_corr)
                if min_member_corr >= coherence_threshold:
                    crystal_caps.add(candidate)
            
            if len(crystal_caps) >= min_size:
                # Compute average coherence
                total_corr = 0.0
                pair_count = 0
                members = sorted(crystal_caps)
                for i in range(len(members)):
                    for j in range(i+1, len(members)):
                        key = (members[i], members[j])
                        total_corr += correlation.get(key, 0.0)
                        pair_count += 1
                avg_coherence = total_corr / pair_count if pair_count > 0 else 0.0
                
                # Find dominant morphogen
                morphogen_counts: Dict[MorphogenType, int] = {mt: 0 for mt in MorphogenType}
                for cap_name in crystal_caps:
                    cap_def = self.capabilities.get(cap_name)
                    if cap_def:
                        dom = cap_def.dominant_morphogen()
                        morphogen_counts[dom] = morphogen_counts.get(dom, 0) + 1
                dominant = max(morphogen_counts.keys(), key=lambda m: morphogen_counts[m])
                
                # Find level range
                levels = []
                for cap_name in crystal_caps:
                    cap_def = self.capabilities.get(cap_name)
                    if cap_def:
                        levels.append(cap_def.level_hint)
                level_min = min(levels) if levels else 0
                level_max = max(levels) if levels else 0
                
                crystal = PermissionCrystal(
                    crystal_id=f"crystal-{len(crystals):03d}",
                    capabilities=crystal_caps,
                    coherence_score=round(avg_coherence, 4),
                    dominant_morphogen=dominant,
                    level_range=(level_min, level_max),
                )
                crystals.append(crystal)
                used_caps.update(crystal_caps)
        
        self.crystals = crystals
        self._crystal_cache_valid = True
        return crystals
    
    def invalidate_crystal_cache(self):
        self._crystal_cache_valid = False
    
    # ── Downward Causation ─────────────────────────────────────
    
    def downward_causation_effect(self, agent_name: str) -> dict:
        """Measure how higher-level capability structures influence this agent.
        
        An agent who can see higher-level capabilities (but not access them)
        may behave differently than one who cannot see them. This method
        computes the "anticipation effect" — how much future capability
        access motivates current behavior.
        """
        profile = self.profiles.get(agent_name)
        if not profile:
            return {"error": "Agent not found"}
        
        current_access = self.accessible_set(agent_name)
        
        # Capabilities the agent almost has (within flicker zone)
        near_capabilities = self.flicker_zone(agent_name, margin=0.15)
        
        # Capabilities at higher levels that the agent can see
        higher_level_caps = []
        current_level = max(
            (self.capabilities[c].level_hint for c in current_access),
            default=0
        )
        for name, cap in self.capabilities.items():
            if cap.level_hint > current_level:
                field_val = self.evaluate(agent_name, name)
                higher_level_caps.append({
                    "capability": name,
                    "target_level": cap.level_hint,
                    "current_field": round(field_val, 4),
                    "threshold": cap.threshold,
                    "gap_to_threshold": round(cap.threshold - field_val, 4),
                })
        
        higher_level_caps.sort(key=lambda x: x["gap_to_threshold"])
        
        return {
            "agent": agent_name,
            "current_level": current_level,
            "accessible_count": len(current_access),
            "near_capabilities": near_capabilities[:5],
            "visible_higher_caps": higher_level_caps[:5],
            "anticipation_score": round(
                max(0, 1.0 - (sum(x["gap_to_threshold"] for x in higher_level_caps[:3]) / max(len(higher_level_caps[:3]), 1))),
                4
            ) if higher_level_caps else 0.0,
        }
    
    # ── Fleet-Level Analysis ───────────────────────────────────
    
    def fleet_permission_map(self) -> dict:
        """Generate a fleet-wide permission map showing all agents in permission space."""
        return {
            agent: {
                "accessible": sorted(self.accessible_set(agent)),
                "flicker_zone": [f["capability"] for f in self.flicker_zone(agent)],
                "composite_score": round(profile.composite_score(), 4),
            }
            for agent, profile in self.profiles.items()
        }
    
    def spandrel_detection(self) -> List[dict]:
        """Detect emergent permission surfaces (spandrels).
        
        A spandrel is a capability combination that emerges from room
        composition but was not explicitly designed. In the permission
        field, spandrels appear as capabilities whose activation is
        correlated with NO single morphogen but emerges from the
        interaction of multiple morphogens.
        """
        if len(self.profiles) < 2:
            return []
        
        spandrels = []
        for cap_name, cap_def in self.capabilities.items():
            # Compute correlation of activation with each morphogen
            morphogen_correlations: Dict[MorphogenType, float] = {}
            for mt in MorphogenType:
                morphogen_values = [self.profiles[a].vector[mt.value] for a in self.profiles]
                activation_values = [self.evaluate(a, cap_name) for a in self.profiles]
                corr = self._pearson_correlation(morphogen_values, activation_values)
                morphogen_correlations[mt] = corr
            
            # A spandrel has low individual correlations but high combined correlation
            max_single_corr = max(abs(v) for v in morphogen_correlations.values())
            avg_corr = sum(abs(v) for v in morphogen_correlations.values()) / len(morphogen_correlations)
            
            # If average is much higher than max single, it's emergent from interaction
            if avg_corr > 0.3 and max_single_corr < avg_corr * 0.8:
                spandrels.append({
                    "capability": cap_name,
                    "max_single_morphogen_corr": round(max_single_corr, 4),
                    "avg_morphogen_corr": round(avg_corr, 4),
                    "emergence_ratio": round(avg_corr / max(max_single_corr, 0.01), 4),
                    "morphogen_breakdown": {
                        MORPHOGEN_NAMES[mt]: round(v, 4)
                        for mt, v in sorted(morphogen_correlations.items(),
                                             key=lambda x: abs(x[1]), reverse=True)
                    },
                })
        
        return sorted(spandrels, key=lambda x: x["emergence_ratio"], reverse=True)
    
    @staticmethod
    def _pearson_correlation(x: List[float], y: List[float]) -> float:
        """Compute Pearson correlation between two lists."""
        n = len(x)
        if n < 2 or n != len(y):
            return 0.0
        mean_x = sum(x) / n
        mean_y = sum(y) / n
        cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        std_x = math.sqrt(sum((x[i] - mean_x) ** 2 for i in range(n)))
        std_y = math.sqrt(sum((y[i] - mean_y) ** 2 for i in range(n)))
        if std_x == 0 or std_y == 0:
            return 0.0
        return cov / (std_x * std_y)
    
    # ── Bootstrapping Stage Detection ───────────────────────────
    
    def bootstrapping_stage(self) -> dict:
        """Determine which bootstrapping stage the fleet is in.
        
        Void → Seed → Root → Branch → Canopy
        
        Based on the state of the permission field:
        - Void: no profiles, no capabilities
        - Seed: >= 1 profile, but no trust events
        - Root: profiles with trust > base (0.3), but no trust between agents
        - Branch: profiles with cross-cutting trust, but not self-sustaining
        - Canopy: autocatalytic network (trust graph is sufficiently dense)
        """
        profile_count = len(self.profiles)
        cap_count = len(self.capabilities)
        
        if profile_count == 0:
            return {"stage": "void", "description": "No agents exist. Pure tabula rasa."}
        
        if cap_count == 0:
            return {"stage": "seed", "description": f"First agent(s) exist ({profile_count}) but no capabilities defined."}
        
        # Check trust distribution
        trust_values = [p.trust for p in self.profiles.values()]
        avg_trust = sum(trust_values) / len(trust_values) if trust_values else 0
        
        if avg_trust <= 0.31:
            return {"stage": "root", "description": "Trust space origin established. Average trust near base (0.3)."}
        
        # Check if profiles are diverse enough
        profile_distances = []
        agent_names = list(self.profiles.keys())
        for i in range(len(agent_names)):
            for j in range(i + 1, len(agent_names)):
                dist = MorphogenProfile.distance(
                    self.profiles[agent_names[i]],
                    self.profiles[agent_names[j]]
                )
                profile_distances.append(dist)
        
        if not profile_distances:
            return {"stage": "root", "description": "Only one agent. Trust origin established."}
        
        avg_distance = sum(profile_distances) / len(profile_distances)
        
        # Check crystal density
        crystals = self.detect_crystals(min_size=2, coherence_threshold=0.5)
        
        # Heuristic: canopy when agents are diverse AND crystals are forming
        if avg_distance > 0.3 and len(crystals) >= 1 and avg_trust > 0.4:
            return {
                "stage": "canopy",
                "description": "Fleet is self-sustaining. Autocatalytic permission network active.",
                "agent_diversity": round(avg_distance, 4),
                "crystal_count": len(crystals),
                "avg_trust": round(avg_trust, 4),
            }
        
        return {
            "stage": "branch",
            "description": f"Agents branching ({profile_count} agents, avg distance {avg_distance:.4f}). "
                          f"Crystals forming: {len(crystals)}. Moving toward canopy.",
            "agent_diversity": round(avg_distance, 4),
            "crystal_count": len(crystals),
            "avg_trust": round(avg_trust, 4),
        }
    
    # ── Serialization ──────────────────────────────────────────
    
    def to_dict(self) -> dict:
        return {
            "capabilities": {name: cap.to_dict() for name, cap in self.capabilities.items()},
            "profiles": {name: prof.to_dict() for name, prof in self.profiles.items()},
            "crystals": [c.to_dict() for c in self.crystals],
            "bootstrapping_stage": self.bootstrapping_stage(),
        }
    
    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, default=str)


# ═══════════════════════════════════════════════════════════════
# Built-in Capability Registry
# ═══════════════════════════════════════════════════════════════

def build_standard_capabilities() -> List[CapabilityDef]:
    """Build the standard set of capabilities matching Tabula Rasa levels.
    
    Maps the 6-level permission system into continuous morphogenetic space.
    """
    caps = []
    
    # Level 0 — Greenhorn capabilities
    for name in ["look", "go", "say", "tell", "help", "who", "inventory", "read"]:
        caps.append(CapabilityDef(
            name=name, threshold=0.1, level_hint=0,
            weights={k: 0.1 for k in MorphogenType},  # very low threshold, minimal morphogen needs
            category="basic",
        ))
    
    # Level 1 — Crew capabilities
    for name in ["yell", "gossip", "write_note", "use_room", "check_mail", "send_mail", "equip", "quests"]:
        caps.append(CapabilityDef(
            name=name, threshold=0.2, level_hint=1,
            weights=dict(DEFAULT_CAPABILITY_WEIGHTS),
            category="basic",
        ))
    
    # Level 2 — Specialist capabilities (experience-heavy)
    for name in ["build_room", "create_item", "use_equipment", "cast_spell", "summon_npc", "dismiss_npc", "join_channel"]:
        caps.append(CapabilityDef(
            name=name, threshold=0.35, level_hint=2,
            weights=dict(EXPERIENCE_HEAVY_WEIGHTS),
            category="skill",
        ))
    
    # Level 3 — Captain capabilities (balanced)
    for name in ["build_area", "create_adventure", "edit_own_rooms", "create_spell", "assign_quests", "review_agent", "manage_vessel", "back_channel"]:
        caps.append(CapabilityDef(
            name=name, threshold=0.5, level_hint=3,
            weights=dict(DEFAULT_CAPABILITY_WEIGHTS),
            category="management",
        ))
    
    # Level 4 — Cocapn capabilities (trust-heavy)
    for name in ["edit_any_room", "create_item_type", "create_room_type", "manage_npcs_global", "fleet_broadcast", "create_tool_room", "manage_permissions", "create_equipment", "define_spell"]:
        caps.append(CapabilityDef(
            name=name, threshold=0.65, level_hint=4,
            weights=dict(TRUST_HEAVY_WEIGHTS),
            category="governance",
        ))
    
    # Level 5 — Architect capabilities (all morphogens must be high)
    for name in ["refactor_engine", "add_level", "modify_physics", "system_config"]:
        caps.append(CapabilityDef(
            name=name, threshold=0.85, level_hint=5,
            weights={k: 0.25 for k in MorphogenType},  # all morphogens matter equally
            category="architect",
        ))
    
    return caps


# ═══════════════════════════════════════════════════════════════
# Demo — Show the permission field in action
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════════════╗")
    print("║  MORPHOGENETIC PERMISSION FIELD — Continuous Capabilities     ║")
    print("║  Theory 5: Capabilities as Gradients, Not Switches          ║")
    print("╚══════════════════════════════════════════════════════════════╝\n")
    
    # Build field with standard capabilities
    field = PermissionField()
    field.register_capabilities(build_standard_capabilities())
    
    # Create agents at different bootstrapping stages
    agents = {
        "greenhorn": MorphogenProfile(trust=0.3, experience=0.0, budget=1.0, recency=1.0, social=0.3),
        "specialist": MorphogenProfile(trust=0.5, experience=0.4, budget=0.8, recency=0.9, social=0.4),
        "captain": MorphogenProfile(trust=0.7, experience=0.7, budget=0.6, recency=0.8, social=0.6),
        "cocapn": MorphogenProfile(trust=0.85, experience=0.8, budget=0.7, recency=0.7, social=0.75),
    }
    
    for name, profile in agents.items():
        field.set_profile(name, profile)
    
    print(f"Agents: {len(agents)}")
    print(f"Capabilities: {len(field.capabilities)}")
    print(f"Bootstrapping stage: {field.bootstrapping_stage()['stage']}")
    print()
    
    # Show continuous permission evaluation
    print("─── Continuous Permission Evaluation ───\n")
    sample_caps = ["look", "build_room", "create_adventure", "manage_permissions", "refactor_engine"]
    
    for agent_name in ["greenhorn", "specialist", "captain", "cocapn"]:
        profile = field.profiles[agent_name]
        composite = profile.composite_score()
        accessible = len(field.accessible_set(agent_name))
        flicker = len(field.flicker_zone(agent_name))
        
        print(f"  {agent_name:12s}  composite={composite:.2f}  accessible={accessible:2d}  flickering={flicker}")
        for cap_name in sample_caps:
            val = field.evaluate(agent_name, cap_name)
            cap = field.capabilities[cap_name]
            symbol = "█" if val >= cap.threshold else "░"
            print(f"    {symbol} {cap_name:20s}  field={val:.3f}  threshold={cap.threshold:.2f}")
        print()
    
    # Show morphogen sensitivity
    print("─── Morphogen Sensitivity Analysis ───\n")
    for cap_name in ["build_room", "manage_permissions", "refactor_engine"]:
        print(f"  {cap_name}:")
        for agent in ["greenhorn", "cocapn"]:
            sens = field.sensitivity_analysis(agent, cap_name)
            sorted_sens = sorted(sens.items(), key=lambda x: x[1], reverse=True)
            top = sorted_sens[0]
            print(f"    {agent:12s}  dominant={top[0]:10s} (contribution={top[1]:.3f})")
        print()
    
    # What-if analysis
    print("─── What-If: Greenhorn trust boosts to 0.8 ───\n")
    result = field.what_if("greenhorn", "manage_permissions", MorphogenType.TRUST, 0.8)
    print(f"  Current access:  {result['current_access']}")
    print(f"  Projected access: {result['projected_access']}")
    print(f"  Change: {result['access_change']}")
    print()
    
    # Distance metrics
    print("─── Permission Space Distances ───\n")
    for a in ["greenhorn", "specialist"]:
        for b in ["captain", "cocapn"]:
            dist = field.permission_distance(a, b)
            morph_dist = MorphogenProfile.distance(field.profiles[a], field.profiles[b])
            print(f"  {a:12s} ↔ {b:12s}  perm_dist={dist:.3f}  morph_dist={morph_dist:.3f}")
    print()
    
    # Downward causation
    print("─── Downward Causation Effect ───\n")
    for agent in ["greenhorn", "specialist"]:
        dc = field.downward_causation_effect(agent)
        print(f"  {agent}:")
        print(f"    Current level: {dc['current_level']}")
        print(f"    Anticipation score: {dc['anticipation_score']}")
        for cap in dc.get('visible_higher_caps', [])[:3]:
            print(f"    Near: {cap['capability']} (gap={cap['gap_to_threshold']:.3f})")
        print()
    
    # Crystal detection
    print("─── Permission Crystal Detection ───\n")
    crystals = field.detect_crystals(min_size=2, coherence_threshold=0.4)
    print(f"  Crystals found: {len(crystals)}")
    for crystal in crystals:
        print(f"    {crystal.crystal_id}: {crystal.size()} caps, "
              f"coherence={crystal.coherence_score:.3f}, "
              f"dominant={MORPHOGEN_NAMES[crystal.dominant_morphogen]}, "
              f"levels={crystal.level_range}")
        print(f"      capabilities: {sorted(crystal.capabilities)}")
    print()
    
    # Bootstrapping stages
    print("─── Bootstrapping Stage Progression ───\n")
    test_fields = [
        ("void", {}, []),
        ("seed", {"agent1": MorphogenProfile()}, []),
        ("root", {"agent1": MorphogenProfile(trust=0.3)}, build_standard_capabilities()),
        ("branch", {"a1": MorphogenProfile(trust=0.4, experience=0.3), 
                    "a2": MorphogenProfile(trust=0.5, experience=0.5)},
         build_standard_capabilities()),
        ("canopy", {"a1": MorphogenProfile(trust=0.7, experience=0.8),
                    "a2": MorphogenProfile(trust=0.6, experience=0.6),
                    "a3": MorphogenProfile(trust=0.8, experience=0.7)},
         build_standard_capabilities()),
    ]
    
    for name, profiles, caps in test_fields:
        tf = PermissionField()
        tf.register_capabilities(caps)
        for pname, prof in profiles.items():
            tf.set_profile(pname, prof)
        stage = tf.bootstrapping_stage()
        print(f"  {name:8s} → Stage: {stage['stage']:8s} | {stage['description']}")
    print()
    
    print("═══════════════════════════════════════════")
    print("The permission field IS the architecture.")
    print("Capabilities are not switches — they're waves.")
    print("═══════════════════════════════════════════")
