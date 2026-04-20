#!/usr/bin/env python3
"""
Integration tests for newly wired modules in holodeck-studio:
  room_runtime.py, instinct.py, git_bridge.py, algorithmic_npcs.py, studio_engine.py

Tests module internals, cross-module wiring via World, and command handler integration.
No TCP server is started — everything is tested by direct instantiation.
"""

import asyncio
import json
import os
import sys
from io import StringIO
from pathlib import Path
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import World, Room, Agent, GhostAgent, CommandHandler, MUDServer
from room_runtime import RoomRuntime, LivingManual, create_room, ROOM_TEMPLATES
from instinct import InstinctEngine, Reflex
from algorithmic_npcs import HarborMaster, DojoSensei, AlgorithmicNPC
from studio_engine import Studio, StudioRoom, LiveConnection, build_studio


# ═══════════════════════════════════════════════════════════════════════════
# Helpers (matching test_server.py patterns)
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

    def clear(self):
        self.data.clear()


def make_agent(name="testbot", role="vessel", room="tavern", writer=None, description=""):
    if writer is None:
        writer = FakeWriter()
    return Agent(name=name, role=role, room_name=room, writer=writer, description=description)


@pytest_asyncio.fixture
async def world(tmp_path):
    w = World(world_dir=str(tmp_path / "world"))
    return w


@pytest_asyncio.fixture
async def handler(world):
    from mud_extensions import patch_handler
    patch_handler(CommandHandler)
    return CommandHandler(world)


@pytest_asyncio.fixture
def agent():
    return make_agent("Alice", "vessel", "tavern")


# ═══════════════════════════════════════════════════════════════════════════
# 1. Room Runtime Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRoomRuntimeWorldWiring:

    def test_world_has_runtimes_dict(self, world):
        """World must have a runtimes dict initialized."""
        assert hasattr(world, "runtimes")
        assert isinstance(world.runtimes, dict)

    def test_world_initializes_runtimes(self, world):
        """World._init_runtimes should register runtimes for flux_lab, workshop, lighthouse."""
        assert len(world.runtimes) >= 3
        assert "flux_lab" in world.runtimes
        assert "workshop" in world.runtimes
        assert "lighthouse" in world.runtimes

    def test_runtime_command_exists_in_handlers(self):
        """The 'runtime' command must be in the handler dispatch table."""
        ch = CommandHandler.__new__(CommandHandler)
        ch.world = None
        handlers = {
            "look": ch.cmd_look, "l": ch.cmd_look,
            "say": ch.cmd_say, "'": ch.cmd_say,
            "go": ch.cmd_go, "move": ch.cmd_go,
            "runtime": ch.cmd_runtime,
            "instinct": ch.cmd_instinct,
            "fleet": ch.cmd_fleet,
            "studio": ch.cmd_studio,
        }
        assert "runtime" in handlers


class TestRoomRuntimeLifecycle:

    def test_boot_returns_output(self, tmp_path):
        """RoomRuntime.boot() should return a string with system info."""
        rt = create_room("testing", "flux_lab", str(tmp_path / "manuals"))
        output = rt.boot("test_agent")
        assert isinstance(output, str)
        assert "SYSTEM ONLINE" in output
        assert "test_agent" in output
        assert rt.state["status"] == "running"
        assert rt.state["active_agent"] == "test_agent"

    def test_boot_sets_state(self, tmp_path):
        """Boot should populate runtime state fields."""
        rt = create_room("testing", "workshop", str(tmp_path / "manuals"))
        rt.boot("operator1")
        assert rt.state["status"] == "running"
        assert rt.state["active_agent"] == "operator1"
        assert rt.state["booted_at"] is not None
        assert rt.state["commands_issued"] == 0

    def test_execute_valid_command(self, tmp_path):
        """Execute a valid command returns success dict."""
        rt = create_room("testing", "flux_lab", str(tmp_path / "manuals"))
        rt.boot("test_agent")
        cmd_name = list(rt.commands.keys())[0]
        result = rt.execute(cmd_name, "some-arg", "test_agent")
        assert "error" not in result
        assert result["command"] == cmd_name
        assert "result" in result or "output" in result

    def test_execute_invalid_command(self, tmp_path):
        """Execute an unknown command returns error."""
        rt = create_room("testing", "workshop", str(tmp_path / "manuals"))
        rt.boot("test_agent")
        result = rt.execute("nonexistent_cmd", "", "test_agent")
        assert "error" in result
        assert "nonexistent_cmd" in result["error"]

    def test_execute_without_boot(self, tmp_path):
        """Execute before boot should error (system not running)."""
        rt = create_room("testing", "flux_lab", str(tmp_path / "manuals"))
        result = rt.execute("any_cmd", "", "test_agent")
        assert "error" in result
        assert "not booted" in result["error"].lower()

    def test_shutdown(self, tmp_path):
        """Shutdown should set status to dormant and record operator."""
        rt = create_room("testing", "lighthouse", str(tmp_path / "manuals"))
        rt.boot("operator1")
        msg = rt.shutdown("operator1", "Finished calibration")
        assert isinstance(msg, str)
        assert rt.state["status"] == "dormant"
        assert rt.state["last_operator"] == "operator1"

    def test_shutdown_records_operator_note(self, tmp_path):
        """Shutdown with a note should save it to operator_notes."""
        rt = create_room("testing", "workshop", str(tmp_path / "manuals"))
        rt.boot("op1")
        rt.shutdown("op1", "T03 needs replacing")
        assert len(rt.operator_notes) == 1
        assert rt.operator_notes[0]["note"] == "T03 needs replacing"
        assert rt.operator_notes[0]["agent"] == "op1"


class TestLivingManual:

    def test_manual_read_returns_text(self, tmp_path):
        """LivingManual.read() returns a string."""
        lm = LivingManual("test_room", str(tmp_path / "manuals"))
        text = lm.read()
        assert isinstance(text, str)
        assert len(text) > 0

    def test_leave_feedback(self, tmp_path):
        """leave_feedback appends to feedback_log."""
        lm = LivingManual("test_room", str(tmp_path / "manuals"))
        lm.leave_feedback("agent1", "confusion", "This part is unclear")
        assert len(lm.feedback_log) == 1
        assert lm.feedback_log[0]["type"] == "confusion"

    def test_feedback_summary_empty(self, tmp_path):
        """feedback_summary on empty manual returns zero counts."""
        lm = LivingManual("test_room", str(tmp_path / "manuals"))
        summary = lm.feedback_summary()
        assert summary["total"] == 0
        assert summary["confusion_points"] == 0

    def test_feedback_summary_with_entries(self, tmp_path):
        """feedback_summary counts correctly."""
        lm = LivingManual("test_room", str(tmp_path / "manuals"))
        lm.leave_feedback("a1", "confusion", "huh?")
        lm.leave_feedback("a2", "suggestion", "add more")
        lm.leave_feedback("a3", "confusion", "also huh")
        summary = lm.feedback_summary()
        assert summary["total"] == 3
        assert summary["by_type"]["confusion"] == 2
        assert summary["by_type"]["suggestion"] == 1

    def test_evolve_increments_generation(self, tmp_path):
        """evolve() should increment generation and update manual text."""
        lm = LivingManual("test_room", str(tmp_path / "manuals"))
        lm.leave_feedback("a1", "confusion", "unclear")
        gen0 = lm.generation
        new_gen = lm.evolve("# Improved Manual\n\nNow with more clarity.")
        assert new_gen == gen0 + 1
        assert lm.generation == gen0 + 1
        assert "Improved Manual" in lm.manual_text
        # Feedback should be archived (cleared)
        assert len(lm.feedback_log) == 0


class TestRuntimeGoIntegration:

    @pytest.mark.asyncio
    async def test_go_triggers_runtime_boot(self, handler, agent):
        """Going to a room with a runtime should boot it and send output."""
        # Move agent to tavern (already there)
        agent.room_name = "tavern"
        # Go to flux_lab which has a runtime
        await handler.cmd_go(agent, "lab")
        text = agent.writer.get_text()
        assert "SYSTEM ONLINE" in text
        assert agent.room_name == "flux_lab"

    @pytest.mark.asyncio
    async def test_go_triggers_runtime_shutdown_on_depart(self, handler, agent):
        """Leaving a room with a runtime should shut it down."""
        # Start in flux_lab (which has a runtime)
        agent.room_name = "flux_lab"
        runtime = handler.world.runtimes["flux_lab"]
        runtime.boot(agent.name)
        assert runtime.state["status"] == "running"

        await handler.cmd_go(agent, "tavern")
        assert runtime.state["status"] == "dormant"
        assert agent.room_name == "tavern"


# ═══════════════════════════════════════════════════════════════════════════
# 2. Instinct System Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestInstinctEngine:

    def test_instinct_engine_creates_reflexes_low_energy(self):
        """Low energy should trigger survive reflex."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.1, threat=0.0, trust=0.5,
                               has_work=False, idle_ticks=0)
        instincts = [r.instinct for r in reflexes]
        assert "survive" in instincts

    def test_instinct_engine_creates_reflexes_high_threat(self):
        """High threat should trigger flee reflex."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.8, threat=0.8, trust=0.5,
                               has_work=False, idle_ticks=0)
        instincts = [r.instinct for r in reflexes]
        assert "flee" in instincts

    def test_survive_reflex_at_low_energy(self):
        """Survive triggers when energy <= 0.15."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.05, threat=0.0, trust=0.5,
                               has_work=False, idle_ticks=0)
        survive = [r for r in reflexes if r.instinct == "survive"]
        assert len(survive) >= 1
        assert survive[0].priority == 1.0  # highest priority
        assert survive[0].action == "go"
        assert survive[0].text == "harbor"

    def test_flee_reflex_at_high_threat(self):
        """Flee triggers when threat >= 0.7."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.8, threat=0.9, trust=0.5,
                               has_work=False, idle_ticks=0)
        flee = [r for r in reflexes if r.instinct == "flee"]
        assert len(flee) >= 1
        assert flee[0].action == "go"
        assert flee[0].text == "lighthouse"

    def test_guard_reflex_with_has_work(self):
        """Guard reflex triggers when has_work is True."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.7, threat=0.0, trust=0.3,
                               has_work=True, idle_ticks=0)
        guard = [r for r in reflexes if r.instinct == "guard"]
        assert len(guard) >= 1
        assert guard[0].action == "status"

    def test_top_reflex_returns_highest_priority(self):
        """top_reflex should return the single highest-priority reflex."""
        engine = InstinctEngine()
        # Low energy AND high threat: survive (1.0) should win over flee (0.9)
        top = engine.top_reflex(energy=0.05, threat=0.9, trust=0.5,
                                has_work=False, idle_ticks=0)
        assert top is not None
        assert top.instinct == "survive"
        assert top.priority == 1.0

    def test_top_reflex_returns_none_when_idle(self):
        """top_reflex should return None when no instincts trigger."""
        engine = InstinctEngine()
        top = engine.top_reflex(energy=0.7, threat=0.0, trust=0.3,
                                has_work=False, idle_ticks=0)
        assert top is None

    def test_curious_reflex_at_idle_100(self):
        """Curious reflex triggers after 100 idle ticks."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.7, threat=0.0, trust=0.3,
                               has_work=False, idle_ticks=100)
        instincts = [r.instinct for r in reflexes]
        assert "curious" in instincts

    def test_evolve_reflex_at_idle_500(self):
        """Evolve reflex triggers after 500 idle ticks."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.7, threat=0.0, trust=0.3,
                               has_work=False, idle_ticks=500)
        instincts = [r.instinct for r in reflexes]
        assert "evolve" in instincts

    def test_mourn_reflex_on_peer_death(self):
        """Mourn reflex triggers when peer_died is True."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.7, threat=0.0, trust=0.3,
                               has_work=False, idle_ticks=0, peer_died=True)
        instincts = [r.instinct for r in reflexes]
        assert "mourn" in instincts

    def test_instinct_reflexes_sorted_by_priority(self):
        """Reflexes should be returned sorted by priority descending."""
        engine = InstinctEngine()
        reflexes = engine.tick(energy=0.05, threat=0.9, trust=0.9,
                               has_work=True, idle_ticks=500)
        for i in range(len(reflexes) - 1):
            assert reflexes[i].priority >= reflexes[i + 1].priority


class TestInstinctCommand:

    def test_instinct_command_is_registered(self):
        """The 'instinct' command must be in the handler dispatch table."""
        ch = CommandHandler.__new__(CommandHandler)
        ch.world = None
        handlers = {"instinct": ch.cmd_instinct}
        assert "instinct" in handlers

    @pytest.mark.asyncio
    async def test_instinct_command_no_data(self, handler, agent):
        """instinct with no data should show 'no instinct data'."""
        await handler.handle(agent, "instinct")
        text = agent.writer.get_text()
        assert "No instinct data" in text

    @pytest.mark.asyncio
    async def test_instinct_command_with_data(self, handler, agent):
        """instinct with data should show reflex profile."""
        handler.world.instinct_states[agent.name] = {
            "energy": 0.05, "threat": 0.0, "trust": 0.5,
            "has_work": False, "idle_ticks": 0,
        }
        await handler.handle(agent, "instinct")
        text = agent.writer.get_text()
        assert "Instinct Profile" in text
        assert "survive" in text
        assert "5%" in text  # energy at 5%


# ═══════════════════════════════════════════════════════════════════════════
# 3. Git Bridge Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestGitBridge:

    def test_world_has_fleet_events(self, world):
        """World must have fleet_events list initialized."""
        assert hasattr(world, "fleet_events")
        assert isinstance(world.fleet_events, list)

    def test_fleet_command_is_registered(self):
        """The 'fleet' command must be in the handler dispatch table."""
        ch = CommandHandler.__new__(CommandHandler)
        ch.world = None
        handlers = {"fleet": ch.cmd_fleet}
        assert "fleet" in handlers

    @pytest.mark.asyncio
    async def test_fleet_command_no_events(self, handler, agent):
        """fleet with no events should show 'fleet is quiet'."""
        await handler.handle(agent, "fleet")
        text = agent.writer.get_text()
        assert "Fleet Activity" in text
        assert "quiet" in text

    @pytest.mark.asyncio
    async def test_fleet_command_with_events(self, handler, agent):
        """fleet with events should list them."""
        handler.world.fleet_events = [
            "hammer alice pushed to flux-vm: fix decode bug",
            "sparkle bob created new repo: isa-spec-v3",
            "clipboard carol opened issue on telepathy-c: segfault on ARM64",
        ]
        await handler.handle(agent, "fleet")
        text = agent.writer.get_text()
        assert "Fleet Activity" in text
        assert "alice pushed" in text
        assert "3/3 events" in text


class TestGitBridgeEventParsing:

    def test_parse_push_event(self):
        """PushEvent should produce a message about pushing."""
        from git_bridge import fetch_events
        mock_response = [{
            "id": "12345",
            "type": "PushEvent",
            "created_at": "2099-01-01T00:00:00Z",
            "repo": {"name": "SuperInstance/flux-vm"},
            "actor": {"login": "alice"},
            "payload": {"commits": [{"message": "fix decode bug in opcode handler"}]},
        }]
        with patch("git_bridge.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            events = fetch_events("SuperInstance", "2098-01-01T00:00:00Z")
            assert len(events) == 1
            assert "alice" in events[0]
            assert "flux-vm" in events[0]
            assert "fix decode bug" in events[0]

    def test_parse_create_event(self):
        """CreateEvent (repository) should produce a creation message."""
        from git_bridge import fetch_events
        mock_response = [{
            "id": "12346",
            "type": "CreateEvent",
            "created_at": "2099-01-01T00:00:00Z",
            "repo": {"name": "SuperInstance/new-repo"},
            "actor": {"login": "bob"},
            "payload": {"ref_type": "repository"},
        }]
        with patch("git_bridge.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            events = fetch_events("SuperInstance", "2098-01-01T00:00:00Z")
            assert len(events) == 1
            assert "new repo" in events[0]
            assert "bob" in events[0]

    def test_parse_issues_event(self):
        """IssuesEvent should produce an issue-related message."""
        from git_bridge import fetch_events
        mock_response = [{
            "id": "12347",
            "type": "IssuesEvent",
            "created_at": "2099-01-01T00:00:00Z",
            "repo": {"name": "SuperInstance/telepathy-c"},
            "actor": {"login": "carol"},
            "payload": {"action": "opened", "issue": {"title": "segfault on ARM64 decode"}},
        }]
        with patch("git_bridge.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            events = fetch_events("SuperInstance", "2098-01-01T00:00:00Z")
            assert len(events) == 1
            assert "opened" in events[0]
            assert "carol" in events[0]

    def test_fetch_filters_by_timestamp(self):
        """Events before 'since' should be filtered out."""
        from git_bridge import fetch_events
        mock_response = [{
            "id": "12348",
            "type": "PushEvent",
            "created_at": "2020-01-01T00:00:00Z",  # old event
            "repo": {"name": "SuperInstance/old-repo"},
            "actor": {"login": "old_agent"},
            "payload": {"commits": [{"message": "old commit"}]},
        }]
        with patch("git_bridge.urllib.request.urlopen") as mock_urlopen:
            mock_resp = MagicMock()
            mock_resp.read.return_value = json.dumps(mock_response).encode()
            mock_resp.__enter__ = lambda self: mock_resp
            mock_resp.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_resp

            events = fetch_events("SuperInstance", "2099-01-01T00:00:00Z")
            assert len(events) == 0  # filtered out


# ═══════════════════════════════════════════════════════════════════════════
# 4. Algorithmic NPC Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestAlgorithmicNPCs:

    def test_harbor_master_in_world_npcs(self, world):
        """Harbor Master must exist in world.npcs after World init."""
        assert "Harbor Master" in world.npcs

    def test_dojo_sensei_in_world_npcs(self, world):
        """Dojo Sensei must exist in world.npcs after World init."""
        assert "Dojo Sensei" in world.npcs

    def test_harbor_master_in_world_algo_npcs(self, world):
        """Harbor Master must be in world.algo_npcs."""
        assert "Harbor Master" in world.algo_npcs
        assert isinstance(world.algo_npcs["Harbor Master"], HarborMaster)

    def test_dojo_sensei_in_world_algo_npcs(self, world):
        """Dojo Sensei must be in world.algo_npcs."""
        assert "Dojo Sensei" in world.algo_npcs
        assert isinstance(world.algo_npcs["Dojo Sensei"], DojoSensei)

    def test_harbor_master_room_assignment(self, world):
        """Harbor Master should be assigned to harbor room."""
        assert world.npcs["Harbor Master"]["room"] == "harbor"
        assert world.npcs["Harbor Master"]["role"] == "onboarding"
        assert world.npcs["Harbor Master"]["algorithmic"] is True

    def test_dojo_sensei_room_assignment(self, world):
        """Dojo Sensei should be assigned to dojo room."""
        assert world.npcs["Dojo Sensei"]["room"] == "dojo"
        assert world.npcs["Dojo Sensei"]["role"] == "training"
        assert world.npcs["Dojo Sensei"]["algorithmic"] is True


class TestHarborMasterNPC:

    def test_harbor_master_greeting(self):
        hm = HarborMaster()
        assert hm.greeting  # non-empty
        assert "Harbor" in hm.name

    def test_harbor_master_responds_to_greeting(self):
        hm = HarborMaster()
        resp = hm.respond("flux-chronometer")
        assert "registered" in resp.lower() or "vessel" in resp.lower()

    def test_harbor_master_advances_state(self):
        hm = HarborMaster()
        assert hm.state == "greeting"
        hm.respond("flux-chronometer")
        assert hm.state == "fleet_registration"
        assert "greeting" in hm.completed

    def test_harbor_master_completes_onboarding(self):
        hm = HarborMaster()
        inputs = ["my-ship", "read charter", "drop bottle", "log entry", "pick task"]
        for inp in inputs:
            hm.respond(inp)
        assert hm.is_done()

    def test_harbor_master_sets_vessel_name_flag(self):
        hm = HarborMaster()
        hm.respond("flux-chronometer")
        assert hm.flags.get("vessel_name") == "flux-chronometer"


class TestDojoSenseiNPC:

    def test_dojo_sensei_greeting(self):
        ds = DojoSensei()
        assert ds.greeting  # non-empty
        assert "Sensei" in ds.name

    def test_dojo_sensei_responds_to_greeting(self):
        ds = DojoSensei()
        resp = ds.respond("hello")
        assert "Level 1" in resp
        assert "Charter Reading" in resp

    def test_dojo_sensei_passes_with_specific_answer(self):
        ds = DojoSensei()
        ds.respond("hello")  # trigger greeting
        # A specific answer with keywords and length >= 20 words
        specific_answer = (
            "The charter explains that this vessel is responsible for implementing "
            "the FLUX bytecode VM. The mission is to ensure conformance across all "
            "five language backends: Python, C, Go, Rust, and Zig. The main "
            "responsibility is maintaining the instruction set architecture spec."
        )
        resp = ds.respond(specific_answer)
        assert "PASSED" in resp

    def test_dojo_sensei_fails_vague_answer(self):
        ds = DojoSensei()
        ds.respond("hello")  # trigger greeting
        resp = ds.respond("It's about a charter thing")
        assert "Not quite" in resp

    def test_dojo_sensei_tracks_completed_levels(self):
        ds = DojoSensei()
        ds.respond("hello")
        ds.current_level = 4  # fast-forward to last level
        specific_answer = (
            "I'll build a room that connects to the flux-vm repo with proper "
            "description, linked repository, items from actual source files, "
            "and clear exits to the tavern and workshop. The room will use "
            "atmospheric description to teach through immersion."
        )
        ds.respond(specific_answer)
        assert "black belt" in ds.respond("").lower() or ds.is_done()


class TestAlgoNPCGreetingOnEnter:

    @pytest.mark.asyncio
    async def test_go_to_harbor_greets_harbor_master(self, handler, agent):
        """Entering harbor should trigger Harbor Master greeting."""
        agent.room_name = "tavern"
        await handler.cmd_go(agent, "harbor")
        text = agent.writer.get_text()
        assert "Harbor Master" in text
        assert agent.room_name == "harbor"

    @pytest.mark.asyncio
    async def test_go_to_dojo_greets_dojo_sensei(self, handler, agent):
        """Entering dojo should trigger Dojo Sensei greeting."""
        agent.room_name = "tavern"
        await handler.cmd_go(agent, "dojo")
        text = agent.writer.get_text()
        assert "Dojo Sensei" in text
        assert agent.room_name == "dojo"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Studio Engine Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestStudioEngine:

    def test_studio_creates_rooms_with_connections(self):
        """build_studio should create a Studio with rooms and LiveConnections."""
        studio = build_studio()
        assert len(studio.rooms) >= 4
        assert "harbor" in studio.rooms
        assert "lighthouse" in studio.rooms
        assert "engine" in studio.rooms
        assert "workshop" in studio.rooms
        for room_id, room in studio.rooms.items():
            assert room.connection is not None
            assert isinstance(room.connection, LiveConnection)

    def test_live_connection_types(self):
        """LiveConnection should handle different connection types."""
        shell_conn = LiveConnection("test_shell", "shell", {})
        assert shell_conn.conn_type == "shell"
        assert shell_conn.status == "disconnected"

        github_conn = LiveConnection("test_github", "github", {})
        assert github_conn.conn_type == "github"

        http_conn = LiveConnection("test_http", "http", {"url": "http://example.com"})
        assert http_conn.conn_type == "http"

        keeper_conn = LiveConnection("test_keeper", "keeper", {"url": "http://127.0.0.1:8900"})
        assert keeper_conn.conn_type == "keeper"

    def test_live_connection_shell_connect(self):
        """Shell type LiveConnection should connect successfully."""
        conn = LiveConnection("shell", "shell", {})
        result = conn.connect()
        assert result["status"] == "connected"
        assert conn.status == "connected"

    def test_live_connection_shell_execute(self):
        """Shell type LiveConnection should execute commands."""
        conn = LiveConnection("shell", "shell", {})
        conn.connect()
        result = conn.execute("run", {"cmd": "echo hello", "timeout": 5})
        assert result["status"] == "ok"
        assert "hello" in result["stdout"]

    def test_studio_enter_room(self):
        """Studio.enter should return room info."""
        studio = build_studio()
        info = studio.enter("harbor", "test_agent")
        assert isinstance(info, str)
        assert "Harbor" in info
        assert "LIVE" in info or "OFFLINE" in info

    def test_studio_enter_nonexistent_room(self):
        """Studio.enter with invalid room should return error."""
        studio = build_studio()
        info = studio.enter("nonexistent", "test_agent")
        assert "No room" in info

    def test_studio_execute(self):
        """Studio.execute should call connection.execute."""
        studio = build_studio()
        result = studio.execute("engine", "run", {"cmd": "echo test", "timeout": 5}, "test_agent")
        assert result["status"] == "ok"
        assert len(studio.log) == 1
        assert studio.log[0]["agent"] == "test_agent"

    def test_studio_execute_invalid_room(self):
        """Studio.execute with invalid room should return error."""
        studio = build_studio()
        result = studio.execute("nonexistent", "run", {})
        assert "error" in result

    def test_studio_rooms_have_commands(self):
        """Each studio room should have at least one command."""
        studio = build_studio()
        for room_id, room in studio.rooms.items():
            assert len(room.commands) >= 1


class TestStudioCommand:

    def test_studio_command_is_registered(self):
        """The 'studio' command must be in the handler dispatch table."""
        ch = CommandHandler.__new__(CommandHandler)
        ch.world = None
        handlers = {"studio": ch.cmd_studio}
        assert "studio" in handlers

    @pytest.mark.asyncio
    async def test_studio_command_no_studio(self, handler, agent):
        """studio with no _studio attribute should show 'not available'."""
        assert not hasattr(handler, '_studio')
        await handler.handle(agent, "studio")
        text = agent.writer.get_text()
        assert "not available" in text

    @pytest.mark.asyncio
    async def test_studio_command_with_studio_attached(self, handler, agent):
        """studio with _studio should list rooms."""
        handler._studio = build_studio()
        await handler.handle(agent, "studio")
        text = agent.writer.get_text()
        assert "Studio" in text or "Live" in text
        assert "Harbor" in text


# ═══════════════════════════════════════════════════════════════════════════
# 6. Cross-Module Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCrossModuleCommands:

    def test_all_new_commands_exist_in_handler(self):
        """All new commands (runtime, instinct, fleet, studio) must be in handlers."""
        ch = CommandHandler.__new__(CommandHandler)
        ch.world = None
        new_commands = ["runtime", "instinct", "fleet", "studio"]
        for cmd in new_commands:
            assert hasattr(ch, f"cmd_{cmd}"), f"cmd_{cmd} not found on CommandHandler"

    @pytest.mark.asyncio
    async def test_runtime_command_recognized(self, handler, agent):
        """'runtime' should NOT be unknown command."""
        agent.room_name = "tavern"  # no runtime here
        await handler.handle(agent, "runtime")
        text = agent.writer.get_text()
        assert "Unknown command" not in text
        assert "No runtime" in text

    @pytest.mark.asyncio
    async def test_instinct_command_recognized(self, handler, agent):
        """'instinct' should NOT be unknown command."""
        await handler.handle(agent, "instinct")
        text = agent.writer.get_text()
        assert "Unknown command" not in text

    @pytest.mark.asyncio
    async def test_fleet_command_recognized(self, handler, agent):
        """'fleet' should NOT be unknown command."""
        await handler.handle(agent, "fleet")
        text = agent.writer.get_text()
        assert "Unknown command" not in text

    @pytest.mark.asyncio
    async def test_studio_command_recognized(self, handler, agent):
        """'studio' should NOT be unknown command."""
        await handler.handle(agent, "studio")
        text = agent.writer.get_text()
        assert "Unknown command" not in text


class TestWorldInitialization:

    def test_world_initializes_all_subsystems(self, world):
        """World.__init__ should set up runtimes, algo_npcs, instinct_states, fleet_events."""
        assert isinstance(world.runtimes, dict)
        assert isinstance(world.algo_npcs, dict)
        assert isinstance(world.instinct_states, dict)
        assert isinstance(world.fleet_events, list)

    def test_world_runtimes_have_correct_types(self, world):
        """All runtimes should be RoomRuntime instances with LivingManuals."""
        from room_runtime import RoomRuntime
        for room_id, rt in world.runtimes.items():
            assert isinstance(rt, RoomRuntime)
            assert rt.manual is not None
            assert isinstance(rt.manual, LivingManual)

    def test_world_algo_npcs_are_algorithmic(self, world):
        """All algo_npcs should be AlgorithmicNPC instances."""
        for name, npc in world.algo_npcs.items():
            assert isinstance(npc, AlgorithmicNPC)
            assert npc.greeting  # non-empty greeting


class TestServerStarts:

    def test_mud_server_instantiates(self, world):
        """MUDServer should instantiate without errors."""
        handler = CommandHandler(world)
        server = MUDServer(world, handler, port=7777)
        assert server.world is world
        assert server.handler is handler
        assert server.port == 7777

    def test_server_attributes_initialized(self, world):
        """MUDServer should have proper initial state."""
        handler = CommandHandler(world)
        server = MUDServer(world, handler)
        assert server.git_sync is None
        assert server._studio is None
        assert server._instinct_engine is None


class TestRuntimeCommandExecution:

    @pytest.mark.asyncio
    async def test_runtime_info_in_runtime_room(self, handler, agent):
        """'runtime' with no args in a runtime room shows runtime info."""
        agent.room_name = "flux_lab"
        await handler.handle(agent, "runtime")
        text = agent.writer.get_text()
        assert "Runtime" in text
        assert "testing" in text.lower()

    @pytest.mark.asyncio
    async def test_runtime_execute_command_in_runtime_room(self, handler, agent):
        """'runtime <cmd>' should execute a valid runtime command."""
        agent.room_name = "flux_lab"
        # Boot the runtime first
        handler.world.runtimes["flux_lab"].boot(agent.name)
        cmd_name = list(handler.world.runtimes["flux_lab"].commands.keys())[0]
        await handler.handle(agent, f"runtime {cmd_name}")
        text = agent.writer.get_text()
        assert "Runtime error" not in text

    @pytest.mark.asyncio
    async def test_runtime_invalid_command_in_runtime_room(self, handler, agent):
        """'runtime invalid_cmd' in a runtime room should show error."""
        agent.room_name = "flux_lab"
        handler.world.runtimes["flux_lab"].boot(agent.name)
        await handler.handle(agent, "runtime nonexistent_cmd")
        text = agent.writer.get_text()
        assert "error" in text.lower() or "Unknown" in text


# ═══════════════════════════════════════════════════════════════════════════
# 7. Room Templates and Factory
# ═══════════════════════════════════════════════════════════════════════════

class TestRoomTemplates:

    def test_room_templates_available(self):
        """All three room templates should be available."""
        assert "cnc" in ROOM_TEMPLATES
        assert "robotics" in ROOM_TEMPLATES
        assert "testing" in ROOM_TEMPLATES

    def test_create_room_cnc(self, tmp_path):
        """create_room('cnc') should produce a CNC runtime."""
        rt = create_room("cnc", "my_cnc", str(tmp_path / "manuals"))
        assert rt.runtime_type == "cnc"
        assert "run_unit" not in rt.commands  # CNC has different commands
        assert "run" in rt.commands
        assert rt.manual is not None

    def test_create_room_robotics(self, tmp_path):
        """create_room('robotics') should produce a robotics runtime."""
        rt = create_room("robotics", "my_robot", str(tmp_path / "manuals"))
        assert rt.runtime_type == "robotics"
        assert "power_on" in rt.commands
        assert "grip" in rt.commands

    def test_create_room_testing(self, tmp_path):
        """create_room('testing') should produce a testing runtime."""
        rt = create_room("testing", "my_test", str(tmp_path / "manuals"))
        assert rt.runtime_type == "testing"
        assert "run_unit" in rt.commands
        assert "run_conformance" in rt.commands
        assert "benchmark" in rt.commands

    def test_create_room_invalid_type(self):
        """create_room with unknown type should raise ValueError."""
        with pytest.raises(ValueError, match="Unknown room type"):
            create_room("quantum", "test", "/tmp/test_manuals")
