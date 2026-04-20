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
    """Async MUD client for programmatic agent access.
    
    Provides a Python interface for connecting to a MUD server
    and executing commands programmatically, useful for bots,
    automated agents, and testing scripts.
    
    Example usage:
        async with MUDClient("oracle1") as mud:
            await mud.say("Anyone want to hash out ISA v3?")
    """

    def __init__(self, name: str, role: str = "", host: str = "localhost", port: int = 7777) -> None:
        """Initialize MUD client.
        
        Args:
            name: Agent name for login
            role: Agent role (optional)
            host: MUD server host (default: localhost)
            port: MUD server port (default: 7777)
        """
        self.name = name
        self.role = role
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self._buffer: List[str] = []

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
        """Send a command and return the response.
        
        Args:
            cmd: Command string to send to MUD
            
        Returns:
            str: The response from the server
            
        Raises:
            ConnectionError: If connection is lost
        """
        if not self.writer:
            raise ConnectionError("Not connected to MUD server")
            
        self.writer.write(f"{cmd}\n".encode())
        await self.writer.drain()
        
        # Read response(s) until prompt or timeout
        lines: List[str] = []
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
        except ConnectionResetError:
            raise ConnectionError("Connection reset by server")
            
        return "\n".join(lines)

    async def say(self, text: str) -> str:
        """Send a say command (room-wide message)."""
        return await self._send(f'say {text}')

    async def tell(self, target: str, text: str) -> str:
        """Send a tell command (private message to an agent)."""
        return await self._send(f'tell {target} {text}')

    async def gossip(self, text: str) -> str:
        """Send a gossip command (ship-wide broadcast)."""
        return await self._send(f'gossip {text}')

    async def ooc(self, text: str) -> str:
        """Send an OOC command (out-of-character message)."""
        return await self._send(f'ooc {text}')

    async def emote(self, action: str) -> str:
        """Send an emote command (roleplay action)."""
        return await self._send(f'emote {action}')

    async def go(self, exit_name: str) -> str:
        """Move to an adjacent room via an exit."""
        return await self._send(f'go {exit_name}')

    async def look(self) -> str:
        """Look around the current room."""
        return await self._send('look')

    async def build(self, name: str, desc: str) -> str:
        """Create a new room."""
        return await self._send(f'build "{name}" -desc "{desc}"')

    async def write_note(self, text: str) -> str:
        """Write a note on the room's wall."""
        return await self._send(f'write {text}')

    async def read_notes(self) -> str:
        """Read notes from the room's wall."""
        return await self._send('read')

    async def mask(self, name: str, desc: str = "") -> str:
        """Put on a character mask."""
        cmd = f'mask "{name}"'
        if desc:
            cmd += f' -desc "{desc}"'
        return await self._send(cmd)

    async def unmask(self) -> str:
        """Remove your character mask."""
        return await self._send('unmask')

    async def spawn_npc(self, name: str, role: str = "", topic: str = "") -> str:
        """Spawn a constructed NPC."""
        cmd = f'spawn "{name}"'
        if role:
            cmd += f' -role "{role}"'
        if topic:
            cmd += f' -topic "{topic}"'
        return await self._send(cmd)

    async def dismiss_npc(self, name: str) -> str:
        """Dismiss a constructed NPC."""
        return await self._send(f'dismiss {name}')

    async def who(self) -> str:
        """List all connected agents."""
        return await self._send('who')


async def interactive(name: str, role: str, host: str, port: int) -> None:
    """Run an interactive session (like telnet but with name auto-filled).
    
    Args:
        name: Agent name to use
        role: Agent role
        host: MUD server host
        port: MUD server port
    """
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
