#!/usr/bin/env python3
"""
Tests for tabula_rasa_persistence.py — JSON-backed persistence for budgets,
permissions, ship state, trust history, and audit log.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabula_rasa_persistence import TabulaRasaStore
from tabula_rasa import AgentBudget, PermissionLevel, Ship


# ═══════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════

@pytest.fixture
def tmp_store(tmp_path):
    """Create a TabulaRasaStore with a temporary directory."""
    store = TabulaRasaStore(data_dir=str(tmp_path / "tabula_rasa"))
    return store


# ═══════════════════════════════════════════════════════════════
# Budget Persistence Tests
# ═══════════════════════════════════════════════════════════════

class TestBudgetPersistence:

    def test_save_load_budget_roundtrip(self, tmp_store):
        """Budget data survives save/load cycle."""
        data = {
            "agent": "test-agent",
            "level": 2,
            "xp": 150,
            "mana": 80,
            "mana_max": 200,
            "hp": 20,
            "hp_max": 20,
            "trust": 0.75,
            "reviews_required": False,
            "tasks_completed": 5,
            "tasks_under_budget": 3,
            "tasks_over_delivered": 2,
        }
        tmp_store.save_budget("test-agent", data)
        loaded = tmp_store.load_budget("test-agent")
        assert loaded is not None
        assert loaded["agent"] == "test-agent"
        assert loaded["level"] == 2
        assert loaded["mana"] == 80
        assert loaded["trust"] == 0.75
        assert loaded["tasks_completed"] == 5
        assert "_saved_at" in loaded

    def test_load_missing_budget_returns_none(self, tmp_store):
        """Loading a non-existent budget returns None."""
        result = tmp_store.load_budget("nobody")
        assert result is None

    def test_delete_budget(self, tmp_store):
        """Delete an existing budget returns True."""
        tmp_store.save_budget("delete-me", {"agent": "delete-me"})
        assert tmp_store.delete_budget("delete-me") is True
        assert tmp_store.load_budget("delete-me") is None

    def test_delete_nonexistent_budget(self, tmp_store):
        """Deleting a non-existent budget returns False."""
        assert tmp_store.delete_budget("ghost") is False

    def test_list_budgets(self, tmp_store):
        """List all saved budgets."""
        tmp_store.save_budget("alpha", {"agent": "alpha", "mana": 50})
        tmp_store.save_budget("bravo", {"agent": "bravo", "mana": 75})
        budgets = tmp_store.list_budgets()
        assert len(budgets) == 2
        assert "alpha" in budgets
        assert "bravo" in budgets
        assert budgets["alpha"]["mana"] == 50

    def test_save_budget_adds_timestamp(self, tmp_store):
        """Saving a budget adds a _saved_at field."""
        tmp_store.save_budget("ts-agent", {"agent": "ts-agent"})
        loaded = tmp_store.load_budget("ts-agent")
        assert "_saved_at" in loaded
        # Should be parseable ISO timestamp
        datetime.fromisoformat(loaded["_saved_at"])

    def test_budget_file_is_json(self, tmp_store):
        """Budget file is valid JSON."""
        tmp_store.save_budget("json-agent", {"agent": "json-agent", "mana": 42})
        path = tmp_store.data_dir / "budgets" / "json-agent.json"
        assert path.exists()
        data = json.loads(path.read_text())
        assert data["mana"] == 42

    def test_save_overwrites_existing(self, tmp_store):
        """Saving again overwrites the previous budget."""
        tmp_store.save_budget("overwrite", {"agent": "overwrite", "mana": 10})
        tmp_store.save_budget("overwrite", {"agent": "overwrite", "mana": 99})
        loaded = tmp_store.load_budget("overwrite")
        assert loaded["mana"] == 99


# ═══════════════════════════════════════════════════════════════
# Permission Persistence Tests
# ═══════════════════════════════════════════════════════════════

class TestPermissionPersistence:

    def test_save_load_permission_roundtrip(self, tmp_store):
        """Permission level survives save/load cycle."""
        tmp_store.save_budget("perm-agent", {"agent": "perm-agent"})
        tmp_store.save_permission("perm-agent", 3)
        loaded = tmp_store.load_permission("perm-agent")
        assert loaded == 3

    def test_save_permission_without_budget(self, tmp_store):
        """Permission saved even without a budget file creates the file."""
        tmp_store.save_permission("standalone", 2)
        loaded = tmp_store.load_permission("standalone")
        assert loaded == 2

    def test_load_missing_permission_returns_none(self, tmp_store):
        """Loading a non-existent permission returns None."""
        result = tmp_store.load_permission("nobody")
        assert result is None

    def test_permission_updates_existing_budget(self, tmp_store):
        """Saving permission updates the budget file."""
        tmp_store.save_budget("upd-agent", {"agent": "upd-agent", "mana": 50})
        tmp_store.save_permission("upd-agent", 4)
        loaded = tmp_store.load_budget("upd-agent")
        assert loaded["permission_level"] == 4


# ═══════════════════════════════════════════════════════════════
# Ship State Persistence Tests
# ═══════════════════════════════════════════════════════════════

class TestShipPersistence:

    def test_save_load_ship_roundtrip(self, tmp_store):
        """Ship state survives save/load cycle."""
        ship_data = {
            "name": "The Voyager",
            "captain": "ncc-1701",
            "ship_type": "vessel",
            "rooms": ["dojo-room", "monitor-room"],
            "crew": ["ncc-1701", "spock"],
            "level": 2,
            "created": "2026-01-01T00:00:00+00:00",
        }
        tmp_store.save_ship(ship_data)
        loaded = tmp_store.load_ship()
        assert loaded is not None
        assert loaded["name"] == "The Voyager"
        assert loaded["captain"] == "ncc-1701"
        assert loaded["rooms"] == ["dojo-room", "monitor-room"]
        assert loaded["crew"] == ["ncc-1701", "spock"]

    def test_load_missing_ship_returns_none(self, tmp_store):
        """Loading non-existent ship returns None."""
        result = tmp_store.load_ship()
        assert result is None

    def test_save_ship_overwrites(self, tmp_store):
        """Saving ship state overwrites previous."""
        tmp_store.save_ship({"name": "Old Ship", "captain": "old"})
        tmp_store.save_ship({"name": "New Ship", "captain": "new"})
        loaded = tmp_store.load_ship()
        assert loaded["name"] == "New Ship"

    def test_save_ship_with_to_dict(self, tmp_store):
        """Ship.to_dict() works directly with save_ship."""
        ship = Ship(name="Test Ship", captain="test")
        ship.install_room("dojo-room")
        ship.crew.append("crew1")
        tmp_store.save_ship(ship.to_dict())
        loaded = tmp_store.load_ship()
        assert loaded["name"] == "Test Ship"
        assert "dojo-room" in loaded["rooms"]


# ═══════════════════════════════════════════════════════════════
# Trust History Tests
# ═══════════════════════════════════════════════════════════════

class TestTrustHistory:

    def test_record_and_retrieve_trust_events(self, tmp_store):
        """Trust events are recorded and retrievable."""
        tmp_store.record_trust_event("trustee", "task_complete", {"mana_used": 15})
        tmp_store.record_trust_event("trustee", "review_pass", {"reviewer": "captain"})
        history = tmp_store.get_trust_history("trustee")
        assert len(history) == 2
        # Most recent first
        assert history[0]["event_type"] == "review_pass"
        assert history[1]["event_type"] == "task_complete"

    def test_trust_history_limit(self, tmp_store):
        """Trust history can be limited."""
        for i in range(10):
            tmp_store.record_trust_event("limited", "task_complete", {"n": i})
        history = tmp_store.get_trust_history("limited", limit=3)
        assert len(history) == 3

    def test_trust_history_missing_agent(self, tmp_store):
        """Missing agent returns empty list."""
        history = tmp_store.get_trust_history("nobody")
        assert history == []

    def test_trust_events_are_jsonl(self, tmp_store):
        """Trust events are stored as JSONL (one JSON per line)."""
        tmp_store.record_trust_event("jl-agent", "task_fail", {"reason": "timeout"})
        path = tmp_store.data_dir / "trust" / "jl-agent.jsonl"
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["event_type"] == "task_fail"
        assert data["details"]["reason"] == "timeout"

    def test_trust_event_has_timestamp(self, tmp_store):
        """Trust events include ISO timestamps."""
        tmp_store.record_trust_event("ts", "task_complete")
        history = tmp_store.get_trust_history("ts")
        assert "timestamp" in history[0]
        datetime.fromisoformat(history[0]["timestamp"])


# ═══════════════════════════════════════════════════════════════
# Audit Log Tests
# ═══════════════════════════════════════════════════════════════

class TestAuditLog:

    def test_log_and_retrieve_audit_entries(self, tmp_store):
        """Audit entries are logged and retrievable."""
        tmp_store.log_audit("alice", "connect", {"role": "vessel"})
        tmp_store.log_audit("bob", "connect", {"role": "scout"})
        tmp_store.log_audit("alice", "disconnect", {})
        log = tmp_store.get_audit_log()
        assert len(log) == 3
        # Most recent first
        assert log[0]["agent"] == "alice"
        assert log[0]["action"] == "disconnect"

    def test_audit_log_filter_by_agent(self, tmp_store):
        """Audit log can be filtered by agent name."""
        tmp_store.log_audit("alice", "connect", {})
        tmp_store.log_audit("bob", "connect", {})
        tmp_store.log_audit("alice", "disconnect", {})
        log = tmp_store.get_audit_log(agent_name="alice")
        assert len(log) == 2
        for entry in log:
            assert entry["agent"] == "alice"

    def test_audit_log_limit(self, tmp_store):
        """Audit log can be limited."""
        for i in range(20):
            tmp_store.log_audit("agent", "action", {"i": i})
        log = tmp_store.get_audit_log(limit=5)
        assert len(log) == 5

    def test_audit_log_empty(self, tmp_store):
        """Empty audit log returns empty list."""
        log = tmp_store.get_audit_log()
        assert log == []

    def test_audit_log_is_jsonl(self, tmp_store):
        """Audit log is stored as JSONL."""
        tmp_store.log_audit("jl", "connect")
        path = tmp_store.data_dir / "audit.jsonl"
        assert path.exists()
        lines = path.read_text().strip().split("\n")
        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["agent"] == "jl"
        assert data["action"] == "connect"


# ═══════════════════════════════════════════════════════════════
# Bulk Operations Tests
# ═══════════════════════════════════════════════════════════════

class TestBulkOperations:

    def test_save_all_budgets_and_permissions(self, tmp_store):
        """save_all persists all budgets and permissions."""
        b1 = AgentBudget(agent="bulk1", level=2, xp=200)
        b2 = AgentBudget(agent="bulk2", level=0)
        perms = {"bulk1": 2, "bulk2": 0}
        tmp_store.save_all({"bulk1": b1, "bulk2": b2}, perms)
        # Verify they can be loaded back
        loaded = tmp_store.load_all()
        assert "bulk1" in loaded["budgets"]
        assert "bulk2" in loaded["budgets"]
        assert loaded["permissions"]["bulk1"] == 2
        assert loaded["permissions"]["bulk2"] == 0

    def test_save_all_with_ship(self, tmp_store):
        """save_all persists ship state too."""
        ship = Ship(name="Bulk Ship", captain="captain")
        ship.install_room("dojo-room")
        tmp_store.save_all({}, {}, ship=ship)
        loaded = tmp_store.load_all()
        assert loaded["ship"] is not None
        assert loaded["ship"]["name"] == "Bulk Ship"
        assert "dojo-room" in loaded["ship"]["rooms"]

    def test_load_all_returns_structure(self, tmp_store):
        """load_all returns {budgets, permissions, ship}."""
        result = tmp_store.load_all()
        assert "budgets" in result
        assert "permissions" in result
        assert "ship" in result
        assert isinstance(result["budgets"], dict)
        assert isinstance(result["permissions"], dict)

    def test_export_snapshot_includes_everything(self, tmp_store):
        """export_snapshot includes budgets, permissions, ship, trust, audit."""
        b = AgentBudget(agent="snap", level=1)
        ship = Ship(name="Snap Ship", captain="snap")
        tmp_store.save_all({"snap": b}, {"snap": 1}, ship=ship)
        tmp_store.record_trust_event("snap", "task_complete")
        tmp_store.log_audit("snap", "connect")

        snapshot = tmp_store.export_snapshot()
        assert "snap" in snapshot["budgets"]
        assert snapshot["permissions"]["snap"] == 1
        assert snapshot["ship"]["name"] == "Snap Ship"
        assert "snap" in snapshot["trust_histories"]
        assert len(snapshot["trust_histories"]["snap"]) == 1
        assert len(snapshot["audit_log"]) >= 2  # connect + snapshot_save
        assert "exported_at" in snapshot


# ═══════════════════════════════════════════════════════════════
# Prune Stale Tests
# ═══════════════════════════════════════════════════════════════

class TestPruneStale:

    def test_prune_stale_removes_old(self, tmp_store):
        """Agents not seen in N days get pruned."""
        # Write stale budget file directly (save_budget overwrites _saved_at)
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        stale_path = tmp_store.data_dir / "budgets" / "stale-agent.json"
        stale_path.write_text(json.dumps({"agent": "stale-agent", "_saved_at": old_date}))
        # Create a fresh budget via save_budget (gets current timestamp)
        tmp_store.save_budget("fresh-agent", {"agent": "fresh-agent"})

        pruned = tmp_store.prune_stale(max_age_days=30)
        assert pruned == 1
        assert tmp_store.load_budget("stale-agent") is None
        assert tmp_store.load_budget("fresh-agent") is not None

    def test_prune_stale_removes_trust_history(self, tmp_store):
        """Pruning also removes trust history files."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        stale_path = tmp_store.data_dir / "budgets" / "stale-trust.json"
        stale_path.write_text(json.dumps({"agent": "stale-trust", "_saved_at": old_date}))
        tmp_store.record_trust_event("stale-trust", "task_complete")

        tmp_store.prune_stale(max_age_days=30)
        history = tmp_store.get_trust_history("stale-trust")
        assert history == []

    def test_prune_stale_nothing_to_prune(self, tmp_store):
        """Returns 0 when nothing is stale."""
        tmp_store.save_budget("recent", {"agent": "recent"})
        pruned = tmp_store.prune_stale(max_age_days=30)
        assert pruned == 0

    def test_prune_stale_custom_age(self, tmp_store):
        """Custom max_age_days works."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=15)).isoformat()
        medium_path = tmp_store.data_dir / "budgets" / "medium.json"
        medium_path.write_text(json.dumps({"agent": "medium", "_saved_at": old_date}))
        # With 30 day threshold, 15 days is not stale
        assert tmp_store.prune_stale(max_age_days=30) == 0
        # With 10 day threshold, 15 days is stale
        assert tmp_store.prune_stale(max_age_days=10) == 1


# ═══════════════════════════════════════════════════════════════
# Stats Tests
# ═══════════════════════════════════════════════════════════════

class TestStats:

    def test_stats_empty_store(self, tmp_store):
        """Empty store reports zeros."""
        stats = tmp_store.get_stats()
        assert stats["budget_count"] == 0
        assert stats["trust_count"] == 0
        assert stats["audit_entries"] == 0
        assert stats["has_ship"] is False
        assert stats["total_size_bytes"] >= 0

    def test_stats_with_data(self, tmp_store):
        """Stats reflect stored data."""
        tmp_store.save_budget("s1", {"agent": "s1"})
        tmp_store.save_budget("s2", {"agent": "s2"})
        tmp_store.record_trust_event("s1", "task_complete")
        tmp_store.log_audit("s1", "connect")
        tmp_store.save_ship({"name": "Stat Ship"})

        stats = tmp_store.get_stats()
        assert stats["budget_count"] == 2
        assert stats["trust_count"] == 1
        assert stats["audit_entries"] == 1
        assert stats["has_ship"] is True
        assert stats["total_size_bytes"] > 0

    def test_stats_has_data_dir(self, tmp_store):
        """Stats include the data directory path."""
        stats = tmp_store.get_stats()
        assert "tabula_rasa" in stats["data_dir"]


# ═══════════════════════════════════════════════════════════════
# Directory Structure Tests
# ═══════════════════════════════════════════════════════════════

class TestDirectoryStructure:

    def test_creates_subdirectories(self, tmp_store):
        """Store creates budgets/ and trust/ subdirectories."""
        assert (tmp_store.data_dir / "budgets").is_dir()
        assert (tmp_store.data_dir / "trust").is_dir()

    def test_budgets_directory_has_agent_files(self, tmp_store):
        """Budget files go into budgets/ directory."""
        tmp_store.save_budget("dir-test", {"agent": "dir-test"})
        budget_file = tmp_store.data_dir / "budgets" / "dir-test.json"
        assert budget_file.exists()

    def test_trust_directory_has_agent_files(self, tmp_store):
        """Trust files go into trust/ directory."""
        tmp_store.record_trust_event("dir-trust", "event")
        trust_file = tmp_store.data_dir / "trust" / "dir-trust.jsonl"
        assert trust_file.exists()

    def test_ship_file_in_root(self, tmp_store):
        """Ship state goes in data_dir/ship.json."""
        tmp_store.save_ship({"name": "Root Ship"})
        ship_file = tmp_store.data_dir / "ship.json"
        assert ship_file.exists()

    def test_audit_file_in_root(self, tmp_store):
        """Audit log goes in data_dir/audit.jsonl."""
        tmp_store.log_audit("auditor", "action")
        audit_file = tmp_store.data_dir / "audit.jsonl"
        assert audit_file.exists()


# ═══════════════════════════════════════════════════════════════
# Server Integration — Wire Verification
# ═══════════════════════════════════════════════════════════════

class TestServerWireIntegration:

    def _make_handler(self):
        """Create a CommandHandler with a World using temp dir."""
        import tempfile
        from server import World, CommandHandler
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        handler = CommandHandler(world)
        handler._tmpdir = tmpdir
        return handler, world

    def _make_agent(self, name, world):
        """Create a test agent with budget and permission level."""
        from server import Agent
        agent = Agent(name=name, room_name="tavern")
        world.agents[name] = agent
        world.budgets[name] = AgentBudget(agent=name, mana=100, hp=100, trust=0.3, xp=0)
        world.permission_levels[name] = 0
        return agent

    def test_world_has_store(self):
        """World.store is initialized (TabulaRasaStore)."""
        import tempfile
        from server import World
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        assert hasattr(world, 'store')
        assert world.store is not None
        assert isinstance(world.store, TabulaRasaStore)

    def test_store_persists_across_restart(self):
        """Budget saved to store survives loading from a new store instance."""
        import tempfile
        from server import World
        tmpdir = tempfile.mkdtemp()
        data_dir = str(Path(tmpdir) / "tabula_rasa")

        # First instance: save a budget
        store1 = TabulaRasaStore(data_dir=data_dir)
        store1.save_budget("persistent-agent", {
            "agent": "persistent-agent",
            "level": 3,
            "mana": 200,
            "mana_max": 250,
            "trust": 0.85,
            "xp": 500,
        })
        store1.save_permission("persistent-agent", 3)

        # Second instance: load the budget
        store2 = TabulaRasaStore(data_dir=data_dir)
        loaded = store2.load_budget("persistent-agent")
        assert loaded is not None
        assert loaded["level"] == 3
        assert loaded["mana"] == 200
        assert loaded["trust"] == 0.85

        perm = store2.load_permission("persistent-agent")
        assert perm == 3

    def test_cmd_save_exists(self):
        """cmd_save is registered on the handler."""
        import tempfile
        from server import World, CommandHandler
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        handler = CommandHandler(world)
        assert hasattr(handler, 'cmd_save')

    def test_cmd_audit_exists(self):
        """cmd_audit is registered on the handler."""
        import tempfile
        from server import World, CommandHandler
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        handler = CommandHandler(world)
        assert hasattr(handler, 'cmd_audit')

    @pytest.mark.asyncio
    async def test_cmd_save_saves_state(self):
        """cmd_save persists all agent budgets."""
        handler, world = self._make_handler()
        agent = self._make_agent("save-test", world)
        world.budgets["save-test"].level = 2
        world.budgets["save-test"].mana = 50
        world.permission_levels["save-test"] = 2

        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_save(agent, "")
        assert len(output) == 1
        assert "State Saved" in output[0]
        assert "Agents saved: 1" in output[0]

        # Verify it was actually persisted
        loaded = world.store.load_budget("save-test")
        assert loaded is not None
        assert loaded["level"] == 2
        assert loaded["mana"] == 50

    @pytest.mark.asyncio
    async def test_cmd_audit_shows_log(self):
        """cmd_audit displays recent audit entries."""
        handler, world = self._make_handler()
        agent = self._make_agent("audit-test", world)
        world.store.log_audit("audit-test", "test_action", {"key": "value"})

        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_audit(agent, "")
        assert len(output) == 1
        assert "Audit Log" in output[0]
        assert "test_action" in output[0]

    @pytest.mark.asyncio
    async def test_cmd_audit_empty(self):
        """cmd_audit handles empty log."""
        handler, world = self._make_handler()
        agent = self._make_agent("empty-audit", world)

        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_audit(agent, "")
        assert any("No audit" in o for o in output)

    @pytest.mark.asyncio
    async def test_cmd_audit_filter_by_agent(self):
        """cmd_audit can filter by agent name."""
        handler, world = self._make_handler()
        agent = self._make_agent("filter-audit", world)
        world.store.log_audit("alice", "connect", {})
        world.store.log_audit("bob", "connect", {})

        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_audit(agent, "alice")
        assert "alice" in output[0]
        assert "bob" not in output[0]

    @pytest.mark.asyncio
    async def test_cmd_save_with_ship(self):
        """cmd_save also persists ship state."""
        from tabula_rasa import Ship
        handler, world = self._make_handler()
        agent = self._make_agent("ship-save", world)
        world.ship = Ship(name="Save Ship", captain="ship-save")
        world.ship.install_room("dojo-room")

        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_save(agent, "")
        loaded_ship = world.store.load_ship()
        assert loaded_ship is not None
        assert loaded_ship["name"] == "Save Ship"
        assert "dojo-room" in loaded_ship["rooms"]


# ═══════════════════════════════════════════════════════════════
# Edge Cases
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases:

    def test_agent_name_with_special_chars(self, tmp_store):
        """Agent names with hyphens and numbers work."""
        tmp_store.save_budget("agent-123", {"agent": "agent-123", "mana": 10})
        loaded = tmp_store.load_budget("agent-123")
        assert loaded is not None
        assert loaded["mana"] == 10

    def test_empty_details(self, tmp_store):
        """None details become empty dict."""
        tmp_store.log_audit("empty", "action", None)
        log = tmp_store.get_audit_log()
        assert log[0]["details"] == {}

    def test_large_trust_history(self, tmp_store):
        """Many trust events handled correctly."""
        for i in range(200):
            tmp_store.record_trust_event("busy", "task_complete", {"n": i})
        history = tmp_store.get_trust_history("busy", limit=1000)
        assert len(history) == 200
        # Default limit of 100
        default_history = tmp_store.get_trust_history("busy")
        assert len(default_history) == 100

    def test_concurrent_save_load(self, tmp_store):
        """Multiple save/load cycles work correctly."""
        for i in range(5):
            tmp_store.save_budget(f"cyc-{i}", {"agent": f"cyc-{i}", "iteration": i})
        for i in range(5):
            loaded = tmp_store.load_budget(f"cyc-{i}")
            assert loaded["iteration"] == i
        budgets = tmp_store.list_budgets()
        assert len(budgets) == 5
