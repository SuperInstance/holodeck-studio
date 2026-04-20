#!/usr/bin/env python3
"""
Comprehensive test suite for capability_integration.py

Covers:
    1. CapabilityMiddleware creation and basic check
    2. Command-to-action mapping correctness
    3. Decorator wrapping of command handlers
    4. ACL fallback when no tokens exist
    5. OCap override when tokens exist
    6. Trust bridge: capability suspension on trust drop
    7. Trust bridge: capability restoration on trust recovery
    8. Endowment on level-up
    9. Audit trail recording and querying
    10. Edge cases: expired tokens, revoked tokens, delegated tokens
    11. Dual-mode operation (both ACL and OCap)
    12. Command gate function
"""

import sys
import json
import shutil
import tempfile
import time
import asyncio
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from capability_integration import (
    CommandActionMap,
    CapabilityMiddleware,
    CapabilityAudit,
    TrustBridge,
    CheckResult,
    check_capability,
    require_capability,
    get_registry,
    reset_registry,
)
from capability_tokens import (
    CapabilityRegistry,
    CapabilityAction,
    CapabilityToken,
    BetaReputation,
    LEVEL_CAPABILITIES,
    EXERCISE_TRUST_THRESHOLD,
    ENDORSEMENT_TRUST_THRESHOLD,
    DELEGATION_TRUST_THRESHOLD,
    BASE_TRUST,
    TRUST_DECAY_ALERT_THRESHOLD,
)


# ═══════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_dir():
    """Provide a temp directory for test data."""
    d = tempfile.mkdtemp(prefix="cap_int_test_")
    yield d
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture(autouse=True)
def reset_singleton():
    """Reset the singleton registry before each test."""
    reset_registry()
    yield
    reset_registry()


def make_registry(data_dir=None, trust_scores=None):
    """Create a CapabilityRegistry with optional trust getter."""
    reg = CapabilityRegistry(data_dir=data_dir or tempfile.mkdtemp())
    if trust_scores:
        def trust_getter(name):
            return trust_scores.get(name, BASE_TRUST)
        reg.set_trust_getter(trust_getter)
    return reg


def make_middleware(registry=None, perm_levels=None, mode="dual", trust_scores=None):
    """Create a CapabilityMiddleware with typical test defaults."""
    reg = registry or make_registry(
        data_dir=tempfile.mkdtemp(),
        trust_scores=trust_scores or {"alice": 0.6, "bob": 0.6, "carol": 0.6},
    )
    levels = perm_levels or {"alice": 3, "bob": 2, "carol": 0}
    return CapabilityMiddleware(registry=reg, permission_levels=levels, mode=mode)


# ═══════════════════════════════════════════════════════════════
# 1. CapabilityMiddleware — Creation and Basic Check
# ═══════════════════════════════════════════════════════════════

class TestMiddlewareCreation:
    def test_create_middleware(self):
        mw = make_middleware()
        assert mw.registry is not None
        assert mw.permission_levels is not None
        assert mw.mode == "dual"

    def test_create_with_custom_mode(self):
        mw = make_middleware(mode="ocap")
        assert mw.mode == "ocap"

    def test_create_with_acl_mode(self):
        mw = make_middleware(mode="acl")
        assert mw.mode == "acl"

    def test_default_permission_levels_empty(self):
        reg = make_registry()
        mw = CapabilityMiddleware(registry=reg)
        assert mw.permission_levels == {}

    def test_check_returns_check_result(self):
        mw = make_middleware()
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert isinstance(result, CheckResult)

    def test_check_result_to_dict(self):
        mw = make_middleware()
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        d = result.to_dict()
        assert "allowed" in d
        assert "via" in d
        assert "reason" in d

    def test_check_allowed_via_ocap(self):
        mw = make_middleware()
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "ocap"

    def test_check_allowed_via_acl(self):
        """No tokens, but ACL level is high enough."""
        reg = make_registry(trust_scores={"alice": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 4},
            mode="dual",
        )
        # No tokens issued — should fall back to ACL
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "acl"

    def test_check_denied_no_token_no_acl(self):
        reg = make_registry(trust_scores={"carol": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"carol": 0},
            mode="dual",
        )
        result = mw.check("carol", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False
        assert result.via == "none"


# ═══════════════════════════════════════════════════════════════
# 2. Command-to-Action Mapping Correctness
# ═══════════════════════════════════════════════════════════════

class TestCommandActionMap:
    def test_build_maps_to_build_room(self):
        assert CommandActionMap.get_action("build") == CapabilityAction.BUILD_ROOM

    def test_spawn_maps_to_summon_npc(self):
        assert CommandActionMap.get_action("spawn") == CapabilityAction.SUMMON_NPC

    def test_cast_maps_to_create_spell(self):
        assert CommandActionMap.get_action("cast") == CapabilityAction.CREATE_SPELL

    def test_install_maps_to_create_tool_room(self):
        assert CommandActionMap.get_action("install") == CapabilityAction.CREATE_TOOL_ROOM

    def test_alert_maps_to_govern(self):
        assert CommandActionMap.get_action("alert") == CapabilityAction.GOVERN

    def test_setmotd_maps_to_broadcast_fleet(self):
        assert CommandActionMap.get_action("setmotd") == CapabilityAction.BROADCAST_FLEET

    def test_hail_maps_to_broadcast_fleet(self):
        assert CommandActionMap.get_action("hail") == CapabilityAction.BROADCAST_FLEET

    def test_look_is_ungated(self):
        assert CommandActionMap.get_action("look") is None

    def test_say_is_ungated(self):
        assert CommandActionMap.get_action("say") is None

    def test_go_is_ungated(self):
        assert CommandActionMap.get_action("go") is None

    def test_help_is_ungated(self):
        assert CommandActionMap.get_action("help") is None

    def test_who_is_ungated(self):
        assert CommandActionMap.get_action("who") is None

    def test_is_gated_build(self):
        assert CommandActionMap.is_gated("build") is True

    def test_is_gated_look(self):
        assert CommandActionMap.is_gated("look") is False

    def test_is_gated_case_insensitive(self):
        assert CommandActionMap.is_gated("BUILD") is True
        assert CommandActionMap.is_gated("Build") is True
        assert CommandActionMap.is_gated(" build ") is True

    def test_all_gated_commands_returns_dict(self):
        gated = CommandActionMap.all_gated_commands()
        assert isinstance(gated, dict)
        assert len(gated) > 0
        assert "build" in gated

    def test_commands_for_action(self):
        cmds = CommandActionMap.commands_for_action(CapabilityAction.BROADCAST_FLEET)
        assert "setmotd" in cmds
        assert "hail" in cmds
        assert "channels" in cmds

    def test_alias_l_maps_to_look(self):
        # 'l' is an alias for 'look' which is ungated
        action = CommandActionMap.get_action("l")
        # Since 'l' maps to 'look', and 'look' is ungated, action should be None
        assert action is None

    def test_unknown_command_returns_none(self):
        assert CommandActionMap.get_action("foobar") is None


# ═══════════════════════════════════════════════════════════════
# 3. Decorator Wrapping of Command Handlers
# ═══════════════════════════════════════════════════════════════

class TestDecorator:
    @pytest.mark.asyncio
    async def test_decorator_allows_authorized_agent(self):
        mw = make_middleware()
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")

        # Create mock handler
        mock_handler = AsyncMock(return_value="built")

        # Wrap it
        wrapped = mw.decorate(CapabilityAction.BUILD_ROOM)(mock_handler)

        # Create mock agent
        agent = MagicMock()
        agent.name = "alice"

        # Call the wrapped handler
        result = await wrapped(mw, agent, "my_room")
        assert mock_handler.called
        assert result == "built"

    @pytest.mark.asyncio
    async def test_decorator_denies_unauthorized_agent(self):
        mw = make_middleware(perm_levels={"alice": 0})

        mock_handler = AsyncMock(return_value="built")
        wrapped = mw.decorate(CapabilityAction.BUILD_ROOM)(mock_handler)

        agent = MagicMock()
        agent.name = "alice"

        result = await wrapped(mw, agent, "my_room")
        assert not mock_handler.called
        assert result is None

    @pytest.mark.asyncio
    async def test_decorator_sends_denial_message(self):
        mw = make_middleware(perm_levels={"alice": 0})
        mock_send = AsyncMock()

        mock_handler = AsyncMock(return_value="built")
        wrapped = mw.decorate(CapabilityAction.BUILD_ROOM)(mock_handler)

        agent = MagicMock()
        agent.name = "alice"

        # Create a mock self that has .send
        mock_self = MagicMock()
        mock_self.send = mock_send

        await wrapped(mock_self, agent, "my_room")
        assert mock_send.called
        msg = mock_send.call_args[0][1]
        assert "[capability]" in msg


# ═══════════════════════════════════════════════════════════════
# 4. ACL Fallback When No Tokens Exist
# ═══════════════════════════════════════════════════════════════

class TestACLFallback:
    def test_acl_fallback_level_3_can_build(self):
        reg = make_registry(trust_scores={"alice": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 3},
            mode="dual",
        )
        # No tokens issued, ACL level 3 >= required level 2 for BUILD_ROOM
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "acl"

    def test_acl_fallback_level_1_cannot_build(self):
        reg = make_registry(trust_scores={"alice": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 1},
            mode="dual",
        )
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False

    def test_acl_fallback_level_5_can_do_everything(self):
        reg = make_registry(trust_scores={"casey": 1.0})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"casey": 5},
            mode="acl",  # ACL-only mode
        )
        for action in CapabilityAction:
            result = mw.check("casey", action)
            assert result.allowed is True, f"Level 5 should allow {action.value}"

    def test_acl_fallback_reason_includes_levels(self):
        reg = make_registry(trust_scores={"carol": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"carol": 0},
            mode="dual",
        )
        result = mw.check("carol", CapabilityAction.BUILD_ROOM)
        assert "0" in result.reason
        assert "2" in result.reason  # BUILD_ROOM requires level 2


# ═══════════════════════════════════════════════════════════════
# 5. OCap Override When Tokens Exist
# ═══════════════════════════════════════════════════════════════

class TestOCapOverride:
    def test_ocap_overrides_acl(self):
        """If an agent has a token but low ACL level, OCap should still pass."""
        mw = make_middleware(perm_levels={"alice": 0})
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "ocap"

    def test_ocap_takes_priority_over_acl(self):
        """OCap is checked first — if token exists, ACL is skipped."""
        mw = make_middleware(perm_levels={"alice": 5})
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "ocap"  # NOT acl, even though acl would also pass

    def test_ocap_mode_denies_without_token(self):
        """In ocap-only mode, no ACL fallback."""
        reg = make_registry(trust_scores={"alice": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 5},  # high level, but no tokens
            mode="ocap",
        )
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False
        assert result.via == "none"

    def test_ocap_result_includes_token_id(self):
        mw = make_middleware()
        token = mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.token_id == token.token_id

    def test_acl_mode_ignores_tokens(self):
        """In acl-only mode, tokens are ignored."""
        reg = make_registry(trust_scores={"alice": 0.6})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 0},
            mode="acl",
        )
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False
        assert result.via == "none"


# ═══════════════════════════════════════════════════════════════
# 6. Trust Bridge — Capability Suspension on Trust Drop
# ═══════════════════════════════════════════════════════════════

class TestTrustBridgeSuspension:
    def test_trust_drop_suspends_agent(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 3},
            audit=audit,
        )
        bridge.endow_capabilities("alice", 3, trust_score=0.6)

        # Trust drops below exercise threshold
        bridge.on_trust_change("alice", 0.6, 0.1)
        assert bridge.is_suspended("alice")

    def test_suspension_recorded_in_audit(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 3},
            audit=audit,
        )
        bridge.on_trust_change("alice", 0.6, 0.1)

        events = audit.recent_checks(action="trust_bridge:suspend")
        assert len(events) == 1
        assert events[0]["agent"] == "alice"

    def test_suspended_agent_cannot_exercise(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.1})
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 1},  # level 1 < required level 2
            mode="dual",
        )
        reg.issue(CapabilityAction.BUILD_ROOM, "alice", trust_at_issue=0.6)

        # Trust is now 0.1, below exercise threshold → OCap fails
        # ACL level 1 < required level 2 → ACL also fails
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False
        assert result.via == "none"

    def test_multiple_agents_suspended_independently(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir)
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 3, "bob": 3},
            audit=audit,
        )

        bridge.on_trust_change("alice", 0.6, 0.1)
        assert bridge.is_suspended("alice")
        assert not bridge.is_suspended("bob")

        bridge.on_trust_change("bob", 0.6, 0.05)
        assert bridge.is_suspended("bob")

    def test_suspended_agents_list(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir)
        bridge = TrustBridge(registry=reg)

        bridge.on_trust_change("alice", 0.6, 0.1)
        bridge.on_trust_change("bob", 0.6, 0.1)

        suspended = bridge.suspended_agents()
        assert "alice" in suspended
        assert "bob" in suspended
        assert len(suspended) == 2


# ═══════════════════════════════════════════════════════════════
# 7. Trust Bridge — Capability Restoration on Trust Recovery
# ═══════════════════════════════════════════════════════════════

class TestTrustBridgeRestoration:
    def test_trust_recovery_restores_agent(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir)
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 3},
            audit=audit,
        )

        # Suspend
        bridge.on_trust_change("alice", 0.6, 0.1)
        assert bridge.is_suspended("alice")

        # Recover (must exceed threshold + hysteresis of 0.05)
        bridge.on_trust_change("alice", 0.1, 0.5)
        assert not bridge.is_suspended("alice")

    def test_hysteresis_prevents_flapping(self, tmp_dir):
        """Recovery requires exceeding EXERCISE_TRUST_THRESHOLD + 0.05."""
        reg = make_registry(data_dir=tmp_dir)
        bridge = TrustBridge(registry=reg)

        bridge.on_trust_change("alice", 0.6, 0.1)
        assert bridge.is_suspended("alice")

        # At exactly the threshold — not enough (need threshold + 0.05)
        bridge.on_trust_change("alice", 0.1, EXERCISE_TRUST_THRESHOLD)
        assert bridge.is_suspended("alice")  # still suspended

        # Just above threshold + hysteresis
        bridge.on_trust_change("alice", 0.1, EXERCISE_TRUST_THRESHOLD + 0.06)
        assert not bridge.is_suspended("alice")

    def test_restoration_recorded_in_audit(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir)
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 3},
            audit=audit,
        )

        bridge.on_trust_change("alice", 0.6, 0.1)
        bridge.on_trust_change("alice", 0.1, 0.5)

        events = audit.recent_checks(action="trust_bridge:restore")
        assert len(events) == 1
        assert events[0]["agent"] == "alice"

    def test_restored_agent_can_exercise_again(self, tmp_dir):
        reg = make_registry(
            data_dir=tmp_dir,
            trust_scores={"alice": 0.5},  # recovered trust
        )
        mw = CapabilityMiddleware(
            registry=reg,
            permission_levels={"alice": 0},
            mode="dual",
        )
        # Issue a token
        reg.issue(CapabilityAction.BUILD_ROOM, "alice")

        # With trust >= 0.25, exercise should work
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "ocap"


# ═══════════════════════════════════════════════════════════════
# 8. Endowment on Level-Up
# ═══════════════════════════════════════════════════════════════

class TestEndowment:
    def test_endow_grants_tokens(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 1},
        )
        tokens = bridge.endow_capabilities("alice", 2, trust_score=0.6)
        assert len(tokens) > 0
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)

    def test_endow_updates_permission_level(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir)
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 0},
        )
        bridge.endow_capabilities("alice", 3)
        assert bridge.permission_levels["alice"] == 3

    def test_endow_multiple_levels(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.9})
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 0},
        )
        tokens = bridge.endow_capabilities("alice", 4)
        assert len(tokens) > 0
        # Should have all level 2-4 capabilities
        assert reg.can_agent("alice", CapabilityAction.BUILD_ROOM)
        assert reg.can_agent("alice", CapabilityAction.CREATE_ADVENTURE)
        assert reg.can_agent("alice", CapabilityAction.BROADCAST_FLEET)

    def test_endow_no_dupes(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 1},
        )
        bridge.endow_capabilities("alice", 2)
        count_before = len(reg.agent_tokens.get("alice", set()))
        bridge.endow_capabilities("alice", 2)  # same level
        count_after = len(reg.agent_tokens.get("alice", set()))
        assert count_before == count_after

    def test_endow_level_5_grants_all(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"casey": 1.0})
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"casey": 0},
        )
        tokens = bridge.endow_capabilities("casey", 5)
        assert len(tokens) > 0
        for action in CapabilityAction:
            assert reg.can_agent("casey", action), f"Level 5 should grant {action.value}"

    def test_endow_level_0_grants_nothing(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir)
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"carol": 0},
        )
        tokens = bridge.endow_capabilities("carol", 0)
        assert len(tokens) == 0

    def test_endow_recorded_in_audit(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 1},
            audit=audit,
        )
        bridge.endow_capabilities("alice", 2)

        events = audit.recent_checks(action="trust_bridge:endow")
        assert len(events) == 1


# ═══════════════════════════════════════════════════════════════
# 9. Audit Trail Recording and Querying
# ═══════════════════════════════════════════════════════════════

class TestAuditTrail:
    def test_record_check(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("alice", "build_room", True, "ocap", "Token valid")
        assert len(audit.recent_checks()) == 1

    def test_record_denied_check(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("carol", "build_room", False, "none", "No permission")
        assert len(audit.recent_checks()) == 1

    def test_multiple_records(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        for i in range(10):
            audit.record("alice", f"action_{i}", True)
        assert len(audit.recent_checks()) == 10

    def test_filter_by_agent(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("alice", "build_room", True)
        audit.record("bob", "build_room", False)
        audit.record("alice", "summon_npc", True)

        results = audit.recent_checks(agent="alice")
        assert len(results) == 2
        for r in results:
            assert r["agent"] == "alice"

    def test_filter_by_action(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("alice", "build_room", True)
        audit.record("alice", "summon_npc", False)
        audit.record("bob", "build_room", True)

        results = audit.recent_checks(action="build_room")
        assert len(results) == 2

    def test_limit_results(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        for i in range(100):
            audit.record("alice", f"action_{i}", True)

        results = audit.recent_checks(limit=10)
        assert len(results) == 10

    def test_recent_checks_newest_first(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("alice", "action_1", True)
        time.sleep(0.01)
        audit.record("alice", "action_2", False)
        time.sleep(0.01)
        audit.record("alice", "action_3", True)

        results = audit.recent_checks(limit=3)
        assert results[0]["action"] == "action_3"  # newest first

    def test_denied_checks_filter(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("alice", "a1", True)
        audit.record("alice", "a2", False)
        audit.record("alice", "a3", False)
        audit.record("alice", "a4", True)

        denied = audit.denied_checks(agent="alice")
        assert len(denied) == 2
        for d in denied:
            assert d["allowed"] is False

    def test_stats(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        audit.record("alice", "build_room", True, "ocap")
        audit.record("bob", "build_room", False, "none")
        audit.record("alice", "summon_npc", True, "acl")

        stats = audit.stats()
        assert stats["total"] == 3
        assert stats["allowed"] == 2
        assert stats["denied"] == 1
        assert stats["by_via"]["ocap"] == 1
        assert stats["by_via"]["acl"] == 1
        assert stats["by_via"]["none"] == 1

    def test_stats_empty(self, tmp_dir):
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        stats = audit.stats()
        assert stats["total"] == 0

    def test_persistence_to_jsonl(self, tmp_dir):
        filepath = Path(tmp_dir) / "audit.jsonl"
        audit = CapabilityAudit(filepath=str(filepath))
        audit.record("alice", "build_room", True)
        audit.record("bob", "summon_npc", False)

        # File should exist
        assert filepath.exists()

        # Load it back
        audit2 = CapabilityAudit(filepath=str(filepath))
        assert len(audit2.recent_checks()) == 2

    def test_clear(self, tmp_dir):
        filepath = Path(tmp_dir) / "audit.jsonl"
        audit = CapabilityAudit(filepath=str(filepath))
        audit.record("alice", "build_room", True)
        audit.clear()
        assert len(audit.recent_checks()) == 0


# ═══════════════════════════════════════════════════════════════
# 10. Edge Cases — Expired, Revoked, Delegated Tokens
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_expired_token_denied(self):
        mw = make_middleware(trust_scores={"alice": 0.6})
        mw.registry.issue(
            CapabilityAction.BUILD_ROOM,
            "alice",
            expires=time.time() - 100,  # expired
        )
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        # OCap fails (expired), falls back to ACL
        assert result.via == "acl"

    def test_revoked_token_denied(self):
        mw = make_middleware(trust_scores={"alice": 0.6})
        token = mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        mw.registry.revoke(token.token_id, "test revocation")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.via == "acl"  # revoked, falls back

    def test_delegated_token_authorizes(self):
        mw = make_middleware(
            perm_levels={"alice": 3, "bob": 2},
            trust_scores={"alice": 0.7, "bob": 0.5},
        )
        parent = mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        child = mw.registry.delegate(parent.token_id, "bob", from_agent="alice")
        assert child is not None

        result = mw.check("bob", CapabilityAction.BUILD_ROOM)
        assert result.allowed is True
        assert result.via == "ocap"

    def test_revoked_parent_revokes_delegated(self):
        mw = make_middleware(
            perm_levels={"alice": 3, "bob": 2, "carol": 0},
            trust_scores={"alice": 0.7, "bob": 0.5, "carol": 0.3},
        )
        parent = mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        child = mw.registry.delegate(parent.token_id, "bob", from_agent="alice")

        # Both can exercise
        assert mw.check("alice", CapabilityAction.BUILD_ROOM).via == "ocap"
        assert mw.check("bob", CapabilityAction.BUILD_ROOM).via == "ocap"

        # Revoke parent
        mw.registry.revoke(parent.token_id, "security")

        # Both should now fail OCap and fall to ACL
        result_alice = mw.check("alice", CapabilityAction.BUILD_ROOM)
        result_bob = mw.check("bob", CapabilityAction.BUILD_ROOM)
        assert result_alice.via == "acl"
        assert result_bob.via == "acl"

    def test_token_with_limited_uses(self):
        mw = make_middleware(trust_scores={"alice": 0.6})
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice", max_uses=1)
        # First use
        r1 = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert r1.via == "ocap"

        # Exercise the token
        mw.registry.exercise("alice", CapabilityAction.BUILD_ROOM)

        # Second use — token exhausted
        r2 = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert r2.via == "acl"  # falls back to ACL

    def test_unknown_agent_gets_base_trust(self):
        mw = make_middleware(trust_scores={})
        result = mw.check("unknown_agent", CapabilityAction.BUILD_ROOM)
        # BASE_TRUST (0.3) >= EXERCISE_TRUST_THRESHOLD (0.25)
        # But agent has no tokens and no permission level
        assert result.allowed is False

    def test_empty_registry(self):
        reg = CapabilityRegistry(data_dir=tempfile.mkdtemp())
        mw = CapabilityMiddleware(registry=reg, mode="dual")
        result = mw.check("nobody", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False


# ═══════════════════════════════════════════════════════════════
# 11. Dual-Mode Operation
# ═══════════════════════════════════════════════════════════════

class TestDualMode:
    def test_dual_mode_ocap_wins(self):
        """In dual mode, OCap takes priority over ACL."""
        mw = make_middleware(perm_levels={"alice": 5})  # ACL would pass
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.via == "ocap"

    def test_dual_mode_acl_fallback(self):
        """In dual mode, ACL is fallback when no OCap."""
        mw = make_middleware(perm_levels={"alice": 4})
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.via == "acl"

    def test_dual_mode_both_fail(self):
        mw = make_middleware(perm_levels={"carol": 0}, trust_scores={"carol": 0.3})
        result = mw.check("carol", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False
        assert result.via == "none"

    def test_ocap_mode_no_acl(self):
        mw = make_middleware(perm_levels={"alice": 5}, mode="ocap")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.allowed is False  # no tokens, ACL ignored
        assert result.via == "none"

    def test_acl_mode_no_ocap(self):
        mw = make_middleware(perm_levels={"alice": 3}, mode="acl")
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")
        result = mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert result.via == "acl"  # tokens ignored in acl mode


# ═══════════════════════════════════════════════════════════════
# 12. Command Gate Function
# ═══════════════════════════════════════════════════════════════

class TestCommandGate:
    def test_gate_command_allows(self):
        mw = make_middleware()
        mw.registry.issue(CapabilityAction.BUILD_ROOM, "alice")

        async def cmd_build(self, agent, args):
            return f"Built {args}"

        wrapped = mw.gate_command(cmd_build, CapabilityAction.BUILD_ROOM)
        assert callable(wrapped)

    def test_check_command_gated(self):
        mw = make_middleware(perm_levels={"carol": 0})
        result = mw.check_command("carol", "build")
        assert result.allowed is False

    def test_check_command_ungated(self):
        mw = make_middleware()
        result = mw.check_command("carol", "look")
        assert result.allowed is True
        assert result.via == "none"

    def test_check_command_spawn(self):
        mw = make_middleware(perm_levels={"carol": 0})
        result = mw.check_command("carol", "spawn")
        assert result.allowed is False

    def test_check_command_hail(self):
        mw = make_middleware(perm_levels={"alice": 3})
        result = mw.check_command("alice", "hail")
        # hail requires BROADCAST_FLEET which needs level 4
        # alice is level 3 — denied
        assert result.allowed is False


# ═══════════════════════════════════════════════════════════════
# 13. Singleton Registry
# ═══════════════════════════════════════════════════════════════

class TestSingletonRegistry:
    def test_get_registry_returns_same_instance(self):
        r1 = get_registry(data_dir=tempfile.mkdtemp())
        r2 = get_registry()
        assert r1 is r2

    def test_reset_registry(self):
        r1 = get_registry(data_dir=tempfile.mkdtemp())
        reset_registry()
        r2 = get_registry(data_dir=tempfile.mkdtemp())
        assert r1 is not r2


# ═══════════════════════════════════════════════════════════════
# 14. Convenience Functions
# ═══════════════════════════════════════════════════════════════

class TestConvenienceFunctions:
    def test_check_capability_returns_dict(self):
        result = check_capability("alice", CapabilityAction.BUILD_ROOM)
        assert isinstance(result, dict)
        assert "allowed" in result

    def test_check_capability_uses_singleton(self):
        reset_registry()
        check_capability("alice", CapabilityAction.BUILD_ROOM)
        # Singleton should now exist
        r = get_registry()
        assert r is not None

    def test_require_capability_returns_decorator(self):
        dec = require_capability(CapabilityAction.BUILD_ROOM)
        assert callable(dec)


# ═══════════════════════════════════════════════════════════════
# 15. Trust Bridge — Revoke All
# ═══════════════════════════════════════════════════════════════

class TestTrustBridgeRevokeAll:
    def test_revoke_all_for_agent(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 0},  # start at 0 so endow issues tokens
        )
        bridge.endow_capabilities("alice", 3)

        assert len(reg.agent_tokens.get("alice", set())) > 0
        bridge.revoke_all_for_agent("alice", "Security review")
        # All tokens should be revoked
        for tid in reg.agent_tokens.get("alice", set()):
            assert reg.tokens[tid].revoked

    def test_revoke_all_recorded_in_audit(self, tmp_dir):
        reg = make_registry(data_dir=tmp_dir, trust_scores={"alice": 0.6})
        audit = CapabilityAudit(filepath=Path(tmp_dir) / "audit.jsonl")
        bridge = TrustBridge(
            registry=reg,
            permission_levels={"alice": 3},
            audit=audit,
        )
        bridge.endow_capabilities("alice", 3)
        bridge.revoke_all_for_agent("alice")

        events = audit.recent_checks(action="trust_bridge:revoke_all")
        assert len(events) == 1


# ═══════════════════════════════════════════════════════════════
# 16. Middleware Audit Trail
# ═══════════════════════════════════════════════════════════════

class TestMiddlewareAudit:
    def test_middleware_records_checks(self):
        mw = make_middleware()
        mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert len(mw.audit_trail) == 1

    def test_middleware_audit_trail_grows(self):
        mw = make_middleware()
        for i in range(20):
            mw.check("alice", CapabilityAction.BUILD_ROOM)
        assert len(mw.audit_trail) == 20

    def test_middleware_clear_audit(self):
        mw = make_middleware()
        mw.check("alice", CapabilityAction.BUILD_ROOM)
        mw.clear_audit()
        assert len(mw.audit_trail) == 0

    def test_middleware_audit_includes_details(self):
        mw = make_middleware()
        mw.check("alice", CapabilityAction.BUILD_ROOM)
        entry = mw.audit_trail[0]
        assert entry["agent"] == "alice"
        assert entry["action"] == "build_room"
        assert "timestamp" in entry
