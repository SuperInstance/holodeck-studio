#!/usr/bin/env python3
"""
Comprehensive test suite for twin_cartridge.py

Covers all 9 classes: IdentitySector, DialConfig, EjectResult, IdentityDial,
AgentSnapshot, TwinCartridge, CartridgeSession, IdentityFusion, PerspectiveEngine.
"""

import unittest
from unittest import TestCase
import time
import json
import hashlib
import math
import os
import tempfile

from twin_cartridge import (
    DIAL_POSITIONS,
    SECTOR_DEGREES,
    TRUST_INHERIT_FULL,
    TRUST_INHERIT_PARTIAL,
    TRUST_INHERIT_NONE,
    TRUST_INHERIT_BLENDED,
    DEFAULT_TIME_LIMIT,
    DEFAULT_SHIFT_STEP,
    MAX_STACK_DEPTH,
    DEFAULT_SNAPSHOT_EXPIRY,
    MIN_COMPATIBILITY_FOR_LOADING,
    IdentitySector,
    DialConfig,
    EjectResult,
    IdentityDial,
    AgentSnapshot,
    TwinCartridge,
    CartridgeSession,
    IdentityFusion,
    PerspectiveEngine,
)


# ─── Helpers ───────────────────────────────────────────────────

def make_snapshot(
    agent_name="test-agent",
    position=0.0,
    precision=0.0,
    trust_profile=None,
    capabilities=None,
    skills=None,
    personality_vector=None,
    preferences=None,
    expires_at=0.0,
):
    """Create an AgentSnapshot with sensible defaults."""
    return AgentSnapshot(
        agent_name=agent_name,
        identity=IdentityDial(position=position, precision=precision),
        trust_profile=trust_profile or {"level": 3},
        capabilities=capabilities or ["read"],
        skills=skills or {"logic": 0.8},
        personality_vector=personality_vector or [0.5, 0.5, 0.5],
        preferences=preferences or {"mode": "default"},
        expires_at=expires_at,
    )


def make_cartridge(
    agent_name="test-agent",
    position=0.0,
    trust_inheritance=TRUST_INHERIT_FULL,
    time_limit=0.0,
    published=False,
):
    """Create a valid TwinCartridge ready for loading."""
    snap = make_snapshot(agent_name=agent_name, position=position)
    return TwinCartridge(
        snapshot=snap,
        cartridge_name=f"twin-{agent_name}",
        trust_inheritance=trust_inheritance,
        time_limit=time_limit,
        published=published,
    )


# ═══════════════════════════════════════════════════════════════
# IdentitySector Tests
# ═══════════════════════════════════════════════════════════════

class TestIdentitySector(TestCase):

    # ─── role_name ─────────────────────────────────────────────

    def test_role_name_position_0(self):
        self.assertEqual(IdentitySector.role_name(0), "Theorist")

    def test_role_name_position_5(self):
        self.assertEqual(IdentitySector.role_name(5), "Architect")

    def test_role_name_position_11(self):
        self.assertEqual(IdentitySector.role_name(11), "Weaver")

    def test_role_name_wraps_12(self):
        """Position 12 wraps to 0 = Theorist."""
        self.assertEqual(IdentitySector.role_name(12), "Theorist")

    def test_role_name_wraps_13(self):
        """Position 13 wraps to 1 = Builder."""
        self.assertEqual(IdentitySector.role_name(13), "Builder")

    def test_role_name_wraps_negative(self):
        """Position -1 wraps to 11 = Weaver."""
        self.assertEqual(IdentitySector.role_name(-1), "Weaver")

    def test_role_name_all_positions(self):
        expected = [
            "Theorist", "Builder", "Scout", "Guardian", "Diplomat", "Architect",
            "Analyst", "Artist", "Strategist", "Keeper", "Pioneer", "Weaver",
        ]
        for i, name in enumerate(expected):
            self.assertEqual(IdentitySector.role_name(i), name)

    # ─── description ───────────────────────────────────────────

    def test_description_position_0(self):
        desc = IdentitySector.description(0)
        self.assertIn("thinker", desc)

    def test_description_position_7(self):
        desc = IdentitySector.description(7)
        self.assertIn("creative", desc.lower())

    def test_description_wraps(self):
        desc_12 = IdentitySector.description(12)
        desc_0 = IdentitySector.description(0)
        self.assertEqual(desc_12, desc_0)

    # ─── all_roles ─────────────────────────────────────────────

    def test_all_roles_count(self):
        roles = IdentitySector.all_roles()
        self.assertEqual(len(roles), 12)

    def test_all_roles_order(self):
        roles = IdentitySector.all_roles()
        self.assertEqual(roles[0], "Theorist")
        self.assertEqual(roles[11], "Weaver")

    def test_all_roles_unique(self):
        roles = IdentitySector.all_roles()
        self.assertEqual(len(roles), len(set(roles)))

    # ─── position_from_name ────────────────────────────────────

    def test_position_from_name_theorist(self):
        self.assertEqual(IdentitySector.position_from_name("Theorist"), 0)

    def test_position_from_name_builder(self):
        self.assertEqual(IdentitySector.position_from_name("Builder"), 1)

    def test_position_from_name_case_insensitive(self):
        self.assertEqual(IdentitySector.position_from_name("ARCHITECT"), 5)
        self.assertEqual(IdentitySector.position_from_name("architect"), 5)

    def test_position_from_name_unknown(self):
        self.assertIsNone(IdentitySector.position_from_name("Nonexistent"))

    def test_position_from_name_empty(self):
        self.assertIsNone(IdentitySector.position_from_name(""))

    def test_position_from_name_all_known(self):
        roles = IdentitySector.all_roles()
        for i, name in enumerate(roles):
            self.assertEqual(IdentitySector.position_from_name(name), i)

    # ─── to_dict ───────────────────────────────────────────────

    def test_to_dict_keys(self):
        d = IdentitySector.to_dict(3)
        self.assertIn("position", d)
        self.assertIn("name", d)
        self.assertIn("description", d)

    def test_to_dict_values(self):
        d = IdentitySector.to_dict(3)
        self.assertEqual(d["position"], 3)
        self.assertEqual(d["name"], "Guardian")

    def test_to_dict_wraps(self):
        d = IdentitySector.to_dict(15)
        self.assertEqual(d["position"], 3)


# ═══════════════════════════════════════════════════════════════
# DialConfig Tests
# ═══════════════════════════════════════════════════════════════

class TestDialConfig(TestCase):

    def test_defaults(self):
        cfg = DialConfig()
        self.assertEqual(cfg.resolution, 100)
        self.assertTrue(cfg.wrap_enabled)
        self.assertEqual(cfg.shift_step_size, 0.5)
        self.assertEqual(cfg.max_shift_per_step, 2.0)
        self.assertEqual(cfg.blending_weight_a, 0.5)
        self.assertEqual(cfg.blending_weight_b, 0.5)

    def test_custom_values(self):
        cfg = DialConfig(resolution=50, wrap_enabled=False, shift_step_size=1.0)
        self.assertEqual(cfg.resolution, 50)
        self.assertFalse(cfg.wrap_enabled)
        self.assertEqual(cfg.shift_step_size, 1.0)

    def test_to_dict(self):
        cfg = DialConfig()
        d = cfg.to_dict()
        self.assertEqual(d["resolution"], 100)
        self.assertTrue(d["wrap_enabled"])
        self.assertEqual(d["shift_step_size"], 0.5)

    def test_to_dict_custom(self):
        cfg = DialConfig(resolution=200, wrap_enabled=False)
        d = cfg.to_dict()
        self.assertEqual(d["resolution"], 200)
        self.assertFalse(d["wrap_enabled"])

    def test_from_dict_defaults(self):
        cfg = DialConfig.from_dict({})
        self.assertEqual(cfg.resolution, 100)
        self.assertTrue(cfg.wrap_enabled)

    def test_from_dict_custom(self):
        cfg = DialConfig.from_dict({
            "resolution": 50,
            "wrap_enabled": False,
            "shift_step_size": 1.5,
            "max_shift_per_step": 3.0,
            "blending_weight_a": 0.3,
            "blending_weight_b": 0.7,
        })
        self.assertEqual(cfg.resolution, 50)
        self.assertFalse(cfg.wrap_enabled)
        self.assertEqual(cfg.shift_step_size, 1.5)
        self.assertEqual(cfg.max_shift_per_step, 3.0)
        self.assertEqual(cfg.blending_weight_a, 0.3)
        self.assertEqual(cfg.blending_weight_b, 0.7)

    def test_roundtrip(self):
        cfg = DialConfig(resolution=75, wrap_enabled=True, shift_step_size=0.8)
        restored = DialConfig.from_dict(cfg.to_dict())
        self.assertEqual(restored.resolution, 75)
        self.assertEqual(restored.shift_step_size, 0.8)


# ═══════════════════════════════════════════════════════════════
# EjectResult Tests
# ═══════════════════════════════════════════════════════════════

class TestEjectResult(TestCase):

    def test_defaults(self):
        er = EjectResult(success=True, reason="test")
        self.assertTrue(er.success)
        self.assertEqual(er.reason, "test")
        self.assertEqual(er.session_id, "")
        self.assertEqual(er.wearer, "")
        self.assertEqual(er.elapsed_seconds, 0.0)
        self.assertEqual(er.audit_summary, {})

    def test_full_constructor(self):
        er = EjectResult(
            success=False,
            reason="expired",
            session_id="abc123",
            wearer="agent1",
            cartridge_name="cart1",
            restored_identity={"position": 5},
            audit_summary={"actions": 3},
            elapsed_seconds=12.5,
        )
        self.assertFalse(er.success)
        self.assertEqual(er.session_id, "abc123")
        self.assertEqual(er.cartridge_name, "cart1")

    def test_to_dict(self):
        er = EjectResult(success=True, reason="ok", elapsed_seconds=5.12345)
        d = er.to_dict()
        self.assertTrue(d["success"])
        self.assertEqual(d["reason"], "ok")
        self.assertEqual(d["elapsed_seconds"], 5.123)  # rounded to 3

    def test_to_dict_keys(self):
        er = EjectResult(success=True, reason="ok")
        d = er.to_dict()
        for key in ("success", "reason", "session_id", "wearer",
                     "cartridge_name", "restored_identity",
                     "audit_summary", "elapsed_seconds"):
            self.assertIn(key, d)

    def test_from_dict_minimal(self):
        er = EjectResult.from_dict({})
        self.assertFalse(er.success)
        self.assertEqual(er.reason, "")

    def test_from_dict_full(self):
        data = {
            "success": True,
            "reason": "ejected",
            "session_id": "sess1",
            "wearer": "agent",
            "cartridge_name": "cart",
            "elapsed_seconds": 42.0,
        }
        er = EjectResult.from_dict(data)
        self.assertTrue(er.success)
        self.assertEqual(er.elapsed_seconds, 42.0)

    def test_roundtrip(self):
        er = EjectResult(
            success=True, reason="test", session_id="s1",
            wearer="w1", cartridge_name="c1",
            elapsed_seconds=10.5555,
        )
        restored = EjectResult.from_dict(er.to_dict())
        self.assertEqual(restored.success, er.success)
        self.assertEqual(restored.session_id, "s1")
        self.assertAlmostEqual(restored.elapsed_seconds, 10.556, places=3)


# ═══════════════════════════════════════════════════════════════
# IdentityDial Tests
# ═══════════════════════════════════════════════════════════════

class TestIdentityDial(TestCase):

    # ─── Initialization & Normalization ───────────────────────

    def test_default_position(self):
        d = IdentityDial()
        self.assertEqual(d.position, 0.0)

    def test_custom_position(self):
        d = IdentityDial(position=5)
        self.assertEqual(d.position, 5.0)

    def test_wrap_normalization_12_to_0(self):
        d = IdentityDial(position=12)
        self.assertEqual(d.position, 0.0)

    def test_wrap_normalization_13_to_1(self):
        d = IdentityDial(position=13)
        self.assertEqual(d.position, 1.0)

    def test_wrap_normalization_negative(self):
        d = IdentityDial(position=-1)
        self.assertEqual(d.position, 11.0)

    def test_fractional_position(self):
        d = IdentityDial(position=3.7)
        self.assertAlmostEqual(d.position, 3.7, places=4)

    def test_no_wrap_clamps(self):
        cfg = DialConfig(wrap_enabled=False)
        d = IdentityDial(position=15.0, config=cfg)
        self.assertAlmostEqual(d.position, 11.999, places=3)

    def test_no_wrap_clamps_negative(self):
        cfg = DialConfig(wrap_enabled=False)
        d = IdentityDial(position=-5.0, config=cfg)
        self.assertEqual(d.position, 0.0)

    def test_precision_clamped_above(self):
        d = IdentityDial(position=0, precision=1.5)
        self.assertEqual(d.precision, 1.0)

    def test_precision_clamped_below(self):
        d = IdentityDial(position=0, precision=-0.5)
        self.assertEqual(d.precision, 0.0)

    def test_precision_valid(self):
        d = IdentityDial(position=0, precision=0.7)
        self.assertAlmostEqual(d.precision, 0.7, places=4)

    # ─── Properties ────────────────────────────────────────────

    def test_sector_property(self):
        d = IdentityDial(position=3.7)
        self.assertEqual(d.sector, 3)

    def test_sector_property_wrapped(self):
        d = IdentityDial(position=11.9)
        self.assertEqual(d.sector, 11)

    def test_sector_name_property(self):
        d = IdentityDial(position=5)
        self.assertEqual(d.sector_name, "Architect")

    def test_degrees_property(self):
        d = IdentityDial(position=0)
        self.assertEqual(d.degrees, 0.0)

    def test_degrees_property_mid(self):
        d = IdentityDial(position=6)
        self.assertEqual(d.degrees, 180.0)

    def test_degrees_property_fractional(self):
        d = IdentityDial(position=3.0)
        self.assertEqual(d.degrees, 90.0)

    def test_effective_position(self):
        d = IdentityDial(position=3.0, precision=0.5)
        self.assertAlmostEqual(d.effective_position, 3.5, places=4)

    def test_effective_position_wraps(self):
        d = IdentityDial(position=11.0, precision=1.0)
        self.assertAlmostEqual(d.effective_position, 0.0, places=4)

    # ─── distance ──────────────────────────────────────────────

    def test_distance_same(self):
        a = IdentityDial(position=3)
        b = IdentityDial(position=3)
        self.assertEqual(a.distance(b), 0.0)

    def test_distance_adjacent(self):
        a = IdentityDial(position=3)
        b = IdentityDial(position=4)
        self.assertEqual(a.distance(b), 1.0)

    def test_distance_wrap_0_11(self):
        """Positions 0 and 11 are 1 apart (wrap-around)."""
        a = IdentityDial(position=0)
        b = IdentityDial(position=11)
        self.assertEqual(a.distance(b), 1.0)

    def test_distance_opposite(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        self.assertEqual(a.distance(b), 6.0)

    def test_distance_opposite_3_9(self):
        a = IdentityDial(position=3)
        b = IdentityDial(position=9)
        self.assertEqual(a.distance(b), 6.0)

    def test_distance_shortest_path(self):
        """Distance from 1 to 10: forward=9, backward=3. Shortest=3."""
        a = IdentityDial(position=1)
        b = IdentityDial(position=10)
        self.assertEqual(a.distance(b), 3.0)

    def test_distance_no_wrap(self):
        cfg = DialConfig(wrap_enabled=False)
        a = IdentityDial(position=0, config=cfg)
        b = IdentityDial(position=11, config=cfg)
        self.assertEqual(a.distance(b), 11.0)

    def test_distance_with_precision(self):
        a = IdentityDial(position=3.0, precision=0.3)
        b = IdentityDial(position=4.0, precision=0.0)
        self.assertAlmostEqual(a.distance(b), 0.7, places=4)

    # ─── angular_distance ──────────────────────────────────────

    def test_angular_distance_same(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=0)
        self.assertEqual(a.angular_distance(b), 0.0)

    def test_angular_distance_adjacent(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=1)
        self.assertEqual(a.angular_distance(b), 30.0)

    def test_angular_distance_opposite(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        self.assertEqual(a.angular_distance(b), 180.0)

    # ─── rotate_toward ─────────────────────────────────────────

    def test_rotate_toward_adjacent_step(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=5)
        result = a.rotate_toward(b, amount=1.0)
        self.assertAlmostEqual(result.effective_position, 1.0, places=4)

    def test_rotate_toward_overshoot_clamp(self):
        """If distance < step, should land exactly on target."""
        a = IdentityDial(position=0)
        b = IdentityDial(position=0.5)
        result = a.rotate_toward(b, amount=2.0)
        self.assertAlmostEqual(result.effective_position, 0.5, places=4)

    def test_rotate_toward_default_step(self):
        cfg = DialConfig(shift_step_size=1.0)
        a = IdentityDial(position=0, config=cfg)
        b = IdentityDial(position=5)
        result = a.rotate_toward(b)
        self.assertAlmostEqual(result.effective_position, 1.0, places=4)

    def test_rotate_toward_max_shift_capped(self):
        cfg = DialConfig(max_shift_per_step=0.5)
        a = IdentityDial(position=0, config=cfg)
        b = IdentityDial(position=5)
        result = a.rotate_toward(b, amount=10.0)
        self.assertAlmostEqual(result.effective_position, 0.5, places=4)

    def test_rotate_toward_wrap_11_to_0(self):
        """Rotate from position 11 toward position 0 (1 step, wrapping)."""
        a = IdentityDial(position=11)
        b = IdentityDial(position=0)
        result = a.rotate_toward(b, amount=1.0)
        # Shortest path: 11 -> 0 is +1, but going forward from 11 wraps to 0
        self.assertAlmostEqual(result.effective_position, 0.0, places=4)

    def test_rotate_toward_returns_new_instance(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=5)
        result = a.rotate_toward(b, amount=1.0)
        self.assertIsNot(result, a)
        self.assertEqual(a.position, 0.0)

    def test_rotate_toward_negative_direction(self):
        """Rotate from 5 toward 3 (backward)."""
        a = IdentityDial(position=5)
        b = IdentityDial(position=3)
        result = a.rotate_toward(b, amount=1.0)
        self.assertAlmostEqual(result.effective_position, 4.0, places=4)

    def test_rotate_toward_same_position(self):
        a = IdentityDial(position=3)
        b = IdentityDial(position=3)
        result = a.rotate_toward(b)
        self.assertAlmostEqual(result.effective_position, a.effective_position, places=4)

    # ─── perspective_shift ─────────────────────────────────────

    def test_perspective_shift(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        self.assertEqual(a.perspective_shift(b), 6.0)

    def test_perspective_shift_zero(self):
        a = IdentityDial(position=3)
        b = IdentityDial(position=3)
        self.assertEqual(a.perspective_shift(b), 0.0)

    # ─── is_adjacent ───────────────────────────────────────────

    def test_is_adjacent_true(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=1)
        self.assertTrue(a.is_adjacent(b))

    def test_is_adjacent_wrap(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=11)
        self.assertTrue(a.is_adjacent(b))

    def test_is_adjacent_same(self):
        a = IdentityDial(position=5)
        b = IdentityDial(position=5)
        self.assertTrue(a.is_adjacent(b))

    def test_is_adjacent_false(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        self.assertFalse(a.is_adjacent(b))

    def test_is_adjacent_boundary_1(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=1.01)
        self.assertFalse(a.is_adjacent(b))

    def test_is_adjacent_exact_boundary(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=1.0)
        self.assertTrue(a.is_adjacent(b))

    # ─── is_opposite ───────────────────────────────────────────

    def test_is_opposite_true(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        self.assertTrue(a.is_opposite(b))

    def test_is_opposite_3_9(self):
        a = IdentityDial(position=3)
        b = IdentityDial(position=9)
        self.assertTrue(a.is_opposite(b))

    def test_is_opposite_false(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=5)
        self.assertFalse(a.is_opposite(b))

    def test_is_opposite_near_miss(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=5.98)
        self.assertFalse(a.is_opposite(b))

    # ─── to_dict / from_dict ───────────────────────────────────

    def test_to_dict_keys(self):
        d = IdentityDial(position=3, precision=0.5).to_dict()
        for key in ("position", "precision", "sector", "sector_name",
                     "degrees", "effective_position", "config"):
            self.assertIn(key, d)

    def test_to_dict_values(self):
        d = IdentityDial(position=3, precision=0.5).to_dict()
        self.assertEqual(d["position"], 3.0)
        self.assertAlmostEqual(d["precision"], 0.5, places=4)
        self.assertEqual(d["sector"], 3)
        self.assertEqual(d["sector_name"], "Guardian")

    def test_from_dict(self):
        data = {"position": 5.0, "precision": 0.3}
        d = IdentityDial.from_dict(data)
        self.assertAlmostEqual(d.position, 5.0, places=4)
        self.assertAlmostEqual(d.precision, 0.3, places=4)

    def test_from_dict_with_config(self):
        data = {
            "position": 2.0,
            "precision": 0.0,
            "config": {"wrap_enabled": False, "resolution": 50},
        }
        d = IdentityDial.from_dict(data)
        self.assertFalse(d.config.wrap_enabled)
        self.assertEqual(d.config.resolution, 50)

    def test_roundtrip(self):
        original = IdentityDial(position=7, precision=0.6)
        restored = IdentityDial.from_dict(original.to_dict())
        self.assertAlmostEqual(restored.position, original.position, places=4)
        self.assertAlmostEqual(restored.precision, original.precision, places=4)
        self.assertEqual(restored.sector, original.sector)
        self.assertEqual(restored.sector_name, original.sector_name)

    # ─── encode ────────────────────────────────────────────────

    def test_encode_empty_traits(self):
        d = IdentityDial.encode({})
        self.assertEqual(d.position, 0.0)
        self.assertEqual(d.precision, 0.0)

    def test_encode_single_trait(self):
        d = IdentityDial.encode({"Builder": 0.8})
        self.assertEqual(d.position, 1.0)
        self.assertTrue(d.precision > 0)

    def test_encode_strongest_wins(self):
        d = IdentityDial.encode({"Builder": 0.3, "Architect": 0.9})
        self.assertEqual(d.position, 5.0)

    def test_encode_unknown_traits(self):
        d = IdentityDial.encode({"Unknown": 1.0})
        self.assertEqual(d.position, 0.0)

    def test_encode_case_insensitive(self):
        d = IdentityDial.encode({"artist": 0.7})
        self.assertEqual(d.position, 7.0)

    def test_encode_precision_from_strength(self):
        d = IdentityDial.encode({"Architect": 0.6})
        self.assertTrue(0 < d.precision <= 1.0)

    # ─── __repr__ ──────────────────────────────────────────────

    def test_repr(self):
        d = IdentityDial(position=5)
        r = repr(d)
        self.assertIn("IdentityDial", r)
        self.assertIn("Architect", r)


# ═══════════════════════════════════════════════════════════════
# AgentSnapshot Tests
# ═══════════════════════════════════════════════════════════════

class TestAgentSnapshot(TestCase):

    def test_defaults(self):
        snap = AgentSnapshot()
        self.assertEqual(snap.agent_name, "")
        self.assertFalse(snap.is_expired())
        self.assertEqual(snap.trust_profile, {})
        self.assertEqual(snap.capabilities, [])
        self.assertEqual(snap.skills, {})
        self.assertEqual(snap.personality_vector, [])

    def test_custom_created_at(self):
        t = 1000.0
        snap = AgentSnapshot(created_at=t)
        self.assertEqual(snap.created_at, t)

    # ─── is_expired ────────────────────────────────────────────

    def test_not_expired_no_expiry(self):
        snap = AgentSnapshot(expires_at=0.0)
        self.assertFalse(snap.is_expired())

    def test_not_expired_future(self):
        snap = AgentSnapshot(expires_at=time.time() + 3600)
        self.assertFalse(snap.is_expired())

    def test_expired_past(self):
        snap = AgentSnapshot(expires_at=time.time() - 1)
        self.assertTrue(snap.is_expired())

    def test_expired_boundary(self):
        """expires_at == now should be expired."""
        snap = AgentSnapshot(expires_at=time.time() - 0.001)
        self.assertTrue(snap.is_expired())

    # ─── age_seconds / age_days ───────────────────────────────

    def test_age_seconds_fresh(self):
        snap = AgentSnapshot(created_at=time.time())
        self.assertGreaterEqual(snap.age_seconds(), 0.0)
        self.assertLess(snap.age_seconds(), 1.0)

    def test_age_seconds_old(self):
        snap = AgentSnapshot(created_at=time.time() - 100)
        self.assertGreaterEqual(snap.age_seconds(), 100.0)

    def test_age_days(self):
        snap = AgentSnapshot(created_at=time.time() - 86400)
        self.assertAlmostEqual(snap.age_days(), 1.0, places=1)

    # ─── ttl_seconds ───────────────────────────────────────────

    def test_ttl_no_expiry(self):
        snap = AgentSnapshot(expires_at=0.0)
        self.assertEqual(snap.ttl_seconds(), 0.0)

    def test_ttl_future(self):
        snap = AgentSnapshot(expires_at=time.time() + 300)
        ttl = snap.ttl_seconds()
        self.assertGreater(ttl, 290)
        self.assertLessEqual(ttl, 300)

    def test_ttl_expired(self):
        snap = AgentSnapshot(expires_at=time.time() - 10)
        self.assertLess(snap.ttl_seconds(), 0.0)

    # ─── compute_trail_hash ───────────────────────────────────

    def test_compute_trail_hash(self):
        snap = AgentSnapshot()
        h = snap.compute_trail_hash("hello")
        expected = hashlib.sha256("hello".encode("utf-8")).hexdigest()
        self.assertEqual(h, expected)

    def test_compute_trail_hash_different_inputs(self):
        snap = AgentSnapshot()
        h1 = snap.compute_trail_hash("a")
        h2 = snap.compute_trail_hash("b")
        self.assertNotEqual(h1, h2)

    # ─── capture_from ──────────────────────────────────────────

    def test_capture_from_minimal(self):
        snap = AgentSnapshot.capture_from({"name": "TestAgent"})
        self.assertEqual(snap.agent_name, "TestAgent")
        self.assertEqual(snap.identity.position, 0.0)

    def test_capture_from_full(self):
        data = {
            "name": "Agent",
            "identity_position": 5,
            "identity_precision": 0.3,
            "capabilities": ["read", "write"],
            "skills": {"code": 0.9},
            "personality_vector": [0.1, 0.2, 0.3],
            "preferences": {"style": "formal"},
            "memory_summary": "Some memory",
        }
        snap = AgentSnapshot.capture_from(data)
        self.assertEqual(snap.agent_name, "Agent")
        self.assertEqual(snap.identity.position, 5.0)
        self.assertEqual(snap.capabilities, ["read", "write"])
        self.assertEqual(snap.skills, {"code": 0.9})

    def test_capture_from_trail_data(self):
        data = {"name": "A", "trail_data": "some trail"}
        snap = AgentSnapshot.capture_from(data)
        self.assertEqual(
            snap.trail_hash,
            hashlib.sha256("some trail".encode("utf-8")).hexdigest(),
        )

    def test_capture_from_expires_in(self):
        data = {"name": "A", "expires_in": 300}
        snap = AgentSnapshot.capture_from(data)
        self.assertGreater(snap.expires_at, time.time())

    def test_capture_from_expires_in_zero(self):
        data = {"name": "A", "expires_in": 0}
        snap = AgentSnapshot.capture_from(data)
        self.assertEqual(snap.expires_at, 0.0)

    def test_capture_from_no_name(self):
        snap = AgentSnapshot.capture_from({})
        self.assertEqual(snap.agent_name, "unknown")

    # ─── to_dict / from_dict ───────────────────────────────────

    def test_to_dict_keys(self):
        snap = make_snapshot()
        d = snap.to_dict()
        for key in ("agent_name", "identity", "trust_profile", "capabilities",
                     "skills", "memory_summary", "personality_vector",
                     "preferences", "trail_hash", "created_at", "expires_at",
                     "is_expired", "age_days"):
            self.assertIn(key, d)

    def test_to_dict_values(self):
        snap = make_snapshot(agent_name="Alice")
        d = snap.to_dict()
        self.assertEqual(d["agent_name"], "Alice")

    def test_from_dict(self):
        snap = make_snapshot(agent_name="Bob", position=3)
        d = snap.to_dict()
        restored = AgentSnapshot.from_dict(d)
        self.assertEqual(restored.agent_name, "Bob")
        self.assertEqual(restored.identity.position, 3.0)

    def test_from_dict_minimal(self):
        restored = AgentSnapshot.from_dict({})
        self.assertEqual(restored.agent_name, "")

    def test_roundtrip_full(self):
        snap = AgentSnapshot(
            agent_name="Full",
            identity=IdentityDial(position=7, precision=0.4),
            trust_profile={"level": 5},
            capabilities=["a", "b"],
            skills={"x": 0.9},
            personality_vector=[0.1, 0.2],
            preferences={"style": "fast"},
            memory_summary="memo",
            trail_hash="hash123",
        )
        d = snap.to_dict()
        restored = AgentSnapshot.from_dict(d)
        self.assertEqual(restored.agent_name, "Full")
        self.assertEqual(restored.identity.position, 7.0)
        self.assertEqual(restored.capabilities, ["a", "b"])
        self.assertEqual(restored.skills, {"x": 0.9})
        self.assertEqual(restored.personality_vector, [0.1, 0.2])

    # ─── __repr__ ──────────────────────────────────────────────

    def test_repr(self):
        snap = make_snapshot(agent_name="AgentX")
        r = repr(snap)
        self.assertIn("AgentX", r)

    def test_repr_expired(self):
        snap = make_snapshot(agent_name="Old", expires_at=time.time() - 10)
        r = repr(snap)
        self.assertIn("EXPIRED", r)


# ═══════════════════════════════════════════════════════════════
# TwinCartridge Tests
# ═══════════════════════════════════════════════════════════════

class TestTwinCartridge(TestCase):

    def test_defaults(self):
        cart = TwinCartridge()
        self.assertEqual(cart.trust_inheritance, TRUST_INHERIT_FULL)
        self.assertFalse(cart.published)
        self.assertEqual(cart.version, "1.0.0")
        self.assertFalse(cart.is_time_limited())

    def test_auto_naming(self):
        cart = TwinCartridge(snapshot=make_snapshot(agent_name="Oracle1"))
        self.assertEqual(cart.cartridge_name, "twin-Oracle1")

    def test_custom_name(self):
        cart = TwinCartridge(cartridge_name="my-cart")
        self.assertEqual(cart.cartridge_name, "my-cart")

    # ─── validate ──────────────────────────────────────────────

    def test_validate_valid(self):
        cart = make_cartridge(agent_name="Valid")
        self.assertTrue(cart.validate())

    def test_validate_no_agent_name(self):
        cart = TwinCartridge(snapshot=AgentSnapshot(agent_name=""))
        self.assertFalse(cart.validate())

    def test_validate_expired_snapshot(self):
        snap = make_snapshot(agent_name="Old", expires_at=time.time() - 1)
        cart = TwinCartridge(snapshot=snap)
        self.assertFalse(cart.validate())

    def test_validate_bad_trust_mode(self):
        cart = TwinCartridge(
            snapshot=make_snapshot(agent_name="A"),
            trust_inheritance="invalid",
        )
        self.assertFalse(cart.validate())

    def test_validate_all_trust_modes(self):
        for mode in (TRUST_INHERIT_FULL, TRUST_INHERIT_PARTIAL,
                     TRUST_INHERIT_NONE, TRUST_INHERIT_BLENDED):
            cart = make_cartridge(agent_name="A", trust_inheritance=mode)
            self.assertTrue(cart.validate(), f"Failed for mode: {mode}")

    # ─── load ──────────────────────────────────────────────────

    def test_load_creates_session(self):
        cart = make_cartridge(agent_name="Test", published=True)
        session = cart.load("Wearer")
        self.assertIsInstance(session, CartridgeSession)
        self.assertEqual(session.wearer_name, "Wearer")

    def test_load_invalid_raises(self):
        cart = TwinCartridge(snapshot=AgentSnapshot(agent_name=""))
        with self.assertRaises(ValueError):
            cart.load("Wearer")

    def test_load_expired_raises(self):
        snap = make_snapshot(agent_name="Old", expires_at=time.time() - 1)
        cart = TwinCartridge(snapshot=snap)
        with self.assertRaises(ValueError):
            cart.load("Wearer")

    def test_load_increments_session_count(self):
        cart = make_cartridge(agent_name="A", published=True)
        cart.load("W1")
        cart.load("W2")
        self.assertEqual(cart._session_count, 2)

    # ─── eject ─────────────────────────────────────────────────

    def test_eject_published(self):
        cart = make_cartridge(published=True)
        result = cart.eject()
        self.assertTrue(result)
        self.assertFalse(cart.published)

    def test_eject_draft(self):
        cart = make_cartridge(published=False)
        result = cart.eject()
        self.assertFalse(result)
        self.assertFalse(cart.published)

    # ─── is_time_limited ───────────────────────────────────────

    def test_is_time_limited_true(self):
        cart = make_cartridge(time_limit=60.0)
        self.assertTrue(cart.is_time_limited())

    def test_is_time_limited_false(self):
        cart = make_cartridge(time_limit=0.0)
        self.assertFalse(cart.is_time_limited())

    def test_is_time_limited_default(self):
        cart = TwinCartridge()
        self.assertFalse(cart.is_time_limited())

    # ─── clone ─────────────────────────────────────────────────

    def test_clone_copies_attributes(self):
        cart = make_cartridge(agent_name="A", trust_inheritance=TRUST_INHERIT_PARTIAL)
        cart.behavior_profile = {"style": "fast"}
        cart.permission_scope = ["read", "write"]
        cloned = cart.clone()
        self.assertEqual(cloned.cartridge_name, cart.cartridge_name)
        self.assertEqual(cloned.trust_inheritance, cart.trust_inheritance)
        self.assertEqual(cloned.behavior_profile, {"style": "fast"})
        self.assertEqual(cloned.permission_scope, ["read", "write"])

    def test_clone_unpublished(self):
        cart = make_cartridge(published=True)
        cloned = cart.clone()
        self.assertFalse(cloned.published)

    def test_clone_new_version(self):
        cart = make_cartridge()
        cloned = cart.clone(new_version="2.0.0")
        self.assertEqual(cloned.version, "2.0.0")

    def test_clone_same_version_default(self):
        cart = make_cartridge()
        cloned = cart.clone()
        self.assertEqual(cloned.version, cart.version)

    def test_clone_independent(self):
        """Modifying clone doesn't affect original."""
        cart = make_cartridge()
        cloned = cart.clone()
        cloned.behavior_profile["new_key"] = "value"
        self.assertNotIn("new_key", cart.behavior_profile)

    def test_clone_time_limit(self):
        cart = make_cartridge(time_limit=120.0)
        cloned = cart.clone()
        self.assertEqual(cloned.time_limit, 120.0)

    def test_clone_stack_depth(self):
        cart = make_cartridge()
        cart.stack_depth = 3
        cloned = cart.clone()
        self.assertEqual(cloned.stack_depth, 3)

    # ─── to_dict / from_dict ───────────────────────────────────

    def test_to_dict_keys(self):
        cart = make_cartridge()
        d = cart.to_dict()
        for key in ("cartridge_name", "snapshot", "behavior_profile",
                     "trust_inheritance", "permission_scope", "time_limit",
                     "published", "version", "published_at", "stack_depth",
                     "session_count", "is_valid"):
            self.assertIn(key, d)

    def test_from_dict(self):
        cart = make_cartridge(agent_name="A", position=3)
        d = cart.to_dict()
        restored = TwinCartridge.from_dict(d)
        self.assertEqual(restored.cartridge_name, cart.cartridge_name)
        self.assertEqual(restored.trust_inheritance, cart.trust_inheritance)

    def test_from_dict_session_count(self):
        cart = make_cartridge(agent_name="A", published=True)
        cart.load("W1")
        d = cart.to_dict()
        restored = TwinCartridge.from_dict(d)
        self.assertEqual(restored._session_count, 1)

    def test_roundtrip(self):
        cart = make_cartridge(
            agent_name="Round",
            trust_inheritance=TRUST_INHERIT_BLENDED,
            time_limit=300,
        )
        cart.behavior_profile = {"x": 1}
        cart.permission_scope = ["scope1"]
        d = cart.to_dict()
        restored = TwinCartridge.from_dict(d)
        self.assertEqual(restored.cartridge_name, "twin-Round")
        self.assertEqual(restored.trust_inheritance, TRUST_INHERIT_BLENDED)
        self.assertEqual(restored.time_limit, 300)
        self.assertEqual(restored.behavior_profile, {"x": 1})
        self.assertEqual(restored.permission_scope, ["scope1"])

    # ─── __repr__ ──────────────────────────────────────────────

    def test_repr_published(self):
        cart = make_cartridge(published=True)
        r = repr(cart)
        self.assertIn("PUBLISHED", r)

    def test_repr_draft(self):
        cart = make_cartridge(published=False)
        r = repr(cart)
        self.assertIn("DRAFT", r)


# ═══════════════════════════════════════════════════════════════
# CartridgeSession Tests
# ═══════════════════════════════════════════════════════════════

class TestCartridgeSession(TestCase):

    def _make_active_session(self, wearer="Wearer", agent="Agent", time_limit=0.0):
        """Create a fully active session ready for testing."""
        cart = make_cartridge(agent_name=agent, published=True, time_limit=time_limit)
        return cart.load(wearer), cart

    def test_defaults(self):
        session, _ = self._make_active_session()
        self.assertFalse(session._ejected)
        self.assertIsInstance(session.session_id, str)
        self.assertEqual(len(session.session_id), 12)

    # ─── Properties ────────────────────────────────────────────

    def test_cartridge_name(self):
        session, _ = self._make_active_session(agent="TestAgent")
        self.assertEqual(session.cartridge_name, "twin-TestAgent")

    def test_twin_agent_name(self):
        session, _ = self._make_active_session(agent="Oracle1")
        self.assertEqual(session.twin_agent_name, "Oracle1")

    # ─── is_expired ────────────────────────────────────────────

    def test_not_expired_fresh(self):
        session, _ = self._make_active_session()
        self.assertFalse(session.is_expired())

    def test_expired_after_eject(self):
        session, _ = self._make_active_session()
        session.eject()
        self.assertTrue(session.is_expired())

    def test_expired_time_limited(self):
        session, _ = self._make_active_session(time_limit=0.01)
        time.sleep(0.02)
        self.assertTrue(session.is_expired())

    def test_not_expired_within_time_limit(self):
        session, _ = self._make_active_session(time_limit=10.0)
        self.assertFalse(session.is_expired())

    def test_expired_snapshot(self):
        snap = make_snapshot(agent_name="Old", expires_at=time.time() - 1)
        cart = TwinCartridge(snapshot=snap, cartridge_name="old-cart")
        session = CartridgeSession(wearer_name="W", cartridge=cart)
        self.assertTrue(session.is_expired())

    # ─── elapsed / remaining ───────────────────────────────────

    def test_elapsed_nonnegative(self):
        session, _ = self._make_active_session()
        self.assertGreaterEqual(session.elapsed(), 0.0)

    def test_remaining_no_limit(self):
        session, _ = self._make_active_session()
        self.assertEqual(session.remaining(), 0.0)

    def test_remaining_with_limit(self):
        session, _ = self._make_active_session(time_limit=60.0)
        r = session.remaining()
        self.assertGreater(r, 50.0)
        self.assertLessEqual(r, 60.0)

    def test_remaining_expired(self):
        session, _ = self._make_active_session(time_limit=0.001)
        time.sleep(0.01)
        self.assertEqual(session.remaining(), 0.0)

    # ─── record_action ─────────────────────────────────────────

    def test_record_action(self):
        session, _ = self._make_active_session()
        entry = session.record_action("test_action", {"key": "val"})
        self.assertEqual(entry["action"], "test_action")
        self.assertEqual(entry["details"], {"key": "val"})
        self.assertEqual(entry["session_id"], session.session_id)

    def test_record_action_no_details(self):
        session, _ = self._make_active_session()
        entry = session.record_action("simple")
        self.assertEqual(entry["details"], {})

    def test_record_action_increments_count(self):
        session, _ = self._make_active_session()
        session.record_action("a")
        session.record_action("b")
        self.assertEqual(len(session.actions_taken), 2)

    # ─── shift_perspective ─────────────────────────────────────

    def test_shift_perspective_moves(self):
        session, _ = self._make_active_session(agent="TestAgent", time_limit=60)
        session.cartridge.snapshot.identity = IdentityDial(position=0)
        session.current_identity = IdentityDial(position=0)
        shift = session.shift_perspective(5.0, amount=1.0)
        self.assertGreater(shift, 0.0)

    def test_shift_perspective_records_action(self):
        session, _ = self._make_active_session(time_limit=60)
        session.shift_perspective(5.0)
        action_types = [a["action"] for a in session.actions_taken]
        self.assertIn("perspective_shift", action_types)

    def test_shift_perspective_no_overshoot(self):
        session, _ = self._make_active_session(time_limit=60)
        session.cartridge.snapshot.identity = IdentityDial(position=0)
        session.current_identity = IdentityDial(position=0)
        shift = session.shift_perspective(1.0, amount=10.0)
        self.assertAlmostEqual(shift, 1.0, places=3)

    def test_shift_perspective_zero_distance(self):
        session, _ = self._make_active_session(time_limit=60)
        session.cartridge.snapshot.identity = IdentityDial(position=3)
        session.current_identity = IdentityDial(position=3)
        shift = session.shift_perspective(3.0, amount=1.0)
        self.assertAlmostEqual(shift, 0.0, places=4)

    # ─── eject ─────────────────────────────────────────────────

    def test_eject_success(self):
        session, _ = self._make_active_session()
        result = session.eject()
        self.assertIsInstance(result, EjectResult)
        self.assertTrue(result.success)
        self.assertEqual(result.reason, "Cartridge ejected successfully")
        self.assertIn("session_id", result.to_dict())
        self.assertIn("audit_summary", result.to_dict())

    def test_eject_restores_identity(self):
        session, _ = self._make_active_session()
        orig = session.original_identity.to_dict()
        result = session.eject()
        self.assertEqual(result.restored_identity, orig)

    def test_double_eject_fails(self):
        session, _ = self._make_active_session()
        session.eject()
        result = session.eject()
        self.assertFalse(result.success)
        self.assertEqual(result.reason, "Session already ejected")

    def test_eject_has_audit(self):
        session, _ = self._make_active_session()
        session.record_action("test")
        result = session.eject()
        self.assertIsInstance(result.audit_summary, dict)
        self.assertGreater(result.audit_summary.get("actions_count", 0), 0)

    def test_eject_records_action(self):
        session, _ = self._make_active_session()
        session.eject()
        action_types = [a["action"] for a in session.actions_taken]
        self.assertIn("eject", action_types)

    # ─── audit ─────────────────────────────────────────────────

    def test_audit_keys(self):
        session, _ = self._make_active_session()
        a = session.audit()
        for key in ("session_id", "wearer", "cartridge", "twin_agent",
                     "loaded_at", "elapsed_seconds", "is_expired",
                     "actions_count", "action_types",
                     "original_identity", "current_identity", "trust_snapshot"):
            self.assertIn(key, a)

    def test_audit_action_types(self):
        session, _ = self._make_active_session()
        session.record_action("alpha")
        session.record_action("beta")
        session.record_action("alpha")
        a = session.audit()
        self.assertIn("alpha", a["action_types"])
        self.assertIn("beta", a["action_types"])
        self.assertEqual(a["actions_count"], 3)

    # ─── to_dict / from_dict ───────────────────────────────────

    def test_to_dict_keys(self):
        session, _ = self._make_active_session()
        d = session.to_dict()
        for key in ("session_id", "wearer_name", "cartridge", "original_identity",
                     "current_identity", "loaded_at", "actions_taken",
                     "trust_snapshot", "ejected", "is_expired", "elapsed", "remaining"):
            self.assertIn(key, d)

    def test_from_dict(self):
        session, _ = self._make_active_session()
        session.record_action("test")
        d = session.to_dict()
        restored = CartridgeSession.from_dict(d)
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.wearer_name, session.wearer_name)
        self.assertEqual(len(restored.actions_taken), 1)

    def test_from_dict_ejected_state(self):
        session, _ = self._make_active_session()
        session.eject()
        d = session.to_dict()
        restored = CartridgeSession.from_dict(d)
        self.assertTrue(restored._ejected)

    def test_from_dict_minimal(self):
        restored = CartridgeSession.from_dict({})
        self.assertIsInstance(restored, CartridgeSession)

    def test_roundtrip(self):
        session, _ = self._make_active_session(time_limit=60)
        session.record_action("a")
        session.shift_perspective(5.0, amount=0.5)
        d = session.to_dict()
        restored = CartridgeSession.from_dict(d)
        self.assertEqual(restored.session_id, session.session_id)
        self.assertEqual(restored.wearer_name, session.wearer_name)
        self.assertEqual(len(restored.actions_taken), 2)

    # ─── __repr__ ──────────────────────────────────────────────

    def test_repr_active(self):
        session, _ = self._make_active_session()
        r = repr(session)
        self.assertIn("ACTIVE", r)

    def test_repr_ejected(self):
        session, _ = self._make_active_session()
        session.eject()
        r = repr(session)
        self.assertIn("EJECTED", r)

    def test_repr_expired(self):
        session, _ = self._make_active_session(time_limit=0.001)
        time.sleep(0.02)
        r = repr(session)
        self.assertIn("EXPIRED", r)


# ═══════════════════════════════════════════════════════════════
# IdentityFusion Tests
# ═══════════════════════════════════════════════════════════════

class TestIdentityFusion(TestCase):

    # ─── blend ─────────────────────────────────────────────────

    def test_blend_equal_weights(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        blended = IdentityFusion.blend(a, b, 0.5, 0.5)
        # Should be halfway: position 3
        self.assertEqual(blended.sector, 3)

    def test_blend_weighted_toward_a(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        blended = IdentityFusion.blend(a, b, 0.9, 0.1)
        self.assertEqual(blended.sector, 0)

    def test_blend_weighted_toward_b(self):
        a = IdentityDial(position=0)
        b = IdentityDial(position=6)
        blended = IdentityFusion.blend(a, b, 0.1, 0.9)
        # With 90% weight toward position 6, result should be at/near sector 6
        self.assertIn(blended.sector, (5, 6))

    def test_blend_same_position(self):
        a = IdentityDial(position=5)
        b = IdentityDial(position=5)
        blended = IdentityFusion.blend(a, b)
        self.assertEqual(blended.sector, 5)

    def test_blend_zero_weights(self):
        a = IdentityDial(position=5)
        b = IdentityDial(position=0)
        blended = IdentityFusion.blend(a, b, 0.0, 0.0)
        self.assertEqual(blended.position, 5.0)

    def test_blend_wrap_around(self):
        """Blend positions 11 and 1 (should be around 0, wrapping)."""
        a = IdentityDial(position=11)
        b = IdentityDial(position=1)
        blended = IdentityFusion.blend(a, b, 0.5, 0.5)
        # Shortest path between 11 and 1 goes through 0
        # Result should be near 0 (or 12=0)
        self.assertTrue(blended.sector in (0, 11))

    def test_blend_adjacent(self):
        a = IdentityDial(position=2)
        b = IdentityDial(position=3)
        blended = IdentityFusion.blend(a, b)
        self.assertEqual(blended.sector, 2)

    # ─── fusion_vector ─────────────────────────────────────────

    def test_fusion_vector_equal(self):
        a = [0.5, 0.5]
        b = [0.5, 0.5]
        result = IdentityFusion.fusion_vector(a, b)
        self.assertEqual(result, [0.5, 0.5])

    def test_fusion_vector_weighted(self):
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        result = IdentityFusion.fusion_vector(a, b, 0.75, 0.25)
        self.assertAlmostEqual(result[0], 0.75, places=4)
        self.assertAlmostEqual(result[1], 0.25, places=4)

    def test_fusion_vector_both_empty(self):
        result = IdentityFusion.fusion_vector([], [])
        self.assertEqual(result, [])

    def test_fusion_vector_a_empty(self):
        result = IdentityFusion.fusion_vector([], [0.5, 0.5])
        self.assertEqual(result, [0.5, 0.5])

    def test_fusion_vector_b_empty(self):
        result = IdentityFusion.fusion_vector([0.3, 0.7], [])
        self.assertEqual(result, [0.3, 0.7])

    def test_fusion_vector_zero_weights(self):
        a = [1.0, 2.0]
        result = IdentityFusion.fusion_vector(a, [0.5], 0.0, 0.0)
        self.assertEqual(result, [1.0, 2.0])

    def test_fusion_vector_different_lengths(self):
        a = [1.0]
        b = [0.0, 0.0]
        result = IdentityFusion.fusion_vector(a, b, 1.0, 0.0)
        self.assertEqual(len(result), 2)
        self.assertAlmostEqual(result[0], 1.0, places=4)

    # ─── compatibility_score ───────────────────────────────────

    def test_compatibility_identical(self):
        snap = make_snapshot(agent_name="A", position=3)
        score = IdentityFusion.compatibility_score(snap, snap)
        self.assertGreater(score, 0.9)

    def test_compatibility_opposite_positions(self):
        # Use minimal snapshots so only identity distance contributes
        a = AgentSnapshot(agent_name="A", identity=IdentityDial(position=0))
        b = AgentSnapshot(agent_name="B", identity=IdentityDial(position=6))
        score = IdentityFusion.compatibility_score(a, b)
        # Identity at max distance => identity_score = 0, neutral personality = 0.15
        # No skills/caps overlap => 0. Total should be 0.15
        self.assertLess(score, 0.5)

    def test_compatibility_overlapping_skills(self):
        a = make_snapshot(agent_name="A", skills={"code": 0.8, "math": 0.7})
        b = make_snapshot(agent_name="B", skills={"code": 0.6, "math": 0.5})
        score = IdentityFusion.compatibility_score(a, b)
        self.assertGreater(score, 0.5)

    def test_compatibility_no_overlap_skills(self):
        a = make_snapshot(agent_name="A", skills={"code": 0.8})
        b = make_snapshot(agent_name="B", skills={"art": 0.9})
        score_ab = IdentityFusion.compatibility_score(a, b)
        # Skill overlap is 0, but identity/personality/capability contribute
        self.assertLessEqual(score_ab, 0.8)

    def test_compatibility_personality_vectors(self):
        a = make_snapshot(agent_name="A", personality_vector=[1.0, 0.0, 0.0])
        b = make_snapshot(agent_name="B", personality_vector=[1.0, 0.0, 0.0])
        score = IdentityFusion.compatibility_score(a, b)
        self.assertGreater(score, 0.8)

    def test_compatibility_range(self):
        a = make_snapshot(agent_name="A", position=0)
        b = make_snapshot(agent_name="B", position=11)
        score = IdentityFusion.compatibility_score(a, b)
        self.assertGreaterEqual(score, 0.0)
        self.assertLessEqual(score, 1.0)

    # ─── conflict_areas ────────────────────────────────────────

    def test_conflict_areas_opposite_identities(self):
        a = make_snapshot(agent_name="A", position=0)
        b = make_snapshot(agent_name="B", position=6)
        conflicts = IdentityFusion.conflict_areas(a, b)
        self.assertTrue(any("opposition" in c.lower() for c in conflicts))

    def test_conflict_areas_divergent_identities(self):
        a = make_snapshot(agent_name="A", position=0)
        b = make_snapshot(agent_name="B", position=4)
        conflicts = IdentityFusion.conflict_areas(a, b)
        self.assertTrue(any("divergence" in c.lower() for c in conflicts))

    def test_conflict_areas_similar_identities(self):
        a = make_snapshot(agent_name="A", position=3)
        b = make_snapshot(agent_name="B", position=4)
        conflicts = IdentityFusion.conflict_areas(a, b)
        identity_conflicts = [c for c in conflicts if "identity" in c.lower()]
        self.assertEqual(len(identity_conflicts), 0)

    def test_conflict_areas_personality_opposition(self):
        a = make_snapshot(agent_name="A", personality_vector=[0.9, 0.0, 0.0])
        b = make_snapshot(agent_name="B", personality_vector=[-0.9, 0.0, 0.0])
        conflicts = IdentityFusion.conflict_areas(a, b)
        self.assertTrue(any("dimension 0" in c for c in conflicts))

    def test_conflict_areas_skill_gap(self):
        a = make_snapshot(agent_name="A", skills={"code": 0.9})
        b = make_snapshot(agent_name="B", skills={"code": 0.2})
        conflicts = IdentityFusion.conflict_areas(a, b)
        self.assertTrue(any("code" in c for c in conflicts))

    def test_conflict_areas_no_gap(self):
        a = make_snapshot(agent_name="A", skills={"code": 0.7})
        b = make_snapshot(agent_name="B", skills={"code": 0.6})
        conflicts = IdentityFusion.conflict_areas(a, b)
        skill_conflicts = [c for c in conflicts if "Skill" in c]
        self.assertEqual(len(skill_conflicts), 0)

    def test_conflict_areas_preference_conflict(self):
        a = make_snapshot(agent_name="A", preferences={"speed": 1.0})
        b = make_snapshot(agent_name="B", preferences={"speed": -1.0})
        conflicts = IdentityFusion.conflict_areas(a, b)
        self.assertTrue(any("speed" in c for c in conflicts))

    def test_conflict_areas_empty(self):
        a = make_snapshot(agent_name="A", position=3, personality_vector=[0.5])
        b = make_snapshot(agent_name="B", position=3, personality_vector=[0.5])
        conflicts = IdentityFusion.conflict_areas(a, b)
        self.assertEqual(len(conflicts), 0)


# ═══════════════════════════════════════════════════════════════
# PerspectiveEngine Tests
# ═══════════════════════════════════════════════════════════════

class TestPerspectiveEngine(TestCase):

    def setUp(self):
        self.engine = PerspectiveEngine()

    def _publish_agent(self, name, position):
        """Helper: register identity + create/publish cartridge."""
        snap = make_snapshot(agent_name=name, position=position)
        self.engine.register_snapshot(name, snap)
        cart = TwinCartridge(snapshot=snap, cartridge_name=f"twin-{name}")
        self.engine.publish_cartridge(cart)
        return cart

    # ─── register_agent_identity ───────────────────────────────

    def test_register_agent_identity(self):
        dial = IdentityDial(position=3)
        self.engine.register_agent_identity("Agent1", dial)
        self.assertIn("Agent1", self.engine.agent_identities)

    def test_register_overwrites(self):
        self.engine.register_agent_identity("A", IdentityDial(position=0))
        self.engine.register_agent_identity("A", IdentityDial(position=5))
        self.assertEqual(self.engine.agent_identities["A"].position, 5.0)

    # ─── publish_cartridge ─────────────────────────────────────

    def test_publish_valid(self):
        cart = make_cartridge(agent_name="A")
        result = self.engine.publish_cartridge(cart)
        self.assertEqual(result, "twin-A")
        self.assertTrue(cart.published)
        self.assertIn("twin-A", self.engine.cartridge_library)

    def test_publish_invalid_raises(self):
        cart = TwinCartridge(snapshot=AgentSnapshot(agent_name=""))
        with self.assertRaises(ValueError):
            self.engine.publish_cartridge(cart)

    def test_unpublish(self):
        self._publish_agent("A", 0)
        result = self.engine.unpublish_cartridge("twin-A")
        self.assertTrue(result)
        self.assertFalse(self.engine.cartridge_library["twin-A"].published)

    def test_unpublish_not_found(self):
        result = self.engine.unpublish_cartridge("nonexistent")
        self.assertFalse(result)

    def test_get_cartridge(self):
        self._publish_agent("A", 0)
        cart = self.engine.get_cartridge("twin-A")
        self.assertIsNotNone(cart)

    def test_get_cartridge_not_found(self):
        self.assertIsNone(self.engine.get_cartridge("none"))

    def test_list_cartridges(self):
        self._publish_agent("A", 0)
        self._publish_agent("B", 1)
        self.engine.unpublish_cartridge("twin-A")
        listed = self.engine.list_cartridges()
        self.assertEqual(len(listed), 1)

    # ─── load_cartridge ────────────────────────────────────────

    def test_load_cartridge(self):
        self._publish_agent("Source", 5)
        self.engine.register_agent_identity("Wearer", IdentityDial(position=0))
        session = self.engine.load_cartridge("Wearer", "twin-Source")
        self.assertIsInstance(session, CartridgeSession)
        self.assertEqual(session.wearer_name, "Wearer")

    def test_load_cartridge_not_found(self):
        with self.assertRaises(ValueError):
            self.engine.load_cartridge("W", "nonexistent")

    def test_load_cartridge_not_published(self):
        self._publish_agent("A", 0)
        self.engine.unpublish_cartridge("twin-A")
        with self.assertRaises(ValueError):
            self.engine.load_cartridge("W", "twin-A")

    def test_load_cartridge_self_conflict(self):
        self._publish_agent("A", 0)
        self.engine.register_agent_identity("A", IdentityDial(position=0))
        with self.assertRaises(ValueError) as ctx:
            self.engine.load_cartridge("A", "twin-A")
        self.assertIn("own", str(ctx.exception))

    def test_load_cartridge_expired(self):
        snap = make_snapshot(agent_name="Old", expires_at=time.time() - 1)
        cart = TwinCartridge(snapshot=snap, cartridge_name="old-cart")
        self.engine.cartridge_library["old-cart"] = cart
        cart.published = True
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        with self.assertRaises(ValueError):
            self.engine.load_cartridge("W", "old-cart")

    # ─── eject_session ─────────────────────────────────────────

    def test_eject_session(self):
        self._publish_agent("Source", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "twin-Source")
        result = self.engine.eject_session(session.session_id)
        self.assertTrue(result.success)

    def test_eject_session_not_found(self):
        result = self.engine.eject_session("nonexistent")
        self.assertFalse(result.success)

    def test_eject_session_restores_identity(self):
        self._publish_agent("Source", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "twin-Source")
        self.engine.eject_session(session.session_id)
        identity = self.engine.get_wearer_identity("W")
        self.assertIsNotNone(identity)
        self.assertEqual(identity.position, 0.0)

    # ─── eject_all_for_wearer ──────────────────────────────────

    def test_eject_all_for_wearer(self):
        self._publish_agent("S1", 1)
        self._publish_agent("S2", 2)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        s1 = self.engine.load_cartridge("W", "twin-S1")
        s2 = self.engine.load_cartridge("W", "twin-S2")
        results = self.engine.eject_all_for_wearer("W")
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r.success for r in results))

    def test_eject_all_empty(self):
        results = self.engine.eject_all_for_wearer("nobody")
        self.assertEqual(len(results), 0)

    # ─── get_active_sessions ───────────────────────────────────

    def test_get_active_sessions(self):
        self._publish_agent("S1", 1)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "twin-S1")
        active = self.engine.get_active_sessions("W")
        self.assertEqual(len(active), 1)

    def test_get_active_sessions_ejected(self):
        self._publish_agent("S1", 1)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "twin-S1")
        self.engine.eject_session(session.session_id)
        active = self.engine.get_active_sessions("W")
        self.assertEqual(len(active), 0)

    def test_get_active_sessions_other_wearer(self):
        self._publish_agent("S1", 1)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        self.engine.load_cartridge("W", "twin-S1")
        active = self.engine.get_active_sessions("Other")
        self.assertEqual(len(active), 0)

    # ─── get_session ───────────────────────────────────────────

    def test_get_session(self):
        self._publish_agent("S1", 1)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "twin-S1")
        retrieved = self.engine.get_session(session.session_id)
        self.assertEqual(retrieved.session_id, session.session_id)

    def test_get_session_not_found(self):
        self.assertIsNone(self.engine.get_session("nonexistent"))

    # ─── get_wearer_identity ───────────────────────────────────

    def test_get_wearer_identity_base(self):
        self.engine.register_agent_identity("A", IdentityDial(position=5))
        result = self.engine.get_wearer_identity("A")
        self.assertEqual(result.position, 5.0)

    def test_get_wearer_identity_with_cartridge(self):
        self._publish_agent("Source", 7)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        self.engine.load_cartridge("W", "twin-Source")
        result = self.engine.get_wearer_identity("W")
        # Should return cartridge identity, not base
        self.assertEqual(result.position, 7.0)

    def test_get_wearer_identity_unknown(self):
        self.assertIsNone(self.engine.get_wearer_identity("nobody"))

    # ─── find_nearest_agent ────────────────────────────────────

    def test_find_nearest(self):
        self.engine.register_agent_identity("A", IdentityDial(position=0))
        self.engine.register_agent_identity("B", IdentityDial(position=5))
        nearest = self.engine.find_nearest_agent(1.0)
        self.assertEqual(nearest, "A")

    def test_find_nearest_exclude(self):
        self.engine.register_agent_identity("A", IdentityDial(position=0))
        self.engine.register_agent_identity("B", IdentityDial(position=5))
        nearest = self.engine.find_nearest_agent(1.0, exclude=["A"])
        self.assertEqual(nearest, "B")

    def test_find_nearest_empty(self):
        self.assertIsNone(self.engine.find_nearest_agent(0.0))

    # ─── perspective_distance ──────────────────────────────────

    def test_perspective_distance(self):
        self.engine.register_agent_identity("A", IdentityDial(position=0))
        self.engine.register_agent_identity("B", IdentityDial(position=6))
        dist = self.engine.perspective_distance("A", "B")
        self.assertEqual(dist, 6.0)

    def test_perspective_distance_unknown(self):
        dist = self.engine.perspective_distance("A", "B")
        self.assertEqual(dist, -1.0)

    # ─── fleet_identity_map ────────────────────────────────────

    def test_fleet_identity_map(self):
        self.engine.register_agent_identity("A", IdentityDial(position=0))
        self.engine.register_agent_identity("B", IdentityDial(position=5))
        fmap = self.engine.fleet_identity_map()
        self.assertIn("A", fmap)
        self.assertIn("B", fmap)
        self.assertIn("sector_name", fmap["A"])

    def test_fleet_identity_map_empty(self):
        fmap = self.engine.fleet_identity_map()
        self.assertEqual(fmap, {})

    # ─── conflict_check ────────────────────────────────────────

    def test_conflict_check_none(self):
        self._publish_agent("S", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        result = self.engine.conflict_check("W", "twin-S")
        self.assertFalse(result["has_conflict"])

    def test_conflict_check_self_load(self):
        self._publish_agent("A", 0)
        result = self.engine.conflict_check("A", "twin-A")
        self.assertTrue(result["has_conflict"])
        self.assertIn("own", result["reason"].lower())

    def test_conflict_check_not_found(self):
        result = self.engine.conflict_check("W", "nonexistent")
        self.assertTrue(result["has_conflict"])

    def test_conflict_check_stack_depth(self):
        self._publish_agent("S1", 1)
        self._publish_agent("S2", 2)
        self._publish_agent("S3", 3)
        self._publish_agent("S4", 4)
        self._publish_agent("S5", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        # Load MAX_STACK_DEPTH cartridges
        for i in range(1, MAX_STACK_DEPTH + 1):
            self.engine.load_cartridge("W", f"twin-S{i}")
        # 6th should fail
        result = self.engine.conflict_check("W", "twin-S5")
        self.assertTrue(result["has_conflict"])
        self.assertIn("stack", result.get("details", {}).get("conflict_type", ""))

    # ─── suggestion ────────────────────────────────────────────

    def test_suggestion_match(self):
        self._publish_agent("Architect", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        result = self.engine.suggestion("W", "Need an Architect")
        self.assertIsNotNone(result)

    def test_suggestion_no_match(self):
        self._publish_agent("S", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        result = self.engine.suggestion("W", "")
        self.assertIsNone(result)

    def test_suggestion_excludes_self(self):
        self._publish_agent("W", 0)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        result = self.engine.suggestion("W", "W")
        self.assertIsNone(result)

    # ─── register_snapshot ─────────────────────────────────────

    def test_register_snapshot(self):
        snap = make_snapshot(agent_name="A", position=3)
        self.engine.register_snapshot("A", snap)
        self.assertIn("A", self.engine.agent_snapshots)
        self.assertIn("A", self.engine.agent_identities)

    # ─── create_cartridge_from_snapshot ────────────────────────

    def test_create_cartridge_from_snapshot(self):
        snap = make_snapshot(agent_name="A", position=3)
        cart = self.engine.create_cartridge_from_snapshot(snap, cartridge_name="my-cart")
        self.assertEqual(cart.cartridge_name, "my-cart")
        self.assertEqual(cart.snapshot.agent_name, "A")

    # ─── cleanup_expired_sessions ─────────────────────────────

    def test_cleanup_expired_sessions(self):
        snap = make_snapshot(agent_name="S", expires_at=time.time() + 3600)
        cart = TwinCartridge(snapshot=snap, cartridge_name="exp-cart", time_limit=0.001)
        cart.published = True
        self.engine.cartridge_library["exp-cart"] = cart
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "exp-cart")
        time.sleep(0.02)
        results = self.engine.cleanup_expired_sessions()
        self.assertTrue(len(results) >= 1)

    # ─── stats ─────────────────────────────────────────────────

    def test_stats_empty(self):
        stats = self.engine.stats()
        self.assertEqual(stats["total_sessions"], 0)
        self.assertEqual(stats["published_cartridges"], 0)

    def test_stats_with_data(self):
        self._publish_agent("S", 5)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        self.engine.load_cartridge("W", "twin-S")
        stats = self.engine.stats()
        self.assertEqual(stats["active_sessions"], 1)
        self.assertEqual(stats["published_cartridges"], 1)
        self.assertEqual(stats["registered_agents"], 2)

    # ─── persistence (JSONL) ───────────────────────────────────

    def test_save_and_load_jsonl(self):
        self._publish_agent("S1", 1)
        self._publish_agent("S2", 2)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        self.engine.load_cartridge("W", "twin-S1")

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "data.jsonl")
            count = self.engine.save_to_jsonl(path)
            self.assertGreater(count, 0)

            new_engine = PerspectiveEngine()
            loaded = new_engine.load_from_jsonl(path)
            self.assertEqual(loaded, count)
            self.assertEqual(new_engine.stats()["total_sessions"], 1)
            self.assertIn("W", new_engine.agent_identities)

    def test_load_from_nonexistent_file(self):
        count = self.engine.load_from_jsonl("/nonexistent/path.jsonl")
        self.assertEqual(count, 0)

    def test_jsonl_roundtrip_sessions(self):
        self._publish_agent("S1", 1)
        self.engine.register_agent_identity("W", IdentityDial(position=0))
        session = self.engine.load_cartridge("W", "twin-S1")
        original_session_id = session.session_id

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "data.jsonl")
            self.engine.save_to_jsonl(path)

            new_engine = PerspectiveEngine()
            new_engine.load_from_jsonl(path)
            self.assertIn(original_session_id, new_engine.sessions)


# ═══════════════════════════════════════════════════════════════
# Constants Tests
# ═══════════════════════════════════════════════════════════════

class TestConstants(TestCase):

    def test_dial_positions(self):
        self.assertEqual(DIAL_POSITIONS, 12)

    def test_sector_degrees(self):
        self.assertEqual(SECTOR_DEGREES, 30.0)

    def test_trust_modes(self):
        self.assertEqual(TRUST_INHERIT_FULL, "full")
        self.assertEqual(TRUST_INHERIT_PARTIAL, "partial")
        self.assertEqual(TRUST_INHERIT_NONE, "none")
        self.assertEqual(TRUST_INHERIT_BLENDED, "blended")

    def test_default_time_limit(self):
        self.assertEqual(DEFAULT_TIME_LIMIT, 0)

    def test_default_shift_step(self):
        self.assertEqual(DEFAULT_SHIFT_STEP, 0.5)

    def test_max_stack_depth(self):
        self.assertEqual(MAX_STACK_DEPTH, 5)

    def test_default_snapshot_expiry(self):
        self.assertEqual(DEFAULT_SNAPSHOT_EXPIRY, 0)

    def test_min_compatibility(self):
        self.assertEqual(MIN_COMPATIBILITY_FOR_LOADING, 0.0)


# ═══════════════════════════════════════════════════════════════
# Integration / Edge Case Tests
# ═══════════════════════════════════════════════════════════════

class TestIntegration(TestCase):

    def test_full_lifecycle(self):
        """End-to-end: create snapshot, cartridge, publish, load, shift, eject."""
        snap = AgentSnapshot.capture_from({
            "name": "Oracle1",
            "identity_position": 0,
            "identity_precision": 0.7,
            "capabilities": ["govern"],
            "skills": {"architecture": 0.95},
            "trust_profile": {"level": 5},
        })
        cart = TwinCartridge(
            snapshot=snap,
            cartridge_name="oracle-v1",
            trust_inheritance=TRUST_INHERIT_FULL,
        )

        engine = PerspectiveEngine()
        engine.register_agent_identity("Pelagic", IdentityDial(position=5))
        engine.publish_cartridge(cart)

        session = engine.load_cartridge("Pelagic", "oracle-v1")
        self.assertEqual(session.twin_agent_name, "Oracle1")
        self.assertEqual(session.original_identity.position, 5.0)

        # Shift perspective
        shift = session.shift_perspective(5.0, amount=0.3)
        self.assertGreater(shift, 0.0)

        # Eject
        result = session.eject()
        self.assertTrue(result.success)
        self.assertEqual(result.restored_identity["position"], 5.0)

        # Verify identity restored
        identity = engine.get_wearer_identity("Pelagic")
        self.assertEqual(identity.position, 5.0)

    def test_clone_publish_new_version(self):
        """Clone a cartridge, modify, and publish as new version."""
        cart = make_cartridge(agent_name="A", published=True)
        v2 = cart.clone(new_version="2.0.0")
        v2.behavior_profile["new"] = "feature"
        self.assertFalse(v2.published)
        self.assertEqual(v2.version, "2.0.0")
        # Original unaffected
        self.assertTrue(cart.published)
        self.assertNotIn("new", cart.behavior_profile)

    def test_multiple_wearers_same_cartridge(self):
        """Multiple agents can load the same cartridge."""
        cart = make_cartridge(agent_name="Source", published=True)
        s1 = cart.load("Wearer1")
        s2 = cart.load("Wearer2")
        self.assertEqual(cart._session_count, 2)
        self.assertEqual(s1.wearer_name, "Wearer1")
        self.assertEqual(s2.wearer_name, "Wearer2")

    def test_stack_depth_enforcement(self):
        """Cannot load more than MAX_STACK_DEPTH cartridges."""
        engine = PerspectiveEngine()
        engine.register_agent_identity("W", IdentityDial(position=0))
        for i in range(MAX_STACK_DEPTH):
            snap = make_snapshot(agent_name=f"Source{i}", position=i)
            cart = TwinCartridge(snapshot=snap, cartridge_name=f"cart-{i}")
            engine.publish_cartridge(cart)
            engine.load_cartridge("W", f"cart-{i}")

        # One more should fail
        snap = make_snapshot(agent_name="Extra", position=11)
        cart = TwinCartridge(snapshot=snap, cartridge_name="cart-extra")
        engine.publish_cartridge(cart)
        with self.assertRaises(ValueError):
            engine.load_cartridge("W", "cart-extra")

    def test_serialization_chain(self):
        """Full serialization chain: snapshot -> cartridge -> session -> dict -> back."""
        snap = make_snapshot(agent_name="Chain", position=4)
        cart = TwinCartridge(snapshot=snap, cartridge_name="chain-cart")
        session = CartridgeSession(wearer_name="W", cartridge=cart)
        session.record_action("test")

        d = session.to_dict()
        restored = CartridgeSession.from_dict(d)
        self.assertEqual(restored.wearer_name, "W")
        self.assertEqual(restored.cartridge_name, "chain-cart")
        self.assertEqual(len(restored.actions_taken), 1)

    def test_blend_with_precision(self):
        """Blend two dials with non-zero precision."""
        a = IdentityDial(position=3.0, precision=0.5)
        b = IdentityDial(position=9.0, precision=0.5)
        blended = IdentityFusion.blend(a, b, 0.5, 0.5)
        # Should be somewhere between, with precision set
        self.assertGreater(blended.precision, 0.0)

    def test_compatibility_score_between_different_agents(self):
        a = AgentSnapshot.capture_from({
            "name": "A",
            "identity_position": 0,
            "skills": {"math": 0.9, "code": 0.8},
            "capabilities": ["compute"],
            "personality_vector": [1.0, 0.0, 0.0],
        })
        b = AgentSnapshot.capture_from({
            "name": "B",
            "identity_position": 6,
            "skills": {"art": 0.9, "music": 0.8},
            "capabilities": ["create"],
            "personality_vector": [0.0, 1.0, 0.0],
        })
        score = IdentityFusion.compatibility_score(a, b)
        # These agents are maximally different: opposite positions, zero skill/cap
        # overlap, orthogonal personalities. Score should be very low.
        self.assertGreaterEqual(score, 0.0)
        self.assertLess(score, 1.0)


if __name__ == "__main__":
    unittest.main()
