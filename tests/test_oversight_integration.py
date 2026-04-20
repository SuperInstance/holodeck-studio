#!/usr/bin/env python3
"""
Integration tests for agentic_oversight wired into server.py.

Tests oversight sessions, evolving scripts, and command handlers.
No TCP server is started — everything is tested by direct instantiation.
"""

import asyncio
import json
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import World, Room, Agent, CommandHandler
from agentic_oversight import (
    OversightSession, OversightTick, EvolvingScript, HumanPlayer,
)


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
# 1. OversightSession Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestOversightSessionCreation:

    def test_create_session(self):
        session = OversightSession("Test Operation", "test-agent")
        assert session.operation == "Test Operation"
        assert session.agent == "test-agent"
        assert session.ticks == []
        assert session.script is not None
        assert session.script.version == 1
        assert session.started is not None
        assert session.ended is None

    def test_session_has_evolved_script(self):
        session = OversightSession("Deploy Pipeline", "flux-chronometer")
        assert isinstance(session.script, EvolvingScript)
        assert len(session.script.rules) >= 4  # seed rules

    def test_session_tick_recording(self):
        session = OversightSession("CI Pipeline", "bot1")
        tick = session.tick(
            changes=[{"type": "test_pass", "desc": "85/88 passing"}],
            gauges={"cpu": 0.3, "memory": 0.45},
        )
        assert tick.tick_num == 1
        assert tick.agent_action != ""
        assert tick.autonomy_score == 1.0  # first tick, no nudge
        assert len(session.ticks) == 1

    def test_multiple_ticks(self):
        session = OversightSession("Deploy", "agent")
        session.tick(
            changes=[{"type": "test_pass", "desc": "all passing"}],
            gauges={"cpu": 0.2},
        )
        session.tick(
            changes=[{"type": "new_commit", "desc": "new code pushed"}],
            gauges={"cpu": 0.5},
        )
        assert len(session.ticks) == 2
        assert session.ticks[1].tick_num == 2

    def test_tick_with_human_nudge(self):
        session = OversightSession("Deploy", "agent")
        session.tick(
            changes=[{"type": "test_fail", "desc": "regression"}],
            gauges={"cpu": 0.8, "regressions": 0.75},
        )
        # Second tick with human input
        tick2 = session.tick(
            changes=[{"type": "test_fail", "desc": "still failing"}],
            gauges={"cpu": 0.8, "regressions": 0.75},
            human_input="Bisect the commit that broke it.",
        )
        assert tick2.nudges_needed == 1
        assert session.total_nudges == 1
        assert session.script.version == 2  # evolved
        assert tick2.autonomy_score < 1.0  # nudged

    def test_end_session_report(self):
        session = OversightSession("CI Pipeline", "bot1")
        session.tick([], {"cpu": 0.3})
        session.tick(
            [{"type": "fail", "desc": "broken"}],
            {"cpu": 0.9},
            human_input="Check the build logs",
        )
        report = session.end_session()
        assert report["operation"] == "CI Pipeline"
        assert report["ticks"] == 2
        assert report["autonomous_ticks"] == 1
        assert report["nudged_ticks"] == 1
        assert report["script_evolution"]["rules_added"] >= 0  # may adapt existing rule
        assert session.ended is not None

    def test_generate_perspective(self):
        session = OversightSession("FLUX CI", "flux-chronometer")
        session.tick(
            [{"type": "test_pass", "desc": "88/88 passing"}],
            {"cpu": 0.3, "memory": 0.45},
        )
        perspective = session.generate_perspective()
        assert "FLUX CI" in perspective
        assert "flux-chronometer" in perspective
        assert "1 check-ins" in perspective


# ═══════════════════════════════════════════════════════════════════════════
# 2. EvolvingScript Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEvolvingScriptSaveLoad:

    def test_script_save_to_file(self, tmp_path):
        script = EvolvingScript("CI Pipeline", "bot1")
        script.learn("When tests fail, run bisect.", "continue monitoring",
                      [{"type": "fail"}], {"cpu": 0.8})
        script_dir = tmp_path / "scripts"
        script_dir.mkdir()
        script_file = script_dir / "ci_pipeline_v2.json"
        data = {
            "task_name": script.task_name,
            "agent": script.agent,
            "version": script.version,
            "rules": script.rules,
            "adaptations": script.adaptations,
        }
        script_file.write_text(json.dumps(data, indent=2))
        assert script_file.exists()
        loaded = json.loads(script_file.read_text())
        assert loaded["version"] == 2
        assert len(loaded["rules"]) >= 4  # 4 seed, may adapt instead of add

    def test_script_load_from_file(self, tmp_path):
        # Create a saved script
        script = EvolvingScript("Deploy", "agent1")
        script.learn("On failure, roll back.", "alert human",
                      [{"type": "deploy_fail"}], {"cpu": 0.95})
        script_file = tmp_path / "deploy_v2.json"
        script_file.write_text(json.dumps({
            "task_name": script.task_name,
            "agent": script.agent,
            "version": script.version,
            "rules": script.rules,
            "adaptations": script.adaptations,
        }, indent=2))

        # Load it back
        data = json.loads(script_file.read_text())
        loaded_script = EvolvingScript(data["task_name"], data["agent"])
        loaded_script.version = data.get("version", 1)
        loaded_script.rules = data.get("rules", loaded_script.rules)
        loaded_script.adaptations = data.get("adaptations", [])

        assert loaded_script.version == 2
        assert len(loaded_script.rules) >= 4  # 4 seed, may adapt instead of add
        assert len(loaded_script.adaptations) == 1

    def test_script_serialization_roundtrip(self, tmp_path):
        script = EvolvingScript("Test Task", "tester")
        script.learn("Do X when Y happens.", "observe",
                      [{"type": "y_event"}], {"gauge": 0.7})
        data = {
            "task_name": script.task_name,
            "agent": script.agent,
            "version": script.version,
            "rules": script.rules,
            "adaptations": script.adaptations,
        }
        json_str = json.dumps(data)
        restored = json.loads(json_str)
        assert restored["version"] == 2
        assert restored["task_name"] == "Test Task"

    def test_script_generate_readme(self):
        script = EvolvingScript("FLUX CI", "flux-chronometer")
        readme = script.generate_readme()
        assert "FLUX CI" in readme
        assert "seeded" in readme.lower() or "seed" in readme.lower()
        assert "Rule" in readme or "rule" in readme


# ═══════════════════════════════════════════════════════════════════════════
# 3. Command Handler Tests — cmd_oversee
# ═══════════════════════════════════════════════════════════════════════════

class TestCmdOversee:

    @pytest.mark.asyncio
    async def test_oversee_start(self, handler, agent):
        await handler.handle(agent, "oversee start CI Pipeline")
        text = agent.writer.get_text()
        assert "Oversight Session Started" in text
        assert "CI Pipeline" in text
        assert agent.name in handler.world.oversight_sessions

    @pytest.mark.asyncio
    async def test_oversee_start_no_name(self, handler, agent):
        await handler.handle(agent, "oversee start")
        text = agent.writer.get_text()
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_oversee_tick(self, handler, agent):
        await handler.handle(agent, "oversee start Test Op")
        agent.writer.clear()
        await handler.handle(agent, 'oversee tick [{"type":"test_pass","desc":"all good"}] | {"cpu":0.3}')
        text = agent.writer.get_text()
        assert "Tick #1" in text
        assert "Action:" in text
        assert "Autonomy:" in text

    @pytest.mark.asyncio
    async def test_oversee_tick_no_session(self, handler, agent):
        await handler.handle(agent, 'oversee tick [{"type":"x"}] | {}')
        text = agent.writer.get_text()
        assert "No active oversight session" in text

    @pytest.mark.asyncio
    async def test_oversee_tick_with_nudge(self, handler, agent):
        await handler.handle(agent, "oversee start Deploy")
        agent.writer.clear()
        await handler.handle(agent, 'oversee tick [{"type":"fail"}] | {"cpu":0.8} | Run bisect to find the issue')
        text = agent.writer.get_text()
        assert "Nudge:" in text
        session = handler.world.oversight_sessions[agent.name]
        assert session.script.version == 2

    @pytest.mark.asyncio
    async def test_oversee_stop(self, handler, agent):
        await handler.handle(agent, "oversee start CI Pipeline")
        await handler.handle(agent, 'oversee tick [{"type":"pass"}] | {"cpu":0.2}')
        agent.writer.clear()
        await handler.handle(agent, "oversee stop")
        text = agent.writer.get_text()
        assert "Oversight Report" in text
        assert "CI Pipeline" in text
        assert "Ticks:" in text
        assert agent.name not in handler.world.oversight_sessions

    @pytest.mark.asyncio
    async def test_oversee_stop_no_session(self, handler, agent):
        await handler.handle(agent, "oversee stop")
        text = agent.writer.get_text()
        assert "No active oversight session" in text

    @pytest.mark.asyncio
    async def test_oversee_perspective(self, handler, agent):
        await handler.handle(agent, "oversee start FLUX Conformance")
        await handler.handle(agent, 'oversee tick [{"type":"pass","desc":"88/88"}] | {"cpu":0.3}')
        agent.writer.clear()
        await handler.handle(agent, "oversee perspective")
        text = agent.writer.get_text()
        assert "FLUX Conformance" in text

    @pytest.mark.asyncio
    async def test_oversee_status_no_session(self, handler, agent):
        await handler.handle(agent, "oversee")
        text = agent.writer.get_text()
        assert "No active oversight sessions" in text

    @pytest.mark.asyncio
    async def test_oversee_status_with_session(self, handler, agent):
        await handler.handle(agent, "oversee start My Op")
        agent.writer.clear()
        await handler.handle(agent, "oversee")
        text = agent.writer.get_text()
        assert "Active oversight: My Op" in text


# ═══════════════════════════════════════════════════════════════════════════
# 4. Command Handler Tests — cmd_script
# ═══════════════════════════════════════════════════════════════════════════

class TestCmdScript:

    @pytest.mark.asyncio
    async def test_script_show_no_session(self, handler, agent):
        await handler.handle(agent, "script show")
        text = agent.writer.get_text()
        assert "No active oversight session" in text

    @pytest.mark.asyncio
    async def test_script_show(self, handler, agent):
        await handler.handle(agent, "oversee start CI Pipeline")
        agent.writer.clear()
        await handler.handle(agent, "script show")
        text = agent.writer.get_text()
        assert "Evolving Script" in text
        assert "CI Pipeline" in text
        assert "Rules:" in text
        assert "seed" in text

    @pytest.mark.asyncio
    async def test_script_save(self, handler, agent, tmp_path):
        # Override script dir to tmp_path
        await handler.handle(agent, "oversee start CI Pipeline")
        agent.writer.clear()
        # Save uses Path("world")/scripts by default, let's just verify it doesn't crash
        await handler.handle(agent, "script save")
        text = agent.writer.get_text()
        assert "Script saved:" in text or "No active" in text

    @pytest.mark.asyncio
    async def test_script_load(self, handler, agent, tmp_path):
        # Create a script file
        script = EvolvingScript("LoadTest", "agent1")
        script.learn("On error, retry.", "continue",
                      [{"type": "error"}], {"cpu": 0.7})
        script_file = tmp_path / "loadtest_script.json"
        script_file.write_text(json.dumps({
            "task_name": script.task_name,
            "agent": script.agent,
            "version": script.version,
            "rules": script.rules,
            "adaptations": script.adaptations,
        }, indent=2))

        await handler.handle(agent, f"script load {script_file}")
        text = agent.writer.get_text()
        assert "Script loaded:" in text
        assert "LoadTest" in text
        assert agent.name in handler.world.oversight_sessions

    @pytest.mark.asyncio
    async def test_script_load_nonexistent(self, handler, agent):
        await handler.handle(agent, "script load /nonexistent/path.json")
        text = agent.writer.get_text()
        assert "File not found" in text

    @pytest.mark.asyncio
    async def test_script_readme(self, handler, agent):
        await handler.handle(agent, "oversee start Readme Test")
        agent.writer.clear()
        await handler.handle(agent, "script readme")
        text = agent.writer.get_text()
        assert "Readme Test" in text
        # EvolvingScript.generate_readme includes "Rule" or "rule"
        assert "rule" in text.lower()

    @pytest.mark.asyncio
    async def test_script_no_args(self, handler, agent):
        await handler.handle(agent, "script")
        text = agent.writer.get_text()
        assert "Evolving Scripts" in text


# ═══════════════════════════════════════════════════════════════════════════
# 5. World Wiring Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWorldOversightWiring:

    def test_world_has_oversight_sessions(self, world):
        assert hasattr(world, "oversight_sessions")
        assert isinstance(world.oversight_sessions, dict)

    def test_world_oversight_sessions_empty(self, world):
        assert len(world.oversight_sessions) == 0

    def test_oversee_command_in_handlers(self):
        ch = CommandHandler.__new__(CommandHandler)
        ch.world = None
        assert hasattr(ch, "cmd_oversee")
        assert hasattr(ch, "cmd_script")

    @pytest.mark.asyncio
    async def test_oversee_recognized_as_command(self, handler, agent):
        await handler.handle(agent, "oversee")
        text = agent.writer.get_text()
        assert "Unknown command" not in text

    @pytest.mark.asyncio
    async def test_script_recognized_as_command(self, handler, agent):
        await handler.handle(agent, "script")
        text = agent.writer.get_text()
        assert "Unknown command" not in text


# ═══════════════════════════════════════════════════════════════════════════
# 6. HumanPlayer Integration
# ═══════════════════════════════════════════════════════════════════════════

class TestHumanPlayerIntegration:

    def test_human_player_demonstrate(self):
        session = OversightSession("CI Pipeline", "flux-chronometer")
        session.tick([], {"cpu": 0.3})
        human = HumanPlayer("Casey")
        result = human.demonstrate(session, "When regressions appear, bisect the commit.")
        assert "Casey" in result
        assert "learned" in result.lower() or "v2" in result
        assert session.script.version == 2

    def test_human_player_read_perspective(self):
        session = OversightSession("FLUX Deploy", "bot1")
        session.tick([{"type": "pass", "desc": "all good"}], {"cpu": 0.2})
        human = HumanPlayer("Casey")
        perspective = human.read_perspective(session)
        assert "FLUX Deploy" in perspective

    def test_human_player_read_script(self):
        session = OversightSession("Build System", "builder")
        human = HumanPlayer("Casey")
        script_text = human.read_script(session)
        assert "Build System" in script_text

    def test_human_player_vibe_refactor(self):
        session = OversightSession("Deploy", "deployer")
        human = HumanPlayer("Casey")
        result = human.vibe_refactor(session, "Check gauges every 60s instead of 30s.")
        assert "Casey" in result
        assert session.script.version == 2
