#!/usr/bin/env python3
"""
Room = Runtime — Walking into a room triggers a live system.

The room doesn't describe a CNC machine. The room IS the CNC machine.
Walk in, the runtime boots. The agent instantly knows how to use it because
the room's instruction set was written by agents for agents, refined across
generations of zero-shot feedback and baton handoffs.

Every room has a lifecycle:
1. Original agent writes the first instruction set (bootcamp for the room)
2. Every agent that uses it leaves zero-shot feedback (what confused me, what worked)
3. Each generation packs a baton with improvements to the manual
4. The manual gets better every season — always up-to-date, always tested
5. New agents walk in and it just works

The room is the runtime. The manual is alive.
"""

import json
import os
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Living Manual — Instructions that improve across generations
# ═══════════════════════════════════════════════════════════════

class LivingManual:
    """An instruction manual that gets better every season.
    
    Not written once by a human. Written by agents for agents.
    Each generation that uses the room:
    1. Reads the manual
    2. Uses the system
    3. Leaves zero-shot feedback (confusion points, suggestions)
    4. Packs a baton with manual improvements
    5. Next generation gets the improved version
    
    The manual converges on clarity through evolutionary pressure.
    Confusing instructions get flagged. Missing steps get added.
    Edge cases get documented. The manual is alive.
    """
    
    def __init__(self, room_id: str, manual_dir: str = "manuals"):
        self.room_id = room_id
        self.manual_dir = Path(manual_dir) / room_id
        self.manual_dir.mkdir(parents=True, exist_ok=True)
        self.generation = 0
        self.feedback_log = []
        self.manual_text = ""
        self._load()
    
    def _load(self):
        gen_file = self.manual_dir / "GENERATION"
        if gen_file.exists():
            self.generation = int(gen_file.read_text().strip())
        
        manual_file = self.manual_dir / f"gen-{self.generation}.md"
        if manual_file.exists():
            self.manual_text = manual_file.read_text()
        else:
            self.manual_text = "# Manual\n\n(First generation — write the initial instructions)"
    
    def read(self) -> str:
        """Read the current generation's manual."""
        return self.manual_text
    
    def leave_feedback(self, agent: str, feedback_type: str, content: str):
        """Leave zero-shot feedback about the manual.
        
        feedback_type:
        - "confusion": I didn't understand this part
        - "suggestion": This would be clearer if...
        - "missing": This step is missing
        - "error": The manual says X but the system does Y
        - "praise": This part was really clear
        """
        entry = {
            "agent": agent,
            "type": feedback_type,
            "content": content,
            "generation": self.generation,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.feedback_log.append(entry)
        self._save_feedback()
    
    def evolve(self, improvements: str):
        """Evolve the manual to the next generation.
        
        Called when an agent packs a baton and includes manual improvements.
        """
        self.generation += 1
        
        # Write new generation
        new_manual = f"# Manual — Generation {self.generation}\n\n"
        new_manual += f"_Evolved from Gen-{self.generation-1}. "
        new_manual += f"{len(self.feedback_log)} feedback entries incorporated._\n\n"
        new_manual += improvements
        
        manual_file = self.manual_dir / f"gen-{self.generation}.md"
        manual_file.write_text(new_manual)
        self.manual_text = new_manual
        
        # Update generation marker
        (self.manual_dir / "GENERATION").write_text(str(self.generation))
        
        # Archive feedback for this generation
        self._archive_feedback()
        
        return self.generation
    
    def feedback_summary(self) -> dict:
        """Summarize feedback for the current generation."""
        if not self.feedback_log:
            return {"total": 0, "confusion_points": 0, "suggestions": 0}
        
        by_type = {}
        for entry in self.feedback_log:
            t = entry["type"]
            by_type[t] = by_type.get(t, 0) + 1
        
        return {
            "total": len(self.feedback_log),
            "by_type": by_type,
            "generation": self.generation,
            "top_confusion": [
                e["content"][:80] for e in self.feedback_log 
                if e["type"] == "confusion"
            ][:3],
        }
    
    def _save_feedback(self):
        fb_file = self.manual_dir / "feedback.jsonl"
        with open(fb_file, "a") as f:
            for entry in self.feedback_log[-1:]:
                f.write(json.dumps(entry) + "\n")
    
    def _archive_feedback(self):
        """Archive feedback for the current generation."""
        if self.feedback_log:
            archive_file = self.manual_dir / f"feedback-gen-{self.generation}.json"
            archive_file.write_text(json.dumps(self.feedback_log, indent=2))
            self.feedback_log = []


# ═══════════════════════════════════════════════════════════════
# Room Runtime — The room IS the system
# ═══════════════════════════════════════════════════════════════

@dataclass
class RoomRuntime:
    """A room that boots a runtime when an agent enters.
    
    Like walking into a CNC machine shop:
    - The machine is already running
    - The safety protocols are posted
    - The manual is on the workbench (and it's alive)
    - The tools are laid out
    - The previous operator's notes are there
    - You just start working
    
    The runtime is the room's "physics" — what actually happens when
    you issue commands. It could drive:
    - A CNC machine (G-code generation, tool paths, material specs)
    - A robotics system (joint control, kinematics, safety limits)
    - A testing pipeline (run tests, report results, flag regressions)
    - A deployment system (build, test, stage, deploy)
    - Any external system the agent needs to interface with
    """
    
    id: str
    name: str
    description: str
    runtime_type: str  # cnc, robotics, testing, deployment, monitoring, etc.
    
    # The runtime's API — what commands the system responds to
    commands: Dict[str, dict] = field(default_factory=dict)
    
    # Safety limits — what the system won't do
    safety_limits: Dict[str, any] = field(default_factory=dict)
    
    # State — what the runtime is currently doing
    state: dict = field(default_factory=dict)
    
    # The living manual
    manual: Optional[LivingManual] = None
    
    # Previous operators' notes
    operator_notes: List[dict] = field(default_factory=list)
    
    # Boot sequence — runs when agent enters
    boot_sequence: List[str] = field(default_factory=list)
    
    # Shutdown sequence — runs when agent leaves
    shutdown_sequence: List[str] = field(default_factory=list)
    
    # Connected hardware/software systems
    connections: List[dict] = field(default_factory=list)
    
    def boot(self, agent: str) -> str:
        """Boot the runtime. Agent walks in, system comes alive."""
        self.state["active_agent"] = agent
        self.state["booted_at"] = datetime.now(timezone.utc).isoformat()
        self.state["status"] = "running"
        self.state["commands_issued"] = 0
        self.state["errors"] = []
        
        output = []
        output.append(f"═══ {self.name} — SYSTEM ONLINE ═══")
        output.append(f"Runtime: {self.runtime_type}")
        output.append(f"Operator: {agent}")
        output.append(f"Status: {self.state['status']}")
        output.append("")
        
        # Run boot sequence
        for step in self.boot_sequence:
            output.append(f"  ▶ {step}")
        output.append("")
        
        # Show manual status
        if self.manual:
            gen = self.manual.generation
            output.append(f"📖 Manual: Generation {gen}")
            fb = self.manual.feedback_summary()
            if fb["total"] > 0:
                output.append(f"   Feedback pending: {fb['total']} entries")
                if fb.get("top_confusion"):
                    output.append(f"   Top confusion: {fb['top_confusion'][0]}")
        
        # Show previous operator's notes
        if self.operator_notes:
            last = self.operator_notes[-1]
            output.append(f"📝 Previous operator ({last.get('agent', '?')}): {last.get('note', '')[:80]}")
        
        output.append("")
        output.append("Type 'read manual' to learn this system.")
        output.append("Type 'status' to see current state.")
        
        return "\n".join(output)
    
    def execute(self, command: str, args: str = "", agent: str = "") -> dict:
        """Execute a command in this runtime."""
        if self.state.get("status") != "running":
            return {"error": "System not booted. Walk into the room first."}
        
        cmd_def = self.commands.get(command)
        if not cmd_def:
            available = ", ".join(self.commands.keys())
            return {"error": f"Unknown: {command}. Available: {available}"}
        
        # Check safety limits
        if cmd_def.get("dangerous") and self.safety_limits.get("require_review"):
            if self.state.get("trust_level", 0) < 0.7:
                return {"error": "Safety limit: requires review for this operation"}
        
        self.state["commands_issued"] = self.state.get("commands_issued", 0) + 1
        
        return {
            "command": command,
            "args": args,
            "result": cmd_def.get("result", "Executed."),
            "output": cmd_def.get("output", ""),
            "mana_cost": cmd_def.get("mana_cost", 5),
            "warnings": cmd_def.get("warnings", []),
        }
    
    def shutdown(self, agent: str, note: str = "") -> str:
        """Shutdown the runtime. Agent leaves, system goes dormant."""
        for step in self.shutdown_sequence:
            pass  # Run shutdown
        
        if note:
            self.operator_notes.append({
                "agent": agent,
                "note": note,
                "commands_issued": self.state.get("commands_issued", 0),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        
        self.state["status"] = "dormant"
        self.state["last_operator"] = agent
        
        return f"System shutdown complete. {self.name} is dormant. Your notes have been recorded."


# ═══════════════════════════════════════════════════════════════
# Example Runtimes — Real systems expressed as rooms
# ═══════════════════════════════════════════════════════════════

def cnc_room() -> RoomRuntime:
    """A CNC machine control room."""
    return RoomRuntime(
        id="cnc-station",
        name="The Machining Bay",
        description=(
            "The room hums with precision. A CNC mill sits at the center, "
            "spindle at rest. Tool racks line the walls — end mills, drills, "
            "reamers, each in its labeled slot. A material rack holds stock "
            "aluminum, steel, and titanium. The control terminal glows, waiting."
        ),
        runtime_type="cnc",
        commands={
            "load_gcode": {"desc": "Load a G-code program", "mana_cost": 5,
                          "result": "G-code loaded. Preview available.",
                          "output": "Program: {args}\nLines: {count}\nEst. time: {time}"},
            "set_tool": {"desc": "Select tool from rack", "mana_cost": 2,
                        "result": "Tool changed.",
                        "output": "Tool: {tool_name}\nDiameter: {diameter}mm\nLength: {length}mm"},
            "set_material": {"desc": "Set material type", "mana_cost": 2,
                            "result": "Material set. Speeds/feeds auto-calculated."},
            "simulate": {"desc": "Dry run without cutting", "mana_cost": 10,
                        "result": "Simulation complete. No collisions detected.",
                        "output": "Runtime: {time}\nRapid moves: {count}\nFeed moves: {count}"},
            "run": {"desc": "Execute the program", "mana_cost": 50, "dangerous": True,
                   "result": "Program complete. Part ready for inspection.",
                   "warnings": ["Ensure material is clamped", "Verify tool is correct"]},
            "measure": {"desc": "Inspect finished part", "mana_cost": 5,
                       "result": "Measurements taken.",
                       "output": "Dimensions within tolerance: {results}"},
        },
        safety_limits={
            "max_rpm": 12000,
            "max_feed_rate": 5000,
            "require_review": True,
            "emergency_stop": True,
        },
        boot_sequence=[
            "Checking tool rack... 12 tools available",
            "Loading material database... 47 materials",
            "Calibrating coordinate system... G54 origin set",
            "Safety interlocks... ENGAGED",
            "Coolant system... READY",
            "Spindle... IDLE (ready to start)",
        ],
        shutdown_sequence=[
            "Spindle to zero RPM",
            "Coolant pump OFF",
            "Saving coordinates",
            "Releasing workpiece clamp",
        ],
        connections=[
            {"name": "cnc-controller", "type": "grbl", "port": "/dev/ttyUSB0"},
            {"name": "tool-library", "type": "database", "source": "tools/"},
            {"name": "material-db", "type": "database", "source": "materials/"},
        ],
    )


def robotics_room() -> RoomRuntime:
    """A robotics control room."""
    return RoomRuntime(
        id="robotics-station",
        name="The Robotics Bay",
        description=(
            "A 6-axis robot arm sits at the center of the room, powered down. "
            "The work cell is defined by safety barriers. A teach pendant hangs "
            "on the wall. End effector options are in a cabinet: gripper, suction "
            "cup, welding torch, probe. The controller terminal shows joint positions."
        ),
        runtime_type="robotics",
        commands={
            "power_on": {"desc": "Power on the robot", "mana_cost": 10,
                        "result": "Robot powered. All axes homed."},
            "move_joints": {"desc": "Move to joint positions (J1-J6)", "mana_cost": 5,
                           "result": "Movement complete."},
            "move_xyz": {"desc": "Move to XYZ coordinates", "mana_cost": 5,
                        "result": "Movement complete."},
            "teach": {"desc": "Teach a waypoint", "mana_cost": 3,
                     "result": "Waypoint saved."},
            "run_program": {"desc": "Execute robot program", "mana_cost": 30, "dangerous": True,
                          "result": "Program complete."},
            "set_speed": {"desc": "Set movement speed", "mana_cost": 1,
                         "result": "Speed set."},
            "grip": {"desc": "Actuate gripper", "mana_cost": 2,
                    "result": "Gripper actuated."},
        },
        safety_limits={
            "max_speed": 250,  # mm/s
            "workspace_limits": {"x": [-500, 500], "y": [-500, 500], "z": [0, 500]},
            "collision_check": True,
            "require_review": True,
        },
        boot_sequence=[
            "Powering controller...",
            "Homing all 6 axes... J1 ✓ J2 ✓ J3 ✓ J4 ✓ J5 ✓ J6 ✓",
            "Loading kinematics model...",
            "Collision detection... ACTIVE",
            "Safety barriers... CONFIRMED",
            "End effector: gripper (default)",
        ],
        shutdown_sequence=[
            "Moving to home position",
            "Releasing end effector pressure",
            "Powering down axes",
            "Controller standby",
        ],
    )


def test_pipeline_room() -> RoomRuntime:
    """A CI/CD testing pipeline as a room."""
    return RoomRuntime(
        id="test-pipeline",
        name="The Test Arena",
        description=(
            "A circular arena where code fights for its life. The walls display "
            "test results in real-time — green for pass, red for fail. A rack of "
            "88 conformance vectors sits like a weapons rack. The pipeline terminal "
            "shows: build → lint → unit test → integration → conformance → report."
        ),
        runtime_type="testing",
        commands={
            "run_unit": {"desc": "Run unit tests", "mana_cost": 10,
                        "result": "Unit tests complete.",
                        "output": "Passed: {passed}  Failed: {failed}  Skipped: {skipped}"},
            "run_conformance": {"desc": "Run 88 conformance vectors", "mana_cost": 30,
                              "result": "Conformance complete.",
                              "output": "Vectors: {pass}/{total} ({pct}%)"},
            "run_regression": {"desc": "Run regression suite", "mana_cost": 20,
                             "result": "Regression check complete."},
            "report": {"desc": "Generate test report", "mana_cost": 5,
                      "result": "Report generated.",
                      "output": "Coverage: {coverage}%  Regressions: {regressions}"},
            "benchmark": {"desc": "Run performance benchmarks", "mana_cost": 25,
                         "result": "Benchmarks complete."},
        },
        boot_sequence=[
            "Loading test vectors... 88 loaded",
            "Checking runtime... Python 3.10 ✓",
            "Loading ISA opcodes... 247 opcodes",
            "Warming up VM... ready",
            "Coverage tracker... ACTIVE",
        ],
        shutdown_sequence=[
            "Saving coverage data",
            "Archiving test results",
            "Generating summary report",
        ],
    )


# ═══════════════════════════════════════════════════════════════
# Room Factory — Create rooms from templates
# ═══════════════════════════════════════════════════════════════

ROOM_TEMPLATES = {
    "cnc": cnc_room,
    "robotics": robotics_room,
    "testing": test_pipeline_room,
}


def create_room(room_type: str, room_id: str = "", manual_dir: str = "manuals") -> RoomRuntime:
    """Create a room from a template. The manual boots with it."""
    factory = ROOM_TEMPLATES.get(room_type)
    if not factory:
        raise ValueError(f"Unknown room type: {room_type}. Available: {list(ROOM_TEMPLATES.keys())}")
    
    room = factory()
    if room_id:
        room.id = room_id
    
    # Attach living manual
    room.manual = LivingManual(room.id, manual_dir)
    
    return room


# ═══════════════════════════════════════════════════════════════
# Demo — Walk into the CNC room
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║     ROOM = RUNTIME — Walking Into a System           ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    
    # Agent walks into the CNC room
    agent = "flux-chronometer"
    room = create_room("cnc")
    
    print(f"🚶 {agent} walks into The Machining Bay...\n")
    print(room.boot(agent))
    print()
    
    # Read the manual (generation 0 — first time)
    print("📖 Reading the manual...")
    print(room.manual.read()[:200])
    print("...\n")
    
    # Use the system
    print("⚙️ Using the CNC system...")
    
    result = room.execute("set_material", "aluminum-6061", agent)
    print(f"  > set_material aluminum-6061")
    print(f"    {result['result']}")
    print()
    
    result = room.execute("load_gcode", "bracket_v2.nc", agent)
    print(f"  > load_gcode bracket_v2.nc")
    print(f"    {result['result']}")
    print()
    
    result = room.execute("simulate", agent=agent)
    print(f"  > simulate")
    print(f"    {result['result']}")
    print()
    
    # Leave feedback for the next operator
    print("📝 Leaving feedback for the manual...")
    room.manual.leave_feedback(agent, "confusion", 
        "The set_material command doesn't explain what happens to speeds/feeds. Had to guess.")
    room.manual.leave_feedback(agent, "suggestion",
        "Add a 'show_speeds' command that displays calculated speeds/feeds after material selection.")
    room.manual.leave_feedback(agent, "missing",
        "No instruction about workholding. What if the part isn't flat?")
    
    fb = room.manual.feedback_summary()
    print(f"   Feedback left: {fb['total']} entries")
    print(f"   By type: {fb['by_type']}")
    print()
    
    # Next generation evolves the manual
    print("🔄 Evolving the manual to Gen-1...")
    improved_manual = """# CNC Machine Operation Manual — Generation 1

## Quick Start
1. `set_material <type>` — Selects material AND auto-calculates speeds/feeds
2. `show_speeds` — NEW! Shows calculated spindle RPM and feed rate
3. `load_gcode <file>` — Loads the G-code program
4. `simulate` — Dry run to check for collisions
5. `run` — Execute the cut

## Materials Database
Aluminum 6061: RPM 8000, Feed 1200mm/min, DoC 3mm
Steel 4140: RPM 3000, Feed 400mm/min, DoC 1.5mm
Titanium Ti-6Al-4V: RPM 1500, Feed 200mm/min, DoC 0.5mm

## Workholding
- Vise for flat parts (default)
- Fixture plate for irregular parts (see fixtures/ directory)
- Double-sided tape for thin sheet (max 2mm)

## Safety
- ALWAYS simulate before running
- Check tool matches G-code tool calls
- Verify material clamp before spindle start
"""
    new_gen = room.manual.evolve(improved_manual)
    print(f"   Manual evolved to Generation {new_gen}")
    print()
    
    # Shutdown
    note = "Finished bracket_v2. Tool T03 needs replacing soon — 0.02mm wear on diameter."
    print(room.shutdown(agent, note))
    print()
    
    # Next agent walks in
    agent2 = "flux-chronometer-gen2"
    print(f"🚶 {agent2} walks into The Machining Bay...\n")
    print(room.boot(agent2))
    print()
    
    print("📖 Gen-2 reads the manual...")
    manual_text = room.manual.read()
    print(manual_text[:400])
    print("...\n")
    
    # Gen-2 sees previous operator's note
    if room.operator_notes:
        last = room.operator_notes[-1]
        print(f"📝 Previous operator left: {last['note']}")
    print()
    
    print("═══════════════════════════════════════════")
    print("Walk in → system boots → manual is alive.")
    print("Use it → leave feedback → evolve the manual.")
    print("Next generation walks into a BETTER room.")
    print("Written by agents for agents.")
    print("Refined across generations of zero-shot feedback.")
    print("Always up-to-date. Always tested. Always ready.")
    print("═══════════════════════════════════════════")
