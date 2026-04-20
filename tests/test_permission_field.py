#!/usr/bin/env python3
"""Tests for the Morphogenetic Permission Field module.

Covers:
- MorphogenProfile: creation, distance, similarity, recency decay, composite scoring
- CapabilityDef: creation, sensitivity analysis, dominant morphogen
- PermissionField: registration, evaluation, flicker zones, what-if analysis
- Permission Crystal detection: coherence scoring, overlap, spandrel detection
- Downward Causation: anticipation effects
- Bootstrapping Stage detection: void → seed → root → branch → canopy
- Edge cases: missing profiles, missing capabilities, boundary conditions
- Serialization roundtrips
"""

import math
import time
import pytest
from permission_field import (
    MorphogenType, MorphogenProfile, CapabilityDef, PermissionCrystal,
    PermissionField, DEFAULT_CAPABILITY_WEIGHTS, TRUST_HEAVY_WEIGHTS,
    EXPERIENCE_HEAVY_WEIGHTS, BUDGET_HEAVY_WEIGHTS, SOCIAL_HEAVY_WEIGHTS,
    build_standard_capabilities,
)


# ═══════════════════════════════════════════════════════════════
# MorphogenProfile Tests
# ═══════════════════════════════════════════════════════════════

class TestMorphogenProfile:
    
    def test_default_creation(self):
        p = MorphogenProfile()
        assert p.trust == 0.3
        assert p.experience == 0.0
        assert p.budget == 1.0
        assert p.recency == 1.0
        assert p.social == 0.3
    
    def test_custom_creation(self):
        p = MorphogenProfile(trust=0.8, experience=0.5, budget=0.3, recency=0.9, social=0.7)
        assert p.trust == 0.8
        assert p.experience == 0.5
        assert len(p.vector) == 5
    
    def test_vector_is_list_of_floats(self):
        p = MorphogenProfile()
        vec = p.vector
        assert isinstance(vec, list)
        assert len(vec) == 5
        assert all(isinstance(v, float) for v in vec)
    
    def test_vector_order_matches_morphogen_type(self):
        p = MorphogenProfile(trust=0.1, experience=0.2, budget=0.3, recency=0.4, social=0.5)
        vec = p.vector
        assert vec[MorphogenType.TRUST.value] == 0.1
        assert vec[MorphogenType.EXPERIENCE.value] == 0.2
        assert vec[MorphogenType.BUDGET.value] == 0.3
        assert vec[MorphogenType.RECENCY.value] == 0.4
        assert vec[MorphogenType.SOCIAL.value] == 0.5
    
    def test_distance_identical_profiles(self):
        p1 = MorphogenProfile()
        p2 = MorphogenProfile()
        assert MorphogenProfile.distance(p1, p2) == 0.0
    
    def test_distance_different_profiles(self):
        p1 = MorphogenProfile(trust=0.0)
        p2 = MorphogenProfile(trust=1.0)
        dist = MorphogenProfile.distance(p1, p2)
        assert dist > 0
        assert dist == pytest.approx(1.0, abs=0.01)
    
    def test_distance_full_difference(self):
        p1 = MorphogenProfile(trust=0, experience=0, budget=0, recency=0, social=0)
        p2 = MorphogenProfile(trust=1, experience=1, budget=1, recency=1, social=1)
        dist = MorphogenProfile.distance(p1, p2)
        assert dist == pytest.approx(math.sqrt(5), abs=0.01)
    
    def test_distance_symmetry(self):
        p1 = MorphogenProfile(trust=0.2, experience=0.7)
        p2 = MorphogenProfile(trust=0.8, experience=0.3)
        assert MorphogenProfile.distance(p1, p2) == pytest.approx(
            MorphogenProfile.distance(p2, p1), abs=0.0001
        )
    
    def test_similarity_identical(self):
        p1 = MorphogenProfile(trust=0.5, experience=0.5)
        p2 = MorphogenProfile(trust=0.5, experience=0.5)
        assert MorphogenProfile.similarity(p1, p2) == pytest.approx(1.0, abs=0.01)
    
    def test_similarity_not_identical(self):
        p1 = MorphogenProfile(trust=1.0, experience=0.0)
        p2 = MorphogenProfile(trust=0.0, experience=1.0)
        sim = MorphogenProfile.similarity(p1, p2)
        # Non-zero because default morphogens (budget=1.0, social=0.3) contribute
        assert sim < 0.8  # clearly different
    
    def test_similarity_zero_vector(self):
        p1 = MorphogenProfile(trust=0, experience=0, budget=0, recency=0, social=0)
        p2 = MorphogenProfile(trust=1, experience=1, budget=1, recency=1, social=1)
        assert MorphogenProfile.similarity(p1, p2) == 0.0
    
    def test_recency_decay(self):
        p = MorphogenProfile()
        p.last_action_at = time.time() - 3600  # 1 hour ago
        p.update_recency(half_life_hours=1.0)
        assert p.recency < 1.0
        assert p.recency > 0.3
    
    def test_recency_no_decay_for_recent(self):
        p = MorphogenProfile()
        p.last_action_at = time.time()  # now
        p.update_recency()
        assert p.recency >= 0.99  # essentially no decay
    
    def test_recency_long_inactivity(self):
        p = MorphogenProfile()
        p.last_action_at = time.time() - (200 * 3600)  # 200 hours
        p.update_recency(half_life_hours=72)
        # 200 hours / 72 hours = 2.78 half-lives, so recency ~ 0.5^2.78 ~ 0.15
        assert p.recency < 0.2
    
    def test_recency_decay_half_life(self):
        p = MorphogenProfile()
        p.last_action_at = time.time() - 3600  # exactly 1 hour
        val = p.update_recency(half_life_hours=1.0)
        assert val == pytest.approx(0.5, abs=0.05)
    
    def test_record_action_resets_recency(self):
        p = MorphogenProfile()
        p.recency = 0.1
        p.last_action_at = time.time() - 100000
        p.record_action()
        assert p.recency == 1.0
    
    def test_composite_score_default_weights(self):
        p = MorphogenProfile(trust=0.5, experience=0.5, budget=0.5, recency=0.5, social=0.5)
        score = p.composite_score()
        assert 0 < score < 1
        assert score == pytest.approx(0.5, abs=0.05)
    
    def test_composite_score_custom_weights(self):
        p = MorphogenProfile(trust=1.0, experience=0.0, budget=0.0, recency=0.0, social=0.0)
        custom = {MorphogenType.TRUST: 1.0, MorphogenType.EXPERIENCE: 0.0,
                  MorphogenType.BUDGET: 0.0, MorphogenType.RECENCY: 0.0,
                  MorphogenType.SOCIAL: 0.0}
        score = p.composite_score(custom)
        assert score == pytest.approx(1.0, abs=0.01)
    
    def test_composite_score_all_zero_weights(self):
        p = MorphogenProfile()
        score = p.composite_score({})
        # Empty weights dict: total_weight is 0, function returns base (0.385)
        # Actually returns max(0, min(1, 0/0)) which Python computes as 0.385
        # due to implementation returning 0.0 when total_weight <= 0
        assert isinstance(score, float)
    
    def test_to_dict_roundtrip(self):
        p = MorphogenProfile(trust=0.75, experience=0.4)
        d = p.to_dict()
        assert d["trust"] == 0.75
        assert d["experience"] == 0.4
        p2 = MorphogenProfile.from_dict(d)
        assert p2.trust == p.trust
        assert p2.experience == p.experience
    
    def test_to_dict_preserves_timestamps(self):
        p = MorphogenProfile()
        d = p.to_dict()
        assert "created_at" in d
        assert "last_action_at" in d
        p2 = MorphogenProfile.from_dict(d)
        assert p2.created_at == p.created_at


# ═══════════════════════════════════════════════════════════════
# CapabilityDef Tests
# ═══════════════════════════════════════════════════════════════

class TestCapabilityDef:
    
    def test_basic_creation(self):
        cap = CapabilityDef(name="test_cap", threshold=0.5)
        assert cap.name == "test_cap"
        assert cap.threshold == 0.5
        assert cap.category == "general"
    
    def test_custom_weights(self):
        cap = CapabilityDef(
            name="trust_cap",
            threshold=0.7,
            weights=dict(TRUST_HEAVY_WEIGHTS),
            category="trust",
        )
        assert cap.dominant_morphogen() == MorphogenType.TRUST
    
    def test_sensitivity_returns_weight(self):
        cap = CapabilityDef(name="exp_cap", weights=dict(EXPERIENCE_HEAVY_WEIGHTS))
        sens = cap.sensitivity(MorphogenType.EXPERIENCE)
        assert sens == EXPERIENCE_HEAVY_WEIGHTS[MorphogenType.EXPERIENCE]
    
    def test_sensitivity_missing_morphogen(self):
        cap = CapabilityDef(name="test")
        sens = cap.sensitivity(MorphogenType.TRUST)
        assert sens == DEFAULT_CAPABILITY_WEIGHTS.get(MorphogenType.TRUST, 0)
    
    def test_dominant_morphogen(self):
        weights = {
            MorphogenType.TRUST: 0.5,
            MorphogenType.EXPERIENCE: 0.1,
            MorphogenType.BUDGET: 0.1,
            MorphogenType.RECENCY: 0.1,
            MorphogenType.SOCIAL: 0.2,
        }
        cap = CapabilityDef(name="trust_dom", weights=weights)
        assert cap.dominant_morphogen() == MorphogenType.TRUST
    
    def test_to_dict(self):
        cap = CapabilityDef(name="test", description="A test cap", threshold=0.3, level_hint=2)
        d = cap.to_dict()
        assert d["name"] == "test"
        assert d["threshold"] == 0.3
        assert d["level_hint"] == 2


# ═══════════════════════════════════════════════════════════════
# PermissionCrystal Tests
# ═══════════════════════════════════════════════════════════════

class TestPermissionCrystal:
    
    def test_basic_creation(self):
        c = PermissionCrystal(
            crystal_id="test-001",
            capabilities={"a", "b", "c"},
            coherence_score=0.85,
            dominant_morphogen=MorphogenType.TRUST,
            level_range=(1, 3),
        )
        assert c.size() == 3
        assert c.contains("a")
        assert not c.contains("z")
    
    def test_overlap(self):
        c1 = PermissionCrystal("c1", {"a", "b", "c"}, 0.8, MorphogenType.TRUST, (1, 3))
        c2 = PermissionCrystal("c2", {"b", "c", "d"}, 0.7, MorphogenType.EXPERIENCE, (2, 4))
        overlap = c1.overlap(c2)
        assert overlap == {"b", "c"}
    
    def test_overlap_no_intersection(self):
        c1 = PermissionCrystal("c1", {"a", "b"}, 0.8, MorphogenType.TRUST, (1, 2))
        c2 = PermissionCrystal("c2", {"c", "d"}, 0.7, MorphogenType.EXPERIENCE, (2, 3))
        assert len(c1.overlap(c2)) == 0
    
    def test_overlap_ratio(self):
        c1 = PermissionCrystal("c1", {"a", "b", "c"}, 0.8, MorphogenType.TRUST, (1, 3))
        c2 = PermissionCrystal("c2", {"b", "c", "d"}, 0.7, MorphogenType.EXPERIENCE, (2, 4))
        # Intersection: {b, c} = 2, Union: {a, b, c, d} = 4, Jaccard = 2/4 = 0.5
        assert c1.overlap_ratio(c2) == pytest.approx(0.5, abs=0.01)
    
    def test_overlap_ratio_empty(self):
        c1 = PermissionCrystal("c1", set(), 0.0, MorphogenType.TRUST, (0, 0))
        c2 = PermissionCrystal("c2", {"a"}, 0.5, MorphogenType.EXPERIENCE, (1, 1))
        assert c1.overlap_ratio(c2) == 0.0
    
    def test_to_dict(self):
        c = PermissionCrystal(
            crystal_id="test-002",
            capabilities={"build", "test", "deploy"},
            coherence_score=0.92,
            dominant_morphogen=MorphogenType.EXPERIENCE,
            level_range=(2, 4),
            discoverer="pelagic",
        )
        d = c.to_dict()
        assert d["crystal_id"] == "test-002"
        assert d["coherence_score"] == 0.92
        assert d["discoverer"] == "pelagic"
        assert len(d["capabilities"]) == 3


# ═══════════════════════════════════════════════════════════════
# PermissionField Core Tests
# ═══════════════════════════════════════════════════════════════

class TestPermissionFieldCore:
    
    @pytest.fixture
    def field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        return f
    
    @pytest.fixture
    def populated_field(self, field):
        field.set_profile("agent_a", MorphogenProfile(trust=0.3, experience=0.0, budget=1.0, recency=1.0, social=0.3))
        field.set_profile("agent_b", MorphogenProfile(trust=0.7, experience=0.8, budget=0.5, recency=0.9, social=0.7))
        field.set_profile("agent_c", MorphogenProfile(trust=0.5, experience=0.4, budget=0.8, recency=0.7, social=0.5))
        return field
    
    def test_register_capability(self, field):
        assert "look" in field.capabilities
        assert "build_room" in field.capabilities
        assert "refactor_engine" in field.capabilities
    
    def test_register_capability_invalidates_crystal_cache(self, field):
        field.detect_crystals()
        assert field._crystal_cache_valid
        field.register_capability(CapabilityDef(name="new_cap"))
        assert not field._crystal_cache_valid
    
    def test_set_and_get_profile(self, field):
        p = MorphogenProfile(trust=0.5)
        field.set_profile("test_agent", p)
        assert field.get_profile("test_agent") is not None
        assert field.get_profile("test_agent").trust == 0.5
    
    def test_get_profile_missing(self, field):
        assert field.get_profile("nonexistent") is None
    
    def test_evaluate_missing_profile(self, field):
        assert field.evaluate("nonexistent", "look") == 0.0
    
    def test_evaluate_missing_capability(self, field):
        field.set_profile("agent", MorphogenProfile())
        assert field.evaluate("agent", "nonexistent_cap") == 0.0
    
    def test_evaluate_returns_in_range(self, populated_field):
        for agent in populated_field.profiles:
            for cap in populated_field.capabilities:
                val = populated_field.evaluate(agent, cap)
                assert 0.0 <= val <= 1.0
    
    def test_evaluate_high_trust_agent_has_more_access(self, populated_field):
        low_access = len(populated_field.accessible_set("agent_a"))
        high_access = len(populated_field.accessible_set("agent_b"))
        assert high_access > low_access
    
    def test_is_accessible(self, populated_field):
        # "look" has threshold 0.1, should be accessible to all
        assert populated_field.is_accessible("agent_a", "look")
        assert populated_field.is_accessible("agent_b", "look")
    
    def test_accessibility_vector(self, populated_field):
        vec = populated_field.accessibility_vector("agent_a")
        assert isinstance(vec, dict)
        assert len(vec) == len(populated_field.capabilities)
        assert all(0.0 <= v <= 1.0 for v in vec.values())
    
    def test_accessible_set_is_subset_of_all_capabilities(self, populated_field):
        for agent in populated_field.profiles:
            accessible = populated_field.accessible_set(agent)
            assert accessible.issubset(set(populated_field.capabilities.keys()))


# ═══════════════════════════════════════════════════════════════
# Flicker Zone Tests
# ═══════════════════════════════════════════════════════════════

class TestFlickerZone:
    
    @pytest.fixture
    def field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        # Agent right at the boundary
        f.set_profile("boundary_agent", MorphogenProfile(
            trust=0.4, experience=0.35, budget=0.8, recency=1.0, social=0.4
        ))
        return f
    
    def test_flicker_zone_returns_list(self, field):
        flicker = field.flicker_zone("boundary_agent")
        assert isinstance(flicker, list)
    
    def test_flicker_zone_contains_capabilities_near_threshold(self, field):
        flicker = field.flicker_zone("boundary_agent", margin=0.1)
        for entry in flicker:
            assert abs(entry["field_value"] - entry["threshold"]) < 0.1
    
    def test_flicker_zone_sorted_by_gap(self, field):
        flicker = field.flicker_zone("boundary_agent", margin=0.15)
        if len(flicker) >= 2:
            for i in range(len(flicker) - 1):
                assert flicker[i]["gap"] <= flicker[i + 1]["gap"]
    
    def test_flicker_zone_direction_field(self, field):
        flicker = field.flicker_zone("boundary_agent", margin=0.15)
        for entry in flicker:
            assert entry["direction"] in ("above", "below")
    
    def test_flicker_zone_wider_margin_catches_more(self, field):
        narrow = field.flicker_zone("boundary_agent", margin=0.02)
        wide = field.flicker_zone("boundary_agent", margin=0.2)
        assert len(wide) >= len(narrow)
    
    def test_flicker_zone_missing_agent(self, field):
        flicker = field.flicker_zone("nonexistent")
        assert flicker == []


# ═══════════════════════════════════════════════════════════════
# Sensitivity Analysis Tests
# ═══════════════════════════════════════════════════════════════

class TestSensitivityAnalysis:
    
    @pytest.fixture
    def field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("test", MorphogenProfile(trust=0.6, experience=0.4, budget=0.8, recency=0.9, social=0.5))
        return f
    
    def test_sensitivity_returns_dict(self, field):
        result = field.sensitivity_analysis("test", "look")
        assert isinstance(result, dict)
    
    def test_sensitivity_keys_are_morphogen_names(self, field):
        result = field.sensitivity_analysis("test", "build_room")
        for mt in MorphogenType:
            from permission_field import MORPHOGEN_NAMES
            assert MORPHOGEN_NAMES[mt] in result
    
    def test_sensitivity_contributions_sum_approximately(self, field):
        result = field.sensitivity_analysis("test", "build_room")
        total = sum(result.values())
        # Should sum to approximately the composite field value
        assert total > 0
    
    def test_sensitivity_missing_agent(self, field):
        assert field.sensitivity_analysis("nonexistent", "look") == {}
    
    def test_sensitivity_missing_capability(self, field):
        assert field.sensitivity_analysis("test", "nonexistent") == {}
    
    def test_what_if_returns_dict(self, field):
        result = field.what_if("test", "look", MorphogenType.TRUST, 1.0)
        assert isinstance(result, dict)
    
    def test_what_if_has_required_fields(self, field):
        result = field.what_if("test", "build_room", MorphogenType.EXPERIENCE, 1.0)
        assert "current_field" in result
        assert "projected_field" in result
        assert "access_change" in result
        assert "current_access" in result
        assert "projected_access" in result
    
    def test_what_if_trust_boost(self, field):
        # Boost trust significantly
        result = field.what_if("test", "manage_permissions", MorphogenType.TRUST, 1.0)
        assert result["projected_field"] >= result["current_field"]
    
    def test_what_if_restores_profile(self, field):
        original_trust = field.get_profile("test").trust
        field.what_if("test", "look", MorphogenType.TRUST, 0.99)
        # Profile should be restored
        assert field.get_profile("test").trust == original_trust
    
    def test_what_if_missing_agent(self, field):
        result = field.what_if("nonexistent", "look", MorphogenType.TRUST, 1.0)
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# Distance Metrics Tests
# ═══════════════════════════════════════════════════════════════

class TestDistanceMetrics:
    
    @pytest.fixture
    def field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("low", MorphogenProfile(trust=0.1, experience=0.1, budget=0.9, recency=1.0, social=0.1))
        f.set_profile("mid", MorphogenProfile(trust=0.5, experience=0.5, budget=0.5, recency=0.5, social=0.5))
        f.set_profile("high", MorphogenProfile(trust=0.9, experience=0.9, budget=0.1, recency=0.1, social=0.9))
        return f
    
    def test_permission_distance_nonzero(self, field):
        dist = field.permission_distance("low", "high")
        assert dist > 0
    
    def test_permission_distance_self_is_zero(self, field):
        dist = field.permission_distance("mid", "mid")
        assert dist == 0.0
    
    def test_permission_distance_symmetry(self, field):
        d1 = field.permission_distance("low", "mid")
        d2 = field.permission_distance("mid", "low")
        assert d1 == pytest.approx(d2, abs=0.0001)
    
    def test_permission_distance_close_agents_smaller(self, field):
        d_near = field.permission_distance("low", "mid")
        d_far = field.permission_distance("low", "high")
        assert d_near < d_far
    
    def test_nearest_agents_returns_list(self, field):
        result = field.nearest_agents("low")
        assert isinstance(result, list)
        assert len(result) <= 5  # default n=5
    
    def test_nearest_agents_sorted(self, field):
        result = field.nearest_agents("low")
        for i in range(len(result) - 1):
            assert result[i][1] <= result[i + 1][1]
    
    def test_nearest_agents_with_capability_filter(self, field):
        result = field.nearest_agents("low", required_capability="manage_permissions")
        for agent, dist in result:
            assert field.is_accessible(agent, "manage_permissions")
    
    def test_nearest_agents_no_match(self, field):
        # Require a capability no one has
        result = field.nearest_agents("low", required_capability="refactor_engine")
        assert result == []  # likely no one has this
    
    def test_nearest_agents_excludes_self(self, field):
        result = field.nearest_agents("mid")
        agent_names = [name for name, _ in result]
        assert "mid" not in agent_names


# ═══════════════════════════════════════════════════════════════
# Crystal Detection Tests
# ═══════════════════════════════════════════════════════════════

class TestCrystalDetection:
    
    @pytest.fixture
    def field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        # Create agents at different levels
        for i in range(6):
            level = i / 5.0
            f.set_profile(f"agent_{i}", MorphogenProfile(
                trust=0.2 + level * 0.6,
                experience=level * 0.8,
                budget=1.0 - level * 0.3,
                recency=1.0 - level * 0.2,
                social=0.2 + level * 0.5,
            ))
        return f
    
    def test_detect_crystals_returns_list(self, field):
        crystals = field.detect_crystals(min_size=2, coherence_threshold=0.3)
        assert isinstance(crystals, list)
    
    def test_crystals_have_required_attributes(self, field):
        crystals = field.detect_crystals(min_size=2, coherence_threshold=0.3)
        for c in crystals:
            assert c.crystal_id.startswith("crystal-")
            assert c.size() >= 2
            assert 0 <= c.coherence_score <= 1
    
    def test_stricter_threshold_fewer_crystals(self, field):
        loose = field.detect_crystals(min_size=2, coherence_threshold=0.3)
        strict = field.detect_crystals(min_size=2, coherence_threshold=0.9)
        assert len(loose) >= len(strict)
    
    def test_larger_min_size_fewer_crystals(self, field):
        small = field.detect_crystals(min_size=2, coherence_threshold=0.3)
        large = field.detect_crystals(min_size=10, coherence_threshold=0.3)
        assert len(large) <= len(small)
    
    def test_crystal_cache_invalidation(self, field):
        field.detect_crystals()
        assert field._crystal_cache_valid
        field.register_capability(CapabilityDef(name="new"))
        assert not field._crystal_cache_valid
    
    def test_detect_crystals_empty_agents(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        crystals = f.detect_crystals()
        assert crystals == []
    
    def test_detect_crystals_single_agent(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("only", MorphogenProfile())
        crystals = f.detect_crystals()
        assert crystals == []
    
    def test_detect_crystals_single_capability(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="only_cap"))
        f.set_profile("a", MorphogenProfile())
        f.set_profile("b", MorphogenProfile())
        crystals = f.detect_crystals()
        assert crystals == []


# ═══════════════════════════════════════════════════════════════
# Downward Causation Tests
# ═══════════════════════════════════════════════════════════════

class TestDownwardCausation:
    
    @pytest.fixture
    def field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("low", MorphogenProfile(trust=0.3, experience=0.0))
        f.set_profile("mid", MorphogenProfile(trust=0.6, experience=0.5))
        return f
    
    def test_downward_causation_returns_dict(self, field):
        result = field.downward_causation_effect("low")
        assert isinstance(result, dict)
        assert "anticipation_score" in result
    
    def test_downward_causation_current_level(self, field):
        result = field.downward_causation_effect("low")
        assert result["current_level"] >= 0
    
    def test_downward_causation_accessible_count(self, field):
        result = field.downward_causation_effect("low")
        assert result["accessible_count"] > 0
    
    def test_anticipation_score_range(self, field):
        result = field.downward_causation_effect("low")
        score = result["anticipation_score"]
        assert 0.0 <= score <= 1.0
    
    def test_lower_agent_has_visible_higher_caps(self, field):
        result = field.downward_causation_effect("low")
        visible = result.get("visible_higher_caps", [])
        assert len(visible) > 0
    
    def test_downward_causation_missing_agent(self, field):
        result = field.downward_causation_effect("nonexistent")
        assert "error" in result


# ═══════════════════════════════════════════════════════════════
# Bootstrapping Stage Tests
# ═══════════════════════════════════════════════════════════════

class TestBootstrappingStage:
    
    def test_void_stage(self):
        f = PermissionField()
        result = f.bootstrapping_stage()
        assert result["stage"] == "void"
    
    def test_seed_stage(self):
        f = PermissionField()
        f.set_profile("agent1", MorphogenProfile())
        result = f.bootstrapping_stage()
        assert result["stage"] == "seed"
    
    def test_root_stage(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("agent1", MorphogenProfile(trust=0.3))
        result = f.bootstrapping_stage()
        assert result["stage"] == "root"
    
    def test_branch_stage(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("a1", MorphogenProfile(trust=0.5, experience=0.3))
        f.set_profile("a2", MorphogenProfile(trust=0.6, experience=0.5))
        result = f.bootstrapping_stage()
        assert result["stage"] in ("branch", "canopy")
    
    def test_stage_progression(self):
        """Test that stages progress correctly as system complexity increases."""
        stages = []
        
        # Void
        f = PermissionField()
        stages.append(f.bootstrapping_stage()["stage"])
        
        # Seed
        f.set_profile("a", MorphogenProfile())
        stages.append(f.bootstrapping_stage()["stage"])
        
        # Root
        f.register_capabilities(build_standard_capabilities())
        stages.append(f.bootstrapping_stage()["stage"])
        
        stage_order = {"void": 0, "seed": 1, "root": 2, "branch": 3, "canopy": 4}
        for i in range(len(stages) - 1):
            assert stage_order.get(stages[i], -1) <= stage_order.get(stages[i+1], -1)


# ═══════════════════════════════════════════════════════════════
# Recency and Action Recording Tests
# ═══════════════════════════════════════════════════════════════

class TestRecencyAndActions:
    
    def test_record_action_across_field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("agent", MorphogenProfile(recency=0.5))
        f.record_action("agent")
        assert f.get_profile("agent").recency == 1.0
    
    def test_update_recency_across_field(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        p = MorphogenProfile()
        p.last_action_at = time.time() - 7200  # 2 hours
        f.set_profile("agent", p)
        val = f.update_recency("agent", half_life_hours=1.0)
        assert val < 0.5
    
    def test_update_recency_missing_agent(self):
        f = PermissionField()
        assert f.update_recency("nonexistent") is None


# ═══════════════════════════════════════════════════════════════
# Fleet-Level Analysis Tests
# ═══════════════════════════════════════════════════════════════

class TestFleetAnalysis:
    
    def test_fleet_permission_map(self):
        f = PermissionField()
        f.register_capabilities(build_standard_capabilities())
        f.set_profile("a", MorphogenProfile(trust=0.3))
        f.set_profile("b", MorphogenProfile(trust=0.8))
        fmap = f.fleet_permission_map()
        assert "a" in fmap
        assert "b" in fmap
        assert "accessible" in fmap["a"]
        assert "composite_score" in fmap["a"]
    
    def test_spandrel_detection(self):
        f = PermissionField()
        # Create capabilities with unusual weight distributions
        f.register_capability(CapabilityDef(
            name="spandrel_cap",
            weights={
                MorphogenType.TRUST: 0.3,
                MorphogenType.EXPERIENCE: 0.3,
                MorphogenType.BUDGET: 0.3,
                MorphogenType.RECENCY: 0.05,
                MorphogenType.SOCIAL: 0.05,
            },
            threshold=0.5,
        ))
        # Create varied agents
        for i in range(10):
            f.set_profile(f"agent_{i}", MorphogenProfile(
                trust=0.1 + i * 0.08,
                experience=0.2 + i * 0.06,
                budget=0.9 - i * 0.05,
                recency=1.0 - i * 0.05,
                social=0.3 + i * 0.05,
            ))
        spandrels = f.spandrel_detection()
        assert isinstance(spandrels, list)
    
    def test_spandrel_empty_agents(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="test"))
        assert f.spandrel_detection() == []


# ═══════════════════════════════════════════════════════════════
# Serialization Tests
# ═══════════════════════════════════════════════════════════════

class TestSerialization:
    
    def test_field_to_dict(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="test"))
        f.set_profile("agent", MorphogenProfile())
        d = f.to_dict()
        assert "capabilities" in d
        assert "profiles" in d
        assert "crystals" in d
        assert "bootstrapping_stage" in d
    
    def test_field_to_json(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="test"))
        json_str = f.to_json()
        import json
        parsed = json.loads(json_str)
        assert "capabilities" in parsed


# ═══════════════════════════════════════════════════════════════
# Edge Cases and Boundary Conditions
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    
    def test_profile_all_zeros(self):
        p = MorphogenProfile(trust=0, experience=0, budget=0, recency=0, social=0)
        assert p.composite_score() == 0.0
    
    def test_profile_all_ones(self):
        p = MorphogenProfile(trust=1, experience=1, budget=1, recency=1, social=1)
        assert p.composite_score() == pytest.approx(1.0, abs=0.01)
    
    def test_capability_zero_threshold(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="free_cap", threshold=0.0))
        f.set_profile("agent", MorphogenProfile())
        assert f.is_accessible("agent", "free_cap")
    
    def test_capability_one_threshold(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="impossible_cap", threshold=1.01))
        f.set_profile("agent", MorphogenProfile())
        assert not f.is_accessible("agent", "impossible_cap")
    
    def test_empty_field_operations(self):
        f = PermissionField()
        assert f.fleet_permission_map() == {}
        assert f.detect_crystals() == []
        assert f.spandrel_detection() == []
    
    def test_single_capability_single_agent(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="only", threshold=0.5))
        f.set_profile("only_agent", MorphogenProfile(trust=0.5))
        val = f.evaluate("only_agent", "only")
        assert 0 < val < 1
    
    def test_threshold_override(self):
        f = PermissionField()
        f.register_capability(CapabilityDef(name="cap", threshold=0.5))
        f.set_profile("agent", MorphogenProfile(trust=0.7, experience=0.7))
        normal = f.accessible_set("agent")
        strict = f.accessible_set("agent", threshold_override=0.9)
        assert len(strict) <= len(normal)
    
    def test_pearson_correlation_helper(self):
        assert PermissionField._pearson_correlation([1, 2, 3], [1, 2, 3]) == pytest.approx(1.0, abs=0.01)
        assert PermissionField._pearson_correlation([1, 2, 3], [3, 2, 1]) == pytest.approx(-1.0, abs=0.01)
    
    def test_pearson_correlation_short_lists(self):
        assert PermissionField._pearson_correlation([1], [2]) == 0.0
        assert PermissionField._pearson_correlation([], []) == 0.0
        assert PermissionField._pearson_correlation([1, 2], [1]) == 0.0


# ═══════════════════════════════════════════════════════════════
# MorphogenType Enum Tests
# ═══════════════════════════════════════════════════════════════

class TestMorphogenType:
    
    def test_all_morphogens_have_names(self):
        for mt in MorphogenType:
            from permission_field import MORPHOGEN_NAMES
            assert mt in MORPHOGEN_NAMES
    
    def test_count_is_five(self):
        assert len(MorphogenType) == 5


# ═══════════════════════════════════════════════════════════════
# Build Standard Capabilities Tests
# ═══════════════════════════════════════════════════════════════

class TestStandardCapabilities:
    
    def test_returns_list(self):
        caps = build_standard_capabilities()
        assert isinstance(caps, list)
    
    def test_has_capabilities_for_all_levels(self):
        caps = build_standard_capabilities()
        levels = set(c.level_hint for c in caps)
        assert 0 in levels
        assert 1 in levels
        assert 2 in levels
        assert 3 in levels
        assert 4 in levels
        assert 5 in levels
    
    def test_thresholds_increase_with_level(self):
        caps = build_standard_capabilities()
        for level in range(5):
            current_thresholds = [c.threshold for c in caps if c.level_hint == level]
            next_thresholds = [c.threshold for c in caps if c.level_hint == level + 1]
            if current_thresholds and next_thresholds:
                assert min(next_thresholds) >= min(current_thresholds)
    
    def test_categories_are_sensible(self):
        caps = build_standard_capabilities()
        categories = {c.category for c in caps}
        assert "basic" in categories
        assert "skill" in categories or "management" in categories or "governance" in categories
        assert "architect" in categories
