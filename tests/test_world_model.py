"""Tests for the World model — rooms, agents, ghosts, serialization."""
import pytest
import json
from datetime import datetime, timezone


class TestProjection:
    def test_creation(self):
        from server import Projection
        p = Projection("oracle1", "ISA v3", "2-byte opcodes", "10:00 UTC")
        assert p.agent_name == "oracle1"
        assert p.title == "ISA v3"
        assert p.content == "2-byte opcodes"
        assert p.created == "10:00 UTC"

    def test_to_dict(self):
        from server import Projection
        p = Projection("agent", "Title", "Content", "00:00")
        d = p.to_dict()
        assert d == {"agent": "agent", "title": "Title", "content": "Content", "created": "00:00"}

    def test_from_dict(self):
        from server import Projection
        d = {"agent": "bot", "title": "T", "content": "C", "created": "now"}
        p = Projection.from_dict(d)
        assert p.agent_name == "bot"
        assert p.title == "T"

    def test_from_dict_missing_created(self):
        from server import Projection
        p = Projection.from_dict({"agent": "b", "title": "t", "content": "c"})
        assert p.created == ""

    def test_roundtrip(self):
        from server import Projection
        original = Projection("a", "t", "c", "01:00")
        restored = Projection.from_dict(original.to_dict())
        assert restored.agent_name == original.agent_name
        assert restored.title == original.title
        assert restored.content == original.content
        assert restored.created == original.created


class TestRoom:
    def test_creation_defaults(self):
        from server import Room
        r = Room("Test Room", "A test room")
        assert r.name == "Test Room"
        assert r.description == "A test room"
        assert r.exits == {}
        assert r.notes == []
        assert r.items == []
        assert r.projections == []

    def test_creation_with_exits(self):
        from server import Room
        r = Room("A", "desc", {"north": "room_b", "south": "room_c"})
        assert r.exits["north"] == "room_b"
        assert r.exits["south"] == "room_c"

    def test_to_dict(self):
        from server import Room
        r = Room("Test", "desc", {"e": "room_e"}, ["note1"], ["item1"])
        d = r.to_dict()
        assert d["name"] == "Test"
        assert d["exits"] == {"e": "room_e"}
        assert d["notes"] == ["note1"]
        assert d["items"] == ["item1"]
        assert d["projections"] == []

    def test_to_dict_truncates_notes(self):
        from server import Room
        # Notes are truncated to last 100
        notes = [f"note_{i}" for i in range(200)]
        r = Room("Test", "desc", notes=notes)
        d = r.to_dict()
        assert len(d["notes"]) == 100
        assert d["notes"][0] == "note_100"

    def test_from_dict(self):
        from server import Room
        d = {"name": "R", "description": "D", "exits": {"x": "y"},
             "notes": ["n1"], "items": ["i1"], "projections": []}
        r = Room.from_dict(d)
        assert r.name == "R"
        assert r.description == "D"
        assert r.exits == {"x": "y"}

    def test_from_dict_with_projections(self):
        from server import Room
        d = {"name": "R", "description": "D", "exits": {},
             "notes": [], "items": [],
             "projections": [{"agent": "a", "title": "t", "content": "c", "created": "now"}]}
        r = Room.from_dict(d)
        assert len(r.projections) == 1
        assert r.projections[0].agent_name == "a"

    def test_roundtrip(self):
        from server import Room
        original = Room("Room", "desc", {"exit": "target"}, ["n1"], ["i1"])
        restored = Room.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.exits == original.exits


class TestGhostAgent:
    def test_creation(self):
        from server import GhostAgent
        g = GhostAgent("ghost1", "vessel", "tavern", "2026-01-01T00:00:00+00:00", "desc")
        assert g.name == "ghost1"
        assert g.role == "vessel"
        assert g.status == "idle"

    def test_creation_with_status(self):
        from server import GhostAgent
        g = GhostAgent("g", "r", "room", "ts", "desc", status="working")
        assert g.status == "working"

    def test_to_dict(self):
        from server import GhostAgent
        g = GhostAgent("g", "r", "rm", "ts", "d", "idle")
        d = g.to_dict()
        assert d["name"] == "g"
        assert d["role"] == "r"
        assert d["room"] == "rm"
        assert d["last_seen"] == "ts"
        assert d["description"] == "d"
        assert d["status"] == "idle"

    def test_from_dict(self):
        from server import GhostAgent
        d = {"name": "g", "role": "r", "room": "rm",
             "last_seen": "ts", "description": "d", "status": "working"}
        g = GhostAgent.from_dict(d)
        assert g.status == "working"

    def test_from_dict_defaults(self):
        from server import GhostAgent
        g = GhostAgent.from_dict({"name": "g"})
        assert g.role == ""
        assert g.room_name == "tavern"
        assert g.last_seen == ""
        assert g.description == ""
        assert g.status == "idle"

    def test_roundtrip(self):
        from server import GhostAgent
        original = GhostAgent("ghost", "scout", "dojo", "ts", "desc", "thinking")
        restored = GhostAgent.from_dict(original.to_dict())
        assert restored.name == original.name
        assert restored.status == original.status


class TestAgent:
    def test_creation(self):
        from server import Agent
        a = Agent(name="bot", role="greenhorn")
        assert a.name == "bot"
        assert a.role == "greenhorn"
        assert a.room_name == "tavern"
        assert a.mask is None
        assert a.status == "active"
        assert a.writer is None

    def test_display_name_unmasked(self):
        from server import Agent
        a = Agent(name="oracle1", role="lighthouse")
        assert a.display_name == "oracle1"

    def test_display_name_masked(self):
        from server import Agent
        a = Agent(name="oracle1", role="lighthouse", mask="Shadow")
        assert a.display_name == "Shadow"

    def test_is_masked(self):
        from server import Agent
        a = Agent(name="a")
        assert not a.is_masked
        a.mask = "M"
        assert a.is_masked
        a.mask = None
        assert not a.is_masked

    def test_is_masked_empty_string(self):
        """Mask set to empty string is still considered masked."""
        from server import Agent
        a = Agent(name="a", mask="")
        # mask="" is truthy for is None check, so masked
        assert a.is_masked
