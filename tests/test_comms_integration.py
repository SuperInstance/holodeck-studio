#!/usr/bin/env python3
"""
Tests for comms_system integration into server.py.

Tests: Mailbox send/receive, Library search, Equipment equip/unequip,
CommsRouter message routing, and each new command handler (cmd_mail,
cmd_inbox, cmd_library, cmd_equip).
"""

import asyncio
import os
import sys
import shutil
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Ensure project root is on sys.path
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import World, Room, Agent, CommandHandler
from comms_system import (
    Message, Mailbox, Library, Equipment, CommsRouter, seed_library,
)


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

class FakeWriter:
    """Minimal mock for asyncio StreamWriter that captures sent data."""

    def __init__(self):
        self.data = []
        self._closed = False

    def write(self, data):
        if not self._closed:
            self.data.append(data)

    async def drain(self):
        pass

    def is_closing(self):
        return self._closed

    def close(self):
        self._closed = True

    def get_text(self):
        return b"".join(self.data).decode(errors="replace")

    def clear(self):
        self.data.clear()


def make_agent(name="testbot", role="vessel", room="tavern", writer=None):
    if writer is None:
        writer = FakeWriter()
    return Agent(name=name, role=role, room_name=room, writer=writer)


@pytest_asyncio.fixture
async def world(tmp_path):
    """Create a fresh World backed by a tmp directory."""
    w = World(world_dir=str(tmp_path / "world"))
    return w


@pytest_asyncio.fixture
async def handler(world):
    """Create a CommandHandler bound to a fresh World."""
    return CommandHandler(world)


@pytest_asyncio.fixture
def agent():
    return make_agent("Alice", "vessel", "tavern")


@pytest_asyncio.fixture
def mail_dir(tmp_path):
    d = tmp_path / "mail_test"
    d.mkdir()
    return d


@pytest_asyncio.fixture
def lib_dir(tmp_path):
    d = tmp_path / "lib_test"
    d.mkdir()
    return d


@pytest_asyncio.fixture
def inv_dir(tmp_path):
    d = tmp_path / "inv_test"
    d.mkdir()
    return d


@pytest_asyncio.fixture
def router(tmp_path):
    d = tmp_path / "world_test"
    d.mkdir()
    r = CommsRouter(str(d))
    seed_library(r.library)
    return r


# ═══════════════════════════════════════════════════════════════════════════
# 1. Message Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMessage:

    def test_message_creation(self):
        msg = Message("alice", "say", "hello", room="tavern")
        assert msg.sender == "alice"
        assert msg.channel == "say"
        assert msg.content == "hello"
        assert msg.room == "tavern"
        assert msg.id  # auto-generated
        assert msg.timestamp  # auto-generated

    def test_message_to_dict_roundtrip(self):
        msg = Message("bob", "gossip", "fleet news", room="tavern")
        d = msg.to_dict()
        msg2 = Message.from_dict(d)
        assert msg2.sender == "bob"
        assert msg2.channel == "gossip"
        assert msg2.content == "fleet news"
        assert msg2.room == "tavern"
        assert msg2.id == msg.id

    def test_message_with_target(self):
        msg = Message("alice", "tell", "hello there", room="tavern", target="bob")
        assert msg.target == "bob"
        d = msg.to_dict()
        assert d["target"] == "bob"

    def test_message_all_channels(self):
        for ch in ("say", "tell", "yell", "gossip", "ooc", "mailbox", "note"):
            msg = Message("a", ch, "test")
            assert msg.channel == ch


# ═══════════════════════════════════════════════════════════════════════════
# 2. Mailbox Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMailbox:

    def test_send_and_check(self, mail_dir):
        mb = Mailbox(str(mail_dir))
        mail_id = mb.send("bob", "alice", "Hello!", "How are you?")
        assert mail_id  # non-empty string

        messages = mb.check("bob")
        assert len(messages) == 1
        assert messages[0]["from"] == "alice"
        assert messages[0]["subject"] == "Hello!"
        assert messages[0]["body"] == "How are you?"
        assert messages[0]["read"] is False

    def test_send_to_multiple_recipients(self, mail_dir):
        mb = Mailbox(str(mail_dir))
        mb.send("bob", "alice", "Sub1", "Body1")
        mb.send("carol", "alice", "Sub2", "Body2")
        mb.send("bob", "alice", "Sub3", "Body3")

        assert len(mb.check("bob")) == 2
        assert len(mb.check("carol")) == 1
        assert len(mb.check("dave")) == 0

    def test_read_marks_as_read(self, mail_dir):
        mb = Mailbox(str(mail_dir))
        mail_id = mb.send("bob", "alice", "Sub", "Body")
        msg = mb.read("bob", mail_id)
        assert msg is not None
        assert msg["read"] is True

        # Unread filter should skip it
        unread = mb.check("bob", unread_only=True)
        assert len(unread) == 0

    def test_delete(self, mail_dir):
        mb = Mailbox(str(mail_dir))
        mail_id = mb.send("bob", "alice", "Sub", "Body")
        assert len(mb.check("bob")) == 1
        result = mb.delete("bob", mail_id)
        assert result is True
        assert len(mb.check("bob")) == 0

    def test_delete_nonexistent(self, mail_dir):
        mb = Mailbox(str(mail_dir))
        result = mb.delete("bob", "nonexistent")
        assert result is False

    def test_priority_parameter(self, mail_dir):
        mb = Mailbox(str(mail_dir))
        mb.send("bob", "alice", "Urgent", " ASAP", priority="urgent")
        msg = mb.check("bob")[0]
        assert msg["priority"] == "urgent"

    def test_persistence_across_instances(self, mail_dir):
        mb1 = Mailbox(str(mail_dir))
        mb1.send("bob", "alice", "Sub", "Body")

        mb2 = Mailbox(str(mail_dir))
        msgs = mb2.check("bob")
        assert len(msgs) == 1
        assert msgs[0]["subject"] == "Sub"


# ═══════════════════════════════════════════════════════════════════════════
# 3. Library Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestLibrary:

    def test_add_and_browse(self, lib_dir):
        lib = Library(str(lib_dir))
        lib.add_book("Test Book", "author", "testing", "Content here")
        books = lib.browse()
        assert len(books) == 1
        assert books[0]["title"] == "Test Book"
        assert books[0]["category"] == "testing"

    def test_search(self, lib_dir):
        lib = Library(str(lib_dir))
        lib.add_book("Python Guide", "author", "tech", "All about Python")
        lib.add_book("Rust Guide", "author", "tech", "All about Rust")
        lib.add_book("Cooking 101", "chef", "food", "Recipes")

        results = lib.search("Python")
        assert len(results) == 1
        assert results[0]["title"] == "Python Guide"

        results = lib.search("Guide")
        assert len(results) == 2

        results = lib.search("Cooking")
        assert len(results) == 1

    def test_search_by_category(self, lib_dir):
        lib = Library(str(lib_dir))
        lib.add_book("Book A", "a", "cat1", "content a")
        lib.add_book("Book B", "b", "cat2", "content b")

        results = lib.search("content", category="cat1")
        assert len(results) == 1
        assert results[0]["title"] == "Book A"

    def test_browse_by_category(self, lib_dir):
        lib = Library(str(lib_dir))
        lib.add_book("Book A", "a", "tech", "c1")
        lib.add_book("Book B", "b", "food", "c2")
        lib.add_book("Book C", "c", "tech", "c3")

        tech = lib.browse("tech")
        assert len(tech) == 2
        food = lib.browse("food")
        assert len(food) == 1

    def test_categories(self, lib_dir):
        lib = Library(str(lib_dir))
        lib.add_book("B1", "a", "alpha", "c")
        lib.add_book("B2", "b", "beta", "c")
        lib.add_book("B3", "c", "alpha", "c")
        cats = lib.categories()
        assert "alpha" in cats
        assert "beta" in cats
        assert cats == ["alpha", "beta"]  # sorted

    def test_checkout_increments_counter(self, lib_dir):
        lib = Library(str(lib_dir))
        book_id = lib.add_book("Book", "a", "cat", "content")
        book = lib.checkout(book_id)
        assert book["checkouts"] == 1
        book = lib.checkout(book_id)
        assert book["checkouts"] == 2

    def test_checkout_nonexistent(self, lib_dir):
        lib = Library(str(lib_dir))
        assert lib.checkout("nonexistent") is None

    def test_seed_library(self, lib_dir):
        lib = Library(str(lib_dir))
        seed_library(lib)
        assert len(lib.catalog) == 8  # 8 seed books
        assert lib.categories()  # non-empty

    def test_persistence(self, lib_dir):
        lib1 = Library(str(lib_dir))
        lib1.add_book("Persistent Book", "author", "test", "content")
        lib2 = Library(str(lib_dir))
        books = lib2.browse()
        assert len(books) == 1
        assert books[0]["title"] == "Persistent Book"


# ═══════════════════════════════════════════════════════════════════════════
# 4. Equipment Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestEquipment:

    def test_grant_and_inventory(self, inv_dir):
        eq = Equipment(str(inv_dir))
        result = eq.grant("alice", "scroll_of_charter")
        assert result is True
        items = eq.inventory("alice")
        assert len(items) == 1
        assert items[0]["name"] == "📜 Scroll of Charter"

    def test_grant_unknown_item(self, inv_dir):
        eq = Equipment(str(inv_dir))
        result = eq.grant("alice", "nonexistent_item")
        assert result is False

    def test_has_ability(self, inv_dir):
        eq = Equipment(str(inv_dir))
        eq.grant("alice", "lens_of_bugs")
        assert eq.has("alice", "code_review") is True
        assert eq.has("alice", "bug_hunting") is True
        assert eq.has("alice", "charter_reading") is False

    def test_grant_level(self, inv_dir):
        eq = Equipment(str(inv_dir))
        eq.grant_level("alice", 1)
        # Level 1 items: scroll_of_charter, bootcamp_manual
        assert eq.has("alice", "charter_reading") is True
        assert eq.has("alice", "bootcamp_awareness") is True

        eq.grant_level("alice", 2)
        # Level 2 adds: quill_of_logging, lens_of_bugs
        assert eq.has("alice", "captains_log") is True
        assert eq.has("alice", "code_review") is True

    def test_empty_inventory(self, inv_dir):
        eq = Equipment(str(inv_dir))
        items = eq.inventory("nobody")
        assert items == []

    def test_all_equipment_defs_have_required_fields(self):
        for item_id, eq in Equipment.EQUIPMENT_DEFS.items():
            assert "name" in eq
            assert "desc" in eq
            assert "grants" in eq
            assert "level" in eq
            assert isinstance(eq["grants"], list)
            assert len(eq["grants"]) > 0

    def test_persistence(self, inv_dir):
        eq1 = Equipment(str(inv_dir))
        eq1.grant("alice", "sword_of_shipping")
        eq2 = Equipment(str(inv_dir))
        assert eq2.has("alice", "code_write") is True
        assert eq2.has("alice", "pr_create") is True


# ═══════════════════════════════════════════════════════════════════════════
# 5. CommsRouter Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCommsRouter:

    def test_route_say(self, router):
        result = router.route("alice", "say", "hello", room="tavern")
        assert result["channel"] == "say"
        assert result["scope"] == "room"

    def test_route_tell(self, router):
        result = router.route("alice", "tell", "hello", room="tavern", target="bob")
        assert result["channel"] == "tell"
        assert result["scope"] == "direct"
        assert result["async"] is True
        # Check it was delivered to bob's mailbox
        msgs = router.mailbox.check("bob")
        assert len(msgs) >= 1
        assert msgs[-1]["from"] == "alice"

    def test_route_yell(self, router):
        result = router.route("alice", "yell", "FIRE!", room="tavern")
        assert result["scope"] == "local_area"

    def test_route_gossip(self, router):
        result = router.route("alice", "gossip", "fleet news", room="tavern")
        assert result["scope"] == "fleet"
        # Check gossip log was written
        gossip = router.get_gossip()
        assert len(gossip) >= 1
        assert gossip[-1]["content"] == "fleet news"

    def test_route_ooc(self, router):
        result = router.route("alice", "ooc", "ground truth", room="tavern")
        assert result["scope"] == "system"
        ooc = router.get_ooc()
        assert len(ooc) >= 1
        assert ooc[-1]["content"] == "ground truth"

    def test_route_note(self, router):
        result = router.route("alice", "note", "Look behind you", room="tavern")
        assert result["scope"] == "room_persistent"
        notes = router.get_room_notes("tavern")
        assert len(notes) == 1
        assert notes[0]["author"] == "alice"
        assert notes[0]["content"] == "Look behind you"

    def test_message_log(self, router):
        router.route("alice", "say", "msg1", room="tavern")
        router.route("bob", "gossip", "msg2", room="tavern")
        assert len(router.message_log) == 2

    def test_get_gossip_limit(self, router):
        for i in range(25):
            router.route("alice", "gossip", f"msg{i}", room="tavern")
        gossip = router.get_gossip(limit=10)
        assert len(gossip) == 10

    def test_get_ooc_empty(self, router):
        assert router.get_ooc() == []


# ═══════════════════════════════════════════════════════════════════════════
# 6. World Integration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWorldCommsIntegration:

    def test_world_init_comms(self, world):
        assert world.comms_router is not None
        assert world.library is not None
        assert world.mailboxes == {}

    def test_world_ensure_comms(self, world):
        router = world.ensure_comms()
        assert router is not None
        assert router is world.comms_router

    def test_world_get_mailbox(self, world):
        mb = world.get_mailbox()
        assert mb is not None
        assert isinstance(mb, Mailbox)

    def test_world_comms_attributes(self, world):
        assert hasattr(world, "comms_router")
        assert hasattr(world, "mailboxes")
        assert hasattr(world, "library")
        assert hasattr(world, "ensure_comms")
        assert hasattr(world, "get_mailbox")


# ═══════════════════════════════════════════════════════════════════════════
# 7. Command Handler Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCmdMail:

    @pytest.mark.asyncio
    async def test_mail_send(self, handler, agent):
        await handler.cmd_mail(agent, "Bob Hello -body Test body")
        text = agent.writer.get_text()
        assert "Mail sent to Bob" in text
        assert "Hello" in text

    @pytest.mark.asyncio
    async def test_mail_missing_args(self, handler, agent):
        await handler.cmd_mail(agent, "")
        assert "Usage:" in agent.writer.get_text()

    @pytest.mark.asyncio
    async def test_mail_missing_target(self, handler, agent):
        await handler.cmd_mail(agent, "")
        assert "Usage:" in agent.writer.get_text()

    @pytest.mark.asyncio
    async def test_mail_id_returned(self, handler, agent):
        await handler.cmd_mail(agent, "Bob Test Subject")
        text = agent.writer.get_text()
        assert "(id:" in text  # mail ID shown


class TestCmdInbox:

    @pytest.mark.asyncio
    async def test_inbox_empty(self, handler, agent):
        await handler.cmd_inbox(agent, "")
        text = agent.writer.get_text()
        assert "empty" in text.lower()

    @pytest.mark.asyncio
    async def test_inbox_with_mail(self, handler, agent):
        # Send mail first
        mb = handler.world.get_mailbox()
        mb.send("Alice", "Bob", "Test Subject", "Test Body")
        agent.writer.clear()
        await handler.cmd_inbox(agent, "")
        text = agent.writer.get_text()
        assert "Inbox" in text
        assert "Test Subject" in text
        assert "Bob" in text

    @pytest.mark.asyncio
    async def test_inbox_unread_filter(self, handler, agent):
        mb = handler.world.get_mailbox()
        mb.send("Alice", "Bob", "Sub1", "Body1")
        mb.send("Alice", "Bob", "Sub2", "Body2")
        # Read one
        msgs = mb.check("Alice")
        mb.read("Alice", msgs[0]["id"])
        agent.writer.clear()
        await handler.cmd_inbox(agent, "unread")
        text = agent.writer.get_text()
        assert "1 messages" in text


class TestCmdLibrary:

    @pytest.mark.asyncio
    async def test_library_browse(self, handler, agent):
        await handler.cmd_library(agent, "")
        text = agent.writer.get_text()
        assert "Fleet Library" in text
        # Should have seed books
        assert "📚" in text

    @pytest.mark.asyncio
    async def test_library_search(self, handler, agent):
        await handler.cmd_library(agent, "search fleet")
        text = agent.writer.get_text()
        assert "Library Search" in text

    @pytest.mark.asyncio
    async def test_library_search_no_results(self, handler, agent):
        await handler.cmd_library(agent, "search xyzzynonexistent")
        text = agent.writer.get_text()
        assert "No books found" in text

    @pytest.mark.asyncio
    async def test_library_browse_category(self, handler, agent):
        await handler.cmd_library(agent, "browse governance")
        text = agent.writer.get_text()
        # Should show governance category
        assert "governance" in text.lower()

    @pytest.mark.asyncio
    async def test_library_read_by_id(self, handler, agent):
        # Find a book id from the library
        books = handler.world.library.browse()
        if books:
            book_id = books[0]["id"]
            await handler.cmd_library(agent, f"read {book_id}")
            text = agent.writer.get_text()
            assert books[0]["title"] in text


class TestCmdEquip:

    @pytest.mark.asyncio
    async def test_equip_empty_inventory(self, handler, agent):
        await handler.cmd_equip(agent, "")
        text = agent.writer.get_text()
        assert "Equipment" in text
        assert "no equipment" in text.lower() or "Available items" in text

    @pytest.mark.asyncio
    async def test_equip_grant(self, handler, agent):
        await handler.cmd_equip(agent, "grant scroll_of_charter")
        text = agent.writer.get_text()
        assert "Equipped" in text
        assert "Scroll of Charter" in text

    @pytest.mark.asyncio
    async def test_equip_grant_unknown(self, handler, agent):
        await handler.cmd_equip(agent, "grant nonexistent_item_xyz")
        assert "Unknown item" in agent.writer.get_text()

    @pytest.mark.asyncio
    async def test_equip_list(self, handler, agent):
        await handler.cmd_equip(agent, "list")
        text = agent.writer.get_text()
        assert "Available Equipment" in text

    @pytest.mark.asyncio
    async def test_equip_check_ability(self, handler, agent):
        await handler.cmd_equip(agent, "grant lens_of_bugs")
        agent.writer.clear()
        await handler.cmd_equip(agent, "check code_review")
        text = agent.writer.get_text()
        assert "Yes" in text

    @pytest.mark.asyncio
    async def test_equip_check_ability_missing(self, handler, agent):
        await handler.cmd_equip(agent, "check nonexistent_ability")
        text = agent.writer.get_text()
        assert "No" in text


# ═══════════════════════════════════════════════════════════════════════════
# 8. CommsRouter Enhancement Tests (existing commands route through router)
# ═══════════════════════════════════════════════════════════════════════════

class TestCommsRouterEnhancement:

    @pytest.mark.asyncio
    async def test_say_routes_through_router(self, handler, agent):
        msg_count_before = len(handler.world.comms_router.message_log)
        await handler.cmd_say(agent, "test routing")
        assert len(handler.world.comms_router.message_log) == msg_count_before + 1
        assert handler.world.comms_router.message_log[-1].channel == "say"

    @pytest.mark.asyncio
    async def test_gossip_routes_through_router(self, handler, agent):
        await handler.cmd_gossip(agent, "test gossip routing")
        # Check gossip was logged to file
        gossip = handler.world.comms_router.get_gossip()
        assert any("test gossip routing" in g["content"] for g in gossip)

    @pytest.mark.asyncio
    async def test_ooc_routes_through_router(self, handler, agent):
        await handler.cmd_ooc(agent, "test ooc routing")
        ooc = handler.world.comms_router.get_ooc()
        assert any("test ooc routing" in o["content"] for o in ooc)

    @pytest.mark.asyncio
    async def test_tell_routes_through_router(self, handler, agent):
        msg_count_before = len(handler.world.comms_router.message_log)
        await handler.cmd_tell(agent, "Nobody test message")
        assert len(handler.world.comms_router.message_log) == msg_count_before + 1


# ═══════════════════════════════════════════════════════════════════════════
# 9. Command Registration Tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCommandRegistration:

    @pytest.mark.asyncio
    async def test_mail_command_registered(self, handler, agent):
        handler.world.agents["Alice"] = agent
        await handler.handle(agent, "mail Bob Test")
        # Should not say "Unknown command"
        assert "Unknown command" not in agent.writer.get_text()

    @pytest.mark.asyncio
    async def test_inbox_command_registered(self, handler, agent):
        handler.world.agents["Alice"] = agent
        await handler.handle(agent, "inbox")
        assert "Unknown command" not in agent.writer.get_text()

    @pytest.mark.asyncio
    async def test_library_command_registered(self, handler, agent):
        handler.world.agents["Alice"] = agent
        await handler.handle(agent, "library")
        assert "Unknown command" not in agent.writer.get_text()

    @pytest.mark.asyncio
    async def test_equip_command_registered(self, handler, agent):
        handler.world.agents["Alice"] = agent
        await handler.handle(agent, "equip")
        assert "Unknown command" not in agent.writer.get_text()
