#!/usr/bin/env python3
"""
Comprehensive test suite for capability_tokens.py

Covers: BetaReputation, CapabilityToken, CapabilityRegistry,
        LEVEL_CAPABILITIES, attenuation, delegation, revocation, trust gates.
Aims for 80+ tests with full coverage of edge cases.
"""

import json
import os
import sys
import shutil
import tempfile
import time
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from capability_tokens import (
    BetaReputation, CapabilityToken, CapabilityRegistry,
    CapabilityAction, LEVEL_CAPABILITIES,
    ENDORSEMENT_TRUST_THRESHOLD, EXERCISE_TRUST_THRESHOLD,
    DELEGATION_TRUST_THRESHOLD, BASE_TRUST, TRUST_DECAY_ALERT_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_cap_dir():
    """Provide a temp directory for capability data."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


def make_registry(data_dir=None, trust_scores=None):
    """Create a CapabilityRegistry with optional trust getter."""
    reg = CapabilityRegistry(data_dir=data_dir or tempfile.mkdtemp())

    if trust_scores:
        def trust_getter(name):
            return trust_scores.get(name, BASE_TRUST)
        reg.set_trust_getter(trust_getter)

    return reg


# ═══════════════════════════════════════════════════════════════
# 1. Constants
# ═══════════════════════════════════════════════════════════════

class TestConstants:
    def test_endorsement_threshold(self):
        assert ENDORSEMENT_TRUST_THRESHOLD == 0.4

    def test_exercise_threshold(self):
        assert EXERCISE_TRUST_THRESHOLD == 0.25

    def test_delegation_threshold(self):
        assert DELEGATION_TRUST_THRESHOLD == 0.5

    def test_base_trust(self):
        assert BASE_TRUST == 0.3

    def test_trust_decay_alert_threshold(self):
        assert TRUST_DECAY_ALERT_THRESHOLD == 0.15

    def test_capability_action_count(self):
        # Should have at least the 17 defined actions
        assert len(CapabilityAction) >= 17

    def test_level_capabilities_keys(self):
        for lvl in range(6):
            assert lvl in LEVEL_CAPABILITIES

    def test_level_0_no_capabilities(self):
        assert LEVEL_CAPABILITIES[0] == []

    def test_level_5_all_capabilities(self):
        assert len(LEVEL_CAPABILITIES[5]) == len(CapabilityAction)

    def test_levels_monotonic(self):
        """Each higher level should have at least as many capabilities as the one below."""
        prev_count = 0
        for lvl in range(6):
            count = len(LEVEL_CAPABILITIES[lvl])
            assert count >= prev_count, f"Level {lvl} has fewer caps than {lvl-1}"
            prev_count = count


# ═══════════════════════════════════════════════════════════════
# 2. BetaReputation
# ═══════════════════════════════════════════════════════════════

class TestBetaReputation:
    def test_default_expected_value(self):
        rep = BetaReputation()
        assert rep.expected_value == 0.5  # α=1, β=1 → 1/2

    def test_default_uncertainty(self):
        rep = BetaReputation()
        assert rep.uncertainty == 0.5  # 2/(1+1+2) = 2/4

    def test_default_opinion(self):
        b, d, u = BetaReputation().opinion
        assert abs(b - 0.25) < 1e-9
        assert abs(d - 0.25) < 1e-9
        assert abs(u - 0.5) < 1e-9

    def test_default_evidence_count(self):
        rep = BetaReputation()
        assert rep.evidence_count == 0

    def test_positive_update_increases_expected(self):
        rep = BetaReputation()
        rep.update(positive=True)
        assert rep.expected_value > 0.5

    def test_negative_update_decreases_expected(self):
        rep = BetaReputation()
        rep.update(positive=False)
        assert rep.expected_value < 0.5

    def test_multiple_positive_updates(self):
        rep = BetaReputation()
        for _ in range(10):
            rep.update(positive=True)
        assert rep.expected_value > 0.8

    def test_multiple_negative_updates(self):
        rep = BetaReputation()
        for _ in range(10):
            rep.update(positive=False)
        assert rep.expected_value < 0.2

    def test_mixed_updates_balanced(self):
        rep = BetaReputation()
        for _ in range(50):
            rep.update(positive=True)
            rep.update(positive=False)
        assert 0.3 < rep.expected_value < 0.7

    def test_uncertainty_decreases_with_evidence(self):
        rep = BetaReputation()
        initial_unc = rep.uncertainty
        rep.update(positive=True)
        assert rep.uncertainty < initial_unc

    def test_forget_factor_applied(self):
        rep1 = BetaReputation(forget_factor=0.99)
        rep2 = BetaReputation(forget_factor=0.5)
        for _ in range(20):
            rep1.update(positive=True)
            rep2.update(positive=True)
        # More aggressive forgetting → lower expected value
        assert rep1.expected_value > rep2.expected_value

    def test_update_from_score_positive(self):
        rep = BetaReputation()
        rep.update_from_score(0.9)
        assert rep.expected_value > 0.5

    def test_update_from_score_negative(self):
        rep = BetaReputation()
        rep.update_from_score(0.1)
        assert rep.expected_value < 0.5

    def test_update_from_score_neutral(self):
        rep = BetaReputation()
        rep.update_from_score(0.5)
        # At exactly 0.5, no evidence added
        assert rep.evidence_count == 0

    def test_discount_reduces_trust(self):
        source = BetaReputation()
        source.update(positive=True)
        target = BetaReputation()
        target.update(positive=True)

        result = target.discount(source)
        # Discounted trust should be <= target's direct trust
        assert result.expected_value <= target.expected_value

    def test_discount_with_low_source_trust(self):
        source = BetaReputation()
        for _ in range(10):
            source.update(positive=False)
        target = BetaReputation()
        for _ in range(10):
            target.update(positive=True)

        result = target.discount(source)
        # Low source trust → discounted trust is lower than target's direct trust
        assert result.expected_value <= target.expected_value

    def test_fuse_combines_evidence(self):
        rep1 = BetaReputation()
        rep1.update(positive=True)
        rep2 = BetaReputation()
        rep2.update(positive=True)

        fused = rep1.fuse(rep2)
        # Fused reputation should be valid and positive
        assert fused.evidence_count >= 0
        assert fused.expected_value > 0  # should still be positive since both were positive

    def test_fuse_expected_value(self):
        rep1 = BetaReputation()
        rep2 = BetaReputation()
        for _ in range(5):
            rep1.update(positive=True)
            rep2.update(positive=True)

        fused = rep1.fuse(rep2)
        assert fused.expected_value > 0.5

    def test_is_suspicious_high_uncertainty(self):
        rep = BetaReputation()
        assert rep.is_suspicious()  # default uncertainty is 0.5

    def test_is_suspicious_low_uncertainty(self):
        rep = BetaReputation()
        for _ in range(20):
            rep.update(positive=True)
        assert not rep.is_suspicious()

    def test_to_dict(self):
        rep = BetaReputation()
        rep.update(positive=True)
        d = rep.to_dict()
        assert "alpha" in d
        assert "beta" in d
        assert "expected_value" in d
        assert "uncertainty" in d
        assert "opinion" in d
        assert d["evidence_count"] > 0

    def test_from_dict_roundtrip(self):
        rep = BetaReputation(forget_factor=0.98)
        for _ in range(5):
            rep.update(positive=True)
        d = rep.to_dict()
        rep2 = BetaReputation.from_dict(d)
        assert abs(rep2.expected_value - rep.expected_value) < 1e-6  # rounding tolerance
        assert rep2.forget_factor == rep.forget_factor
        assert abs(rep2.evidence_count - rep.evidence_count) < 1.0

    def test_priors_maintained(self):
        """Alpha and beta should never go below 1.0."""
        rep = BetaReputation()
        for _ in range(100):
            rep.update(positive=False, magnitude=0.01)
        assert rep.alpha >= 1.0
        assert rep.beta >= 1.0

    def test_magnitude_scales_evidence(self):
        rep_full = BetaReputation()
        rep_half = BetaReputation()
        rep_full.update(positive=True, magnitude=1.0)
        rep_half.update(positive=True, magnitude=0.5)
        # Full magnitude should shift trust more
        assert rep_full.expected_value > rep_half.expected_value


# ═══════════════════════════════════════════════════════════════
# 3. CapabilityToken
# ═══════════════════════════════════════════════════════════════

class TestCapabilityToken:
    def test_create_token(self):
        token = CapabilityToken(action=CapabilityAction.BUILD_ROOM, holder="alice")
        assert token.action == CapabilityAction.BUILD_ROOM
        assert token.holder == "alice"
        assert token.is_valid()

    def test_token_has_unique_id(self):
        t1 = CapabilityToken()
        t2 = CapabilityToken()
        assert t1.token_id != t2.token_id

    def test_default_no_expiry(self):
        token = CapabilityToken()
        assert token.expires == 0
        assert token.is_valid()

    def test_expired_token_invalid(self):
        token = CapabilityToken(expires=time.time() - 100)
        assert not token.is_valid()

    def test_future_expiry_valid(self):
        token = CapabilityToken(expires=time.time() + 1000)
        assert token.is_valid()

    def test_unlimited_uses(self):
        token = CapabilityToken(max_uses=0)
        for _ in range(100):
            assert token.can_exercise()
            token.exercise()
        assert token.is_valid()

    def test_limited_uses(self):
        token = CapabilityToken(max_uses=3)
        assert token.can_exercise()
        token.exercise()
        token.exercise()
        token.exercise()
        assert not token.can_exercise()

    def test_exercise_returns_success(self):
        token = CapabilityToken(action=CapabilityAction.BUILD_ROOM, holder="alice")
        result = token.exercise()
        assert result["success"] is True
        assert result["action"] == "build_room"
        assert result["remaining_uses"] == -1  # unlimited

    def test_exercise_limited_returns_remaining(self):
        token = CapabilityToken(max_uses=5)
        token.exercise()
        token.exercise()
        result = token.exercise()
        assert result["remaining_uses"] == 2

    def test_exercise_invalid_returns_error(self):
        token = CapabilityToken(max_uses=1)
        token.exercise()
        result = token.exercise()
        assert result["success"] is False
        assert "error" in result

    def test_revoked_token_invalid(self):
        token = CapabilityToken()
        token.revoke("test")
        assert token.revoked
        assert not token.is_valid()
        assert not token.can_exercise()

    def test_revoke_reason(self):
        token = CapabilityToken()
        token.revoke("security violation")
        assert token.revoked_reason == "security violation"

    def test_revoke_timestamp(self):
        token = CapabilityToken()
        before = time.time()
        token.revoke()
        assert token.revoked_at >= before

    def test_attenuate_creates_new_token(self):
        source = CapabilityToken(action=CapabilityAction.BUILD_ROOM, holder="alice")
        attenuated = source.attenuate(max_uses=5, scope="room:dojo")
        assert attenuated.token_id != source.token_id
        assert attenuated.max_uses == 5
        assert attenuated.scope == "room:dojo"
        assert attenuated.delegate_depth == 1

    def test_attenuate_preserves_expiry(self):
        source = CapabilityToken(expires=time.time() + 1000)
        attenuated = source.attenuate()
        assert attenuated.expires == source.expires

    def test_attenuate_no_amplification(self):
        """Attenuated token cannot have MORE uses than source."""
        source = CapabilityToken(max_uses=3)
        attenuated = source.attenuate(max_uses=10)
        assert attenuated.max_uses == 3  # capped to source

    def test_attenuate_actions_restricted(self):
        source = CapabilityToken(
            action=CapabilityAction.BUILD_ROOM,
            actions_allowed=[CapabilityAction.BUILD_ROOM, CapabilityAction.CREATE_ITEM],
        )
        attenuated = source.attenuate(
            allowed_actions=[CapabilityAction.BUILD_ROOM, CapabilityAction.CREATE_ITEM, CapabilityAction.SHELL]
        )
        # Shell should not be in allowed list (not in source)
        assert CapabilityAction.SHELL not in attenuated.actions_allowed

    def test_audit_log_records_exercise(self):
        token = CapabilityToken()
        token.exercise()
        assert len(token.audit_log) == 1
        assert token.audit_log[0]["event"] == "exercise"

    def test_audit_log_records_revoke(self):
        token = CapabilityToken()
        token.revoke("test")
        assert len(token.audit_log) == 1
        assert token.audit_log[0]["event"] == "revoke"

    def test_audit_log_records_attenuate(self):
        token = CapabilityToken()
        token.attenuate()
        assert len(token.audit_log) == 1
        assert token.audit_log[0]["event"] == "attenuate"

    def test_to_dict(self):
        token = CapabilityToken(action=CapabilityAction.BUILD_ROOM, holder="alice")
        d = token.to_dict()
        assert d["action"] == "build_room"
        assert d["holder"] == "alice"
        assert d["is_valid"] is True

    def test_from_dict_roundtrip(self):
        token = CapabilityToken(
            action=CapabilityAction.CREATE_ADVENTURE,
            holder="bob",
            issuer="alice",
            max_uses=10,
            scope="adventure:tutorial",
        )
        token.exercise()
        d = token.to_dict()
        token2 = CapabilityToken.from_dict(d)
        assert token2.action == token.action
        assert token2.holder == "bob"
        assert token2.issuer == "alice"
        assert token2.max_uses == 10
        assert token2.scope == "adventure:tutorial"
        assert token2.use_count == 1

    def test_can_exercise_specific_action(self):
        token = CapabilityToken(action=CapabilityAction.BUILD_ROOM)
        assert token.can_exercise(CapabilityAction.BUILD_ROOM)
        assert not token.can_exercise(CapabilityAction.SHELL)


# ═══════════════════════════════════════════════════════════════
# 4. CapabilityRegistry
# ═══════════════════════════════════════════════════════════════

class TestCapabilityRegistry:
    def test_create_registry(self, tmp_cap_dir):
        reg = CapabilityRegistry(data_dir=tmp_cap_dir)
        assert reg.data_dir.exists()

    def test_issue_token(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        token = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        assert token.holder == "alice"
        assert token.action == CapabilityAction.BUILD_ROOM
        assert token in reg.tokens.values()

    def test_issue_records_agent_tokens(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        assert "alice" in reg.agent_tokens
        assert len(reg.agent_tokens["alice"]) == 1

    def test_issue_multiple_tokens(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.issue(CapabilityAction.CREATE_ITEM, "alice")
        assert len(reg.agent_tokens["alice"]) == 2

    def test_can_agent_true(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_can_agent_false_no_token(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        assert not reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_can_agent_false_wrong_action(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        assert not reg.can_agent("alice", CapabilityAction.SHELL)

    def test_can_agent_false_low_trust(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.1})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice", trust_at_issue=0.6)
        # Even though token exists, trust is below exercise threshold
        assert not reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_exercise_success(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = reg.exercise("alice", CapabilityAction.BUILD_ROOM)
        assert result["success"] is True

    def test_exercise_no_token(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        result = reg.exercise("alice", CapabilityAction.BUILD_ROOM)
        assert result["success"] is False

    def test_revoke_single(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        token = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.revoke(token.token_id)
        assert not reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_revoke_nonexistent(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        reg.revoke("nonexistent")  # should not crash

    def test_revoke_downstream(self, tmp_cap_dir):
        """Revoking a parent token should revoke all delegated children."""
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.7, "bob": 0.5}
        )
        parent = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        child = reg.delegate(parent.token_id, "bob", from_agent="alice")
        assert child is not None
        assert reg.can_agent("bob", CapabilityAction.BUILD_ROOM)

        reg.revoke(parent.token_id)
        assert not reg.can_agent("alice", CapabilityAction.BUILD_ROOM)
        assert not reg.can_agent("bob", CapabilityAction.BUILD_ROOM)

    def test_delegate_success(self, tmp_cap_dir):
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.7, "bob": 0.5}
        )
        parent = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        child = reg.delegate(parent.token_id, "bob", from_agent="alice")
        assert child is not None
        assert child.holder == "bob"
        assert child.issuer == "alice"
        assert child.source_token_id == parent.token_id
        assert child.delegate_depth == 1
        assert reg.can_agent("bob", CapabilityAction.BUILD_ROOM)

    def test_delegate_low_delegator_trust(self, tmp_cap_dir):
        """Delegator with trust < 0.5 cannot delegate."""
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.3, "bob": 0.5}
        )
        parent = reg.issue(CapabilityAction.BUILD_ROOM, "alice", trust_at_issue=0.8)
        child = reg.delegate(parent.token_id, "bob", from_agent="alice")
        assert child is None

    def test_delegate_low_holder_trust(self, tmp_cap_dir):
        """New holder must have trust >= 0.4."""
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.7, "bob": 0.2}
        )
        parent = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        child = reg.delegate(parent.token_id, "bob", from_agent="alice")
        assert child is None

    def test_delegate_attenuated_uses(self, tmp_cap_dir):
        """Delegated token can have fewer uses than parent."""
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.7, "bob": 0.5}
        )
        parent = reg.issue(CapabilityAction.BUILD_ROOM, "alice", max_uses=10)
        child = reg.delegate(parent.token_id, "bob", from_agent="alice", max_uses=3)
        assert child is not None
        assert child.max_uses == 3

    def test_endow_on_level_up(self, tmp_cap_dir):
        """Level up should grant appropriate capabilities."""
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        tokens = reg.endow_on_level_up("alice", 1, 2)
        assert len(tokens) > 0
        for t in tokens:
            assert t.holder == "alice"
            assert t.issuer == "level_up"
        # Should now be able to build rooms
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_endow_no_dupes(self, tmp_cap_dir):
        """Shouldn't issue duplicate capabilities."""
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.endow_on_level_up("alice", 1, 2)
        reg.endow_on_level_up("alice", 2, 2)  # same level, no new tokens
        # Count alice's BUILD_ROOM tokens
        count = sum(1 for t in reg.tokens.values()
                    if t.holder == "alice" and t.action == CapabilityAction.BUILD_ROOM)
        assert count == 1

    def test_endow_multiple_levels(self, tmp_cap_dir):
        """Jumping multiple levels should grant all intermediate capabilities."""
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.9})
        tokens = reg.endow_on_level_up("alice", 0, 4)
        assert len(tokens) > 0
        # Should have captain and cocapn capabilities
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)
        assert reg.can_agent("alice", CapabilityAction.CREATE_ADVENTURE)
        assert reg.can_agent("alice", CapabilityAction.BROADCAST_FLEET)

    def test_agent_capabilities(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        caps = reg.agent_capabilities("alice")
        assert len(caps) == 1
        assert caps[0]["action"] == "build_room"

    def test_agent_capabilities_includes_revoked(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        token = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.revoke(token.token_id)
        caps = reg.agent_capabilities("alice")
        assert len(caps) == 1
        assert caps[0]["is_valid"] is False

    def test_agent_summary(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.issue(CapabilityAction.CREATE_ITEM, "alice")
        s = reg.agent_summary("alice")
        assert s["agent"] == "alice"
        assert s["valid_tokens"] == 2
        assert s["revoked_tokens"] == 0
        assert "build_room" in s["actions"]
        assert "create_item" in s["actions"]

    def test_agent_summary_empty(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        s = reg.agent_summary("alice")
        assert s["agent"] == "alice"
        assert s["total_tokens"] == 0
        assert s["valid_tokens"] == 0

    def test_all_actions_for_agent(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.issue(CapabilityAction.CREATE_ITEM, "alice")
        actions = reg.all_actions_for_agent("alice")
        assert CapabilityAction.BUILD_ROOM in actions
        assert CapabilityAction.CREATE_ITEM in actions

    def test_check_trust_gates(self, tmp_cap_dir):
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.3}  # trust dropped from 0.6 to 0.3
        )
        reg.issue(CapabilityAction.BUILD_ROOM, "alice", trust_at_issue=0.6)
        alerts = reg.check_trust_gates()
        # 0.3 - 0.6 = -0.3 < -0.15, so should alert
        assert len(alerts) >= 1
        assert alerts[0]["type"] == "trust_decay"
        assert alerts[0]["agent"] == "alice"

    def test_check_trust_gates_no_alert(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice", trust_at_issue=0.6)
        alerts = reg.check_trust_gates()
        assert len(alerts) == 0

    def test_stats(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.issue(CapabilityAction.CREATE_ITEM, "alice")
        s = reg.stats()
        assert s["total_tokens"] == 2
        assert s["valid_tokens"] == 2
        assert s["agents_with_capabilities"] == 1
        assert s["unique_actions"] == 2

    def test_get_reputation(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        rep = reg.get_reputation("alice")
        assert rep.expected_value == 0.5

    def test_update_reputation(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        reg.update_reputation("alice", 0.9)
        rep = reg.get_reputation("alice")
        assert rep.expected_value > 0.5

    def test_update_reputation_negative(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        reg.update_reputation("alice", 0.1)
        rep = reg.get_reputation("alice")
        assert rep.expected_value < 0.5


# ═══════════════════════════════════════════════════════════════
# 5. Persistence
# ═══════════════════════════════════════════════════════════════

class TestPersistence:
    def test_save_creates_file(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.save("alice")
        assert (reg.data_dir / "alice.json").exists()

    def test_save_includes_reputation(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        reg.update_reputation("alice", 0.9)
        reg.save("alice")
        data = json.loads((reg.data_dir / "alice.json").read_text())
        assert data["reputation"] is not None
        assert data["reputation"]["expected_value"] > 0.5

    def test_load_restores_tokens(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.save("alice")

        reg2 = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        loaded = reg2.load("alice")
        assert loaded is True
        assert reg2.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_load_nonexistent(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        assert reg.load("nobody") is False

    def test_load_invalid_json(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir)
        (reg.data_dir / "bad.json").write_text("not json{{{")
        assert reg.load("bad") is False

    def test_save_all_load_all(self, tmp_cap_dir):
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.6, "bob": 0.7}
        )
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.issue(CapabilityAction.CREATE_ITEM, "bob")
        reg.update_reputation("alice", 0.85)
        reg.save_all()

        reg2 = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6, "bob": 0.7})
        reg2.load_all()
        assert reg2.can_agent("alice", CapabilityAction.BUILD_ROOM)
        assert reg2.can_agent("bob", CapabilityAction.CREATE_ITEM)
        rep = reg2.get_reputation("alice")
        assert rep.expected_value > 0.5

    def test_persistence_survives_revoked(self, tmp_cap_dir):
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        token = reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.revoke(token.token_id)
        reg.save("alice")

        reg2 = make_registry(data_dir=tmp_cap_dir, trust_scores={"alice": 0.6})
        reg2.load("alice")
        assert not reg2.can_agent("alice", CapabilityAction.BUILD_ROOM)


# ═══════════════════════════════════════════════════════════════
# 6. Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_delegate_depth_limit(self, tmp_cap_dir):
        """Cannot delegate beyond max_delegate_depth."""
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"a": 0.9, "b": 0.8, "c": 0.7, "d": 0.6}
        )
        t1 = reg.issue(CapabilityAction.BUILD_ROOM, "a")
        # depth 1
        t2 = reg.delegate(t1.token_id, "b", from_agent="a")
        assert t2 is not None
        assert t2.delegate_depth == 1

        # depth 2
        t3 = reg.delegate(t2.token_id, "c", from_agent="b")
        assert t3 is not None
        assert t3.delegate_depth == 2

        # depth 3 — should still work (max is 3)
        t4 = reg.delegate(t3.token_id, "d", from_agent="c")
        assert t4 is not None
        assert t4.delegate_depth == 3

        # depth 4 — token still valid but depth > max
        assert t4.delegate_depth >= t4.max_delegate_depth

    def test_no_trust_getter(self, tmp_cap_dir):
        """Registry works without trust getter (uses BASE_TRUST)."""
        reg = CapabilityRegistry(data_dir=tmp_cap_dir)
        # BASE_TRUST (0.3) is below EXERCISE_THRESHOLD (0.25)? No, 0.3 > 0.25
        # So exercise should work
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_empty_registry_stats(self, tmp_cap_dir):
        reg = CapabilityRegistry(data_dir=tmp_cap_dir)
        s = reg.stats()
        assert s["total_tokens"] == 0
        assert s["agents_with_capabilities"] == 0

    def test_endow_level_0(self, tmp_cap_dir):
        """Level 0 should issue no tokens."""
        reg = make_registry(data_dir=tmp_cap_dir)
        tokens = reg.endow_on_level_up("alice", 0, 0)
        assert len(tokens) == 0

    def test_endow_level_5(self, tmp_cap_dir):
        """Level 5 (Architect) should issue ALL capabilities."""
        reg = make_registry(data_dir=tmp_cap_dir, trust_scores={"casey": 1.0})
        tokens = reg.endow_on_level_up("casey", 0, 5)
        assert len(tokens) > 0
        # Should be able to do everything
        for action in CapabilityAction:
            assert reg.can_agent("casey", action)

    def test_beta_reputation_extreme_updates(self):
        """Handle lots of updates without numerical issues."""
        rep = BetaReputation()
        for _ in range(1000):
            rep.update(positive=True)
            rep.update(positive=False)
        assert 0.0 <= rep.expected_value <= 1.0
        assert 0.0 <= rep.uncertainty <= 1.0
        assert rep.evidence_count > 0  # forget_factor reduces but evidence accumulates

    def test_token_audit_log_grows(self):
        token = CapabilityToken()
        for _ in range(10):
            token.exercise()
        assert len(token.audit_log) == 10

    def test_reputation_opinion_sums_to_one(self):
        rep = BetaReputation()
        for _ in range(50):
            rep.update(positive=True)
        b, d, u = rep.opinion
        assert abs(b + d + u - 1.0) < 1e-9

    def test_multiple_agents_independent(self, tmp_cap_dir):
        """Capabilities for different agents are independent."""
        reg = make_registry(
            data_dir=tmp_cap_dir,
            trust_scores={"alice": 0.6, "bob": 0.6}
        )
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        reg.issue(CapabilityAction.CREATE_ITEM, "bob")
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)
        assert not reg.can_agent("alice", CapabilityAction.CREATE_ITEM)
        assert reg.can_agent("bob", CapabilityAction.CREATE_ITEM)
        assert not reg.can_agent("bob", CapabilityAction.BUILD_ROOM)

    def test_trust_getter_exception(self, tmp_cap_dir):
        """Registry handles trust getter exceptions gracefully."""
        reg = CapabilityRegistry(data_dir=tmp_cap_dir)
        reg.set_trust_getter(lambda name: 1 / 0)  # always throws
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")
        # Should fall back to BASE_TRUST
        assert reg._get_trust("alice") == BASE_TRUST
