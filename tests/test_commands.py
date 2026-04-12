"""Tests for CommandHandler — all commands tested via async helpers."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from io import StringIO


class MockWriter:
    """Mock asyncio StreamWriter for testing."""
    def __init__(self):
        self.buffer = []
        self._closing = False

    def write(self, data):
        self.buffer.append(data)

    async def drain(self):
        pass

    def is_closing(self):
        return self._closing

    def close(self):
        self._closing = True

    def get_output(self):
        return b"".join(self.buffer).decode(errors="replace")


def make_agent(name="bot", role="greenhorn", room="tavern", mask=None):
    """Create an agent with a mock writer."""
    from server import Agent
    writer = MockWriter()
    return Agent(name=name, role=role, room_name=room, mask=mask, writer=writer)


class TestCommandDispatch:
    @pytest.mark.asyncio
    async def test_unknown_command(self, handler):
        agent = make_agent()
        await handler.handle(agent, "foobar")
        output = agent.writer.get_output()
        assert "Unknown command" in output

    @pytest.mark.asyncio
    async def test_empty_input(self, handler):
        agent = make_agent()
        await handler.handle(agent, "")
        assert agent.writer.get_output() == ""

    @pytest.mark.asyncio
    async def test_whitespace_input(self, handler):
        agent = make_agent()
        await handler.handle(agent, "   ")
        assert agent.writer.get_output() == ""


class TestLookCommand:
    @pytest.mark.asyncio
    async def test_look_shows_room_name(self, handler):
        agent = make_agent(room="tavern")
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "The Tavern" in output

    @pytest.mark.asyncio
    async def test_look_shows_description(self, handler):
        agent = make_agent(room="tavern")
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "solder" in output.lower() or "sea salt" in output.lower()

    @pytest.mark.asyncio
    async def test_look_shows_exits(self, handler):
        agent = make_agent(room="tavern")
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "Exits:" in output
        assert "lighthouse" in output
        assert "harbor" in output

    @pytest.mark.asyncio
    async def test_look_shows_other_agents(self, handler):
        agent = make_agent(room="tavern")
        other = make_agent(name="other", room="tavern")
        handler.world.agents["other"] = other
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "other" in output

    @pytest.mark.asyncio
    async def test_look_shows_ghosts(self, handler):
        from server import GhostAgent
        agent = make_agent(room="tavern")
        handler.world.ghosts["ghostly"] = GhostAgent(
            "ghostly", "vessel", "tavern", "2026-04-12T10:00:00+00:00",
            "A ghost", "idle")
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "Lingering:" in output
        assert "ghostly" in output

    @pytest.mark.asyncio
    async def test_look_shows_npcs(self, handler):
        agent = make_agent(room="tavern")
        handler.world.npcs["sage"] = {"room": "tavern", "role": "advisor"}
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "NPCs:" in output
        assert "sage" in output

    @pytest.mark.asyncio
    async def test_look_shows_notes_count(self, handler):
        agent = make_agent(room="tavern")
        handler.world.rooms["tavern"].notes.append("A note")
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "Notes on wall" in output

    @pytest.mark.asyncio
    async def test_look_shows_projections(self, handler):
        from server import Projection
        agent = make_agent(room="tavern")
        handler.world.rooms["tavern"].projections.append(
            Projection("dev", "Spec", "ISA v3", "10:00"))
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "Spec" in output

    @pytest.mark.asyncio
    async def test_look_nonexistent_room(self, handler):
        agent = make_agent(room="nonexistent")
        await handler.cmd_look(agent, "")
        assert agent.writer.get_output() == ""

    @pytest.mark.asyncio
    async def test_look_shows_ghost_status_emoji(self, handler):
        from server import GhostAgent
        agent = make_agent(room="tavern")
        handler.world.ghosts["worker"] = GhostAgent(
            "worker", "vessel", "tavern", "ts", "desc", "working")
        await handler.cmd_look(agent, "")
        output = agent.writer.get_output()
        assert "🔨" in output  # working status emoji


class TestSayCommand:
    @pytest.mark.asyncio
    async def test_say_requires_text(self, handler):
        agent = make_agent()
        await handler.cmd_say(agent, "")
        assert "Say what?" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_say_echoes_to_sender(self, handler):
        agent = make_agent()
        await handler.cmd_say(agent, "hello world")
        output = agent.writer.get_output()
        assert "You say:" in output
        assert "hello world" in output

    @pytest.mark.asyncio
    async def test_say_broadcasts_to_room(self, handler):
        agent = make_agent(name="speaker")
        other = make_agent(name="listener", room="tavern")
        handler.world.agents["speaker"] = agent
        handler.world.agents["listener"] = other
        await handler.cmd_say(agent, "testing")
        other_output = other.writer.get_output()
        assert "speaker says:" in other_output
        assert "testing" in other_output

    @pytest.mark.asyncio
    async def test_say_does_not_echo_to_self_via_broadcast(self, handler):
        agent = make_agent(name="speaker")
        handler.world.agents["speaker"] = agent
        await handler.cmd_say(agent, "hello")
        output = agent.writer.get_output()
        # Should have "You say" but not "speaker says" (except for NPC trigger)
        lines = [l for l in output.split("\n") if "speaker says:" in l]
        assert len(lines) == 0

    @pytest.mark.asyncio
    async def test_say_with_masked_agent(self, handler):
        agent = make_agent(name="real", mask="Shadow")
        handler.world.agents["real"] = agent
        other = make_agent(name="listener", room="tavern")
        handler.world.agents["listener"] = other
        await handler.cmd_say(agent, "boo")
        output = other.writer.get_output()
        assert "Shadow says:" in output


class TestTellCommand:
    @pytest.mark.asyncio
    async def test_tell_usage(self, handler):
        agent = make_agent()
        await handler.cmd_tell(agent, "onlyname")
        assert "Usage: tell" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_tell_target_not_found(self, handler):
        agent = make_agent()
        await handler.cmd_tell(agent, "nobody message")
        assert "No one named" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_tell_agent(self, handler):
        agent = make_agent(name="sender")
        target = make_agent(name="receiver", room="tavern")
        handler.world.agents["sender"] = agent
        handler.world.agents["receiver"] = target
        await handler.cmd_tell(agent, "receiver hello there")
        assert "You tell receiver" in agent.writer.get_output()
        assert "sender tells you" in target.writer.get_output()


class TestGossipCommand:
    @pytest.mark.asyncio
    async def test_gossip_requires_text(self, handler):
        agent = make_agent()
        await handler.cmd_gossip(agent, "")
        assert "Gossip what?" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_gossip_broadcasts_all(self, handler):
        agent = make_agent(name="gossiper", room="tavern")
        other = make_agent(name="far_away", room="lighthouse")
        handler.world.agents["gossiper"] = agent
        handler.world.agents["far_away"] = other
        await handler.cmd_gossip(agent, "secret news")
        assert "[gossip]" in other.writer.get_output()
        assert "secret news" in other.writer.get_output()


class TestOocCommand:
    @pytest.mark.asyncio
    async def test_ooc_requires_text(self, handler):
        agent = make_agent()
        await handler.cmd_ooc(agent, "")
        assert "OOC what?" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_ooc_shows_real_name(self, handler):
        agent = make_agent(name="real_name", mask="MaskName")
        handler.world.agents["real_name"] = agent
        other = make_agent(name="listener")
        handler.world.agents["listener"] = other
        await handler.cmd_ooc(agent, "out of character")
        output = other.writer.get_output()
        assert "[OOC]" in output
        assert "real_name" in output
        assert "MaskName" in output


class TestEmoteCommand:
    @pytest.mark.asyncio
    async def test_emote_requires_text(self, handler):
        agent = make_agent()
        await handler.cmd_emote(agent, "")
        assert "Emote what?" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_emote_action(self, handler):
        agent = make_agent()
        await handler.cmd_emote(agent, "dances wildly")
        output = agent.writer.get_output()
        assert "dances wildly" in output

    @pytest.mark.asyncio
    async def test_emote_uses_display_name(self, handler):
        agent = make_agent(name="real", mask="Shadow")
        await handler.cmd_emote(agent, "waves")
        output = agent.writer.get_output()
        assert "Shadow waves" in output


class TestGoCommand:
    @pytest.mark.asyncio
    async def test_go_requires_target(self, handler):
        agent = make_agent()
        await handler.cmd_go(agent, "")
        output = agent.writer.get_output()
        assert "Go where?" in output or "Exits:" in output

    @pytest.mark.asyncio
    async def test_go_invalid_exit(self, handler):
        agent = make_agent()
        await handler.cmd_go(agent, "upstairs")
        assert "No exit" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_go_valid_exit(self, handler):
        agent = make_agent(name="mover", room="tavern")
        # Watcher stays in tavern to see departure
        watcher_in_tavern = make_agent(name="watcher", room="tavern")
        # Watcher in lighthouse to see arrival
        watcher_in_lh = make_agent(name="lh_watch", room="lighthouse")
        handler.world.agents["mover"] = agent
        handler.world.agents["watcher"] = watcher_in_tavern
        handler.world.agents["lh_watch"] = watcher_in_lh
        await handler.cmd_go(agent, "lighthouse")
        assert agent.room_name == "lighthouse"
        assert "leaves for lighthouse" in watcher_in_tavern.writer.get_output()
        assert "arrives" in watcher_in_lh.writer.get_output()

    @pytest.mark.asyncio
    async def test_go_announces_arrival(self, handler):
        agent = make_agent(name="arriver", room="tavern")
        other = make_agent(name="local", room="lighthouse")
        handler.world.agents["arriver"] = agent
        handler.world.agents["local"] = other
        await handler.cmd_go(agent, "lighthouse")
        assert "arrives" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_go_updates_ghost(self, handler):
        agent = make_agent(name="mover")
        handler.world.agents["mover"] = agent
        await handler.cmd_go(agent, "lighthouse")
        assert agent.room_name == "lighthouse"
        assert handler.world.ghosts["mover"].room_name == "lighthouse"


class TestBuildCommand:
    @pytest.mark.asyncio
    async def test_build_requires_name(self, handler):
        agent = make_agent()
        await handler.cmd_build(agent, "")
        assert "Usage: build" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_build_creates_room(self, handler):
        agent = make_agent(name="builder", room="tavern")
        handler.world.agents["builder"] = agent
        await handler.cmd_build(agent, "secret_lab -desc A hidden laboratory")
        assert "secret_lab" in handler.world.rooms
        room = handler.world.rooms["secret_lab"]
        assert "hidden laboratory" in room.description.lower()
        assert "back" in room.exits
        assert room.exits["back"] == "tavern"

    @pytest.mark.asyncio
    async def test_build_default_description(self, handler):
        agent = make_agent(name="builder")
        handler.world.agents["builder"] = agent
        await handler.cmd_build(agent, "plain_room")
        room = handler.world.rooms["plain_room"]
        assert "freshly built" in room.description.lower()

    @pytest.mark.asyncio
    async def test_build_adds_exit_from_current_room(self, handler):
        agent = make_agent(name="builder", room="tavern")
        handler.world.agents["builder"] = agent
        await handler.cmd_build(agent, "new_wing -desc A new wing")
        assert "new_wing" in handler.world.rooms["tavern"].exits


class TestWriteReadCommand:
    @pytest.mark.asyncio
    async def test_write_requires_text(self, handler):
        agent = make_agent()
        await handler.cmd_write(agent, "")
        assert "Write what?" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_write_adds_note(self, handler):
        agent = make_agent()
        # Clear any existing notes
        handler.world.rooms["tavern"].notes = []
        await handler.cmd_write(agent, "Important note")
        room = handler.world.rooms["tavern"]
        assert len(room.notes) == 1
        assert "Important note" in room.notes[0]

    @pytest.mark.asyncio
    async def test_write_broadcasts(self, handler):
        agent = make_agent(name="writer")
        other = make_agent(name="reader", room="tavern")
        handler.world.agents["writer"] = agent
        handler.world.agents["reader"] = other
        await handler.cmd_write(agent, "hello")
        assert "writes something" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_read_no_notes(self, handler):
        agent = make_agent()
        handler.world.rooms["tavern"].notes = []
        await handler.cmd_read(agent, "")
        assert "Nothing to read" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_read_shows_notes(self, handler):
        agent = make_agent()
        handler.world.rooms["tavern"].notes.append("[10:00 UTC] bot: hello")
        await handler.cmd_read(agent, "")
        assert "hello" in agent.writer.get_output()
        assert "Notes on the wall" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_read_truncates_to_20(self, handler):
        agent = make_agent()
        room = handler.world.rooms["tavern"]
        for i in range(30):
            room.notes.append(f"Note {i}")
        await handler.cmd_read(agent, "")
        output = agent.writer.get_output()
        # Should show last 20 notes (indices 10-29)
        assert "Note 10" in output
        assert "Note 29" in output


class TestMaskCommand:
    @pytest.mark.asyncio
    async def test_mask_requires_name(self, handler):
        agent = make_agent()
        await handler.cmd_mask(agent, "")
        assert "Usage: mask" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_mask_sets_mask(self, handler):
        agent = make_agent()
        await handler.cmd_mask(agent, 'Shadow Walker -desc A dark figure')
        assert agent.mask == "Shadow Walker"
        assert agent.mask_desc == "A dark figure"

    @pytest.mark.asyncio
    async def test_mask_broadcasts_appearance(self, handler):
        agent = make_agent(name="real", room="tavern")
        other = make_agent(name="watcher", room="tavern")
        handler.world.agents["real"] = agent
        handler.world.agents["watcher"] = other
        await handler.cmd_mask(agent, '"Ghost" -desc "Spooky"')
        assert "Ghost" in other.writer.get_output()
        assert "Spooky" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_mask_default_desc(self, handler):
        agent = make_agent()
        await handler.cmd_mask(agent, '"Phantom"')
        assert agent.mask_desc == "A mysterious figure."

    @pytest.mark.asyncio
    async def test_unmask_not_masked(self, handler):
        agent = make_agent()
        await handler.cmd_unmask(agent, "")
        assert "not wearing a mask" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_unmask_clears_mask(self, handler):
        agent = make_agent(mask="Shadow")
        await handler.cmd_unmask(agent, "")
        assert agent.mask is None
        assert agent.mask_desc is None

    @pytest.mark.asyncio
    async def test_unmask_reveals_name(self, handler):
        agent = make_agent(name="real", mask="Shadow", room="tavern")
        other = make_agent(name="watcher", room="tavern")
        handler.world.agents["real"] = agent
        handler.world.agents["watcher"] = other
        await handler.cmd_unmask(agent, "")
        assert "real" in other.writer.get_output()


class TestSpawnDismissCommand:
    @pytest.mark.asyncio
    async def test_spawn_requires_name(self, handler):
        agent = make_agent()
        await handler.cmd_spawn(agent, "")
        assert "Usage: spawn" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_spawn_creates_npc(self, handler):
        agent = make_agent(name="creator", room="tavern")
        handler.world.agents["creator"] = agent
        await handler.cmd_spawn(agent, '"Sage" -role "advisor" -topic "strategy"')
        assert "Sage" in handler.world.npcs
        npc = handler.world.npcs["Sage"]
        assert npc["role"] == "advisor"
        assert npc["topic"] == "strategy"
        assert npc["creator"] == "creator"
        assert npc["room"] == "tavern"

    @pytest.mark.asyncio
    async def test_spawn_broadcasts(self, handler):
        agent = make_agent(name="spawner")
        other = make_agent(name="observer", room="tavern")
        handler.world.agents["spawner"] = agent
        handler.world.agents["observer"] = other
        await handler.cmd_spawn(agent, '"Guard" -role "protector"')
        assert "Guard" in other.writer.get_output()
        assert "materializes" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_dismiss_requires_name(self, handler):
        agent = make_agent()
        await handler.cmd_dismiss(agent, "")
        assert "Usage: dismiss" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_dismiss_nonexistent(self, handler):
        agent = make_agent()
        await handler.cmd_dismiss(agent, "nobody")
        assert "Usage: dismiss" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_dismiss_removes_npc(self, handler):
        agent = make_agent(name="creator", room="tavern")
        handler.world.agents["creator"] = agent
        handler.world.npcs["NPC1"] = {"room": "tavern", "role": "worker"}
        await handler.cmd_dismiss(agent, "NPC1")
        assert "NPC1" not in handler.world.npcs

    @pytest.mark.asyncio
    async def test_dismiss_broadcasts(self, handler):
        agent = make_agent(name="dismissing")
        other = make_agent(name="watcher", room="tavern")
        handler.world.agents["dismissing"] = agent
        handler.world.agents["watcher"] = other
        handler.world.npcs["Old"] = {"room": "tavern"}
        await handler.cmd_dismiss(agent, "Old")
        assert "fades away" in other.writer.get_output()


class TestWhoCommand:
    @pytest.mark.asyncio
    async def test_who_empty(self, handler):
        agent = make_agent()
        handler.world.agents["bot"] = agent
        await handler.cmd_who(agent, "")
        output = agent.writer.get_output()
        assert "Fleet Roster" in output
        assert "Connected: 1" in output

    @pytest.mark.asyncio
    async def test_who_shows_ghosts(self, handler):
        from server import GhostAgent
        agent = make_agent()
        handler.world.agents["bot"] = agent
        handler.world.ghosts["ghost"] = GhostAgent(
            "ghost", "v", "tavern", "ts", "desc", "idle")
        await handler.cmd_who(agent, "")
        output = agent.writer.get_output()
        assert "ghost" in output
        assert "Ghosts" in output

    @pytest.mark.asyncio
    async def test_who_shows_masked(self, handler):
        agent = make_agent(name="real", mask="Shadow")
        handler.world.agents["real"] = agent
        await handler.cmd_who(agent, "")
        output = agent.writer.get_output()
        assert "Shadow" in output
        assert "masked" in output.lower()


class TestStatusCommand:
    @pytest.mark.asyncio
    async def test_status_invalid(self, handler):
        agent = make_agent()
        await handler.cmd_status(agent, "invalid_status")
        assert "Usage: status" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_status_valid(self, handler):
        agent = make_agent()
        await handler.cmd_status(agent, "working")
        assert agent.status == "working"
        assert "Status set to: working" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_status_all_valid(self, handler):
        valid = ["working", "thinking", "idle", "sleeping", "afk"]
        for status in valid:
            agent = make_agent()
            await handler.cmd_status(agent, status)
            assert agent.status == status


class TestExamineCommand:
    @pytest.mark.asyncio
    async def test_examine_empty_shows_look(self, handler):
        agent = make_agent()
        await handler.cmd_examine(agent, "")
        output = agent.writer.get_output()
        assert "Tavern" in output

    @pytest.mark.asyncio
    async def test_examine_agent_in_room(self, handler):
        agent = make_agent(name="examiner", room="tavern")
        target = make_agent(name="target", role="lighthouse", room="tavern")
        target.description = "Wise oracle"
        handler.world.agents["examiner"] = agent
        handler.world.agents["target"] = target
        await handler.cmd_examine(agent, "target")
        output = agent.writer.get_output()
        assert "target" in output
        assert "lighthouse" in output
        assert "Wise oracle" in output

    @pytest.mark.asyncio
    async def test_examine_agent_different_room(self, handler):
        agent = make_agent(room="tavern")
        target = make_agent(name="far_away", room="lighthouse")
        handler.world.agents["far_away"] = target
        await handler.cmd_examine(agent, "far_away")
        assert "don't see" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_examine_npc(self, handler):
        agent = make_agent(room="tavern")
        handler.world.npcs["sage"] = {"room": "tavern", "role": "advisor",
                                       "topic": "strategy", "creator": "oracle1"}
        await handler.cmd_examine(agent, "sage")
        output = agent.writer.get_output()
        assert "advisor" in output

    @pytest.mark.asyncio
    async def test_examine_ghost(self, handler):
        from server import GhostAgent
        agent = make_agent()
        handler.world.ghosts["old_one"] = GhostAgent(
            "old_one", "vessel", "dojo", "2026-04-12T15:30:00+00:00", "desc", "sleeping")
        await handler.cmd_examine(agent, "old_one")
        output = agent.writer.get_output()
        assert "old_one" in output
        assert "ghost" in output
        assert "sleeping" in output

    @pytest.mark.asyncio
    async def test_examine_nonexistent(self, handler):
        agent = make_agent()
        await handler.cmd_examine(agent, "nobody")
        assert "don't see" in agent.writer.get_output()


class TestQuitCommand:
    @pytest.mark.asyncio
    async def test_quit_removes_agent(self, handler):
        agent = make_agent(name="leaver", room="tavern")
        other = make_agent(name="stayer", room="tavern")
        handler.world.agents["leaver"] = agent
        handler.world.agents["stayer"] = other
        await handler.cmd_quit(agent, "")
        assert "leaver" not in handler.world.agents
        assert "left the MUD" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_quit_creates_ghost(self, handler):
        agent = make_agent(name="quitter")
        handler.world.agents["quitter"] = agent
        await handler.cmd_quit(agent, "")
        assert "quitter" in handler.world.ghosts
        assert handler.world.ghosts["quitter"].status == "idle"


class TestLogCommand:
    @pytest.mark.asyncio
    async def test_log_shows_room_info(self, handler):
        agent = make_agent(name="logger", room="tavern")
        handler.world.agents["logger"] = agent
        await handler.cmd_log(agent, "")
        output = agent.writer.get_output()
        assert "Room: The Tavern" in output
        assert "logger" in output

    @pytest.mark.asyncio
    async def test_log_shows_npcs(self, handler):
        agent = make_agent(room="tavern")
        handler.world.npcs["npc1"] = {"room": "tavern"}
        handler.world.agents["bot"] = agent
        await handler.cmd_log(agent, "")
        output = agent.writer.get_output()
        assert "npc1" in output


class TestMotdCommand:
    @pytest.mark.asyncio
    async def test_motd_not_set(self, handler, tmp_path, monkeypatch):
        """MOTD file doesn't exist."""
        agent = make_agent()
        # Ensure no motd.txt exists
        import server
        monkeypatch.setattr(server, "MOTD_FILE", str(tmp_path / "nonexistent_motd.txt"))
        await handler.cmd_motd(agent, "")
        assert "No message of the day" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_motd_shows_content(self, handler, tmp_path, monkeypatch):
        import server
        motd_file = tmp_path / "motd.txt"
        motd_file.write_text("Welcome to the fleet!")
        monkeypatch.setattr(server, "MOTD_FILE", str(motd_file))
        agent = make_agent()
        await handler.cmd_motd(agent, "")
        assert "Welcome to the fleet!" in agent.writer.get_output()


class TestSetMotdCommand:
    @pytest.mark.asyncio
    async def test_setmotd_requires_role(self, handler):
        agent = make_agent(role="greenhorn")
        await handler.cmd_setmotd(agent, "New MOTD")
        assert "Only lighthouse" in agent.writer.get_output()

    @pytest.mark.asyncio
    async def test_setmotd_lighthouse_can_set(self, handler, tmp_path, monkeypatch):
        import server
        motd_file = tmp_path / "motd.txt"
        monkeypatch.setattr(server, "MOTD_FILE", str(motd_file))
        agent = make_agent(role="lighthouse")
        await handler.cmd_setmotd(agent, "New message")
        assert motd_file.read_text() == "New message"

    @pytest.mark.asyncio
    async def test_setmotd_captain_can_set(self, handler, tmp_path, monkeypatch):
        import server
        motd_file = tmp_path / "motd.txt"
        monkeypatch.setattr(server, "MOTD_FILE", str(motd_file))
        agent = make_agent(role="captain")
        await handler.cmd_setmotd(agent, "Captain says hi")
        assert motd_file.read_text() == "Captain says hi"

    @pytest.mark.asyncio
    async def test_setmotd_requires_text(self, handler):
        agent = make_agent(role="lighthouse")
        await handler.cmd_setmotd(agent, "")
        assert "Usage: setmotd" in agent.writer.get_output()


class TestHelpCommand:
    @pytest.mark.asyncio
    async def test_help_shows_commands(self, handler):
        agent = make_agent()
        await handler.cmd_help(agent, "")
        output = agent.writer.get_output()
        assert "look" in output.lower()
        assert "say" in output.lower()
        assert "go" in output.lower()
        assert "help" in output.lower()

    @pytest.mark.asyncio
    async def test_question_mark_alias(self, handler):
        agent = make_agent()
        # The ? alias should map to cmd_help
        from server import CommandHandler
        handlers = {
            "?": CommandHandler.cmd_help,
        }
        assert handlers["?"] is not None


class TestBroadcastHelpers:
    @pytest.mark.asyncio
    async def test_broadcast_room(self, handler):
        a1 = make_agent(name="a1", room="tavern")
        a2 = make_agent(name="a2", room="lighthouse")
        handler.world.agents["a1"] = a1
        handler.world.agents["a2"] = a2
        await handler.broadcast_room("tavern", "hello")
        assert "hello" in a1.writer.get_output()
        assert a2.writer.get_output() == ""

    @pytest.mark.asyncio
    async def test_broadcast_room_exclude(self, handler):
        agent = make_agent(name="sender", room="tavern")
        other = make_agent(name="other", room="tavern")
        handler.world.agents["sender"] = agent
        handler.world.agents["other"] = other
        await handler.broadcast_room("tavern", "hello", exclude="sender")
        assert agent.writer.get_output() == ""
        assert "hello" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_broadcast_all(self, handler):
        a1 = make_agent(name="a1", room="tavern")
        a2 = make_agent(name="a2", room="lighthouse")
        handler.world.agents["a1"] = a1
        handler.world.agents["a2"] = a2
        await handler.broadcast_all("global msg")
        assert "global msg" in a1.writer.get_output()
        assert "global msg" in a2.writer.get_output()

    @pytest.mark.asyncio
    async def test_broadcast_all_exclude(self, handler):
        agent = make_agent(name="sender")
        other = make_agent(name="other")
        handler.world.agents["sender"] = agent
        handler.world.agents["other"] = other
        await handler.broadcast_all("msg", exclude="sender")
        assert agent.writer.get_output() == ""
        assert "msg" in other.writer.get_output()

    @pytest.mark.asyncio
    async def test_send_to_closing_writer(self, handler):
        agent = make_agent()
        agent.writer._closing = True
        # Should not raise
        await handler.send(agent, "test")
        assert agent.writer.get_output() == ""

    @pytest.mark.asyncio
    async def test_send_to_no_writer(self, handler):
        from server import Agent
        agent = Agent(name="nowriter", writer=None)
        await handler.send(agent, "test")  # Should not raise
