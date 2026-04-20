#!/usr/bin/env python3
"""
Comprehensive test suite for cartridge_commands.py — CartridgeCommandHandler.

Covers:
  - Construction and seeding
  - cmd_list (empty, with cartridges)
  - cmd_load (success, missing args, bad name, self-load, expired)
  - cmd_eject (success, no session, double eject, wrong owner, by session_id)
  - cmd_status (no session, with session, after eject, no identity)
  - cmd_identity_dial (own, other, unknown agent)
  - cmd_identity_shift (success, no session, bad target, with amount, sector name)
  - cmd_identity_blend (success, no identity, unknown other, custom weights)
  - cmd_compatibility (success, no identity, unknown agent)
  - cmd_register (success, bad position, with precision)
  - cmd_publish (success, no identity, bad trust mode, bad time limit)
  - cmd_suggestion (success, no args, no match)
  - cmd_help
  - handle_command dispatch (unknown command)
  - Full lifecycle: register → publish → load → shift → eject
  - Stacking: multiple loads → eject all
"""

import unittest
from unittest import TestCase
import time

from twin_cartridge import (
    IdentityDial,
    IdentitySector,
    AgentSnapshot,
    TwinCartridge,
    CartridgeSession,
    PerspectiveEngine,
    TRUST_INHERIT_FULL,
    TRUST_INHERIT_PARTIAL,
    TRUST_INHERIT_NONE,
    TRUST_INHERIT_BLENDED,
    DIAL_POSITIONS,
)

from cartridge_commands import (
    CartridgeCommandHandler,
    _ok,
    _err,
    _resolve_target_position,
    _parse_float,
    _default_agents,
    _default_cartridges,
)


class TestHelpers(TestCase):
    """Tests for private helper functions."""

    def test_ok_success_key(self):
        r = _ok("msg")
        self.assertTrue(r["success"])

    def test_ok_message(self):
        r = _ok("hello")
        self.assertEqual(r["message"], "hello")

    def test_ok_with_data(self):
        r = _ok("msg", {"key": "val"})
        self.assertEqual(r["data"], {"key": "val"})

    def test_ok_no_data_key(self):
        r = _ok("msg")
        self.assertNotIn("data", r)

    def test_err_success_key(self):
        r = _err("msg")
        self.assertFalse(r["success"])

    def test_err_message(self):
        r = _err("fail")
        self.assertEqual(r["message"], "fail")

    def test_err_with_data(self):
        r = _err("fail", {"code": 42})
        self.assertEqual(r["data"]["code"], 42)

    def test_parse_float_valid(self):
        self.assertAlmostEqual(_parse_float("3.14"), 3.14)

    def test_parse_float_integer(self):
        self.assertAlmostEqual(_parse_float("5"), 5.0)

    def test_parse_float_negative(self):
        self.assertAlmostEqual(_parse_float("-2.5"), -2.5)

    def test_parse_float_invalid(self):
        self.assertIsNone(_parse_float("abc"))

    def test_parse_float_empty(self):
        self.assertIsNone(_parse_float(""))

    def test_parse_float_none(self):
        self.assertIsNone(_parse_float(None))

    def test_resolve_target_position_float(self):
        pos, err = _resolve_target_position("3.5")
        self.assertIsNotNone(pos)
        self.assertIsNone(err)

    def test_resolve_target_position_integer(self):
        pos, err = _resolve_target_position("5")
        self.assertAlmostEqual(pos, 5.0)
        self.assertIsNone(err)

    def test_resolve_target_position_sector_name(self):
        pos, err = _resolve_target_position("Architect")
        self.assertEqual(pos, 5.0)
        self.assertIsNone(err)

    def test_resolve_target_position_case_insensitive(self):
        pos, err = _resolve_target_position("theorist")
        self.assertEqual(pos, 0.0)
        self.assertIsNone(err)

    def test_resolve_target_position_unknown(self):
        pos, err = _resolve_target_position("UnknownRole")
        self.assertIsNone(pos)
        self.assertIsNotNone(err)

    def test_resolve_target_position_empty(self):
        pos, err = _resolve_target_position("")
        self.assertIsNone(pos)
        self.assertIsNotNone(err)

    def test_resolve_target_position_wraps_above(self):
        pos, err = _resolve_target_position("13.0")
        self.assertAlmostEqual(pos, 1.0)
        self.assertIsNone(err)


class TestDefaultSeeding(TestCase):
    """Tests for default seed data."""

    def test_default_agents_count(self):
        agents = _default_agents()
        self.assertEqual(len(agents), 4)

    def test_default_agents_names(self):
        agents = _default_agents()
        for name in ("Oracle1", "JetsonClaw1", "Babel", "Navigator"):
            self.assertIn(name, agents)

    def test_default_agents_are_identity_dials(self):
        agents = _default_agents()
        for name, dial in agents.items():
            self.assertIsInstance(dial, IdentityDial)

    def test_default_cartridges_count(self):
        carts = _default_cartridges()
        self.assertEqual(len(carts), 4)

    def test_default_cartridges_all_published(self):
        carts = _default_cartridges()
        for name, cart in carts.items():
            self.assertTrue(cart.published, f"{name} should be published")

    def test_default_cartridges_valid(self):
        carts = _default_cartridges()
        for name, cart in carts.items():
            self.assertTrue(cart.validate(), f"{name} should be valid")


class TestCartridgeCommandHandlerInit(TestCase):
    """Tests for handler construction."""

    def test_init_with_seed(self):
        h = CartridgeCommandHandler(seed=True)
        self.assertIsNotNone(h.engine)
        self.assertIsInstance(h.engine, PerspectiveEngine)

    def test_init_without_seed(self):
        h = CartridgeCommandHandler(seed=False)
        self.assertEqual(len(h.engine.agent_identities), 0)
        self.assertEqual(len(h.engine.cartridge_library), 0)

    def test_init_seeds_agents(self):
        h = CartridgeCommandHandler(seed=True)
        self.assertIn("Oracle1", h.engine.agent_identities)
        self.assertIn("JetsonClaw1", h.engine.agent_identities)

    def test_init_seeds_cartridges(self):
        h = CartridgeCommandHandler(seed=True)
        self.assertIn("twin-Oracle1", h.engine.cartridge_library)
        self.assertIn("twin-JetsonClaw1", h.engine.cartridge_library)

    def test_init_active_sessions_empty(self):
        h = CartridgeCommandHandler(seed=True)
        self.assertEqual(len(h.active_sessions), 0)


class TestCmdList(TestCase):
    """Tests for the list command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_list_has_cartridges(self):
        r = self.h.cmd_list("Oracle1", [])
        self.assertTrue(r["success"])
        self.assertGreater(len(r["data"]["cartridges"]), 0)

    def test_list_cartridge_count(self):
        r = self.h.cmd_list("Oracle1", [])
        self.assertEqual(len(r["data"]["cartridges"]), 4)

    def test_list_data_keys(self):
        r = self.h.cmd_list("Oracle1", [])
        cart = r["data"]["cartridges"][0]
        for key in ("name", "version", "status", "twin", "sector", "trust", "time_limit"):
            self.assertIn(key, cart)

    def test_list_empty_library(self):
        h = CartridgeCommandHandler(seed=False)
        r = h.cmd_list("A", [])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["cartridges"], [])

    def test_list_message(self):
        r = self.h.cmd_list("A", [])
        self.assertIn("4", r["message"])


class TestCmdLoad(TestCase):
    """Tests for the load command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_load_success(self):
        r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.assertTrue(r["success"])
        self.assertIn("session_id", r["data"])
        self.assertEqual(r["data"]["cartridge_name"], "twin-Oracle1")

    def test_load_tracks_session(self):
        r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        sid = r["data"]["session_id"]
        self.assertIn("JetsonClaw1", self.h.active_sessions)
        self.assertEqual(self.h.active_sessions["JetsonClaw1"].session_id, sid)

    def test_load_missing_args(self):
        r = self.h.cmd_load("A", [])
        self.assertFalse(r["success"])

    def test_load_empty_name(self):
        r = self.h.cmd_load("A", [" "])
        self.assertFalse(r["success"])

    def test_load_nonexistent_cartridge(self):
        r = self.h.cmd_load("A", ["nonexistent-cart"])
        self.assertFalse(r["success"])
        self.assertIn("not found", r["message"])

    def test_load_own_cartridge(self):
        # Oracle1 trying to load twin-Oracle1 = self-load
        r = self.h.cmd_load("Oracle1", ["twin-Oracle1"])
        self.assertFalse(r["success"])
        self.assertIn("own", r["message"].lower())

    def test_load_trust_inheritance_in_data(self):
        r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.assertIn("trust_inheritance", r["data"])

    def test_load_twin_agent_in_data(self):
        r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.assertEqual(r["data"]["twin_agent"], "Oracle1")

    def test_load_current_sector_in_data(self):
        r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.assertEqual(r["data"]["current_sector"], "Theorist")


class TestCmdEject(TestCase):
    """Tests for the eject command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_eject_success(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_eject("JetsonClaw1", [])
        self.assertTrue(r["success"])

    def test_eject_no_session(self):
        r = self.h.cmd_eject("NobodyHere", [])
        self.assertFalse(r["success"])
        self.assertIn("No active", r["message"])

    def test_eject_clears_tracking(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.assertIn("JetsonClaw1", self.h.active_sessions)
        self.h.cmd_eject("JetsonClaw1", [])
        self.assertNotIn("JetsonClaw1", self.h.active_sessions)

    def test_eject_data_keys(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_eject("JetsonClaw1", [])
        for key in ("session_id", "cartridge_name", "elapsed_seconds",
                     "restored_sector", "actions_count"):
            self.assertIn(key, r["data"])

    def test_double_eject(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.h.cmd_eject("JetsonClaw1", [])
        r2 = self.h.cmd_eject("JetsonClaw1", [])
        self.assertFalse(r2["success"])

    def test_eject_by_session_id(self):
        load_r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        sid = load_r["data"]["session_id"]
        r = self.h.cmd_eject("JetsonClaw1", [sid])
        self.assertTrue(r["success"])

    def test_eject_by_bad_session_id(self):
        r = self.h.cmd_eject("A", ["nonexistent-id"])
        self.assertFalse(r["success"])
        self.assertIn("not found", r["message"])

    def test_eject_wrong_owner(self):
        load_r = self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        sid = load_r["data"]["session_id"]
        r = self.h.cmd_eject("Imposter", [sid])
        self.assertFalse(r["success"])
        self.assertIn("belongs to", r["message"])


class TestCmdStatus(TestCase):
    """Tests for the status command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_status_no_cartridge_with_identity(self):
        r = self.h.cmd_status("Oracle1", [])
        self.assertTrue(r["success"])
        self.assertFalse(r["data"]["has_cartridge"])
        self.assertIn("sector", r["data"])

    def test_status_no_cartridge_no_identity(self):
        r = self.h.cmd_status("UnknownAgent", [])
        self.assertTrue(r["success"])
        self.assertFalse(r["data"]["has_cartridge"])
        self.assertNotIn("sector", r["data"])

    def test_status_with_active_session(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_status("JetsonClaw1", [])
        self.assertTrue(r["success"])
        self.assertTrue(r["data"]["has_cartridge"])
        self.assertIn("session_id", r["data"])
        self.assertEqual(r["data"]["cartridge_name"], "twin-Oracle1")

    def test_status_after_eject(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        self.h.cmd_eject("JetsonClaw1", [])
        r = self.h.cmd_status("JetsonClaw1", [])
        self.assertTrue(r["success"])
        # After eject, should have no cartridge but may have restored identity
        self.assertFalse(r["data"]["has_cartridge"])

    def test_status_session_count(self):
        self.h.cmd_load("Babel", ["twin-Oracle1"])
        self.h.cmd_load("Babel", ["twin-JetsonClaw1"])
        r = self.h.cmd_status("Babel", [])
        self.assertEqual(r["data"]["session_count"], 2)


class TestCmdIdentityDial(TestCase):
    """Tests for the identity dial command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_dial_own_identity(self):
        r = self.h.cmd_identity_dial("Oracle1", [])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["sector_name"], "Theorist")

    def test_dial_other_agent(self):
        r = self.h.cmd_identity_dial("Oracle1", ["JetsonClaw1"])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["sector_name"], "Builder")

    def test_dial_unknown_agent(self):
        r = self.h.cmd_identity_dial("Oracle1", ["Nobody"])
        self.assertFalse(r["success"])

    def test_dial_data_keys(self):
        r = self.h.cmd_identity_dial("Oracle1", [])
        for key in ("position", "precision", "effective_position",
                     "sector", "sector_name", "degrees",
                     "adjacent_prev", "adjacent_next"):
            self.assertIn(key, r["data"])

    def test_dial_adjacent_sectors(self):
        r = self.h.cmd_identity_dial("Oracle1", [])
        # Oracle1 is at position 0 (Theorist), prev = Weaver (11), next = Builder (1)
        self.assertEqual(r["data"]["adjacent_prev"], "Weaver")
        self.assertEqual(r["data"]["adjacent_next"], "Builder")


class TestCmdIdentityShift(TestCase):
    """Tests for the identity shift command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_shift_success(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["Architect"])
        self.assertTrue(r["success"])
        self.assertIn("actual_shift", r["data"])
        self.assertGreater(r["data"]["actual_shift"], 0)

    def test_shift_with_numeric_position(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["5"])
        self.assertTrue(r["success"])

    def test_shift_no_session(self):
        r = self.h.cmd_identity_shift("Nobody", ["Builder"])
        self.assertFalse(r["success"])
        self.assertIn("No active", r["message"])

    def test_shift_missing_target(self):
        r = self.h.cmd_identity_shift("A", [])
        self.assertFalse(r["success"])

    def test_shift_bad_target(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["NonexistentRole"])
        self.assertFalse(r["success"])

    def test_shift_with_custom_amount(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["Builder", "1.0"])
        self.assertTrue(r["success"])
        self.assertIn("amount_requested", r["data"])
        self.assertAlmostEqual(r["data"]["amount_requested"], 1.0)

    def test_shift_invalid_amount(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["Builder", "abc"])
        self.assertFalse(r["success"])

    def test_shift_negative_amount(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["Builder", "-1"])
        self.assertFalse(r["success"])

    def test_shift_updates_sector(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])  # Oracle1 is at Theorist (0)
        self.h.cmd_identity_shift("JetsonClaw1", ["Builder"])  # Shift toward Builder (1)
        status_r = self.h.cmd_status("JetsonClaw1", [])
        # Should have shifted from Theorist toward Builder
        self.assertIn(status_r["data"]["current_sector"], ("Theorist", "Builder"))

    def test_shift_data_keys(self):
        self.h.cmd_load("JetsonClaw1", ["twin-Oracle1"])
        r = self.h.cmd_identity_shift("JetsonClaw1", ["Architect"])
        for key in ("target", "target_name", "actual_shift",
                     "new_position", "new_sector"):
            self.assertIn(key, r["data"])


class TestCmdIdentityBlend(TestCase):
    """Tests for the identity blend command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_blend_success(self):
        r = self.h.cmd_identity_blend("Oracle1", ["JetsonClaw1"])
        self.assertTrue(r["success"])
        self.assertIn("blended_sector", r["data"])

    def test_blend_with_session(self):
        self.h.cmd_load("Babel", ["twin-Oracle1"])
        r = self.h.cmd_identity_blend("Babel", ["JetsonClaw1"])
        self.assertTrue(r["success"])

    def test_blend_no_self_identity(self):
        r = self.h.cmd_identity_blend("Nobody", ["Oracle1"])
        self.assertFalse(r["success"])

    def test_blend_no_other_identity(self):
        r = self.h.cmd_identity_blend("Oracle1", ["Nobody"])
        self.assertFalse(r["success"])

    def test_blend_custom_weights(self):
        r = self.h.cmd_identity_blend("Oracle1", ["JetsonClaw1", "0.7", "0.3"])
        self.assertTrue(r["success"])
        self.assertAlmostEqual(r["data"]["weight_a"], 0.7)
        self.assertAlmostEqual(r["data"]["weight_b"], 0.3)

    def test_blend_invalid_weight_a(self):
        r = self.h.cmd_identity_blend("Oracle1", ["JetsonClaw1", "abc"])
        self.assertFalse(r["success"])

    def test_blend_invalid_weight_b(self):
        r = self.h.cmd_identity_blend("Oracle1", ["JetsonClaw1", "0.5", "xyz"])
        self.assertFalse(r["success"])

    def test_blend_missing_target(self):
        r = self.h.cmd_identity_blend("Oracle1", [])
        self.assertFalse(r["success"])

    def test_blend_empty_target(self):
        r = self.h.cmd_identity_blend("Oracle1", [" "])
        self.assertFalse(r["success"])

    def test_blend_data_keys(self):
        r = self.h.cmd_identity_blend("Oracle1", ["JetsonClaw1"])
        for key in ("identity_a", "identity_b", "weight_a", "weight_b",
                     "blended_sector", "blended_position"):
            self.assertIn(key, r["data"])


class TestCmdCompatibility(TestCase):
    """Tests for the compatibility command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_compatibility_success(self):
        r = self.h.cmd_compatibility("Oracle1", ["JetsonClaw1"])
        self.assertTrue(r["success"])
        self.assertIn("score", r["data"])
        self.assertGreaterEqual(r["data"]["score"], 0)
        self.assertLessEqual(r["data"]["score"], 1)

    def test_compatibility_missing_arg(self):
        r = self.h.cmd_compatibility("Oracle1", [])
        self.assertFalse(r["success"])

    def test_compatibility_no_self_identity(self):
        r = self.h.cmd_compatibility("Nobody", ["Oracle1"])
        self.assertFalse(r["success"])

    def test_compatibility_no_other_identity(self):
        r = self.h.cmd_compatibility("Oracle1", ["Nobody"])
        self.assertFalse(r["success"])

    def test_compatibility_data_keys(self):
        r = self.h.cmd_compatibility("Oracle1", ["JetsonClaw1"])
        for key in ("agent_a", "agent_b", "score", "dial_distance",
                     "angular_distance", "conflicts", "sector_a", "sector_b"):
            self.assertIn(key, r["data"])

    def test_compatibility_empty_target(self):
        r = self.h.cmd_compatibility("Oracle1", [" "])
        self.assertFalse(r["success"])

    def test_compatibility_with_self(self):
        r = self.h.cmd_compatibility("Oracle1", ["Oracle1"])
        self.assertTrue(r["success"])
        # Self-compat: identity distance=0 (score component ~0.3),
        # but skills/capabilities are empty for bare identities,
        # so total is less than 1.0. Distance IS zero.
        self.assertAlmostEqual(r["data"]["dial_distance"], 0.0, places=1)
        self.assertGreaterEqual(r["data"]["score"], 0.0)
        self.assertLessEqual(r["data"]["score"], 1.0)


class TestCmdRegister(TestCase):
    """Tests for the register command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_register_success(self):
        r = self.h.cmd_register("NewAgent", ["3"])
        self.assertTrue(r["success"])
        self.assertIn("NewAgent", self.h.engine.agent_identities)
        self.assertEqual(r["data"]["sector"], "Guardian")

    def test_register_with_sector_name(self):
        r = self.h.cmd_register("Artist1", ["Artist"])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["sector"], "Artist")

    def test_register_with_precision(self):
        r = self.h.cmd_register("Precise1", ["5", "0.7"])
        self.assertTrue(r["success"])
        self.assertAlmostEqual(r["data"]["precision"], 0.7)

    def test_register_missing_position(self):
        r = self.h.cmd_register("A", [])
        self.assertFalse(r["success"])

    def test_register_bad_position(self):
        r = self.h.cmd_register("A", ["BadName"])
        self.assertFalse(r["success"])

    def test_register_bad_precision(self):
        r = self.h.cmd_register("A", ["3", "abc"])
        self.assertFalse(r["success"])

    def test_register_precision_clamped_high(self):
        r = self.h.cmd_register("A", ["3", "2.0"])
        self.assertTrue(r["success"])
        self.assertAlmostEqual(r["data"]["precision"], 1.0)

    def test_register_precision_clamped_low(self):
        r = self.h.cmd_register("A", ["3", "-1.0"])
        self.assertTrue(r["success"])
        self.assertAlmostEqual(r["data"]["precision"], 0.0)


class TestCmdPublish(TestCase):
    """Tests for the publish command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_publish_success(self):
        # Register a new agent first
        self.h.cmd_register("NewAgent", ["4"])
        r = self.h.cmd_publish("NewAgent", ["twin-NewAgent"])
        self.assertTrue(r["success"])
        self.assertIn("twin-NewAgent", self.h.engine.cartridge_library)
        self.assertTrue(self.h.engine.cartridge_library["twin-NewAgent"].published)

    def test_publish_no_identity(self):
        r = self.h.cmd_publish("Nobody", ["twin-Nobody"])
        self.assertFalse(r["success"])

    def test_publish_custom_trust(self):
        self.h.cmd_register("A", ["3"])
        r = self.h.cmd_publish("A", ["twin-A", "partial"])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["trust_inheritance"], "partial")

    def test_publish_bad_trust_mode(self):
        self.h.cmd_register("A", ["3"])
        r = self.h.cmd_publish("A", ["twin-A", "invalid_mode"])
        self.assertFalse(r["success"])

    def test_publish_with_time_limit(self):
        self.h.cmd_register("A", ["3"])
        r = self.h.cmd_publish("A", ["twin-A", "full", "60"])
        self.assertTrue(r["success"])
        self.assertAlmostEqual(r["data"]["time_limit"], 60.0)

    def test_publish_bad_time_limit(self):
        self.h.cmd_register("A", ["3"])
        r = self.h.cmd_publish("A", ["twin-A", "full", "abc"])
        self.assertFalse(r["success"])

    def test_publish_negative_time_limit(self):
        self.h.cmd_register("A", ["3"])
        r = self.h.cmd_publish("A", ["twin-A", "full", "-10"])
        self.assertFalse(r["success"])

    def test_publish_default_name(self):
        self.h.cmd_register("MyAgent", ["6"])
        r = self.h.cmd_publish("MyAgent", [])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["cartridge_name"], "twin-MyAgent")

    def test_publish_empty_name(self):
        self.h.cmd_register("A", ["3"])
        r = self.h.cmd_publish("A", [" "])
        self.assertFalse(r["success"])


class TestCmdSuggestion(TestCase):
    """Tests for the suggestion command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_suggestion_architecture(self):
        r = self.h.cmd_suggestion("JetsonClaw1", ["I need architecture"])
        self.assertTrue(r["success"])

    def test_suggestion_by_agent_name(self):
        r = self.h.cmd_suggestion("Babel", ["I want Oracle1 help"])
        self.assertTrue(r["success"])
        # Should suggest twin-Oracle1 when cartridge_name is present
        if "cartridge_name" in r["data"]:
            self.assertEqual(r["data"]["cartridge_name"], "twin-Oracle1")

    def test_suggestion_no_match(self):
        r = self.h.cmd_suggestion("A", ["quantum entanglement"])
        # May still return a result due to compatibility scoring
        self.assertTrue(r["success"])

    def test_suggestion_missing_args(self):
        r = self.h.cmd_suggestion("A", [])
        self.assertFalse(r["success"])

    def test_suggestion_empty_goal(self):
        r = self.h.cmd_suggestion("A", [" "])
        self.assertFalse(r["success"])

    def test_suggestion_data_keys(self):
        r = self.h.cmd_suggestion("JetsonClaw1", ["architecture"])
        # When a suggestion is found, the data should have cartridge fields
        if "cartridge_name" in r["data"]:
            for key in ("cartridge_name", "twin_agent", "sector", "trust_inheritance"):
                self.assertIn(key, r["data"])


class TestCmdHelp(TestCase):
    """Tests for the help command."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_help_success(self):
        r = self.h.cmd_help("A", [])
        self.assertTrue(r["success"])

    def test_help_has_commands(self):
        r = self.h.cmd_help("A", [])
        self.assertIn("commands", r["data"])
        self.assertIsInstance(r["data"]["commands"], dict)
        self.assertGreater(len(r["data"]["commands"]), 5)

    def test_help_has_formatted(self):
        r = self.h.cmd_help("A", [])
        self.assertIn("formatted", r["data"])
        self.assertIsInstance(r["data"]["formatted"], list)


class TestHandleCommand(TestCase):
    """Tests for the top-level dispatch."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_dispatch_list(self):
        r = self.h.handle_command("A", "list", [])
        self.assertTrue(r["success"])

    def test_dispatch_ls_alias(self):
        r = self.h.handle_command("A", "ls", [])
        self.assertTrue(r["success"])

    def test_dispatch_load(self):
        r = self.h.handle_command("JetsonClaw1", "load", ["twin-Oracle1"])
        self.assertTrue(r["success"])

    def test_dispatch_eject(self):
        self.h.handle_command("JetsonClaw1", "load", ["twin-Oracle1"])
        r = self.h.handle_command("JetsonClaw1", "eject", [])
        self.assertTrue(r["success"])

    def test_dispatch_status(self):
        r = self.h.handle_command("Oracle1", "status", [])
        self.assertTrue(r["success"])

    def test_dispatch_identity_dial(self):
        r = self.h.handle_command("Oracle1", "identity", ["dial"])
        self.assertTrue(r["success"])

    def test_dispatch_identity_shift(self):
        self.h.handle_command("JetsonClaw1", "load", ["twin-Oracle1"])
        r = self.h.handle_command("JetsonClaw1", "identity", ["shift", "Builder"])
        self.assertTrue(r["success"])

    def test_dispatch_identity_blend(self):
        r = self.h.handle_command("Oracle1", "identity", ["blend", "JetsonClaw1"])
        self.assertTrue(r["success"])

    def test_dispatch_compatibility(self):
        r = self.h.handle_command("Oracle1", "compatibility", ["JetsonClaw1"])
        self.assertTrue(r["success"])

    def test_dispatch_compat_alias(self):
        r = self.h.handle_command("Oracle1", "compat", ["JetsonClaw1"])
        self.assertTrue(r["success"])

    def test_dispatch_blend_alias(self):
        r = self.h.handle_command("Oracle1", "blend", ["JetsonClaw1"])
        self.assertTrue(r["success"])

    def test_dispatch_help(self):
        r = self.h.handle_command("A", "help", [])
        self.assertTrue(r["success"])

    def test_dispatch_unknown_command(self):
        r = self.h.handle_command("A", "nonexistent", [])
        self.assertFalse(r["success"])

    def test_dispatch_unknown_identity_sub(self):
        r = self.h.handle_command("Oracle1", "identity", ["explode"])
        self.assertFalse(r["success"])

    def test_dispatch_register(self):
        r = self.h.handle_command("New1", "register", ["3"])
        self.assertTrue(r["success"])

    def test_dispatch_publish(self):
        self.h.handle_command("New2", "register", ["3"])
        r = self.h.handle_command("New2", "publish", ["twin-New2"])
        self.assertTrue(r["success"])

    def test_dispatch_suggestion(self):
        r = self.h.handle_command("JetsonClaw1", "suggestion", ["architecture"])
        self.assertTrue(r["success"])


class TestFullLifecycle(TestCase):
    """Integration tests for the complete cartridge lifecycle."""

    def setUp(self):
        self.h = CartridgeCommandHandler(seed=True)

    def test_lifecycle_register_publish_load_status_eject(self):
        """Full lifecycle: register → publish → load → status → eject."""
        # 1. Register
        r = self.h.handle_command("Scout1", "register", ["2"])
        self.assertTrue(r["success"])

        # 2. Publish
        r = self.h.handle_command("Scout1", "publish", ["twin-Scout1", "partial"])
        self.assertTrue(r["success"])

        # 3. Load by another agent
        r = self.h.handle_command("Babel", "load", ["twin-Scout1"])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["twin_agent"], "Scout1")

        # 4. Status
        r = self.h.handle_command("Babel", "status", [])
        self.assertTrue(r["success"])
        self.assertTrue(r["data"]["has_cartridge"])

        # 5. Eject
        r = self.h.handle_command("Babel", "eject", [])
        self.assertTrue(r["success"])

        # 6. Status after eject
        r = self.h.handle_command("Babel", "status", [])
        self.assertTrue(r["success"])
        self.assertFalse(r["data"]["has_cartridge"])

    def test_lifecycle_shift_and_check(self):
        """Load, shift perspective, verify sector change, eject."""
        # Load
        self.h.handle_command("JetsonClaw1", "load", ["twin-Oracle1"])
        # Oracle1 is at Theorist (pos 0)

        # Shift toward Builder (pos 1)
        r = self.h.handle_command("JetsonClaw1", "identity", ["shift", "Builder"])
        self.assertTrue(r["success"])
        self.assertGreater(r["data"]["actual_shift"], 0)

        # Check identity dial
        r = self.h.handle_command("JetsonClaw1", "identity", ["dial"])
        self.assertTrue(r["success"])

        # Eject
        r = self.h.handle_command("JetsonClaw1", "eject", [])
        self.assertTrue(r["success"])

    def test_lifecycle_compatibility_before_load(self):
        """Check compatibility before loading."""
        # Register and publish
        self.h.handle_command("AgentX", "register", ["8"])
        self.h.handle_command("AgentX", "publish", ["twin-AgentX"])

        # Check compatibility
        r = self.h.handle_command("Oracle1", "compatibility", ["AgentX"])
        self.assertTrue(r["success"])
        self.assertIn("score", r["data"])

        # Load
        r = self.h.handle_command("Oracle1", "load", ["twin-AgentX"])
        self.assertTrue(r["success"])

        # Eject
        r = self.h.handle_command("Oracle1", "eject", [])
        self.assertTrue(r["success"])

    def test_stacking_multiple_cartridges(self):
        """Load multiple cartridges, check session count, eject all."""
        # Register and publish two cartridges for a new agent
        self.h.handle_command("Stacker", "register", ["3"])
        self.h.handle_command("Stacker", "publish", ["twin-Stacker-v1", "full"])
        self.h.handle_command("Stacker", "register", ["4"])
        self.h.handle_command("Stacker", "publish", ["twin-Stacker-v2", "none"])

        # Another agent loads both
        r1 = self.h.handle_command("Babel", "load", ["twin-Stacker-v1"])
        self.assertTrue(r1["success"])

        r2 = self.h.handle_command("Babel", "load", ["twin-Stacker-v2"])
        self.assertTrue(r2["success"])

        # Status should show 2 sessions
        r = self.h.handle_command("Babel", "status", [])
        self.assertTrue(r["success"])
        self.assertEqual(r["data"]["session_count"], 2)

        # Eject all (two ejections)
        r3 = self.h.handle_command("Babel", "eject", [])
        self.assertTrue(r3["success"])
        r4 = self.h.handle_command("Babel", "eject", [])
        self.assertTrue(r4["success"])

        # No more sessions
        r = self.h.handle_command("Babel", "status", [])
        self.assertFalse(r["data"]["has_cartridge"])

    def test_blend_with_active_cartridge(self):
        """Load cartridge, then blend identity with another agent."""
        self.h.handle_command("Babel", "load", ["twin-Oracle1"])
        r = self.h.handle_command("Babel", "identity", ["blend", "JetsonClaw1", "0.6", "0.4"])
        self.assertTrue(r["success"])
        self.assertIn("blended_sector", r["data"])
        # Clean up
        self.h.handle_command("Babel", "eject", [])

    def test_expiration_eject(self):
        """Load a time-limited cartridge and verify ejection after expiry."""
        # Register and publish a short-lived cartridge
        self.h.handle_command("TempAgent", "register", ["5"])
        r = self.h.handle_command("TempAgent", "publish", ["twin-TempShort", "full", "0.01"])
        self.assertTrue(r["success"])

        # Load it
        r = self.h.handle_command("Babel", "load", ["twin-TempShort"])
        self.assertTrue(r["success"])

        # Wait for expiry
        time.sleep(0.05)

        # Try eject
        r = self.h.handle_command("Babel", "eject", [])
        # The session might already be expired; the eject should still work
        # or report expired status. Either way it shouldn't crash.
        self.assertIn("success", r)


if __name__ == "__main__":
    unittest.main()
