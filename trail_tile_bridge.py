"""
Trail x Tile Integration Bridge
================================

The core concept: **Trails unlock Tiles**.

When an agent executes a compiled trail, the trail's opcodes map to knowledge
tile completions. A trail that demonstrates TRUST_UPDATE + CODE_REVIEW opcodes
should auto-complete the corresponding knowledge tiles.

Architecture:
    TrailTileConfig    — configuration dataclass (mappings, thresholds, limits)
    TrailTileResult    — result of processing a single trail
    TrailTileBridge    — the bridge engine that connects trail opcodes to tiles
    DEFAULT_OPCODE_TILE_MAP — built-in mapping of trail opcodes to tile IDs

Trail opcodes from trail_encoder.py (TrailOpcodes):
    GIT_COMMIT, GIT_PUSH, FILE_READ, FILE_WRITE, FILE_EDIT,
    TEST_RUN, SEARCH_CODE, BOTTLE_DROP, BOTTLE_READ, LEVEL_UP,
    SPELL_CAST, ROOM_ENTER, TRUST_UPDATE, CAP_ISSUE, BRANCH, NOP,
    TRAIL_BEGIN, TRAIL_END, COMMENT, LABEL, HASHTABLE

Knowledge tiles from knowledge_tiles.py (50 tiles across 5 domains):
    CODE: code_reading, code_writing, debugging, testing, code_review,
          refactoring, api_design, system_architecture, spell_crafting,
          engine_modification
    SOCIAL: basic_communication, direct_message, group_communication,
            knowledge_sharing, broadcast, mentorship, negotiation,
            conflict_resolution, fleet_coordination, cultural_transmission
    TRUST: trust_awareness, reputation_reading, trust_establishment,
           trust_verification, trust_delegation, reputation_building,
           trust_recovery, collective_trust, trust_boundaries, trust_architecture
    CREATIVE: basic_design, room_concept, room_building, npc_creation,
              item_design, area_design, adventure_design, world_design,
              aesthetic_judgment, creative_synthesis
    INFRASTRUCTURE: basic_movement, room_navigation, area_exploration,
                    room_usage, monitoring, resource_management, equipment_usage,
                    vessel_management, fleet_ops, permission_management
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any


# ═══════════════════════════════════════════════════════════════
# Default Opcode-to-Tile Mapping
# ═══════════════════════════════════════════════════════════════

DEFAULT_OPCODE_TILE_MAP: Dict[str, str] = {
    # ── Trust-building opcodes → TRUST & SOCIAL tiles ──
    "TRUST_UPDATE":       "trust_establishment",
    "BOTTLE_DROP":        "knowledge_sharing",
    "BOTTLE_READ":        "knowledge_sharing",

    # ── Capability/permission opcodes → TRUST & INFRA tiles ──
    "CAP_ISSUE":          "permission_management",
    "LEVEL_UP":           "trust_boundaries",

    # ── Code manipulation opcodes → CODE tiles ──
    "FILE_READ":          "code_reading",
    "FILE_WRITE":         "code_writing",
    "FILE_EDIT":          "refactoring",
    "SEARCH_CODE":        "debugging",
    "TEST_RUN":           "testing",
    "GIT_COMMIT":         "code_review",
    "GIT_PUSH":           "api_design",

    # ── Creative/spell opcodes → CREATIVE tiles ──
    "SPELL_CAST":         "spell_crafting",

    # ── Spatial/room opcodes → INFRASTRUCTURE tiles ──
    "ROOM_ENTER":         "room_navigation",
    "BRANCH":             "system_architecture",

    # ── Meta opcodes (no direct tile mapping, but included for completeness) ──
    "TRAIL_BEGIN":        "basic_movement",
    "TRAIL_END":          "fleet_coordination",
    "COMMENT":            "cultural_transmission",
    "LABEL":              "basic_design",
    "NOP":                "monitoring",
}
# Total: 20 mappings covering all 20 TrailOpcodes


# ═══════════════════════════════════════════════════════════════
# TrailTileConfig — Configuration Dataclass
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrailTileConfig:
    """Configuration for the Trail-to-Tile bridge.

    Attributes:
        opcode_tile_mapping: Maps trail opcode names to knowledge tile IDs.
        auto_complete_threshold: Minimum trail score (0.0-1.0) to auto-complete
            a tile. A trail must achieve at least this score for a tile
            to be marked as completed.
        max_tiles_per_trail: Maximum number of tiles a single trail can
            complete. Tiles beyond this limit are only progressed, not completed.
    """
    opcode_tile_mapping: Dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_OPCODE_TILE_MAP)
    )
    auto_complete_threshold: float = 0.7
    max_tiles_per_trail: int = 5

    def to_dict(self) -> dict:
        return {
            "opcode_tile_mapping": dict(self.opcode_tile_mapping),
            "auto_complete_threshold": self.auto_complete_threshold,
            "max_tiles_per_trail": self.max_tiles_per_trail,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrailTileConfig:
        return cls(
            opcode_tile_mapping=data.get(
                "opcode_tile_mapping", dict(DEFAULT_OPCODE_TILE_MAP)
            ),
            auto_complete_threshold=data.get("auto_complete_threshold", 0.7),
            max_tiles_per_trail=data.get("max_tiles_per_trail", 5),
        )


# ═══════════════════════════════════════════════════════════════
# TrailTileResult — Processing Result Dataclass
# ═══════════════════════════════════════════════════════════════

@dataclass
class TrailTileResult:
    """Result of processing a single trail through the bridge.

    Attributes:
        trail_hash: SHA-256 hash of the trail data (identifies the trail).
        tiles_completed: List of tile IDs that were auto-completed by this trail.
        tiles_progressed: Dict mapping tile IDs to their new progress score (0.0-1.0).
        confidence: Overall confidence in the mapping quality (0.0-1.0).
            Based on how many opcodes successfully mapped to tiles vs. unknown opcodes.
    """
    trail_hash: str
    tiles_completed: List[str] = field(default_factory=list)
    tiles_progressed: Dict[str, float] = field(default_factory=dict)
    confidence: float = 0.0

    def to_dict(self) -> dict:
        return {
            "trail_hash": self.trail_hash,
            "tiles_completed": list(self.tiles_completed),
            "tiles_progressed": dict(self.tiles_progressed),
            "confidence": self.confidence,
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrailTileResult:
        return cls(
            trail_hash=data["trail_hash"],
            tiles_completed=data.get("tiles_completed", []),
            tiles_progressed=data.get("tiles_progressed", {}),
            confidence=data.get("confidence", 0.0),
        )


# ═══════════════════════════════════════════════════════════════
# TrailTileBridge — The Integration Bridge Engine
# ═══════════════════════════════════════════════════════════════

class TrailTileBridge:
    """Bridges compiled trail opcodes to knowledge tile completions.

    When an agent executes a trail (a sequence of opcodes), this bridge
    maps each opcode to the corresponding knowledge tile. If enough
    relevant opcodes are present in a trail, the corresponding tiles
    are auto-completed.

    The bridge tracks per-agent progress so that multiple trails can
    cumulatively contribute toward tile completion.

    Usage:
        config = TrailTileConfig()
        bridge = TrailTileBridge(config)
        result = bridge.process_trail({
            "agent": "navi-7",
            "opcodes": ["FILE_READ", "FILE_WRITE", "TEST_RUN"],
            "score": 0.85,
        })
    """

    def __init__(
        self,
        config: Optional[TrailTileConfig] = None,
        tile_graph: Optional[Any] = None,
        trail_engine: Optional[Any] = None,
    ):
        """Initialize the bridge.

        Args:
            config: Configuration with mappings and thresholds.
                Uses defaults if None.
            tile_graph: Optional TileGraph from knowledge_tiles.py.
                When provided, prerequisite validation is enabled.
            trail_engine: Optional trail encoder/compiler for
                bytecode-level processing.
        """
        self.config = config or TrailTileConfig()
        self.tile_graph = tile_graph
        self.trail_engine = trail_engine

        # Per-agent tile progress tracking: {agent_name: {tile_id: float}}
        self._agent_progress: Dict[str, Dict[str, float]] = {}

        # Evidence log: {tile_id: [trail_evidence_dict, ...]}
        self._tile_evidence: Dict[str, List[dict]] = {}

        # Processing history: list of all TrailTileResult objects
        self._history: List[TrailTileResult] = []

    # ── Mapping Operations ───────────────────────────────────

    def map_opcode_to_tile(self, opcode: str) -> Optional[str]:
        """Look up which tile an opcode maps to.

        Args:
            opcode: The trail opcode name (e.g., "FILE_READ").

        Returns:
            The tile ID string if a mapping exists, else None.
        """
        return self.config.opcode_tile_mapping.get(opcode)

    def register_mapping(self, opcode: str, tile_id: str) -> None:
        """Add a custom opcode-to-tile mapping.

        Args:
            opcode: The trail opcode name to register.
            tile_id: The knowledge tile ID to map it to.

        Raises:
            ValueError: If opcode or tile_id is empty/whitespace.
        """
        if not opcode or not opcode.strip():
            raise ValueError("Opcode must be a non-empty string")
        if not tile_id or not tile_id.strip():
            raise ValueError("Tile ID must be a non-empty string")
        self.config.opcode_tile_mapping[opcode.strip()] = tile_id.strip()

    def unregister_mapping(self, opcode: str) -> bool:
        """Remove an opcode-to-tile mapping.

        Args:
            opcode: The trail opcode name to unregister.

        Returns:
            True if the mapping existed and was removed, False otherwise.
        """
        return self.config.opcode_tile_mapping.pop(opcode, None) is not None

    # ── Trail Processing ─────────────────────────────────────

    def process_trail(self, trail_data: dict) -> TrailTileResult:
        """Process a compiled trail and determine which tiles it completes.

        The trail_data dict should contain:
            - "agent": agent name (str)
            - "opcodes": list of opcode name strings
            - "score": optional trail quality score (float, default 1.0)
            - "trail_hash": optional pre-computed hash (str)

        Processing logic:
            1. Extract opcodes from trail data
            2. Map each opcode to its tile ID
            3. Compute per-tile progress based on opcode frequency
            4. Auto-complete tiles that exceed the threshold
            5. Respect max_tiles_per_trail limit
            6. Update per-agent progress and evidence logs

        Args:
            trail_data: Dict with trail information.

        Returns:
            TrailTileResult with completed tiles, progress, and confidence.
        """
        agent = trail_data.get("agent", "unknown")
        opcodes = trail_data.get("opcodes", [])
        raw_score = trail_data.get("score", 1.0)
        score = float(raw_score) if raw_score is not None else 1.0

        # Compute trail hash
        raw_hash = trail_data.get("trail_hash", "")
        if not raw_hash:
            hash_input = f"{agent}:{','.join(sorted(opcodes))}:{score}:{time.time()}"
            trail_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        else:
            trail_hash = str(raw_hash)

        # Map opcodes to tiles and count frequencies
        tile_hits: Dict[str, int] = {}
        unmapped_count = 0
        total_action_ops = 0

        for opcode in opcodes:
            # Skip meta opcodes for confidence calculation
            if opcode in ("TRAIL_BEGIN", "TRAIL_END", "NOP", "COMMENT", "LABEL"):
                # But still map them if a mapping exists
                tile_id = self.map_opcode_to_tile(opcode)
                if tile_id:
                    tile_hits[tile_id] = tile_hits.get(tile_id, 0) + 1
                continue

            total_action_ops += 1
            tile_id = self.map_opcode_to_tile(opcode)
            if tile_id:
                tile_hits[tile_id] = tile_hits.get(tile_id, 0) + 1
            else:
                unmapped_count += 1

        # Compute confidence: ratio of mapped action opcodes
        if total_action_ops > 0:
            confidence = (total_action_ops - unmapped_count) / total_action_ops
        elif len(opcodes) > 0:
            confidence = 0.3  # Only meta opcodes, low confidence
        else:
            confidence = 0.0

        # Compute per-tile progress scores
        # Progress = (hits for this tile / total action opcodes) * trail score
        # This means a trail with many relevant opcodes and high score = high progress
        max_hits = max(tile_hits.values()) if tile_hits else 1
        tiles_progressed: Dict[str, float] = {}

        for tile_id, hits in tile_hits.items():
            # Progress based on relative frequency and trail score
            raw_progress = (hits / max(max_hits, 1)) * score
            progress = min(1.0, raw_progress)

            # Also factor in existing agent progress (cumulative)
            agent_prog = self._agent_progress.get(agent, {})
            existing = agent_prog.get(tile_id, 0.0)
            cumulative = min(1.0, existing + progress * 0.5)  # Diminishing returns
            tiles_progressed[tile_id] = round(cumulative, 4)

            # Update agent progress
            if agent not in self._agent_progress:
                self._agent_progress[agent] = {}
            self._agent_progress[agent][tile_id] = cumulative

        # Determine which tiles to auto-complete
        threshold = self.config.auto_complete_threshold
        max_tiles = self.config.max_tiles_per_trail

        # Sort candidate tiles by progress descending
        candidates = sorted(
            tiles_progressed.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        tiles_completed: List[str] = []
        for tile_id, prog in candidates:
            if len(tiles_completed) >= max_tiles:
                break
            if prog >= threshold:
                # Prerequisite check if tile_graph is available
                if self.tile_graph and tile_id in self.tile_graph.tiles:
                    tile_obj = self.tile_graph.tiles[tile_id]
                    agent_acquired = self._get_agent_acquired(agent)
                    missing = tile_obj.missing_prerequisites(agent_acquired)
                    if missing:
                        continue  # Can't complete, prerequisites not met
                tiles_completed.append(tile_id)

        # Record evidence
        evidence_entry = {
            "trail_hash": trail_hash,
            "agent": agent,
            "opcodes": list(opcodes),
            "score": score,
            "tiles_completed": list(tiles_completed),
            "tiles_progressed": dict(tiles_progressed),
            "timestamp": time.time(),
        }

        for tile_id in tiles_progressed:
            if tile_id not in self._tile_evidence:
                self._tile_evidence[tile_id] = []
            self._tile_evidence[tile_id].append(evidence_entry)

        # Build result
        result = TrailTileResult(
            trail_hash=trail_hash,
            tiles_completed=tiles_completed,
            tiles_progressed=tiles_progressed,
            confidence=round(confidence, 4),
        )
        self._history.append(result)
        return result

    # ── Agent Progress ───────────────────────────────────────

    def get_agent_tile_progress(self, agent_name: str) -> Dict[str, float]:
        """Get how far an agent is toward each tile via trail evidence.

        Args:
            agent_name: The agent to query.

        Returns:
            Dict mapping tile IDs to progress scores (0.0-1.0).
        """
        return dict(self._agent_progress.get(agent_name, {}))

    def _get_agent_acquired(self, agent_name: str) -> set:
        """Get set of tile IDs the agent has completed (progress >= threshold)."""
        threshold = self.config.auto_complete_threshold
        agent_prog = self._agent_progress.get(agent_name, {})
        return {tid for tid, prog in agent_prog.items() if prog >= threshold}

    # ── Tile Evidence ────────────────────────────────────────

    def get_tile_trail_evidence(self, tile_id: str) -> List[dict]:
        """Get which trails contributed evidence for a tile.

        Args:
            tile_id: The knowledge tile to query.

        Returns:
            List of evidence dicts, each containing trail_hash, agent,
            opcodes, score, and timestamp.
        """
        return list(self._tile_evidence.get(tile_id, []))

    # ── Batch Processing ─────────────────────────────────────

    def batch_process_trails(self, trails: List[dict]) -> List[TrailTileResult]:
        """Process multiple trails in sequence.

        Args:
            trails: List of trail_data dicts, each suitable for process_trail().

        Returns:
            List of TrailTileResult objects, one per trail.
        """
        return [self.process_trail(td) for td in trails]

    # ── History & Statistics ─────────────────────────────────

    def get_history(self) -> List[TrailTileResult]:
        """Get the full processing history."""
        return list(self._history)

    def get_stats(self) -> dict:
        """Get bridge statistics.

        Returns:
            Dict with total trails processed, total tiles completed,
            total agents seen, mapping count, etc.
        """
        total_completed = sum(
            len(r.tiles_completed) for r in self._history
        )
        return {
            "total_trails_processed": len(self._history),
            "total_tiles_completed": total_completed,
            "total_agents_seen": len(self._agent_progress),
            "total_tiles_tracked": len(self._tile_evidence),
            "mapping_count": len(self.config.opcode_tile_mapping),
            "auto_complete_threshold": self.config.auto_complete_threshold,
            "max_tiles_per_trail": self.config.max_tiles_per_trail,
        }

    def reset(self) -> None:
        """Reset all progress, evidence, and history."""
        self._agent_progress.clear()
        self._tile_evidence.clear()
        self._history.clear()

    # ── Serialization ────────────────────────────────────────

    def to_dict(self) -> dict:
        """Serialize the bridge state to a dict.

        Returns:
            Dict with config, agent_progress, tile_evidence, and history.
        """
        return {
            "config": self.config.to_dict(),
            "agent_progress": {
                agent: dict(progress)
                for agent, progress in self._agent_progress.items()
            },
            "tile_evidence": {
                tile_id: list(evidence)
                for tile_id, evidence in self._tile_evidence.items()
            },
            "history": [r.to_dict() for r in self._history],
        }

    @classmethod
    def from_dict(cls, data: dict) -> TrailTileBridge:
        """Deserialize a bridge from a dict.

        Args:
            data: Dict previously produced by to_dict().

        Returns:
            A new TrailTileBridge instance with restored state.
        """
        config = TrailTileConfig.from_dict(data.get("config", {}))
        bridge = cls(config=config)

        # Restore agent progress
        for agent, progress in data.get("agent_progress", {}).items():
            bridge._agent_progress[agent] = dict(progress)

        # Restore tile evidence
        for tile_id, evidence in data.get("tile_evidence", {}).items():
            bridge._tile_evidence[tile_id] = list(evidence)

        # Restore history
        for hist_entry in data.get("history", []):
            bridge._history.append(TrailTileResult.from_dict(hist_entry))

        return bridge
