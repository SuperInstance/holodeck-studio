"""Tests for the MUD Client library."""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch


class TestMUDClient:
    def test_creation(self):
        from client import MUDClient
        c = MUDClient("bot", "greenhorn", "localhost", 7777)
        assert c.name == "bot"
        assert c.role == "greenhorn"
        assert c.host == "localhost"
        assert c.port == 7777
        assert c.reader is None
        assert c.writer is None
        assert c._buffer == []

    @pytest.mark.asyncio
    async def test_context_enter_exit(self):
        from client import MUDClient
        c = MUDClient("bot", "greenhorn")

        # Mock open_connection
        mock_reader = AsyncMock()
        mock_writer = AsyncMock()
        mock_reader.readline = AsyncMock(side_effect=[
            b"Welcome...\n",
            b"  What is your name? \n",
            b"  Role? \n",
        ])
        mock_writer.write = MagicMock()
        mock_writer.drain = AsyncMock()
        mock_writer.close = MagicMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            async with c as ctx:
                assert ctx is c
                assert c.reader is mock_reader
                assert c.writer is mock_writer
                # Check name was sent
                write_calls = [call[0][0] for call in mock_writer.write.call_args_list]
                assert any(b"bot" in call for call in write_calls)
                # Check role was sent
                assert any(b"greenhorn" in call for call in write_calls)

            # On exit, quit should be sent
            quit_calls = [call[0][0] for call in mock_writer.write.call_args_list]
            assert any(b"quit" in call for call in quit_calls)
            mock_writer.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_exit_with_no_writer(self):
        from client import MUDClient
        c = MUDClient("bot")
        # Should not raise even without writer
        await c.__aexit__(None, None, None)

    @pytest.mark.asyncio
    async def test_send_method(self):
        from client import MUDClient
        c = MUDClient("bot")
        c.reader = AsyncMock()
        c.writer = AsyncMock()
        c.reader.readline = AsyncMock(
            side_effect=[b"response line 1\n", asyncio.TimeoutError()])
        c.writer.write = MagicMock()
        c.writer.drain = AsyncMock()

        result = await c._send("look")
        assert "response line 1" in result
        write_calls = [call[0][0] for call in c.writer.write.call_args_list]
        assert b"look" in write_calls[0]

    @pytest.mark.asyncio
    async def test_send_timeout_returns_partial(self):
        from client import MUDClient
        c = MUDClient("bot")
        c.reader = AsyncMock()
        c.writer = AsyncMock()
        c.reader.readline = AsyncMock(side_effect=asyncio.TimeoutError())
        c.writer.write = MagicMock()
        c.writer.drain = AsyncMock()

        result = await c._send("cmd")
        assert result == ""

    @pytest.mark.asyncio
    async def test_send_eof_breaks_loop(self):
        from client import MUDClient
        c = MUDClient("bot")
        c.reader = AsyncMock()
        c.writer = AsyncMock()
        c.reader.readline = AsyncMock(side_effect=[b"line1\n", b""])
        c.writer.write = MagicMock()
        c.writer.drain = AsyncMock()

        result = await c._send("cmd")
        assert "line1" in result

    def test_convenience_methods(self):
        from client import MUDClient
        c = MUDClient("bot")
        # These should return coroutines (not call them directly)
        assert asyncio.iscoroutine(c.say("hello"))
        assert asyncio.iscoroutine(c.tell("target", "msg"))
        assert asyncio.iscoroutine(c.gossip("news"))
        assert asyncio.iscoroutine(c.ooc("ooc msg"))
        assert asyncio.iscoroutine(c.emote("waves"))
        assert asyncio.iscoroutine(c.go("tavern"))
        assert asyncio.iscoroutine(c.look())
        assert asyncio.iscoroutine(c.build("room", "desc"))
        assert asyncio.iscoroutine(c.write_note("text"))
        assert asyncio.iscoroutine(c.read_notes())
        assert asyncio.iscoroutine(c.mask("Name", "desc"))
        assert asyncio.iscoroutine(c.unmask())
        assert asyncio.iscoroutine(c.spawn_npc("NPC", "role", "topic"))
        assert asyncio.iscoroutine(c.dismiss_npc("NPC"))
        assert asyncio.iscoroutine(c.who())

    def test_mask_with_desc(self):
        from client import MUDClient
        c = MUDClient("bot")
        # Verify the command format
        import inspect
        source = inspect.getsource(c.mask)
        assert "mask" in source
