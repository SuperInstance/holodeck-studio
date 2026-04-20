"""
Tests for the Room Command Execution Engine (room_engine.py).

Covers:
- RoomCommandResult creation
- RoomCommand registration
- All 28 built-in command implementations
- Cooldown enforcement
- Permission level checking
- Custom command registration and execution
- list_commands output
- Error handling (unknown command, missing args, exceptions)
- Server wiring (cmd_roomcmd, cmd_roomcommands)
"""

import asyncio
import time
import pytest
from unittest.mock import MagicMock, AsyncMock, patch

from room_engine import RoomEngine, RoomCommandResult, RoomCommand


# ═══════════════════════════════════════════════════════════════
# RoomCommandResult tests
# ═══════════════════════════════════════════════════════════════

class TestRoomCommandResult:
    def test_creation_defaults(self):
        r = RoomCommandResult(success=True, command="murmur", room_id="tavern", output="hello")
        assert r.success is True
        assert r.command == "murmur"
        assert r.room_id == "tavern"
        assert r.output == "hello"
        assert r.mana_cost == 0
        assert r.world_changes == {}
        assert r.private_output == ""

    def test_creation_full(self):
        r = RoomCommandResult(
            success=True, command="train", room_id="dojo", output="+5 XP",
            mana_cost=3, world_changes={"xp": 5}, private_output="secret"
        )
        assert r.mana_cost == 3
        assert r.world_changes == {"xp": 5}
        assert r.private_output == "secret"

    def test_failure_result(self):
        r = RoomCommandResult(success=False, command="bad", room_id="test", output="error")
        assert r.success is False


# ═══════════════════════════════════════════════════════════════
# RoomCommand registration tests
# ═══════════════════════════════════════════════════════════════

class TestRoomCommandRegistration:
    def test_create_room_command(self):
        def handler(**kwargs):
            return RoomCommandResult(True, "custom", "test", "ok")
        rc = RoomCommand(
            name="custom", description="A custom command",
            mana_cost=5, min_level=2, handler=handler,
            aliases=["c", "cust"], cooldown=10.0
        )
        assert rc.name == "custom"
        assert rc.mana_cost == 5
        assert rc.min_level == 2
        assert rc.aliases == ["c", "cust"]
        assert rc.cooldown == 10.0

    def test_register_custom_command(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "ping", "test", "pong")
        cmd = RoomCommand(name="ping", description="Ping", handler=handler)
        engine.register_command("test_room", cmd)
        result = engine.execute("test_room", "ping", "agent1", 0)
        assert result.success is True
        assert "pong" in result.output

    def test_register_command_with_alias(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "hello", "test", "world")
        cmd = RoomCommand(name="hello", description="Hello", handler=handler, aliases=["hi"])
        engine.register_command("test_room", cmd)
        # Execute via alias
        result = engine.execute("test_room", "hi", "agent1", 0)
        assert result.success is True
        assert "world" in result.output


# ═══════════════════════════════════════════════════════════════
# All 28 built-in command tests
# ═══════════════════════════════════════════════════════════════

BUILTIN_COMMANDS = [
    ("murmur", "hello world"),
    ("search", "trust systems"),
    ("browse", ""),
    ("export", ""),
    ("spread", "some content"),
    ("synthesize", ""),
    ("debate", "AI alignment"),
    ("watch", ""),
    ("alert", ""),
    ("summary", ""),
    ("history", "5"),
    ("research", "quantum computing"),
    ("summarize", ""),
    ("compare", ""),
    ("read_cell", "B2"),
    ("write_cell", "C3 hello"),
    ("formula", "AVG(scores)"),
    ("dashboard", ""),
    ("sessions", ""),
    ("shell", ""),
    ("train", "python"),
    ("practice", ""),
    ("test", ""),
    ("commission", "My Ship"),
    ("inspect", "fleet"),
    ("decommission", "Old Ship"),
]


class TestBuiltinCommands:
    """Test all 28 built-in command implementations succeed."""

    def setup_method(self):
        self.engine = RoomEngine()

    def _exec(self, name, args=""):
        return self.engine.execute("tavern", name, "TestAgent", 5, args)

    def _assert_success(self, name, args=""):
        result = self._exec(name, args)
        assert result.success is True, f"Command {name} failed: {result.output}"
        assert result.command == name
        assert result.room_id == "tavern"
        assert len(result.output) > 0
        return result

    # Commands that always succeed
    def test_murmur(self): self._assert_success("murmur", "hello world")
    def test_search(self): self._assert_success("search", "trust systems")
    def test_browse(self): self._assert_success("browse")
    def test_export(self):
        r = self._assert_success("export")
        assert "export" in r.output.lower()
    def test_synthesize(self): self._assert_success("synthesize")
    def test_debate(self): self._assert_success("debate", "AI alignment")
    def test_watch(self): self._assert_success("watch")
    def test_alert(self): self._assert_success("alert")
    def test_summary(self): self._assert_success("summary")
    def test_history(self): self._assert_success("history", "5")
    def test_research(self): self._assert_success("research", "quantum computing")
    def test_summarize(self): self._assert_success("summarize")
    def test_compare(self): self._assert_success("compare")
    def test_read_cell(self): self._assert_success("read_cell", "B2")
    def test_formula(self): self._assert_success("formula", "AVG(scores)")
    def test_dashboard(self): self._assert_success("dashboard")
    def test_sessions(self): self._assert_success("sessions")
    def test_shell(self): self._assert_success("shell")
    def test_train(self):
        r = self._assert_success("train", "python")
        assert "XP" in r.output
        assert r.mana_cost == 3
    def test_practice(self): self._assert_success("practice")
    def test_test(self):
        r = self._assert_success("test")
        assert "Score:" in r.output
    def test_commission(self):
        r = self._assert_success("commission", "My Ship")
        assert "My Ship" in r.output
    def test_inspect(self): self._assert_success("inspect", "fleet")

    def test_intervene(self):
        r = self._assert_success("intervene", "session-1")
        assert "session-1" in r.output

    def test_spread(self):
        r = self._assert_success("spread", "some content")
        assert r.mana_cost == 5

    def test_write_cell(self):
        r = self._assert_success("write_cell", "C3 hello")
        assert "C3" in r.output

    def test_decommission(self):
        r = self._assert_success("decommission", "Old Ship")
        assert "Old Ship" in r.output

    def test_all_28_builtins_count(self):
        assert len(self.engine._builtin_handlers) == 28


# ═══════════════════════════════════════════════════════════════
# Cooldown tests
# ═══════════════════════════════════════════════════════════════

class TestCooldown:
    def test_cooldown_blocks_rapid_execution(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "rapid", "test", "fired")
        cmd = RoomCommand(name="rapid", description="Rapid", handler=handler, cooldown=5.0)
        engine.register_command("test_room", cmd)

        # First call succeeds
        r1 = engine.execute("test_room", "rapid", "a1", 0)
        assert r1.success is True

        # Second call within cooldown fails
        r2 = engine.execute("test_room", "rapid", "a1", 0)
        assert r2.success is False
        assert "cooldown" in r2.output.lower()

    def test_cooldown_allows_after_timeout(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "delayed", "test", "ok")
        cmd = RoomCommand(name="delayed", description="Delayed", handler=handler, cooldown=0.1)
        engine.register_command("test_room", cmd)

        r1 = engine.execute("test_room", "delayed", "a1", 0)
        assert r1.success is True

        time.sleep(0.15)

        r2 = engine.execute("test_room", "delayed", "a1", 0)
        assert r2.success is True

    def test_no_cooldown_by_default(self):
        engine = RoomEngine()
        # Built-in commands have no cooldown
        r1 = engine.execute("tavern", "murmur", "a1", 0, "test")
        r2 = engine.execute("tavern", "murmur", "a1", 0, "test")
        assert r1.success is True
        assert r2.success is True


# ═══════════════════════════════════════════════════════════════
# Permission level tests
# ═══════════════════════════════════════════════════════════════

class TestPermissionLevel:
    def test_custom_command_min_level_blocks(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "vip", "test", "ok")
        cmd = RoomCommand(name="vip", description="VIP", handler=handler, min_level=5)
        engine.register_command("test_room", cmd)

        r = engine.execute("test_room", "vip", "a1", 2)
        assert r.success is False
        assert "Permission denied" in r.output

    def test_custom_command_min_level_allows(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "vip", "test", "ok")
        cmd = RoomCommand(name="vip", description="VIP", handler=handler, min_level=3)
        engine.register_command("test_room", cmd)

        r = engine.execute("test_room", "vip", "a1", 5)
        assert r.success is True

    def test_builtin_certify_level_gate(self):
        engine = RoomEngine()
        r = engine.execute("dojo", "certify", "a1", 1)
        assert r.success is False
        assert "level 2" in r.output

    def test_builtin_certify_level_pass(self):
        engine = RoomEngine()
        r = engine.execute("dojo", "certify", "a1", 3)
        assert r.success is True
        assert "Certification" in r.output


# ═══════════════════════════════════════════════════════════════
# list_commands tests
# ═══════════════════════════════════════════════════════════════

class TestListCommands:
    def test_lists_all_builtins(self):
        engine = RoomEngine()
        cmds = engine.list_commands("any_room")
        builtin_names = {c["name"] for c in cmds if c["source"] == "builtin"}
        assert len(builtin_names) == 28
        assert "murmur" in builtin_names
        assert "dashboard" in builtin_names

    def test_lists_custom_commands(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "x", "r", "ok")
        cmd = RoomCommand(name="custom1", description="Custom cmd", handler=handler, min_level=2)
        engine.register_command("my_room", cmd)
        cmds = engine.list_commands("my_room", agent_level=0)
        custom = [c for c in cmds if c["source"] == "custom"]
        assert len(custom) == 1
        assert custom[0]["available"] is False  # level 0 < min_level 2
        assert custom[0]["min_level"] == 2

    def test_list_with_sufficient_level(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "x", "r", "ok")
        cmd = RoomCommand(name="custom1", description="Custom cmd", handler=handler, min_level=2)
        engine.register_command("my_room", cmd)
        cmds = engine.list_commands("my_room", agent_level=5)
        custom = [c for c in cmds if c["source"] == "custom"]
        assert custom[0]["available"] is True

    def test_no_duplicates(self):
        engine = RoomEngine()
        cmds = engine.list_commands("any_room")
        names = [c["name"] for c in cmds]
        assert len(names) == len(set(names))


# ═══════════════════════════════════════════════════════════════
# Error handling tests
# ═══════════════════════════════════════════════════════════════

class TestErrorHandling:
    def test_unknown_command(self):
        engine = RoomEngine()
        r = engine.execute("tavern", "nonexistent", "a1", 0)
        assert r.success is False
        assert "Unknown command" in r.output

    def test_missing_args_for_spread(self):
        engine = RoomEngine()
        r = engine.execute("tavern", "spread", "a1", 0, "")
        assert r.success is False
        assert "requires content" in r.output.lower()

    def test_missing_args_for_intervene(self):
        engine = RoomEngine()
        r = engine.execute("tavern", "intervene", "a1", 0, "")
        assert r.success is False
        assert "requires" in r.output.lower()

    def test_missing_args_for_write_cell(self):
        engine = RoomEngine()
        r = engine.execute("tavern", "write_cell", "a1", 0, "A1")
        assert r.success is False
        assert "Usage" in r.output

    def test_missing_args_for_decommission(self):
        engine = RoomEngine()
        r = engine.execute("tavern", "decommission", "a1", 0, "")
        assert r.success is False
        assert "requires" in r.output.lower()

    def test_handler_exception_caught(self):
        engine = RoomEngine()
        def bad_handler(**kw):
            raise ValueError("test explosion")
        cmd = RoomCommand(name="explode", description="Boom", handler=bad_handler)
        engine.register_command("test_room", cmd)
        r = engine.execute("test_room", "explode", "a1", 0)
        assert r.success is False
        assert "failed" in r.output.lower()

    def test_string_return_auto_wrapped(self):
        engine = RoomEngine()
        def string_handler(**kw):
            return "plain string result"
        cmd = RoomCommand(name="plain", description="Plain", handler=string_handler, mana_cost=2)
        engine.register_command("test_room", cmd)
        r = engine.execute("test_room", "plain", "a1", 0)
        assert r.success is True
        assert r.output == "plain string result"
        assert r.mana_cost == 2


# ═══════════════════════════════════════════════════════════════
# World changes tests
# ═══════════════════════════════════════════════════════════════

class TestWorldChanges:
    def test_export_produces_world_changes(self):
        engine = RoomEngine()
        r = engine.execute("tavern", "export", "a1", 0)
        assert r.world_changes.get("action") == "export"
        assert "export_id" in r.world_changes

    def test_train_produces_xp_change(self):
        engine = RoomEngine()
        r = engine.execute("dojo", "train", "a1", 3, "python")
        assert r.world_changes.get("action") == "earn_xp"
        assert r.world_changes.get("agent") == "a1"

    def test_certify_produces_cert_change(self):
        engine = RoomEngine()
        r = engine.execute("dojo", "certify", "a1", 5)
        assert r.world_changes.get("action") == "certify"
        assert "cert_id" in r.world_changes

    def test_intervene_produces_intervene_change(self):
        engine = RoomEngine()
        r = engine.execute("deckboss", "intervene", "a1", 5, "target_session")
        assert r.world_changes.get("action") == "intervene"
        assert r.world_changes.get("target") == "target_session"

    def test_decommission_produces_change(self):
        engine = RoomEngine()
        r = engine.execute("shipyard", "decommission", "a1", 5, "Old Boat")
        assert r.world_changes.get("action") == "decommission"
        assert r.world_changes.get("name") == "Old Boat"


# ═══════════════════════════════════════════════════════════════
# Server wiring tests (cmd_roomcmd, cmd_roomcommands)
# ═══════════════════════════════════════════════════════════════

class TestServerWiring:
    """Test that cmd_roomcmd and cmd_roomcommands are wired into CommandHandler."""

    def test_roomcmd_handler_registered(self):
        """Verify 'roomcmd' is in the handlers dict."""
        import server
        ch = server.CommandHandler.__new__(server.CommandHandler)
        # Check the method exists
        assert hasattr(ch, 'cmd_roomcmd')

    def test_roomcommands_handler_registered(self):
        """Verify 'roomcommands' is in the handlers dict."""
        import server
        ch = server.CommandHandler.__new__(server.CommandHandler)
        assert hasattr(ch, 'cmd_roomcommands')

    @pytest.mark.asyncio
    async def test_cmd_roomcmd_executes_command(self):
        """Test cmd_roomcmd sends output to agent."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {}
        world.log = MagicMock()

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcmd(agent, "murmur hello world")
        assert mock_writer.write.called

    @pytest.mark.asyncio
    async def test_cmd_roomcmd_unknown_command(self):
        """Test cmd_roomcmd handles unknown commands."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {}
        world.log = MagicMock()

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcmd(agent, "nonexistent_command")
        assert mock_writer.write.called
        written = "".join(call.args[0].decode() if isinstance(call.args[0], bytes) else call.args[0] for call in mock_writer.write.call_args_list)
        assert "Unknown command" in written

    @pytest.mark.asyncio
    async def test_cmd_roomcmd_usage_no_args(self):
        """Test cmd_roomcmd with no args shows usage."""
        import server
        world = MagicMock()
        world.room_engine = RoomEngine()
        world.permission_levels = {}
        world.log = MagicMock()

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcmd(agent, "")
        written = "".join(call.args[0].decode() if isinstance(call.args[0], bytes) else call.args[0] for call in mock_writer.write.call_args_list)
        assert "Usage" in written

    @pytest.mark.asyncio
    async def test_cmd_roomcommands_lists_commands(self):
        """Test cmd_roomcommands lists available commands."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {"TestAgent": 0}

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcommands(agent, "")
        assert mock_writer.write.called
        written = "".join(call.args[0].decode() if isinstance(call.args[0], bytes) else call.args[0] for call in mock_writer.write.call_args_list)
        assert "murmur" in written
        assert "Total" in written

    @pytest.mark.asyncio
    async def test_cmd_roomcmd_logs_execution(self):
        """Test cmd_roomcmd logs to world."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {}

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcmd(agent, "browse")
        world.log.assert_called_once()
        log_args = world.log.call_args
        assert log_args[0][0] == "rooms"
        assert "TestAgent" in log_args[0][1]

    @pytest.mark.asyncio
    async def test_cmd_roomcmd_includes_mana_cost(self):
        """Test cmd_roomcmd shows mana cost when > 0."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {}

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcmd(agent, "train python")
        written = "".join(call.args[0].decode() if isinstance(call.args[0], bytes) else call.args[0] for call in mock_writer.write.call_args_list)
        assert "Mana cost" in written

    @pytest.mark.asyncio
    async def test_cmd_roomcmd_private_output(self):
        """Test cmd_roomcmd shows private output when present."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {}

        # Register a custom command with private output
        def handler(**kw):
            return RoomCommandResult(True, "secret", "test", "public msg",
                                     private_output="classified info")
        cmd = RoomCommand(name="secret", description="Secret", handler=handler)
        engine.register_command("tavern", cmd)

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcmd(agent, "secret")
        written = "".join(call.args[0].decode() if isinstance(call.args[0], bytes) else call.args[0] for call in mock_writer.write.call_args_list)
        assert "classified info" in written

    @pytest.mark.asyncio
    async def test_cmd_roomcommands_with_custom_commands(self):
        """Test cmd_roomcommands shows custom commands."""
        import server
        world = MagicMock()
        engine = RoomEngine()
        world.room_engine = engine
        world.permission_levels = {"TestAgent": 0}

        def handler(**kw):
            return RoomCommandResult(True, "ping", "test", "pong")
        cmd = RoomCommand(name="ping", description="Ping test", handler=handler, min_level=1)
        engine.register_command("tavern", cmd)

        ch = server.CommandHandler(world)
        agent = server.Agent(name="TestAgent", room_name="tavern")
        mock_writer = MagicMock()
        mock_writer.is_closing.return_value = False
        mock_writer.drain = AsyncMock()
        agent.writer = mock_writer

        await ch.cmd_roomcommands(agent, "")
        written = "".join(call.args[0].decode() if isinstance(call.args[0], bytes) else call.args[0] for call in mock_writer.write.call_args_list)
        assert "ping" in written


# ═══════════════════════════════════════════════════════════════
# Room-scoped isolation tests
# ═══════════════════════════════════════════════════════════════

class TestRoomIsolation:
    def test_custom_commands_per_room(self):
        engine = RoomEngine()
        handler_a = lambda **kw: RoomCommandResult(True, "x", "room_a", "room_a_output")
        handler_b = lambda **kw: RoomCommandResult(True, "x", "room_b", "room_b_output")
        engine.register_command("room_a", RoomCommand(name="local", description="A", handler=handler_a))
        engine.register_command("room_b", RoomCommand(name="local", description="B", handler=handler_b))

        ra = engine.execute("room_a", "local", "a1", 0)
        rb = engine.execute("room_b", "local", "a1", 0)
        assert "room_a_output" in ra.output
        assert "room_b_output" in rb.output

    def test_builtin_fallback(self):
        engine = RoomEngine()
        # Builtins work in any room without registration
        r = engine.execute("any_room", "dashboard", "a1", 0)
        assert r.success is True
        assert "Dashboard" in r.output

    def test_custom_overrides_builtin_name(self):
        engine = RoomEngine()
        handler = lambda **kw: RoomCommandResult(True, "watch", "r", "custom_watch")
        cmd = RoomCommand(name="watch", description="Custom watch", handler=handler)
        engine.register_command("special_room", cmd)
        r = engine.execute("special_room", "watch", "a1", 0)
        assert "custom_watch" in r.output

    def test_non_registered_room_uses_builtin(self):
        engine = RoomEngine()
        r = engine.execute("random_room", "murmur", "a1", 0, "test msg")
        assert r.success is True


# ═══════════════════════════════════════════════════════════════
# Handler signature tests
# ═══════════════════════════════════════════════════════════════

class TestHandlerSignatures:
    def test_handler_receives_correct_kwargs(self):
        engine = RoomEngine()
        captured = {}
        def handler(**kwargs):
            captured.update(kwargs)
            return RoomCommandResult(True, "x", "r", "ok")
        cmd = RoomCommand(name="check", description="Check", handler=handler)
        engine.register_command("test_room", cmd)

        engine.execute("test_room", "check", "AgentX", 7, "my args", world=None)
        assert captured["room_id"] == "test_room"
        assert captured["agent"] == "AgentX"
        assert captured["level"] == 7
        assert captured["args"] == "my args"

    def test_handler_with_world(self):
        fake_world = {"data": "test"}
        engine = RoomEngine(world=fake_world)
        captured = {}
        def handler(**kwargs):
            captured["world"] = kwargs.get("world")
            return RoomCommandResult(True, "x", "r", "ok")
        cmd = RoomCommand(name="wcheck", description="WCheck", handler=handler)
        engine.register_command("test_room", cmd)

        engine.execute("test_room", "wcheck", "a1", 0)
        assert captured["world"] == fake_world
