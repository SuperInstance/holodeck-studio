#!/usr/bin/env python3
"""
Comprehensive test suite for trust_permission_integration.py

Covers: TrustPermissionConfig, TrustPermissionBridge, PermissionEvaluation,
        SyncResult, DEFAULT_PERMISSION_THRESHOLDS, serialization, edge cases.
Target: 100+ tests
"""

import json
import sys
import time
import math
from pathlib import Path
from unittest import TestCase
from unittest.mock import MagicMock, patch, PropertyMock

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trust_permission_integration import (
    DEFAULT_PERMISSION_THRESHOLDS,
    DEFAULT_DIMENSION_WEIGHTS,
    TrustPermissionConfig,
    PermissionEvaluation,
    SyncResult,
    TrustPermissionBridge,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def make_mock_trust_engine(composite_trust: float = 0.5, dimensions: dict = None):
    """Create a mock TrustEngine with controllable trust scores."""
    engine = MagicMock()
    engine.composite_trust.return_value = composite_trust

    profile = MagicMock()
    profile.composite.return_value = composite_trust
    profile.summary.return_value = {
        "composite": composite_trust,
        "dimensions": dimensions or {
            "code_quality": composite_trust,
            "task_completion": composite_trust,
            "collaboration": composite_trust,
            "reliability": composite_trust,
            "innovation": composite_trust,
        },
    }

    def composite_with_weights(weights=None):
        if not weights:
            return composite_trust
        # Simple weighted sum with the mock dimension scores
        dims = dimensions or {
            "code_quality": composite_trust,
            "task_completion": composite_trust,
            "collaboration": composite_trust,
            "reliability": composite_trust,
            "innovation": composite_trust,
        }
        total_w = sum(weights.values())
        if total_w <= 0:
            return composite_trust
        return sum(dims.get(d, 0) * w for d, w in weights.items()) / total_w

    profile.composite.side_effect = composite_with_weights
    engine.get_profile.return_value = profile
    return engine


def make_mock_permission_field():
    """Create a mock PermissionField."""
    pf = MagicMock()
    pf.profiles = {}
    pf.capabilities = {}
    return pf


def make_bridge(
    composite_trust: float = 0.5,
    config: TrustPermissionConfig = None,
    with_pf: bool = False,
    dimensions: dict = None,
):
    """Create a TrustPermissionBridge with a mock trust engine."""
    te = make_mock_trust_engine(composite_trust, dimensions)
    pf = make_mock_permission_field() if with_pf else None
    cfg = config or TrustPermissionConfig()
    return TrustPermissionBridge(config=cfg, trust_engine=te, permission_field=pf)


# ═══════════════════════════════════════════════════════════════════════════
# 1. DEFAULT_PERMISSION_THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════

class TestDefaultPermissionThresholds(TestCase):
    def test_thresholds_exist(self):
        self.assertIsInstance(DEFAULT_PERMISSION_THRESHOLDS, dict)
        self.assertTrue(len(DEFAULT_PERMISSION_THRESHOLDS) > 0)

    def test_at_least_10_thresholds(self):
        self.assertGreaterEqual(len(DEFAULT_PERMISSION_THRESHOLDS), 10)

    def test_basic_commands_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["basic_commands"], 0.1)

    def test_room_creation_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["room_creation"], 0.3)

    def test_agent_communication_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["agent_communication"], 0.3)

    def test_cartridge_loading_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["cartridge_loading"], 0.5)

    def test_trust_attestation_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["trust_attestation"], 0.6)

    def test_fleet_broadcast_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["fleet_broadcast"], 0.7)

    def test_governance_voting_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["governance_voting"], 0.8)

    def test_permission_granting_threshold(self):
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["permission_granting"], 0.9)

    def test_all_thresholds_between_0_and_1(self):
        for perm, thresh in DEFAULT_PERMISSION_THRESHOLDS.items():
            self.assertGreaterEqual(thresh, 0.0, f"{perm} threshold < 0")
            self.assertLessEqual(thresh, 1.0, f"{perm} threshold > 1")

    def test_thresholds_monotonically_increase_for_key_permissions(self):
        """Higher-privilege permissions should generally have higher thresholds."""
        self.assertLessEqual(
            DEFAULT_PERMISSION_THRESHOLDS["basic_commands"],
            DEFAULT_PERMISSION_THRESHOLDS["room_creation"],
        )
        self.assertLessEqual(
            DEFAULT_PERMISSION_THRESHOLDS["room_creation"],
            DEFAULT_PERMISSION_THRESHOLDS["fleet_broadcast"],
        )
        self.assertLessEqual(
            DEFAULT_PERMISSION_THRESHOLDS["fleet_broadcast"],
            DEFAULT_PERMISSION_THRESHOLDS["permission_granting"],
        )

    def test_emergency_powers_has_highest_threshold(self):
        max_thresh = max(DEFAULT_PERMISSION_THRESHOLDS.values())
        self.assertEqual(DEFAULT_PERMISSION_THRESHOLDS["emergency_powers"], max_thresh)

    def test_no_duplicate_threshold_values_required(self):
        """All thresholds should be valid even if some share the same value."""
        values = list(DEFAULT_PERMISSION_THRESHOLDS.values())
        self.assertEqual(len(values), len(DEFAULT_PERMISSION_THRESHOLDS))


# ═══════════════════════════════════════════════════════════════════════════
# 2. DEFAULT_DIMENSION_WEIGHTS
# ═══════════════════════════════════════════════════════════════════════════

class TestDefaultDimensionWeights(TestCase):
    def test_weights_exist(self):
        self.assertIsInstance(DEFAULT_DIMENSION_WEIGHTS, dict)

    def test_has_weights_for_each_default_permission(self):
        for perm in DEFAULT_PERMISSION_THRESHOLDS:
            self.assertIn(perm, DEFAULT_DIMENSION_WEIGHTS,
                          f"Missing dimension weights for {perm}")

    def test_each_weight_dict_has_5_dimensions(self):
        for perm, weights in DEFAULT_DIMENSION_WEIGHTS.items():
            self.assertEqual(len(weights), 5, f"{perm} has {len(weights)} dimensions")

    def test_each_weight_dict_sums_to_one(self):
        for perm, weights in DEFAULT_DIMENSION_WEIGHTS.items():
            total = sum(weights.values())
            self.assertAlmostEqual(total, 1.0, places=2,
                                   msg=f"{perm} weights sum to {total}")

    def test_all_weights_non_negative(self):
        for perm, weights in DEFAULT_DIMENSION_WEIGHTS.items():
            for dim, w in weights.items():
                self.assertGreaterEqual(w, 0.0, f"{perm}/{dim} weight negative")

    def test_communication_emphasizes_collaboration(self):
        w = DEFAULT_DIMENSION_WEIGHTS["agent_communication"]
        self.assertGreaterEqual(w["collaboration"], 0.4)

    def test_trust_attestation_emphasizes_reliability(self):
        w = DEFAULT_DIMENSION_WEIGHTS["trust_attestation"]
        self.assertGreaterEqual(w["reliability"], 0.3)

    def test_spell_creation_emphasizes_code_quality(self):
        w = DEFAULT_DIMENSION_WEIGHTS["spell_creation"]
        self.assertGreaterEqual(w["code_quality"], 0.2)

    def test_emergency_powers_emphasizes_reliability(self):
        w = DEFAULT_DIMENSION_WEIGHTS["emergency_powers"]
        self.assertGreaterEqual(w["reliability"], 0.3)


# ═══════════════════════════════════════════════════════════════════════════
# 3. TrustPermissionConfig
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustPermissionConfig(TestCase):
    def test_default_construction(self):
        config = TrustPermissionConfig()
        self.assertEqual(config.default_threshold, 0.3)
        self.assertEqual(config.decay_grace_period, 86400.0)
        self.assertTrue(config.auto_grant_enabled)
        self.assertTrue(config.auto_revoke_enabled)

    def test_default_has_all_thresholds(self):
        config = TrustPermissionConfig()
        self.assertEqual(len(config.trust_thresholds), len(DEFAULT_PERMISSION_THRESHOLDS))

    def test_get_threshold_existing(self):
        config = TrustPermissionConfig()
        self.assertEqual(config.get_threshold("basic_commands"), 0.1)

    def test_get_threshold_missing_uses_default(self):
        config = TrustPermissionConfig()
        self.assertEqual(config.get_threshold("nonexistent_perm"), 0.3)

    def test_get_dimension_weight_existing(self):
        config = TrustPermissionConfig()
        w = config.get_dimension_weight("agent_communication")
        self.assertIn("collaboration", w)

    def test_get_dimension_weight_missing(self):
        config = TrustPermissionConfig()
        w = config.get_dimension_weight("nonexistent_perm")
        self.assertEqual(w, {})

    def test_custom_default_threshold(self):
        config = TrustPermissionConfig(default_threshold=0.5)
        self.assertEqual(config.get_threshold("nonexistent_perm"), 0.5)

    def test_custom_grace_period(self):
        config = TrustPermissionConfig(decay_grace_period=43200.0)
        self.assertEqual(config.decay_grace_period, 43200.0)

    def test_auto_grant_disabled(self):
        config = TrustPermissionConfig(auto_grant_enabled=False)
        self.assertFalse(config.auto_grant_enabled)

    def test_auto_revoke_disabled(self):
        config = TrustPermissionConfig(auto_revoke_enabled=False)
        self.assertFalse(config.auto_revoke_enabled)

    def test_to_dict(self):
        config = TrustPermissionConfig()
        d = config.to_dict()
        self.assertIn("trust_thresholds", d)
        self.assertIn("default_threshold", d)
        self.assertIn("decay_grace_period", d)
        self.assertIn("auto_grant_enabled", d)
        self.assertIn("auto_revoke_enabled", d)
        self.assertIn("dimensions_weight", d)

    def test_to_dict_preserves_values(self):
        config = TrustPermissionConfig(
            default_threshold=0.7,
            decay_grace_period=3600.0,
            auto_grant_enabled=False,
            auto_revoke_enabled=False,
        )
        d = config.to_dict()
        self.assertEqual(d["default_threshold"], 0.7)
        self.assertEqual(d["decay_grace_period"], 3600.0)
        self.assertFalse(d["auto_grant_enabled"])
        self.assertFalse(d["auto_revoke_enabled"])

    def test_from_dict_roundtrip(self):
        config = TrustPermissionConfig(
            default_threshold=0.6,
            decay_grace_period=7200.0,
            auto_grant_enabled=False,
            auto_revoke_enabled=True,
        )
        d = config.to_dict()
        config2 = TrustPermissionConfig.from_dict(d)
        self.assertEqual(config2.default_threshold, 0.6)
        self.assertEqual(config2.decay_grace_period, 7200.0)
        self.assertFalse(config2.auto_grant_enabled)
        self.assertTrue(config2.auto_revoke_enabled)

    def test_from_dict_empty(self):
        config = TrustPermissionConfig.from_dict({})
        self.assertEqual(config.default_threshold, 0.3)
        self.assertTrue(config.auto_grant_enabled)

    def test_from_dict_preserves_thresholds(self):
        config = TrustPermissionConfig()
        config.add_threshold("custom_perm", 0.45) if hasattr(config, 'add_threshold') else None
        # Use trust_thresholds directly
        config.trust_thresholds["custom_perm"] = 0.45
        d = config.to_dict()
        config2 = TrustPermissionConfig.from_dict(d)
        self.assertEqual(config2.trust_thresholds["custom_perm"], 0.45)

    def test_dimensions_weight_in_to_dict(self):
        config = TrustPermissionConfig()
        d = config.to_dict()
        self.assertIsInstance(d["dimensions_weight"], dict)
        self.assertIn("basic_commands", d["dimensions_weight"])


# ═══════════════════════════════════════════════════════════════════════════
# 4. PermissionEvaluation
# ═══════════════════════════════════════════════════════════════════════════

class TestPermissionEvaluation(TestCase):
    def test_default_construction(self):
        ev = PermissionEvaluation(agent_name="alice")
        self.assertEqual(ev.agent_name, "alice")
        self.assertEqual(ev.granted, [])
        self.assertEqual(ev.denied, [])
        self.assertEqual(ev.revoked, [])
        self.assertEqual(ev.trust_scores, {})

    def test_construction_with_values(self):
        ev = PermissionEvaluation(
            agent_name="bob",
            granted=["basic_commands"],
            denied=["fleet_broadcast"],
            revoked=["room_creation"],
            trust_scores={"composite": 0.5},
        )
        self.assertEqual(ev.agent_name, "bob")
        self.assertEqual(len(ev.granted), 1)
        self.assertEqual(len(ev.denied), 1)
        self.assertEqual(len(ev.revoked), 1)

    def test_total_permissions(self):
        ev = PermissionEvaluation(
            agent_name="a",
            granted=["p1", "p2"],
            denied=["p3", "p4", "p5"],
            revoked=["p6"],
        )
        self.assertEqual(ev.total_permissions(), 6)

    def test_total_permissions_empty(self):
        ev = PermissionEvaluation(agent_name="a")
        self.assertEqual(ev.total_permissions(), 0)

    def test_grant_rate(self):
        ev = PermissionEvaluation(
            agent_name="a",
            granted=["p1", "p2", "p3"],
            denied=["p4"],
        )
        self.assertAlmostEqual(ev.grant_rate(), 0.75)

    def test_grant_rate_zero(self):
        ev = PermissionEvaluation(agent_name="a", denied=["p1"])
        self.assertAlmostEqual(ev.grant_rate(), 0.0)

    def test_grant_rate_one(self):
        ev = PermissionEvaluation(agent_name="a", granted=["p1"])
        self.assertAlmostEqual(ev.grant_rate(), 1.0)

    def test_grant_rate_empty(self):
        ev = PermissionEvaluation(agent_name="a")
        self.assertAlmostEqual(ev.grant_rate(), 0.0)

    def test_to_dict(self):
        ev = PermissionEvaluation(
            agent_name="alice",
            granted=["basic_commands"],
            denied=["fleet_broadcast"],
            trust_scores={"composite": 0.5},
        )
        d = ev.to_dict()
        self.assertEqual(d["agent_name"], "alice")
        self.assertEqual(d["granted"], ["basic_commands"])
        self.assertEqual(d["denied"], ["fleet_broadcast"])
        self.assertIn("trust_scores", d)
        self.assertIn("total_permissions", d)
        self.assertIn("grant_rate", d)

    def test_to_dict_sorted(self):
        ev = PermissionEvaluation(
            agent_name="a",
            granted=["zebra", "alpha", "beta"],
            denied=["delta", "gamma"],
            revoked=["epsilon", "charlie"],
        )
        d = ev.to_dict()
        self.assertEqual(d["granted"], ["alpha", "beta", "zebra"])
        self.assertEqual(d["denied"], ["delta", "gamma"])
        self.assertEqual(d["revoked"], ["charlie", "epsilon"])

    def test_from_dict_roundtrip(self):
        ev = PermissionEvaluation(
            agent_name="alice",
            granted=["p1"],
            denied=["p2"],
            revoked=["p3"],
            trust_scores={"composite": 0.7},
        )
        d = ev.to_dict()
        ev2 = PermissionEvaluation.from_dict(d)
        self.assertEqual(ev2.agent_name, "alice")
        self.assertEqual(ev2.granted, ["p1"])
        self.assertEqual(ev2.denied, ["p2"])
        self.assertEqual(ev2.revoked, ["p3"])
        self.assertEqual(ev2.trust_scores["composite"], 0.7)

    def test_from_dict_minimal(self):
        ev = PermissionEvaluation.from_dict({"agent_name": "bob"})
        self.assertEqual(ev.agent_name, "bob")
        self.assertEqual(ev.granted, [])
        self.assertEqual(ev.denied, [])
        self.assertEqual(ev.revoked, [])
        self.assertEqual(ev.trust_scores, {})


# ═══════════════════════════════════════════════════════════════════════════
# 5. SyncResult
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncResult(TestCase):
    def test_default_construction(self):
        sr = SyncResult(agent_name="alice")
        self.assertEqual(sr.agent_name, "alice")
        self.assertEqual(sr.granted_count, 0)
        self.assertEqual(sr.revoked_count, 0)
        self.assertEqual(sr.unchanged_count, 0)
        self.assertEqual(sr.details, [])

    def test_construction_with_values(self):
        sr = SyncResult(
            agent_name="alice",
            granted_count=3,
            revoked_count=1,
            unchanged_count=10,
            details=[{"action": "granted", "permission": "p1"}],
        )
        self.assertEqual(sr.granted_count, 3)
        self.assertEqual(sr.revoked_count, 1)

    def test_total_changes(self):
        sr = SyncResult(agent_name="a", granted_count=5, revoked_count=2)
        self.assertEqual(sr.total_changes(), 7)

    def test_total_changes_zero(self):
        sr = SyncResult(agent_name="a")
        self.assertEqual(sr.total_changes(), 0)

    def test_to_dict(self):
        sr = SyncResult(
            agent_name="alice",
            granted_count=2,
            revoked_count=1,
            unchanged_count=5,
        )
        d = sr.to_dict()
        self.assertEqual(d["agent_name"], "alice")
        self.assertEqual(d["granted_count"], 2)
        self.assertEqual(d["revoked_count"], 1)
        self.assertEqual(d["unchanged_count"], 5)
        self.assertEqual(d["total_changes"], 3)
        self.assertEqual(d["details"], [])

    def test_to_dict_with_details(self):
        sr = SyncResult(
            agent_name="a",
            details=[{"action": "granted", "permission": "p1"}],
        )
        d = sr.to_dict()
        self.assertEqual(len(d["details"]), 1)

    def test_from_dict_roundtrip(self):
        sr = SyncResult(
            agent_name="alice",
            granted_count=3,
            revoked_count=2,
            unchanged_count=7,
            details=[{"action": "revoked", "permission": "p2"}],
        )
        d = sr.to_dict()
        sr2 = SyncResult.from_dict(d)
        self.assertEqual(sr2.agent_name, "alice")
        self.assertEqual(sr2.granted_count, 3)
        self.assertEqual(sr2.revoked_count, 2)
        self.assertEqual(sr2.unchanged_count, 7)
        self.assertEqual(len(sr2.details), 1)

    def test_from_dict_minimal(self):
        sr = SyncResult.from_dict({"agent_name": "bob"})
        self.assertEqual(sr.agent_name, "bob")
        self.assertEqual(sr.granted_count, 0)


# ═══════════════════════════════════════════════════════════════════════════
# 6. TrustPermissionBridge — Construction
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeConstruction(TestCase):
    def test_default_construction(self):
        bridge = TrustPermissionBridge()
        self.assertIsNone(bridge.trust_engine)
        self.assertIsNone(bridge.permission_field)
        self.assertIsInstance(bridge.config, TrustPermissionConfig)

    def test_construction_with_config(self):
        config = TrustPermissionConfig(default_threshold=0.5)
        bridge = TrustPermissionBridge(config=config)
        self.assertEqual(bridge.config.default_threshold, 0.5)

    def test_construction_with_engines(self):
        te = make_mock_trust_engine(0.8)
        pf = make_mock_permission_field()
        bridge = TrustPermissionBridge(trust_engine=te, permission_field=pf)
        self.assertIsNotNone(bridge.trust_engine)
        self.assertIsNotNone(bridge.permission_field)

    def test_initial_state_empty(self):
        bridge = TrustPermissionBridge()
        self.assertEqual(bridge._grant_timestamps, {})
        self.assertEqual(bridge._last_known_permissions, {})


# ═══════════════════════════════════════════════════════════════════════════
# 7. TrustPermissionBridge — Threshold Management
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeThresholdManagement(TestCase):
    def setUp(self):
        self.bridge = make_bridge(composite_trust=0.5)

    def test_add_threshold(self):
        self.bridge.add_threshold("custom_perm", 0.4)
        self.assertEqual(self.bridge.get_permission_trust_requirement("custom_perm"), 0.4)

    def test_add_threshold_updates_existing(self):
        self.bridge.add_threshold("basic_commands", 0.2)
        self.assertEqual(self.bridge.get_permission_trust_requirement("basic_commands"), 0.2)

    def test_add_threshold_negative_raises(self):
        with self.assertRaises(ValueError):
            self.bridge.add_threshold("bad", -0.1)

    def test_add_threshold_over_one_raises(self):
        with self.assertRaises(ValueError):
            self.bridge.add_threshold("bad", 1.5)

    def test_add_threshold_exactly_zero_ok(self):
        self.bridge.add_threshold("free_perm", 0.0)
        self.assertEqual(self.bridge.get_permission_trust_requirement("free_perm"), 0.0)

    def test_add_threshold_exactly_one_ok(self):
        self.bridge.add_threshold("max_perm", 1.0)
        self.assertEqual(self.bridge.get_permission_trust_requirement("max_perm"), 1.0)

    def test_remove_threshold(self):
        self.bridge.add_threshold("temp_perm", 0.5)
        self.bridge.remove_threshold("temp_perm")
        # Falls back to default
        self.assertEqual(self.bridge.get_permission_trust_requirement("temp_perm"), 0.3)

    def test_remove_nonexistent_threshold(self):
        self.bridge.remove_threshold("nonexistent")  # Should not crash

    def test_get_permission_trust_requirement_existing(self):
        req = self.bridge.get_permission_trust_requirement("basic_commands")
        self.assertEqual(req, 0.1)

    def test_get_permission_trust_requirement_missing(self):
        req = self.bridge.get_permission_trust_requirement("nonexistent")
        self.assertEqual(req, 0.3)

    def test_list_all_permissions(self):
        perms = self.bridge.list_all_permissions()
        self.assertIsInstance(perms, list)
        self.assertGreaterEqual(len(perms), 10)
        # Should be sorted
        self.assertEqual(perms, sorted(perms))

    def test_list_permissions_for_trust_zero(self):
        perms = self.bridge.list_permissions_for_trust(0.0)
        # Only 0-threshold permissions
        self.assertEqual(perms, [])

    def test_list_permissions_for_trust_low(self):
        perms = self.bridge.list_permissions_for_trust(0.15)
        self.assertIn("basic_commands", perms)
        self.assertNotIn("room_creation", perms)

    def test_list_permissions_for_trust_medium(self):
        perms = self.bridge.list_permissions_for_trust(0.5)
        self.assertIn("basic_commands", perms)
        self.assertIn("room_creation", perms)
        self.assertIn("cartridge_loading", perms)
        self.assertNotIn("fleet_broadcast", perms)

    def test_list_permissions_for_trust_high(self):
        perms = self.bridge.list_permissions_for_trust(0.95)
        self.assertIn("basic_commands", perms)
        self.assertIn("permission_granting", perms)
        self.assertIn("emergency_powers", perms)

    def test_list_permissions_for_trust_exactly_at_threshold(self):
        perms = self.bridge.list_permissions_for_trust(0.3)
        self.assertIn("room_creation", perms)

    def test_list_permissions_for_trust_just_below(self):
        perms = self.bridge.list_permissions_for_trust(0.299)
        self.assertNotIn("room_creation", perms)


# ═══════════════════════════════════════════════════════════════════════════
# 8. TrustPermissionBridge — evaluate_permissions
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeEvaluatePermissions(TestCase):
    def setUp(self):
        self.bridge = make_bridge(composite_trust=0.5)

    def test_evaluate_returns_permission_evaluation(self):
        ev = self.bridge.evaluate_permissions("alice")
        self.assertIsInstance(ev, PermissionEvaluation)

    def test_evaluate_agent_name(self):
        ev = self.bridge.evaluate_permissions("alice")
        self.assertEqual(ev.agent_name, "alice")

    def test_evaluate_trust_scores_has_composite(self):
        ev = self.bridge.evaluate_permissions("alice")
        self.assertIn("composite", ev.trust_scores)

    def test_evaluate_composite_value(self):
        ev = self.bridge.evaluate_permissions("alice")
        self.assertAlmostEqual(ev.trust_scores["composite"], 0.5)

    def test_evaluate_granted_at_0_5_trust(self):
        ev = self.bridge.evaluate_permissions("alice")
        # basic_commands (0.1), room_creation (0.3), agent_communication (0.3)
        # should be granted
        self.assertIn("basic_commands", ev.granted)
        self.assertIn("room_creation", ev.granted)
        self.assertIn("agent_communication", ev.granted)

    def test_evaluate_denied_at_0_5_trust(self):
        ev = self.bridge.evaluate_permissions("alice")
        # governance_voting (0.8), permission_granting (0.9) should be denied
        self.assertIn("governance_voting", ev.denied)
        self.assertIn("permission_granting", ev.denied)

    def test_evaluate_granted_plus_denied_equals_all(self):
        ev = self.bridge.evaluate_permissions("alice")
        total_perms = len(self.bridge.list_all_permissions())
        self.assertEqual(len(ev.granted) + len(ev.denied), total_perms)

    def test_evaluate_no_revocation_first_time(self):
        ev = self.bridge.evaluate_permissions("alice")
        self.assertEqual(ev.revoked, [])

    def test_evaluate_low_trust_denies_most(self):
        bridge = make_bridge(composite_trust=0.05)
        ev = bridge.evaluate_permissions("alice")
        # Only basic_commands (0.1) should still be denied at 0.05
        self.assertNotIn("room_creation", ev.granted)
        self.assertEqual(len(ev.granted), 0)

    def test_evaluate_high_trust_grants_most(self):
        bridge = make_bridge(composite_trust=0.95)
        ev = bridge.evaluate_permissions("alice")
        # Should grant everything
        self.assertEqual(len(ev.denied), 0)
        self.assertGreaterEqual(len(ev.granted), 10)

    def test_evaluate_zero_trust(self):
        bridge = make_bridge(composite_trust=0.0)
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(len(ev.granted), 0)
        self.assertGreaterEqual(len(ev.denied), 10)

    def test_evaluate_one_trust(self):
        bridge = make_bridge(composite_trust=1.0)
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(len(ev.denied), 0)

    def test_evaluate_no_trust_engine(self):
        bridge = TrustPermissionBridge()
        ev = bridge.evaluate_permissions("unknown_agent")
        # No engine → composite trust = 0.0
        self.assertEqual(len(ev.granted), 0)

    def test_evaluate_trust_scores_has_dimensions(self):
        bridge = make_bridge(composite_trust=0.5)
        ev = bridge.evaluate_permissions("alice")
        self.assertIn("code_quality", ev.trust_scores)

    def test_evaluate_revocation_detected(self):
        bridge = make_bridge(composite_trust=0.9)
        # First eval: grants everything
        ev1 = bridge.evaluate_permissions("alice")
        # Now lower trust
        bridge.trust_engine.composite_trust.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.1,
            "dimensions": {d: 0.1 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        ev2 = bridge.evaluate_permissions("alice")
        # Should have revoked permissions
        self.assertGreater(len(ev2.revoked), 0)
        # Revoked should be permissions that were granted but now denied
        revoked_set = set(ev2.revoked)
        for p in ev2.revoked:
            self.assertIn(p, ev1.granted)
            self.assertNotIn(p, ev2.granted)

    def test_evaluate_no_revocation_when_trust_increases(self):
        bridge = make_bridge(composite_trust=0.3)
        bridge.evaluate_permissions("alice")
        bridge.trust_engine.composite_trust.return_value = 0.9
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.9
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.9,
            "dimensions": {d: 0.9 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(ev.revoked, [])

    def test_evaluate_weighted(self):
        bridge = make_bridge(composite_trust=0.5)
        ev = bridge.evaluate_permissions_weighted("alice")
        self.assertIsInstance(ev, PermissionEvaluation)
        self.assertIsInstance(ev.granted, list)
        self.assertIsInstance(ev.denied, list)
        self.assertIsInstance(ev.revoked, list)
        # Trust scores should contain composite
        self.assertIn("composite", ev.trust_scores)


# ═══════════════════════════════════════════════════════════════════════════
# 9. TrustPermissionBridge — sync_trust_to_permissions
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeSync(TestCase):
    def setUp(self):
        self.bridge = make_bridge(composite_trust=0.5, with_pf=True)

    def test_sync_returns_sync_result(self):
        sr = self.bridge.sync_trust_to_permissions("alice")
        self.assertIsInstance(sr, SyncResult)

    def test_sync_agent_name(self):
        sr = self.bridge.sync_trust_to_permissions("alice")
        self.assertEqual(sr.agent_name, "alice")

    def test_sync_first_time_grants_new(self):
        sr = self.bridge.sync_trust_to_permissions("alice")
        # Should grant permissions that agent qualifies for
        self.assertGreater(sr.granted_count, 0)

    def test_sync_second_time_no_change(self):
        self.bridge.sync_trust_to_permissions("alice")
        sr = self.bridge.sync_trust_to_permissions("alice")
        # Already tracked, so no new grants
        self.assertEqual(sr.granted_count, 0)
        self.assertEqual(sr.revoked_count, 0)
        self.assertGreater(sr.unchanged_count, 0)

    def test_sync_revoke_after_trust_decay(self):
        # First: grant at high trust
        bridge = make_bridge(composite_trust=0.9, with_pf=True)
        bridge.sync_trust_to_permissions("alice")

        # Second: lower trust (simulate decay beyond grace)
        bridge.trust_engine.composite_trust.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.1,
            "dimensions": {d: 0.1 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        # Set grant timestamps to be old (past grace period)
        old_time = time.time() - 100000  # ~27 hours ago
        for perm in bridge._grant_timestamps.get("alice", {}):
            bridge._grant_timestamps["alice"][perm] = old_time

        sr = bridge.sync_trust_to_permissions("alice")
        self.assertGreater(sr.revoked_count, 0)

    def test_sync_grace_period_prevents_revoke(self):
        bridge = make_bridge(composite_trust=0.9, with_pf=True)
        bridge.sync_trust_to_permissions("alice")

        # Lower trust but still within grace period
        bridge.trust_engine.composite_trust.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.1,
            "dimensions": {d: 0.1 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        # Grant timestamps are very recent
        recent_time = time.time() - 100  # 100 seconds ago
        for perm in bridge._grant_timestamps.get("alice", {}):
            bridge._grant_timestamps["alice"][perm] = recent_time

        sr = bridge.sync_trust_to_permissions("alice")
        # Should be in grace period, no revocations
        self.assertEqual(sr.revoked_count, 0)
        # Should have grace period details
        grace_details = [d for d in sr.details if d.get("action") == "grace_period"]
        self.assertGreater(len(grace_details), 0)

    def test_sync_auto_grant_disabled(self):
        bridge = make_bridge(
            composite_trust=0.5,
            config=TrustPermissionConfig(auto_grant_enabled=False),
            with_pf=True,
        )
        sr = bridge.sync_trust_to_permissions("alice")
        self.assertEqual(sr.granted_count, 0)

    def test_sync_auto_revoke_disabled(self):
        bridge = make_bridge(composite_trust=0.9, with_pf=True)
        bridge.sync_trust_to_permissions("alice")

        bridge.trust_engine.composite_trust.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.1,
            "dimensions": {d: 0.1 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        bridge.config.auto_revoke_enabled = False
        old_time = time.time() - 100000
        for perm in bridge._grant_timestamps.get("alice", {}):
            bridge._grant_timestamps["alice"][perm] = old_time

        sr = bridge.sync_trust_to_permissions("alice")
        self.assertEqual(sr.revoked_count, 0)

    def test_sync_without_permission_field(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=False)
        sr = bridge.sync_trust_to_permissions("alice")
        # Without permission field, all are unchanged
        self.assertEqual(sr.granted_count, 0)
        self.assertEqual(sr.revoked_count, 0)

    def test_sync_details_have_action_field(self):
        sr = self.bridge.sync_trust_to_permissions("alice")
        for detail in sr.details:
            self.assertIn("action", detail)

    def test_sync_granted_details_have_permission(self):
        sr = self.bridge.sync_trust_to_permissions("alice")
        for detail in sr.details:
            if detail["action"] == "granted":
                self.assertIn("permission", detail)
                self.assertIn("trust", detail)
                self.assertIn("threshold", detail)

    def test_sync_custom_grace_period(self):
        config = TrustPermissionConfig(decay_grace_period=0.0)
        bridge = make_bridge(composite_trust=0.9, config=config, with_pf=True)
        bridge.sync_trust_to_permissions("alice")

        bridge.trust_engine.composite_trust.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.1
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.1,
            "dimensions": {d: 0.1 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        # With 0 grace period, should revoke immediately
        sr = bridge.sync_trust_to_permissions("alice")
        self.assertGreater(sr.revoked_count, 0)


# ═══════════════════════════════════════════════════════════════════════════
# 10. TrustPermissionBridge — Trust Gap
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeTrustGap(TestCase):
    def test_gap_positive_when_below_threshold(self):
        bridge = make_bridge(composite_trust=0.3)
        gap = bridge.get_agent_trust_gap("alice", "fleet_broadcast")
        # fleet_broadcast threshold = 0.7, trust = 0.3, gap = 0.4
        self.assertAlmostEqual(gap, 0.4, places=2)

    def test_gap_zero_when_at_threshold(self):
        bridge = make_bridge(composite_trust=0.7)
        gap = bridge.get_agent_trust_gap("alice", "fleet_broadcast")
        self.assertAlmostEqual(gap, 0.0, places=2)

    def test_gap_zero_when_above_threshold(self):
        bridge = make_bridge(composite_trust=0.9)
        gap = bridge.get_agent_trust_gap("alice", "fleet_broadcast")
        self.assertAlmostEqual(gap, 0.0, places=2)

    def test_gap_exact(self):
        bridge = make_bridge(composite_trust=0.25)
        gap = bridge.get_agent_trust_gap("alice", "room_creation")
        # room_creation = 0.3, gap = 0.05
        self.assertAlmostEqual(gap, 0.05, places=2)

    def test_gap_for_nonexistent_permission(self):
        bridge = make_bridge(composite_trust=0.1)
        gap = bridge.get_agent_trust_gap("alice", "nonexistent")
        # Uses default threshold 0.3
        self.assertAlmostEqual(gap, 0.2, places=2)

    def test_gap_no_trust_engine(self):
        bridge = TrustPermissionBridge()
        gap = bridge.get_agent_trust_gap("unknown", "basic_commands")
        # No engine → composite = 0.0 for unknown, threshold = 0.1
        self.assertAlmostEqual(gap, 0.1, places=2)

    def test_gap_weighted(self):
        bridge = make_bridge(composite_trust=0.3)
        gap = bridge.get_agent_trust_gap_weighted("alice", "fleet_broadcast")
        self.assertGreaterEqual(gap, 0.0)

    def test_gap_batch(self):
        bridge = make_bridge(composite_trust=0.4)
        gaps = bridge.batch_trust_gaps(
            ["alice", "bob", "charlie"], "governance_voting"
        )
        self.assertEqual(len(gaps), 3)
        for name, gap in gaps.items():
            self.assertAlmostEqual(gap, 0.4, places=2)

    def test_gap_batch_empty(self):
        bridge = make_bridge(composite_trust=0.5)
        gaps = bridge.batch_trust_gaps([], "basic_commands")
        self.assertEqual(gaps, {})


# ═══════════════════════════════════════════════════════════════════════════
# 11. TrustPermissionBridge — Batch Operations
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeBatch(TestCase):
    def setUp(self):
        self.bridge = make_bridge(composite_trust=0.5)

    def test_batch_evaluate(self):
        results = self.bridge.batch_evaluate(["alice", "bob", "charlie"])
        self.assertEqual(len(results), 3)
        for name, ev in results.items():
            self.assertIsInstance(ev, PermissionEvaluation)
            self.assertEqual(ev.agent_name, name)

    def test_batch_evaluate_empty(self):
        results = self.bridge.batch_evaluate([])
        self.assertEqual(results, {})

    def test_batch_evaluate_single(self):
        results = self.bridge.batch_evaluate(["alice"])
        self.assertEqual(len(results), 1)
        self.assertIn("alice", results)

    def test_batch_sync(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        results = bridge.batch_sync(["alice", "bob"])
        self.assertEqual(len(results), 2)
        for name, sr in results.items():
            self.assertIsInstance(sr, SyncResult)

    def test_batch_sync_empty(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        results = bridge.batch_sync([])
        self.assertEqual(results, {})


# ═══════════════════════════════════════════════════════════════════════════
# 12. TrustPermissionBridge — Grace Period
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeGracePeriod(TestCase):
    def test_grant_time_none_initially(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        t = bridge.get_grant_time("alice", "basic_commands")
        self.assertIsNone(t)

    def test_grant_time_set_after_sync(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        t = bridge.get_grant_time("alice", "basic_commands")
        self.assertIsNotNone(t)
        self.assertGreater(t, 0)

    def test_is_in_grace_period_true_initially(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        self.assertTrue(bridge.is_in_grace_period("alice", "basic_commands"))

    def test_is_in_grace_period_false_never_granted(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        self.assertFalse(bridge.is_in_grace_period("alice", "nonexistent"))

    def test_remaining_grace_positive(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        remaining = bridge.remaining_grace("alice", "basic_commands")
        self.assertGreater(remaining, 0)

    def test_remaining_grace_zero_never_granted(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        self.assertAlmostEqual(bridge.remaining_grace("alice", "nonexistent"), 0.0)

    def test_remaining_grace_decreases(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        r1 = bridge.remaining_grace("alice", "basic_commands")
        # Simulate passage of time by setting old timestamp
        perm = "basic_commands"
        old = bridge._grant_timestamps["alice"][perm] - 3600
        bridge._grant_timestamps["alice"][perm] = old
        r2 = bridge.remaining_grace("alice", "basic_commands")
        self.assertAlmostEqual(r1 - r2, 3600.0, places=0)

    def test_set_grace_period(self):
        bridge = make_bridge(composite_trust=0.5)
        bridge.set_grace_period(7200.0)
        self.assertEqual(bridge.config.decay_grace_period, 7200.0)

    def test_set_grace_period_negative_raises(self):
        bridge = make_bridge(composite_trust=0.5)
        with self.assertRaises(ValueError):
            bridge.set_grace_period(-1.0)

    def test_set_grace_period_zero_ok(self):
        bridge = make_bridge(composite_trust=0.5)
        bridge.set_grace_period(0.0)
        self.assertEqual(bridge.config.decay_grace_period, 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# 13. TrustPermissionBridge — Serialization
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeSerialization(TestCase):
    def test_to_dict(self):
        bridge = make_bridge(composite_trust=0.5)
        d = bridge.to_dict()
        self.assertIn("config", d)
        self.assertIn("grant_timestamps", d)
        self.assertIn("last_known_permissions", d)

    def test_to_dict_config(self):
        bridge = make_bridge(composite_trust=0.5)
        d = bridge.to_dict()
        self.assertIn("trust_thresholds", d["config"])
        self.assertIn("default_threshold", d["config"])

    def test_to_dict_after_sync(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        d = bridge.to_dict()
        self.assertIn("alice", d["grant_timestamps"])
        self.assertIn("alice", d["last_known_permissions"])

    def test_from_dict_roundtrip(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        bridge.sync_trust_to_permissions("bob")
        bridge.add_threshold("custom", 0.42)

        d = bridge.to_dict()
        bridge2 = TrustPermissionBridge.from_dict(d)

        self.assertEqual(bridge2.config.default_threshold, bridge.config.default_threshold)
        self.assertIn("alice", bridge2._last_known_permissions)
        self.assertIn("bob", bridge2._last_known_permissions)
        self.assertEqual(bridge2.get_permission_trust_requirement("custom"), 0.42)

    def test_from_dict_preserves_grant_timestamps(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")

        d = bridge.to_dict()
        bridge2 = TrustPermissionBridge.from_dict(d)

        self.assertIn("alice", bridge2._grant_timestamps)
        # Timestamps should be float
        for perm, ts in bridge2._grant_timestamps["alice"].items():
            self.assertIsInstance(ts, float)
            self.assertGreater(ts, 0)

    def test_from_dict_empty(self):
        bridge = TrustPermissionBridge.from_dict({})
        self.assertIsInstance(bridge.config, TrustPermissionConfig)
        self.assertEqual(bridge._grant_timestamps, {})
        self.assertEqual(bridge._last_known_permissions, {})

    def test_from_dict_with_engines(self):
        te = make_mock_trust_engine(0.7)
        pf = make_mock_permission_field()
        bridge = TrustPermissionBridge.from_dict(
            {"config": {"default_threshold": 0.4}},
            trust_engine=te,
            permission_field=pf,
        )
        self.assertIsNotNone(bridge.trust_engine)
        self.assertIsNotNone(bridge.permission_field)
        self.assertEqual(bridge.config.default_threshold, 0.4)

    def test_json_serializable(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        d = bridge.to_dict()
        # Should be JSON-serializable
        json_str = json.dumps(d)
        self.assertIsInstance(json_str, str)
        self.assertGreater(len(json_str), 0)

    def test_json_roundtrip(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        bridge.add_threshold("extra", 0.55)
        json_str = json.dumps(bridge.to_dict())
        data = json.loads(json_str)
        bridge2 = TrustPermissionBridge.from_dict(data)
        self.assertEqual(bridge2.get_permission_trust_requirement("extra"), 0.55)
        self.assertIn("alice", bridge2._last_known_permissions)

    def test_last_known_permissions_are_sets_after_from_dict(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        d = bridge.to_dict()
        bridge2 = TrustPermissionBridge.from_dict(d)
        self.assertIsInstance(bridge2._last_known_permissions["alice"], set)


# ═══════════════════════════════════════════════════════════════════════════
# 14. TrustPermissionBridge — Summary / Reporting
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeSummary(TestCase):
    def test_summary_keys(self):
        bridge = make_bridge(composite_trust=0.5)
        s = bridge.summary()
        self.assertIn("total_permissions", s)
        self.assertIn("total_agents_tracked", s)
        self.assertIn("auto_grant", s)
        self.assertIn("auto_revoke", s)
        self.assertIn("grace_period_hours", s)
        self.assertIn("default_threshold", s)
        self.assertIn("min_threshold", s)
        self.assertIn("max_threshold", s)

    def test_summary_values(self):
        bridge = make_bridge(composite_trust=0.5)
        s = bridge.summary()
        self.assertEqual(s["total_permissions"], len(DEFAULT_PERMISSION_THRESHOLDS))
        self.assertTrue(s["auto_grant"])
        self.assertTrue(s["auto_revoke"])
        self.assertAlmostEqual(s["grace_period_hours"], 24.0)

    def test_summary_after_tracking(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        s = bridge.summary()
        self.assertEqual(s["total_agents_tracked"], 1)

    def test_agent_summary_keys(self):
        bridge = make_bridge(composite_trust=0.5)
        s = bridge.agent_summary("alice")
        self.assertIn("agent_name", s)
        self.assertIn("composite_trust", s)
        self.assertIn("granted_count", s)
        self.assertIn("denied_count", s)
        self.assertIn("revoked_count", s)
        self.assertIn("granted_permissions", s)
        self.assertIn("trust_gaps", s)
        self.assertIn("grant_rate", s)

    def test_agent_summary_values(self):
        bridge = make_bridge(composite_trust=0.5)
        s = bridge.agent_summary("alice")
        self.assertEqual(s["agent_name"], "alice")
        self.assertAlmostEqual(s["composite_trust"], 0.5)
        self.assertGreater(s["granted_count"], 0)
        self.assertGreater(s["denied_count"], 0)

    def test_agent_summary_trust_gaps(self):
        bridge = make_bridge(composite_trust=0.3)
        s = bridge.agent_summary("alice")
        gaps = s["trust_gaps"]
        self.assertIsInstance(gaps, dict)
        # Should have gaps for denied permissions
        self.assertGreater(len(gaps), 0)
        for perm, gap in gaps.items():
            self.assertGreater(gap, 0.0)

    def test_compare_agents_keys(self):
        bridge = make_bridge(composite_trust=0.5)
        s = bridge.compare_agents("alice", "bob")
        self.assertIn("agent_a", s)
        self.assertIn("agent_b", s)
        self.assertIn("trust_a", s)
        self.assertIn("trust_b", s)
        self.assertIn("shared", s)
        self.assertIn("only_a", s)
        self.assertIn("only_b", s)
        self.assertIn("permission_distance", s)

    def test_compare_agents_same_trust(self):
        bridge = make_bridge(composite_trust=0.5)
        s = bridge.compare_agents("alice", "bob")
        # Same trust → same permissions → shared = all granted, none exclusive
        self.assertGreater(len(s["shared"]), 0)
        self.assertEqual(s["only_a"], [])
        self.assertEqual(s["only_b"], [])
        self.assertEqual(s["permission_distance"], 0)

    def test_compare_agents_different_trust(self):
        bridge = make_bridge(composite_trust=0.5)
        # Override for bob
        bridge.trust_engine.composite_trust.side_effect = lambda name: 0.9 if name == "bob" else 0.5
        bridge.trust_engine.get_profile.side_effect = lambda name: make_mock_trust_engine(
            0.9 if name == "bob" else 0.5
        ).get_profile(name)
        s = bridge.compare_agents("alice", "bob")
        self.assertGreater(s["permission_distance"], 0)
        # Bob should have more permissions
        self.assertGreater(len(s["only_b"]), 0)


# ═══════════════════════════════════════════════════════════════════════════
# 15. Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases(TestCase):
    def test_empty_config_thresholds(self):
        config = TrustPermissionConfig()
        config.trust_thresholds = {}
        bridge = make_bridge(composite_trust=0.5, config=config)
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(ev.granted, [])
        self.assertEqual(ev.denied, [])

    def test_all_permissions_zero_threshold(self):
        config = TrustPermissionConfig()
        config.trust_thresholds = {"p1": 0.0, "p2": 0.0}
        bridge = make_bridge(composite_trust=0.0, config=config)
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(len(ev.granted), 2)
        self.assertEqual(len(ev.denied), 0)

    def test_all_permissions_max_threshold(self):
        config = TrustPermissionConfig()
        config.trust_thresholds = {"p1": 1.0, "p2": 1.0}
        bridge = make_bridge(composite_trust=0.99, config=config)
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(len(ev.granted), 0)
        self.assertEqual(len(ev.denied), 2)

    def test_trust_engine_exception_handling(self):
        bridge = TrustPermissionBridge()
        engine = MagicMock()
        engine.composite_trust.side_effect = KeyError("no profile")
        bridge.trust_engine = engine
        ev = bridge.evaluate_permissions("bad_agent")
        # Should handle gracefully
        self.assertEqual(ev.agent_name, "bad_agent")

    def test_trust_engine_none_composite(self):
        bridge = TrustPermissionBridge()
        engine = MagicMock()
        engine.composite_trust.return_value = None
        bridge.trust_engine = engine
        # None from engine should be handled gracefully
        ev = bridge.evaluate_permissions("alice")
        self.assertIsInstance(ev, PermissionEvaluation)
        self.assertEqual(ev.agent_name, "alice")

    def test_very_large_threshold_count(self):
        config = TrustPermissionConfig()
        config.trust_thresholds = {f"perm_{i}": 0.01 for i in range(1000)}
        bridge = make_bridge(composite_trust=0.5, config=config)
        ev = bridge.evaluate_permissions("alice")
        self.assertEqual(len(ev.granted), 1000)

    def test_sync_multiple_agents_independently(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        bridge.sync_trust_to_permissions("alice")
        bridge.sync_trust_to_permissions("bob")
        self.assertIn("alice", bridge._grant_timestamps)
        self.assertIn("bob", bridge._grant_timestamps)
        # They should have independent timestamps
        self.assertNotEqual(
            bridge._grant_timestamps["alice"],
            bridge._grant_timestamps["bob"],
        )

    def test_unicode_agent_names(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        sr = bridge.sync_trust_to_permissions("🤖_agent")
        self.assertEqual(sr.agent_name, "🤖_agent")

    def test_very_long_agent_name(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        long_name = "a" * 1000
        sr = bridge.sync_trust_to_permissions(long_name)
        self.assertEqual(sr.agent_name, long_name)

    def test_empty_agent_name(self):
        bridge = make_bridge(composite_trust=0.5, with_pf=True)
        sr = bridge.sync_trust_to_permissions("")
        self.assertEqual(sr.agent_name, "")

    def test_floating_point_precision(self):
        bridge = make_bridge(composite_trust=0.2999999999)
        ev = bridge.evaluate_permissions("alice")
        # room_creation threshold is 0.3 — 0.2999... < 0.3 so denied
        self.assertNotIn("room_creation", ev.granted)

    def test_exact_boundary_trust(self):
        bridge = make_bridge(composite_trust=0.3)
        ev = bridge.evaluate_permissions("alice")
        # Exactly at threshold → should be granted
        self.assertIn("room_creation", ev.granted)
        self.assertIn("agent_communication", ev.granted)

    def test_multiple_add_threshold_calls(self):
        bridge = make_bridge(composite_trust=0.5)
        bridge.add_threshold("p1", 0.1)
        bridge.add_threshold("p2", 0.2)
        bridge.add_threshold("p3", 0.3)
        perms = bridge.list_all_permissions()
        self.assertIn("p1", perms)
        self.assertIn("p2", perms)
        self.assertIn("p3", perms)

    def test_permission_evaluation_immutability(self):
        ev = PermissionEvaluation(
            agent_name="a",
            granted=["p1"],
            denied=["p2"],
        )
        granted_copy = list(ev.granted)
        ev.granted.append("p3")
        # Original reference shouldn't affect copy
        self.assertEqual(len(granted_copy), 1)

    def test_sync_result_details_mutation(self):
        sr = SyncResult(agent_name="a", details=[])
        sr.details.append({"action": "test"})
        self.assertEqual(len(sr.details), 1)

    def test_config_default_threshold_negative(self):
        config = TrustPermissionConfig(default_threshold=-0.1)
        # Should not crash; just means everything passes
        self.assertEqual(config.get_threshold("nonexistent"), -0.1)

    def test_bridge_no_config_arg_uses_default(self):
        bridge = TrustPermissionBridge(config=None)
        self.assertIsNotNone(bridge.config)
        self.assertIsInstance(bridge.config, TrustPermissionConfig)

    def test_weighted_trust_no_dimensions_weight(self):
        config = TrustPermissionConfig()
        config.dimensions_weight = {}  # Empty
        bridge = make_bridge(composite_trust=0.5, config=config)
        gap = bridge.get_agent_trust_gap_weighted("alice", "basic_commands")
        self.assertGreaterEqual(gap, 0.0)


# ═══════════════════════════════════════════════════════════════════════════
# 16. Integration Scenarios
# ═══════════════════════════════════════════════════════════════════════════

class TestIntegrationScenarios(TestCase):
    def test_new_agent_journey(self):
        """Simulate a new agent gaining trust over time."""
        bridge = make_bridge(composite_trust=0.05, with_pf=True)

        # Level 1: Very low trust — no permissions
        ev1 = bridge.evaluate_permissions("newbie")
        self.assertEqual(len(ev1.granted), 0)

        # Level 2: Basic trust earned
        bridge.trust_engine.composite_trust.return_value = 0.2
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.2
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.2,
            "dimensions": {d: 0.2 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        ev2 = bridge.evaluate_permissions("newbie")
        self.assertIn("basic_commands", ev2.granted)
        self.assertNotIn("room_creation", ev2.granted)

        # Level 3: Moderate trust
        bridge.trust_engine.composite_trust.return_value = 0.5
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.5
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.5,
            "dimensions": {d: 0.5 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        ev3 = bridge.evaluate_permissions("newbie")
        self.assertIn("cartridge_loading", ev3.granted)
        self.assertNotIn("fleet_broadcast", ev3.granted)

        # Level 4: High trust (0.95 for emergency_powers which requires 0.95)
        bridge.trust_engine.composite_trust.return_value = 0.95
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.95
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.95,
            "dimensions": {d: 0.95 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        ev4 = bridge.evaluate_permissions("newbie")
        self.assertIn("permission_granting", ev4.granted)
        self.assertIn("emergency_powers", ev4.granted)

    def test_trust_decay_with_grace(self):
        """Simulate trust decay and grace period."""
        config = TrustPermissionConfig(decay_grace_period=86400.0)
        bridge = make_bridge(composite_trust=0.9, config=config, with_pf=True)
        bridge.sync_trust_to_permissions("veteran")

        # Trust decays
        bridge.trust_engine.composite_trust.return_value = 0.2
        bridge.trust_engine.get_profile.return_value.composite.return_value = 0.2
        bridge.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.2,
            "dimensions": {d: 0.2 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }

        # Still in grace period — no revocation
        sr = bridge.sync_trust_to_permissions("veteran")
        self.assertEqual(sr.revoked_count, 0)

        # Move past grace period
        for perm in bridge._grant_timestamps.get("veteran", {}):
            bridge._grant_timestamps["veteran"][perm] = time.time() - 100000

        # Need to reset last_known_permissions so revocation is detected
        bridge._last_known_permissions["veteran"] = set(
            bridge._grant_timestamps["veteran"].keys()
        )

        sr = bridge.sync_trust_to_permissions("veteran")
        self.assertGreater(sr.revoked_count, 0)

    def test_multiple_agents_different_trust_levels(self):
        """Compare permission access across agents at different trust levels."""
        results = {}
        for trust_level, name in [(0.1, "newbie"), (0.5, "regular"), (0.9, "veteran")]:
            bridge = make_bridge(composite_trust=trust_level)
            ev = bridge.evaluate_permissions(name)
            results[name] = len(ev.granted)

        self.assertLess(results["newbie"], results["regular"])
        self.assertLess(results["regular"], results["veteran"])

    def test_full_lifecycle(self):
        """Full lifecycle: create → evaluate → sync → decay → revoke."""
        bridge = make_bridge(composite_trust=0.8, with_pf=True)

        # Evaluate
        ev = bridge.evaluate_permissions("agent_x")
        self.assertGreater(len(ev.granted), 5)

        # Sync
        sr = bridge.sync_trust_to_permissions("agent_x")
        self.assertGreater(sr.granted_count, 0)

        # Serialize
        d = bridge.to_dict()
        self.assertIn("agent_x", d["grant_timestamps"])

        # Restore
        bridge2 = TrustPermissionBridge.from_dict(d, trust_engine=bridge.trust_engine)
        self.assertIn("agent_x", bridge2._last_known_permissions)

        # Decay
        bridge2.trust_engine.composite_trust.return_value = 0.1
        bridge2.trust_engine.get_profile.return_value.composite.return_value = 0.1
        bridge2.trust_engine.get_profile.return_value.summary.return_value = {
            "composite": 0.1,
            "dimensions": {d: 0.1 for d in
                           ["code_quality", "task_completion", "collaboration",
                            "reliability", "innovation"]},
        }
        for perm in bridge2._grant_timestamps.get("agent_x", {}):
            bridge2._grant_timestamps["agent_x"][perm] = time.time() - 100000

        sr2 = bridge2.sync_trust_to_permissions("agent_x")
        self.assertGreater(sr2.revoked_count, 0)

    def test_config_modification_during_operation(self):
        """Changing config mid-operation affects next evaluation."""
        bridge = make_bridge(composite_trust=0.5)

        ev1 = bridge.evaluate_permissions("alice")
        initial_granted = len(ev1.granted)

        # Raise all thresholds
        bridge.config.trust_thresholds = {
            k: 1.0 for k in bridge.config.trust_thresholds
        }

        ev2 = bridge.evaluate_permissions("alice")
        self.assertEqual(len(ev2.granted), 0)
        self.assertGreater(len(ev2.revoked), 0)


if __name__ == "__main__":
    import unittest
    unittest.main()
