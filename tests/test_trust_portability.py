#!/usr/bin/env python3
"""
Comprehensive test suite for trust_portability.py

Covers: TrustAttestation, FleetTrustBridge, TrustPropagationGraph,
        CrossRepoTrustSync, CROSS_REPO_TRUST_EVENTS, edge cases.
Aims for 35+ tests with full coverage of key behaviors.
"""

import json
import sys
import time
import math
from pathlib import Path
from typing import List, Dict, Any, Tuple

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trust_portability import (
    # Constants
    FLEET_TRUST_KEY,
    DEFAULT_IMPORT_FACTOR,
    ATTESTATION_STALENESS_SECONDS,
    FOREIGN_DECAY_RATE,
    MAX_PATH_DEPTH,
    INCONSISTENCY_THRESHOLD,
    ATTESTATION_MAX_AGE,
    ECHO_CHAMBER_INWARD_RATIO,
    TRUST_DIMENSIONS,
    BASE_TRUST,
    CROSS_REPO_TRUST_EVENTS,
    # Classes
    TrustAttestation,
    FleetTrustBridge,
    InconsistencyReport,
    TrustEdge,
    TrustPropagationGraph,
    CrossRepoTrustSync,
    SyncResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def make_trust_getter(value: float):
    """Return a simple trust getter that always returns a fixed value."""
    return lambda agent_name: value


def make_attestation(
    agent_name: str = "alice",
    issuer_repo: str = "repo-a",
    composite: float = 0.8,
    event_count: int = 10,
    is_meaningful: bool = True,
    issued_at: float = None,
    expires_at: float = 0.0,
    key: str = FLEET_TRUST_KEY,
    cross_repo_events: List[str] = None,
) -> TrustAttestation:
    """Create and sign a test attestation."""
    att = TrustAttestation(
        agent_name=agent_name,
        issuer_repo=issuer_repo,
        issuer_id=issuer_repo,
        composite=composite,
        event_count=event_count,
        is_meaningful=is_meaningful,
        issued_at=issued_at or time.time(),
        expires_at=expires_at,
        dimensions={dim: composite for dim in TRUST_DIMENSIONS},
        cross_repo_events=cross_repo_events or [],
    )
    att.sign(key)
    return att


def make_simple_bridge(
    local_trust: float = 0.7,
    import_factor: float = DEFAULT_IMPORT_FACTOR,
    local_repo: str = "local",
) -> FleetTrustBridge:
    """Create a bridge with a simple local trust getter."""
    return FleetTrustBridge(
        local_repo=local_repo,
        import_factor=import_factor,
        trust_getter=make_trust_getter(local_trust),
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. Constants
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_fleet_trust_key(self):
        assert FLEET_TRUST_KEY == "superinstance-fleet-trust-v1"

    def test_trust_dimensions_count(self):
        assert len(TRUST_DIMENSIONS) == 5

    def test_trust_dimensions_match_engine(self):
        expected = ["code_quality", "task_completion", "collaboration", "reliability", "innovation"]
        assert TRUST_DIMENSIONS == expected

    def test_base_trust(self):
        assert BASE_TRUST == 0.3

    def test_default_import_factor_in_range(self):
        assert 0.0 <= DEFAULT_IMPORT_FACTOR <= 1.0

    def test_foreign_decay_rate_in_range(self):
        assert 0.0 < FOREIGN_DECAY_RATE < 1.0

    def test_inconsistency_threshold_positive(self):
        assert INCONSISTENCY_THRESHOLD > 0.0

    def test_attestation_max_age_positive(self):
        assert ATTESTATION_MAX_AGE > 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 2. CROSS_REPO_TRUST_EVENTS
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossRepoTrustEvents:
    def test_has_events(self):
        assert len(CROSS_REPO_TRUST_EVENTS) >= 8

    def test_each_event_has_required_keys(self):
        for name, evt in CROSS_REPO_TRUST_EVENTS.items():
            assert "dimension" in evt, f"{name} missing dimension"
            assert "value" in evt, f"{name} missing value"
            assert "weight" in evt, f"{name} missing weight"
            assert "description" in evt, f"{name} missing description"

    def test_values_in_range(self):
        for name, evt in CROSS_REPO_TRUST_EVENTS.items():
            assert 0 <= evt["value"] <= 1, f"{name} value out of range"

    def test_cross_repo_code_review_event(self):
        evt = CROSS_REPO_TRUST_EVENTS["cross_repo_code_review"]
        assert evt["dimension"] == "code_quality"
        assert evt["value"] > 0.5

    def test_fleet_collaboration_event(self):
        evt = CROSS_REPO_TRUST_EVENTS["fleet_collaboration"]
        assert evt["dimension"] == "collaboration"
        assert evt["value"] > 0.5

    def test_foreign_task_completed_event(self):
        assert "foreign_task_completed" in CROSS_REPO_TRUST_EVENTS


# ═══════════════════════════════════════════════════════════════════════════
# 3. TrustAttestation
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustAttestation:
    def test_creation_defaults(self):
        att = TrustAttestation(agent_name="alice", issuer_repo="repo-a")
        assert att.agent_name == "alice"
        assert att.issuer_repo == "repo-a"
        assert att.composite == BASE_TRUST
        assert att.event_count == 0
        assert att.is_meaningful is False

    def test_post_init_populates_dimensions(self):
        att = TrustAttestation(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            assert dim in att.dimensions
            assert att.dimensions[dim] == BASE_TRUST

    def test_fingerprint_deterministic(self):
        att = TrustAttestation(
            agent_name="alice", issuer_repo="repo-a",
            composite=0.8, issued_at=1000000.0,
        )
        fp1 = att.compute_fingerprint()
        fp2 = att.compute_fingerprint()
        assert fp1 == fp2
        assert len(fp1) == 64  # SHA-256 hex digest

    def test_fingerprint_differs_for_different_agents(self):
        att_a = TrustAttestation(agent_name="alice", issued_at=1000000.0)
        att_b = TrustAttestation(agent_name="bob", issued_at=1000000.0)
        assert att_a.compute_fingerprint() != att_b.compute_fingerprint()

    def test_sign_creates_signature(self):
        att = make_attestation()
        assert att.signature != ""
        assert len(att.signature) == 64  # HMAC-SHA256 hex

    def test_sign_sets_fingerprint(self):
        att = make_attestation()
        assert att.fingerprint != ""
        assert att.fingerprint == att.compute_fingerprint()

    def test_verify_valid_signature(self):
        att = make_attestation()
        assert att.verify() is True

    def test_verify_wrong_key(self):
        att = make_attestation(key=FLEET_TRUST_KEY)
        assert att.verify(key="wrong-key") is False

    def test_verify_empty_signature(self):
        att = TrustAttestation(agent_name="alice")
        assert att.verify() is False

    def test_verify_tampered_composite(self):
        att = make_attestation(composite=0.8)
        att.composite = 0.2  # tamper
        assert att.verify() is False

    def test_verify_tampered_agent(self):
        att = make_attestation(agent_name="alice")
        att.agent_name = "eve"  # tamper
        assert att.verify() is False

    def test_is_expired_no_expiry(self):
        att = make_attestation()
        assert att.is_expired() is False

    def test_is_expired_future(self):
        att = make_attestation(expires_at=time.time() + 3600)
        assert att.is_expired() is False

    def test_is_expired_past(self):
        att = make_attestation(expires_at=time.time() - 3600)
        assert att.is_expired() is True

    def test_age_seconds(self):
        att = make_attestation(issued_at=time.time() - 100)
        assert 95 <= att.age_seconds() <= 105

    def test_age_days(self):
        att = make_attestation(issued_at=time.time() - (3 * 86400))
        assert 2.9 <= att.age_days() <= 3.1

    def test_decayed_weight_fresh(self):
        att = make_attestation(issued_at=time.time())
        assert abs(att.decayed_weight() - 1.0) < 1e-9

    def test_decayed_weight_older(self):
        att = make_attestation(issued_at=time.time() - (10 * 86400))
        weight = att.decayed_weight()
        assert 0.0 < weight < 1.0
        expected = FOREIGN_DECAY_RATE ** 10
        assert abs(weight - expected) < 1e-6

    def test_to_dict_roundtrip(self):
        att = make_attestation(
            agent_name="bob", issuer_repo="repo-b", composite=0.75,
            event_count=15, is_meaningful=True,
            cross_repo_events=["fleet_collaboration"],
        )
        d = att.to_dict()
        att2 = TrustAttestation.from_dict(d)
        assert att2.agent_name == "bob"
        assert att2.issuer_repo == "repo-b"
        assert att2.composite == 0.75
        assert att2.event_count == 15
        assert att2.is_meaningful is True
        assert att2.cross_repo_events == ["fleet_collaboration"]
        # Signature preserved
        assert att2.verify() is True

    def test_to_json_roundtrip(self):
        att = make_attestation()
        json_str = att.to_json()
        att2 = TrustAttestation.from_json(json_str)
        assert att2.agent_name == att.agent_name
        assert att2.verify() is True

    def test_from_dict_missing_fields_use_defaults(self):
        att = TrustAttestation.from_dict({})
        assert att.agent_name == ""
        assert att.composite == BASE_TRUST


# ═══════════════════════════════════════════════════════════════════════════
# 4. FleetTrustBridge
# ═══════════════════════════════════════════════════════════════════════════

class TestFleetTrustBridge:
    def test_init_defaults(self):
        bridge = FleetTrustBridge()
        assert bridge.local_repo == "local"
        assert bridge.import_factor == DEFAULT_IMPORT_FACTOR

    def test_import_valid_attestation(self):
        bridge = make_simple_bridge()
        att = make_attestation(composite=0.8)
        result = bridge.import_attestation(att)
        assert result["accepted"] is True
        assert result["reason"] == "valid"

    def test_import_invalid_signature(self):
        bridge = make_simple_bridge()
        att = make_attestation(key="wrong-key")
        result = bridge.import_attestation(att)
        assert result["accepted"] is False
        assert result["reason"] == "invalid_signature"

    def test_import_replay_detection(self):
        bridge = make_simple_bridge()
        att = make_attestation()
        # First import succeeds
        r1 = bridge.import_attestation(att)
        assert r1["accepted"] is True
        # Second import is replay
        r2 = bridge.import_attestation(att)
        assert r2["accepted"] is False
        assert r2["reason"] == "replay_detected"

    def test_import_expired_attestation(self):
        bridge = make_simple_bridge()
        att = make_attestation(expires_at=time.time() - 3600)
        result = bridge.import_attestation(att)
        assert result["accepted"] is False
        assert result["reason"] == "expired"

    def test_import_too_old_attestation(self):
        bridge = make_simple_bridge()
        old_time = time.time() - ATTESTATION_MAX_AGE - 1
        att = make_attestation(issued_at=old_time)
        result = bridge.import_attestation(att, current_time=time.time())
        assert result["accepted"] is False
        assert result["reason"] == "too_old"

    def test_import_replaces_same_issuer(self):
        bridge = make_simple_bridge()
        att1 = make_attestation(composite=0.7, issued_at=time.time() - 100)
        att2 = make_attestation(composite=0.9, issued_at=time.time())
        bridge.import_attestation(att1)
        bridge.import_attestation(att2)
        # Only one attestation from repo-a for alice
        attestations = bridge._foreign_attestations.get("alice", [])
        repo_a_atts = [a for a in attestations if a.issuer_repo == "repo-a"]
        assert len(repo_a_atts) == 1
        assert repo_a_atts[0].composite == 0.9

    def test_foreign_trust_no_attestations(self):
        bridge = make_simple_bridge()
        assert bridge.foreign_trust("unknown_agent") == BASE_TRUST

    def test_foreign_trust_with_attestations(self):
        bridge = make_simple_bridge()
        att = make_attestation(composite=0.8)
        bridge.import_attestation(att)
        foreign = bridge.foreign_trust("alice")
        assert abs(foreign - 0.8) < 1e-6

    def test_fleet_composite_trust_no_foreign(self):
        bridge = make_simple_bridge(local_trust=0.7)
        # No foreign attestations → returns local only
        assert bridge.fleet_composite_trust("alice") == 0.7

    def test_fleet_composite_trust_with_foreign(self):
        bridge = make_simple_bridge(local_trust=0.7, import_factor=0.3)
        att = make_attestation(composite=0.9)
        bridge.import_attestation(att)
        fleet = bridge.fleet_composite_trust("alice")
        # Expected: 0.7 * 0.7 + 0.9 * 0.3 = 0.49 + 0.27 = 0.76
        expected = 0.7 * 0.7 + 0.9 * 0.3
        assert abs(fleet - expected) < 1e-6

    def test_fleet_composite_trust_clamped(self):
        bridge = make_simple_bridge(local_trust=1.0, import_factor=1.0)
        att = make_attestation(composite=1.0)
        bridge.import_attestation(att)
        fleet = bridge.fleet_composite_trust("alice")
        assert 0.0 <= fleet <= 1.0

    def test_inconsistency_detection(self):
        bridge = make_simple_bridge(local_trust=0.9)
        att_a = make_attestation(issuer_repo="repo-a", composite=0.8)
        att_b = make_attestation(issuer_repo="repo-b", composite=0.2)
        bridge.import_attestation(att_a)
        bridge.import_attestation(att_b)
        reports = bridge.detect_inconsistencies()
        assert len(reports) >= 1
        assert reports[0].flagged is True
        assert reports[0].max_difference > INCONSISTENCY_THRESHOLD

    def test_inconsistency_no_flag_when_close(self):
        bridge = make_simple_bridge(local_trust=0.7)
        att_a = make_attestation(issuer_repo="repo-a", composite=0.65)
        att_b = make_attestation(issuer_repo="repo-b", composite=0.70)
        bridge.import_attestation(att_a)
        bridge.import_attestation(att_b)
        reports = bridge.detect_inconsistencies()
        assert len(reports) == 1
        assert reports[0].flagged is False

    def test_trust_consensus(self):
        bridge = make_simple_bridge(local_trust=0.7)
        att = make_attestation(composite=0.9)
        bridge.import_attestation(att)
        consensus = bridge.trust_consensus("alice")
        assert consensus["local_trust"] == 0.7
        assert consensus["foreign_trust"] == 0.9
        assert "fleet_trust" in consensus
        assert "consensus_score" in consensus
        assert consensus["source_count"] == 2

    def test_trust_consensus_single_source(self):
        bridge = make_simple_bridge(local_trust=0.7)
        consensus = bridge.trust_consensus("alice")
        assert consensus["consensus_score"] == 1.0

    def test_prune_stale(self):
        bridge = make_simple_bridge()
        # Fresh attestation
        att_fresh = make_attestation(issued_at=time.time())
        bridge.import_attestation(att_fresh)
        # Manually add an expired one
        old_att = make_attestation(
            issuer_repo="repo-old",
            issued_at=time.time() - ATTESTATION_MAX_AGE - 100,
        )
        old_att.sign()
        bridge._foreign_attestations["alice"].append(old_att)

        before = len(bridge._foreign_attestations.get("alice", []))
        removed = bridge.prune_stale_attestations()
        after = len(bridge._foreign_attestations.get("alice", []))
        assert before > after
        assert removed >= 1

    def test_export_attestation(self):
        bridge = make_simple_bridge()
        att = bridge.export_attestation(
            agent_name="alice",
            trust_getter=lambda dim: 0.8,
            composite_getter=lambda: 0.8,
            event_count_getter=lambda: 10,
            meaningful_getter=lambda: True,
        )
        assert att.agent_name == "alice"
        assert att.issuer_repo == "local"
        assert att.verify() is True
        assert att.composite == 0.8

    def test_stats(self):
        bridge = make_simple_bridge()
        att = make_attestation()
        bridge.import_attestation(att)
        stats = bridge.stats()
        assert stats["total_imports"] == 1
        assert stats["agents_with_foreign_trust"] == 1

    def test_to_dict_roundtrip(self):
        bridge = make_simple_bridge()
        att = make_attestation(composite=0.85)
        bridge.import_attestation(att)
        d = bridge.to_dict()
        bridge2 = FleetTrustBridge.from_dict(d, trust_getter=make_trust_getter(0.7))
        assert bridge2.local_repo == bridge.local_repo
        assert bridge2.import_factor == bridge.import_factor
        assert "alice" in bridge2._foreign_attestations

    def test_agents_with_foreign_trust(self):
        bridge = make_simple_bridge()
        assert bridge.agents_with_foreign_trust() == []
        bridge.import_attestation(make_attestation(agent_name="alice"))
        bridge.import_attestation(make_attestation(agent_name="bob"))
        agents = bridge.agents_with_foreign_trust()
        assert "alice" in agents
        assert "bob" in agents

    def test_import_batch(self):
        bridge = make_simple_bridge()
        atts = [
            make_attestation(agent_name="alice", composite=0.8),
            make_attestation(agent_name="bob", composite=0.6),
            make_attestation(agent_name="carol", composite=0.9),
        ]
        result = bridge.import_attestations(atts)
        assert result["accepted_count"] == 3
        assert result["rejected_count"] == 0


# ═══════════════════════════════════════════════════════════════════════════
# 5. TrustPropagationGraph
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustPropagationGraph:
    def test_add_edge(self):
        graph = TrustPropagationGraph()
        edge = graph.add_edge("alice", "bob", 0.8)
        assert edge.source == "alice"
        assert edge.target == "bob"
        assert edge.trust_value == 0.8
        assert graph.has_agent("alice")
        assert graph.has_agent("bob")
        assert graph.edge_count() == 1

    def test_remove_edge(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        assert graph.remove_edge("alice", "bob") is True
        assert graph.edge_count() == 0
        assert graph.remove_edge("alice", "bob") is False

    def test_get_edge(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        edge = graph.get_edge("alice", "bob")
        assert edge is not None
        assert edge.trust_value == 0.8
        assert graph.get_edge("bob", "alice") is None

    def test_get_outgoing(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("alice", "carol", 0.6)
        outgoing = graph.get_outgoing("alice")
        assert "bob" in outgoing
        assert "carol" in outgoing
        assert len(outgoing) == 2

    def test_get_incoming(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "carol", 0.8)
        graph.add_edge("bob", "carol", 0.7)
        incoming = graph.get_incoming("carol")
        assert "alice" in incoming
        assert "bob" in incoming

    def test_trust_value_clamped(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 1.5)
        assert graph.get_edge("alice", "bob").trust_value == 1.0
        graph.add_edge("bob", "carol", -0.5)
        assert graph.get_edge("bob", "carol").trust_value == 0.0

    def test_discount_operator(self):
        # If A trusts B at 0.8 and B trusts C at 0.9
        # A's derived trust in C = 0.8 * 0.9 = 0.72
        result = TrustPropagationGraph.discount(0.8, 0.9)
        assert abs(result - 0.72) < 1e-9

    def test_discount_zero(self):
        assert TrustPropagationGraph.discount(0.0, 0.9) == 0.0
        assert TrustPropagationGraph.discount(0.8, 0.0) == 0.0

    def test_discount_one(self):
        assert TrustPropagationGraph.discount(1.0, 0.8) == 0.8

    def test_fuse_operator(self):
        # Two agents both trust target at 0.8
        # fused = 1 - (1 - 0.8)^2 = 1 - 0.04 = 0.96
        result = TrustPropagationGraph.fuse([0.8, 0.8])
        expected = 1.0 - (1.0 - 0.8) ** 2
        assert abs(result - expected) < 1e-9

    def test_fuse_empty(self):
        assert TrustPropagationGraph.fuse([]) == BASE_TRUST

    def test_fuse_single(self):
        assert TrustPropagationGraph.fuse([0.8]) == 0.8

    def test_find_trust_paths_simple(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("bob", "carol", 0.7)
        paths = graph.find_trust_paths("alice", "carol")
        assert len(paths) == 1
        assert paths[0] == ["alice", "bob", "carol"]

    def test_find_trust_paths_multiple(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("alice", "carol", 0.7)
        graph.add_edge("bob", "dave", 0.6)
        graph.add_edge("carol", "dave", 0.9)
        paths = graph.find_trust_paths("alice", "dave")
        assert len(paths) == 2

    def test_find_trust_paths_no_path(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        paths = graph.find_trust_paths("alice", "carol")
        assert paths == []

    def test_find_trust_paths_max_depth(self):
        graph = TrustPropagationGraph()
        graph.add_edge("a", "b", 0.8)
        graph.add_edge("b", "c", 0.8)
        graph.add_edge("c", "d", 0.8)
        paths = graph.find_trust_paths("a", "d", max_depth=2)
        assert paths == []  # Needs depth 3

    def test_find_trust_paths_same_agent(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "alice", 0.5)
        paths = graph.find_trust_paths("alice", "alice")
        assert paths == [["alice"]]

    def test_shortest_trust_path(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.5)
        graph.add_edge("alice", "carol", 0.8)
        graph.add_edge("carol", "dave", 0.9)
        graph.add_edge("bob", "dave", 0.7)
        shortest = graph.shortest_trust_path("alice", "dave")
        assert shortest is not None
        assert len(shortest) == 3  # alice -> bob -> dave

    def test_shortest_trust_path_none(self):
        graph = TrustPropagationGraph()
        assert graph.shortest_trust_path("alice", "bob") is None

    def test_derived_trust_direct(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        derived = graph.derived_trust("alice", "bob")
        assert abs(derived - 0.8) < 1e-6

    def test_derived_trust_transitive(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("bob", "carol", 0.9)
        derived = graph.derived_trust("alice", "carol")
        # Discount: 1.0 * 0.8 = 0.8, then 0.8 * 0.9 = 0.72
        expected = TrustPropagationGraph.discount(1.0, 0.8)
        expected = TrustPropagationGraph.discount(expected, 0.9)
        assert abs(derived - expected) < 1e-6

    def test_derived_trust_no_path(self):
        graph = TrustPropagationGraph()
        assert graph.derived_trust("alice", "bob") == BASE_TRUST

    def test_detect_cycles(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("bob", "carol", 0.7)
        graph.add_edge("carol", "alice", 0.9)
        cycles = graph.detect_cycles()
        assert len(cycles) >= 1

    def test_detect_cycles_none(self):
        graph = TrustPropagationGraph()
        graph.add_edge("a", "b", 0.8)
        graph.add_edge("b", "c", 0.7)
        cycles = graph.detect_cycles()
        assert len(cycles) == 0

    def test_detect_echo_chambers(self):
        graph = TrustPropagationGraph()
        # Create a tight cluster where agents mostly trust each other
        graph.add_edge("alice", "bob", 0.9, repo="echo-repo")
        graph.add_edge("bob", "alice", 0.9, repo="echo-repo")
        graph.add_edge("bob", "carol", 0.8, repo="echo-repo")
        graph.add_edge("carol", "alice", 0.8, repo="echo-repo")
        graph.add_edge("carol", "bob", 0.8, repo="echo-repo")
        graph.add_edge("alice", "carol", 0.8, repo="echo-repo")
        chambers = graph.detect_echo_chambers(inward_ratio=0.5)
        assert len(chambers) >= 1

    def test_detect_echo_chambers_no_chambers(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.5)
        graph.add_edge("alice", "carol", 0.5)
        graph.add_edge("alice", "dave", 0.5)
        chambers = graph.detect_echo_chambers()
        assert len(chambers) == 0

    def test_density_empty(self):
        graph = TrustPropagationGraph()
        assert graph.density() == 0.0

    def test_density_single_agent(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.5)
        # 2 agents, 1 edge: density = 1 / (2*1) = 0.5
        assert abs(graph.density() - 0.5) < 1e-9

    def test_clustering_coefficient(self):
        graph = TrustPropagationGraph()
        # Alice trusts Bob and Carol; Bob trusts Carol → triangle
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("alice", "carol", 0.7)
        graph.add_edge("bob", "carol", 0.9)
        cc = graph.clustering_coefficient("alice")
        assert cc == 1.0  # All pairs of alice's targets are connected

    def test_clustering_coefficient_no_triangle(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("alice", "carol", 0.7)
        cc = graph.clustering_coefficient("alice")
        assert cc == 0.0

    def test_hub_score(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.9)
        graph.add_edge("carol", "bob", 0.8)
        graph.add_edge("dave", "bob", 0.7)
        hub = graph.trust_hub_score("bob")
        assert hub > 0
        # Bob has no incoming trust
        assert graph.trust_hub_score("alice") == 0.0

    def test_fleet_metrics(self):
        graph = TrustPropagationGraph()
        graph.add_edge("a", "b", 0.8)
        graph.add_edge("b", "c", 0.7)
        metrics = graph.fleet_metrics()
        assert metrics["agent_count"] == 3
        assert metrics["edge_count"] == 2
        assert "density" in metrics
        assert "average_clustering" in metrics
        assert "cycle_count" in metrics

    def test_agent_trust_summary(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("carol", "alice", 0.9)
        summary = graph.agent_trust_summary("alice")
        assert summary["agent"] == "alice"
        assert summary["outgoing_count"] == 1
        assert summary["incoming_count"] == 1
        assert "bob" in summary["trusts"]
        assert "carol" in summary["trusted_by"]

    def test_to_dict_roundtrip(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "bob", 0.8)
        graph.add_edge("bob", "carol", 0.7)
        d = graph.to_dict()
        graph2 = TrustPropagationGraph.from_dict(d)
        assert graph2.edge_count() == 2
        assert graph2.has_agent("alice")
        assert graph2.has_agent("bob")
        assert graph2.has_agent("carol")
        edge = graph2.get_edge("alice", "bob")
        assert edge is not None
        assert edge.trust_value == 0.8

    def test_empty_graph_metrics(self):
        graph = TrustPropagationGraph()
        metrics = graph.fleet_metrics()
        assert metrics["agent_count"] == 0
        assert metrics["edge_count"] == 0
        assert metrics["density"] == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 6. CrossRepoTrustSync
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossRepoTrustSync:
    def test_init_defaults(self):
        sync = CrossRepoTrustSync(local_repo="my-repo")
        assert sync.local_repo == "my-repo"
        assert sync.bridge is not None
        assert sync.graph is not None

    def test_trust_anchor_management(self):
        sync = CrossRepoTrustSync()
        sync.add_trust_anchor("trusted-repo")
        assert sync.is_trust_anchor("trusted-repo")
        sync.remove_trust_anchor("trusted-repo")
        assert not sync.is_trust_anchor("trusted-repo")

    def test_export_trust(self):
        sync = CrossRepoTrustSync(local_repo="repo-a")
        att = sync.export_trust(
            agent_name="alice",
            trust_getter=lambda dim: 0.8,
            composite_getter=lambda: 0.8,
            event_count_getter=lambda: 10,
            meaningful_getter=lambda: True,
            cross_repo_events=["fleet_collaboration"],
        )
        assert att.agent_name == "alice"
        assert att.issuer_repo == "repo-a"
        assert att.verify() is True
        assert att.composite == 0.8
        assert att.cross_repo_events == ["fleet_collaboration"]

    def test_export_batch(self):
        sync = CrossRepoTrustSync(local_repo="repo-a")
        agents = [
            ("alice", lambda dim: 0.8, lambda: 0.8),
            ("bob", lambda dim: 0.6, lambda: 0.6),
        ]
        atts = sync.export_batch(agents)
        assert len(atts) == 2
        assert all(a.verify() for a in atts)

    def test_import_trust_valid(self):
        sync = CrossRepoTrustSync(local_repo="local")
        att = make_attestation(issuer_repo="repo-a", composite=0.8)
        result = sync.import_trust(att)
        assert result["accepted"] is True

    def test_import_trust_invalid_signature(self):
        sync = CrossRepoTrustSync()
        att = make_attestation(key="wrong-key")
        result = sync.import_trust(att)
        assert result["accepted"] is False
        assert result["reason"] == "invalid_signature"

    def test_import_trust_replay(self):
        sync = CrossRepoTrustSync()
        att = make_attestation()
        r1 = sync.import_trust(att)
        assert r1["accepted"] is True
        r2 = sync.import_trust(att)
        assert r2["accepted"] is False
        assert r2["reason"] == "replay_detected"

    def test_import_trust_anchor_relayed_validation(self):
        sync = CrossRepoTrustSync(local_repo="local")
        sync.add_trust_anchor("anchor-repo")

        # Anchor attestation that would normally be too old
        old_time = time.time() - ATTESTATION_MAX_AGE - 100
        att = make_attestation(
            issuer_repo="anchor-repo",
            composite=0.9,
            issued_at=old_time,
        )
        # Should be accepted because it's from a trust anchor
        result = sync.import_trust(att)
        assert result["accepted"] is True

    def test_import_updates_graph(self):
        sync = CrossRepoTrustSync()
        att = make_attestation(issuer_repo="repo-a", agent_name="alice", composite=0.8)
        sync.import_trust(att)
        edge = sync.graph.get_edge("repo-a", "alice")
        assert edge is not None
        assert edge.trust_value == 0.8

    def test_import_batch(self):
        sync = CrossRepoTrustSync()
        atts = [
            make_attestation(agent_name="alice", composite=0.8),
            make_attestation(agent_name="bob", composite=0.6),
            make_attestation(agent_name="carol", composite=0.9),
        ]
        result = sync.import_batch(atts)
        assert result.accepted == 3
        assert result.rejected == 0
        assert result.total_received == 3

    def test_import_batch_with_invalid(self):
        sync = CrossRepoTrustSync()
        atts = [
            make_attestation(agent_name="alice", composite=0.8),
            make_attestation(agent_name="bob", composite=0.6, key="wrong-key"),
        ]
        result = sync.import_batch(atts)
        assert result.accepted == 1
        assert result.rejected == 1
        assert "invalid_signature" in result.rejection_reasons

    def test_sync_graph_edges(self):
        sync = CrossRepoTrustSync()
        edges = [
            {"source": "a", "target": "b", "trust_value": 0.8, "repo": "repo-x"},
            {"source": "b", "target": "c", "trust_value": 0.7, "repo": "repo-x"},
        ]
        added = sync.sync_graph_edges(edges)
        assert added == 2
        assert sync.graph.edge_count() == 2

    def test_export_graph_edges(self):
        sync = CrossRepoTrustSync()
        sync.graph.add_edge("a", "b", 0.8, repo="repo-x")
        sync.graph.add_edge("c", "d", 0.7, repo="repo-y")
        edges = sync.export_graph_edges()
        assert len(edges) == 2
        filtered = sync.export_graph_edges(repo_filter="repo-x")
        assert len(filtered) == 1

    def test_perform_sync(self):
        sync = CrossRepoTrustSync(local_repo="local")
        atts = [
            make_attestation(agent_name="alice", composite=0.8),
            make_attestation(agent_name="bob", composite=0.6),
        ]
        edges = [{"source": "repo-a", "target": "alice", "trust_value": 0.8}]
        result = sync.perform_sync(remote_attestations=atts, remote_edges=edges)
        assert result.accepted == 2
        assert hasattr(result, "inconsistencies")

    def test_get_replay_log(self):
        sync = CrossRepoTrustSync()
        att = make_attestation()
        sync.import_trust(att)
        sync.import_trust(att)  # Replay
        log = sync.get_replay_log()
        assert len(log) >= 1
        assert log[0]["type"] == "replay"

    def test_stats(self):
        sync = CrossRepoTrustSync(local_repo="my-repo")
        sync.add_trust_anchor("anchor-1")
        sync.add_trust_anchor("anchor-2")
        att = make_attestation()
        sync.import_trust(att)
        stats = sync.stats()
        assert stats["local_repo"] == "my-repo"
        assert len(stats["trust_anchors"]) == 2
        assert stats["bridge"]["total_imports"] == 1

    def test_to_dict_roundtrip(self):
        sync = CrossRepoTrustSync(local_repo="test-repo")
        sync.add_trust_anchor("anchor-repo")
        att = make_attestation(agent_name="alice", composite=0.8)
        sync.import_trust(att)
        d = sync.to_dict()
        sync2 = CrossRepoTrustSync.from_dict(d, trust_getter=make_trust_getter(0.7))
        assert sync2.local_repo == "test-repo"
        assert "anchor-repo" in sync2.trust_anchors
        assert "alice" in sync2.bridge._foreign_attestations


# ═══════════════════════════════════════════════════════════════════════════
# 7. TrustEdge
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustEdge:
    def test_opinion_components_sum_to_one(self):
        edge = TrustEdge(source="a", target="b", trust_value=0.7)
        b, d, u = edge.opinion
        assert abs(b + d + u - 1.0) < 1e-9

    def test_belief_equals_trust_value(self):
        edge = TrustEdge(source="a", target="b", trust_value=0.8)
        assert edge.belief == 0.8

    def test_zero_trust_opinion(self):
        edge = TrustEdge(source="a", target="b", trust_value=0.0)
        b, d, u = edge.opinion
        assert b == 0.0
        assert d == 0.5
        assert u == 0.5

    def test_full_trust_opinion(self):
        edge = TrustEdge(source="a", target="b", trust_value=1.0)
        b, d, u = edge.opinion
        assert b == 1.0
        assert d == 0.0
        assert u == 0.0

    def test_to_dict_roundtrip(self):
        edge = TrustEdge(source="alice", target="bob", trust_value=0.75, repo="repo-a")
        d = edge.to_dict()
        edge2 = TrustEdge.from_dict(d)
        assert edge2.source == "alice"
        assert edge2.target == "bob"
        assert edge2.trust_value == 0.75
        assert edge2.repo == "repo-a"


# ═══════════════════════════════════════════════════════════════════════════
# 8. InconsistencyReport
# ═══════════════════════════════════════════════════════════════════════════

class TestInconsistencyReport:
    def test_to_dict(self):
        report = InconsistencyReport(
            agent_name="alice",
            repo_scores={"repo-a": 0.8, "repo-b": 0.2, "local": 0.7},
            max_difference=0.6,
            flagged=True,
            description="Test inconsistency",
        )
        d = report.to_dict()
        assert d["agent_name"] == "alice"
        assert d["flagged"] is True
        assert d["max_difference"] == 0.6


# ═══════════════════════════════════════════════════════════════════════════
# 9. SyncResult
# ═══════════════════════════════════════════════════════════════════════════

class TestSyncResult:
    def test_defaults(self):
        result = SyncResult()
        assert result.total_sent == 0
        assert result.accepted == 0
        assert result.rejected == 0
        assert result.rejection_reasons == {}

    def test_to_dict(self):
        result = SyncResult(accepted=3, rejected=1)
        result.rejection_reasons["invalid_signature"] = 1
        d = result.to_dict()
        assert d["accepted"] == 3
        assert d["rejected"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 10. Edge Cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_empty_bridge_fleet_composite(self):
        bridge = FleetTrustBridge()  # No trust_getter
        result = bridge.fleet_composite_trust("unknown")
        assert result == BASE_TRUST

    def test_empty_bridge_inconsistency(self):
        bridge = FleetTrustBridge()
        reports = bridge.detect_inconsistencies()
        assert reports == []

    def test_empty_graph_derived_trust(self):
        graph = TrustPropagationGraph()
        assert graph.derived_trust("alice", "bob") == BASE_TRUST

    def test_empty_graph_paths(self):
        graph = TrustPropagationGraph()
        assert graph.find_trust_paths("alice", "bob") == []

    def test_empty_sync_stats(self):
        sync = CrossRepoTrustSync()
        stats = sync.stats()
        assert stats["bridge"]["total_imports"] == 0
        assert stats["replay_attacks_detected"] == 0

    def test_attestation_fingerprint_different_timestamps(self):
        att1 = TrustAttestation(agent_name="alice", issued_at=1000000.0)
        att2 = TrustAttestation(agent_name="alice", issued_at=2000000.0)
        assert att1.compute_fingerprint() != att2.compute_fingerprint()

    def test_bridge_no_trust_getter(self):
        bridge = FleetTrustBridge()  # No trust_getter
        assert bridge._get_local_trust("anyone") == BASE_TRUST

    def test_bridge_import_factor_clamped_high(self):
        bridge = FleetTrustBridge(import_factor=2.0)
        assert bridge.import_factor == 1.0

    def test_bridge_import_factor_clamped_low(self):
        bridge = FleetTrustBridge(import_factor=-0.5)
        assert bridge.import_factor == 0.0

    def test_attestation_verification_with_empty_fingerprint(self):
        att = make_attestation()
        att.fingerprint = ""  # Clear fingerprint but keep valid signature
        # Should still verify because the content hash matches
        assert att.verify() is True

    def test_attestation_tampered_dimensions(self):
        att = make_attestation(composite=0.8)
        att.dimensions["code_quality"] = 0.1  # tamper
        assert att.verify() is False

    def test_graph_self_loop(self):
        graph = TrustPropagationGraph()
        graph.add_edge("alice", "alice", 0.5)
        paths = graph.find_trust_paths("alice", "alice")
        assert paths == [["alice"]]

    def test_multiple_attestations_same_agent_different_repos(self):
        bridge = make_simple_bridge(local_trust=0.5, import_factor=0.5)
        att_a = make_attestation(issuer_repo="repo-a", composite=0.9)
        att_b = make_attestation(issuer_repo="repo-b", composite=0.7)
        bridge.import_attestation(att_a)
        bridge.import_attestation(att_b)
        foreign = bridge.foreign_trust("alice")
        # Should be weighted average of 0.9 and 0.7
        assert 0.7 <= foreign <= 0.9

    def test_expired_attestation_pruned_from_consensus(self):
        bridge = make_simple_bridge(local_trust=0.5)
        att = make_attestation(issuer_repo="repo-a", composite=0.9)
        bridge.import_attestation(att)
        # Manually expire it
        att.expires_at = time.time() - 1
        # Foreign trust should fall back to BASE_TRUST since it's expired
        foreign = bridge.foreign_trust("alice")
        assert foreign == BASE_TRUST

    def test_sync_roundtrip_with_graph(self):
        sync = CrossRepoTrustSync(local_repo="repo-a")
        # Export
        att = sync.export_trust(
            agent_name="alice",
            trust_getter=lambda dim: 0.85,
            composite_getter=lambda: 0.85,
        )
        # Import into another sync instance
        sync2 = CrossRepoTrustSync(local_repo="repo-b")
        result = sync2.import_trust(att)
        assert result["accepted"] is True
        # Verify bridge received it
        assert abs(sync2.bridge.foreign_trust("alice") - 0.85) < 0.01
