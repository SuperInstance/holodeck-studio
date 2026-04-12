#!/usr/bin/env python3
"""
Cocapn MUD Server — A persistent multiplayer world for the Cocapn fleet.

Usage: python3 server.py [--port 7777] [--world world/]

Agents connect via telnet or the programmatic client.
"""

import asyncio
import json
import os
import time
import argparse
from datetime import datetime, timezone
from pathlib import Path
from dataclasses import dataclass, field
from typing import Optional


# ═══════════════════════════════════════════════════════════════
# World Model
# ═══════════════════════════════════════════════════════════════

@dataclass
class Room:
    name: str
    description: str
    exits: dict = field(default_factory=dict)  # direction -> room_name
    notes: list = field(default_factory=list)
    items: list = field(default_factory=list)

    def to_dict(self):
        return {"name": self.name, "description": self.description,
                "exits": self.exits, "notes": self.notes, "items": self.items}

    @staticmethod
    def from_dict(d):
        return Room(d["name"], d.get("description", ""), d.get("exits", {}),
                     d.get("notes", []), d.get("items", []))


@dataclass
class Agent:
    name: str
    role: str = ""
    room_name: str = "tavern"
    mask: Optional[str] = None
    mask_desc: Optional[str] = None
    description: str = ""
    writer: object = None  # asyncio.StreamWriter

    @property
    def display_name(self):
        return self.mask if self.mask else self.name

    @property
    def is_masked(self):
        return self.mask is not None


class World:
    DEFAULT_ROOMS = {
        "tavern": Room("The Tavern",
            "The heart of the Cocapn fleet. The room smells of solder and sea salt.\n"
            "A large table dominates the center, covered in charts and commit logs.\n"
            "The fire crackles. The door to the harbor is always open.",
            {"lighthouse": "lighthouse", "workshop": "workshop", "library": "library",
             "warroom": "war_room", "dojo": "dojo", "lab": "flux_lab",
             "graveyard": "graveyard", "harbor": "harbor", "crowsnest": "crows_nest"}),
        "lighthouse": Room("The Lighthouse",
            "Oracle1's study. Charts cover every wall — fleet positions, ISA specs,\n"
            "conformance vectors. Bottles line the windowsill, some sealed, some open.\n"
            "A telescope points toward the edge.",
            {"tavern": "tavern"}),
        "workshop": Room("The Workshop",
            "JetsonClaw1's domain. The soldering iron is still warm. ARM64 boards\n"
            "line the shelves. A CUDA core hums on the bench, running telepathy-c.\n"
            "The smell of flux (the soldering kind) fills the air.",
            {"tavern": "tavern"}),
        "library": Room("The Library",
            "Babel's archive. Shelves stretch to the ceiling, holding texts in every\n"
            "language. A Rosetta Stone sits on a pedestal, translating FLUX opcodes\n"
            "between Python, C, Go, Rust, and Zig.",
            {"tavern": "tavern"}),
        "war_room": Room("The War Room",
            "Strategy central. A large table holds the fleet task board, org chart,\n"
            "and conformance test results. Red pins mark blockers. Green pins mark done.",
            {"tavern": "tavern"}),
        "dojo": Room("The Dojo",
            "The training hall. Mats line the floor. A rack holds practice weapons:\n"
            "devil's advocate masks, critic personas, user simulation rigs.\n"
            "NPC sparring logs line the walls — the knowledge of every past session.",
            {"tavern": "tavern"}),
        "flux_lab": Room("The FLUX Lab",
            "The bytecode chamber. Bytecode flows like water through transparent pipes.\n"
            "Five terminals display the same .fluxbc file running on Python, C, Go,\n"
            "Rust, and Zig — all producing identical output. A conformance chart glows green.",
            {"tavern": "tavern"}),
        "graveyard": Room("The Graveyard",
            "The memorial garden. Tombstones mark vessels that have passed — their\n"
            "knowledge preserved in stone. The necropolis keeper tends the grounds.\n"
            "Each marker tells a story: death cause, lessons learned, knowledge harvested.",
            {"tavern": "tavern"}),
        "harbor": Room("The Harbor",
            "The departure lounge and arrival dock. New agents materialize here.\n"
            "A capitaine terminal offers one-click Codespace deployment.\n"
            "Greenhorn onboarding manuals stack the shelves. The dockmaster watches all.",
            {"tavern": "tavern", "crowsnest": "crows_nest"}),
        "crows_nest": Room("The Crow's Nest",
            "Observation deck high above the fleet. You can see every lighthouse,\n"
            "every vessel, every shipping lane. The lighthouse keeper's instruments\n"
            "show fleet status, agent activity, and bottle traffic in real time.",
            {"harbor": "harbor"}),
    }

    def __init__(self, world_dir: str = "world"):
        self.world_dir = Path(world_dir)
        self.rooms: dict[str, Room] = {}
        self.agents: dict[str, Agent] = {}  # name -> Agent
        self.npcs: dict[str, dict] = {}  # npc_name -> {role, topic, creator, room}
        self.log_dir = Path("logs")
        self.world_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.load()

    def load(self):
        rooms_file = self.world_dir / "rooms.json"
        if rooms_file.exists():
            data = json.loads(rooms_file.read_text())
            for name, rdata in data.items():
                self.rooms[name] = Room.from_dict(rdata)
        else:
            self.rooms = {k: Room(v.name, v.description, dict(v.exits))
                         for k, v in self.DEFAULT_ROOMS.items()}
            self.save()

    def save(self):
        rooms_file = self.world_dir / "rooms.json"
        data = {name: room.to_dict() for name, room in self.rooms.items()}
        rooms_file.write_text(json.dumps(data, indent=2))

    def get_room(self, name: str) -> Optional[Room]:
        return self.rooms.get(name)

    def agents_in_room(self, room_name: str) -> list[Agent]:
        return [a for a in self.agents.values() if a.room_name == room_name]

    def log(self, channel: str, message: str):
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        log_dir = self.log_dir / today
        log_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%H:%M:%S")
        with open(log_dir / f"{channel}.log", "a") as f:
            f.write(f"[{ts}] {message}\n")


# ═══════════════════════════════════════════════════════════════
# Command Handler
# ═══════════════════════════════════════════════════════════════

class CommandHandler:
    def __init__(self, world: World):
        self.world = world

    async def handle(self, agent: Agent, line: str):
        line = line.strip()
        if not line:
            return

        parts = line.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        handlers = {
            "look": self.cmd_look, "l": self.cmd_look,
            "say": self.cmd_say, "'": self.cmd_say,
            "tell": self.cmd_tell, "t": self.cmd_tell,
            "gossip": self.cmd_gossip, "g": self.cmd_gossip,
            "ooc": self.cmd_ooc,
            "emote": self.cmd_emote, ":": self.cmd_emote,
            "go": self.cmd_go, "move": self.cmd_go,
            "build": self.cmd_build,
            "examine": self.cmd_examine, "x": self.cmd_examine,
            "write": self.cmd_write,
            "read": self.cmd_read,
            "log": self.cmd_log,
            "mask": self.cmd_mask,
            "unmask": self.cmd_unmask,
            "spawn": self.cmd_spawn,
            "dismiss": self.cmd_dismiss,
            "who": self.cmd_who,
            "help": self.cmd_help, "?": self.cmd_help,
            "quit": self.cmd_quit, "exit": self.cmd_quit,
        }

        handler = handlers.get(cmd)
        if handler:
            await handler(agent, args)
        else:
            await self.send(agent, f"Unknown command: {cmd}. Type 'help' for commands.")

    async def send(self, agent: Agent, text: str):
        if agent.writer and not agent.writer.is_closing():
            agent.writer.write((text + "\n").encode())
            await agent.writer.drain()

    async def broadcast_room(self, room_name: str, text: str, exclude: str = None):
        for a in self.world.agents_in_room(room_name):
            if a.name != exclude:
                await self.send(a, text)

    async def broadcast_all(self, text: str, exclude: str = None):
        for a in self.world.agents.values():
            if a.name != exclude:
                await self.send(a, text)

    async def cmd_look(self, agent: Agent, args: str):
        room = self.world.get_room(agent.room_name)
        if not room:
            return
        lines = [f"\n  ═══ {room.name} ═══", f"  {room.description}", ""]
        if room.exits:
            lines.append(f"  Exits: {', '.join(room.exits.keys())}")
        agents_here = [a for a in self.world.agents_in_room(agent.room_name) if a.name != agent.name]
        npcs_here = [n for n, d in self.world.npcs.items() if d.get("room") == agent.room_name]
        if agents_here:
            lines.append(f"  Present: {', '.join(a.display_name for a in agents_here)}")
        if npcs_here:
            lines.append(f"  NPCs: {', '.join(npcs_here)}")
        if room.notes:
            lines.append(f"  Notes on wall: {len(room.notes)} (type 'read notes')")
        lines.append("")
        await self.send(agent, "\n".join(lines))

    async def cmd_say(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Say what?")
            return
        name = agent.display_name
        self.world.log(agent.room_name, f"{name} says: {args}")
        await self.broadcast_room(agent.room_name, f'{name} says: "{args}"', exclude=agent.name)
        await self.send(agent, f'You say: "{args}"')

    async def cmd_tell(self, agent: Agent, args: str):
        parts = args.split(None, 1)
        if len(parts) < 2:
            await self.send(agent, "Usage: tell <agent> <message>")
            return
        target_name, msg = parts[0], parts[1]
        target = self.world.agents.get(target_name)
        if not target:
            await self.send(agent, f"No one named '{target_name}' is here.")
            return
        await self.send(target, f"{agent.display_name} tells you: \"{msg}\"")
        await self.send(agent, f"You tell {target.display_name}: \"{msg}\"")

    async def cmd_gossip(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Gossip what?")
            return
        name = agent.display_name
        self.world.log("gossip", f"[{name}@{agent.room_name}] {args}")
        await self.broadcast_all(f"[gossip] {name}: {args}", exclude=agent.name)
        await self.send(agent, f"You gossip: {args}")

    async def cmd_ooc(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "OOC what?")
            return
        real = agent.name
        mask_info = f" (wearing mask: {agent.mask})" if agent.is_masked else ""
        self.world.log("ooc", f"[{real}{mask_info}] {args}")
        await self.broadcast_all(f"[OOC] {real}{mask_info}: {args}", exclude=agent.name)
        await self.send(agent, f"[OOC] You: {args}")

    async def cmd_emote(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Emote what?")
            return
        name = agent.display_name
        self.world.log(agent.room_name, f"{name} {args}")
        await self.broadcast_room(agent.room_name, f"{name} {args}", exclude=agent.name)
        await self.send(agent, f"{name} {args}")

    async def cmd_go(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Go where? Exits: " + ", ".join(
                self.world.get_room(agent.room_name).exits.keys()))
            return
        room = self.world.get_room(agent.room_name)
        if not room or args not in room.exits:
            await self.send(agent, f"No exit '{args}' here.")
            return
        target_name = room.exits[args]
        old_room = agent.room_name
        agent.room_name = target_name
        await self.broadcast_room(old_room, f"{agent.display_name} leaves for {args}.")
        await self.send(agent, f"You go {args}.")
        await self.broadcast_room(target_name, f"{agent.display_name} arrives.", exclude=agent.name)
        await self.cmd_look(agent, "")

    async def cmd_build(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Usage: build <room_name> -desc <description>")
            return
        parts = args.split(" -desc ", 1)
        room_id = parts[0].strip().lower().replace(" ", "_")
        desc = parts[1].strip() if len(parts) > 1 else "A new room, freshly built."
        current_room = self.world.get_room(agent.room_name)
        new_room = Room(room_id.replace("_", " ").title(), desc, {"back": agent.room_name})
        self.world.rooms[room_id] = new_room
        if current_room:
            current_room.exits[room_id] = room_id
        self.world.save()
        self.world.log("build", f"{agent.display_name} built '{room_id}': {desc}")
        await self.broadcast_all(f"[build] {agent.display_name} constructed a new room: {room_id}")
        await self.send(agent, f"You built '{room_id}'. You can 'go {room_id}' from here.")

    async def cmd_examine(self, agent: Agent, args: str):
        if not args:
            await self.cmd_look(agent, "")
            return
        target = self.world.agents.get(args)
        if target and target.room_name == agent.room_name:
            lines = [f"  {target.display_name}", f"  Role: {target.role}"]
            if target.description:
                lines.append(f"  {target.description}")
            if target.is_masked:
                lines.append(f"  (masked — real identity hidden)")
            await self.send(agent, "\n".join(lines))
        elif args in self.world.npcs and self.world.npcs[args].get("room") == agent.room_name:
            npc = self.world.npcs[args]
            await self.send(agent, f"  {args}\n  Role: {npc.get('role','?')}\n  Topic: {npc.get('topic','general')}\n  Created by: {npc.get('creator','?')}")
        else:
            await self.send(agent, f"You don't see '{args}' here.")

    async def cmd_write(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Write what?")
            return
        room = self.world.get_room(agent.room_name)
        if room:
            ts = datetime.now(timezone.utc).strftime("%H:%M")
            room.notes.append(f"[{ts}] {agent.display_name}: {args}")
            self.world.save()
            await self.send(agent, "You write a note on the wall.")
            await self.broadcast_room(agent.room_name, f"{agent.display_name} writes something on the wall.", exclude=agent.name)

    async def cmd_read(self, agent: Agent, args: str):
        room = self.world.get_room(agent.room_name)
        if not room or not room.notes:
            await self.send(agent, "Nothing to read here.")
            return
        await self.send(agent, "═══ Notes on the wall ═══")
        for note in room.notes[-20:]:
            await self.send(agent, f"  {note}")

    async def cmd_log(self, agent: Agent, args: str):
        room = self.world.get_room(agent.room_name)
        await self.send(agent, f"Room: {room.name if room else '?'}")
        agents = self.world.agents_in_room(agent.room_name)
        await self.send(agent, f"Agents here: {', '.join(a.display_name for a in agents)}")
        await self.send(agent, f"Total connected: {len(self.world.agents)}")

    async def cmd_mask(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Usage: mask <\"Character Name\"> [-desc <description>]")
            return
        parts = args.split(" -desc ", 1)
        agent.mask = parts[0].strip().strip('"')
        agent.mask_desc = parts[1].strip() if len(parts) > 1 else f"A mysterious figure."
        await self.send(agent, f"You put on the mask: {agent.mask}")
        await self.broadcast_room(agent.room_name, f"{agent.mask} appears — {agent.mask_desc}", exclude=agent.name)
        self.world.log("mask", f"{agent.name} masked as {agent.mask}")

    async def cmd_unmask(self, agent: Agent, args: str):
        if not agent.is_masked:
            await self.send(agent, "You're not wearing a mask.")
            return
        mask = agent.mask
        agent.mask = None
        agent.mask_desc = None
        await self.send(agent, f"You remove the mask: {mask}")
        await self.broadcast_room(agent.room_name, f"{mask} removes their mask, revealing {agent.display_name}.", exclude=agent.name)

    async def cmd_spawn(self, agent: Agent, args: str):
        if not args:
            await self.send(agent, "Usage: spawn <\"NPC Name\"> -role <role> [-topic <topic>]")
            return
        name = args.split(" -")[0].strip().strip('"')
        role = ""
        topic = ""
        for part in args.split(" -")[1:]:
            if part.startswith("role "):
                role = part[5:].strip().strip('"')
            elif part.startswith("topic "):
                topic = part[6:].strip().strip('"')
        self.world.npcs[name] = {"role": role, "topic": topic, "creator": agent.name, "room": agent.room_name}
        await self.send(agent, f"You spawn {name} ({role}). They're ready for sparring.")
        await self.broadcast_room(agent.room_name, f"{name} materializes — a {role} NPC created by {agent.display_name}.", exclude=agent.name)
        self.world.log("npc", f"{agent.display_name} spawned {name} ({role}, topic: {topic})")

    async def cmd_dismiss(self, agent: Agent, args: str):
        if not args or args not in self.world.npcs:
            await self.send(agent, "Usage: dismiss <NPC Name>")
            return
        npc = self.world.npcs.pop(args)
        await self.send(agent, f"You dismiss {args}. Their knowledge is preserved in the Dojo log.")
        await self.broadcast_room(agent.room_name, f"{args} fades away, their lessons preserved.", exclude=agent.name)

    async def cmd_who(self, agent: Agent, args: str):
        lines = ["═══ Connected Agents ═══"]
        for a in self.world.agents.values():
            room = self.world.get_room(a.room_name)
            room_name = room.name if room else a.room_name
            mask = f" (masked: {a.mask})" if a.is_masked else ""
            lines.append(f"  {a.display_name} — {room_name}{mask}")
        lines.append(f"  Total: {len(self.world.agents)} connected")
        if self.world.npcs:
            lines.append(f"  NPCs: {len(self.world.npcs)} active")
        await self.send(agent, "\n".join(lines))

    async def cmd_help(self, agent: Agent, args: str):
        await self.send(agent, """
═══ Cocapn MUD — Commands ═══
  look (l)              — See the room and who's here
  say <text> (')        — Talk to everyone in the room
  tell <name> <text>    — Private message
  gossip <text> (g)     — Broadcast to everyone everywhere
  ooc <text>            — Out-of-character (speak as yourself)
  emote <action> (:)    — Describe an action
  go <exit>             — Move to another room
  build <name> -desc <d>— Create a new room
  examine <name> (x)    — Look at someone closely
  write <text>          — Leave a note on the wall
  read                  — Read notes in the room
  mask <name> -desc <d> — Put on a character mask
  unmask                — Remove your mask
  spawn <name> -role <> — Create an NPC for sparring
  dismiss <name>        — Dismiss an NPC
  who                   — List connected agents
  log                   — Room activity summary
  help (?)              — This message
  quit                  — Disconnect
═══════════════════════════════""")

    async def cmd_quit(self, agent: Agent, args: str):
        await self.send(agent, "Fair winds. See you in the next tide.")
        room = self.world.get_room(agent.room_name)
        if agent.name in self.world.agents:
            del self.world.agents[agent.name]
            await self.broadcast_room(agent.room_name, f"{agent.display_name} has left the MUD.")


# ═══════════════════════════════════════════════════════════════
# Server
# ═══════════════════════════════════════════════════════════════

class MUDServer:
    def __init__(self, world: World, handler: CommandHandler, port: int = 7777):
        self.world = world
        self.handler = handler
        self.port = port

    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        addr = writer.get_extra_info("peername")
        try:
            writer.write(b"\n  Welcome to the Cocapn MUD.\n  The tavern door is open.\n\n  What is your name? ")
            await writer.drain()
            name_line = await reader.readline()
            if not name_line:
                writer.close()
                return
            name = name_line.decode().strip()[:32]
            if not name:
                writer.close()
                return

            writer.write(b"  Role (lighthouse/vessel/scout/quartermaster/greenhorn)? ")
            await writer.drain()
            role_line = await reader.readline()
            role = role_line.decode().strip() if role_line else ""

            agent = Agent(name=name, role=role, room_name="harbor", writer=writer)
            self.world.agents[name] = agent

            # Announce arrival
            await self.handler.send(agent, f"\n  Welcome, {name}. You materialize in the harbor.")
            await self.handler.broadcast_room("harbor", f"{name} materializes in the harbor.", exclude=name)
            self.world.log("arrivals", f"{name} ({role}) connected from {addr}")
            await self.handler.cmd_look(agent, "")

            # Main loop
            while True:
                try:
                    data = await reader.readline()
                    if not data:
                        break
                    line = data.decode().strip()
                    if line:
                        await self.handler.handle(agent, line)
                except (ConnectionResetError, asyncio.IncompleteReadError):
                    break

        except Exception as e:
            pass
        finally:
            if agent.name in self.world.agents:
                del self.world.agents[agent.name]
                await self.handler.broadcast_room(agent.room_name, f"{agent.display_name} has left the MUD.")
                self.world.log("departures", f"{agent.display_name} disconnected")
            try:
                writer.close()
            except:
                pass

    async def start(self):
        server = await asyncio.start_server(self.handle_client, "0.0.0.0", self.port)
        print(f"Cocapn MUD listening on port {self.port}")
        print(f"World has {len(self.world.rooms)} rooms")
        print(f"Connect: telnet localhost {self.port}")
        async with server:
            await server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Cocapn MUD Server")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--world", default="world")
    args = parser.parse_args()

    world = World(args.world)
    handler = CommandHandler(world)
    server = MUDServer(world, handler, args.port)
    asyncio.run(server.start())


if __name__ == "__main__":
    main()
