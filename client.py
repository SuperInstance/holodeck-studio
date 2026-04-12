#!/usr/bin/env python3
"""
Cocapn MUD Client — Programmatic interface for agents.

Usage:
    python3 client.py --name oracle1 --role lighthouse
    
Or as a library:
    async with MUDClient("oracle1") as mud:
        await mud.say("Anyone want to hash out ISA v3?")
"""

import asyncio
import sys
import argparse


class MUDClient:
    """Async MUD client for programmatic agent access."""

    def __init__(self, name: str, role: str = "", host: str = "localhost", port: int = 7777):
        self.name = name
        self.role = role
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self._buffer = []

    async def __aenter__(self):
        self.reader, self.writer = await asyncio.open_connection(self.host, self.port)
        # Read welcome prompt
        await self.reader.readline()  # "Welcome..."
        await self.reader.readline()  # "What is your name?"
        # Send name
        self.writer.write(f"{self.name}\n".encode())
        await self.writer.drain()
        # Read role prompt
        await self.reader.readline()  # "Role?"
        self.writer.write(f"{self.role}\n".encode())
        await self.writer.drain()
        return self

    async def __aexit__(self, *args):
        if self.writer:
            self.writer.write(b"quit\n")
            await self.writer.drain()
            self.writer.close()

    async def _send(self, cmd: str) -> str:
        """Send a command and return the response."""
        self.writer.write(f"{cmd}\n".encode())
        await self.writer.drain()
        # Read response(s) until prompt or timeout
        lines = []
        try:
            while True:
                line = await asyncio.wait_for(self.reader.readline(), timeout=1.0)
                if not line:
                    break
                decoded = line.decode().strip()
                if decoded:
                    lines.append(decoded)
        except asyncio.TimeoutError:
            pass
        return "\n".join(lines)

    async def say(self, text: str) -> str:
        return await self._send(f'say {text}')

    async def tell(self, target: str, text: str) -> str:
        return await self._send(f'tell {target} {text}')

    async def gossip(self, text: str) -> str:
        return await self._send(f'gossip {text}')

    async def ooc(self, text: str) -> str:
        return await self._send(f'ooc {text}')

    async def emote(self, action: str) -> str:
        return await self._send(f'emote {action}')

    async def go(self, exit_name: str) -> str:
        return await self._send(f'go {exit_name}')

    async def look(self) -> str:
        return await self._send('look')

    async def build(self, name: str, desc: str) -> str:
        return await self._send(f'build "{name}" -desc "{desc}"')

    async def write_note(self, text: str) -> str:
        return await self._send(f'write {text}')

    async def read_notes(self) -> str:
        return await self._send('read')

    async def mask(self, name: str, desc: str = "") -> str:
        cmd = f'mask "{name}"'
        if desc:
            cmd += f' -desc "{desc}"'
        return await self._send(cmd)

    async def unmask(self) -> str:
        return await self._send('unmask')

    async def spawn_npc(self, name: str, role: str = "", topic: str = "") -> str:
        cmd = f'spawn "{name}"'
        if role:
            cmd += f' -role "{role}"'
        if topic:
            cmd += f' -topic "{topic}"'
        return await self._send(cmd)

    async def dismiss_npc(self, name: str) -> str:
        return await self._send(f'dismiss {name}')

    async def who(self) -> str:
        return await self._send('who')


async def interactive(name: str, role: str, host: str, port: int):
    """Run an interactive session (like telnet but with name auto-filled)."""
    async with MUDClient(name, role, host, port) as mud:
        print(f"Connected as {name}. Type 'help' for commands.")
        loop = asyncio.get_event_loop()
        
        async def read_input():
            while True:
                line = await loop.run_in_executor(None, input, "")
                if line.strip():
                    result = await mud._send(line.strip())
                    if result:
                        print(result)

        await read_input()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Cocapn MUD Client")
    parser.add_argument("--name", required=True)
    parser.add_argument("--role", default="")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=7777)
    args = parser.parse_args()
    asyncio.run(interactive(args.name, args.role, args.host, args.port))
