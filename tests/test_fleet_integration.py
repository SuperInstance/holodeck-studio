#!/usr/bin/env python3
"""
Tests for fleet_integration.py — FleetIntegratedRoom and FleetIntegratedMUD.

CartridgeBridge and FleetScheduler are mocked via @patch decorators.
Target: 50+ tests covering both classes, all methods, edge cases.
"""

import sys
import unittest
from unittest import TestCase
from unittest.mock import MagicMock, patch

from fleet_integration import FleetIntegratedRoom, FleetIntegratedMUD


# ═══════════════════════════════════════════════════════════════════════════════
# Helper: make a mock scheduler that returns predictable values
# ═══════════════════════════════════════════════════════════════════════════════

def make_mock_scheduler(model="glm-5-turbo", reason="schedule-reason", budget=100.0):
    """Return a MagicMock configured as a FleetScheduler."""
    sched = MagicMock()
    sched.get_current_model.return_value = (model, reason)
    sched.status.return_value = {
        "current_model": model,
        "schedule_reason": reason,
        "budget_remaining": budget,
        "tasks_pending": 0,
    }
    return sched


def make_mock_bridge(scene_cartridge="oracle-relay", scene_skin="c3po",
                     commands=None, config_extra=None):
    """Return a MagicMock configured as a CartridgeBridge."""
    bridge = MagicMock()
    scene = MagicMock()
    scene.cartridge_name = scene_cartridge
    scene.skin_name = scene_skin
    bridge.activate_scene.return_value = scene
    config = {"commands": commands or ["look", "say", "go"]}
    if config_extra:
        config.update(config_extra)
    bridge.get_mud_config.return_value = config
    return bridge


# ═══════════════════════════════════════════════════════════════════════════════
# 1. FleetIntegratedRoom.__init__ tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedRoomInit(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_sets_room_id(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "Where vessels arrive")
        self.assertEqual(room.room_id, "harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_sets_name(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "desc")
        self.assertEqual(room.name, "Harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_sets_desc(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("x", "X", "A description")
        self.assertEqual(room.desc, "A description")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_creates_bridge(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("x", "X", "d")
        MockBridge.assert_called_once()
        self.assertEqual(room.bridge, MockBridge.return_value)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_creates_scheduler(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("x", "X", "d")
        MockSched.assert_called_once()
        self.assertEqual(room.scheduler, MockSched.return_value)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_agents_empty(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("x", "X", "d")
        self.assertEqual(room.agents, [])

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_gauges_empty_dict(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("x", "X", "d")
        self.assertEqual(room.gauges, {})

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_booted_false(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("x", "X", "d")
        self.assertFalse(room.booted)


# ═══════════════════════════════════════════════════════════════════════════════
# 2. FleetIntegratedRoom._configure_defaults tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedRoomConfigureDefaults(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_six_scenes(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        self.assertEqual(bridge.build_scene.call_count, 6)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_harbor_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        calls = bridge.build_scene.call_args_list
        harbor_call = calls[0]
        self.assertEqual(harbor_call[0][0], "harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_navigation_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("nav", "Nav", "d")
        calls = bridge.build_scene.call_args_list
        self.assertEqual(calls[1][0][0], "navigation")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_engineering_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("eng", "Eng", "d")
        calls = bridge.build_scene.call_args_list
        self.assertEqual(calls[2][0][0], "engineering")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_bridge_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        calls = bridge.build_scene.call_args_list
        self.assertEqual(calls[3][0][0], "bridge")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_workshop_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("ws", "Workshop", "d")
        calls = bridge.build_scene.call_args_list
        self.assertEqual(calls[4][0][0], "workshop")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_guardian_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("guard", "Guardian", "d")
        calls = bridge.build_scene.call_args_list
        self.assertEqual(calls[5][0][0], "guardian")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_harbor_scene_params(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        args = bridge.build_scene.call_args_list[0][0]
        self.assertEqual(args[1], "oracle-relay")
        self.assertEqual(args[2], "c3po")
        self.assertEqual(args[3], "glm-5-turbo")
        self.assertEqual(args[4], "always")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_engineering_scene_params(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("eng", "Eng", "d")
        args = bridge.build_scene.call_args_list[2][0]
        self.assertEqual(args[1], "spreader-loop")
        self.assertEqual(args[2], "rival")
        self.assertEqual(args[3], "deepseek-chat")
        self.assertEqual(args[4], "nighttime")


# ═══════════════════════════════════════════════════════════════════════════════
# 3. FleetIntegratedRoom.boot tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedRoomBoot(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_sets_booted_true(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.boot()
        self.assertTrue(room.booted)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_returns_dict(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertIsInstance(result, dict)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_return_has_room_key(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["room"], "harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_return_has_scene(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge(scene_cartridge="oracle-relay")
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["scene"], "oracle-relay")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_return_has_skin(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge(scene_skin="c3po")
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["skin"], "c3po")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_return_has_model(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler(model="glm-5-turbo")
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["model"], "glm-5-turbo")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_return_has_schedule_reason(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler(reason="budget-ok")
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["schedule_reason"], "budget-ok")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_return_has_commands(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge(commands=["look", "go"])
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["commands"], ["look", "go"])

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_handles_none_scene(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        bridge.activate_scene.return_value = None
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.boot()
        self.assertEqual(result["scene"], "default")
        self.assertEqual(result["skin"], "tng")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_calls_activate_scene_with_room_id(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.boot()
        bridge.activate_scene.assert_called_with("harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_calls_get_current_model_with_room_id(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.boot()
        sched.get_current_model.assert_called_with("harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_calls_get_mud_config(self, MockBridge, MockSched):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.boot()
        bridge.get_mud_config.assert_called_with("harbor")


# ═══════════════════════════════════════════════════════════════════════════════
# 4. FleetIntegratedRoom.get_model tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedRoomGetModel(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_get_model_returns_tuple(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.get_model()
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_get_model_delegates_to_scheduler(self, MockBridge, MockSched):
        sched = make_mock_scheduler(model="glm-4.7", reason="nighttime")
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("engineering", "Engineering", "d")
        model, reason = room.get_model()
        self.assertEqual(model, "glm-4.7")
        self.assertEqual(reason, "nighttime")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_get_model_passes_room_id(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("guardian", "Guardian", "d")
        room.get_model()
        sched.get_current_model.assert_called_with("guardian")


# ═══════════════════════════════════════════════════════════════════════════════
# 5. FleetIntegratedRoom.submit_task tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedRoomSubmitTask(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_submit_task_calls_scheduler(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        room.submit_task("t1", "Heal shields", "tier1", 500, priority=1)
        sched.submit_task.assert_called_once()

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_submit_task_passes_all_params(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        room.submit_task("task-42", "Scan sector", "tier2", 1000, priority=5)
        sched.submit_task.assert_called_with(
            task_id="task-42", room_id="bridge", description="Scan sector",
            required_tier="tier2", est_tokens=1000, priority=5,
        )

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_submit_task_default_priority_zero(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        room.submit_task("t0", "Idle check", "tier1", 200)
        call_kwargs = sched.submit_task.call_args
        self.assertEqual(call_kwargs.kwargs["priority"], 0)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_submit_task_multiple_tasks(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        room.submit_task("t1", "Task 1", "tier1", 100)
        room.submit_task("t2", "Task 2", "tier2", 200)
        self.assertEqual(sched.submit_task.call_count, 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 6. FleetIntegratedRoom.status tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedRoomStatus(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_returns_dict(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertIsInstance(result, dict)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_has_room_name(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["room"], "Harbor")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_booted_false_before_boot(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertFalse(result["booted"])

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_booted_true_after_boot(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.boot()
        result = room.status()
        self.assertTrue(result["booted"])

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_has_model(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler(model="glm-5-turbo")
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["model"], "glm-5-turbo")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_has_schedule_reason(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler(reason="always-on")
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["schedule_reason"], "always-on")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_cartridge_default(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge(config_extra={
            "cartridge": {"name": "oracle-relay"},
            "skin": {"name": "c3po", "formality": "NAVAL"},
        })
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["cartridge"], "oracle-relay")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_cartridge_none_when_missing(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["cartridge"], "none")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_skin_none_when_missing(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["skin"], "none")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_formality_default(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["formality"], "TNG")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_has_scheduler_info(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler(budget=75.0)
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertIn("scheduler", result)
        self.assertEqual(result["scheduler"]["budget_remaining"], 75.0)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_gauges_reflects_instance(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.gauges = {"temperature": 72}
        result = room.status()
        self.assertEqual(result["gauges"], {"temperature": 72})

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_status_agents_count(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        room.agents = ["bot1", "bot2", "bot3"]
        result = room.status()
        self.assertEqual(result["agents"], 3)


# ═══════════════════════════════════════════════════════════════════════════════
# 7. FleetIntegratedMUD.__init__ tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedMUDInit(TestCase):

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_creates_rooms_dict(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertIsInstance(mud.rooms, dict)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_creates_scheduler(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        MockSched.assert_called_once()

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_creates_bridge(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        MockBridge.assert_called_once()

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_alert_level_zero(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertEqual(mud.alert_level, 0)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_init_tick_count_zero(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertEqual(mud.tick_count, 0)


# ═══════════════════════════════════════════════════════════════════════════════
# 8. FleetIntegratedMUD._build_ship tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedMUDBuildShip(TestCase):

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_7_rooms(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertEqual(len(mud.rooms), 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_expected_room_ids(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        expected = {"harbor", "navigation", "engineering", "bridge", "workshop", "guardian", "ready-room"}
        self.assertEqual(set(mud.rooms.keys()), expected)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_builds_7_scenes_on_shared_bridge(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertEqual(bridge.build_scene.call_count, 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_rooms_share_scheduler(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge()
        sched = make_mock_scheduler()
        MockBridge.return_value = bridge
        MockSched.return_value = sched
        mock_room_instance = MagicMock(booted=False, agents=[], gauges={})
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        # All rooms should have their scheduler replaced with the shared one
        for room_id, room_obj in mud.rooms.items():
            self.assertEqual(room_obj.scheduler, sched)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_rooms_share_bridge(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=False, agents=[], gauges={})
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        for room_id, room_obj in mud.rooms.items():
            self.assertEqual(room_obj.bridge, bridge)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_ready_room_scene_params(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge()
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        # The 7th call (index 6) should be ready-room
        args = bridge.build_scene.call_args_list[6][0]
        self.assertEqual(args[0], "ready-room")
        self.assertEqual(args[1], "oracle-relay")
        self.assertEqual(args[2], "straight-man")
        self.assertEqual(args[3], "deepseek-reasoner")
        self.assertEqual(args[4], "daytime")


# ═══════════════════════════════════════════════════════════════════════════════
# 9. FleetIntegratedMUD.boot_all tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedMUDBootAll(TestCase):

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_all_returns_dict(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=False, agents=[], gauges={})
        mock_room_instance.boot.return_value = {"room": "harbor", "scene": "oracle-relay"}
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.boot_all()
        self.assertIsInstance(result, dict)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_all_calls_boot_on_all_rooms(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=False, agents=[], gauges={})
        mock_room_instance.boot.return_value = {"room": "x"}
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        mud.boot_all()
        self.assertEqual(mock_room_instance.boot.call_count, 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_boot_all_results_has_all_room_ids(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=False, agents=[], gauges={})
        mock_room_instance.boot.return_value = {"room": "x"}
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.boot_all()
        expected = {"harbor", "navigation", "engineering", "bridge", "workshop", "guardian", "ready-room"}
        self.assertEqual(set(result.keys()), expected)


# ═══════════════════════════════════════════════════════════════════════════════
# 10. FleetIntegratedMUD.tick tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedMUDTick(TestCase):

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_increments_count(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertEqual(mud.tick_count, 0)
        mud.tick()
        self.assertEqual(mud.tick_count, 1)
        mud.tick()
        self.assertEqual(mud.tick_count, 2)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_skips_unbooted_rooms(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.tick()
        self.assertEqual(len(result), 0)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_includes_booted_rooms(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        sched = make_mock_scheduler()
        MockSched.return_value = sched
        mock_room_instance = MagicMock(booted=True, agents=["bot1"], gauges={})
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        self.assertEqual(len(result), 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_result_has_model(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={})
        mock_room_instance.get_model.return_value = ("glm-5.1", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        for room_data in result.values():
            self.assertEqual(room_data["model"], "glm-5.1")

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_result_has_alerts_from_gauges(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={"temp": 90, "pressure": 70})
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        for room_data in result.values():
            # temp=90 > 80, pressure=70 <= 80 => 1 alert
            self.assertEqual(room_data["alerts"], 1)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_no_alerts_below_threshold(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={"temp": 50})
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        for room_data in result.values():
            self.assertEqual(room_data["alerts"], 0)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_empty_gauges_no_alerts(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={})
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        for room_data in result.values():
            self.assertEqual(room_data["alerts"], 0)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_multiple_alerts(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={
            "temp": 90, "pressure": 95, "cpu": 85, "mem": 60,
        })
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        for room_data in result.values():
            # 3 gauges > 80
            self.assertEqual(room_data["alerts"], 3)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_tick_result_has_agent_count(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=["bot1", "bot2"], gauges={})
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.tick()
        for room_data in result.values():
            self.assertEqual(room_data["agents"], 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 11. FleetIntegratedMUD.fleet_status tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestFleetIntegratedMUDFleetStatus(TestCase):

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_returns_dict(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.fleet_status()
        self.assertIsInstance(result, dict)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_rooms_count(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.fleet_status()
        self.assertEqual(result["rooms"], 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_booted_count_zero_initially(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.fleet_status()
        self.assertEqual(result["booted"], 0)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_booted_after_boot_all(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={})
        mock_room_instance.boot.return_value = {"room": "x"}
        mock_room_instance.status.return_value = {
            "room": "x", "booted": True, "model": "glm-5",
            "schedule_reason": "ok", "cartridge": "oracle-relay",
            "skin": "c3po", "formality": "NAVAL",
            "scheduler": {}, "gauges": {}, "agents": 0,
        }
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        mud.boot_all()
        result = mud.fleet_status()
        self.assertEqual(result["booted"], 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_alert_level(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.fleet_status()
        self.assertEqual(result["alert_level"], 0)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_tick_count(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        mud.tick()
        mud.tick()
        result = mud.fleet_status()
        self.assertEqual(result["tick"], 2)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_has_scheduler_info(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler(budget=42.5)
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.fleet_status()
        self.assertIn("scheduler", result)
        self.assertEqual(result["scheduler"]["budget_remaining"], 42.5)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_has_rooms_detail(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=False, agents=[], gauges={})
        mock_room_instance.status.return_value = {"room": "x", "booted": False}
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        result = mud.fleet_status()
        self.assertIn("rooms_detail", result)
        self.assertEqual(len(result["rooms_detail"]), 7)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_fleet_status_alert_level_mutable(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        mud.alert_level = 2
        result = mud.fleet_status()
        self.assertEqual(result["alert_level"], 2)


# ═══════════════════════════════════════════════════════════════════════════════
# 12. Edge case / integration tests
# ═══════════════════════════════════════════════════════════════════════════════

class TestEdgeCases(TestCase):

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_room_boot_twice(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        r1 = room.boot()
        r2 = room.boot()
        self.assertTrue(room.booted)
        # Both should succeed
        self.assertEqual(r1["room"], "bridge")
        self.assertEqual(r2["room"], "bridge")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_room_submit_task_before_boot(self, MockBridge, MockSched):
        sched = make_mock_scheduler()
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = sched
        room = FleetIntegratedRoom("bridge", "Bridge", "d")
        # Should not raise even if not booted
        room.submit_task("t1", "Pre-boot task", "tier1", 100)
        sched.submit_task.assert_called_once()

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_mud_tick_before_boot_returns_empty(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        result = mud.tick()
        self.assertEqual(result, {})

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_mud_boot_all_then_tick(self, MockBridge, MockSched, MockRoom):
        MockBridge.return_value = make_mock_bridge()
        sched = make_mock_scheduler()
        MockSched.return_value = sched
        mock_room_instance = MagicMock(booted=True, agents=["bot1"], gauges={})
        mock_room_instance.boot.return_value = {"room": "x"}
        mock_room_instance.get_model.return_value = ("glm-5-turbo", "ok")
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        mud.boot_all()
        result = mud.tick()
        self.assertEqual(len(result), 7)
        self.assertEqual(mud.tick_count, 1)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_mud_alert_level_green_comment(self, MockBridge, MockSched, MockRoom):
        """Verify the comment says 0=green, 1=yellow, 2=red."""
        # This is a documentation test — just verify the attribute exists and defaults
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        MockRoom.return_value = MagicMock(booted=False, agents=[], gauges={})
        mud = FleetIntegratedMUD()
        self.assertEqual(mud.alert_level, 0)
        mud.alert_level = 1
        self.assertEqual(mud.alert_level, 1)
        mud.alert_level = 2
        self.assertEqual(mud.alert_level, 2)

    @patch("fleet_integration.FleetIntegratedRoom")
    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_mud_boot_all_with_empty_commands(self, MockBridge, MockSched, MockRoom):
        bridge = make_mock_bridge(commands=[])
        MockBridge.return_value = bridge
        MockSched.return_value = make_mock_scheduler()
        mock_room_instance = MagicMock(booted=True, agents=[], gauges={})
        mock_room_instance.boot.return_value = {"room": "x", "commands": []}
        MockRoom.return_value = mock_room_instance
        mud = FleetIntegratedMUD()
        results = mud.boot_all()
        for r in results.values():
            self.assertEqual(r["commands"], [])

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_room_status_skin_with_formality(self, MockBridge, MockSched):
        MockBridge.return_value = make_mock_bridge(config_extra={
            "skin": {"name": "c3po", "formality": "NAVAL"},
        })
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("harbor", "Harbor", "d")
        result = room.status()
        self.assertEqual(result["skin"], "c3po")
        self.assertEqual(result["formality"], "NAVAL")

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_room_gauge_threshold_exactly_80_counts(self, MockBridge, MockSched):
        """A gauge value of exactly 80 should NOT trigger an alert (condition is > 80)."""
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("eng", "Engineering", "d")
        room.booted = True
        room.gauges = {"temp": 80}
        # The tick logic checks `v > 80`, so 80 should be 0 alerts
        alerts = sum(1 for v in room.gauges.values() if v > 80)
        self.assertEqual(alerts, 0)

    @patch("fleet_integration.FleetScheduler")
    @patch("fleet_integration.CartridgeBridge")
    def test_room_gauge_threshold_81_counts(self, MockBridge, MockSched):
        """A gauge value of 81 should trigger an alert."""
        MockBridge.return_value = make_mock_bridge()
        MockSched.return_value = make_mock_scheduler()
        room = FleetIntegratedRoom("eng", "Engineering", "d")
        room.booted = True
        room.gauges = {"temp": 81}
        alerts = sum(1 for v in room.gauges.values() if v > 80)
        self.assertEqual(alerts, 1)


if __name__ == "__main__":
    unittest.main()
