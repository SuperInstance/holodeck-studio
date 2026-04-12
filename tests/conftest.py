"""Shared fixtures for cocapn-mud tests."""
import sys
import os
import pytest
import tempfile
import shutil

# Ensure server.py is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def tmp_world_dir(tmp_path):
    """Provide a temporary directory for world data."""
    world_dir = tmp_path / "world"
    world_dir.mkdir(parents=True, exist_ok=True)
    return world_dir


@pytest.fixture
def tmp_log_dir(tmp_path):
    """Provide a temporary directory for logs."""
    log_dir = tmp_path / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture
def world(tmp_world_dir, tmp_log_dir):
    """Create a World instance backed by temp directories."""
    from server import World
    w = World(str(tmp_world_dir))
    w.log_dir = tmp_log_dir
    # Clear any loaded state for fresh tests
    w.rooms = dict(World.DEFAULT_ROOMS)
    w.agents = {}
    w.ghosts = {}
    w.npcs = {}
    return w


@pytest.fixture
def agent():
    """Create a basic test agent."""
    from server import Agent
    return Agent(name="testbot", role="greenhorn", room_name="tavern")


@pytest.fixture
def masked_agent():
    """Create a masked test agent."""
    from server import Agent
    return Agent(name="hidden_one", role="scout", room_name="tavern",
                 mask="Shadow Walker", mask_desc="A mysterious cloaked figure")


@pytest.fixture
def ghost_agent():
    """Create a ghost agent for testing."""
    from server import GhostAgent
    return GhostAgent(name="ghost_walker", role="vessel", room_name="lighthouse",
                      last_seen="2026-04-12T10:00:00+00:00",
                      description="A lingering presence", status="idle")


@pytest.fixture
def handler(world):
    """Create a CommandHandler with a fresh world."""
    from server import CommandHandler
    return CommandHandler(world)
