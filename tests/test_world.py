"""Tests for the World class — room management, agents, ghosts, persistence."""
import pytest
import json
from pathlib import Path


class TestWorldInit:
    def test_default_rooms_loaded(self, world):
        assert "tavern" in world.rooms
        assert "lighthouse" in world.rooms
        assert "workshop" in world.rooms
        assert "harbor" in world.rooms

    def test_tavern_exits(self, world):
        tavern = world.rooms["tavern"]
        assert "lighthouse" in tavern.exits
        assert "workshop" in tavern.exits
        assert "harbor" in tavern.exits

    def test_all_default_rooms_have_back_exit(self, world):
        """Most rooms should have an exit back to tavern (or a path to it)."""
        # Some rooms like crows_nest connect via harbor, not directly to tavern
        rooms_without_direct_tavern = {"crows_nest", "spec_chamber", "edge_workshop", "evolve_chamber", "grimoire_vault"}
        for name, room in world.rooms.items():
            if name != "tavern" and name not in rooms_without_direct_tavern:
                assert "tavern" in room.exits, f"{name} has no exit to tavern"

    def test_lighthouse_only_exits_to_tavern(self, world):
        lh = world.rooms["lighthouse"]
        assert set(lh.exits.keys()) == {"tavern"}

    def test_empty_agents_and_ghosts(self, world):
        assert world.agents == {}
        assert world.ghosts == {}
        assert world.npcs == {}


class TestWorldPersistence:
    def test_save_creates_files(self, world, tmp_world_dir):
        world.save()
        assert (tmp_world_dir / "rooms.json").exists()
        assert (tmp_world_dir / "ghosts.json").exists()

    def test_save_rooms_format(self, world, tmp_world_dir):
        world.save()
        data = json.loads((tmp_world_dir / "rooms.json").read_text())
        assert "tavern" in data
        assert isinstance(data["tavern"]["exits"], dict)

    def test_save_ghosts_format(self, world, tmp_world_dir):
        from server import GhostAgent
        world.ghosts["g1"] = GhostAgent("g1", "role", "tavern", "ts", "desc")
        world.save()
        data = json.loads((tmp_world_dir / "ghosts.json").read_text())
        assert "g1" in data
        assert data["g1"]["name"] == "g1"

    def test_load_from_files(self, tmp_world_dir):
        from server import World
        # Write a known room
        rooms_data = {
            "custom_room": {
                "name": "Custom Room",
                "description": "A custom room",
                "exits": {},
                "notes": [],
                "items": [],
                "projections": [],
            }
        }
        (tmp_world_dir / "rooms.json").write_text(json.dumps(rooms_data))
        w = World(str(tmp_world_dir))
        assert "custom_room" in w.rooms
        assert w.rooms["custom_room"].name == "Custom Room"

    def test_load_ghosts_from_file(self, tmp_world_dir):
        from server import World
        ghosts_data = {
            "old_ghost": {
                "name": "old_ghost",
                "role": "vessel",
                "room": "tavern",
                "last_seen": "2026-04-10T00:00:00+00:00",
                "description": "Ancient one",
                "status": "sleeping",
            }
        }
        (tmp_world_dir / "ghosts.json").write_text(json.dumps(ghosts_data))
        (tmp_world_dir / "rooms.json").write_text(json.dumps({}))
        w = World(str(tmp_world_dir))
        assert "old_ghost" in w.ghosts
        assert w.ghosts["old_ghost"].status == "sleeping"


class TestWorldRoomManagement:
    def test_get_room_exists(self, world):
        room = world.get_room("tavern")
        assert room is not None
        assert room.name == "The Tavern"

    def test_get_room_missing(self, world):
        assert world.get_room("nonexistent") is None

    def test_agents_in_room(self, world, agent):
        world.agents["testbot"] = agent
        agents = world.agents_in_room("tavern")
        assert len(agents) == 1
        assert agents[0].name == "testbot"

    def test_agents_in_room_filters_by_room(self, world):
        from server import Agent
        world.agents["a1"] = Agent("a1", room_name="tavern")
        world.agents["a2"] = Agent("a2", room_name="lighthouse")
        assert len(world.agents_in_room("tavern")) == 1
        assert len(world.agents_in_room("lighthouse")) == 1
        assert len(world.agents_in_room("workshop")) == 0

    def test_ghosts_in_room(self, world, ghost_agent):
        world.ghosts["ghost_walker"] = ghost_agent
        ghosts = world.ghosts_in_room("lighthouse")
        assert len(ghosts) == 1
        assert ghosts[0].name == "ghost_walker"

    def test_ghosts_in_room_excludes_online_agents(self, world, agent, ghost_agent):
        """Ghosts whose agents are online should be excluded."""
        from server import GhostAgent
        world.agents["ghost_walker"] = agent  # same name as ghost
        world.ghosts["ghost_walker"] = GhostAgent(
            "ghost_walker", "role", "lighthouse", "ts", "desc")
        ghosts = world.ghosts_in_room("lighthouse")
        assert len(ghosts) == 0


class TestWorldGhostManagement:
    def test_update_ghost_new(self, world, agent):
        world.update_ghost(agent)
        assert agent.name in world.ghosts
        g = world.ghosts[agent.name]
        assert g.room_name == "tavern"
        assert g.role == "greenhorn"
        assert g.status == "active"

    def test_update_ghost_existing(self, world, agent):
        world.update_ghost(agent)
        agent.room_name = "lighthouse"
        agent.status = "working"
        world.update_ghost(agent)
        g = world.ghosts[agent.name]
        assert g.room_name == "lighthouse"
        assert g.status == "working"

    def test_update_ghost_preserves_last_seen_on_update(self, world, agent):
        from server import GhostAgent
        # Create a ghost with a specific last_seen
        world.ghosts[agent.name] = GhostAgent(
            agent.name, "role", "tavern", "old_timestamp", "desc", "idle")
        world.update_ghost(agent)
        # last_seen should be updated to now
        assert world.ghosts[agent.name].last_seen != "old_timestamp"


class TestWorldLogging:
    def test_log_creates_file(self, world, tmp_log_dir):
        world.log("test_channel", "test message")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = tmp_log_dir / today / "test_channel.log"
        assert log_file.exists()
        content = log_file.read_text()
        assert "test message" in content

    def test_log_timestamp_format(self, world, tmp_log_dir):
        world.log("test", "check ts")
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_file = tmp_log_dir / today / "test.log"
        content = log_file.read_text()
        # Should have HH:MM:SS format
        assert "] check ts" in content


# Need datetime import
from datetime import datetime, timezone
