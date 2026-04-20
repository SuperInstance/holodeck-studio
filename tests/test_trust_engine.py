#!/usr/bin/env python3
"""
Comprehensive test suite for trust_engine.py

Covers: WeightedHistory, TrustProfile, TrustEngine, TRUST_EVENTS, cmd_trust
Aims for 60+ tests with full coverage of edge cases.
"""

import asyncio
import json
import os
import sys
import shutil
import time
import tempfile
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from trust_engine import (
    WeightedHistory, TrustProfile, TrustEngine,
    TRUST_DIMENSIONS, DEFAULT_WEIGHTS, DECAY_RATES,
    BASE_TRUST, MIN_EVENTS_FOR_TRUST, TRUST_EVENTS,
)
from server import World, Agent, CommandHandler


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

class FakeWriter:
    def __init__(self):
        self.data = []
        self._closed = False

    def write(self, data):
        if not self._closed:
            self.data.append(data)

    async def drain(self):
        pass

    def is_closing(self):
        return self._closed

    def close(self):
        self._closed = True

    def get_text(self):
        return b"".join(self.data).decode(errors="replace")


def make_agent(name="testbot", role="vessel", room="tavern", writer=None):
    if writer is None:
        writer = FakeWriter()
    return Agent(name=name, role=role, room_name=room, writer=writer)


@pytest.fixture
def tmp_trust_dir():
    """Provide a temp directory for trust engine data."""
    d = tempfile.mkdtemp()
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ═══════════════════════════════════════════════════════════════════════════
# 1. Constants
# ═══════════════════════════════════════════════════════════════════════════

class TestConstants:
    def test_trust_dimensions_count(self):
        assert len(TRUST_DIMENSIONS) == 5

    def test_trust_dimensions_names(self):
        assert "code_quality" in TRUST_DIMENSIONS
        assert "task_completion" in TRUST_DIMENSIONS
        assert "collaboration" in TRUST_DIMENSIONS
        assert "reliability" in TRUST_DIMENSIONS
        assert "innovation" in TRUST_DIMENSIONS

    def test_default_weights_sum_to_one(self):
        assert abs(sum(DEFAULT_WEIGHTS.values()) - 1.0) < 1e-9

    def test_default_weights_match_dimensions(self):
        for dim in TRUST_DIMENSIONS:
            assert dim in DEFAULT_WEIGHTS

    def test_decay_rates_match_dimensions(self):
        for dim in TRUST_DIMENSIONS:
            assert dim in DECAY_RATES

    def test_decay_rates_between_0_and_1(self):
        for dim, rate in DECAY_RATES.items():
            assert 0 < rate < 1, f"{dim} decay rate {rate} not in (0,1)"

    def test_base_trust_value(self):
        assert BASE_TRUST == 0.3

    def test_min_events_for_trust(self):
        assert MIN_EVENTS_FOR_TRUST == 3

    def test_reliability_decays_slowest(self):
        assert DECAY_RATES["reliability"] == max(DECAY_RATES.values())

    def test_innovation_decays_fastest(self):
        assert DECAY_RATES["innovation"] == min(DECAY_RATES.values())


# ═══════════════════════════════════════════════════════════════════════════
# 2. TRUST_EVENTS presets
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustEventsPresets:
    def test_preset_count(self):
        assert len(TRUST_EVENTS) == 11

    def test_each_preset_has_required_keys(self):
        for name, evt in TRUST_EVENTS.items():
            assert "dimension" in evt, f"{name} missing dimension"
            assert "value" in evt, f"{name} missing value"
            assert "weight" in evt, f"{name} missing weight"

    def test_preset_values_in_range(self):
        for name, evt in TRUST_EVENTS.items():
            assert 0 <= evt["value"] <= 1, f"{name} value out of range"
            assert evt["weight"] > 0, f"{name} weight must be positive"

    def test_task_completed_preset(self):
        assert TRUST_EVENTS["task_completed"]["dimension"] == "task_completion"
        assert TRUST_EVENTS["task_completed"]["value"] == 0.8

    def test_task_failed_preset(self):
        assert TRUST_EVENTS["task_failed"]["dimension"] == "reliability"
        assert TRUST_EVENTS["task_failed"]["value"] == 0.2
        assert TRUST_EVENTS["task_failed"]["weight"] == 1.5

    def test_code_review_passed_preset(self):
        assert TRUST_EVENTS["code_review_passed"]["dimension"] == "code_quality"

    def test_code_review_failed_preset(self):
        assert TRUST_EVENTS["code_review_failed"]["dimension"] == "code_quality"

    def test_collaboration_good_preset(self):
        assert TRUST_EVENTS["collaboration_good"]["dimension"] == "collaboration"

    def test_innovation_shown_preset(self):
        assert TRUST_EVENTS["innovation_shown"]["dimension"] == "innovation"

    def test_tests_written_preset(self):
        assert TRUST_EVENTS["tests_written"]["dimension"] == "reliability"

    def test_docs_written_preset(self):
        assert TRUST_EVENTS["docs_written"]["dimension"] == "collaboration"


# ═══════════════════════════════════════════════════════════════════════════
# 3. WeightedHistory
# ═══════════════════════════════════════════════════════════════════════════

class TestWeightedHistory:
    def test_empty_score_returns_base_trust(self):
        wh = WeightedHistory()
        assert wh.score() == BASE_TRUST

    def test_single_event_score(self):
        wh = WeightedHistory()
        wh.add(0.8)
        assert wh.score() == 0.8

    def test_multiple_events_weighted_average(self):
        wh = WeightedHistory()
        wh.add(0.6, weight=1.0, timestamp=time.time())
        wh.add(1.0, weight=1.0, timestamp=time.time())
        assert abs(wh.score() - 0.8) < 1e-9

    def test_add_clamps_value_to_01(self):
        wh = WeightedHistory()
        wh.add(1.5)
        wh.add(-0.5)
        assert len(wh.events) == 2
        assert wh.events[0][1] == 1.0  # clamped
        assert wh.events[1][1] == 0.0  # clamped

    def test_add_records_current_timestamp(self):
        wh = WeightedHistory()
        before = time.time()
        wh.add(0.5)
        after = time.time()
        assert before <= wh.events[0][0] <= after

    def test_add_custom_timestamp(self):
        wh = WeightedHistory()
        ts = 1000000.0
        wh.add(0.7, timestamp=ts)
        assert wh.events[0][0] == ts

    def test_temporal_decay_old_event_weighs_less(self):
        wh = WeightedHistory(decay_rate=0.9)
        now = time.time()
        old_ts = now - (10 * 86400)  # 10 days ago
        wh.add(1.0, timestamp=old_ts)
        wh.add(0.5, timestamp=now)
        score = wh.score()
        # Recent 0.5 should pull score below 1.0, but above 0.5
        assert 0.5 < score < 1.0

    def test_no_decay_at_same_timestamp(self):
        wh = WeightedHistory(decay_rate=0.5)
        now = time.time()
        wh.add(1.0, timestamp=now, weight=1.0)
        wh.add(0.0, timestamp=now, weight=1.0)
        assert abs(wh.score() - 0.5) < 1e-9

    def test_event_count(self):
        wh = WeightedHistory()
        assert wh.event_count() == 0
        wh.add(0.5)
        wh.add(0.7)
        assert wh.event_count() == 2

    def test_recent_returns_n_events(self):
        wh = WeightedHistory()
        now = time.time()
        for i in range(20):
            wh.add(i / 20.0, timestamp=now - (20 - i))
        recent = wh.recent(n=5)
        assert len(recent) == 5
        # Should be most recent first
        assert recent[0]["value"] == 0.95  # last 5th
        assert recent[4]["value"] == 0.75

    def test_recent_empty(self):
        wh = WeightedHistory()
        assert wh.recent() == []

    def test_recent_contains_required_keys(self):
        wh = WeightedHistory()
        wh.add(0.5)
        recent = wh.recent()
        assert "timestamp" in recent[0]
        assert "value" in recent[0]
        assert "weight" in recent[0]
        assert "days_ago" in recent[0]

    def test_prune_removes_old_events(self):
        wh = WeightedHistory()
        now = time.time()
        wh.add(0.5, timestamp=now - (100 * 86400))  # 100 days ago
        wh.add(0.8, timestamp=now - (1 * 86400))     # 1 day ago
        wh.add(0.9, timestamp=now)                     # now
        assert wh.event_count() == 3
        wh.prune(max_age_days=90)
        assert wh.event_count() == 2

    def test_prune_keeps_all_when_young(self):
        wh = WeightedHistory()
        now = time.time()
        for i in range(10):
            wh.add(0.5, timestamp=now - i)
        wh.prune(max_age_days=365)
        assert wh.event_count() == 10

    def test_to_dict_structure(self):
        wh = WeightedHistory(decay_rate=0.93)
        wh.add(0.7)
        d = wh.to_dict()
        assert d["decay_rate"] == 0.93
        assert d["event_count"] == 1
        assert "score" in d
        assert "events" in d

    def test_to_dict_events_format(self):
        wh = WeightedHistory()
        ts = 1234567890.0
        wh.add(0.8, weight=1.5, timestamp=ts)
        d = wh.to_dict()
        assert len(d["events"]) == 1
        assert d["events"][0]["t"] == ts
        assert d["events"][0]["v"] == 0.8
        assert d["events"][0]["w"] == 1.5

    def test_from_dict_roundtrip(self):
        wh = WeightedHistory(decay_rate=0.92)
        now = time.time()
        wh.add(0.6, weight=2.0, timestamp=now)
        wh.add(0.9, weight=0.5, timestamp=now - 86400)
        d = wh.to_dict()
        wh2 = WeightedHistory.from_dict(d)
        assert wh2.decay_rate == 0.92
        assert wh2.event_count() == 2
        assert abs(wh2.score() - wh.score()) < 1e-6

    def test_from_dict_empty(self):
        wh = WeightedHistory.from_dict({"decay_rate": 0.88, "events": []})
        assert wh.decay_rate == 0.88
        assert wh.event_count() == 0
        assert wh.score() == BASE_TRUST

    def test_to_dict_limits_to_last_50_events(self):
        wh = WeightedHistory()
        now = time.time()
        for i in range(100):
            wh.add(0.5, timestamp=now - i)
        d = wh.to_dict()
        assert len(d["events"]) == 50
        # All 100 events still in memory
        assert wh.event_count() == 100


# ═══════════════════════════════════════════════════════════════════════════
# 4. TrustProfile
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustProfile:
    def test_creates_all_dimensions(self):
        tp = TrustProfile(agent_name="alice")
        assert len(tp.dimensions) == 5
        for dim in TRUST_DIMENSIONS:
            assert dim in tp.dimensions

    def test_default_weights(self):
        tp = TrustProfile(agent_name="alice")
        assert tp.weights == DEFAULT_WEIGHTS

    def test_record_adds_event(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("code_quality", 0.9)
        assert tp.dimensions["code_quality"].event_count() == 1

    def test_record_creates_unknown_dimension(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("custom_dim", 0.5)
        assert "custom_dim" in tp.dimensions
        assert tp.dimensions["custom_dim"].event_count() == 1

    def test_record_updates_last_seen(self):
        tp = TrustProfile(agent_name="alice")
        old_last_seen = tp.last_seen
        time.sleep(0.01)
        tp.record("code_quality", 0.8)
        assert tp.last_seen > old_last_seen

    def test_score_single_dimension(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("code_quality", 0.9)
        assert tp.score("code_quality") == 0.9

    def test_score_composite_no_events(self):
        tp = TrustProfile(agent_name="alice")
        assert tp.score() == BASE_TRUST

    def test_composite_with_events(self):
        tp = TrustProfile(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            tp.record(dim, 1.0)
        assert tp.composite() == 1.0

    def test_composite_custom_weights(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("code_quality", 1.0)
        tp.record("task_completion", 0.0)
        custom = {"code_quality": 1.0, "task_completion": 0.0,
                  "collaboration": 0.0, "reliability": 0.0, "innovation": 0.0}
        assert tp.composite(weights=custom) == 1.0

    def test_is_meaningful_false(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("code_quality", 0.8)
        assert not tp.is_meaningful()

    def test_is_meaningful_true(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("code_quality", 0.8)
        tp.record("task_completion", 0.8)
        tp.record("reliability", 0.8)
        assert tp.is_meaningful()

    def test_review_exempt_false_no_events(self):
        tp = TrustProfile(agent_name="alice")
        assert not tp.review_exempt()

    def test_review_exempt_false_low_trust(self):
        tp = TrustProfile(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            tp.record(dim, 0.3)
        # 5 events but composite ~ 0.3 < 0.7
        assert not tp.review_exempt()

    def test_review_exempt_true_high_trust(self):
        tp = TrustProfile(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            tp.record(dim, 0.9)
        assert tp.review_exempt()

    def test_summary_structure(self):
        tp = TrustProfile(agent_name="test_agent")
        s = tp.summary()
        assert s["agent"] == "test_agent"
        assert "composite" in s
        assert "dimensions" in s
        assert "meaningful" in s
        assert "review_exempt" in s
        assert "total_events" in s
        assert "last_seen" in s

    def test_summary_dimensions_keys(self):
        tp = TrustProfile(agent_name="alice")
        s = tp.summary()
        for dim in TRUST_DIMENSIONS:
            assert dim in s["dimensions"]

    def test_to_dict_roundtrip(self):
        tp = TrustProfile(agent_name="alice")
        tp.record("code_quality", 0.8)
        tp.record("task_completion", 0.9)
        d = tp.to_dict()
        tp2 = TrustProfile.from_dict(d)
        assert tp2.agent_name == "alice"
        assert tp2.score("code_quality") == 0.8
        assert abs(tp2.score("task_completion") - 0.9) < 0.01

    def test_from_dict_preserves_weights(self):
        tp = TrustProfile(agent_name="alice")
        custom = {"code_quality": 0.5, "task_completion": 0.5,
                  "collaboration": 0.0, "reliability": 0.0, "innovation": 0.0}
        tp.weights = custom
        d = tp.to_dict()
        tp2 = TrustProfile.from_dict(d)
        assert tp2.weights == custom

    def test_all_same_values(self):
        tp = TrustProfile(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            for _ in range(5):
                tp.record(dim, 0.6)
        assert abs(tp.composite() - 0.6) < 1e-9

    def test_extreme_values_0_and_1(self):
        tp = TrustProfile(agent_name="alice")
        tp.dimensions["code_quality"].add(1.0)
        tp.dimensions["code_quality"].add(0.0)
        score = tp.dimensions["code_quality"].score()
        assert 0.0 <= score <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# 5. TrustEngine
# ═══════════════════════════════════════════════════════════════════════════

class TestTrustEngine:
    def test_init_creates_data_dir(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        assert te.data_dir.exists()

    def test_get_profile_creates_new(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        p = te.get_profile("alice")
        assert p.agent_name == "alice"
        assert "alice" in te.profiles

    def test_get_profile_returns_existing(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        p1 = te.get_profile("alice")
        p2 = te.get_profile("alice")
        assert p1 is p2

    def test_record_event(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        assert abs(te.get_trust("alice", "code_quality") - 0.9) < 1e-9

    def test_get_trust_no_dimension(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        trust = te.get_trust("alice")
        assert 0.0 <= trust <= 1.0

    def test_composite_trust(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        for dim in TRUST_DIMENSIONS:
            te.record_event("alice", dim, 1.0)
        assert te.composite_trust("alice") == 1.0

    def test_compare_returns_dict(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        te.record_event("bob", "code_quality", 0.5)
        result = te.compare("alice", "bob")
        assert "agent_a" in result
        assert "agent_b" in result
        assert "similarity" in result

    def test_similarity_identical_profiles(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        for dim in TRUST_DIMENSIONS:
            te.record_event("alice", dim, 0.8)
            te.record_event("bob", dim, 0.8)
        result = te.compare("alice", "bob")
        assert abs(result["similarity"] - 1.0) < 1e-9

    def test_similarity_different_profiles(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        for dim in TRUST_DIMENSIONS:
            te.record_event("alice", dim, 1.0)
            te.record_event("bob", dim, 0.0)
        result = te.compare("alice", "bob")
        assert result["similarity"] < 1.0

    def test_leaderboard_empty(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        assert te.leaderboard() == []

    def test_leaderboard_sorted(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        for dim in TRUST_DIMENSIONS:
            te.record_event("low_agent", dim, 0.3)
            te.record_event("high_agent", dim, 0.9)
            te.record_event("mid_agent", dim, 0.6)
        board = te.leaderboard()
        assert board[0]["agent"] == "high_agent"
        assert board[1]["agent"] == "mid_agent"
        assert board[2]["agent"] == "low_agent"

    def test_leaderboard_limits_n(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        for i in range(10):
            for dim in TRUST_DIMENSIONS:
                te.record_event(f"agent_{i}", dim, 0.5)
        board = te.leaderboard(n=3)
        assert len(board) == 3

    def test_save_creates_file(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        te.save("alice")
        assert (te.data_dir / "alice.json").exists()

    def test_load_reads_file(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        te.save("alice")
        te2 = TrustEngine(data_dir=tmp_trust_dir)
        profile = te2.load("alice")
        assert profile is not None
        assert profile.agent_name == "alice"
        assert abs(profile.score("code_quality") - 0.9) < 1e-9

    def test_load_nonexistent_returns_none(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        assert te.load("nobody") is None

    def test_load_invalid_json_returns_none(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        (te.data_dir / "bad.json").write_text("not json{{{")
        assert te.load("bad") is None

    def test_save_all(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        te.record_event("bob", "code_quality", 0.8)
        te.save_all()
        assert (te.data_dir / "alice.json").exists()
        assert (te.data_dir / "bob.json").exists()

    def test_load_all(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.9)
        te.record_event("bob", "task_completion", 0.7)
        te.save_all()
        te2 = TrustEngine(data_dir=tmp_trust_dir)
        te2.load_all()
        assert "alice" in te2.profiles
        assert "bob" in te2.profiles
        assert abs(te2.get_trust("alice", "code_quality") - 0.9) < 0.01

    def test_prune_stale(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        # Create profile with old last_seen
        te.record_event("old_agent", "code_quality", 0.9)
        te.profiles["old_agent"].last_seen = time.time() - (100 * 86400)
        te.save("old_agent")
        # Create fresh profile
        te.record_event("new_agent", "code_quality", 0.8)
        te.save("new_agent")
        # Prune
        pruned = te.prune_stale(max_age_days=60)
        assert pruned == 1
        assert "old_agent" not in te.profiles
        assert "new_agent" in te.profiles
        assert not (te.data_dir / "old_agent.json").exists()

    def test_prune_stale_no_files_left(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("fresh", "code_quality", 0.9)
        te.save("fresh")
        pruned = te.prune_stale(max_age_days=60)
        assert pruned == 0
        assert "fresh" in te.profiles

    def test_stats_empty(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        s = te.stats()
        assert s["total_profiles"] == 0
        assert s["meaningful_profiles"] == 0
        assert s["average_trust"] == BASE_TRUST
        assert s["review_exempt"] == 0
        assert s["dimensions"] == 5

    def test_stats_with_profiles(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        for dim in TRUST_DIMENSIONS:
            te.record_event("alice", dim, 0.9)
        s = te.stats()
        assert s["total_profiles"] == 1
        assert s["meaningful_profiles"] == 1
        assert s["average_trust"] == 0.9
        assert s["review_exempt"] == 1


# ═══════════════════════════════════════════════════════════════════════════
# 6. Server wiring — cmd_trust
# ═══════════════════════════════════════════════════════════════════════════

class TestCmdTrust:
    @pytest.mark.asyncio
    async def test_trust_shows_own_profile(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "")
        text = agent.writer.get_text()
        assert "Trust Profile" in text
        assert "Alice" in text
        assert "Composite:" in text

    @pytest.mark.asyncio
    async def test_trust_shows_dimensions(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "")
        text = agent.writer.get_text()
        for dim in TRUST_DIMENSIONS:
            assert dim in text

    @pytest.mark.asyncio
    async def test_trust_board_empty(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "board")
        text = agent.writer.get_text()
        assert "No agents" in text or "Leaderboard" in text

    @pytest.mark.asyncio
    async def test_trust_record_valid_event(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "record task_completed")
        text = agent.writer.get_text()
        assert "Recorded" in text
        assert "task_completed" in text

    @pytest.mark.asyncio
    async def test_trust_record_invalid_event(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "record nonexistent_event")
        text = agent.writer.get_text()
        assert "Unknown event" in text

    @pytest.mark.asyncio
    async def test_trust_compare(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "compare Bob")
        text = agent.writer.get_text()
        assert "Comparison" in text or "Usage" in text

    @pytest.mark.asyncio
    async def test_trust_agent_not_meaningful(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        await handler.cmd_trust(agent, "Bob")
        text = agent.writer.get_text()
        assert "meaningful" in text.lower() or "Usage" in text or "Bob" in text

    @pytest.mark.asyncio
    async def test_trust_engine_initialized_in_world(self):
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        assert world.trust_engine is not None

    @pytest.mark.asyncio
    async def test_ensure_trust_returns_engine(self):
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        te = world.ensure_trust()
        assert te is not None

    @pytest.mark.asyncio
    async def test_trust_record_persists_to_profile(self):
        agent = make_agent("Alice")
        world = World(world_dir=str(Path(tempfile.mkdtemp()) / "world"))
        handler = CommandHandler(world)
        # Record multiple events to make meaningful
        for _ in range(3):
            await handler.cmd_trust(agent, "record task_completed")
            await handler.cmd_trust(agent, "record code_review_passed")
            await handler.cmd_trust(agent, "record tests_written")
        te = world.ensure_trust()
        profile = te.get_profile("Alice")
        assert profile.is_meaningful()


# ═══════════════════════════════════════════════════════════════════════════
# 7. Edge cases
# ═══════════════════════════════════════════════════════════════════════════

class TestEdgeCases:
    def test_single_event_composite(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.record_event("alice", "code_quality", 0.5)
        # Other dims at BASE_TRUST, code_quality at 0.5
        composite = te.composite_trust("alice")
        assert 0.0 <= composite <= 1.0

    def test_all_zero_values(self, tmp_trust_dir):
        tp = TrustProfile(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            tp.record(dim, 0.0)
        assert tp.composite() == 0.0

    def test_all_one_values(self, tmp_trust_dir):
        tp = TrustProfile(agent_name="alice")
        for dim in TRUST_DIMENSIONS:
            tp.record(dim, 1.0)
        assert tp.composite() == 1.0

    def test_very_old_event_minimal_impact(self, tmp_trust_dir):
        wh = WeightedHistory(decay_rate=0.9)
        very_old = time.time() - (365 * 86400)  # 1 year ago
        wh.add(1.0, timestamp=very_old)
        wh.add(0.5, timestamp=time.time())
        score = wh.score()
        # Old event should have minimal weight
        assert 0.49 < score < 0.52

    def test_engine_save_nonexistent_profile(self, tmp_trust_dir):
        te = TrustEngine(data_dir=tmp_trust_dir)
        te.save("nobody")  # should not crash

    def test_profile_from_dict_minimal(self):
        data = {"agent_name": "minimal"}
        tp = TrustProfile.from_dict(data)
        assert tp.agent_name == "minimal"
        # Should have default dimensions
        for dim in TRUST_DIMENSIONS:
            assert dim in tp.dimensions

    def test_weighted_history_zero_weight(self):
        wh = WeightedHistory()
        wh.add(1.0, weight=0.0)
        # Zero weight event means weight_total=0, so returns BASE_TRUST
        assert wh.score() == BASE_TRUST
        # But adding a real event on top gives the real event's score
        wh.add(0.8, weight=1.0)
        assert wh.score() == 0.8

    def test_weighted_history_negative_weight(self):
        wh = WeightedHistory()
        wh.add(0.0, weight=-1.0)
        # Negative weight makes the score calculation subtract
        # But clamp keeps in range
        score = wh.score()
        assert 0.0 <= score <= 1.0

    def test_multiple_prune_calls(self):
        wh = WeightedHistory()
        now = time.time()
        for i in range(10):
            wh.add(0.5, timestamp=now - i * 86400)
        wh.prune(max_age_days=5)
        count1 = wh.event_count()
        wh.prune(max_age_days=2)
        count2 = wh.event_count()
        assert count2 <= count1
