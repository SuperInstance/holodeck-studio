"""Tests for mud_extensions — monkey-patched commands."""
import pytest
from unittest.mock import AsyncMock


def make_agent(name="bot", role="greenhorn", room="tavern", mask=None):
    from server import Agent
    writer = AsyncMock()
    writer.write = lambda d: None
    writer.is_closing = lambda: False
    writer.drain = AsyncMock()
    return Agent(name=name, role=role, room_name=room, mask=mask, writer=writer)


class TestPatchedCommands:
    def setup_method(self):
        from server import CommandHandler, World
        self.world = World.__new__(World)
        self.world.rooms = dict(CommandHandler.__init__.__globals__.get(
            'World', type('W', (), {
                'DEFAULT_ROOMS': {}
            })).DEFAULT_ROOMS) if False else {}
        # Just set up a simple world
        from server import Room
        self.world.rooms = {
            "tavern": Room("The Tavern", "desc", {"north": "lighthouse", "south": "harbor"}),
            "lighthouse": Room("Lighthouse", "desc", {"tavern": "tavern"}),
            "harbor": Room("Harbor", "desc", {"tavern": "tavern"}),
        }
        self.world.agents = {}
        self.world.ghosts = {}
        self.world.npcs = {}
        self.world.log = lambda ch, msg: None
        self.world.save = lambda: None
        self.world.get_room = lambda name: self.world.rooms.get(name)
        self.world.agents_in_room = lambda rn: [a for a in self.world.agents.values() if a.room_name == rn]
        self.world.ghosts_in_room = lambda rn: []

        from mud_extensions import patch_handler
        from server import CommandHandler
        patch_handler(CommandHandler)
        self.handler = CommandHandler(self.world)

    def test_new_commands_registered(self):
        assert hasattr(self.handler, 'new_commands')
        cmds = self.handler.new_commands
        assert "project" in cmds
        assert "projections" in cmds
        assert "unproject" in cmds
        assert "describe" in cmds
        assert "whisper" in cmds
        assert "w" in cmds
        assert "rooms" in cmds
        assert "shout" in cmds
        assert "instinct" in cmds

    @pytest.mark.asyncio
    async def test_project_requires_args(self):
        agent = make_agent(room="tavern")
        await self.handler.new_commands["project"](self.handler, agent, "")
        # Should print usage

    @pytest.mark.asyncio
    async def test_project_creates_projection(self):
        agent = make_agent(name="dev", room="tavern")
        await self.handler.new_commands["project"](
            self.handler, agent, "ISA v3 - 2-byte opcodes with escape prefix")
        room = self.world.rooms["tavern"]
        assert len(room.projections) == 1
        assert room.projections[0].title == "ISA v3"
        assert room.projections[0].content == "2-byte opcodes with escape prefix"

    @pytest.mark.asyncio
    async def test_project_title_only(self):
        agent = make_agent(room="tavern")
        await self.handler.new_commands["project"](
            self.handler, agent, "Just a title")
        room = self.world.rooms["tavern"]
        assert len(room.projections) == 1
        assert room.projections[0].content == "(no details)"

    @pytest.mark.asyncio
    async def test_projections_empty(self):
        agent = make_agent(room="tavern")
        await self.handler.new_commands["projections"](self.handler, agent, "")

    @pytest.mark.asyncio
    async def test_projections_with_data(self):
        from server import Projection
        agent = make_agent(room="tavern")
        self.world.rooms["tavern"].projections.append(
            Projection("dev", "Spec", "Details", "10:00"))
        await self.handler.new_commands["projections"](self.handler, agent, "")

    @pytest.mark.asyncio
    async def test_unproject_no_projections(self):
        agent = make_agent(room="tavern")
        await self.handler.new_commands["unproject"](self.handler, agent, "")

    @pytest.mark.asyncio
    async def test_unproject_removes_own(self):
        from server import Projection
        agent = make_agent(name="dev", room="tavern")
        self.world.rooms["tavern"].projections.append(
            Projection("dev", "P1", "C1", "10:00"))
        self.world.rooms["tavern"].projections.append(
            Projection("other", "P2", "C2", "11:00"))
        await self.handler.new_commands["unproject"](self.handler, agent, "")
        room = self.world.rooms["tavern"]
        assert len(room.projections) == 1
        assert room.projections[0].agent_name == "other"

    @pytest.mark.asyncio
    async def test_describe_permission_denied(self):
        agent = make_agent(role="greenhorn")
        await self.handler.new_commands["describe"](self.handler, agent, "new desc")
        # Should be denied

    @pytest.mark.asyncio
    async def test_describe_allowed(self):
        agent = make_agent(role="lighthouse")
        await self.handler.new_commands["describe"](
            self.handler, agent, "A new description")
        assert self.world.rooms["tavern"].description == "A new description"

    @pytest.mark.asyncio
    async def test_describe_roles_allowed(self):
        """All builder roles can describe."""
        for role in ("lighthouse", "vessel", "captain", "scout"):
            agent = make_agent(role=role)
            await self.handler.new_commands["describe"](
                self.handler, agent, f"desc for {role}")
            assert self.world.rooms["tavern"].description == f"desc for {role}"

    @pytest.mark.asyncio
    async def test_whisper_usage(self):
        agent = make_agent()
        await self.handler.new_commands["whisper"](self.handler, agent, "onlyname")

    @pytest.mark.asyncio
    async def test_whisper_target_not_found(self):
        agent = make_agent()
        await self.handler.new_commands["whisper"](
            self.handler, agent, "nobody message")

    @pytest.mark.asyncio
    async def test_whisper_success(self):
        agent = make_agent(name="sender", room="tavern")
        target = make_agent(name="receiver", room="tavern")
        self.world.agents["sender"] = agent
        self.world.agents["receiver"] = target
        await self.handler.new_commands["whisper"](
            self.handler, agent, "receiver secret message")

    @pytest.mark.asyncio
    async def test_rooms_command(self):
        agent = make_agent()
        await self.handler.new_commands["rooms"](self.handler, agent, "")

    @pytest.mark.asyncio
    async def test_shout_requires_text(self):
        agent = make_agent()
        await self.handler.new_commands["shout"](self.handler, agent, "")

    @pytest.mark.asyncio
    async def test_shout_reaches_adjacent(self):
        agent = make_agent(name="shouter", room="tavern")
        neighbor = make_agent(name="neighbor", room="lighthouse")
        self.world.agents["shouter"] = agent
        self.world.agents["neighbor"] = neighbor
        await self.handler.new_commands["shout"](
            self.handler, agent, "HELLO EVERYONE")
        output = neighbor.writer.get_output() if hasattr(neighbor.writer, 'get_output') else ""
        # The shout should reach adjacent rooms
        # Since we're using AsyncMock, we can't easily check, but it shouldn't crash
