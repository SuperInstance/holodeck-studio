#!/usr/bin/env python3
"""
Tests for tile_trust_fusion.py — Tile x Trust Fusion Layer

Covers all components:
1. TileTrustConfig — settings, trust gates, tile-trust weight computation
2. TileTrustAuditEntry — creation, hashing, chain verification, serialization
3. TileTrustProfile — completion tracking, decay, revocation, composite trust
4. TileTrustFusion — trust-gated access, tile-earned trust, discovery,
   fleet propagation, audit trail, serialization
"""

import hashlib
import json
import time
import unittest
from unittest.mock import MagicMock, patch

from tile_trust_fusion import (
    # Constants
    TRUST_GAIN_PER_TILE,
    TRUST_GATE_DEFAULT,
    TRUST_PROPAGATION_FACTOR,
    MAX_TILE_TRUST_BONUS,
    TRUST_DIMENSIONS,
    BASE_TRUST,
    DEFAULT_DECAY_RATE,
    AUDIT_HASH_ALGORITHM,
    DEFAULT_DOMAIN_TRUST_MAP,
    DEFAULT_TILE_TRUST_OVERRIDES,
    # Classes
    TileTrustConfig,
    TileTrustAuditEntry,
    AuditEventType,
    TileTrustProfile,
    TileTrustRecord,
    TileTrustFusion,
    TrustPropagationResult,
    TileDiscoveryResult,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

def _make_mock_tile(tile_id, domain="code", prerequisites=None, tags=None):
    """Create a mock KnowledgeTile-like object."""
    mock = MagicMock()
    mock.id = tile_id
    mock.name = tile_id.replace("_", " ").title()
    mock.domain = MagicMock()
    mock.domain.value = domain
    mock.prerequisites = prerequisites or []
    mock.tags = tags or []
    mock.difficulty = 0.3
    mock.description = f"Mock tile {tile_id}"
    return mock


def _make_mock_graph(tiles_dict):
    """Create a mock TileGraph with the given tiles.

    Args:
        tiles_dict: dict of tile_id -> (domain, prerequisites_list)
    """
    mock = MagicMock()
    mock.tiles = {}
    for tid, (domain, prereqs) in tiles_dict.items():
        mock.tiles[tid] = _make_mock_tile(tid, domain, prereqs)
    return mock


def _make_fusion_with_graph():
    """Create a TileTrustFusion with a simple tile graph."""
    graph = _make_mock_graph({
        "tile_a": ("code", []),
        "tile_b": ("social", ["tile_a"]),
        "tile_c": ("trust", ["tile_a"]),
        "tile_d": ("infrastructure", ["tile_b", "tile_c"]),
        "tile_e": ("creative", []),
        "security_hardening": ("infrastructure", ["tile_d"]),
    })
    fusion = TileTrustFusion(tile_graph=graph)
    return fusion, graph


# ═══════════════════════════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════════════════════════

class TestConstants(unittest.TestCase):
    """Verify module constants match specification."""

    def test_trust_gain_per_tile(self):
        self.assertEqual(TRUST_GAIN_PER_TILE, 0.05)

    def test_trust_gate_default(self):
        self.assertEqual(TRUST_GATE_DEFAULT, 0.3)

    def test_trust_propagation_factor(self):
        self.assertEqual(TRUST_PROPAGATION_FACTOR, 0.5)

    def test_max_tile_trust_bonus(self):
        self.assertEqual(MAX_TILE_TRUST_BONUS, 0.3)

    def test_trust_dimensions(self):
        self.assertIn("competence", TRUST_DIMENSIONS)
        self.assertIn("reliability", TRUST_DIMENSIONS)
        self.assertIn("honesty", TRUST_DIMENSIONS)
        self.assertIn("generosity", TRUST_DIMENSIONS)
        self.assertIn("reciprocity", TRUST_DIMENSIONS)
        self.assertEqual(len(TRUST_DIMENSIONS), 5)

    def test_base_trust(self):
        self.assertEqual(BASE_TRUST, 0.3)

    def test_default_decay_rate(self):
        self.assertEqual(DEFAULT_DECAY_RATE, 0.95)

    def test_audit_hash_algorithm(self):
        self.assertEqual(AUDIT_HASH_ALGORITHM, "sha256")

    def test_default_domain_trust_map_keys(self):
        for domain in ["code", "social", "trust", "creative", "infrastructure"]:
            self.assertIn(domain, DEFAULT_DOMAIN_TRUST_MAP)

    def test_default_tile_trust_overrides(self):
        self.assertIn("security_hardening", DEFAULT_TILE_TRUST_OVERRIDES)


# ═══════════════════════════════════════════════════════════════
# TileTrustConfig Tests
# ═══════════════════════════════════════════════════════════════

class TestTileTrustConfig(unittest.TestCase):
    """Tests for the fusion configuration dataclass."""

    def test_default_creation(self):
        config = TileTrustConfig()
        self.assertEqual(config.trust_gain_per_tile, TRUST_GAIN_PER_TILE)
        self.assertEqual(config.trust_gate_default, TRUST_GATE_DEFAULT)
        self.assertEqual(config.propagation_factor, TRUST_PROPAGATION_FACTOR)
        self.assertEqual(config.max_tile_trust_bonus, MAX_TILE_TRUST_BONUS)
        self.assertEqual(config.decay_rate, DEFAULT_DECAY_RATE)
        self.assertEqual(config.propagation_depth_limit, 3)
        self.assertEqual(config.discovery_trust_weight, 0.3)

    def test_custom_creation(self):
        config = TileTrustConfig(
            trust_gain_per_tile=0.1,
            trust_gate_default=0.5,
            propagation_factor=0.7,
        )
        self.assertEqual(config.trust_gain_per_tile, 0.1)
        self.assertEqual(config.trust_gate_default, 0.5)
        self.assertEqual(config.propagation_factor, 0.7)

    def test_get_trust_gate_default(self):
        config = TileTrustConfig()
        self.assertEqual(config.get_trust_gate("any_tile"), 0.3)

    def test_get_trust_gate_override(self):
        config = TileTrustConfig()
        config.trust_gate_overrides["secret_tile"] = 0.8
        self.assertEqual(config.get_trust_gate("secret_tile"), 0.8)

    def test_set_trust_gate_valid(self):
        config = TileTrustConfig()
        config.set_trust_gate("t1", 0.6)
        self.assertEqual(config.get_trust_gate("t1"), 0.6)

    def test_set_trust_gate_minimum(self):
        config = TileTrustConfig()
        config.set_trust_gate("t1", 0.0)
        self.assertEqual(config.get_trust_gate("t1"), 0.0)

    def test_set_trust_gate_maximum(self):
        config = TileTrustConfig()
        config.set_trust_gate("t1", 1.0)
        self.assertEqual(config.get_trust_gate("t1"), 1.0)

    def test_set_trust_gate_invalid(self):
        config = TileTrustConfig()
        with self.assertRaises(ValueError):
            config.set_trust_gate("t1", 1.5)
        with self.assertRaises(ValueError):
            config.set_trust_gate("t1", -0.1)

    def test_get_tile_trust_weights_domain_only(self):
        config = TileTrustConfig()
        weights = config.get_tile_trust_weights("tile_a", "code")
        self.assertIn("competence", weights)
        self.assertGreater(weights["competence"], 0)

    def test_get_tile_trust_weights_with_override(self):
        config = TileTrustConfig()
        weights = config.get_tile_trust_weights("security_hardening", "infrastructure")
        self.assertIn("reliability", weights)
        self.assertEqual(weights["reliability"], 1.5)

    def test_get_tile_trust_weights_unknown_domain(self):
        config = TileTrustConfig()
        weights = config.get_tile_trust_weights("tile_x", "unknown")
        self.assertEqual(weights, {})

    def test_serialization_roundtrip(self):
        config = TileTrustConfig(
            trust_gain_per_tile=0.07,
            trust_gate_default=0.4,
            propagation_factor=0.6,
        )
        config.set_trust_gate("special", 0.9)
        d = config.to_dict()
        restored = TileTrustConfig.from_dict(d)
        self.assertEqual(restored.trust_gain_per_tile, 0.07)
        self.assertEqual(restored.trust_gate_default, 0.4)
        self.assertEqual(restored.propagation_factor, 0.6)
        self.assertEqual(restored.get_trust_gate("special"), 0.9)

    def test_serialization_defaults(self):
        config = TileTrustConfig()
        d = config.to_dict()
        restored = TileTrustConfig.from_dict(d)
        self.assertEqual(restored.trust_gain_per_tile, TRUST_GAIN_PER_TILE)
        self.assertEqual(restored.trust_gate_default, TRUST_GATE_DEFAULT)

    def test_serialization_empty_dict(self):
        config = TileTrustConfig.from_dict({})
        self.assertEqual(config.trust_gain_per_tile, TRUST_GAIN_PER_TILE)
        self.assertEqual(config.trust_gate_default, TRUST_GATE_DEFAULT)


# ═══════════════════════════════════════════════════════════════
# TileTrustAuditEntry Tests
# ═══════════════════════════════════════════════════════════════

class TestTileTrustAuditEntry(unittest.TestCase):
    """Tests for the cryptographic audit entry."""

    def test_basic_creation(self):
        entry = TileTrustAuditEntry(
            event_type="tile_completed",
            agent_name="agent1",
            tile_id="tile_a",
        )
        self.assertEqual(entry.event_type, "tile_completed")
        self.assertEqual(entry.agent_name, "agent1")
        self.assertEqual(entry.tile_id, "tile_a")

    def test_compute_hash_deterministic(self):
        entry = TileTrustAuditEntry(
            event_type="trust_updated",
            agent_name="agent1",
            tile_id="tile_a",
            old_value=0.3,
            new_value=0.35,
            delta=0.05,
            timestamp=1000000.0,
        )
        h1 = entry.compute_hash()
        h2 = entry.compute_hash()
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)  # SHA-256 hex digest

    def test_compute_hash_uses_sha256(self):
        entry = TileTrustAuditEntry(
            event_type="test",
            agent_name="a",
            timestamp=1234567890.0,
        )
        content = json.dumps({
            "event_type": "test",
            "agent_name": "a",
            "tile_id": "",
            "trust_dimension": "",
            "old_value": 0.0,
            "new_value": 0.0,
            "delta": 0.0,
            "timestamp": 1234567890.0,
            "context": "",
            "previous_hash": "",
            "metadata": {},
        }, sort_keys=True, separators=(",", ":"))
        expected = hashlib.sha256(content.encode("utf-8")).hexdigest()
        self.assertEqual(entry.compute_hash(), expected)

    def test_seal_creates_hash(self):
        entry = TileTrustAuditEntry(
            event_type="tile_completed",
            agent_name="agent1",
        )
        h = entry.seal()
        self.assertEqual(h, entry.hash)
        self.assertEqual(len(h), 64)

    def test_seal_with_previous_hash(self):
        entry = TileTrustAuditEntry(
            event_type="tile_completed",
            agent_name="agent1",
        )
        prev = "a" * 64
        h = entry.seal(prev)
        self.assertEqual(entry.previous_hash, prev)

    def test_verify_valid(self):
        entry = TileTrustAuditEntry(
            event_type="tile_completed",
            agent_name="agent1",
            tile_id="t1",
            delta=0.05,
            timestamp=1000000.0,
        )
        entry.seal()
        self.assertTrue(entry.verify())

    def test_verify_tampered(self):
        entry = TileTrustAuditEntry(
            event_type="tile_completed",
            agent_name="agent1",
        )
        entry.seal()
        entry.delta = 999.0  # tamper
        self.assertFalse(entry.verify())

    def test_verify_chain_intact(self):
        prev_hash = "abc123" * 5 + "x" * 4  # 64 chars
        entry = TileTrustAuditEntry(
            event_type="trust_updated",
            agent_name="agent1",
        )
        entry.seal(prev_hash)
        self.assertTrue(entry.verify(previous_hash=prev_hash))

    def test_verify_chain_broken(self):
        entry = TileTrustAuditEntry(
            event_type="trust_updated",
            agent_name="agent1",
        )
        entry.seal("original_prev")
        self.assertFalse(entry.verify(previous_hash="wrong_prev"))

    def test_serialization_roundtrip(self):
        entry = TileTrustAuditEntry(
            event_type="trust_updated",
            agent_name="agent2",
            tile_id="tile_b",
            trust_dimension="competence",
            old_value=0.3,
            new_value=0.35,
            delta=0.05,
            timestamp=2000000.0,
            context="Test entry",
            metadata={"key": "value"},
        )
        entry.seal("prev_hash_placeholder")
        d = entry.to_dict()
        restored = TileTrustAuditEntry.from_dict(d)
        self.assertEqual(restored.event_type, "trust_updated")
        self.assertEqual(restored.agent_name, "agent2")
        self.assertEqual(restored.tile_id, "tile_b")
        self.assertEqual(restored.trust_dimension, "competence")
        self.assertEqual(restored.delta, 0.05)
        self.assertEqual(restored.context, "Test entry")
        self.assertEqual(restored.metadata, {"key": "value"})
        self.assertEqual(restored.hash, entry.hash)
        self.assertEqual(restored.previous_hash, entry.previous_hash)

    def test_serialization_from_empty(self):
        entry = TileTrustAuditEntry.from_dict({})
        self.assertEqual(entry.event_type, "")
        self.assertEqual(entry.agent_name, "")

    def test_audit_event_type_values(self):
        self.assertEqual(AuditEventType.TILE_COMPLETED, "tile_completed")
        self.assertEqual(AuditEventType.TRUST_GATE_CHECK, "trust_gate_check")
        self.assertEqual(AuditEventType.TRUST_UPDATED, "trust_updated")
        self.assertEqual(AuditEventType.TRUST_PROPAGATED, "trust_propagated")
        self.assertEqual(AuditEventType.TILE_DISCOVERY, "tile_discovery")
        self.assertEqual(AuditEventType.CONFIG_CHANGED, "config_changed")
        self.assertEqual(AuditEventType.PREREQUISITE_WAIVED, "prerequisite_waived")
        self.assertEqual(AuditEventType.PROFILE_CREATED, "profile_created")


# ═══════════════════════════════════════════════════════════════
# TileTrustProfile Tests
# ═══════════════════════════════════════════════════════════════

class TestTileTrustProfile(unittest.TestCase):
    """Tests for per-agent tile-trust profile."""

    def test_creation(self):
        profile = TileTrustProfile("agent1")
        self.assertEqual(profile.agent_name, "agent1")
        self.assertEqual(profile.completed_tiles, set())
        self.assertEqual(profile.tile_count(), 0)
        for dim in TRUST_DIMENSIONS:
            self.assertEqual(profile.get_dimension_trust(dim), 0.0)

    def test_record_tile_completion(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.05, "reliability": 0.025})
        self.assertIn("tile_a", profile.completed_tiles)
        self.assertEqual(profile.tile_count(), 1)
        self.assertAlmostEqual(profile.get_dimension_trust("competence"), 0.05)

    def test_record_multiple_tiles(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.05})
        profile.record_tile_completion("tile_b", {"competence": 0.03, "generosity": 0.04})
        self.assertEqual(profile.tile_count(), 2)
        self.assertAlmostEqual(profile.get_dimension_trust("competence"), 0.08)
        self.assertAlmostEqual(profile.get_dimension_trust("generosity"), 0.04)

    def test_record_duplicate_tile_ignored(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.05})
        profile.record_tile_completion("tile_a", {"competence": 0.99})
        self.assertEqual(profile.tile_count(), 1)
        self.assertAlmostEqual(profile.get_dimension_trust("competence"), 0.05)

    def test_get_tile_contribution(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.05, "reliability": 0.025})
        contrib = profile.get_tile_contribution("tile_a")
        self.assertAlmostEqual(contrib["competence"], 0.05)
        self.assertAlmostEqual(contrib["reliability"], 0.025)

    def test_get_tile_contribution_unknown(self):
        profile = TileTrustProfile("agent1")
        contrib = profile.get_tile_contribution("nonexistent")
        self.assertEqual(contrib, {})

    def test_get_composite_trust_equal_weights(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.1})
        composite = profile.get_composite_trust()
        # competence=0.1, others=0, equal weights -> 0.1/5 = 0.02
        self.assertAlmostEqual(composite, 0.02, places=4)

    def test_get_composite_trust_custom_weights(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.1, "reliability": 0.2})
        weights = {"competence": 1.0, "reliability": 1.0}
        composite = profile.get_composite_trust(weights)
        self.assertAlmostEqual(composite, 0.15, places=4)

    def test_get_composite_trust_empty(self):
        profile = TileTrustProfile("agent1")
        composite = profile.get_composite_trust()
        self.assertAlmostEqual(composite, 0.0)

    def test_apply_decay_no_time_passed(self):
        profile = TileTrustProfile("agent1")
        now = time.time()
        profile.record_tile_completion("tile_a", {"competence": 0.1})
        # Set the record timestamp to now so no decay
        for dim_records in profile.trust_gains.values():
            for record in dim_records:
                record.timestamp = now
        decayed = profile.apply_decay(0.95, now)
        self.assertAlmostEqual(profile.get_dimension_trust("competence"), 0.1, places=4)

    def test_apply_decay_with_time(self):
        profile = TileTrustProfile("agent1")
        base_time = 1000000.0
        profile.record_tile_completion("tile_a", {"competence": 0.1})
        for dim_records in profile.trust_gains.values():
            for record in dim_records:
                record.timestamp = base_time
        # 1 day later at 0.95 decay: 0.1 * 0.95 = 0.095
        decayed = profile.apply_decay(0.95, base_time + 86400.0)
        self.assertAlmostEqual(
            profile.get_dimension_trust("competence"), 0.095, places=3
        )

    def test_revoke_tile_trust(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.05, "reliability": 0.025})
        profile.record_tile_completion("tile_b", {"competence": 0.03})
        revoked = profile.revoke_tile_trust("tile_a")
        self.assertNotIn("tile_a", profile.completed_tiles)
        self.assertEqual(profile.tile_count(), 1)
        self.assertAlmostEqual(revoked["competence"], 0.05)
        self.assertAlmostEqual(revoked["reliability"], 0.025)
        self.assertAlmostEqual(profile.get_dimension_trust("competence"), 0.03)

    def test_revoke_nonexistent_tile(self):
        profile = TileTrustProfile("agent1")
        revoked = profile.revoke_tile_trust("nonexistent")
        self.assertEqual(revoked, {})

    def test_summary(self):
        profile = TileTrustProfile("agent1")
        profile.record_tile_completion("tile_a", {"competence": 0.05})
        s = profile.summary()
        self.assertEqual(s["agent_name"], "agent1")
        self.assertEqual(s["completed_tiles_count"], 1)
        self.assertIn("tile_a", s["completed_tiles"])
        self.assertIn("total_tile_trust", s)
        self.assertIn("composite_trust", s)

    def test_serialization_roundtrip(self):
        profile = TileTrustProfile("agent2")
        profile.record_tile_completion("tile_a", {"competence": 0.05})
        profile.record_tile_completion("tile_b", {"generosity": 0.04})
        d = profile.to_dict()
        restored = TileTrustProfile.from_dict(d)
        self.assertEqual(restored.agent_name, "agent2")
        self.assertEqual(restored.completed_tiles, {"tile_a", "tile_b"})
        self.assertAlmostEqual(
            restored.get_dimension_trust("competence"), 0.05, places=4
        )
        self.assertAlmostEqual(
            restored.get_dimension_trust("generosity"), 0.04, places=4
        )

    def test_serialization_from_empty(self):
        profile = TileTrustProfile.from_dict({})
        self.assertEqual(profile.agent_name, "")
        self.assertEqual(profile.tile_count(), 0)


# ═══════════════════════════════════════════════════════════════
# TileTrustRecord Tests
# ═══════════════════════════════════════════════════════════════

class TestTileTrustRecord(unittest.TestCase):
    """Tests for the tile trust record dataclass."""

    def test_creation(self):
        record = TileTrustRecord(
            tile_id="tile_a",
            dimensions_affected={"competence": 0.05},
        )
        self.assertEqual(record.tile_id, "tile_a")
        self.assertEqual(record.decayed, False)

    def test_serialization_roundtrip(self):
        record = TileTrustRecord(
            tile_id="tile_b",
            dimensions_affected={"competence": 0.03, "reliability": 0.01},
            timestamp=1234567890.0,
            decayed=True,
        )
        d = record.to_dict()
        restored = TileTrustRecord.from_dict(d)
        self.assertEqual(restored.tile_id, "tile_b")
        self.assertAlmostEqual(restored.dimensions_affected["competence"], 0.03)
        self.assertEqual(restored.decayed, True)


# ═══════════════════════════════════════════════════════════════
# TrustPropagationResult Tests
# ═══════════════════════════════════════════════════════════════

class TestTrustPropagationResult(unittest.TestCase):
    """Tests for the propagation result dataclass."""

    def test_creation(self):
        result = TrustPropagationResult(
            source_agent="bob",
            target_agent="alice",
            tile_id="tile_d",
            propagated_trust={"competence": 0.02},
            waived_prerequisites=["tile_b"],
            depth=1,
        )
        self.assertEqual(result.source_agent, "bob")
        self.assertEqual(result.target_agent, "alice")
        self.assertEqual(result.depth, 1)

    def test_serialization(self):
        result = TrustPropagationResult(
            source_agent="bob",
            target_agent="alice",
            tile_id="tile_d",
            propagated_trust={"competence": 0.02},
        )
        d = result.to_dict()
        self.assertEqual(d["source_agent"], "bob")
        self.assertEqual(d["tile_id"], "tile_d")
        self.assertIn("competence", d["propagated_trust"])


# ═══════════════════════════════════════════════════════════════
# TileDiscoveryResult Tests
# ═══════════════════════════════════════════════════════════════

class TestTileDiscoveryResult(unittest.TestCase):
    """Tests for the tile discovery result dataclass."""

    def test_creation(self):
        result = TileDiscoveryResult(
            tile_id="tile_c",
            score=0.75,
            trust_bonus=0.15,
            contributor_trust=0.5,
            reasons=["Meets trust gate threshold"],
        )
        self.assertEqual(result.tile_id, "tile_c")
        self.assertEqual(len(result.reasons), 1)

    def test_serialization(self):
        result = TileDiscoveryResult(
            tile_id="tile_c",
            score=0.75,
            trust_bonus=0.15,
            contributor_trust=0.5,
        )
        d = result.to_dict()
        self.assertEqual(d["tile_id"], "tile_c")
        self.assertAlmostEqual(d["score"], 0.75, places=4)


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Trust-Gated Tile Access Tests
# ═══════════════════════════════════════════════════════════════

class TestTrustGatedAccess(unittest.TestCase):
    """Tests for trust-gated tile access (Requirement 1)."""

    def test_check_trust_gate_granted(self):
        fusion, _ = _make_fusion_with_graph()
        result = fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        self.assertTrue(result["granted"])
        self.assertAlmostEqual(result["actual"], 0.5)

    def test_check_trust_gate_denied(self):
        fusion, _ = _make_fusion_with_graph()
        result = fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.1)
        self.assertFalse(result["granted"])
        self.assertAlmostEqual(result["required"], 0.3)

    def test_check_trust_gate_exact_threshold(self):
        fusion, _ = _make_fusion_with_graph()
        result = fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.3)
        self.assertTrue(result["granted"])

    def test_check_trust_gate_custom_threshold(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.set_trust_gate("tile_d", 0.8)
        result = fusion.check_trust_gate("agent1", "tile_d", agent_trust=0.5)
        self.assertFalse(result["granted"])
        self.assertAlmostEqual(result["required"], 0.8)

    def test_check_trust_gate_uses_profile_trust(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.set_trust_gate("tile_a", 0.001)  # very low gate
        fusion.record_tile_completion("agent1", "tile_a")
        result = fusion.check_trust_gate("agent1", "tile_a")
        self.assertTrue(result["granted"])

    def test_check_trust_gate_creates_audit(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        self.assertGreater(fusion.audit_count(), 0)

    def test_get_accessible_tiles(self):
        fusion, _ = _make_fusion_with_graph()
        accessible = fusion.get_accessible_tiles("agent1", agent_trust=0.5)
        self.assertIn("tile_a", accessible)
        self.assertIn("tile_b", accessible)
        self.assertIn("tile_d", accessible)

    def test_get_accessible_tiles_low_trust(self):
        fusion, _ = _make_fusion_with_graph()
        accessible = fusion.get_accessible_tiles("agent1", agent_trust=0.1)
        self.assertEqual(accessible, [])

    def test_get_accessible_tiles_with_custom_gate(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.set_trust_gate("tile_a", 0.0)
        accessible = fusion.get_accessible_tiles("agent1", agent_trust=0.0)
        self.assertIn("tile_a", accessible)

    def test_get_locked_tiles(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.set_trust_gate("tile_d", 0.8)
        locked = fusion.get_locked_tiles("agent1", agent_trust=0.5)
        self.assertIn("tile_d", locked)
        self.assertAlmostEqual(locked["tile_d"], 0.8)

    def test_get_locked_tiles_none_locked(self):
        fusion, _ = _make_fusion_with_graph()
        locked = fusion.get_locked_tiles("agent1", agent_trust=1.0)
        self.assertEqual(locked, {})

    def test_get_accessible_tiles_no_graph(self):
        fusion = TileTrustFusion()
        accessible = fusion.get_accessible_tiles("agent1", agent_trust=0.5)
        self.assertEqual(accessible, [])


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Tile-Earned Trust Tests
# ═══════════════════════════════════════════════════════════════

class TestTileEarnedTrust(unittest.TestCase):
    """Tests for tile-earned trust (Requirement 2)."""

    def test_compute_tile_trust_gain_code(self):
        fusion, _ = _make_fusion_with_graph()
        gains = fusion.compute_tile_trust_gain("tile_a")
        self.assertIn("competence", gains)
        self.assertGreater(gains["competence"], 0)

    def test_compute_tile_trust_gain_social(self):
        fusion, _ = _make_fusion_with_graph()
        gains = fusion.compute_tile_trust_gain("tile_b")
        self.assertIn("generosity", gains)

    def test_compute_tile_trust_gain_trust_domain(self):
        fusion, _ = _make_fusion_with_graph()
        gains = fusion.compute_tile_trust_gain("tile_c")
        self.assertIn("honesty", gains)

    def test_compute_tile_trust_gain_security_hardening(self):
        fusion, _ = _make_fusion_with_graph()
        gains = fusion.compute_tile_trust_gain("security_hardening")
        # Has override: reliability=1.5, competence=1.0
        self.assertAlmostEqual(gains["reliability"], 0.05 * 1.5, places=4)
        self.assertAlmostEqual(gains["competence"], 0.05 * 1.0, places=4)

    def test_compute_tile_trust_gain_unknown_tile(self):
        fusion = TileTrustFusion()
        gains = fusion.compute_tile_trust_gain("nonexistent")
        self.assertEqual(gains, {})

    def test_record_tile_completion_success(self):
        fusion, _ = _make_fusion_with_graph()
        result = fusion.record_tile_completion("agent1", "tile_a")
        self.assertTrue(result["success"])
        self.assertEqual(result["tile_id"], "tile_a")
        self.assertIn("trust_gains", result)
        self.assertIn("profile_summary", result)

    def test_record_tile_completion_creates_audit(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        audit = fusion.get_audit_trail(agent_name="agent1")
        tile_events = [e for e in audit if e["tile_id"] == "tile_a"]
        self.assertGreater(len(tile_events), 0)

    def test_record_tile_completion_duplicate_rejected(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        result = fusion.record_tile_completion("agent1", "tile_a")
        self.assertFalse(result["success"])
        self.assertIn("already", result["error"])

    def test_record_tile_completion_unknown_tile(self):
        fusion, _ = _make_fusion_with_graph()
        result = fusion.record_tile_completion("agent1", "nonexistent")
        self.assertFalse(result["success"])

    def test_record_tile_completion_updates_profile(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        profile = fusion.get_profile("agent1")
        self.assertIn("tile_a", profile.completed_tiles)
        self.assertGreater(profile.get_dimension_trust("competence"), 0)

    def test_record_tile_completion_tracks_contributor(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a", contributor="system")
        self.assertEqual(fusion.tile_contributors.get("tile_a"), "system")

    def test_get_agent_trust_from_tiles_dimension(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        trust = fusion.get_agent_trust_from_tiles("agent1", "competence")
        self.assertGreater(trust, 0)

    def test_get_agent_trust_from_tiles_composite(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        trust = fusion.get_agent_trust_from_tiles("agent1")
        self.assertGreater(trust, 0)

    def test_get_agent_trust_from_tiles_unknown_agent(self):
        fusion, _ = _make_fusion_with_graph()
        trust = fusion.get_agent_trust_from_tiles("nobody")
        self.assertAlmostEqual(trust, 0.0)


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Trust-Weighted Discovery Tests
# ═══════════════════════════════════════════════════════════════

class TestTrustWeightedDiscovery(unittest.TestCase):
    """Tests for trust-weighted tile discovery (Requirement 3)."""

    def test_recommend_tiles_basic(self):
        fusion, _ = _make_fusion_with_graph()
        results = fusion.recommend_tiles("agent1")
        self.assertIsInstance(results, list)
        self.assertGreater(len(results), 0)

    def test_recommend_tiles_respects_top_n(self):
        fusion, _ = _make_fusion_with_graph()
        results = fusion.recommend_tiles("agent1", top_n=2)
        self.assertLessEqual(len(results), 2)

    def test_recommend_tiles_excludes_acquired(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        results = fusion.recommend_tiles("agent1")
        tile_ids = [r.tile_id for r in results]
        self.assertNotIn("tile_a", tile_ids)

    def test_recommend_tiles_with_contributor_trust(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.tile_contributors["tile_e"] = "bob"
        fusion.set_social_trust("agent1", "bob", 0.9)
        results = fusion.recommend_tiles("agent1")
        tile_e_result = next((r for r in results if r.tile_id == "tile_e"), None)
        if tile_e_result:
            self.assertGreater(tile_e_result.trust_bonus, 0)

    def test_recommend_tiles_sorted_by_score(self):
        fusion, _ = _make_fusion_with_graph()
        results = fusion.recommend_tiles("agent1")
        for i in range(len(results) - 1):
            self.assertGreaterEqual(results[i].score, results[i + 1].score)

    def test_recommend_tiles_creates_audit(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.recommend_tiles("agent1")
        audit = fusion.get_audit_trail(
            event_type="tile_discovery", agent_name="agent1"
        )
        self.assertGreater(len(audit), 0)

    def test_recommend_tiles_no_graph(self):
        fusion = TileTrustFusion()
        results = fusion.recommend_tiles("agent1")
        self.assertEqual(results, [])

    def test_recommend_tiles_with_high_trust(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent1", "tile_b")
        fusion.record_tile_completion("agent1", "tile_c")
        results = fusion.recommend_tiles("agent1")
        # All tiles should be accessible (high trust from completions)
        for r in results:
            self.assertGreaterEqual(r.score, 0.0)
            self.assertLessEqual(r.score, 1.0)

    def test_discovery_result_serialization(self):
        result = TileDiscoveryResult(
            tile_id="tile_x",
            score=0.85,
            trust_bonus=0.2,
            contributor_trust=0.6,
            reasons=["Meets trust gate threshold", "High contributor trust"],
        )
        d = result.to_dict()
        self.assertEqual(d["tile_id"], "tile_x")
        self.assertAlmostEqual(d["score"], 0.85, places=4)
        self.assertEqual(len(d["reasons"]), 2)


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Fleet Trust Propagation Tests
# ═══════════════════════════════════════════════════════════════

class TestFleetTrustPropagation(unittest.TestCase):
    """Tests for fleet tile trust propagation (Requirement 4)."""

    def test_set_and_get_social_trust(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.set_social_trust("alice", "bob", 0.8)
        self.assertAlmostEqual(fusion.get_social_trust("alice", "bob"), 0.8)

    def test_get_social_trust_missing(self):
        fusion, _ = _make_fusion_with_graph()
        self.assertAlmostEqual(fusion.get_social_trust("alice", "bob"), 0.0)

    def test_set_social_trust_clamped(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.set_social_trust("alice", "bob", 1.5)
        self.assertAlmostEqual(fusion.get_social_trust("alice", "bob"), 1.0)
        fusion.set_social_trust("alice", "bob", -0.5)
        self.assertAlmostEqual(fusion.get_social_trust("alice", "bob"), 0.0)

    def test_compute_propagated_trust_basic(self):
        fusion, _ = _make_fusion_with_graph()
        # Agent B completes tile_d
        fusion.record_tile_completion("bob", "tile_a")
        fusion.record_tile_completion("bob", "tile_b")
        fusion.record_tile_completion("bob", "tile_c")
        fusion.record_tile_completion("bob", "tile_d")
        # Alice trusts Bob
        fusion.set_social_trust("alice", "bob", 0.9)
        # Compute propagation
        results = fusion.compute_propagated_trust("alice", "tile_d")
        self.assertGreater(len(results), 0)
        source_agents = {r.source_agent for r in results}
        self.assertIn("bob", source_agents)

    def test_compute_propagated_trust_no_social_links(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("bob", "tile_a")
        results = fusion.compute_propagated_trust("alice", "tile_a")
        self.assertEqual(results, [])

    def test_compute_propagated_trust_target_not_completed(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.set_social_trust("alice", "bob", 0.9)
        # Bob hasn't completed tile_d
        results = fusion.compute_propagated_trust("alice", "tile_d")
        self.assertEqual(results, [])

    def test_compute_propagated_trust_capped(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("bob", "tile_a")
        fusion.set_social_trust("alice", "bob", 1.0)
        results = fusion.compute_propagated_trust("alice", "tile_a")
        for result in results:
            for dim, bonus in result.propagated_trust.items():
                self.assertLessEqual(bonus, MAX_TILE_TRUST_BONUS)

    def test_compute_propagated_trust_unknown_tile(self):
        fusion, _ = _make_fusion_with_graph()
        results = fusion.compute_propagated_trust("alice", "nonexistent")
        self.assertEqual(results, [])

    def test_compute_propagated_trust_depth_limit(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.propagation_depth_limit = 1
        fusion.record_tile_completion("charlie", "tile_a")
        fusion.set_social_trust("alice", "bob", 0.8)
        fusion.set_social_trust("bob", "charlie", 0.8)
        results = fusion.compute_propagated_trust("alice", "tile_a")
        # Charlie is at depth 2, should be excluded
        for r in results:
            self.assertLessEqual(r.depth, 1)

    def test_compute_propagated_trust_creates_audit(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("bob", "tile_a")
        fusion.set_social_trust("alice", "bob", 0.9)
        fusion.compute_propagated_trust("alice", "tile_a")
        audit = fusion.get_audit_trail(event_type="trust_propagated")
        self.assertGreater(len(audit), 0)

    def test_get_effective_prerequisites_basic(self):
        fusion, _ = _make_fusion_with_graph()
        # tile_d requires [tile_b, tile_c]
        prereqs = fusion.get_effective_prerequisites("alice", "tile_d")
        self.assertIn("tile_b", prereqs)
        self.assertIn("tile_c", prereqs)

    def test_get_effective_prerequisites_after_completion(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("alice", "tile_b")
        prereqs = fusion.get_effective_prerequisites("alice", "tile_d")
        self.assertNotIn("tile_b", prereqs)
        self.assertIn("tile_c", prereqs)

    def test_get_effective_prerequisites_with_propagation(self):
        fusion, _ = _make_fusion_with_graph()
        # Bob completes tile_b and tile_c
        fusion.record_tile_completion("bob", "tile_a")
        fusion.record_tile_completion("bob", "tile_b")
        fusion.record_tile_completion("bob", "tile_c")
        # Alice trusts Bob
        fusion.set_social_trust("alice", "bob", 1.0)
        # The propagation may waive some prerequisites
        prereqs = fusion.get_effective_prerequisites("alice", "tile_d")
        # prereqs should be a subset of the original [tile_b, tile_c]
        # depending on whether propagated trust exceeds gate thresholds
        for p in prereqs:
            self.assertIn(p, ["tile_b", "tile_c"])

    def test_get_effective_prerequisites_no_prereqs(self):
        fusion, _ = _make_fusion_with_graph()
        # tile_a has no prerequisites
        prereqs = fusion.get_effective_prerequisites("alice", "tile_a")
        self.assertEqual(prereqs, [])


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Audit Trail Tests
# ═══════════════════════════════════════════════════════════════

class TestAuditTrail(unittest.TestCase):
    """Tests for the tile trust audit trail (Requirement 5)."""

    def test_audit_trail_records_gate_check(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        audit = fusion.get_audit_trail(event_type="trust_gate_check")
        self.assertGreater(len(audit), 0)

    def test_audit_trail_records_tile_completion(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        audit = fusion.get_audit_trail(event_type="tile_completed")
        self.assertGreater(len(audit), 0)

    def test_audit_trail_records_trust_update(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        audit = fusion.get_audit_trail(event_type="trust_updated")
        self.assertGreater(len(audit), 0)

    def test_audit_trail_records_profile_creation(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.get_profile("new_agent")
        audit = fusion.get_audit_trail(event_type="profile_created")
        self.assertGreater(len(audit), 0)

    def test_audit_trail_filter_by_agent(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        fusion.check_trust_gate("agent2", "tile_a", agent_trust=0.5)
        audit = fusion.get_audit_trail(agent_name="agent1")
        for entry in audit:
            self.assertEqual(entry["agent_name"], "agent1")

    def test_audit_trail_filter_by_tile(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent1", "tile_b")
        audit = fusion.get_audit_trail(tile_id="tile_a")
        for entry in audit:
            self.assertEqual(entry["tile_id"], "tile_a")

    def test_audit_trail_limit(self):
        fusion, _ = _make_fusion_with_graph()
        for i in range(5):
            fusion.check_trust_gate(f"agent{i}", "tile_a", agent_trust=0.5)
        audit = fusion.get_audit_trail(limit=2)
        self.assertLessEqual(len(audit), 2)

    def test_audit_trail_most_recent_first(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        fusion.check_trust_gate("agent2", "tile_b", agent_trust=0.5)
        audit = fusion.get_audit_trail()
        if len(audit) >= 2:
            self.assertGreaterEqual(
                audit[0]["timestamp"], audit[1]["timestamp"]
            )

    def test_verify_audit_trail_valid(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent1", "tile_b")
        result = fusion.verify_audit_trail()
        self.assertTrue(result["valid"])
        self.assertGreater(result["entry_count"], 0)

    def test_verify_audit_trail_empty(self):
        fusion, _ = _make_fusion_with_graph()
        result = fusion.verify_audit_trail()
        self.assertTrue(result["valid"])
        self.assertEqual(result["entry_count"], 0)

    def test_verify_audit_trail_detects_tamper(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        # Tamper with an entry
        fusion.audit_trail[-1].delta = 999.0
        result = fusion.verify_audit_trail()
        self.assertFalse(result["valid"])
        self.assertGreater(len(result["issues"]), 0)

    def test_prune_audit_trail(self):
        fusion, _ = _make_fusion_with_graph()
        for i in range(20):
            fusion.check_trust_gate(f"agent{i}", "tile_a", agent_trust=0.5)
        removed = fusion.prune_audit_trail(max_entries=5)
        self.assertGreater(removed, 0)
        self.assertLessEqual(len(fusion.audit_trail), 5)

    def test_prune_audit_trail_no_prune_needed(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        removed = fusion.prune_audit_trail(max_entries=100)
        self.assertEqual(removed, 0)

    def test_prune_reseals_chain(self):
        fusion, _ = _make_fusion_with_graph()
        for i in range(10):
            fusion.check_trust_gate(f"agent{i}", "tile_a", agent_trust=0.5)
        fusion.prune_audit_trail(max_entries=5)
        result = fusion.verify_audit_trail()
        self.assertTrue(result["valid"])

    def test_audit_count(self):
        fusion, _ = _make_fusion_with_graph()
        self.assertEqual(fusion.audit_count(), 0)
        fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        self.assertGreater(fusion.audit_count(), 0)


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Aggregate Operations Tests
# ═══════════════════════════════════════════════════════════════

class TestAggregateOperations(unittest.TestCase):
    """Tests for aggregate fleet operations."""

    def test_apply_decay_all(self):
        fusion, _ = _make_fusion_with_graph()
        base_time = 1000000.0
        fusion.record_tile_completion("agent1", "tile_a")
        # Override timestamps
        for profile in fusion.profiles.values():
            for dim_records in profile.trust_gains.values():
                for record in dim_records:
                    record.timestamp = base_time
        decayed = fusion.apply_decay_all(current_time=base_time + 86400.0)
        self.assertIn("agent1", decayed)

    def test_fleet_summary(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent2", "tile_b")
        summary = fusion.fleet_summary()
        self.assertEqual(summary["agent_count"], 2)
        self.assertIn("profiles", summary)
        self.assertIn("tile_completion_counts", summary)
        self.assertIn("audit_trail_entries", summary)
        self.assertIn("config", summary)

    def test_fleet_summary_empty(self):
        fusion, _ = _make_fusion_with_graph()
        summary = fusion.fleet_summary()
        self.assertEqual(summary["agent_count"], 0)


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Serialization Tests
# ═══════════════════════════════════════════════════════════════

class TestFusionSerialization(unittest.TestCase):
    """Tests for full fusion engine serialization roundtrips."""

    def test_to_dict(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        d = fusion.to_dict()
        self.assertIn("config", d)
        self.assertIn("profiles", d)
        self.assertIn("audit_trail", d)
        self.assertIn("social_trust", d)
        self.assertIn("tile_contributors", d)

    def test_from_dict_roundtrip(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent2", "tile_b")
        fusion.set_social_trust("agent1", "agent2", 0.8)
        d = fusion.to_dict()
        restored = TileTrustFusion.from_dict(d)
        self.assertEqual(len(restored.profiles), 2)
        self.assertIn("agent1", restored.profiles)
        self.assertIn("agent2", restored.profiles)
        self.assertIn("tile_a", restored.profiles["agent1"].completed_tiles)
        self.assertAlmostEqual(
            restored.get_social_trust("agent1", "agent2"), 0.8, places=3
        )

    def test_from_dict_preserves_audit_trail(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        d = fusion.to_dict()
        restored = TileTrustFusion.from_dict(d)
        self.assertEqual(len(restored.audit_trail), len(fusion.audit_trail))

    def test_from_dict_empty(self):
        fusion = TileTrustFusion.from_dict({})
        self.assertIsNotNone(fusion)
        self.assertEqual(len(fusion.profiles), 0)

    def test_serialization_with_config_changes(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.set_trust_gate("tile_a", 0.9)
        fusion.record_tile_completion("agent1", "tile_a")
        d = fusion.to_dict()
        restored = TileTrustFusion.from_dict(d)
        self.assertAlmostEqual(restored.config.get_trust_gate("tile_a"), 0.9)


# ═══════════════════════════════════════════════════════════════
# TileTrustFusion — Integration / Edge Case Tests
# ═══════════════════════════════════════════════════════════════

class TestIntegrationAndEdgeCases(unittest.TestCase):
    """Integration tests and edge cases."""

    def test_full_workflow_trust_gates_and_earned_trust(self):
        """Simulate a complete workflow: agent earns trust, unlocks tiles."""
        fusion, _ = _make_fusion_with_graph()
        # Initially no trust
        profile = fusion.get_profile("agent1")
        self.assertAlmostEqual(profile.get_composite_trust(), 0.0)
        # Complete tiles to earn trust
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent1", "tile_e")
        # Now composite trust should be positive
        profile = fusion.get_profile("agent1")
        trust = profile.get_composite_trust()
        self.assertGreater(trust, 0.0)
        # Set gate just above zero — any earned trust should pass
        fusion.config.set_trust_gate("tile_d", 0.001)
        result = fusion.check_trust_gate("agent1", "tile_d", agent_trust=trust)
        self.assertTrue(result["granted"])
        # With default gate (0.3), should still be locked
        result_high = fusion.check_trust_gate(
            "agent1", "tile_d", agent_trust=trust
        )
        # Use the default gate, not the overridden one
        fusion.config.trust_gate_overrides.pop("tile_d", None)
        result_default = fusion.check_trust_gate(
            "agent1", "tile_d", agent_trust=trust
        )
        self.assertFalse(result_default["granted"])
        self.assertAlmostEqual(result_default["required"], 0.3)

    def test_trust_propagation_chain(self):
        """A -> B -> C chain: C completed a tile, trust flows to A."""
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("charlie", "tile_a")
        fusion.set_social_trust("bob", "charlie", 0.9)
        fusion.set_social_trust("alice", "bob", 0.9)
        results = fusion.compute_propagated_trust("alice", "tile_a")
        # Should find a path through bob -> charlie
        source_agents = {r.source_agent for r in results}
        self.assertIn("charlie", source_agents)

    def test_no_double_counting_completions(self):
        """Completing the same tile twice should not double-count trust."""
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        profile = fusion.get_profile("agent1")
        trust_before = profile.get_composite_trust()
        fusion.record_tile_completion("agent1", "tile_a")
        trust_after = profile.get_composite_trust()
        self.assertAlmostEqual(trust_before, trust_after)

    def test_multiple_agents_completing_same_tile(self):
        """Multiple agents can each earn trust from the same tile."""
        fusion, _ = _make_fusion_with_graph()
        fusion.record_tile_completion("agent1", "tile_a")
        fusion.record_tile_completion("agent2", "tile_a")
        p1 = fusion.get_profile("agent1")
        p2 = fusion.get_profile("agent2")
        self.assertAlmostEqual(
            p1.get_dimension_trust("competence"),
            p2.get_dimension_trust("competence"),
        )

    def test_domain_to_trust_dim_mapping(self):
        fusion, _ = _make_fusion_with_graph()
        self.assertEqual(fusion._domain_to_trust_dim("code"), "competence")
        self.assertEqual(fusion._domain_to_trust_dim("social"), "generosity")
        self.assertEqual(fusion._domain_to_trust_dim("trust"), "honesty")
        self.assertEqual(fusion._domain_to_trust_dim("infrastructure"), "reliability")
        self.assertEqual(fusion._domain_to_trust_dim("creative"), "competence")
        self.assertEqual(fusion._domain_to_trust_dim("unknown"), "competence")

    def test_set_tile_graph(self):
        fusion = TileTrustFusion()
        self.assertIsNone(fusion.tile_graph)
        graph = _make_mock_graph({"t1": ("code", [])})
        fusion.set_tile_graph(graph)
        self.assertIsNotNone(fusion.tile_graph)

    def test_all_tile_ids_empty_graph(self):
        fusion = TileTrustFusion()
        self.assertEqual(fusion._all_tile_ids(), [])

    def test_get_tile_domain_no_graph(self):
        fusion = TileTrustFusion()
        self.assertEqual(fusion._get_tile_domain("anything"), "unknown")

    def test_get_tile_prerequisites_no_graph(self):
        fusion = TileTrustFusion()
        self.assertEqual(fusion._get_tile_prerequisites("anything"), [])

    def test_profile_created_on_first_access(self):
        fusion, _ = _make_fusion_with_graph()
        self.assertNotIn("newbie", fusion.profiles)
        fusion.get_profile("newbie")
        self.assertIn("newbie", fusion.profiles)

    def test_fleet_summary_includes_social_edges(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.set_social_trust("a", "b", 0.5)
        fusion.set_social_trust("a", "c", 0.7)
        summary = fusion.fleet_summary()
        self.assertEqual(summary["social_trust_edges"], 2)

    def test_empty_audit_trail_query(self):
        fusion, _ = _make_fusion_with_graph()
        audit = fusion.get_audit_trail(agent_name="nobody")
        self.assertEqual(audit, [])

    def test_config_change_affects_gates(self):
        fusion, _ = _make_fusion_with_graph()
        fusion.config.trust_gate_default = 0.9
        result = fusion.check_trust_gate("agent1", "tile_a", agent_trust=0.5)
        self.assertFalse(result["granted"])
        self.assertAlmostEqual(result["required"], 0.9)


if __name__ == "__main__":
    unittest.main()
