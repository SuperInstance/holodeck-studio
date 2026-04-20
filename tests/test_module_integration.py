#!/usr/bin/env python3
"""
Integration tests for the 4 wired standalone modules:
- deckboss_bridge: character sheets, bootcamp levels, dashboard
- perception_room: visitor tracking, perception profiles
- rival_combat: duels, backtesting scenarios
- actualization_loop: live gauges, CI pipeline, after-action reports
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

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


def make_agent(name="testbot", role="vessel", room="tavern"):
    return Agent(name=name, role=role, room_name=room, writer=FakeWriter())


@pytest_asyncio.fixture
async def world(tmp_path):
    return World(world_dir=str(tmp_path / "world"))


@pytest_asyncio.fixture
async def handler(world):
    from mud_extensions import patch_handler
    patch_handler(CommandHandler)
    return CommandHandler(world)


@pytest_asyncio.fixture
def agent():
    return make_agent("TestAgent", "vessel", "tavern")


# ═══════════════════════════════════════════════════════════════════════════
# 1. deckboss_bridge module tests
# ═══════════════════════════════════════════════════════════════════════════

class TestDeckBossModule:

    def test_deckboss_bridge_import(self):
        from deckboss_bridge import DeckBossBridge, generate_character_sheet, BOOTCAMP_LEVELS
        assert callable(DeckBossBridge)
        assert callable(generate_character_sheet)
        assert isinstance(BOOTCAMP_LEVELS, dict)
        assert len(BOOTCAMP_LEVELS) == 5

    def test_deckboss_bridge_creation(self):
        from deckboss_bridge import DeckBossBridge
        bridge = DeckBossBridge()
        assert bridge.sessions == {}
        assert bridge.artifact_queue == []

    def test_generate_character_sheet(self):
        from deckboss_bridge import generate_character_sheet
        sheet = generate_character_sheet(
            agent_name="test-agent", level=3,
            completed_quests=["Quest 1", "Quest 2"],
            skills={"fleet_navigation": 7, "combat_scripts": 5})
        assert "test-agent" in sheet
        assert "3/5" in sheet
        assert "Quest 1" in sheet
        assert "fleet_navigation" in sheet

    def test_bootcamp_levels_structure(self):
        from deckboss_bridge import BOOTCAMP_LEVELS
        for level in range(1, 6):
            assert level in BOOTCAMP_LEVELS
            data = BOOTCAMP_LEVELS[level]
            assert "name" in data
            assert "room" in data
            assert "objective" in data
            assert "skills" in data

    def test_deckboss_dashboard(self):
        from deckboss_bridge import DeckBossBridge
        bridge = DeckBossBridge()
        bridge.watch_conversation("test-001", "tavern", [], [])
        dashboard = bridge.format_dashboard()
        assert "DECKBOSS" in dashboard
        assert "Active Sessions" in dashboard

    @pytest.mark.asyncio
    async def test_cmd_sheet(self, handler, agent):
        await handler.cmd_sheet(agent, "")
        text = agent.writer.get_text()
        assert "Character Sheet" in text
        assert "TestAgent" in text

    @pytest.mark.asyncio
    async def test_cmd_sheet_for_target(self, handler, agent):
        await handler.cmd_sheet(agent, "OtherAgent")
        text = agent.writer.get_text()
        assert "OtherAgent" in text

    @pytest.mark.asyncio
    async def test_cmd_bootcamp(self, handler, agent):
        await handler.cmd_bootcamp(agent, "")
        text = agent.writer.get_text()
        assert "Bootcamp" in text
        assert "Level 1" in text
        assert "Level 5" in text
        assert "Harbor Orientation" in text

    @pytest.mark.asyncio
    async def test_cmd_deckboss(self, handler, agent):
        await handler.cmd_deckboss(agent, "")
        text = agent.writer.get_text()
        assert "DECKBOSS" in text

    @pytest.mark.asyncio
    async def test_sheet_command_via_handle(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "sheet")
        text = agent.writer.get_text()
        assert "Character Sheet" in text


# ═══════════════════════════════════════════════════════════════════════════
# 2. perception_room module tests
# ═══════════════════════════════════════════════════════════════════════════

class TestPerceptionModule:

    def test_perception_tracker_import(self):
        from perception_room import PerceptionTracker, VisitorProfile, JEPAOptimizer, OpcodeBreeder
        assert callable(PerceptionTracker)
        assert callable(JEPAOptimizer)
        assert callable(OpcodeBreeder)

    def test_perception_tracker_creation(self):
        from perception_room import PerceptionTracker
        tracker = PerceptionTracker("test-agent", "tavern")
        assert tracker.agent == "test-agent"
        assert tracker.room_id == "tavern"
        assert len(tracker.moments) == 0

    def test_perception_tracker_record(self):
        from perception_room import PerceptionTracker
        tracker = PerceptionTracker("test-agent", "tavern")
        tracker.record("command", "look", confidence=0.8)
        assert len(tracker.moments) == 1
        assert tracker.moments[0].action == "command"

    def test_perception_tracker_analysis(self):
        from perception_room import PerceptionTracker
        tracker = PerceptionTracker("test-agent", "tavern")
        tracker.record("command", "look", confidence=0.8)
        tracker.record("hesitate", "exit_list", confidence=0.3)
        analysis = tracker.analysis()
        assert "error" not in analysis
        assert analysis["total_moments"] == 2
        assert analysis["hesitation_count"] == 1

    def test_visitor_profiles(self):
        from perception_room import VisitorProfile
        all_profiles = VisitorProfile.all()
        assert "first_timer" in all_profiles
        assert "expert_evaluator" in all_profiles
        profile = VisitorProfile.get("first_timer")
        assert profile["name"] == "The Genuine First-Timer"

    def test_jepa_optimizer(self):
        from perception_room import JEPAOptimizer, PerceptionTracker
        jepa = JEPAOptimizer()
        tracker = PerceptionTracker("agent1", "room1")
        tracker.record("hesitate", "step_2", confidence=0.2)
        tracker.execute("run", True)
        jepa.ingest(tracker.analysis())
        result = jepa.optimize("room1")
        assert "sessions_analyzed" in result
        assert result["sessions_analyzed"] == 1

    def test_opcode_breeder(self):
        from perception_room import OpcodeBreeder
        breeder = OpcodeBreeder()
        for _ in range(15):
            breeder.observe(["read", "execute"], "room1", "agent1")
        candidates = breeder.get_candidates(min_count=5, min_rooms=1)
        assert len(candidates) >= 1

    @pytest.mark.asyncio
    async def test_cmd_perception_no_data(self, handler, agent):
        await handler.cmd_perception(agent, "")
        text = agent.writer.get_text()
        assert "No perception data" in text

    @pytest.mark.asyncio
    async def test_cmd_perception_with_data(self, handler, agent):
        from perception_room import PerceptionTracker
        agent.perception = PerceptionTracker(agent.name, agent.room_name)
        agent.perception.record("command", "look", confidence=0.9)
        agent.perception.record("hesitate", "exit", confidence=0.2)
        await handler.cmd_perception(agent, "")
        text = agent.writer.get_text()
        assert "Perception Profile" in text
        assert "Moments: 2" in text
        assert "Hesitations: 1" in text

    @pytest.mark.asyncio
    async def test_perception_recorded_on_command(self, handler, agent):
        from perception_room import PerceptionTracker
        agent.perception = PerceptionTracker(agent.name, agent.room_name)
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "look")
        assert len(agent.perception.moments) >= 1
        # Should have recorded the "look" command
        actions = [m.action for m in agent.perception.moments]
        assert "command" in actions


# ═══════════════════════════════════════════════════════════════════════════
# 3. rival_combat module tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRivalCombatModule:

    def test_backtest_engine_import(self):
        from rival_combat import BackTestEngine, RivalMatch, FleetEvolution
        assert len(BackTestEngine.SCENARIOS) == 7

    def test_backtest_single_scenario(self):
        from rival_combat import BackTestEngine
        rules = [
            {"condition": "all gauges normal", "action": "continue monitoring"},
            {"condition": "regression", "action": "bisect recent commits to find cause"},
        ]
        result = BackTestEngine.run(rules, BackTestEngine.SCENARIOS[0])
        assert "score" in result
        assert "passed" in result
        assert 0 <= result["score"] <= 1

    def test_rival_match(self):
        from rival_combat import RivalAgent, RivalMatch
        seed = [
            {"condition": "test fails", "action": "investigate"},
            {"condition": "service down", "action": "circuit break"},
        ]
        a = RivalAgent("agent-a")
        b = RivalAgent("agent-b")
        a.seed(list(seed))
        b.seed(list(seed))
        match = RivalMatch(a, b)
        result = match.run_match(rounds=2)
        assert "winner" in result
        assert "rounds" in result
        assert len(result["rounds"]) == 2

    def test_rival_match_report(self):
        from rival_combat import RivalAgent, RivalMatch
        a = RivalAgent("alpha")
        b = RivalAgent("beta")
        match = RivalMatch(a, b)
        match.run_match(rounds=1)
        report = match.generate_match_report()
        assert "alpha" in report
        assert "beta" in report
        assert "RIVAL COMBAT" in report

    def test_fleet_evolution(self):
        from rival_combat import RivalAgent, RivalMatch, FleetEvolution
        a = RivalAgent("a")
        b = RivalAgent("b")
        match = RivalMatch(a, b)
        evolution = FleetEvolution()
        evolution.record_match(match)
        best = evolution.get_best_practices()
        assert isinstance(best, list)

    @pytest.mark.asyncio
    async def test_cmd_duel(self, handler, agent):
        await handler.cmd_duel(agent, "alpha beta 2")
        text = agent.writer.get_text()
        assert "alpha" in text
        assert "beta" in text
        assert "RIVAL COMBAT" in text

    @pytest.mark.asyncio
    async def test_cmd_duel_missing_args(self, handler, agent):
        await handler.cmd_duel(agent, "alpha")
        text = agent.writer.get_text()
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_cmd_backtest_all(self, handler, agent):
        await handler.cmd_backtest(agent, "all")
        text = agent.writer.get_text()
        assert "Backtest Results" in text
        assert "S01" in text  # First scenario

    @pytest.mark.asyncio
    async def test_cmd_backtest_single(self, handler, agent):
        await handler.cmd_backtest(agent, "S01")
        text = agent.writer.get_text()
        assert "S01" in text
        assert "Regression" in text

    @pytest.mark.asyncio
    async def test_cmd_backtest_not_found(self, handler, agent):
        await handler.cmd_backtest(agent, "S99")
        text = agent.writer.get_text()
        assert "not found" in text

    @pytest.mark.asyncio
    async def test_duel_command_via_handle(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "duel alpha beta 1")
        text = agent.writer.get_text()
        assert "RIVAL COMBAT" in text


# ═══════════════════════════════════════════════════════════════════════════
# 4. actualization_loop module tests
# ═══════════════════════════════════════════════════════════════════════════

class TestActualizationLoopModule:

    def test_gauge_monitor_import(self):
        from actualization_loop import CIPipeline, GaugeMonitor, AfterActionReport
        assert callable(GaugeMonitor)
        assert callable(AfterActionReport)
        assert callable(CIPipeline)

    def test_gauge_monitor_creation(self):
        from actualization_loop import GaugeMonitor
        gm = GaugeMonitor()
        assert len(gm.readings) == 0

    def test_gauge_monitor_read(self):
        from actualization_loop import GaugeMonitor
        gm = GaugeMonitor()
        reading = gm.read("system_load")
        assert reading.name == "System Load"
        assert reading.status in ("normal", "warning", "critical")

    def test_gauge_monitor_dashboard(self):
        from actualization_loop import GaugeMonitor
        gm = GaugeMonitor()
        gm.read("system_load")
        dashboard = gm.dashboard()
        assert "GAUGE READINGS" in dashboard
        assert "System Load" in dashboard

    def test_gauge_reading_display(self):
        from actualization_loop import GaugeReading
        gr = GaugeReading("Test", 75.0, "%", "warning")
        display = gr.display()
        assert "Test" in display
        assert "75.0%" in display

    def test_after_action_report(self):
        from actualization_loop import AfterActionReport
        aar = AfterActionReport("test-agent", "session-001")
        aar.record_event("strike", "Fixed bug X", "success")
        aar.record_event("adapt", "Changed approach", "discovery")
        aar.add_lesson("Always check edge cases")
        report = aar.generate_report()
        assert "After-Action Report" in report
        assert "test-agent" in report
        assert "Fixed bug X" in report
        assert "edge cases" in report

    def test_aar_experience_weights(self):
        from actualization_loop import AfterActionReport
        aar = AfterActionReport("agent", "s1")
        aar.record_event("strike", "hit", "success")
        aar.record_event("strike", "miss", "failure")
        aar.record_event("adapt", "changed", "discovery")
        aar.weight_experience()
        assert "overall" in aar.weights
        assert 0 <= aar.weights["combat_effectiveness"] <= 1

    def test_room_change(self):
        from actualization_loop import RoomChange
        rc = RoomChange("lab", "agent1", "edit_script", "test.py",
                        "old code", "new code", "bug fix")
        assert rc.room_id == "lab"
        assert rc.agent == "agent1"
        msg = rc.to_commit_message()
        assert "edit_script" in msg
        assert "test.py" in msg

    def test_combat_script(self):
        from actualization_loop import CombatScript
        cs = CombatScript("test-script", "agent1")
        cs.add_rule("test fails", "investigate")
        action = cs.evaluate("test fails after deploy")
        assert action == "investigate"
        action_default = cs.evaluate("everything fine")
        assert action_default == "observe"

    @pytest.mark.asyncio
    async def test_cmd_gauges(self, handler, agent):
        await handler.cmd_gauges(agent, "")
        text = agent.writer.get_text()
        assert "GAUGE READINGS" in text
        assert "System Load" in text

    @pytest.mark.asyncio
    async def test_cmd_aar(self, handler, agent):
        await handler.cmd_aar(agent, "test-session")
        text = agent.writer.get_text()
        assert "After-Action Report" in text
        assert "test-session" in text
        assert "testagent" in text.lower() or "TestAgent" in text

    @pytest.mark.asyncio
    async def test_gauges_command_via_handle(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "gauges")
        text = agent.writer.get_text()
        assert "GAUGE READINGS" in text

    @pytest.mark.asyncio
    async def test_aar_command_via_handle(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "aar my-session")
        text = agent.writer.get_text()
        assert "After-Action Report" in text


# ═══════════════════════════════════════════════════════════════════════════
# 5. World initialization tests — verify modules wire up
# ═══════════════════════════════════════════════════════════════════════════

class TestWorldModuleWiring:

    def test_world_has_deckboss(self, world):
        assert hasattr(world, 'deckboss')
        # Should be initialized
        assert world.deckboss is not None

    def test_world_has_perception_systems(self, world):
        assert hasattr(world, 'jepa_optimizer')
        assert hasattr(world, 'opcode_breeder')
        assert world.jepa_optimizer is not None
        assert world.opcode_breeder is not None

    def test_world_deckboss_is_bridge(self, world):
        from deckboss_bridge import DeckBossBridge
        assert isinstance(world.deckboss, DeckBossBridge)

    def test_world_jepa_is_optimizer(self, world):
        from perception_room import JEPAOptimizer, OpcodeBreeder
        assert isinstance(world.jepa_optimizer, JEPAOptimizer)
        assert isinstance(world.opcode_breeder, OpcodeBreeder)


# ═══════════════════════════════════════════════════════════════════════════
# 6. MUDServer integration tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMUDServerIntegration:

    def test_server_has_gauge_monitor_attr(self):
        from server import MUDServer
        world = World(world_dir="/tmp/test_world_gauge")
        handler = CommandHandler(world)
        server = MUDServer(world, handler)
        assert hasattr(server, 'gauge_monitor')
        assert hasattr(server, '_gauge_poll_loop')

    def test_server_gauge_poll_loop_is_coroutine(self):
        from server import MUDServer
        import inspect
        assert inspect.iscoroutinefunction(MUDServer._gauge_poll_loop)

    def test_handler_has_gauge_monitor_getter(self):
        from server import CommandHandler
        assert hasattr(CommandHandler, '_get_gauge_monitor')
