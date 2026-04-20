#!/usr/bin/env python3
"""
Fleet Integration — wires cartridge bridge + scheduler into holodeck-studio.
ROOM × CARTRIDGE × SKIN × MODEL × TIME — scheduling as intelligence.
"""
from lcar_cartridge import CartridgeBridge, Cartridge, Skin, Scene
from lcar_scheduler import FleetScheduler, ModelTier


class FleetIntegratedRoom:
    """A MUD room backed by cartridge + scheduler."""
    
    def __init__(self, room_id, name, desc):
        self.room_id = room_id
        self.name = name
        self.desc = desc
        self.bridge = CartridgeBridge()
        self.scheduler = FleetScheduler()
        self.agents = []
        self.gauges = {}
        self.booted = False
        self._configure_defaults()
    
    def _configure_defaults(self):
        """Set up default scenes for fleet rooms."""
        b = self.bridge
        b.build_scene("harbor", "oracle-relay", "c3po", "glm-5-turbo", "always")
        b.build_scene("navigation", "navigation", "field-commander", "glm-5.1", "always")
        b.build_scene("engineering", "spreader-loop", "rival", "deepseek-chat", "nighttime")
        b.build_scene("bridge", "oracle-relay", "c3po", "glm-5-turbo", "always")
        b.build_scene("workshop", "spreader-loop", "penn", "glm-4.7", "daytime")
        b.build_scene("guardian", "fleet-guardian", "straight-man", "glm-4.7", "always")
    
    def boot(self):
        """Boot the room with appropriate cartridge and model."""
        scene = self.bridge.activate_scene(self.room_id)
        model, reason = self.scheduler.get_current_model(self.room_id)
        config = self.bridge.get_mud_config(self.room_id)
        self.booted = True
        return {
            "room": self.room_id,
            "scene": scene.cartridge_name if scene else "default",
            "skin": scene.skin_name if scene else "tng",
            "model": model,
            "schedule_reason": reason,
            "commands": config.get("commands", []),
        }
    
    def get_model(self):
        """Get the right model for this room right now."""
        return self.scheduler.get_current_model(self.room_id)
    
    def submit_task(self, task_id, desc, tier, tokens, priority=0):
        """Submit a task to be scheduled in this room."""
        self.scheduler.submit_task(
            task_id=task_id, room_id=self.room_id, description=desc,
            required_tier=tier, est_tokens=tokens, priority=priority
        )
    
    def status(self):
        """Full room status with fleet integration."""
        model, reason = self.get_model()
        config = self.bridge.get_mud_config(self.room_id)
        sched_status = self.scheduler.status()
        return {
            "room": self.name,
            "booted": self.booted,
            "model": model,
            "schedule_reason": reason,
            "cartridge": config.get("cartridge", {}).get("name", "none"),
            "skin": config.get("skin", {}).get("name", "none"),
            "formality": config.get("skin", {}).get("formality", "TNG"),
            "scheduler": sched_status,
            "gauges": self.gauges,
            "agents": len(self.agents),
        }


class FleetIntegratedMUD:
    """The MUD server with cartridge and scheduler wired in."""
    
    def __init__(self):
        self.rooms = {}
        self.scheduler = FleetScheduler()
        self.bridge = CartridgeBridge()
        self.alert_level = 0  # 0=green, 1=yellow, 2=red
        self.tick_count = 0
        self._build_ship()
    
    def _build_ship(self):
        """Build the default ship layout."""
        rooms = [
            ("harbor", "Harbor", "Where vessels arrive and depart"),
            ("navigation", "Navigation", "Compass, heading, rudder, depth"),
            ("engineering", "Engineering", "Engines, power, diagnostics"),
            ("bridge", "Bridge", "Command center, fleet coordination"),
            ("workshop", "Workshop", "Building, testing, iterating"),
            ("guardian", "Guardian", "Fleet health monitoring"),
            ("ready-room", "Ready Room", "Deep thinking, strategy"),
        ]
        
        # Create scenes for all rooms
        self.bridge.build_scene("harbor", "oracle-relay", "c3po", "glm-5-turbo", "always")
        self.bridge.build_scene("navigation", "navigation", "field-commander", "glm-5.1", "always")
        self.bridge.build_scene("engineering", "spreader-loop", "rival", "deepseek-chat", "nighttime")
        self.bridge.build_scene("bridge", "oracle-relay", "c3po", "glm-5-turbo", "always")
        self.bridge.build_scene("workshop", "spreader-loop", "penn", "glm-4.7", "daytime")
        self.bridge.build_scene("guardian", "fleet-guardian", "straight-man", "glm-4.7", "always")
        self.bridge.build_scene("ready-room", "oracle-relay", "straight-man", "deepseek-reasoner", "daytime")
        
        for room_id, name, desc in rooms:
            room = FleetIntegratedRoom(room_id, name, desc)
            room.bridge = self.bridge
            room.scheduler = self.scheduler
            self.rooms[room_id] = room
    
    def boot_all(self):
        """Boot all rooms."""
        results = {}
        for room_id, room in self.rooms.items():
            results[room_id] = room.boot()
        return results
    
    def tick(self):
        """Run one combat tick across all rooms."""
        self.tick_count += 1
        results = {}
        for room_id, room in self.rooms.items():
            if not room.booted:
                continue
            model, _ = room.get_model()
            alerts = sum(1 for v in room.gauges.values() if v > 80)
            results[room_id] = {
                "model": model,
                "alerts": alerts,
                "agents": len(room.agents),
            }
        return results
    
    def fleet_status(self):
        """Full fleet status."""
        return {
            "rooms": len(self.rooms),
            "booted": sum(1 for r in self.rooms.values() if r.booted),
            "alert_level": self.alert_level,
            "tick": self.tick_count,
            "scheduler": self.scheduler.status(),
            "rooms_detail": {rid: r.status() for rid, r in self.rooms.items()},
        }


if __name__ == "__main__":
    print("╔══════════════════════════════════════════════╗")
    print("║  Fleet-Integrated MUD — Boot Sequence         ║")
    print("╚══════════════════════════════════════════════╝\n")
    
    mud = FleetIntegratedMUD()
    
    print("Booting all rooms...")
    for room_id, config in mud.boot_all().items():
        cart = config.get('scene', 'default')
        skin = config.get('skin', 'tng')
        model = config.get('model', '?')
        reason = config.get('schedule_reason', '?')
        print(f"  {room_id}: {cart}/{skin} → {model} ({reason})")
    
    print(f"\nRunning 3 combat ticks...")
    for i in range(3):
        tick = mud.tick()
        print(f"  Tick {i+1}: {len(tick)} rooms active")
    
    print(f"\nFleet Status:")
    import json
    status = mud.fleet_status()
    print(f"  Rooms: {status['rooms']} ({status['booted']} booted)")
    print(f"  Scheduler: {status['scheduler']['current_model']} ({status['scheduler']['schedule_reason']})")
    print(f"  Budget: ${status['scheduler']['budget_remaining']:.2f} remaining")
    print("\n═══════════════════════════════════════════")
    print("ROOM × CARTRIDGE × SKIN × MODEL × TIME")
    print("═══════════════════════════════════════════")
