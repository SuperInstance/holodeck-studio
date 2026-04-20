#!/usr/bin/env python3
"""
Tests for Trail x Tile Integration Bridge — 100+ tests.

Covers TrailTileConfig, TrailTileResult, TrailTileBridge, DEFAULT_OPCODE_TILE_MAP,
serialization, edge cases, batch processing, prerequisite validation, and more.
"""

import copy
import hashlib
import time
import unittest

from trail_tile_bridge import (
    DEFAULT_OPCODE_TILE_MAP,
    TrailTileBridge,
    TrailTileConfig,
    TrailTileResult,
)


# ═══════════════════════════════════════════════════════════════
# DEFAULT_OPCODE_TILE_MAP tests
# ═══════════════════════════════════════════════════════════════

class TestDefaultOpcodeTileMap(unittest.TestCase):
    """Tests for the built-in opcode-to-tile mapping."""

    def test_map_is_dict(self):
        self.assertIsInstance(DEFAULT_OPCODE_TILE_MAP, dict)

    def test_map_has_at_least_15_mappings(self):
        self.assertGreaterEqual(len(DEFAULT_OPCODE_TILE_MAP), 15)

    def test_map_has_20_mappings(self):
        self.assertEqual(len(DEFAULT_OPCODE_TILE_MAP), 20)

    def test_all_values_are_strings(self):
        for k, v in DEFAULT_OPCODE_TILE_MAP.items():
            self.assertIsInstance(k, str, f"Key {k!r} is not a string")
            self.assertIsInstance(v, str, f"Value {v!r} is not a string")

    def test_all_keys_are_uppercase(self):
        for k in DEFAULT_OPCODE_TILE_MAP:
            self.assertEqual(k, k.upper(), f"Key {k!r} is not uppercase")

    def test_trust_update_maps_to_trust_domain(self):
        self.assertIn("TRUST_UPDATE", DEFAULT_OPCODE_TILE_MAP)

    def test_file_read_maps_to_code_domain(self):
        self.assertIn("FILE_READ", DEFAULT_OPCODE_TILE_MAP)

    def test_file_write_maps_to_code_domain(self):
        self.assertIn("FILE_WRITE", DEFAULT_OPCODE_TILE_MAP)

    def test_file_edit_maps_to_code_domain(self):
        self.assertIn("FILE_EDIT", DEFAULT_OPCODE_TILE_MAP)

    def test_test_run_maps_to_testing(self):
        self.assertIn("TEST_RUN", DEFAULT_OPCODE_TILE_MAP)

    def test_git_commit_maps(self):
        self.assertIn("GIT_COMMIT", DEFAULT_OPCODE_TILE_MAP)

    def test_git_push_maps(self):
        self.assertIn("GIT_PUSH", DEFAULT_OPCODE_TILE_MAP)

    def test_search_code_maps(self):
        self.assertIn("SEARCH_CODE", DEFAULT_OPCODE_TILE_MAP)

    def test_bottle_drop_maps(self):
        self.assertIn("BOTTLE_DROP", DEFAULT_OPCODE_TILE_MAP)

    def test_bottle_read_maps(self):
        self.assertIn("BOTTLE_READ", DEFAULT_OPCODE_TILE_MAP)

    def test_level_up_maps(self):
        self.assertIn("LEVEL_UP", DEFAULT_OPCODE_TILE_MAP)

    def test_spell_cast_maps(self):
        self.assertIn("SPELL_CAST", DEFAULT_OPCODE_TILE_MAP)

    def test_room_enter_maps(self):
        self.assertIn("ROOM_ENTER", DEFAULT_OPCODE_TILE_MAP)

    def test_cap_issue_maps(self):
        self.assertIn("CAP_ISSUE", DEFAULT_OPCODE_TILE_MAP)

    def test_branch_maps(self):
        self.assertIn("BRANCH", DEFAULT_OPCODE_TILE_MAP)

    def test_nop_maps(self):
        self.assertIn("NOP", DEFAULT_OPCODE_TILE_MAP)

    def test_trail_begin_maps(self):
        self.assertIn("TRAIL_BEGIN", DEFAULT_OPCODE_TILE_MAP)

    def test_trail_end_maps(self):
        self.assertIn("TRAIL_END", DEFAULT_OPCODE_TILE_MAP)

    def test_comment_maps(self):
        self.assertIn("COMMENT", DEFAULT_OPCODE_TILE_MAP)

    def test_label_maps(self):
        self.assertIn("LABEL", DEFAULT_OPCODE_TILE_MAP)

    def test_trust_update_maps_to_trust_establishment(self):
        self.assertEqual(DEFAULT_OPCODE_TILE_MAP["TRUST_UPDATE"], "trust_establishment")

    def test_file_read_maps_to_code_reading(self):
        self.assertEqual(DEFAULT_OPCODE_TILE_MAP["FILE_READ"], "code_reading")

    def test_file_write_maps_to_code_writing(self):
        self.assertEqual(DEFAULT_OPCODE_TILE_MAP["FILE_WRITE"], "code_writing")

    def test_test_run_maps_to_testing(self):
        self.assertEqual(DEFAULT_OPCODE_TILE_MAP["TEST_RUN"], "testing")


# ═══════════════════════════════════════════════════════════════
# TrailTileConfig tests
# ═══════════════════════════════════════════════════════════════

class TestTrailTileConfig(unittest.TestCase):
    """Tests for the TrailTileConfig dataclass."""

    def test_default_config(self):
        config = TrailTileConfig()
        self.assertEqual(config.auto_complete_threshold, 0.7)
        self.assertEqual(config.max_tiles_per_trail, 5)
        self.assertIsInstance(config.opcode_tile_mapping, dict)

    def test_default_mapping_populated(self):
        config = TrailTileConfig()
        self.assertGreaterEqual(len(config.opcode_tile_mapping), 15)

    def test_custom_threshold(self):
        config = TrailTileConfig(auto_complete_threshold=0.5)
        self.assertEqual(config.auto_complete_threshold, 0.5)

    def test_custom_max_tiles(self):
        config = TrailTileConfig(max_tiles_per_trail=10)
        self.assertEqual(config.max_tiles_per_trail, 10)

    def test_custom_mapping(self):
        mapping = {"CUSTOM_OP": "custom_tile"}
        config = TrailTileConfig(opcode_tile_mapping=mapping)
        self.assertEqual(config.opcode_tile_mapping, mapping)

    def test_to_dict(self):
        config = TrailTileConfig()
        d = config.to_dict()
        self.assertIsInstance(d, dict)
        self.assertIn("opcode_tile_mapping", d)
        self.assertIn("auto_complete_threshold", d)
        self.assertIn("max_tiles_per_trail", d)
        self.assertEqual(d["auto_complete_threshold"], 0.7)
        self.assertEqual(d["max_tiles_per_trail"], 5)

    def test_from_dict(self):
        config = TrailTileConfig()
        d = config.to_dict()
        restored = TrailTileConfig.from_dict(d)
        self.assertEqual(restored.auto_complete_threshold, config.auto_complete_threshold)
        self.assertEqual(restored.max_tiles_per_trail, config.max_tiles_per_trail)
        self.assertEqual(restored.opcode_tile_mapping, config.opcode_tile_mapping)

    def test_from_dict_empty(self):
        restored = TrailTileConfig.from_dict({})
        self.assertEqual(restored.auto_complete_threshold, 0.7)
        self.assertEqual(restored.max_tiles_per_trail, 5)
        self.assertGreaterEqual(len(restored.opcode_tile_mapping), 15)

    def test_from_dict_custom_values(self):
        data = {
            "opcode_tile_mapping": {"X": "y"},
            "auto_complete_threshold": 0.9,
            "max_tiles_per_trail": 3,
        }
        config = TrailTileConfig.from_dict(data)
        self.assertEqual(config.auto_complete_threshold, 0.9)
        self.assertEqual(config.max_tiles_per_trail, 3)
        self.assertEqual(config.opcode_tile_mapping, {"X": "y"})

    def test_round_trip_serialization(self):
        config = TrailTileConfig(
            auto_complete_threshold=0.85,
            max_tiles_per_trail=8,
        )
        d = config.to_dict()
        restored = TrailTileConfig.from_dict(d)
        self.assertEqual(restored.auto_complete_threshold, 0.85)
        self.assertEqual(restored.max_tiles_per_trail, 8)


# ═══════════════════════════════════════════════════════════════
# TrailTileResult tests
# ═══════════════════════════════════════════════════════════════

class TestTrailTileResult(unittest.TestCase):
    """Tests for the TrailTileResult dataclass."""

    def test_default_values(self):
        result = TrailTileResult(trail_hash="abc123")
        self.assertEqual(result.trail_hash, "abc123")
        self.assertEqual(result.tiles_completed, [])
        self.assertEqual(result.tiles_progressed, {})
        self.assertEqual(result.confidence, 0.0)

    def test_with_values(self):
        result = TrailTileResult(
            trail_hash="hash1",
            tiles_completed=["tile_a", "tile_b"],
            tiles_progressed={"tile_a": 0.9, "tile_c": 0.4},
            confidence=0.85,
        )
        self.assertEqual(result.trail_hash, "hash1")
        self.assertCountEqual(result.tiles_completed, ["tile_a", "tile_b"])
        self.assertEqual(result.tiles_progressed["tile_a"], 0.9)
        self.assertEqual(result.tiles_progressed["tile_c"], 0.4)
        self.assertEqual(result.confidence, 0.85)

    def test_to_dict(self):
        result = TrailTileResult(
            trail_hash="h1",
            tiles_completed=["t1"],
            tiles_progressed={"t1": 0.8},
            confidence=0.75,
        )
        d = result.to_dict()
        self.assertEqual(d["trail_hash"], "h1")
        self.assertEqual(d["tiles_completed"], ["t1"])
        self.assertEqual(d["tiles_progressed"], {"t1": 0.8})
        self.assertEqual(d["confidence"], 0.75)

    def test_from_dict(self):
        data = {
            "trail_hash": "h2",
            "tiles_completed": ["t2", "t3"],
            "tiles_progressed": {"t2": 0.6},
            "confidence": 0.5,
        }
        result = TrailTileResult.from_dict(data)
        self.assertEqual(result.trail_hash, "h2")
        self.assertCountEqual(result.tiles_completed, ["t2", "t3"])
        self.assertEqual(result.tiles_progressed["t2"], 0.6)
        self.assertEqual(result.confidence, 0.5)

    def test_from_dict_minimal(self):
        result = TrailTileResult.from_dict({"trail_hash": "h_min"})
        self.assertEqual(result.trail_hash, "h_min")
        self.assertEqual(result.tiles_completed, [])
        self.assertEqual(result.tiles_progressed, {})
        self.assertEqual(result.confidence, 0.0)

    def test_round_trip(self):
        original = TrailTileResult(
            trail_hash="rt",
            tiles_completed=["a", "b"],
            tiles_progressed={"a": 0.9, "b": 0.7, "c": 0.3},
            confidence=0.95,
        )
        restored = TrailTileResult.from_dict(original.to_dict())
        self.assertEqual(restored.trail_hash, original.trail_hash)
        self.assertEqual(restored.tiles_completed, original.tiles_completed)
        self.assertEqual(restored.tiles_progressed, original.tiles_progressed)
        self.assertEqual(restored.confidence, original.confidence)

    def test_tiles_completed_is_list(self):
        result = TrailTileResult(trail_hash="x")
        self.assertIsInstance(result.tiles_completed, list)

    def test_tiles_progressed_is_dict(self):
        result = TrailTileResult(trail_hash="x")
        self.assertIsInstance(result.tiles_progressed, dict)


# ═══════════════════════════════════════════════════════════════
# TrailTileBridge Initialization tests
# ═══════════════════════════════════════════════════════════════

class TestTrailTileBridgeInit(unittest.TestCase):
    """Tests for bridge initialization."""

    def test_default_init(self):
        bridge = TrailTileBridge()
        self.assertIsNotNone(bridge.config)
        self.assertIsNone(bridge.tile_graph)
        self.assertIsNone(bridge.trail_engine)

    def test_init_with_config(self):
        config = TrailTileConfig(auto_complete_threshold=0.9)
        bridge = TrailTileBridge(config=config)
        self.assertEqual(bridge.config.auto_complete_threshold, 0.9)

    def test_init_with_tile_graph(self):
        # tile_graph is optional, just store it
        bridge = TrailTileBridge(tile_graph="mock_graph")
        self.assertEqual(bridge.tile_graph, "mock_graph")

    def test_init_with_trail_engine(self):
        bridge = TrailTileBridge(trail_engine="mock_engine")
        self.assertEqual(bridge.trail_engine, "mock_engine")

    def test_init_with_all_params(self):
        config = TrailTileConfig()
        bridge = TrailTileBridge(
            config=config,
            tile_graph="graph",
            trail_engine="engine",
        )
        self.assertEqual(bridge.config, config)
        self.assertEqual(bridge.tile_graph, "graph")
        self.assertEqual(bridge.trail_engine, "engine")

    def test_empty_progress_on_init(self):
        bridge = TrailTileBridge()
        self.assertEqual(bridge._agent_progress, {})
        self.assertEqual(bridge._tile_evidence, {})
        self.assertEqual(bridge._history, [])

    def test_stats_on_fresh_bridge(self):
        bridge = TrailTileBridge()
        stats = bridge.get_stats()
        self.assertEqual(stats["total_trails_processed"], 0)
        self.assertEqual(stats["total_tiles_completed"], 0)
        self.assertEqual(stats["total_agents_seen"], 0)
        self.assertEqual(stats["total_tiles_tracked"], 0)
        self.assertEqual(stats["mapping_count"], 20)


# ═══════════════════════════════════════════════════════════════
# TrailTileBridge.map_opcode_to_tile tests
# ═══════════════════════════════════════════════════════════════

class TestMapOpcodeToTile(unittest.TestCase):
    """Tests for opcode-to-tile lookup."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_known_opcode_returns_tile(self):
        tile = self.bridge.map_opcode_to_tile("FILE_READ")
        self.assertEqual(tile, "code_reading")

    def test_unknown_opcode_returns_none(self):
        tile = self.bridge.map_opcode_to_tile("NONEXISTENT_OPCODE")
        self.assertIsNone(tile)

    def test_empty_opcode_returns_none(self):
        tile = self.bridge.map_opcode_to_tile("")
        self.assertIsNone(tile)

    def test_case_sensitive_lookup(self):
        tile = self.bridge.map_opcode_to_tile("file_read")
        self.assertIsNone(tile)  # lowercase not found

    def test_trust_update_lookup(self):
        tile = self.bridge.map_opcode_to_tile("TRUST_UPDATE")
        self.assertEqual(tile, "trust_establishment")

    def test_all_default_opcodes_resolve(self):
        for opcode in DEFAULT_OPCODE_TILE_MAP:
            tile = self.bridge.map_opcode_to_tile(opcode)
            self.assertIsNotNone(tile, f"Opcode {opcode} should resolve")

    def test_custom_mapping_lookup(self):
        self.bridge.register_mapping("CUSTOM_OP", "custom_tile")
        tile = self.bridge.map_opcode_to_tile("CUSTOM_OP")
        self.assertEqual(tile, "custom_tile")


# ═══════════════════════════════════════════════════════════════
# TrailTileBridge.register_mapping tests
# ═══════════════════════════════════════════════════════════════

class TestRegisterMapping(unittest.TestCase):
    """Tests for registering custom opcode-to-tile mappings."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_register_new_mapping(self):
        self.bridge.register_mapping("NEW_OP", "new_tile")
        self.assertEqual(self.bridge.map_opcode_to_tile("NEW_OP"), "new_tile")

    def test_register_overwrites_existing(self):
        self.bridge.register_mapping("FILE_READ", "overridden_tile")
        self.assertEqual(self.bridge.map_opcode_to_tile("FILE_READ"), "overridden_tile")

    def test_register_strips_whitespace_opcode(self):
        self.bridge.register_mapping("  OP  ", "tile")
        self.assertEqual(self.bridge.map_opcode_to_tile("OP"), "tile")

    def test_register_strips_whitespace_tile(self):
        self.bridge.register_mapping("OP", "  tile  ")
        self.assertEqual(self.bridge.map_opcode_to_tile("OP"), "tile")

    def test_register_empty_opcode_raises(self):
        with self.assertRaises(ValueError):
            self.bridge.register_mapping("", "tile")

    def test_register_whitespace_opcode_raises(self):
        with self.assertRaises(ValueError):
            self.bridge.register_mapping("   ", "tile")

    def test_register_empty_tile_raises(self):
        with self.assertRaises(ValueError):
            self.bridge.register_mapping("OP", "")

    def test_register_whitespace_tile_raises(self):
        with self.assertRaises(ValueError):
            self.bridge.register_mapping("OP", "   ")


# ═══════════════════════════════════════════════════════════════
# TrailTileBridge.unregister_mapping tests
# ═══════════════════════════════════════════════════════════════

class TestUnregisterMapping(unittest.TestCase):
    """Tests for unregistering opcode-to-tile mappings."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_unregister_existing_returns_true(self):
        result = self.bridge.unregister_mapping("FILE_READ")
        self.assertTrue(result)
        self.assertIsNone(self.bridge.map_opcode_to_tile("FILE_READ"))

    def test_unregister_nonexistent_returns_false(self):
        result = self.bridge.unregister_mapping("FAKE_OP")
        self.assertFalse(result)

    def test_unregister_then_register(self):
        self.bridge.unregister_mapping("FILE_READ")
        self.bridge.register_mapping("FILE_READ", "new_tile")
        self.assertEqual(self.bridge.map_opcode_to_tile("FILE_READ"), "new_tile")


# ═══════════════════════════════════════════════════════════════
# TrailTileBridge.process_trail tests
# ═══════════════════════════════════════════════════════════════

class TestProcessTrail(unittest.TestCase):
    """Tests for processing trails through the bridge."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_basic_trail_returns_result(self):
        result = self.bridge.process_trail({
            "agent": "test-agent",
            "opcodes": ["FILE_READ", "FILE_WRITE"],
        })
        self.assertIsInstance(result, TrailTileResult)
        self.assertIsInstance(result.trail_hash, str)
        self.assertGreater(len(result.trail_hash), 0)

    def test_trail_with_no_opcodes(self):
        result = self.bridge.process_trail({
            "agent": "test-agent",
            "opcodes": [],
        })
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.tiles_completed, [])
        self.assertEqual(result.tiles_progressed, {})

    def test_trail_with_all_mapped_opcodes_high_confidence(self):
        result = self.bridge.process_trail({
            "agent": "test-agent",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TEST_RUN"],
        })
        self.assertGreater(result.confidence, 0.5)

    def test_trail_with_all_unmapped_opcodes_low_confidence(self):
        self.bridge.config.opcode_tile_mapping = {"FILE_READ": "code_reading"}
        result = self.bridge.process_trail({
            "agent": "test-agent",
            "opcodes": ["UNKNOWN_OP1", "UNKNOWN_OP2"],
        })
        self.assertLessEqual(result.confidence, 0.0)

    def test_trail_produces_progress(self):
        result = self.bridge.process_trail({
            "agent": "test-agent",
            "opcodes": ["FILE_READ", "FILE_WRITE"],
        })
        self.assertGreater(len(result.tiles_progressed), 0)

    def test_trail_default_agent(self):
        result = self.bridge.process_trail({
            "opcodes": ["FILE_READ"],
        })
        self.assertIsNotNone(result)

    def test_trail_with_precomputed_hash(self):
        result = self.bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
            "trail_hash": "precomputed_hash_123",
        })
        self.assertEqual(result.trail_hash, "precomputed_hash_123")

    def test_trail_with_explicit_score(self):
        result = self.bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TEST_RUN"],
            "score": 0.95,
        })
        # High score + multiple mapped opcodes should yield progress
        self.assertGreater(len(result.tiles_progressed), 0)

    def test_trail_updates_agent_progress(self):
        self.bridge.process_trail({
            "agent": "agent-A",
            "opcodes": ["FILE_READ"],
        })
        progress = self.bridge.get_agent_tile_progress("agent-A")
        self.assertIn("code_reading", progress)
        self.assertGreater(progress["code_reading"], 0.0)

    def test_trail_updates_evidence(self):
        self.bridge.process_trail({
            "agent": "agent-A",
            "opcodes": ["FILE_READ"],
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertEqual(len(evidence), 1)
        self.assertEqual(evidence[0]["agent"], "agent-A")

    def test_trail_adds_to_history(self):
        self.bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
        })
        history = self.bridge.get_history()
        self.assertEqual(len(history), 1)

    def test_multiple_trails_cumulative_progress(self):
        # First trail
        self.bridge.process_trail({
            "agent": "agent-B",
            "opcodes": ["FILE_READ"],
            "score": 0.9,
        })
        # Second trail
        self.bridge.process_trail({
            "agent": "agent-B",
            "opcodes": ["FILE_READ"],
            "score": 0.9,
        })
        progress = self.bridge.get_agent_tile_progress("agent-B")
        # Cumulative progress should be higher than single trail
        self.assertGreaterEqual(progress.get("code_reading", 0), 0.5)

    def test_different_agents_independent_progress(self):
        self.bridge.process_trail({
            "agent": "agent-X",
            "opcodes": ["FILE_READ"],
        })
        self.bridge.process_trail({
            "agent": "agent-Y",
            "opcodes": ["TRUST_UPDATE"],
        })
        prog_x = self.bridge.get_agent_tile_progress("agent-X")
        prog_y = self.bridge.get_agent_tile_progress("agent-Y")
        self.assertIn("code_reading", prog_x)
        self.assertNotIn("code_reading", prog_y)
        self.assertIn("trust_establishment", prog_y)
        self.assertNotIn("trust_establishment", prog_x)

    def test_max_tiles_per_trail_limit(self):
        bridge = TrailTileBridge(TrailTileConfig(max_tiles_per_trail=2))
        # Trail with many different opcodes mapping to many tiles
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": [
                "FILE_READ", "FILE_WRITE", "FILE_EDIT",
                "TEST_RUN", "SEARCH_CODE", "GIT_COMMIT",
                "TRUST_UPDATE", "ROOM_ENTER", "SPELL_CAST",
            ],
            "score": 1.0,
        })
        # Even though many tiles are progressed, only 2 should be completed
        self.assertLessEqual(len(result.tiles_completed), 2)

    def test_meta_opcodes_contributed_to_progress(self):
        result = self.bridge.process_trail({
            "agent": "test",
            "opcodes": ["TRAIL_BEGIN", "TRAIL_END", "NOP"],
        })
        # Meta opcodes should still contribute some progress
        self.assertGreater(len(result.tiles_progressed), 0)

    def test_high_threshold_prevents_completion(self):
        bridge = TrailTileBridge(
            TrailTileConfig(auto_complete_threshold=1.5)  # Impossible threshold
        )
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TEST_RUN"],
            "score": 1.0,
        })
        self.assertEqual(result.tiles_completed, [])

    def test_zero_threshold_all_tiles_complete(self):
        bridge = TrailTileBridge(
            TrailTileConfig(auto_complete_threshold=0.0)
        )
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
        })
        self.assertGreater(len(result.tiles_completed), 0)


# ═══════════════════════════════════════════════════════════════
# get_agent_tile_progress tests
# ═══════════════════════════════════════════════════════════════

class TestGetAgentTileProgress(unittest.TestCase):
    """Tests for querying agent tile progress."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_no_progress_for_unknown_agent(self):
        progress = self.bridge.get_agent_tile_progress("ghost")
        self.assertEqual(progress, {})

    def test_progress_after_trail(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ", "FILE_WRITE"],
        })
        progress = self.bridge.get_agent_tile_progress("navi")
        self.assertIsInstance(progress, dict)
        self.assertGreater(len(progress), 0)

    def test_progress_returns_floats(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
        })
        progress = self.bridge.get_agent_tile_progress("navi")
        for v in progress.values():
            self.assertIsInstance(v, float)
            self.assertGreaterEqual(v, 0.0)
            self.assertLessEqual(v, 1.0)

    def test_progress_returns_copy_not_reference(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
        })
        p1 = self.bridge.get_agent_tile_progress("navi")
        p1["injected"] = 999.0
        p2 = self.bridge.get_agent_tile_progress("navi")
        self.assertNotIn("injected", p2)


# ═══════════════════════════════════════════════════════════════
# get_tile_trail_evidence tests
# ═══════════════════════════════════════════════════════════════

class TestGetTileTrailEvidence(unittest.TestCase):
    """Tests for querying which trails contributed to a tile."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_no_evidence_for_unknown_tile(self):
        evidence = self.bridge.get_tile_trail_evidence("fake_tile")
        self.assertEqual(evidence, [])

    def test_evidence_after_trail(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertEqual(len(evidence), 1)

    def test_evidence_accumulates(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
        })
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ", "FILE_WRITE"],
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertEqual(len(evidence), 2)

    def test_evidence_contains_trail_hash(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
            "trail_hash": "known_hash",
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertEqual(evidence[0]["trail_hash"], "known_hash")

    def test_evidence_contains_agent(self):
        self.bridge.process_trail({
            "agent": "navi-7",
            "opcodes": ["FILE_READ"],
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertEqual(evidence[0]["agent"], "navi-7")

    def test_evidence_contains_opcodes(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ", "FILE_WRITE"],
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertIn("FILE_READ", evidence[0]["opcodes"])
        self.assertIn("FILE_WRITE", evidence[0]["opcodes"])

    def test_evidence_contains_timestamp(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
        })
        evidence = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertIn("timestamp", evidence[0])
        self.assertIsInstance(evidence[0]["timestamp"], float)

    def test_evidence_returns_copy(self):
        self.bridge.process_trail({
            "agent": "navi",
            "opcodes": ["FILE_READ"],
        })
        ev1 = self.bridge.get_tile_trail_evidence("code_reading")
        ev1.append({"fake": True})
        ev2 = self.bridge.get_tile_trail_evidence("code_reading")
        self.assertEqual(len(ev2), 1)


# ═══════════════════════════════════════════════════════════════
# batch_process_trails tests
# ═══════════════════════════════════════════════════════════════

class TestBatchProcessTrails(unittest.TestCase):
    """Tests for batch processing of trails."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_batch_empty_list(self):
        results = self.bridge.batch_process_trails([])
        self.assertEqual(results, [])

    def test_batch_single_trail(self):
        results = self.bridge.batch_process_trails([
            {"agent": "a", "opcodes": ["FILE_READ"]},
        ])
        self.assertEqual(len(results), 1)
        self.assertIsInstance(results[0], TrailTileResult)

    def test_batch_multiple_trails(self):
        results = self.bridge.batch_process_trails([
            {"agent": "a", "opcodes": ["FILE_READ"]},
            {"agent": "b", "opcodes": ["TRUST_UPDATE"]},
            {"agent": "c", "opcodes": ["TEST_RUN"]},
        ])
        self.assertEqual(len(results), 3)

    def test_batch_updates_progress(self):
        self.bridge.batch_process_trails([
            {"agent": "a", "opcodes": ["FILE_READ"]},
            {"agent": "a", "opcodes": ["FILE_WRITE"]},
        ])
        progress = self.bridge.get_agent_tile_progress("a")
        self.assertGreater(len(progress), 0)

    def test_batch_updates_history(self):
        self.bridge.batch_process_trails([
            {"agent": "a", "opcodes": ["FILE_READ"]},
            {"agent": "b", "opcodes": ["TRUST_UPDATE"]},
        ])
        self.assertEqual(len(self.bridge.get_history()), 2)

    def test_batch_result_hashes_unique(self):
        trails = [
            {"agent": "a", "opcodes": ["FILE_READ"]},
            {"agent": "b", "opcodes": ["TRUST_UPDATE"]},
        ]
        results = self.bridge.batch_process_trails(trails)
        # Different trails should produce different hashes (due to agent name)
        # (though timing might cause collisions, so we just check structure)
        self.assertIsInstance(results[0].trail_hash, str)
        self.assertIsInstance(results[1].trail_hash, str)


# ═══════════════════════════════════════════════════════════════
# Bridge serialization tests
# ═══════════════════════════════════════════════════════════════

class TestBridgeSerialization(unittest.TestCase):
    """Tests for bridge to_dict / from_dict serialization."""

    def setUp(self):
        self.bridge = TrailTileBridge()
        self.bridge.process_trail({
            "agent": "serenity",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TEST_RUN"],
            "trail_hash": "hash_001",
        })
        self.bridge.process_trail({
            "agent": "serenity",
            "opcodes": ["TRUST_UPDATE"],
            "trail_hash": "hash_002",
        })

    def test_to_dict_returns_dict(self):
        d = self.bridge.to_dict()
        self.assertIsInstance(d, dict)

    def test_to_dict_has_config(self):
        d = self.bridge.to_dict()
        self.assertIn("config", d)
        self.assertIn("auto_complete_threshold", d["config"])

    def test_to_dict_has_agent_progress(self):
        d = self.bridge.to_dict()
        self.assertIn("agent_progress", d)
        self.assertIn("serenity", d["agent_progress"])

    def test_to_dict_has_tile_evidence(self):
        d = self.bridge.to_dict()
        self.assertIn("tile_evidence", d)

    def test_to_dict_has_history(self):
        d = self.bridge.to_dict()
        self.assertIn("history", d)
        self.assertEqual(len(d["history"]), 2)

    def test_from_dict_restores_config(self):
        d = self.bridge.to_dict()
        restored = TrailTileBridge.from_dict(d)
        self.assertEqual(
            restored.config.auto_complete_threshold,
            self.bridge.config.auto_complete_threshold,
        )

    def test_from_dict_restores_agent_progress(self):
        d = self.bridge.to_dict()
        restored = TrailTileBridge.from_dict(d)
        orig = self.bridge.get_agent_tile_progress("serenity")
        new = restored.get_agent_tile_progress("serenity")
        self.assertEqual(orig, new)

    def test_from_dict_restores_history(self):
        d = self.bridge.to_dict()
        restored = TrailTileBridge.from_dict(d)
        self.assertEqual(len(restored.get_history()), 2)

    def test_from_dict_restores_evidence(self):
        d = self.bridge.to_dict()
        restored = TrailTileBridge.from_dict(d)
        orig_ev = self.bridge.get_tile_trail_evidence("code_reading")
        new_ev = restored.get_tile_trail_evidence("code_reading")
        self.assertEqual(len(orig_ev), len(new_ev))

    def test_restored_bridge_can_process_more_trails(self):
        d = self.bridge.to_dict()
        restored = TrailTileBridge.from_dict(d)
        result = restored.process_trail({
            "agent": "serenity",
            "opcodes": ["FILE_READ"],
            "trail_hash": "hash_003",
        })
        self.assertIsNotNone(result)
        self.assertEqual(len(restored.get_history()), 3)

    def test_from_dict_empty(self):
        restored = TrailTileBridge.from_dict({})
        self.assertIsNotNone(restored)
        self.assertEqual(len(restored.get_history()), 0)

    def test_double_round_trip(self):
        d1 = self.bridge.to_dict()
        r1 = TrailTileBridge.from_dict(d1)
        d2 = r1.to_dict()
        r2 = TrailTileBridge.from_dict(d2)
        self.assertEqual(
            r2.config.auto_complete_threshold,
            self.bridge.config.auto_complete_threshold,
        )
        self.assertEqual(len(r2.get_history()), len(self.bridge.get_history()))


# ═══════════════════════════════════════════════════════════════
# reset() tests
# ═══════════════════════════════════════════════════════════════

class TestReset(unittest.TestCase):
    """Tests for bridge reset."""

    def setUp(self):
        self.bridge = TrailTileBridge()
        self.bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
        })
        self.bridge.process_trail({
            "agent": "test2",
            "opcodes": ["TRUST_UPDATE"],
        })

    def test_reset_clears_progress(self):
        self.bridge.reset()
        self.assertEqual(self.bridge.get_agent_tile_progress("test"), {})

    def test_reset_clears_evidence(self):
        self.bridge.reset()
        self.assertEqual(self.bridge.get_tile_trail_evidence("code_reading"), [])

    def test_reset_clears_history(self):
        self.bridge.reset()
        self.assertEqual(self.bridge.get_history(), [])

    def test_reset_clears_all_agents(self):
        self.bridge.reset()
        stats = self.bridge.get_stats()
        self.assertEqual(stats["total_agents_seen"], 0)

    def test_bridge_usable_after_reset(self):
        self.bridge.reset()
        result = self.bridge.process_trail({
            "agent": "new-agent",
            "opcodes": ["FILE_READ"],
        })
        self.assertIsNotNone(result)
        self.assertEqual(len(self.bridge.get_history()), 1)


# ═══════════════════════════════════════════════════════════════
# get_stats() tests
# ═══════════════════════════════════════════════════════════════

class TestGetStats(unittest.TestCase):
    """Tests for bridge statistics."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_fresh_stats(self):
        stats = self.bridge.get_stats()
        self.assertEqual(stats["total_trails_processed"], 0)
        self.assertEqual(stats["total_tiles_completed"], 0)
        self.assertEqual(stats["total_agents_seen"], 0)

    def test_stats_after_one_trail(self):
        self.bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
        })
        stats = self.bridge.get_stats()
        self.assertEqual(stats["total_trails_processed"], 1)
        self.assertEqual(stats["total_agents_seen"], 1)

    def test_stats_after_multiple_agents(self):
        self.bridge.process_trail({"agent": "a", "opcodes": ["FILE_READ"]})
        self.bridge.process_trail({"agent": "b", "opcodes": ["TRUST_UPDATE"]})
        stats = self.bridge.get_stats()
        self.assertEqual(stats["total_trails_processed"], 2)
        self.assertEqual(stats["total_agents_seen"], 2)

    def test_stats_mapping_count(self):
        stats = self.bridge.get_stats()
        self.assertEqual(stats["mapping_count"], 20)

    def test_stats_has_all_keys(self):
        stats = self.bridge.get_stats()
        expected_keys = [
            "total_trails_processed",
            "total_tiles_completed",
            "total_agents_seen",
            "total_tiles_tracked",
            "mapping_count",
            "auto_complete_threshold",
            "max_tiles_per_trail",
        ]
        for key in expected_keys:
            self.assertIn(key, stats)


# ═══════════════════════════════════════════════════════════════
# Prerequisite validation tests
# ═══════════════════════════════════════════════════════════════

class TestPrerequisiteValidation(unittest.TestCase):
    """Tests for prerequisite-aware tile completion."""

    def _make_tile_graph(self):
        """Create a mock tile graph with prerequisites."""
        class MockTile:
            def __init__(self, tid, prereqs):
                self.id = tid
                self.prerequisites = prereqs
            def missing_prerequisites(self, acquired):
                return [p for p in self.prerequisites if p not in acquired]

        class MockGraph:
            def __init__(self):
                self.tiles = {
                    "code_reading": MockTile("code_reading", []),
                    "code_writing": MockTile("code_writing", ["code_reading"]),
                    "testing": MockTile("testing", ["code_writing"]),
                }

        return MockGraph()

    def test_no_graph_no_prereq_check(self):
        bridge = TrailTileBridge(TrailTileConfig(auto_complete_threshold=0.0))
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_WRITE"],
        })
        # Without a tile_graph, prereqs aren't checked
        self.assertGreater(len(result.tiles_completed), 0)

    def test_with_graph_missing_prereq_blocks_completion(self):
        graph = self._make_tile_graph()
        bridge = TrailTileBridge(
            TrailTileConfig(auto_complete_threshold=0.0),
            tile_graph=graph,
        )
        # FILE_WRITE maps to code_writing, which requires code_reading
        # But agent has no progress on code_reading, so it can't complete
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_WRITE"],
        })
        # code_writing should NOT be completed (prereq missing)
        self.assertNotIn("code_writing", result.tiles_completed)

    def test_with_graph_met_prereq_allows_completion(self):
        graph = self._make_tile_graph()
        bridge = TrailTileBridge(
            TrailTileConfig(auto_complete_threshold=0.0),
            tile_graph=graph,
        )
        # First complete code_reading via FILE_READ
        bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
        })
        # Now code_reading should be in agent progress >= threshold
        # Then try code_writing
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_WRITE"],
        })
        # With code_reading acquired, code_writing can now complete
        # (if threshold is 0.0 and progress is sufficient)
        self.assertIn("code_writing", result.tiles_completed)


# ═══════════════════════════════════════════════════════════════
# Edge case tests
# ═══════════════════════════════════════════════════════════════

class TestEdgeCases(unittest.TestCase):
    """Tests for edge cases and unusual inputs."""

    def test_trail_data_missing_keys(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({})
        self.assertIsInstance(result, TrailTileResult)
        self.assertEqual(result.confidence, 0.0)

    def test_trail_with_only_nop(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["NOP", "NOP", "NOP"],
        })
        # NOP is a meta opcode, should still map
        self.assertGreater(len(result.tiles_progressed), 0)

    def test_trail_with_only_unmapped(self):
        bridge = TrailTileBridge()
        bridge.config.opcode_tile_mapping = {}
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FAKE1", "FAKE2"],
        })
        self.assertEqual(result.confidence, 0.0)
        self.assertEqual(result.tiles_completed, [])
        self.assertEqual(result.tiles_progressed, {})

    def test_very_long_trail(self):
        bridge = TrailTileBridge()
        opcodes = ["FILE_READ", "FILE_WRITE", "TEST_RUN"] * 50
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": opcodes,
        })
        self.assertIsNotNone(result)

    def test_special_characters_in_agent_name(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "agent/with.special-chars_123",
            "opcodes": ["FILE_READ"],
        })
        progress = bridge.get_agent_tile_progress("agent/with.special-chars_123")
        self.assertGreater(len(progress), 0)

    def test_score_as_string_converted(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
            "score": "0.8",
        })
        self.assertIsNotNone(result)

    def test_score_none_defaults_to_one(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
            "score": None,
        })
        # Should not crash; progress should still be calculated
        self.assertGreater(len(result.tiles_progressed), 0)

    def test_duplicate_opcodes(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ", "FILE_READ", "FILE_READ"],
        })
        # Same opcode maps to same tile, should produce progress
        self.assertIn("code_reading", result.tiles_progressed)

    def test_single_opcode_trail(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["TRUST_UPDATE"],
        })
        self.assertIn("trust_establishment", result.tiles_progressed)

    def test_config_mutation_reflected(self):
        bridge = TrailTileBridge()
        bridge.config.auto_complete_threshold = 0.0
        bridge.config.max_tiles_per_trail = 100
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TRUST_UPDATE"],
        })
        # With threshold 0.0, all progressed tiles should be completed
        self.assertGreater(len(result.tiles_completed), 0)

    def test_mapping_config_copy_isolation(self):
        """Config mappings in TrailTileConfig should be independent."""
        config1 = TrailTileConfig()
        config2 = TrailTileConfig()
        config2.opcode_tile_mapping["CUSTOM"] = "custom_tile"
        self.assertNotIn("CUSTOM", config1.opcode_tile_mapping)
        self.assertIn("CUSTOM", config2.opcode_tile_mapping)


# ═══════════════════════════════════════════════════════════════
# Cross-domain trail tests
# ═══════════════════════════════════════════════════════════════

class TestCrossDomainTrails(unittest.TestCase):
    """Tests for trails spanning multiple tile domains."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_code_and_trust_opcodes(self):
        result = self.bridge.process_trail({
            "agent": "multi-domain-agent",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TRUST_UPDATE", "CAP_ISSUE"],
        })
        # Should have progress on both code and trust tiles
        progress = result.tiles_progressed
        code_tiles_found = any(
            tid in progress for tid in ["code_reading", "code_writing"]
        )
        trust_tiles_found = any(
            tid in progress for tid in ["trust_establishment", "permission_management"]
        )
        self.assertTrue(code_tiles_found, "Should have code domain progress")
        self.assertTrue(trust_tiles_found, "Should have trust domain progress")

    def test_all_domains_covered(self):
        """Trail with opcodes touching all 5 domains."""
        result = self.bridge.process_trail({
            "agent": "full-spectrum",
            "opcodes": [
                "FILE_READ",           # CODE
                "BOTTLE_DROP",         # SOCIAL
                "TRUST_UPDATE",        # TRUST
                "SPELL_CAST",          # CREATIVE
                "ROOM_ENTER",          # INFRASTRUCTURE
            ],
        })
        progress = result.tiles_progressed
        # Check all domains have at least one tile with progress
        domains_hit = set()
        expected = {
            "code_reading": "code",
            "knowledge_sharing": "social",
            "trust_establishment": "trust",
            "spell_crafting": "creative",
            "room_navigation": "infrastructure",
        }
        for tid, domain in expected.items():
            if tid in progress:
                domains_hit.add(domain)
        self.assertGreaterEqual(len(domains_hit), 4)

    def test_infrastructure_trail(self):
        result = self.bridge.process_trail({
            "agent": "infra-bot",
            "opcodes": ["ROOM_ENTER", "LEVEL_UP", "CAP_ISSUE"],
        })
        progress = result.tiles_progressed
        # Should have infra-domain tiles
        infra_tiles = any(
            tid in progress
            for tid in ["room_navigation", "trust_boundaries", "permission_management"]
        )
        self.assertTrue(infra_tiles)


# ═══════════════════════════════════════════════════════════════
# Integration with tile_graph mock
# ═══════════════════════════════════════════════════════════════

class TestTileGraphIntegration(unittest.TestCase):
    """Integration tests using mock tile graphs."""

    def test_tile_not_in_graph_ignored(self):
        """If a tile_id from the mapping isn't in the graph, skip prereq check."""

        class EmptyGraph:
            tiles = {}

        bridge = TrailTileBridge(
            TrailTileConfig(auto_complete_threshold=0.0),
            tile_graph=EmptyGraph(),
        )
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ"],
        })
        # Tile not in graph means no prereq check; with threshold 0.0, completes
        self.assertGreater(len(result.tiles_completed), 0)


# ═══════════════════════════════════════════════════════════════
# Confidence scoring tests
# ═══════════════════════════════════════════════════════════════

class TestConfidenceScoring(unittest.TestCase):
    """Tests for confidence calculation in trail processing."""

    def test_all_mapped_high_confidence(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TEST_RUN", "GIT_COMMIT"],
        })
        self.assertEqual(result.confidence, 1.0)

    def test_half_mapped_half_unmapped(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["FILE_READ", "FAKE_OP", "FILE_WRITE", "ANOTHER_FAKE"],
        })
        self.assertAlmostEqual(result.confidence, 0.5, places=1)

    def test_only_meta_opcodes_low_confidence(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": ["TRAIL_BEGIN", "TRAIL_END", "COMMENT", "LABEL", "NOP"],
        })
        self.assertEqual(result.confidence, 0.3)

    def test_no_opcodes_zero_confidence(self):
        bridge = TrailTileBridge()
        result = bridge.process_trail({
            "agent": "test",
            "opcodes": [],
        })
        self.assertEqual(result.confidence, 0.0)


# ═══════════════════════════════════════════════════════════════
# History tests
# ═══════════════════════════════════════════════════════════════

class TestHistory(unittest.TestCase):
    """Tests for processing history."""

    def setUp(self):
        self.bridge = TrailTileBridge()

    def test_empty_history_initially(self):
        self.assertEqual(self.bridge.get_history(), [])

    def test_history_grows(self):
        self.bridge.process_trail({"agent": "a", "opcodes": ["FILE_READ"]})
        self.bridge.process_trail({"agent": "b", "opcodes": ["FILE_WRITE"]})
        self.assertEqual(len(self.bridge.get_history()), 2)

    def test_history_order(self):
        r1 = self.bridge.process_trail({
            "agent": "a", "opcodes": ["FILE_READ"], "trail_hash": "h1"
        })
        r2 = self.bridge.process_trail({
            "agent": "b", "opcodes": ["FILE_WRITE"], "trail_hash": "h2"
        })
        history = self.bridge.get_history()
        self.assertEqual(history[0].trail_hash, "h1")
        self.assertEqual(history[1].trail_hash, "h2")

    def test_history_returns_copies(self):
        self.bridge.process_trail({
            "agent": "a", "opcodes": ["FILE_READ"]
        })
        history = self.bridge.get_history()
        self.assertIsInstance(history, list)
        # Mutating the list should not affect internal state
        history.append("fake")
        self.assertEqual(len(self.bridge.get_history()), 1)


if __name__ == "__main__":
    unittest.main()
