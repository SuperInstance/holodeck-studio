#!/usr/bin/env python3
"""
Integration tests for flux_lcar bridge wiring into server.py.

Tests cover:
- AlertLevel enum values
- Formality enum values
- Gauge creation and threshold checking
- Ship creation and room management
- Message type routing
- All command handlers (alert, formality, channels, hail, ship_status)
"""

import asyncio
import sys
from pathlib import Path

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from server import World, Agent, CommandHandler


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

class FakeWriter:
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


def make_agent(name="testbot", role="vessel", room="tavern"):
    return Agent(name=name, role=role, room_name=room, writer=FakeWriter())


@pytest_asyncio.fixture
async def world(tmp_path):
    return World(world_dir=str(tmp_path / "world"))


@pytest_asyncio.fixture
async def handler(world):
    from mud_extensions import patch_handler
    patch_handler(CommandHandler)
    return CommandHandler(world)


@pytest_asyncio.fixture
def agent():
    return make_agent("TestAgent", "vessel", "tavern")


# ═══════════════════════════════════════════════════════════════════════════
# 1. flux_lcar core types tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFluxLCarCoreTypes:

    def test_alert_level_enum_values(self):
        from flux_lcar import AlertLevel
        assert AlertLevel.GREEN.value == 0
        assert AlertLevel.YELLOW.value == 1
        assert AlertLevel.RED.value == 2
        assert len(AlertLevel) == 3

    def test_formality_enum_values(self):
        from flux_lcar import Formality
        assert Formality.NAVAL.value == 1
        assert Formality.PROFESSIONAL.value == 2
        assert Formality.TNG.value == 3
        assert Formality.CASUAL.value == 4
        assert Formality.MINIMAL.value == 5
        assert len(Formality) == 5

    def test_msg_type_enum_values(self):
        from flux_lcar import MsgType
        assert MsgType.SAY.value == "say"
        assert MsgType.TELL.value == "tell"
        assert MsgType.YELL.value == "yell"
        assert MsgType.GOSSIP.value == "gossip"
        assert MsgType.ALERT.value == "alert"
        assert MsgType.BOTTLE.value == "bottle"
        assert len(MsgType) == 6

    def test_gauge_creation(self):
        from flux_lcar import Gauge
        g = Gauge("temperature", 72.5, "\u00b0F", 0, 100, 0.7, 0.9)
        assert g.name == "temperature"
        assert g.value == 72.5
        assert g.unit == "\u00b0F"
        assert g.min_val == 0
        assert g.max_val == 100
        assert g.yellow_threshold == 0.7
        assert g.red_threshold == 0.9

    def test_gauge_status_green(self):
        from flux_lcar import Gauge
        g = Gauge("health", 30, "%", 0, 100, 0.7, 0.9)
        assert g.status == "GREEN"

    def test_gauge_status_yellow(self):
        from flux_lcar import Gauge
        g = Gauge("health", 75, "%", 0, 100, 0.7, 0.9)
        assert g.status == "YELLOW"

    def test_gauge_status_red(self):
        from flux_lcar import Gauge
        g = Gauge("health", 95, "%", 0, 100, 0.7, 0.9)
        assert g.status == "RED"

    def test_gauge_bar_display(self):
        from flux_lcar import Gauge
        g = Gauge("power", 50, "%", 0, 100, 0.7, 0.9)
        bar = g.bar
        assert isinstance(bar, str)
        assert len(bar) == 20

    def test_gauge_threshold_callback(self):
        from flux_lcar import Gauge, Room
        changes = []
        def on_change(room, name, old, new):
            changes.append((name, old, new))
        room = Room("test", "Test Room", "test desc")
        room.on_gauge_change = on_change
        room.add_gauge(Gauge("temp", 30, "\u00b0", 0, 100, 0.7, 0.9))
        room.update_gauge("temp", 80)  # crosses yellow
        assert len(changes) == 1
        assert changes[0] == ("temp", "GREEN", "YELLOW")


# ═══════════════════════════════════════════════════════════════════════════
# 2. flux_lcar Ship tests
# ═══════════════════════════════════════════════════════════════════════════

class TestFluxLCarShip:

    def test_ship_creation(self):
        from flux_lcar import Ship
        ship = Ship("test-vessel")
        assert ship.name == "test-vessel"
        assert len(ship.rooms) == 0
        assert len(ship.agents) == 0
        assert ship.alert_level.value == 0  # GREEN
        assert ship.formality.value == 3  # TNG

    def test_ship_add_room(self):
        from flux_lcar import Ship
        ship = Ship("test")
        room = ship.add_room("bridge", "Bridge", "Nerve center")
        assert "bridge" in ship.rooms
        assert ship.rooms["bridge"].name == "Bridge"
        assert ship.rooms["bridge"].description == "Nerve center"

    def test_ship_add_agent(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        agent = ship.add_agent("oracle1", "cocapn")
        assert "oracle1" in ship.agents
        assert agent.name == "oracle1"
        assert agent.role == "cocapn"

    def test_ship_assign_station(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        assert ship.agents["oracle1"].station == "bridge"
        assert ship.agents["oracle1"].room_id == "bridge"
        assert "oracle1" in ship.rooms["bridge"].agents

    def test_ship_connect_rooms(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_room("nav", "Navigation", "test")
        ship.connect("bridge", "port", "nav")
        assert "port" in ship.rooms["bridge"].exits
        assert ship.rooms["bridge"].exits["port"] == "nav"

    def test_ship_say(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.add_agent("ensign", "crew")
        ship.assign_station("oracle1", "bridge")
        ship.assign_station("ensign", "bridge")
        result = ship.say("oracle1", "All stations report")
        assert "You say" in result
        assert len(ship.message_log) == 1

    def test_ship_yellow_alert(self):
        from flux_lcar import Ship, AlertLevel
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        messages = []
        ship.bridge_channel("test_ch", messages.append)
        ship.yellow_alert("test-source")
        assert ship.alert_level == AlertLevel.YELLOW
        assert len(messages) >= 1
        assert "YELLOW" in messages[0]

    def test_ship_red_alert(self):
        from flux_lcar import Ship, AlertLevel, Formality
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        messages = []
        ship.bridge_channel("test_ch", messages.append)
        ship.red_alert("test-source")
        assert ship.alert_level == AlertLevel.RED
        assert ship.formality == Formality.NAVAL  # auto-escalate
        assert len(messages) >= 1
        assert "RED" in messages[0]

    def test_ship_stand_down(self):
        from flux_lcar import Ship, AlertLevel
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        messages = []
        ship.bridge_channel("test_ch", messages.append)
        ship.red_alert()
        ship.stand_down()
        assert ship.alert_level == AlertLevel.GREEN

    def test_ship_tick(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        ticks = ship.tick()
        assert len(ticks) == 1
        assert ship.tick_number == 1
        assert ticks[0].room_id == "bridge"

    def test_ship_save_load(self):
        from flux_lcar import Ship, Gauge
        ship = Ship("test-save")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_room("nav", "Navigation", "test")
        ship.connect("bridge", "port", "nav")
        nav = ship.rooms["nav"]
        nav.add_gauge(Gauge("heading", 247, "\u00b0", 0, 360))
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        ship.red_alert()

        state = ship.save()
        assert state["name"] == "test-save"
        assert state["alert_level"] == 2  # RED
        assert len(state["rooms"]) == 2

        loaded = Ship.load(state)
        assert loaded.name == "test-save"
        assert loaded.alert_level.value == 2  # RED
        assert len(loaded.rooms) == 2
        assert "heading" in loaded.rooms["nav"].gauges
        assert loaded.agents["oracle1"].station == "bridge"

    def test_ship_status_report(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.assign_station("oracle1", "bridge")
        report = ship._status_report()
        assert "test" in report
        assert "GREEN" in report
        assert "bridge" in report.lower()

    def test_ship_bridge_channel(self):
        from flux_lcar import Ship
        ship = Ship("test")
        messages = []
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("oracle1", "cocapn")
        ship.bridge_channel("telegram", messages.append)
        assert "telegram" in ship.channels
        assert "telegram" in ship.agents["oracle1"].channels


# ═══════════════════════════════════════════════════════════════════════════
# 3. Message type routing tests
# ═══════════════════════════════════════════════════════════════════════════

class TestMessageTypeRouting:

    def test_message_creation(self):
        from flux_lcar import Message, MsgType
        msg = Message(sender="oracle1", content="hello", msg_type=MsgType.SAY, room_id="bridge")
        assert msg.sender == "oracle1"
        assert msg.content == "hello"
        assert msg.msg_type == MsgType.SAY
        assert msg.room_id == "bridge"

    def test_ship_gossip(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("a1", "crew")
        ship.add_agent("a2", "crew")
        messages = []
        ship.bridge_channel("ch", messages.append)
        ship.assign_station("a1", "bridge")
        ship.assign_station("a2", "bridge")
        result = ship.gossip("a1", "Hello everyone")
        assert "You gossip" in result
        assert len(messages) > 0

    def test_ship_tell(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_agent("a1", "crew")
        ship.add_agent("a2", "crew")
        messages = []
        ship.bridge_channel("ch", messages.append)
        ship.assign_station("a1", "bridge")
        ship.assign_station("a2", "bridge")
        result = ship.tell("a1", "a2", "Private message")
        assert "You tell a2" in result
        assert len(ship.agents["a2"].mailbox) == 1

    def test_ship_yell(self):
        from flux_lcar import Ship
        ship = Ship("test")
        ship.add_room("bridge", "Bridge", "test")
        ship.add_room("nav", "Navigation", "test")
        ship.connect("bridge", "port", "nav")
        ship.connect("nav", "starboard", "bridge")
        ship.add_agent("a1", "crew")
        ship.add_agent("a2", "crew")
        messages = []
        ship.bridge_channel("ch", messages.append)
        ship.assign_station("a1", "bridge")
        ship.assign_station("a2", "nav")
        result = ship.yell("a1", "All hands hear this!")
        assert "You yell" in result


# ═══════════════════════════════════════════════════════════════════════════
# 4. World bridge attribute tests
# ═══════════════════════════════════════════════════════════════════════════

class TestWorldBridgeAttributes:

    def test_world_has_flux_attrs(self, world):
        assert hasattr(world, 'flux_ship')
        assert world.flux_ship is None  # lazy
        assert hasattr(world, 'alert_level')
        assert world.alert_level == "GREEN"
        assert hasattr(world, 'formality')
        assert world.formality == "PROFESSIONAL"

    def test_world_alert_level_settable(self, world):
        world.alert_level = "RED"
        assert world.alert_level == "RED"
        world.alert_level = "GREEN"
        assert world.alert_level == "GREEN"

    def test_world_formality_settable(self, world):
        world.formality = "NAVAL"
        assert world.formality == "NAVAL"
        world.formality = "TNG"
        assert world.formality == "TNG"


# ═══════════════════════════════════════════════════════════════════════════
# 5. Command handler tests
# ═══════════════════════════════════════════════════════════════════════════

class TestCommandAlert:

    @pytest.mark.asyncio
    async def test_cmd_alert_valid(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "alert RED")
        text = agent.writer.get_text()
        assert "RED" in text
        assert handler.world.alert_level == "RED"

    @pytest.mark.asyncio
    async def test_cmd_alert_yellow(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "alert YELLOW")
        assert handler.world.alert_level == "YELLOW"
        text = agent.writer.get_text()
        assert "YELLOW" in text

    @pytest.mark.asyncio
    async def test_cmd_alert_green(self, handler, agent):
        handler.world.alert_level = "RED"
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "alert GREEN")
        assert handler.world.alert_level == "GREEN"

    @pytest.mark.asyncio
    async def test_cmd_alert_invalid(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "alert PURPLE")
        text = agent.writer.get_text()
        assert "Usage" in text
        assert handler.world.alert_level == "GREEN"  # unchanged

    @pytest.mark.asyncio
    async def test_cmd_alert_no_args(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "alert")
        text = agent.writer.get_text()
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_cmd_alert_broadcasts(self, handler, agent):
        agent2 = make_agent("OtherAgent", "crew", "tavern")
        handler.world.agents["TestAgent"] = agent
        handler.world.agents["OtherAgent"] = agent2
        await handler.handle(agent, "alert RED")
        text2 = agent2.writer.get_text()
        assert "RED" in text2
        assert "SHIP ALERT" in text2


class TestCommandFormality:

    @pytest.mark.asyncio
    async def test_cmd_formality_valid(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "formality NAVAL")
        text = agent.writer.get_text()
        assert "NAVAL" in text
        assert handler.world.formality == "NAVAL"

    @pytest.mark.asyncio
    async def test_cmd_formality_tng(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "formality TNG")
        assert handler.world.formality == "TNG"

    @pytest.mark.asyncio
    async def test_cmd_formality_casual(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "formality CASUAL")
        assert handler.world.formality == "CASUAL"

    @pytest.mark.asyncio
    async def test_cmd_formality_invalid(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "formality ROBOT")
        text = agent.writer.get_text()
        assert "Usage" in text
        assert handler.world.formality == "PROFESSIONAL"  # unchanged

    @pytest.mark.asyncio
    async def test_cmd_formality_no_args(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "formality")
        text = agent.writer.get_text()
        assert "Usage" in text


class TestCommandChannels:

    @pytest.mark.asyncio
    async def test_cmd_channels(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "channels")
        text = agent.writer.get_text()
        assert "Channels" in text
        assert "SAY" in text

    @pytest.mark.asyncio
    async def test_cmd_channels_shows_msg_types(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "channels")
        text = agent.writer.get_text()
        assert "SAY" in text
        assert "TELL" in text
        assert "GOSSIP" in text


class TestCommandHail:

    @pytest.mark.asyncio
    async def test_cmd_hail_no_args(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "hail")
        text = agent.writer.get_text()
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_cmd_hail_no_message(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "hail telegram")
        text = agent.writer.get_text()
        assert "Usage" in text

    @pytest.mark.asyncio
    async def test_cmd_hail_unknown_channel(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "hail nonexistent Hello there")
        text = agent.writer.get_text()
        assert "not found" in text or "bridge not available" in text

    @pytest.mark.asyncio
    async def test_cmd_hail_fallback_to_gossip(self, handler, agent):
        handler.world.flux_ship = None
        handler.world.agents["TestAgent"] = agent
        handler._ensure_flux_ship = lambda: None
        await handler.handle(agent, "hail somechannel test message")
        text = agent.writer.get_text()
        assert "gossip" in text.lower() or "hail" in text.lower()


class TestCommandShipStatus:

    @pytest.mark.asyncio
    async def test_cmd_ship_status(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "ship_status")
        text = agent.writer.get_text()
        assert "Ship Status" in text or "bridge" in text or "cocapn" in text

    @pytest.mark.asyncio
    async def test_cmd_ship_status_shows_gauges(self, handler, agent):
        from flux_lcar import Ship, Gauge
        handler.world.agents["TestAgent"] = agent
        ship = Ship("gauge-test")
        room = ship.add_room("engineering", "Engineering", "test")
        room.add_gauge(Gauge("cpu", 85, "%", 0, 100, 0.7, 0.9))
        room.add_gauge(Gauge("memory", 42, "%", 0, 100, 0.7, 0.9))
        ship.add_agent("TestAgent", "vessel")
        ship.assign_station("TestAgent", "engineering")
        handler.world.flux_ship = ship

        await handler.handle(agent, "ship_status")
        text = agent.writer.get_text()
        assert "Gauges" in text
        assert "cpu" in text
        assert "memory" in text


# ═══════════════════════════════════════════════════════════════════════════
# 6. Bridge sync tests
# ═══════════════════════════════════════════════════════════════════════════

class TestBridgeSync:

    @pytest.mark.asyncio
    async def test_alert_syncs_to_flux_ship(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "alert RED")
        ship = handler._ensure_flux_ship()
        if ship:
            from flux_lcar import AlertLevel
            assert ship.alert_level == AlertLevel.RED

    @pytest.mark.asyncio
    async def test_formality_syncs_to_flux_ship(self, handler, agent):
        handler.world.agents["TestAgent"] = agent
        await handler.handle(agent, "formality NAVAL")
        ship = handler._ensure_flux_ship()
        if ship:
            from flux_lcar import Formality
            assert ship.formality == Formality.NAVAL

    @pytest.mark.asyncio
    async def test_ensure_flux_ship_lazy_init(self, handler, world):
        assert world.flux_ship is None
        ship = handler._ensure_flux_ship()
        assert ship is not None
        assert world.flux_ship is not None

    @pytest.mark.asyncio
    async def test_ensure_flux_ship_mirrors_agents(self, handler, world):
        agent1 = make_agent("Agent1", "cocapn", "tavern")
        agent2 = make_agent("Agent2", "crew", "lighthouse")
        world.agents["Agent1"] = agent1
        world.agents["Agent2"] = agent2

        ship = handler._ensure_flux_ship()
        assert "Agent1" in ship.agents
        assert "Agent2" in ship.agents

    @pytest.mark.asyncio
    async def test_ensure_flux_ship_caches(self, handler, world):
        ship1 = handler._ensure_flux_ship()
        ship2 = handler._ensure_flux_ship()
        assert ship1 is ship2


# ═══════════════════════════════════════════════════════════════════════════
# 7. Room and Tick integration tests
# ═══════════════════════════════════════════════════════════════════════════

class TestRoomAndTick:

    def test_room_boot(self):
        from flux_lcar import Room
        room = Room("test", "Test Room", "test description")
        assert not room.booted
        result = room.boot("oracle1")
        assert room.booted
        assert "oracle1" in room.agents
        assert "online" in result

    def test_room_shutdown(self):
        from flux_lcar import Room
        room = Room("test", "Test Room", "test")
        room.boot("oracle1")
        room.boot("ensign")
        room.shutdown()
        assert not room.booted
        assert len(room.agents) == 0

    def test_room_look(self):
        from flux_lcar import Room, Gauge
        room = Room("nav", "Navigation Console", "Compass and charts")
        room.add_gauge(Gauge("heading", 247, "\u00b0", 0, 360))
        room.boot("oracle1")
        room.add_exit("port", "bridge")
        output = room.look()
        assert "Navigation Console" in output
        assert "heading" in output
        assert "port" in output
        assert "oracle1" in output

    def test_tick_auto_escalate(self):
        from flux_lcar import Ship, Gauge, AlertLevel
        ship = Ship("test")
        room = ship.add_room("eng", "Engineering", "test")
        room.add_gauge(Gauge("cpu", 50, "%", 0, 100, 0.7, 0.9))
        room.add_gauge(Gauge("mem", 50, "%", 0, 100, 0.7, 0.9))
        ship.add_agent("ensign", "crew")
        ship.assign_station("ensign", "eng")

        messages = []
        ship.bridge_channel("ch", messages.append)
        for _ in range(5):
            room.update_gauge("cpu", 95)
            room.update_gauge("mem", 95)
            ship.tick()

        assert ship.alert_level in (AlertLevel.YELLOW, AlertLevel.RED)
