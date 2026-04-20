#!/usr/bin/env python3
"""
Tests for tabula_rasa integration into server.py — permissions, budgets, spells, room library.
"""

import asyncio
import pytest
import json
import os
import sys

# Ensure the project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tabula_rasa import (
    PermissionLevel, AgentBudget, ToolRoom, RoomLibrary,
    SpellBook, Ship,
)


# ═══════════════════════════════════════════════════════════════
# PermissionLevel Tests
# ═══════════════════════════════════════════════════════════════

class TestPermissionLevel:
    def test_has_six_levels(self):
        assert len(PermissionLevel.LEVELS) == 6

    def test_level_titles(self):
        assert PermissionLevel.title(0) == "Greenhorn"
        assert PermissionLevel.title(1) == "Crew"
        assert PermissionLevel.title(2) == "Specialist"
        assert PermissionLevel.title(3) == "Captain"
        assert PermissionLevel.title(4) == "Cocapn"
        assert PermissionLevel.title(5) == "Architect"

    def test_invalid_level_returns_greenhorn(self):
        assert PermissionLevel.title(99) == "Greenhorn"
        assert PermissionLevel.title(-1) == "Greenhorn"

    def test_can_do_basic_actions(self):
        assert PermissionLevel.can_do(0, "look") is True
        assert PermissionLevel.can_do(0, "go") is True
        assert PermissionLevel.can_do(0, "say") is True
        assert PermissionLevel.can_do(0, "help") is True

    def test_greenhorn_cannot_build(self):
        assert PermissionLevel.can_do(0, "build_room") is False

    def test_specialist_can_build(self):
        assert PermissionLevel.can_do(2, "build_room") is True
        assert PermissionLevel.can_do(2, "cast_spell") is True

    def test_captain_can_manage_vessel(self):
        assert PermissionLevel.can_do(3, "manage_vessel") is True
        assert PermissionLevel.can_do(3, "create_adventure") is True

    def test_cocapn_can_edit_any_room(self):
        assert PermissionLevel.can_do(4, "edit_any_room") is True
        assert PermissionLevel.can_do(4, "create_tool_room") is True

    def test_architect_can_do_all(self):
        assert PermissionLevel.can_do(5, "anything_at_all") is True
        assert PermissionLevel.can_do(5, "build_room") is True
        assert PermissionLevel.can_do(5, "refactor_engine") is True

    def test_hierarchy_is_ordered(self):
        for lvl in range(5):
            higher_perms = set(PermissionLevel.LEVELS[lvl + 1]["can"])
            lower_perms = set(PermissionLevel.LEVELS[lvl]["can"])
            # Architect (5) has ALL, so level 4 -> 5 is a special case
            if lvl + 1 < 5:
                assert not higher_perms.issubset(lower_perms), f"Level {lvl+1} should have more perms than {lvl}"


# ═══════════════════════════════════════════════════════════════
# AgentBudget Tests
# ═══════════════════════════════════════════════════════════════

class TestAgentBudget:
    def test_creation_defaults(self):
        b = AgentBudget(agent="test-agent")
        assert b.agent == "test-agent"
        assert b.mana == 100
        assert b.mana_max == 100
        assert b.hp == 100
        assert b.hp_max == 100
        assert b.trust == 0.3
        assert b.xp == 0
        assert b.level == 0
        assert b.reviews_required is True

    def test_custom_starting_values(self):
        b = AgentBudget(agent="custom", mana=50, hp=50, trust=0.8, xp=100)
        assert b.mana == 50
        assert b.hp == 50
        assert b.trust == 0.8
        assert b.xp == 100

    def test_spend_mana_success(self):
        b = AgentBudget(agent="spender")
        assert b.spend_mana(30) is True
        assert b.mana == 70

    def test_spend_mana_insufficient(self):
        b = AgentBudget(agent="broke")
        assert b.spend_mana(200) is False
        assert b.mana == 100  # unchanged

    def test_spend_hp_success(self):
        b = AgentBudget(agent="worker")
        assert b.spend_hp(3) is True
        assert b.hp == 97

    def test_spend_hp_insufficient(self):
        b = AgentBudget(agent="exhausted")
        assert b.spend_hp(200) is False
        assert b.hp == 100  # unchanged

    def test_rest_restores_resources(self):
        b = AgentBudget(agent="tired")
        b.spend_mana(50)
        b.spend_hp(5)
        b.rest()
        assert b.mana == 100
        assert b.hp == 100

    def test_record_task_updates_counters(self):
        b = AgentBudget(agent="productive")
        b.record_task(20, delivered_extra=True)
        assert b.tasks_completed == 1
        assert b.tasks_under_budget == 1
        assert b.tasks_over_delivered == 1
        assert b.xp > 0

    def test_level_up_increases_budgets(self):
        b = AgentBudget(agent="leveler")
        b.level_up(2)
        assert b.level == 2
        assert b.mana_max == 200  # 100 + 2*50
        assert b.hp_max == 20     # 10 + 2*5
        # Restored after level up
        assert b.mana == 200
        assert b.hp == 20

    def test_trust_increases_with_consistent_work(self):
        b = AgentBudget(agent="trustworthy")
        for i in range(5):
            b.record_task(10, delivered_extra=True)
        assert b.trust > 0.5

    def test_to_dict(self):
        b = AgentBudget(agent="serial")
        d = b.to_dict()
        assert d["agent"] == "serial"
        assert "title" in d
        assert d["mana"] == 100
        assert d["hp"] == 100


# ═══════════════════════════════════════════════════════════════
# SpellBook Tests
# ═══════════════════════════════════════════════════════════════

class TestSpellBook:
    def test_has_18_spells(self):
        assert len(SpellBook.SPELLS) == 18

    def test_cantrip_available_at_level_0(self):
        spells = SpellBook.available(0)
        names = [s["name"] for s in spells]
        assert "Read" in names
        assert "Look" in names
        assert "Navigatium" in names

    def test_level_1_unlocks_more_spells(self):
        lvl0 = SpellBook.available(0)
        lvl1 = SpellBook.available(1)
        assert len(lvl1) > len(lvl0)
        names = [s["name"] for s in lvl1]
        assert "Scribus" in names
        assert "Mailus" in names
        assert "Detectum" in names

    def test_level_2_unlocks_build_spells(self):
        spells = SpellBook.available(2)
        names = [s["name"] for s in spells]
        assert "Constructus" in names
        assert "Summonus" in names
        assert "Reviewum" in names

    def test_level_3_unlocks_ship_spell(self):
        spells = SpellBook.available(3)
        names = [s["name"] for s in spells]
        assert "Shippus" in names
        assert "Adventurium" in names

    def test_level_4_unlocks_refactoring(self):
        spells = SpellBook.available(4)
        names = [s["name"] for s in spells]
        assert "Refactorium" in names
        assert "Creatius" in names

    def test_cast_success(self):
        result = SpellBook.cast("read", 0, 100)
        assert result["success"] is True
        assert result["spell"] == "Read"
        assert result["mana_cost"] == 0

    def test_cast_unknown_spell(self):
        result = SpellBook.cast("nonexistent", 0, 100)
        assert "error" in result

    def test_cast_insufficient_level(self):
        result = SpellBook.cast("constructus", 0, 100)
        assert "error" in result
        assert "level" in result["error"].lower()

    def test_cast_insufficient_mana(self):
        result = SpellBook.cast("constructus", 2, 5)
        assert "error" in result
        assert "mana" in result["error"].lower()


# ═══════════════════════════════════════════════════════════════
# RoomLibrary Tests
# ═══════════════════════════════════════════════════════════════

class TestRoomLibrary:
    def test_has_8_rooms(self):
        assert len(RoomLibrary.ROOMS) == 8

    def test_catalog_returns_list(self):
        catalog = RoomLibrary.catalog()
        assert isinstance(catalog, list)
        assert len(catalog) == 8
        for entry in catalog:
            assert "id" in entry
            assert "name" in entry
            assert "type" in entry
            assert "level" in entry
            assert "commands" in entry

    def test_get_existing_room(self):
        room = RoomLibrary.get("dojo-room")
        assert room is not None
        assert room.name == "The Training Dojo"

    def test_get_nonexistent_room(self):
        room = RoomLibrary.get("nonexistent-room")
        assert room is None

    def test_search_by_name(self):
        results = RoomLibrary.search("monitor")
        assert len(results) > 0
        ids = [r["id"] for r in results]
        assert "monitor-room" in ids

    def test_search_by_type(self):
        results = RoomLibrary.search("tool")
        assert len(results) > 0

    def test_search_no_results(self):
        results = RoomLibrary.search("xyznonexistent123")
        assert len(results) == 0

    def test_all_rooms_have_commands(self):
        for room_id, room in RoomLibrary.ROOMS.items():
            assert len(room.commands) > 0, f"Room {room_id} has no commands"

    def test_dojo_min_level_zero(self):
        dojo = RoomLibrary.get("dojo-room")
        assert dojo.min_level == 0

    def test_deckboss_min_level_four(self):
        deckboss = RoomLibrary.get("deckboss-room")
        assert deckboss.min_level == 4


# ═══════════════════════════════════════════════════════════════
# Ship Tests
# ═══════════════════════════════════════════════════════════════

class TestShip:
    def test_creation(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        assert ship.name == "Test Ship"
        assert ship.captain == "test-agent"
        assert ship.ship_type == "vessel"
        assert len(ship.rooms) == 0
        assert len(ship.crew) == 0

    def test_install_room(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        assert ship.install_room("dojo-room") is True
        assert "dojo-room" in ship.rooms
        assert ship.rooms["dojo-room"].name == "The Training Dojo"

    def test_install_nonexistent_room(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        assert ship.install_room("nonexistent-room") is False
        assert len(ship.rooms) == 0

    def test_remove_room(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        ship.install_room("dojo-room")
        assert ship.remove_room("dojo-room") is True
        assert "dojo-room" not in ship.rooms

    def test_remove_nonexistent_room(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        assert ship.remove_room("nonexistent") is False

    def test_list_rooms(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        ship.install_room("dojo-room")
        ship.install_room("monitor-room")
        rooms = ship.list_rooms()
        assert len(rooms) == 2
        names = [r["name"] for r in rooms]
        assert "The Training Dojo" in names
        assert "The Watch Tower" in names

    def test_to_dict(self):
        ship = Ship(name="Test Ship", captain="test-agent")
        ship.install_room("dojo-room")
        ship.crew.append("agent1")
        d = ship.to_dict()
        assert d["name"] == "Test Ship"
        assert d["captain"] == "test-agent"
        assert "dojo-room" in d["rooms"]
        assert "agent1" in d["crew"]

    def test_multiple_rooms(self):
        ship = Ship(name="Multi Ship", captain="test-agent")
        installed = []
        for room_id in RoomLibrary.ROOMS:
            if ship.install_room(room_id):
                installed.append(room_id)
        assert len(installed) == 8  # all rooms can be installed
        assert len(ship.rooms) == 8


# ═══════════════════════════════════════════════════════════════
# ToolRoom Tests
# ═══════════════════════════════════════════════════════════════

class TestToolRoom:
    def test_use_command(self):
        dojo = RoomLibrary.get("dojo-room")
        result = dojo.use_command("train", "test-agent")
        assert "room" in result
        assert result["room"] == "The Training Dojo"
        assert result["command"] == "train"

    def test_use_unknown_command(self):
        dojo = RoomLibrary.get("dojo-room")
        result = dojo.use_command("nonexistent", "test-agent")
        assert "error" in result

    def test_read_instructions(self):
        dojo = RoomLibrary.get("dojo-room")
        instructions = dojo.read_instructions()
        assert "The Training Dojo" in instructions
        assert "train" in instructions

    def test_room_with_spells(self):
        spreader = RoomLibrary.get("spreader-room")
        assert len(spreader.spells) > 0
        assert spreader.spells[0]["name"] == "six-eyes"


# ═══════════════════════════════════════════════════════════════
# Server Integration Tests — CommandHandler methods
# ═══════════════════════════════════════════════════════════════

class TestServerIntegration:
    """Test the command handlers wired into CommandHandler."""

    def _make_handler(self):
        """Create a CommandHandler with a World using temp dir."""
        import tempfile, shutil
        from server import World, CommandHandler
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        handler = CommandHandler(world)
        # Clean up tmpdir later
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

    def test_world_has_tabula_rasa_attributes(self):
        import tempfile
        from server import World
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        assert hasattr(world, 'budgets')
        assert hasattr(world, 'permission_levels')
        assert hasattr(world, 'ship')
        assert isinstance(world.budgets, dict)
        assert isinstance(world.permission_levels, dict)
        assert world.ship is None  # not yet initialized

    def test_check_permission_default(self):
        handler, world = self._make_handler()
        agent = self._make_agent("perm-test", world)
        allowed, level, title = handler.check_permission(agent, 0)
        assert allowed is True
        assert level == 0
        assert title == "Greenhorn"

    def test_check_permission_insufficient(self):
        handler, world = self._make_handler()
        agent = self._make_agent("perm-test2", world)
        world.permission_levels["perm-test2"] = 0
        allowed, level, title = handler.check_permission(agent, 2)
        assert allowed is False

    @pytest.mark.asyncio
    async def test_cmd_budget(self):
        handler, world = self._make_handler()
        agent = self._make_agent("budget-agent", world)
        output = []
        # Mock send
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_budget(agent, "")
        assert len(output) == 1
        assert "Budget:" in output[0]
        assert "Greenhorn" in output[0]
        assert "Mana:" in output[0]

    @pytest.mark.asyncio
    async def test_cmd_budget_no_budget(self):
        handler, world = self._make_handler()
        from server import Agent
        agent = Agent(name="no-budget", room_name="tavern")
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_budget(agent, "")
        assert len(output) == 1
        assert "No budget found" in output[0]

    @pytest.mark.asyncio
    async def test_cmd_cast_success(self):
        handler, world = self._make_handler()
        agent = self._make_agent("caster", world)
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_cast(agent, "read")
        assert any("cast Read" in o for o in output)
        # Mana should be spent (0 for read, so budget unchanged)
        budget = world.budgets["caster"]
        assert budget.mana == 100  # read costs 0 mana

    @pytest.mark.asyncio
    async def test_cmd_cast_insufficient_level(self):
        handler, world = self._make_handler()
        agent = self._make_agent("low-caster", world)
        world.permission_levels["low-caster"] = 0
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_cast(agent, "constructus")
        assert any("level" in o.lower() for o in output)

    @pytest.mark.asyncio
    async def test_cmd_cast_unknown(self):
        handler, world = self._make_handler()
        agent = self._make_agent("bad-caster", world)
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_cast(agent, "nonexistent_spell")
        assert any("Unknown spell" in o for o in output)

    @pytest.mark.asyncio
    async def test_cmd_catalog(self):
        handler, world = self._make_handler()
        agent = self._make_agent("catalog-user", world)
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_catalog(agent, "")
        assert len(output) == 1
        text = output[0]
        assert "Room Library" in text
        assert "8 rooms" in text
        # Should list some room names
        assert "Training Dojo" in text

    @pytest.mark.asyncio
    async def test_cmd_install_success(self):
        handler, world = self._make_handler()
        agent = self._make_agent("installer", world)
        world.ship = Ship(name="Test Ship", captain="installer")
        output = []
        async def mock_send(a, text):
            output.append(text)
        async def mock_broadcast(text, exclude=None):
            output.append(text)
        handler.send = mock_send
        handler.broadcast_all = mock_broadcast

        await handler.cmd_install(agent, "dojo-room")
        assert any("Installed" in o for o in output)
        assert "dojo-room" in world.ship.rooms

    @pytest.mark.asyncio
    async def test_cmd_install_locked(self):
        handler, world = self._make_handler()
        agent = self._make_agent("green-installer", world)
        world.permission_levels["green-installer"] = 0
        world.ship = Ship(name="Test Ship", captain="green-installer")
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_install(agent, "deckboss-room")
        assert any("requires level" in o for o in output)

    @pytest.mark.asyncio
    async def test_cmd_install_nonexistent(self):
        handler, world = self._make_handler()
        agent = self._make_agent("bad-installer", world)
        world.ship = Ship(name="Test Ship", captain="bad-installer")
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_install(agent, "nonexistent-room")
        assert any("Unknown room" in o for o in output)

    @pytest.mark.asyncio
    async def test_cmd_ship(self):
        handler, world = self._make_handler()
        agent = self._make_agent("ship-cmd-user", world)
        world.ship = Ship(name="Test Ship", captain="ship-cmd-user")
        world.ship.install_room("dojo-room")
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_ship(agent, "")
        assert len(output) == 1
        text = output[0]
        assert "Test Ship" in text
        assert "Training Dojo" in text

    @pytest.mark.asyncio
    async def test_cmd_ship_no_ship(self):
        handler, world = self._make_handler()
        agent = self._make_agent("no-ship-user", world)
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        await handler.cmd_ship(agent, "")
        assert any("No ship" in o for o in output)

    @pytest.mark.asyncio
    async def test_cmd_cast_spends_mana(self):
        handler, world = self._make_handler()
        agent = self._make_agent("mana-user", world)
        world.permission_levels["mana-user"] = 1
        world.budgets["mana-user"].level = 1
        output = []
        async def mock_send(a, text):
            output.append(text)
        handler.send = mock_send

        budget = world.budgets["mana-user"]
        initial_mana = budget.mana
        await handler.cmd_cast(agent, "scribus")
        # Scribus costs 5 mana
        assert budget.mana == initial_mana - 5

    @pytest.mark.asyncio
    async def test_handlers_registered(self):
        """Verify the 5 new commands are in the handler dispatch table."""
        import tempfile
        from server import CommandHandler, World
        tmpdir = tempfile.mkdtemp()
        world = World(world_dir=tmpdir)
        handler = CommandHandler(world)
        # The handle method references these as self.cmd_*
        assert hasattr(handler, 'cmd_budget')
        assert hasattr(handler, 'cmd_cast')
        assert hasattr(handler, 'cmd_catalog')
        assert hasattr(handler, 'cmd_install')
        assert hasattr(handler, 'cmd_ship')
        assert hasattr(handler, 'check_permission')
