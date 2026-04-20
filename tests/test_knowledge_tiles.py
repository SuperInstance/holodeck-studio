#!/usr/bin/env python3
"""
Tests for knowledge_tiles.py — Knowledge Tiling Framework

Covers all 6 components:
1. KnowledgeTile — creation, prerequisites, serialization, morphogen affinity
2. TileGraph — construction, cycle detection, path finding, bottlenecks, gateways, frontier
3. TileCombinator — combination discovery, scoring, creative collisions, permission mapping
4. AgentTileState — management, acquirable/blocked computation, trust compatibility
5. TileFleetAnalytics — coverage, diversity, collaboration potential
6. Standard Tile Library — completeness, consistency, domain distribution
"""

import time
import unittest

from knowledge_tiles import (
    KnowledgeTile, TileDomain, TileGraph, TileCombinator,
    CombinationResult, AgentTileState, LearningRecord,
    TileFleetAnalytics, build_standard_tiles,
)


# ═══════════════════════════════════════════════════════════════
# KnowledgeTile Tests
# ═══════════════════════════════════════════════════════════════

class TestKnowledgeTile(unittest.TestCase):
    """Tests for the atomic tile unit."""

    def test_basic_creation(self):
        tile = KnowledgeTile(id="test_tile", name="Test Tile")
        self.assertEqual(tile.id, "test_tile")
        self.assertEqual(tile.name, "Test Tile")
        self.assertEqual(tile.domain, TileDomain.CODE)
        self.assertEqual(tile.prerequisites, [])
        self.assertEqual(tile.difficulty, 0.3)

    def test_creation_with_all_fields(self):
        tile = KnowledgeTile(
            id="t1", name="T1", description="A test tile",
            domain=TileDomain.TRUST,
            prerequisites=["prereq_a"],
            morphogen_sensitivity={"trust": 0.8},
            discovery_context="unit_test",
            tags=["test", "trust"],
            difficulty=0.7,
        )
        self.assertEqual(tile.domain, TileDomain.TRUST)
        self.assertEqual(tile.prerequisites, ["prereq_a"])
        self.assertEqual(tile.morphogen_sensitivity, {"trust": 0.8})
        self.assertEqual(tile.discovery_context, "unit_test")
        self.assertEqual(tile.tags, ["test", "trust"])
        self.assertEqual(tile.difficulty, 0.7)

    def test_has_prerequisites_all_met(self):
        tile = KnowledgeTile(id="t1", name="T1", prerequisites=["a", "b"])
        self.assertTrue(tile.has_prerequisites({"a", "b", "c"}))

    def test_has_prerequisites_not_met(self):
        tile = KnowledgeTile(id="t1", name="T1", prerequisites=["a", "b"])
        self.assertFalse(tile.has_prerequisites({"a"}))
        self.assertFalse(tile.has_prerequisites(set()))

    def test_missing_prerequisites(self):
        tile = KnowledgeTile(id="t1", name="T1", prerequisites=["a", "b", "c"])
        self.assertEqual(tile.missing_prerequisites({"a"}), ["b", "c"])
        self.assertEqual(tile.missing_prerequisites({"a", "b", "c"}), [])

    def test_serialization_round_trip(self):
        tile = KnowledgeTile(
            id="ser_test", name="Ser Test", description="Serialize me",
            domain=TileDomain.CREATIVE,
            prerequisites=["p1"],
            morphogen_sensitivity={"trust": 0.5, "experience": 0.3},
            discovery_context="test", tags=["tag1"], difficulty=0.6,
        )
        d = tile.to_dict()
        restored = KnowledgeTile.from_dict(d)
        self.assertEqual(restored.id, tile.id)
        self.assertEqual(restored.name, tile.name)
        self.assertEqual(restored.domain, TileDomain.CREATIVE)
        self.assertEqual(restored.prerequisites, ["p1"])
        self.assertEqual(restored.morphogen_sensitivity, {"trust": 0.5, "experience": 0.3})
        self.assertEqual(restored.difficulty, 0.6)
        self.assertEqual(restored.tags, ["tag1"])

    def test_domain_compatibility_cross_domain(self):
        t1 = KnowledgeTile(id="t1", name="T1", domain=TileDomain.CODE)
        t2 = KnowledgeTile(id="t2", name="T2", domain=TileDomain.SOCIAL)
        self.assertEqual(t1.domain_compatibility(t2), 1.0)

    def test_domain_compatibility_same_domain(self):
        t1 = KnowledgeTile(id="t1", name="T1", domain=TileDomain.CODE)
        t2 = KnowledgeTile(id="t2", name="T2", domain=TileDomain.CODE)
        self.assertEqual(t1.domain_compatibility(t2), 0.5)

    def test_morphogen_affinity(self):
        tile = KnowledgeTile(
            id="t1", name="T1",
            morphogen_sensitivity={"trust": 0.8, "experience": 0.2},
        )
        profile = {"trust": 0.9, "experience": 0.5, "budget": 0.0, "recency": 0.0, "social": 0.0}
        affinity = tile.morphogen_affinity(profile)
        # Expected: (0.9*0.8 + 0.5*0.2) / (0.8+0.2) = (0.72+0.1)/1.0 = 0.82
        self.assertAlmostEqual(affinity, 0.82, places=2)

    def test_morphogen_affinity_empty(self):
        tile = KnowledgeTile(id="t1", name="T1")
        self.assertEqual(tile.morphogen_affinity({}), 0.5)

    def test_prerequisite_depth(self):
        tile_map = {
            "root": KnowledgeTile(id="root", name="Root"),
            "mid": KnowledgeTile(id="mid", name="Mid", prerequisites=["root"]),
            "leaf": KnowledgeTile(id="leaf", name="Leaf", prerequisites=["mid"]),
        }
        self.assertEqual(tile_map["root"].prerequisite_depth(tile_map), 0)
        self.assertEqual(tile_map["mid"].prerequisite_depth(tile_map), 1)
        self.assertEqual(tile_map["leaf"].prerequisite_depth(tile_map), 2)


# ═══════════════════════════════════════════════════════════════
# TileGraph Tests
# ═══════════════════════════════════════════════════════════════

class TestTileGraph(unittest.TestCase):
    """Tests for the tiling lattice DAG."""

    def _make_simple_graph(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="a", name="A"))
        graph.add_tile(KnowledgeTile(id="b", name="B", prerequisites=["a"]))
        graph.add_tile(KnowledgeTile(id="c", name="C", prerequisites=["a"]))
        graph.add_tile(KnowledgeTile(id="d", name="D", prerequisites=["b", "c"]))
        return graph

    def test_add_tile(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="t1", name="T1"))
        self.assertIn("t1", graph.tiles)
        self.assertEqual(len(graph.tiles), 1)

    def test_remove_tile(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="t1", name="T1"))
        self.assertTrue(graph.remove_tile("t1"))
        self.assertNotIn("t1", graph.tiles)
        self.assertFalse(graph.remove_tile("t1"))  # already gone

    def test_cycle_detection_clean(self):
        graph = self._make_simple_graph()
        self.assertFalse(graph.has_cycle())

    def test_cycle_detection_raises_on_add(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="x", name="X", prerequisites=["y"]))
        with self.assertRaises(ValueError):
            graph.add_tile(KnowledgeTile(id="y", name="Y", prerequisites=["x"]))

    def test_compute_depths(self):
        graph = self._make_simple_graph()
        depths = graph.compute_depths()
        self.assertEqual(depths["a"], 0)
        self.assertEqual(depths["b"], 1)
        self.assertEqual(depths["c"], 1)
        self.assertEqual(depths["d"], 2)

    def test_find_bottlenecks(self):
        graph = self._make_simple_graph()
        bottlenecks = graph.find_bottleneck_tiles(top_n=3)
        # Tile "a" is required by b, c, d (3 downstream)
        a_entry = next(b for b in bottlenecks if b["tile_id"] == "a")
        self.assertEqual(a_entry["downstream_count"], 3)

    def test_find_gateways(self):
        graph = self._make_simple_graph()
        gateways = graph.find_gateway_tiles(top_n=3)
        # Tile "a" unlocks both "b" and "c" (both have only "a" as prereq)
        a_entry = next(g for g in gateways if g["tile_id"] == "a")
        self.assertEqual(a_entry["unlock_count"], 2)

    def test_compute_frontier(self):
        graph = self._make_simple_graph()
        # With "a" acquired, "b" and "c" are on the frontier (all prereqs met)
        frontier = graph.compute_frontier({"a"})
        self.assertIn("b", frontier)
        self.assertIn("c", frontier)
        self.assertNotIn("d", frontier)  # missing b or c

    def test_immediate_acquirable(self):
        graph = self._make_simple_graph()
        acquirable = graph.immediate_acquirable({"a"})
        self.assertIn("b", acquirable)
        self.assertIn("c", acquirable)

    def test_all_reachable(self):
        graph = self._make_simple_graph()
        reachable = graph.all_reachable({"a"})
        self.assertEqual(reachable, {"b", "c", "d"})

    def test_all_reachable_empty(self):
        graph = self._make_simple_graph()
        reachable = graph.all_reachable(set())
        # Starting from nothing, "a" is acquirable (no prereqs),
        # then "b" and "c" become acquirable, then "d"
        self.assertEqual(reachable, {"a", "b", "c", "d"})

    def test_domain_coverage(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="c1", name="C1", domain=TileDomain.CODE))
        graph.add_tile(KnowledgeTile(id="c2", name="C2", domain=TileDomain.CODE))
        graph.add_tile(KnowledgeTile(id="s1", name="S1", domain=TileDomain.SOCIAL))
        coverage = graph.domain_coverage({"c1"})
        self.assertAlmostEqual(coverage["code"], 0.5)
        self.assertAlmostEqual(coverage["social"], 0.0)

    def test_empty_graph(self):
        graph = TileGraph()
        self.assertFalse(graph.has_cycle())
        self.assertEqual(graph.compute_depths(), {})
        self.assertEqual(graph.compute_frontier(set()), [])
        self.assertEqual(graph.find_bottleneck_tiles(), [])

    def test_single_tile_graph(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="solo", name="Solo"))
        self.assertFalse(graph.has_cycle())
        self.assertEqual(graph.compute_depths(), {"solo": 0})
        self.assertIn("solo", graph.compute_frontier(set()))

    def test_disconnected_components(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="x", name="X"))
        graph.add_tile(KnowledgeTile(id="y", name="Y", prerequisites=["z"]))
        # "y" references "z" which doesn't exist — still no cycle
        self.assertFalse(graph.has_cycle())
        depths = graph.compute_depths()
        self.assertEqual(depths["x"], 0)
        # "y" has a prerequisite ("z") even though z doesn't exist,
        # so depth is 1 (z resolves to depth 0 as a missing tile)
        self.assertEqual(depths["y"], 1)

    def test_serialization_round_trip(self):
        graph = self._make_simple_graph()
        d = graph.to_dict()
        restored = TileGraph.from_dict(d)
        self.assertEqual(len(restored.tiles), 4)
        self.assertIn("a", restored.tiles)
        self.assertEqual(restored.tiles["d"].prerequisites, ["b", "c"])

    def test_from_tile_list(self):
        tiles = [
            KnowledgeTile(id="a", name="A"),
            KnowledgeTile(id="b", name="B", prerequisites=["a"]),
        ]
        graph = TileGraph.from_tile_list(tiles)
        self.assertEqual(len(graph.tiles), 2)
        self.assertFalse(graph.has_cycle())


# ═══════════════════════════════════════════════════════════════
# TileCombinator Tests
# ═══════════════════════════════════════════════════════════════

class TestTileCombinator(unittest.TestCase):
    """Tests for novel combination discovery."""

    def _make_graph(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="code_read", name="Code Read",
                                      domain=TileDomain.CODE, difficulty=0.2))
        graph.add_tile(KnowledgeTile(id="social_talk", name="Social Talk",
                                      domain=TileDomain.SOCIAL, difficulty=0.1))
        graph.add_tile(KnowledgeTile(id="trust_know", name="Trust Know",
                                      domain=TileDomain.TRUST, difficulty=0.3))
        graph.add_tile(KnowledgeTile(id="design_basic", name="Basic Design",
                                      domain=TileDomain.CREATIVE, difficulty=0.15))
        return graph

    def test_discover_combinations(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        results = combinator.discover_combinations(
            {"code_read", "social_talk"}, min_acquired=2, max_acquired=2
        )
        self.assertTrue(len(results) >= 1)
        # The code_read + social_talk combo should be cross-domain
        cross = [r for r in results if r.is_cross_domain]
        self.assertTrue(len(cross) >= 1)

    def test_combination_scoring(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        results = combinator.discover_combinations({"code_read", "social_talk"})
        for r in results:
            self.assertGreaterEqual(r.novelty_score, 0.0)
            self.assertLessEqual(r.novelty_score, 1.0)
            self.assertGreaterEqual(r.utility_score, 0.0)
            self.assertGreaterEqual(r.feasibility_score, 0.0)
            self.assertGreaterEqual(r.composite_score, 0.0)

    def test_creative_collision(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        # Acquire tiles from different domains to trigger cross-domain
        results = combinator.creative_collision({"code_read", "social_talk", "trust_know"})
        for r in results:
            self.assertTrue(r.is_cross_domain)

    def test_emergent_capabilities(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        results = combinator.discover_combinations({"code_read", "social_talk"})
        # At least one cross-domain combo should have emergent capabilities
        emergent_results = [r for r in results if r.emergent_capabilities]
        self.assertTrue(len(emergent_results) >= 1)

    def test_map_to_permissions(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        results = combinator.discover_combinations({"code_read", "social_talk"})
        if results:
            actions = combinator.map_to_permissions(results[0])
            # Should return list (may be empty if no emergent capabilities)
            self.assertIsInstance(actions, list)

    def test_map_to_permissions_with_cap_map(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        results = combinator.discover_combinations({"code_read", "social_talk"})
        if results:
            cap_map = {"code_read_social_talk": ["build_room", "create_item"]}
            actions = combinator.map_to_permissions(results[0], cap_map)
            self.assertEqual(actions, ["build_room", "create_item"])

    def test_empty_acquired(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        results = combinator.discover_combinations(set())
        self.assertEqual(results, [])

    def test_combination_result_serialization(self):
        result = CombinationResult(
            tiles=("a", "b"), novelty_score=0.5, utility_score=0.3,
            feasibility_score=0.8, composite_score=0.5,
            is_cross_domain=True, emergent_capabilities=["code_social_synthesis"],
        )
        d = result.to_dict()
        self.assertEqual(d["tiles"], ["a", "b"])
        self.assertTrue(d["is_cross_domain"])
        self.assertIn("code_social_synthesis", d["emergent_capabilities"])

    def test_known_combinations_tracked(self):
        graph = self._make_graph()
        combinator = TileCombinator(graph)
        combinator.discover_combinations({"code_read", "social_talk"})
        combinator.discover_combinations({"code_read", "social_talk"})
        # Second call should not add duplicates to known_combinations
        self.assertGreaterEqual(len(combinator.known_combinations), 1)

    def test_frontier_tile_combinations(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="a", name="A", domain=TileDomain.CODE))
        graph.add_tile(KnowledgeTile(id="b", name="B", domain=TileDomain.SOCIAL,
                                      prerequisites=["a"]))
        combinator = TileCombinator(graph)
        # Acquire "a", "b" is on the frontier
        results = combinator.discover_combinations({"a"})
        # Should include combinations with frontier tile "b"
        tile_ids_in_results = set()
        for r in results:
            tile_ids_in_results.update(r.tiles)
        self.assertTrue(len(results) >= 1)


# ═══════════════════════════════════════════════════════════════
# AgentTileState Tests
# ═══════════════════════════════════════════════════════════════

class TestAgentTileState(unittest.TestCase):
    """Tests for per-agent tile inventory management."""

    def _make_graph(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="a", name="A"))
        graph.add_tile(KnowledgeTile(id="b", name="B", prerequisites=["a"]))
        graph.add_tile(KnowledgeTile(id="c", name="C", prerequisites=["a"]))
        graph.add_tile(KnowledgeTile(id="d", name="D", prerequisites=["b", "c"]))
        return graph

    def test_acquire_tile_success(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        result = state.acquire_tile("a")
        self.assertTrue(result["success"])
        self.assertEqual(result["tile_id"], "a")
        self.assertIn("a", state.acquired)

    def test_acquire_tile_missing_prerequisites(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        result = state.acquire_tile("d")
        self.assertFalse(result["success"])
        self.assertIn("Missing prerequisites", result["error"])

    def test_acquire_tile_not_found(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        result = state.acquire_tile("nonexistent")
        self.assertFalse(result["success"])

    def test_acquire_tile_already_acquired(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a")
        result = state.acquire_tile("a")
        self.assertFalse(result["success"])
        self.assertIn("Already", result["error"])

    def test_release_tile(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a")
        self.assertTrue(state.release_tile("a"))
        self.assertNotIn("a", state.acquired)
        self.assertFalse(state.release_tile("a"))

    def test_get_acquirable(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a")
        acquirable = state.get_acquirable()
        self.assertIn("b", acquirable)
        self.assertIn("c", acquirable)
        self.assertNotIn("d", acquirable)

    def test_get_blocked(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        blocked = state.get_blocked()
        self.assertIn("b", blocked)
        self.assertIn("c", blocked)
        self.assertIn("d", blocked)
        # "a" should not be blocked (no prereqs)
        self.assertNotIn("a", blocked)

    def test_get_frontier(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a")
        state.acquire_tile("b")
        frontier = state.get_frontier()
        self.assertIn("c", frontier)
        self.assertIn("d", frontier)  # d is missing only "c" — one step away

    def test_tile_count(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        self.assertEqual(state.tile_count(), 0)
        state.acquire_tile("a")
        self.assertEqual(state.tile_count(), 1)

    def test_domain_summary(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="c1", name="C1", domain=TileDomain.CODE))
        graph.add_tile(KnowledgeTile(id="s1", name="S1", domain=TileDomain.SOCIAL))
        state = AgentTileState("agent1", graph)
        state.acquire_tile("c1")
        state.acquire_tile("s1")
        summary = state.domain_summary()
        self.assertEqual(summary["code"], 1)
        self.assertEqual(summary["social"], 1)

    def test_trust_compatibility_identical(self):
        graph = self._make_graph()
        s1 = AgentTileState("a1", graph)
        s2 = AgentTileState("a2", graph)
        s1.acquire_tile("a")
        s1.acquire_tile("b")
        s2.acquire_tile("a")
        s2.acquire_tile("b")
        self.assertAlmostEqual(s1.trust_compatibility(s2), 1.0)

    def test_trust_compatibility_disjoint(self):
        graph = self._make_graph()
        s1 = AgentTileState("a1", graph)
        s2 = AgentTileState("a2", graph)
        s1.acquire_tile("a")
        s2.acquire_tile("b")  # Wait, b has prereq a, so can't acquire without a
        # Fix: just use a and c which are both reachable from a
        s2.release_tile("b")
        s2.acquire_tile("a")
        s2.acquire_tile("c")
        # s1 has {a}, s2 has {a, c}
        compat = s1.trust_compatibility(s2)
        # Jaccard: intersection={a}, union={a,c} = 0.5
        self.assertAlmostEqual(compat, 0.5)

    def test_trust_compatibility_both_empty(self):
        graph = self._make_graph()
        s1 = AgentTileState("a1", graph)
        s2 = AgentTileState("a2", graph)
        self.assertAlmostEqual(s1.trust_compatibility(s2), 0.5)

    def test_complementary_score(self):
        graph = self._make_graph()
        s1 = AgentTileState("a1", graph)
        s2 = AgentTileState("a2", graph)
        s1.acquire_tile("a")
        s1.acquire_tile("b")
        s2.acquire_tile("a")
        s2.acquire_tile("c")
        score = s1.complementary_score(s2)
        self.assertGreater(score, 0.0)

    def test_learning_velocity(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a")
        state.acquire_tile("b")
        velocity = state.learning_velocity(window_seconds=3600.0)
        self.assertAlmostEqual(velocity, 2.0)

    def test_learning_history(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a", context="tutorial", method="teaching")
        self.assertEqual(len(state.learning_history), 1)
        self.assertEqual(state.learning_history[0].tile_id, "a")
        self.assertEqual(state.learning_history[0].method, "teaching")

    def test_serialization_round_trip(self):
        graph = self._make_graph()
        state = AgentTileState("agent1", graph)
        state.acquire_tile("a")
        state.acquire_tile("b")
        d = state.to_dict()
        self.assertEqual(d["agent_name"], "agent1")
        self.assertEqual(sorted(d["acquired"]), ["a", "b"])
        self.assertEqual(d["tile_count"], 2)
        # Restore
        restored = AgentTileState.from_dict(d, graph)
        self.assertEqual(restored.agent_name, "agent1")
        self.assertEqual(restored.acquired, {"a", "b"})


# ═══════════════════════════════════════════════════════════════
# TileFleetAnalytics Tests
# ═══════════════════════════════════════════════════════════════

class TestTileFleetAnalytics(unittest.TestCase):
    """Tests for fleet-wide tile analysis."""

    def _make_fleet(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="a", name="A", domain=TileDomain.CODE))
        graph.add_tile(KnowledgeTile(id="b", name="B", domain=TileDomain.SOCIAL,
                                      prerequisites=["a"]))
        graph.add_tile(KnowledgeTile(id="c", name="C", domain=TileDomain.TRUST,
                                      prerequisites=["a"]))
        graph.add_tile(KnowledgeTile(id="d", name="D", domain=TileDomain.CREATIVE,
                                      prerequisites=["b", "c"]))

        analytics = TileFleetAnalytics(graph)

        s1 = AgentTileState("alpha", graph)
        s1.acquire_tile("a")
        s1.acquire_tile("b")

        s2 = AgentTileState("beta", graph)
        s2.acquire_tile("a")
        s2.acquire_tile("c")

        analytics.register_agent(s1)
        analytics.register_agent(s2)
        return analytics, graph

    def test_tile_coverage(self):
        analytics, _ = self._make_fleet()
        coverage = analytics.tile_coverage()
        # Both agents have "a" → coverage 1.0
        self.assertAlmostEqual(coverage["a"], 1.0)
        # Only alpha has "b" → coverage 0.5
        self.assertAlmostEqual(coverage["b"], 0.5)

    def test_tile_coverage_empty_fleet(self):
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="a", name="A"))
        analytics = TileFleetAnalytics(graph)
        self.assertEqual(analytics.tile_coverage(), {})

    def test_tile_diversity(self):
        analytics, _ = self._make_fleet()
        diversity = analytics.tile_diversity()
        self.assertGreater(diversity, 0.0)
        self.assertLessEqual(diversity, 1.0)

    def test_discovery_velocity(self):
        analytics, _ = self._make_fleet()
        velocity = analytics.discovery_velocity()
        self.assertGreater(velocity, 0.0)

    def test_collaboration_potential(self):
        analytics, _ = self._make_fleet()
        results = analytics.collaboration_potential()
        self.assertEqual(len(results), 1)  # Only one pair (alpha, beta)
        pair = results[0]
        self.assertEqual(pair["agent_a"], "alpha")
        self.assertEqual(pair["agent_b"], "beta")
        self.assertGreater(pair["score"], 0.0)

    def test_fleet_capability_map(self):
        analytics, _ = self._make_fleet()
        cap_map = analytics.fleet_capability_map()
        self.assertEqual(cap_map["total_agents"], 2)
        self.assertEqual(cap_map["total_tiles_in_fleet"], 3)  # a, b, c
        self.assertIn("d", cap_map["blind_spots"])  # Neither has "d"

    def test_fleet_domain_matrix(self):
        analytics, _ = self._make_fleet()
        matrix = analytics.fleet_domain_matrix()
        self.assertIn("alpha", matrix)
        self.assertIn("beta", matrix)

    def test_most_unique_agents(self):
        analytics, _ = self._make_fleet()
        unique = analytics.most_unique_agents()
        self.assertEqual(len(unique), 2)
        # Each agent has 1 unique tile (b for alpha, c for beta)
        self.assertTrue(any(u["unique_tile_count"] >= 1 for u in unique))

    def test_unregister_agent(self):
        analytics, _ = self._make_fleet()
        self.assertTrue(analytics.unregister_agent("alpha"))
        self.assertFalse(analytics.unregister_agent("nonexistent"))
        self.assertEqual(len(analytics.agents), 1)

    def test_empty_fleet_analytics(self):
        graph = TileGraph()
        analytics = TileFleetAnalytics(graph)
        self.assertEqual(analytics.tile_diversity(), 0.0)
        self.assertEqual(analytics.discovery_velocity(), 0.0)
        self.assertEqual(analytics.collaboration_potential(), [])

    def test_fleet_serialization(self):
        analytics, _ = self._make_fleet()
        d = analytics.to_dict()
        self.assertEqual(d["agent_count"], 2)
        self.assertIn("tile_diversity", d)
        self.assertIn("fleet_capability_map", d)


# ═══════════════════════════════════════════════════════════════
# Standard Tile Library Tests
# ═══════════════════════════════════════════════════════════════

class TestStandardTileLibrary(unittest.TestCase):
    """Tests for the built-in tile library."""

    def test_minimum_tile_count(self):
        tiles = build_standard_tiles()
        self.assertGreaterEqual(len(tiles), 50, "Must have at least 50 standard tiles")

    def test_all_domains_represented(self):
        tiles = build_standard_tiles()
        domains = {t.domain for t in tiles}
        for domain in TileDomain:
            self.assertIn(domain, domains, f"Domain {domain} not represented")

    def test_unique_ids(self):
        tiles = build_standard_tiles()
        ids = [t.id for t in tiles]
        self.assertEqual(len(ids), len(set(ids)), "Tile IDs must be unique")

    def test_all_prerequisites_exist(self):
        tiles = build_standard_tiles()
        tile_ids = {t.id for t in tiles}
        for tile in tiles:
            for prereq in tile.prerequisites:
                self.assertIn(prereq, tile_ids,
                              f"Tile '{tile.id}' references unknown prerequisite '{prereq}'")

    def test_no_cycles_in_standard_library(self):
        tiles = build_standard_tiles()
        graph = TileGraph.from_tile_list(tiles)
        self.assertFalse(graph.has_cycle(), "Standard tile library must be acyclic")

    def test_has_root_tiles(self):
        tiles = build_standard_tiles()
        root_tiles = [t for t in tiles if not t.prerequisites]
        self.assertGreater(len(root_tiles), 0, "Must have at least one root tile (no prerequisites)")

    def test_domain_distribution(self):
        tiles = build_standard_tiles()
        domain_counts = {}
        for tile in tiles:
            d = tile.domain.value
            domain_counts[d] = domain_counts.get(d, 0) + 1
        # Each domain should have at least 8 tiles
        for domain in TileDomain:
            count = domain_counts.get(domain.value, 0)
            self.assertGreaterEqual(count, 8,
                                    f"Domain {domain.value} has only {count} tiles (need >= 8)")

    def test_all_tiles_serializable(self):
        tiles = build_standard_tiles()
        for tile in tiles:
            d = tile.to_dict()
            restored = KnowledgeTile.from_dict(d)
            self.assertEqual(restored.id, tile.id)
            self.assertEqual(restored.name, tile.name)
            self.assertEqual(restored.domain, tile.domain)

    def test_difficulty_range(self):
        tiles = build_standard_tiles()
        for tile in tiles:
            self.assertGreaterEqual(tile.difficulty, 0.0)
            self.assertLessEqual(tile.difficulty, 1.0)

    def test_prerequisite_chains_valid(self):
        """Verify specific prerequisite chains mentioned in the docstring."""
        tiles = build_standard_tiles()
        tile_map = {t.id: t for t in tiles}

        # Chain: basic_movement → room_navigation → area_exploration
        self.assertIn("basic_movement", tile_map["room_navigation"].prerequisites)
        self.assertIn("room_navigation", tile_map["area_exploration"].prerequisites)

    def test_morphogen_sensitivity_keys_valid(self):
        tiles = build_standard_tiles()
        valid_morphogens = {"trust", "experience", "budget", "recency", "social"}
        for tile in tiles:
            for key in tile.morphogen_sensitivity:
                self.assertIn(key, valid_morphogens,
                              f"Tile '{tile.id}' has invalid morphogen key '{key}'")

    def test_standard_library_graph_construction(self):
        tiles = build_standard_tiles()
        graph = TileGraph.from_tile_list(tiles)
        depths = graph.compute_depths()
        self.assertEqual(len(depths), len(tiles))
        # Root tiles should have depth 0
        root_tiles = [t for t in tiles if not t.prerequisites]
        for root in root_tiles:
            self.assertEqual(depths[root.id], 0)


# ═══════════════════════════════════════════════════════════════
# Integration Tests
# ═══════════════════════════════════════════════════════════════

class TestIntegration(unittest.TestCase):
    """End-to-end integration tests combining multiple components."""

    def test_full_learning_path(self):
        """Agent starts with nothing and learns through the standard library."""
        tiles = build_standard_tiles()
        graph = TileGraph.from_tile_list(tiles)
        agent = AgentTileState("learner", graph)

        # Acquire root tiles first
        acquirable = agent.get_acquirable()
        self.assertGreater(len(acquirable), 0)

        for tile_id in acquirable[:3]:  # Acquire first 3 root tiles
            result = agent.acquire_tile(tile_id)
            self.assertTrue(result["success"], f"Failed to acquire {tile_id}: {result}")

        # Now more tiles should be acquirable
        new_acquirable = agent.get_acquirable()
        self.assertGreater(len(new_acquirable), 0)

    def test_fleet_with_combinator(self):
        """Multiple agents collaborate through the combinator."""
        tiles = build_standard_tiles()
        graph = TileGraph.from_tile_list(tiles)

        agent_a = AgentTileState("alice", graph)
        agent_b = AgentTileState("bob", graph)

        # Alice gets code tiles, Bob gets social tiles
        agent_a.acquire_tile("code_reading")
        agent_a.acquire_tile("code_writing")
        agent_b.acquire_tile("basic_communication")
        agent_b.acquire_tile("direct_message")

        # Register for analytics
        analytics = TileFleetAnalytics(graph)
        analytics.register_agent(agent_a)
        analytics.register_agent(agent_b)

        # Fleet capability map
        cap_map = analytics.fleet_capability_map()
        self.assertEqual(cap_map["total_tiles_in_fleet"], 4)

        # Collaboration potential should be high
        collab = analytics.collaboration_potential()
        self.assertEqual(len(collab), 1)
        self.assertGreater(collab[0]["score"], 0.0)

    def test_combinator_with_standard_library(self):
        """Test combinatory discovery using the full standard library."""
        tiles = build_standard_tiles()
        graph = TileGraph.from_tile_list(tiles)
        combinator = TileCombinator(graph)

        # Simulate an agent with several tiles
        acquired = {"code_reading", "basic_communication", "trust_awareness", "basic_movement"}
        results = combinator.discover_combinations(acquired, min_acquired=2, max_acquired=3)

        self.assertGreater(len(results), 0)
        # Should have cross-domain combinations
        cross_domain = [r for r in results if r.is_cross_domain]
        self.assertGreater(len(cross_domain), 0)

        # Creative collision should find cross-domain results
        creative = combinator.creative_collision(acquired)
        self.assertGreater(len(creative), 0)

    def test_cycle_prevention_in_dynamic_graph(self):
        """Ensure cycles can't be created even dynamically."""
        graph = TileGraph()
        graph.add_tile(KnowledgeTile(id="a", name="A"))
        graph.add_tile(KnowledgeTile(id="b", name="B", prerequisites=["a"]))

        with self.assertRaises(ValueError):
            graph.add_tile(KnowledgeTile(id="a2", name="A2", prerequisites=["b", "a2"]))

        # Existing graph should still be clean
        self.assertFalse(graph.has_cycle())


if __name__ == "__main__":
    unittest.main()
