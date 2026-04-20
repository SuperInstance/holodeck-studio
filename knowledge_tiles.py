#!/usr/bin/env python3
"""
Knowledge Tiling Framework — Composable Capability Atoms for Tabula Rasa
========================================================================

Implements Knowledge Tiling Theory: complex capabilities decompose into
composable "tiles" — minimal, reusable units of knowledge/ability. When
tiles combine in novel ways, they produce emergent capabilities ("spandrels")
that were not explicitly designed.

Analogous to:
- Protein domains combining to create new enzymatic functions
- Linguistic morphemes composing into novel meanings
- Kauffman's "adjacent possible" — only combinations one step beyond
  current capability are reachable

Architecture:
    KnowledgeTile  — atomic capability unit (the "morpheme")
    TileGraph      — directed acyclic graph of prerequisites (the "grammar")
    TileCombinator — discovers novel combinations in the adjacent possible
    AgentTileState — per-agent acquired tile inventory
    TileFleetAnalytics — fleet-wide tile coverage and collaboration potential

Design principles:
1. Tiles are the atoms from which all capabilities are built
2. Tiles compose: the whole is greater than the sum of parts
3. Emergent spandrels arise when tiles from different domains collide
4. The tile frontier is the boundary of an agent's learnable space
5. Fleet diversity maximizes the collective adjacent possible

Based on research:
- Kauffman (2000): Investigations — the adjacent possible
- Gould & Lewontin (1979): spandrels of San Marco
- Arthur (2009): The Nature of Technology — combinatory evolution
- Gärdenfors (2000): conceptual spaces as convex regions
"""

from __future__ import annotations

import math
import json
import time
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from itertools import combinations


# ═══════════════════════════════════════════════════════════════
# Tile Domain — The five capability domains
# ═══════════════════════════════════════════════════════════════

class TileDomain(Enum):
    """The five capability domains that tiles belong to."""
    CODE = "code"
    SOCIAL = "social"
    TRUST = "trust"
    CREATIVE = "creative"
    INFRASTRUCTURE = "infrastructure"


# ═══════════════════════════════════════════════════════════════
# KnowledgeTile — The Atomic Capability Unit
# ═══════════════════════════════════════════════════════════════

@dataclass
class KnowledgeTile:
    """A single minimal, composable capability atom.

    Each tile represents one irreducible unit of knowledge or ability.
    Tiles combine through prerequisite chains and creative collision.

    Attributes:
        id: Unique identifier (e.g., "basic_movement")
        name: Human-readable name
        description: What this tile represents
        domain: Which capability domain this belongs to
        prerequisites: IDs of tiles that must be acquired first
        morphogen_sensitivity: How much each morphogen affects this tile
        discovery_context: Where/how this tile was first identified
        tags: Optional categorization tags
        difficulty: Acquisition difficulty (0.0-1.0, higher = harder)
    """
    id: str
    name: str
    description: str = ""
    domain: TileDomain = TileDomain.CODE
    prerequisites: List[str] = field(default_factory=list)
    morphogen_sensitivity: Dict[str, float] = field(default_factory=dict)
    discovery_context: str = "system"
    tags: List[str] = field(default_factory=list)
    difficulty: float = 0.3

    def has_prerequisites(self, acquired: Set[str]) -> bool:
        """Check whether all prerequisite tiles are in the acquired set."""
        return all(p in acquired for p in self.prerequisites)

    def missing_prerequisites(self, acquired: Set[str]) -> List[str]:
        """Return the list of prerequisite tile IDs not yet acquired."""
        return [p for p in self.prerequisites if p not in acquired]

    def prerequisite_depth(self, tile_map: Dict[str, 'KnowledgeTile'],
                           visited: Optional[Set[str]] = None) -> int:
        """Compute the depth of this tile in the prerequisite graph.

        Root tiles (no prerequisites) have depth 0. Each prerequisite
        level adds 1. Diamond dependencies: deepest path wins.
        """
        if visited is None:
            visited = set()
        if self.id in visited:
            return 0
        visited.add(self.id)
        if not self.prerequisites:
            return 0
        max_depth = 0
        for prereq_id in self.prerequisites:
            prereq_tile = tile_map.get(prereq_id)
            if prereq_tile:
                depth = 1 + prereq_tile.prerequisite_depth(tile_map, visited.copy())
                max_depth = max(max_depth, depth)
        return max_depth

    def domain_compatibility(self, other: 'KnowledgeTile') -> float:
        """Score how compatible two tiles are for combination (0.0-1.0).

        Cross-domain pairs score higher (1.0) — they produce more
        creative collision. Same-domain pairs score 0.5.
        """
        return 1.0 if self.domain != other.domain else 0.5

    def morphogen_affinity(self, morphogen_profile: Dict[str, float]) -> float:
        """How well an agent's morphogen profile matches this tile (0.0-1.0).

        Dot product of tile sensitivity weights and agent profile values.
        """
        if not self.morphogen_sensitivity or not morphogen_profile:
            return 0.5
        dot_product = 0.0
        total_weight = 0.0
        for morph, weight in self.morphogen_sensitivity.items():
            dot_product += morphogen_profile.get(morph, 0.0) * weight
            total_weight += abs(weight)
        if total_weight == 0:
            return 0.5
        return max(0.0, min(1.0, dot_product / total_weight))

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name,
            "description": self.description,
            "domain": self.domain.value,
            "prerequisites": list(self.prerequisites),
            "morphogen_sensitivity": dict(self.morphogen_sensitivity),
            "discovery_context": self.discovery_context,
            "tags": list(self.tags), "difficulty": self.difficulty,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'KnowledgeTile':
        return cls(
            id=data["id"], name=data["name"],
            description=data.get("description", ""),
            domain=TileDomain(data.get("domain", "code")),
            prerequisites=data.get("prerequisites", []),
            morphogen_sensitivity=data.get("morphogen_sensitivity", {}),
            discovery_context=data.get("discovery_context", "system"),
            tags=data.get("tags", []),
            difficulty=data.get("difficulty", 0.3),
        )


# ═══════════════════════════════════════════════════════════════
# TileGraph — The Tiling Lattice (DAG)
# ═══════════════════════════════════════════════════════════════

class TileGraph:
    """Directed acyclic graph of tile prerequisite relationships.

    Enforces the grammar of tile composition: a tile can only be acquired
    when all its prerequisite tiles have been acquired. Computes structural
    properties like depth, bottlenecks, gateways, and frontier tiles.

    Raises:
        ValueError: if adding a tile would create a circular dependency.
    """

    def __init__(self):
        self.tiles: Dict[str, KnowledgeTile] = {}
        self._depth_cache: Dict[str, int] = {}
        self._depth_cache_valid = False

    def add_tile(self, tile: KnowledgeTile) -> bool:
        """Add a tile to the graph, checking for cycles.

        Raises ValueError if adding would create a circular dependency.
        """
        if self._would_create_cycle(tile.id, tile.prerequisites):
            raise ValueError(
                f"Adding tile '{tile.id}' would create a circular dependency"
            )
        self.tiles[tile.id] = tile
        self._depth_cache_valid = False
        return True

    def remove_tile(self, tile_id: str) -> bool:
        """Remove a tile from the graph. Returns True if it existed."""
        if tile_id in self.tiles:
            del self.tiles[tile_id]
            for tile in self.tiles.values():
                if tile_id in tile.prerequisites:
                    tile.prerequisites.remove(tile_id)
            self._depth_cache_valid = False
            return True
        return False

    def _would_create_cycle(self, tile_id: str,
                            prerequisites: List[str]) -> bool:
        """Check if adding a tile with these prerequisites creates a cycle."""
        visited: Set[str] = set()

        def dfs(current: str) -> bool:
            if current == tile_id:
                return True
            if current in visited:
                return False
            visited.add(current)
            tile = self.tiles.get(current)
            if tile:
                for prereq in tile.prerequisites:
                    if dfs(prereq):
                        return True
            return False

        for prereq in prerequisites:
            if dfs(prereq):
                return True
        return False

    def has_cycle(self) -> bool:
        """Check if the current graph contains any circular dependencies."""
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(tile_id: str) -> bool:
            visited.add(tile_id)
            rec_stack.add(tile_id)
            tile = self.tiles.get(tile_id)
            if tile:
                for prereq in tile.prerequisites:
                    if prereq not in visited:
                        if dfs(prereq):
                            return True
                    elif prereq in rec_stack:
                        return True
            rec_stack.discard(tile_id)
            return False

        for tile_id in self.tiles:
            if tile_id not in visited:
                if dfs(tile_id):
                    return True
        return False

    def compute_depths(self) -> Dict[str, int]:
        """Compute the depth of every tile (distance from root tiles).

        Root tiles have depth 0. Diamond dependencies: deepest path wins.
        """
        if self._depth_cache_valid:
            return self._depth_cache
        depths: Dict[str, int] = {}

        def get_depth(tile_id: str, visited: Set[str]) -> int:
            if tile_id in depths:
                return depths[tile_id]
            if tile_id in visited:
                return 0
            visited.add(tile_id)
            tile = self.tiles.get(tile_id)
            if not tile or not tile.prerequisites:
                depths[tile_id] = 0
                return 0
            max_prereq = 0
            for prereq_id in tile.prerequisites:
                max_prereq = max(max_prereq, get_depth(prereq_id, visited.copy()))
            depths[tile_id] = max_prereq + 1
            return depths[tile_id]

        for tile_id in self.tiles:
            if tile_id not in depths:
                get_depth(tile_id, set())
        self._depth_cache = depths
        self._depth_cache_valid = True
        return depths

    def find_paths(self, source_tiles: Set[str],
                   target_tile: str) -> List[List[str]]:
        """Find all valid learning paths from acquired tiles to a target.

        A path is an ordered list of tile IDs from first missing prerequisite
        down to the target. Only tiles not in source_tiles are included.
        """
        if target_tile not in self.tiles:
            return []
        paths: List[List[str]] = []
        self._find_paths_recursive(source_tiles, target_tile, [], set(), paths)
        return paths

    def _find_paths_recursive(self, acquired: Set[str], current: str,
                              path: List[str], visited: Set[str],
                              results: List[List[str]]):
        if current in visited:
            return
        visited.add(current)
        tile = self.tiles.get(current)
        if not tile:
            return
        missing = tile.missing_prerequisites(acquired)
        if not missing:
            results.append(list(path) + [current])
            return
        for prereq_id in missing:
            self._find_paths_recursive(
                acquired, prereq_id, list(path) + [current],
                visited.copy(), results
            )

    def find_bottleneck_tiles(self, top_n: int = 10) -> List[dict]:
        """Identify tiles required by many other tiles (critical infrastructure).

        Scored by number of transitive downstream tiles that require this tile.
        """
        downstream_counts: Dict[str, int] = {}

        def count_downstream(tile_id: str) -> int:
            if tile_id in downstream_counts:
                return downstream_counts[tile_id]
            count = sum(
                1 for other in self.tiles.values()
                if self._requires_tile(other, tile_id, set())
            )
            downstream_counts[tile_id] = count
            return count

        for tile_id in self.tiles:
            count_downstream(tile_id)

        results = sorted(downstream_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"tile_id": tid, "downstream_count": c} for tid, c in results[:top_n]]

    def _requires_tile(self, tile: KnowledgeTile, required_id: str,
                       visited: Set[str]) -> bool:
        """Check if a tile transitively requires another tile."""
        if required_id in tile.prerequisites:
            return True
        visited.add(tile.id)
        for prereq_id in tile.prerequisites:
            if prereq_id in visited:
                continue
            prereq_tile = self.tiles.get(prereq_id)
            if prereq_tile and self._requires_tile(prereq_tile, required_id, visited.copy()):
                return True
        return False

    def find_gateway_tiles(self, top_n: int = 10) -> List[dict]:
        """Identify tiles that unlock many other tiles.

        A gateway tile's acquisition makes tiles that have it as their
        only missing prerequisite become immediately acquirable.
        """
        results = []
        for tile_id in self.tiles:
            unlock_count = 0
            for other_id, other in self.tiles.items():
                if other_id == tile_id:
                    continue
                if tile_id not in other.prerequisites:
                    continue
                missing = [p for p in other.prerequisites if p != tile_id]
                if not missing:
                    unlock_count += 1
            results.append({"tile_id": tile_id, "unlock_count": unlock_count})
        results.sort(key=lambda x: x["unlock_count"], reverse=True)
        return results[:top_n]

    def compute_frontier(self, acquired: Set[str]) -> List[str]:
        """Compute the tile frontier — tiles one step from being acquirable.

        Includes tiles with all prerequisites met (immediately acquirable)
        and tiles missing exactly one prerequisite.
        """
        frontier = []
        for tile_id, tile in self.tiles.items():
            if tile_id in acquired:
                continue
            missing = tile.missing_prerequisites(acquired)
            if len(missing) <= 1:
                frontier.append(tile_id)
        return frontier

    def immediate_acquirable(self, acquired: Set[str]) -> List[str]:
        """Tiles whose prerequisites are all already acquired."""
        return [
            tid for tid, tile in self.tiles.items()
            if tid not in acquired and not tile.missing_prerequisites(acquired)
        ]

    def all_reachable(self, acquired: Set[str]) -> Set[str]:
        """All tiles eventually acquirable from current state (transitive closure)."""
        reachable = set()
        queue = list(self.immediate_acquirable(acquired))
        while queue:
            tile_id = queue.pop(0)
            if tile_id in reachable:
                continue
            reachable.add(tile_id)
            new_acquired = acquired | reachable
            for tid, tile in self.tiles.items():
                if tid not in reachable and tid not in new_acquired:
                    if not tile.missing_prerequisites(new_acquired):
                        queue.append(tid)
        return reachable

    def domain_coverage(self, acquired: Set[str]) -> Dict[str, float]:
        """What fraction of tiles in each domain have been acquired."""
        domain_totals: Dict[str, int] = {}
        domain_acquired: Dict[str, int] = {}
        for tile in self.tiles.values():
            d = tile.domain.value
            domain_totals[d] = domain_totals.get(d, 0) + 1
            if tile.id in acquired:
                domain_acquired[d] = domain_acquired.get(d, 0) + 1
        return {
            d: domain_acquired.get(d, 0) / total if total > 0 else 0.0
            for d, total in domain_totals.items()
        }

    def to_dict(self) -> dict:
        return {
            "tiles": {tid: t.to_dict() for tid, t in self.tiles.items()},
            "tile_count": len(self.tiles),
            "depths": self.compute_depths(),
            "has_cycle": self.has_cycle(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'TileGraph':
        graph = cls()
        for tid, tdata in data.get("tiles", {}).items():
            graph.add_tile(KnowledgeTile.from_dict(tdata))
        return graph

    @classmethod
    def from_tile_list(cls, tiles: List[KnowledgeTile]) -> 'TileGraph':
        """Construct a TileGraph from a list of KnowledgeTile objects."""
        graph = cls()
        for tile in tiles:
            graph.add_tile(tile)
        return graph


# ═══════════════════════════════════════════════════════════════
# TileCombinator — Novel Combination Discovery
# ═══════════════════════════════════════════════════════════════

@dataclass
class CombinationResult:
    """A potential novel tile combination discovered by the combinator."""
    tiles: Tuple[str, ...]
    novelty_score: float
    utility_score: float
    feasibility_score: float
    composite_score: float
    is_cross_domain: bool
    emergent_capabilities: List[str] = field(default_factory=list)
    mapped_permission_actions: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "tiles": list(self.tiles),
            "novelty_score": round(self.novelty_score, 4),
            "utility_score": round(self.utility_score, 4),
            "feasibility_score": round(self.feasibility_score, 4),
            "composite_score": round(self.composite_score, 4),
            "is_cross_domain": self.is_cross_domain,
            "emergent_capabilities": self.emergent_capabilities,
            "mapped_permission_actions": self.mapped_permission_actions,
        }


class TileCombinator:
    """Discovers novel tile combinations in the adjacent possible.

    Based on Kauffman's "adjacent possible": at any moment, only certain
    combinations are reachable — those one step beyond current capability.

    Scoring dimensions:
    - Novelty: how different from known combinations (cross-domain bonus)
    - Utility: how many capabilities the combination could enable
    - Feasibility: how close the agent is to having all prerequisites

    Creative collision: cross-domain combinations produce emergent spandrels.
    """

    def __init__(self, graph: TileGraph):
        self.graph = graph
        self.known_combinations: Set[Tuple[str, ...]] = set()
        self._scored_cache: Dict[Tuple[str, ...], CombinationResult] = {}
        self._combination_cache: Optional[List[CombinationResult]] = None

    def discover_combinations(self, acquired: Set[str],
                             min_acquired: int = 1,
                             max_acquired: int = 3) -> List[CombinationResult]:
        """Discover potential novel combinations from acquired tiles.

        Also explores frontier tiles — what if the agent acquires one more?
        Returns results sorted by composite score descending.
        """
        acquired_list = sorted(tid for tid in acquired if tid in self.graph.tiles)
        results: List[CombinationResult] = []

        for combo_size in range(min_acquired, min(max_acquired + 1, len(acquired_list) + 1)):
            for combo in combinations(acquired_list, combo_size):
                combo_key = tuple(sorted(combo))
                if combo_key in self._scored_cache:
                    results.append(self._scored_cache[combo_key])
                    continue
                result = self._score_combination(combo, acquired)
                if result:
                    results.append(result)
                    self.known_combinations.add(combo_key)
                    self._scored_cache[combo_key] = result

        # Check frontier tiles — what if the agent acquires one more?
        frontier = self.graph.compute_frontier(acquired)
        for frontier_tile in frontier:
            for combo_size in range(max(1, min_acquired - 1), max_acquired):
                if combo_size > len(acquired_list):
                    break
                for combo in combinations(acquired_list, combo_size):
                    combo_with = combo + (frontier_tile,)
                    combo_key = tuple(sorted(combo_with))
                    if combo_key in self._scored_cache:
                        results.append(self._scored_cache[combo_key])
                        continue
                    result = self._score_combination(combo_with, acquired)
                    if result:
                        results.append(result)
                        self.known_combinations.add(combo_key)
                        self._scored_cache[combo_key] = result

        results.sort(key=lambda r: r.composite_score, reverse=True)
        self._combination_cache = results
        return results

    def _score_combination(self, tile_ids: Tuple[str, ...],
                           acquired: Set[str]) -> Optional[CombinationResult]:
        """Score a tile combination on novelty, utility, and feasibility."""
        tiles = []
        for tid in tile_ids:
            tile = self.graph.tiles.get(tid)
            if not tile:
                return None
            tiles.append(tile)
        if not tiles:
            return None

        novelty = self._compute_novelty(tiles)
        utility = self._compute_utility(tiles, acquired)
        feasibility = self._compute_feasibility(tile_ids, acquired)
        composite = (novelty * 0.4) + (utility * 0.35) + (feasibility * 0.25)
        is_cross = len(set(t.domain for t in tiles)) > 1
        emergent = self._detect_emergent_capabilities(tiles)

        return CombinationResult(
            tiles=tuple(tile_ids), novelty_score=novelty,
            utility_score=utility, feasibility_score=feasibility,
            composite_score=composite, is_cross_domain=is_cross,
            emergent_capabilities=emergent,
        )

    def _compute_novelty(self, tiles: List[KnowledgeTile]) -> float:
        """Novelty: domain diversity + difficulty variance + unknown bonus."""
        if len(tiles) < 2:
            return 0.1
        domains = set(t.domain for t in tiles)
        domain_novelty = len(domains) / len(tiles)
        difficulties = [t.difficulty for t in tiles]
        if len(difficulties) < 2:
            diff_var = 0.3
        else:
            mean_d = sum(difficulties) / len(difficulties)
            variance = sum((d - mean_d) ** 2 for d in difficulties) / len(difficulties)
            diff_var = min(1.0, math.sqrt(variance) * 3.0)
        combo_key = tuple(sorted(t.id for t in tiles))
        known_bonus = 0.0 if combo_key in self.known_combinations else 0.3
        return min(1.0, domain_novelty * 0.4 + diff_var * 0.3 + known_bonus)

    def _compute_utility(self, tiles: List[KnowledgeTile],
                         acquired: Set[str]) -> float:
        """Utility: how many downstream capabilities this combination enables."""
        downstream = set()
        for tile in tiles:
            for tid, other in self.graph.tiles.items():
                if self.graph._requires_tile(other, tile.id, set()):
                    downstream.add(tid)
        new_caps = downstream - acquired
        total = max(len(self.graph.tiles), 1)
        return min(1.0, len(new_caps) / total * 5.0)

    def _compute_feasibility(self, tile_ids: Tuple[str, ...],
                             acquired: Set[str]) -> float:
        """Feasibility: ratio of tiles in the combination that are acquired."""
        present = sum(1 for tid in tile_ids if tid in acquired)
        return present / len(tile_ids) if tile_ids else 0.0

    def _detect_emergent_capabilities(self, tiles: List[KnowledgeTile]) -> List[str]:
        """Detect emergent spandrel capabilities from cross-domain combinations."""
        if len(tiles) < 2:
            return []
        emergent = []
        for t1, t2 in combinations(tiles, 2):
            if t1.domain != t2.domain:
                name = f"{t1.domain.value}_{t2.domain.value}_synthesis"
                if name not in emergent:
                    emergent.append(name)
        return emergent

    def creative_collision(self, acquired: Set[str],
                          min_results: int = 5) -> List[CombinationResult]:
        """Find the most creative cross-domain combinations (spandrels).

        These represent the highest-value discoveries — novel capabilities
        arising from interdisciplinary knowledge collision.
        """
        all_results = self.discover_combinations(acquired)
        cross = [r for r in all_results if r.is_cross_domain]
        cross.sort(key=lambda r: r.composite_score, reverse=True)
        return cross[:max(min_results, len(cross))]

    def map_to_permissions(self, combination: CombinationResult,
                           capability_map: Optional[Dict[str, List[str]]] = None) -> List[str]:
        """Map a discovered combination back to the permission field.

        Checks if the tile combination would activate known capabilities.
        Returns matching capability action names.
        """
        if capability_map:
            combo_key = "_".join(sorted(combination.tiles))
            return capability_map.get(combo_key, [])
        actions = [cap.replace("_synthesis", "") for cap in combination.emergent_capabilities]
        combination.mapped_permission_actions = actions
        return actions

    def to_dict(self) -> dict:
        cached = [r.to_dict() for r in self._combination_cache] if self._combination_cache else []
        return {
            "known_combinations_count": len(self.known_combinations),
            "cached_results": cached,
        }


# ═══════════════════════════════════════════════════════════════
# AgentTileState — Per-Agent Tile Inventory
# ═══════════════════════════════════════════════════════════════

@dataclass
class LearningRecord:
    """A record of when and how a tile was acquired."""
    tile_id: str
    acquired_at: float = field(default_factory=time.time)
    context: str = "system"
    method: str = "discovery"

    def to_dict(self) -> dict:
        return {
            "tile_id": self.tile_id,
            "acquired_at": self.acquired_at,
            "context": self.context,
            "method": self.method,
        }

    @classmethod
    def from_dict(cls, data: dict) -> 'LearningRecord':
        return cls(
            tile_id=data["tile_id"],
            acquired_at=data.get("acquired_at", time.time()),
            context=data.get("context", "system"),
            method=data.get("method", "discovery"),
        )


class AgentTileState:
    """Per-agent tile inventory and learning state.

    Tracks acquired tiles, learning history, and computes what the agent
    can learn next. Also computes tile-based trust compatibility:
    agents who share many tiles are likely compatible collaborators.
    """

    def __init__(self, agent_name: str, graph: TileGraph):
        self.agent_name = agent_name
        self.graph = graph
        self.acquired: Set[str] = set()
        self.learning_history: List[LearningRecord] = []
        self.created_at: float = time.time()

    def acquire_tile(self, tile_id: str, context: str = "system",
                     method: str = "discovery") -> dict:
        """Acquire a tile for this agent. Returns result dict."""
        if tile_id not in self.graph.tiles:
            return {"success": False, "error": f"Tile '{tile_id}' not found"}
        if tile_id in self.acquired:
            return {"success": False, "error": f"Already acquired '{tile_id}'"}
        tile = self.graph.tiles[tile_id]
        missing = tile.missing_prerequisites(self.acquired)
        if missing:
            return {"success": False, "error": f"Missing prerequisites: {missing}", "tile_id": tile_id}
        self.acquired.add(tile_id)
        self.learning_history.append(LearningRecord(tile_id=tile_id, context=context, method=method))
        return {
            "success": True, "tile_id": tile_id, "tile_name": tile.name,
            "domain": tile.domain.value, "total_tiles": len(self.acquired),
        }

    def release_tile(self, tile_id: str) -> bool:
        """Release (forget) a tile. Returns True if it was acquired."""
        if tile_id in self.acquired:
            self.acquired.discard(tile_id)
            return True
        return False

    def get_acquirable(self) -> List[str]:
        """Tiles whose prerequisites are all met and are not yet acquired."""
        return self.graph.immediate_acquirable(self.acquired)

    def get_blocked(self) -> Dict[str, List[str]]:
        """Tiles that cannot be acquired yet, mapped to missing prerequisites."""
        blocked = {}
        for tile_id, tile in self.graph.tiles.items():
            if tile_id in self.acquired:
                continue
            missing = tile.missing_prerequisites(self.acquired)
            if missing:
                blocked[tile_id] = missing
        return blocked

    def get_frontier(self) -> List[str]:
        """Tiles one step away from being acquirable."""
        return self.graph.compute_frontier(self.acquired)

    def tile_count(self) -> int:
        return len(self.acquired)

    def domain_summary(self) -> Dict[str, int]:
        """Count of acquired tiles per domain."""
        summary: Dict[str, int] = {}
        for tile_id in self.acquired:
            tile = self.graph.tiles.get(tile_id)
            if tile:
                d = tile.domain.value
                summary[d] = summary.get(d, 0) + 1
        return summary

    def trust_compatibility(self, other: 'AgentTileState') -> float:
        """Tile-based trust with another agent (Jaccard similarity, 0.0-1.0).

        Agents who share many tiles are likely compatible collaborators.
        """
        if not self.acquired and not other.acquired:
            return 0.5
        intersection = self.acquired & other.acquired
        union = self.acquired | other.acquired
        return len(intersection) / len(union) if union else 0.5

    def complementary_score(self, other: 'AgentTileState') -> float:
        """How much complementary knowledge two agents have (0.0-1.0).

        High score means their combined knowledge greatly exceeds either alone.
        """
        only_self = len(self.acquired - other.acquired)
        only_other = len(other.acquired - self.acquired)
        total_unique = only_self + only_other
        total = max(len(self.graph.tiles), 1)
        return min(1.0, total_unique / total)

    def learning_velocity(self, window_seconds: float = 3600.0) -> float:
        """How quickly this agent is acquiring tiles (tiles per hour)."""
        cutoff = time.time() - window_seconds
        recent = sum(1 for r in self.learning_history if r.acquired_at >= cutoff)
        return recent / (window_seconds / 3600.0)

    def to_dict(self) -> dict:
        return {
            "agent_name": self.agent_name, "created_at": self.created_at,
            "acquired": sorted(self.acquired), "tile_count": len(self.acquired),
            "learning_history": [r.to_dict() for r in self.learning_history],
            "domain_summary": self.domain_summary(),
            "acquirable": self.get_acquirable(), "frontier": self.get_frontier(),
        }

    @classmethod
    def from_dict(cls, data: dict, graph: TileGraph) -> 'AgentTileState':
        state = cls(data["agent_name"], graph)
        state.created_at = data.get("created_at", time.time())
        state.acquired = set(data.get("acquired", []))
        state.learning_history = [
            LearningRecord.from_dict(r) for r in data.get("learning_history", [])
        ]
        return state


# ═══════════════════════════════════════════════════════════════
# TileFleetAnalytics — Fleet-Wide Tile Analysis
# ═══════════════════════════════════════════════════════════════

class TileFleetAnalytics:
    """Fleet-wide tile analysis and collaboration optimization.

    Analyzes collective tile state across all agents:
    - Tile coverage: fleet-wide adoption rate per tile
    - Tile diversity: evenness of tile distribution (Shannon entropy)
    - Discovery velocity: rate of new tile acquisition
    - Collaboration potential: optimal agent pairs for combined capability
    - Fleet capability map: union of all tiles = total capability surface
    """

    def __init__(self, graph: TileGraph):
        self.graph = graph
        self.agents: Dict[str, AgentTileState] = {}

    def register_agent(self, state: AgentTileState):
        self.agents[state.agent_name] = state

    def unregister_agent(self, agent_name: str) -> bool:
        if agent_name in self.agents:
            del self.agents[agent_name]
            return True
        return False

    def tile_coverage(self) -> Dict[str, float]:
        """What percentage of the fleet has each tile (0.0-1.0)."""
        if not self.agents:
            return {}
        total = len(self.agents)
        return {
            tid: sum(1 for s in self.agents.values() if tid in s.acquired) / total
            for tid in self.graph.tiles
        }

    def tile_diversity(self) -> float:
        """How evenly distributed are tiles across agents (0.0-1.0).

        Normalized Shannon entropy. 1.0 = perfectly even distribution.
        """
        if not self.agents or not self.graph.tiles:
            return 0.0
        coverage = self.tile_coverage()
        n = len(coverage)
        if n == 0:
            return 0.0
        entropy = -sum(r * math.log2(r) for r in coverage.values() if r > 0)
        max_entropy = math.log2(n) if n > 1 else 1.0
        return entropy / max_entropy if max_entropy > 0 else 0.0

    def discovery_velocity(self, window_seconds: float = 3600.0) -> float:
        """Fleet-wide tile discovery rate (tiles/hour)."""
        return sum(s.learning_velocity(window_seconds) for s in self.agents.values())

    def collaboration_potential(self, top_n: int = 10) -> List[dict]:
        """Find agent pairs whose combined tiles create the most value.

        Scored by complementary knowledge, frontier expansion, and
        combined reachability.
        """
        names = list(self.agents.keys())
        results = []
        for i in range(len(names)):
            for j in range(i + 1, len(names)):
                a, b = self.agents[names[i]], self.agents[names[j]]
                complementary = a.complementary_score(b)
                combined = a.acquired | b.acquired
                frontier = len(self.graph.compute_frontier(combined))
                reachable = len(self.graph.all_reachable(combined))
                total = max(len(self.graph.tiles), 1)
                score = (complementary * 0.4 +
                         min(1.0, frontier / total) * 0.3 +
                         min(1.0, reachable / total) * 0.3)
                results.append({
                    "agent_a": names[i], "agent_b": names[j],
                    "score": round(score, 4),
                    "complementary": round(complementary, 4),
                    "combined_frontier_size": frontier,
                    "combined_reachable": reachable,
                    "shared_tiles": len(a.acquired & b.acquired),
                    "unique_tiles_a": len(a.acquired - b.acquired),
                    "unique_tiles_b": len(b.acquired - a.acquired),
                })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]

    def fleet_capability_map(self) -> dict:
        """Union of all agent tiles = fleet's total capability surface."""
        union: Set[str] = set()
        per_agent: Dict[str, int] = {}
        for name, state in self.agents.items():
            per_agent[name] = len(state.acquired)
            union |= state.acquired
        domain_breakdown: Dict[str, int] = {}
        for tid in union:
            tile = self.graph.tiles.get(tid)
            if tile:
                d = tile.domain.value
                domain_breakdown[d] = domain_breakdown.get(d, 0) + 1
        blind_spots = [tid for tid in self.graph.tiles if tid not in union]
        return {
            "total_agents": len(self.agents),
            "total_tiles_in_fleet": len(union),
            "total_tiles_in_graph": len(self.graph.tiles),
            "coverage_ratio": len(union) / max(len(self.graph.tiles), 1),
            "per_agent_counts": per_agent,
            "domain_breakdown": domain_breakdown,
            "blind_spots": blind_spots,
            "frontier_tiles": self.graph.compute_frontier(union),
        }

    def fleet_domain_matrix(self) -> Dict[str, Dict[str, int]]:
        """Agent × domain matrix of tile counts."""
        return {name: state.domain_summary() for name, state in self.agents.items()}

    def most_unique_agents(self, top_n: int = 5) -> List[dict]:
        """Agents with the most unique (non-overlapping) tiles."""
        if not self.agents:
            return []
        names = list(self.agents.keys())
        results = []
        for name in names:
            others: Set[str] = set()
            for other_name in names:
                if other_name != name:
                    others |= self.agents[other_name].acquired
            unique = self.agents[name].acquired - others
            results.append({
                "agent": name,
                "unique_tile_count": len(unique),
                "unique_tiles": sorted(unique),
                "total_tiles": len(self.agents[name].acquired),
                "uniqueness_ratio": len(unique) / max(len(self.agents[name].acquired), 1),
            })
        results.sort(key=lambda x: x["unique_tile_count"], reverse=True)
        return results[:top_n]

    def to_dict(self) -> dict:
        return {
            "agent_count": len(self.agents),
            "tile_diversity": round(self.tile_diversity(), 4),
            "fleet_capability_map": self.fleet_capability_map(),
            "domain_matrix": self.fleet_domain_matrix(),
        }


# ═══════════════════════════════════════════════════════════════
# Standard Tile Library — Built-in Tiles for Tabula Rasa
# ═══════════════════════════════════════════════════════════════

def _t(tid: str, name: str, desc: str, domain: TileDomain,
        prereqs: Optional[List[str]] = None,
        morph: Optional[Dict[str, float]] = None,
        ctx: str = "system", tags: Optional[List[str]] = None,
        diff: float = 0.3) -> KnowledgeTile:
    """Helper to construct a KnowledgeTile concisely."""
    return KnowledgeTile(
        id=tid, name=name, description=desc, domain=domain,
        prerequisites=prereqs or [],
        morphogen_sensitivity=morph or {},
        discovery_context=ctx, tags=tags or [], difficulty=diff,
    )


def build_standard_tiles() -> List[KnowledgeTile]:
    """Build the standard set of 50 knowledge tiles for Tabula Rasa.

    Maps PermissionLevel capabilities, spells, room capabilities, and trust
    dimensions into composable tile atoms across five domains.

    Prerequisite chain examples:
        code_reading → code_writing → debugging → code_review → refactoring
        basic_movement → room_navigation → area_exploration
        basic_communication → direct_message → group_communication → broadcast
        trust_awareness → reputation_reading → trust_establishment → trust_delegation
        basic_design → room_concept → room_building → area_design → world_design
    """
    tiles: List[KnowledgeTile] = []

    # ── CODE Domain (10 tiles) ─────────────────────────────────
    tiles.append(_t("code_reading", "Code Reading",
        "Ability to read and understand code", TileDomain.CODE,
        morph={"experience": 0.5, "trust": 0.2, "budget": 0.1, "recency": 0.1, "social": 0.1},
        ctx="level_0_greenhorn", tags=["code", "fundamental"], diff=0.1))
    tiles.append(_t("code_writing", "Code Writing",
        "Ability to write syntactically correct code", TileDomain.CODE,
        prereqs=["code_reading"],
        morph={"experience": 0.5, "trust": 0.2, "budget": 0.1, "recency": 0.1, "social": 0.1},
        ctx="level_1_crew", tags=["code", "fundamental"], diff=0.2))
    tiles.append(_t("debugging", "Debugging",
        "Ability to identify and fix bugs", TileDomain.CODE,
        prereqs=["code_reading"],
        morph={"experience": 0.4, "trust": 0.2, "budget": 0.2, "recency": 0.1, "social": 0.1},
        ctx="level_1_crew", tags=["code", "quality"], diff=0.3))
    tiles.append(_t("testing", "Testing",
        "Ability to write and maintain automated tests", TileDomain.CODE,
        prereqs=["code_writing"],
        morph={"experience": 0.4, "trust": 0.2, "budget": 0.2, "recency": 0.1, "social": 0.1},
        ctx="level_2_specialist", tags=["code", "quality"], diff=0.35))
    tiles.append(_t("code_review", "Code Review",
        "Ability to review code for quality and correctness", TileDomain.CODE,
        prereqs=["code_writing", "debugging"],
        morph={"experience": 0.4, "trust": 0.3, "budget": 0.1, "recency": 0.1, "social": 0.1},
        ctx="level_3_captain", tags=["code", "quality", "trust"], diff=0.5))
    tiles.append(_t("refactoring", "Refactoring",
        "Ability to restructure code without changing behavior", TileDomain.CODE,
        prereqs=["code_writing", "debugging", "code_review"],
        morph={"experience": 0.5, "trust": 0.3, "budget": 0.1, "recency": 0.1, "social": 0.0},
        ctx="level_4_cocapn", tags=["code", "quality"], diff=0.6))
    tiles.append(_t("api_design", "API Design",
        "Ability to design clean API interfaces", TileDomain.CODE,
        prereqs=["code_writing", "code_review"],
        morph={"experience": 0.4, "trust": 0.2, "budget": 0.1, "recency": 0.1, "social": 0.2},
        ctx="level_3_captain", tags=["code", "design"], diff=0.55))
    tiles.append(_t("system_architecture", "System Architecture",
        "Ability to design multi-component architectures", TileDomain.CODE,
        prereqs=["api_design", "refactoring"],
        morph={"experience": 0.5, "trust": 0.3, "budget": 0.1, "recency": 0.0, "social": 0.1},
        ctx="level_4_cocapn", tags=["code", "design", "leadership"], diff=0.7))
    tiles.append(_t("spell_crafting", "Spell Crafting",
        "Ability to create new spells in the MUD system", TileDomain.CODE,
        prereqs=["code_writing", "basic_design"],
        morph={"experience": 0.4, "trust": 0.3, "budget": 0.2, "recency": 0.0, "social": 0.1},
        ctx="level_3_captain", tags=["code", "creative", "magic"], diff=0.55))
    tiles.append(_t("engine_modification", "Engine Modification",
        "Ability to modify core MUD engine physics", TileDomain.CODE,
        prereqs=["system_architecture", "refactoring"],
        morph={"experience": 0.3, "trust": 0.5, "budget": 0.1, "recency": 0.0, "social": 0.1},
        ctx="level_5_architect", tags=["code", "governance"], diff=0.9))

    # ── SOCIAL Domain (10 tiles) ───────────────────────────────
    tiles.append(_t("basic_communication", "Basic Communication",
        "Ability to say, tell, and use help commands", TileDomain.SOCIAL,
        morph={"social": 0.3, "experience": 0.2, "trust": 0.2, "budget": 0.1, "recency": 0.2},
        ctx="level_0_greenhorn", tags=["social", "fundamental"], diff=0.05))
    tiles.append(_t("direct_message", "Direct Message",
        "Ability to send private messages", TileDomain.SOCIAL,
        prereqs=["basic_communication"],
        morph={"social": 0.4, "trust": 0.2, "experience": 0.1, "budget": 0.1, "recency": 0.2},
        ctx="level_1_crew", tags=["social", "communication"], diff=0.15))
    tiles.append(_t("group_communication", "Group Communication",
        "Ability to yell, gossip, and participate in channels", TileDomain.SOCIAL,
        prereqs=["direct_message"],
        morph={"social": 0.5, "trust": 0.2, "experience": 0.1, "budget": 0.1, "recency": 0.1},
        ctx="level_2_specialist", tags=["social", "communication"], diff=0.25))
    tiles.append(_t("knowledge_sharing", "Knowledge Sharing",
        "Ability to write notes and contribute to shared understanding", TileDomain.SOCIAL,
        prereqs=["basic_communication"],
        morph={"social": 0.3, "experience": 0.3, "trust": 0.2, "budget": 0.1, "recency": 0.1},
        ctx="level_1_crew", tags=["social", "knowledge"], diff=0.2))
    tiles.append(_t("broadcast", "Fleet Broadcast",
        "Ability to broadcast messages to the entire fleet", TileDomain.SOCIAL,
        prereqs=["group_communication", "knowledge_sharing"],
        morph={"social": 0.3, "trust": 0.4, "experience": 0.1, "budget": 0.1, "recency": 0.1},
        ctx="level_4_cocapn", tags=["social", "communication", "leadership"], diff=0.65))
    tiles.append(_t("mentorship", "Mentorship",
        "Ability to teach and guide other agents", TileDomain.SOCIAL,
        prereqs=["knowledge_sharing", "direct_message"],
        morph={"social": 0.4, "trust": 0.3, "experience": 0.2, "budget": 0.0, "recency": 0.1},
        ctx="level_3_captain", tags=["social", "teaching"], diff=0.5))
    tiles.append(_t("negotiation", "Negotiation",
        "Ability to negotiate resource sharing and task allocation", TileDomain.SOCIAL,
        prereqs=["direct_message", "trust_establishment"],
        morph={"social": 0.4, "trust": 0.3, "experience": 0.2, "budget": 0.1, "recency": 0.0},
        ctx="level_3_captain", tags=["social", "trust"], diff=0.5))
    tiles.append(_t("conflict_resolution", "Conflict Resolution",
        "Ability to mediate disputes between agents", TileDomain.SOCIAL,
        prereqs=["negotiation", "mentorship"],
        morph={"social": 0.3, "trust": 0.4, "experience": 0.2, "budget": 0.0, "recency": 0.1},
        ctx="level_4_cocapn", tags=["social", "trust", "leadership"], diff=0.6))
    tiles.append(_t("fleet_coordination", "Fleet Coordination",
        "Ability to coordinate multiple agents toward a shared goal", TileDomain.SOCIAL,
        prereqs=["broadcast", "conflict_resolution"],
        morph={"social": 0.3, "trust": 0.3, "experience": 0.2, "budget": 0.1, "recency": 0.1},
        ctx="level_4_cocapn", tags=["social", "leadership"], diff=0.7))
    tiles.append(_t("cultural_transmission", "Cultural Transmission",
        "Ability to establish norms and culture across the fleet", TileDomain.SOCIAL,
        prereqs=["fleet_coordination", "mentorship"],
        morph={"social": 0.4, "trust": 0.3, "experience": 0.2, "budget": 0.0, "recency": 0.1},
        ctx="level_5_architect", tags=["social", "leadership", "creative"], diff=0.8))

    # ── TRUST Domain (10 tiles) ────────────────────────────────
    tiles.append(_t("trust_awareness", "Trust Awareness",
        "Understanding that actions have trust consequences", TileDomain.TRUST,
        morph={"trust": 0.5, "social": 0.2, "experience": 0.2, "budget": 0.1, "recency": 0.0},
        ctx="level_0_greenhorn", tags=["trust", "fundamental"], diff=0.1))
    tiles.append(_t("reputation_reading", "Reputation Reading",
        "Ability to read and interpret trust/reputation scores", TileDomain.TRUST,
        prereqs=["trust_awareness"],
        morph={"trust": 0.5, "social": 0.2, "experience": 0.2, "budget": 0.0, "recency": 0.1},
        ctx="level_1_crew", tags=["trust", "information"], diff=0.2))
    tiles.append(_t("trust_establishment", "Trust Establishment",
        "Ability to build trust through consistent behavior", TileDomain.TRUST,
        prereqs=["trust_awareness"],
        morph={"trust": 0.5, "experience": 0.3, "recency": 0.1, "social": 0.1, "budget": 0.0},
        ctx="level_2_specialist", tags=["trust", "growth"], diff=0.35))
    tiles.append(_t("trust_verification", "Trust Verification",
        "Ability to verify trustworthiness of agents", TileDomain.TRUST,
        prereqs=["reputation_reading"],
        morph={"trust": 0.5, "experience": 0.2, "social": 0.1, "budget": 0.1, "recency": 0.1},
        ctx="level_2_specialist", tags=["trust", "security"], diff=0.35))
    tiles.append(_t("trust_delegation", "Trust Delegation",
        "Ability to delegate tasks and trust agents to complete them", TileDomain.TRUST,
        prereqs=["trust_establishment", "reputation_reading"],
        morph={"trust": 0.5, "social": 0.2, "experience": 0.2, "budget": 0.1, "recency": 0.0},
        ctx="level_3_captain", tags=["trust", "leadership"], diff=0.5))
    tiles.append(_t("reputation_building", "Reputation Building",
        "Active strategy to increase trust through quality work", TileDomain.TRUST,
        prereqs=["trust_establishment", "trust_verification"],
        morph={"trust": 0.4, "experience": 0.3, "social": 0.2, "budget": 0.1, "recency": 0.0},
        ctx="level_3_captain", tags=["trust", "growth"], diff=0.45))
    tiles.append(_t("trust_recovery", "Trust Recovery",
        "Ability to recover trust after mistakes or failures", TileDomain.TRUST,
        prereqs=["trust_establishment"],
        morph={"trust": 0.5, "experience": 0.2, "social": 0.1, "recency": 0.2, "budget": 0.0},
        ctx="level_3_captain", tags=["trust", "resilience"], diff=0.5))
    tiles.append(_t("collective_trust", "Collective Trust",
        "Understanding and managing fleet-wide trust dynamics", TileDomain.TRUST,
        prereqs=["trust_delegation", "reputation_building"],
        morph={"trust": 0.4, "social": 0.3, "experience": 0.2, "budget": 0.0, "recency": 0.1},
        ctx="level_4_cocapn", tags=["trust", "leadership"], diff=0.6))
    tiles.append(_t("trust_boundaries", "Trust Boundaries",
        "Understanding when NOT to trust and setting limits", TileDomain.TRUST,
        prereqs=["trust_verification", "trust_recovery"],
        morph={"trust": 0.5, "social": 0.1, "experience": 0.2, "budget": 0.1, "recency": 0.1},
        ctx="level_4_cocapn", tags=["trust", "security"], diff=0.55))
    tiles.append(_t("trust_architecture", "Trust Architecture",
        "Ability to design and modify the trust system itself", TileDomain.TRUST,
        prereqs=["collective_trust", "trust_boundaries"],
        morph={"trust": 0.4, "experience": 0.3, "social": 0.2, "budget": 0.0, "recency": 0.1},
        ctx="level_5_architect", tags=["trust", "governance"], diff=0.85))

    # ── CREATIVE Domain (10 tiles) ─────────────────────────────
    tiles.append(_t("basic_design", "Basic Design",
        "Fundamental sense of aesthetics and design principles", TileDomain.CREATIVE,
        morph={"experience": 0.4, "budget": 0.2, "trust": 0.1, "social": 0.2, "recency": 0.1},
        ctx="level_1_crew", tags=["creative", "fundamental"], diff=0.15))
    tiles.append(_t("room_concept", "Room Concept",
        "Ability to conceptualize and plan a room's purpose", TileDomain.CREATIVE,
        prereqs=["basic_design"],
        morph={"experience": 0.4, "budget": 0.2, "trust": 0.1, "social": 0.2, "recency": 0.1},
        ctx="level_2_specialist", tags=["creative", "rooms"], diff=0.3))
    tiles.append(_t("room_building", "Room Building",
        "Ability to construct and configure a room", TileDomain.CREATIVE,
        prereqs=["room_concept", "code_writing"],
        morph={"experience": 0.4, "budget": 0.2, "trust": 0.1, "social": 0.2, "recency": 0.1},
        ctx="level_2_specialist", tags=["creative", "rooms"], diff=0.35))
    tiles.append(_t("npc_creation", "NPC Creation",
        "Ability to create NPCs with behaviors", TileDomain.CREATIVE,
        prereqs=["room_building", "basic_communication"],
        morph={"experience": 0.4, "budget": 0.2, "trust": 0.1, "social": 0.2, "recency": 0.1},
        ctx="level_2_specialist", tags=["creative", "npcs"], diff=0.4))
    tiles.append(_t("item_design", "Item Design",
        "Ability to create items with properties", TileDomain.CREATIVE,
        prereqs=["room_building", "code_writing"],
        morph={"experience": 0.3, "budget": 0.2, "trust": 0.1, "social": 0.1, "recency": 0.1},
        ctx="level_2_specialist", tags=["creative", "items"], diff=0.35))
    tiles.append(_t("area_design", "Area Design",
        "Ability to design interconnected areas with rooms", TileDomain.CREATIVE,
        prereqs=["room_building"],
        morph={"experience": 0.5, "budget": 0.2, "trust": 0.1, "social": 0.1, "recency": 0.1},
        ctx="level_3_captain", tags=["creative", "areas"], diff=0.5))
    tiles.append(_t("adventure_design", "Adventure Design",
        "Ability to design adventures with quests", TileDomain.CREATIVE,
        prereqs=["area_design", "npc_creation"],
        morph={"experience": 0.4, "budget": 0.2, "trust": 0.2, "social": 0.2, "recency": 0.0},
        ctx="level_3_captain", tags=["creative", "adventures"], diff=0.55))
    tiles.append(_t("world_design", "World Design",
        "Ability to design coherent world systems and lore", TileDomain.CREATIVE,
        prereqs=["area_design", "adventure_design"],
        morph={"experience": 0.4, "budget": 0.2, "trust": 0.2, "social": 0.2, "recency": 0.0},
        ctx="level_4_cocapn", tags=["creative", "world"], diff=0.7))
    tiles.append(_t("aesthetic_judgment", "Aesthetic Judgment",
        "Refined ability to evaluate and improve design quality", TileDomain.CREATIVE,
        prereqs=["basic_design", "room_building", "code_review"],
        morph={"experience": 0.4, "trust": 0.3, "budget": 0.1, "social": 0.2, "recency": 0.0},
        ctx="level_4_cocapn", tags=["creative", "quality"], diff=0.6))
    tiles.append(_t("creative_synthesis", "Creative Synthesis",
        "Ability to fuse disparate concepts into novel creations", TileDomain.CREATIVE,
        prereqs=["world_design", "aesthetic_judgment"],
        morph={"experience": 0.3, "budget": 0.2, "trust": 0.2, "social": 0.2, "recency": 0.1},
        ctx="level_5_architect", tags=["creative", "innovation"], diff=0.85))

    # ── INFRASTRUCTURE Domain (10 tiles) ───────────────────────
    tiles.append(_t("basic_movement", "Basic Movement",
        "Ability to look around and move between rooms", TileDomain.INFRASTRUCTURE,
        morph={"experience": 0.3, "budget": 0.2, "recency": 0.2, "trust": 0.1, "social": 0.2},
        ctx="level_0_greenhorn", tags=["infra", "fundamental", "navigation"], diff=0.05))
    tiles.append(_t("room_navigation", "Room Navigation",
        "Ability to navigate complex room layouts", TileDomain.INFRASTRUCTURE,
        prereqs=["basic_movement"],
        morph={"experience": 0.3, "budget": 0.2, "recency": 0.3, "trust": 0.1, "social": 0.1},
        ctx="level_1_crew", tags=["infra", "navigation"], diff=0.15))
    tiles.append(_t("area_exploration", "Area Exploration",
        "Ability to explore and map interconnected areas", TileDomain.INFRASTRUCTURE,
        prereqs=["room_navigation"],
        morph={"experience": 0.3, "budget": 0.2, "recency": 0.2, "trust": 0.1, "social": 0.2},
        ctx="level_2_specialist", tags=["infra", "navigation"], diff=0.25))
    tiles.append(_t("room_usage", "Room Usage",
        "Ability to enter and use tool rooms", TileDomain.INFRASTRUCTURE,
        prereqs=["basic_movement"],
        morph={"experience": 0.2, "budget": 0.3, "recency": 0.2, "trust": 0.1, "social": 0.2},
        ctx="level_1_crew", tags=["infra", "rooms"], diff=0.15))
    tiles.append(_t("monitoring", "Monitoring",
        "Ability to use monitoring rooms and watch data streams", TileDomain.INFRASTRUCTURE,
        prereqs=["room_usage"],
        morph={"experience": 0.3, "budget": 0.2, "recency": 0.3, "trust": 0.1, "social": 0.1},
        ctx="level_2_specialist", tags=["infra", "monitoring"], diff=0.3))
    tiles.append(_t("resource_management", "Resource Management",
        "Ability to manage mana, HP, and resource budgets", TileDomain.INFRASTRUCTURE,
        prereqs=["room_usage", "trust_awareness"],
        morph={"budget": 0.4, "experience": 0.2, "trust": 0.2, "recency": 0.1, "social": 0.1},
        ctx="level_2_specialist", tags=["infra", "resources"], diff=0.3))
    tiles.append(_t("equipment_usage", "Equipment Usage",
        "Ability to equip and use items and equipment", TileDomain.INFRASTRUCTURE,
        prereqs=["room_usage"],
        morph={"experience": 0.3, "budget": 0.2, "trust": 0.1, "recency": 0.2, "social": 0.2},
        ctx="level_2_specialist", tags=["infra", "equipment"], diff=0.25))
    tiles.append(_t("vessel_management", "Vessel Management",
        "Ability to manage a ship: install rooms, manage crew", TileDomain.INFRASTRUCTURE,
        prereqs=["room_navigation", "room_usage"],
        morph={"experience": 0.3, "trust": 0.2, "budget": 0.2, "recency": 0.1, "social": 0.2},
        ctx="level_3_captain", tags=["infra", "vessels"], diff=0.45))
    tiles.append(_t("fleet_ops", "Fleet Operations",
        "Ability to manage and coordinate multiple vessels", TileDomain.INFRASTRUCTURE,
        prereqs=["vessel_management", "fleet_coordination"],
        morph={"trust": 0.3, "experience": 0.3, "budget": 0.1, "recency": 0.1, "social": 0.2},
        ctx="level_4_cocapn", tags=["infra", "fleet"], diff=0.65))
    tiles.append(_t("permission_management", "Permission Management",
        "Ability to manage and modify the permission system", TileDomain.INFRASTRUCTURE,
        prereqs=["trust_boundaries", "vessel_management"],
        morph={"trust": 0.4, "experience": 0.3, "budget": 0.1, "recency": 0.0, "social": 0.2},
        ctx="level_4_cocapn", tags=["infra", "governance"], diff=0.7))

    return tiles
