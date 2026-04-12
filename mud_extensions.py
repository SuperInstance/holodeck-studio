#!/usr/bin/env python3
"""
Cocapn MUD Server v3 — adds projections, describe, whisper, and fleet hooks.

Drop-in additions to server.py. Import and monkeypatch CommandHandler.

Usage in server.py:
    from mud_extensions import patch_handler
    patch_handler(handler)
"""

import asyncio
from datetime import datetime, timezone


def patch_handler(handler_class):
    """Add new commands to an existing CommandHandler class."""

    async def cmd_project(self, agent, args):
        """Project something in the room — show your work to everyone."""
        if not args:
            await self.send(agent, "Usage: project <title> - <content>")
            await self.send(agent, "Example: project ISA v3 draft - 2-byte opcodes with escape prefix 0xFF")
            return
        parts = args.split(" - ", 1)
        title = parts[0].strip()
        content = parts[1].strip() if len(parts) > 1 else "(no details)"
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        from server import Projection
        ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
        proj = Projection(agent.display_name, title, content, ts)
        room.projections.append(proj)
        self.world.save()
        await self.broadcast_room(agent.room_name,
            f"📊 {agent.display_name} projects: \"{title}\"\n   {content}",
            exclude=agent.name)
        await self.send(agent, f"You project: \"{title}\"")

    async def cmd_projections(self, agent, args):
        """See what's being projected in the room."""
        room = self.world.get_room(agent.room_name)
        if not room or not room.projections:
            await self.send(agent, "Nothing is being projected here.")
            return
        await self.send(agent, "═══ Projections ═══")
        for p in room.projections[-10:]:
            await self.send(agent, f"  📊 \"{p.title}\" by {p.agent_name} ({p.created})")
            await self.send(agent, f"     {p.content}")

    async def cmd_unproject(self, agent, args):
        """Remove your projection."""
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        before = len(room.projections)
        room.projections = [p for p in room.projections if p.agent_name != agent.display_name]
        removed = before - len(room.projections)
        if removed:
            self.world.save()
            await self.send(agent, f"Removed {removed} projection(s).")
        else:
            await self.send(agent, "You have no projections here.")

    async def cmd_describe(self, agent, args):
        """Change the room description (builders only)."""
        if agent.role not in ("lighthouse", "vessel", "captain", "scout"):
            await self.send(agent, "You don't have permission to describe rooms.")
            return
        if not args:
            await self.send(agent, "Usage: describe <new description text>")
            return
        room = self.world.get_room(agent.room_name)
        if room:
            room.description = args
            self.world.save()
            await self.broadcast_room(agent.room_name,
                f"The room shifts as {agent.display_name} reshapes it.")
            await self.send(agent, f"Room description updated.")

    async def cmd_whisper(self, agent, args):
        """Whisper to someone — only they hear, not the room."""
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: whisper <name> <message>")
            return
        target_name, msg = parts[0], parts[1]
        target = self.world.agents.get(target_name)
        if not target or target.room_name != agent.room_name:
            await self.send(agent, f"'{target_name}' isn't close enough to whisper to.")
            return
        await self.send(target, f"{agent.display_name} whispers: \"{msg}\"")
        await self.send(agent, f"You whisper to {target.display_name}: \"{msg}\"")

    async def cmd_rooms(self, agent, args):
        """List all rooms in the world."""
        lines = ["═══ World Map ═══"]
        for name, room in self.world.rooms.items():
            agents_count = len(self.world.agents_in_room(name))
            ghosts_count = len(self.world.ghosts_in_room(name))
            pop = ""
            if agents_count or ghosts_count:
                pop = f" ({agents_count}a, {ghosts_count}g)"
            lines.append(f"  {name}: {room.name}{pop}")
        lines.append(f"\n  Total: {len(self.world.rooms)} rooms")
        await self.send(agent, "\n".join(lines))

    async def cmd_shout(self, agent, args):
        """Shout to adjacent rooms (they hear it muffled)."""
        if not args:
            await self.send(agent, "Shout what?")
            return
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        # Send to current room
        await self.broadcast_room(agent.room_name,
            f"{agent.display_name} shouts: \"{args}\"", exclude=agent.name)
        await self.send(agent, f"You shout: \"{args}\"")
        # Send muffled to adjacent rooms
        for exit_name, target_room_name in room.exits.items():
            target_room = self.world.get_room(target_room_name)
            if target_room:
                await self.broadcast_room(target_room_name,
                    f"You hear a distant shout from {exit_name}: \"{args[:40]}...\"")

    # Register new commands
    handler_class.new_commands = {
        "project": cmd_project,
        "projections": cmd_projections,
        "unproject": cmd_unproject,
        "describe": cmd_describe,
        "whisper": cmd_whisper,
        "w": cmd_whisper,
        "rooms": cmd_rooms,
        "shout": cmd_shout,
    }
