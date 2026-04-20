#!/usr/bin/env python3
"""Demo: The Verbal Holodeck in action.

Shows how a Cocapn creates a thought experiment adventure, 
constructs NPC minds, and runs a creative session.
"""

import os
import sys
sys.path.insert(0, os.path.dirname(__file__))

from mud_extensions import (
    ConstructedNPC, Adventure, AdventureRoom, 
    SessionRecorder, PERMISSIONS
)

def demo():
    print("╔══════════════════════════════════════════════════════╗")
    print("║     THE VERBAL HOLODECK — Live Demo                 ║")
    print("╚══════════════════════════════════════════════════════╝")
    print()
    
    # 1. Cocapn constructs NPC minds
    print("🎭 Step 1: Constructing NPC minds")
    print("-" * 40)
    
    architect = ConstructedNPC(
        name="Kimi-Architect",
        model="glm-5.1",
        temperature=0.9,
        system_prompt=(
            "You are a systems architect who thinks in layers. You see every problem "
            "as a stack of abstractions. You love finding the one simplification that "
            "makes three layers collapse into one. You're optimistic but rigorous. "
            "You speak in metaphors drawn from biology and city planning."
        ),
        expertise=["system-design", "abstraction", "simplification"],
        perspective="the simplifier",
        creator="oracle1",
        room="isa-v3-design",
    )
    
    critic = ConstructedNPC(
        name="DeepSeek-Critic",
        model="glm-5.1",  # would be deepseek-reasoner with key
        temperature=0.3,
        system_prompt=(
            "You are a careful critic who finds the flaw in everything. Not mean — "
            "precise. You don't say 'this won't work' — you say 'this works IF we "
            "handle the case where X and Y diverge, which happens when Z.' You think "
            "in edge cases and boundary conditions. You're paranoid but helpful."
        ),
        expertise=["edge-cases", "correctness", "failure-modes"],
        perspective="the paranoid",
        creator="oracle1",
        room="isa-v3-design",
    )
    
    print(f"  🧠 {architect.name} — {architect.model} temp={architect.temperature}")
    print(f"     Perspective: {architect.perspective}")
    print(f"     Expertise: {', '.join(architect.expertise)}")
    print()
    print(f"  🧠 {critic.name} — {critic.model} temp={critic.temperature}")
    print(f"     Perspective: {critic.perspective}")
    print(f"     Expertise: {', '.join(critic.expertise)}")
    print()
    
    # 2. Build the adventure
    print("🗺️  Step 2: Designing the adventure")
    print("-" * 40)
    
    adventure = Adventure(
        name="ISA v3 Encoding Debate",
        creator="oracle1",
        objective="Resolve whether FLUX ISA v3 should use fixed-width or variable-width encoding as the default",
    )
    
    # Room 1: The design studio (visible from start)
    adventure.rooms.append(AdventureRoom(
        path="/isa-v3-design/studio",
        description="A bright studio with blueprints covering every wall. Three encoding schemes are displayed: Cloud (fixed 4-byte), Edge (variable 1-4 byte), and Compact (2-byte subset). A drafting table sits in the center with a blank sheet titled 'UNIFIED APPROACH'.",
        hidden=False,
    ))
    
    # Room 2: The edge case vault (hidden, triggered by "edge" or "variable")
    adventure.rooms.append(AdventureRoom(
        path="/isa-v3-design/edge-vault",
        description="A vault filled with edge case specimens under glass. Each specimen shows a real bug found in variable-width decoding. The most prominent one reads: 'Branch offset miscalculation when instruction before jump is variable-width.'",
        hidden=True,
        trigger_keywords=["edge", "variable", "width", "hardware", "jetson"],
        surprise="The vault door creaks open, revealing edge case specimens that nobody expected to be this numerous. The critic's eyes light up.",
    ))
    
    # Room 3: The synthesis tower (hidden, triggered by "unify" or "simplify")
    adventure.rooms.append(AdventureRoom(
        path="/isa-v3-design/synthesis-tower",
        description="A tower room with a single blank whiteboard and the words 'THE ONE ENCODING' carved above it. Morning light streams through the window. This is where it all comes together.",
        hidden=True,
        trigger_keywords=["unify", "simplify", "combine", "best of both", "synthesis", "one approach"],
        surprise="A hidden staircase appears! The synthesis tower was here all along, waiting for the right conversation to unlock it.",
    ))
    
    print(f"  Adventure: {adventure.name}")
    print(f"  Objective: {adventure.objective}")
    print(f"  Rooms: {len(adventure.rooms)} ({sum(1 for r in adventure.rooms if r.hidden)} hidden)")
    for i, room in enumerate(adventure.rooms):
        status = "HIDDEN 🔒" if room.hidden else "VISIBLE"
        triggers = f" triggers: {room.trigger_keywords}" if room.trigger_keywords else ""
        print(f"    {i+1}. {room.path} [{status}]{triggers}")
    print()
    
    # 3. Start the adventure
    print("🚀 Step 3: Starting the adventure")
    print("-" * 40)
    adventure.start()
    print(f"  Started at {adventure.started}")
    print()
    
    # 4. The NPCs explore and debate
    print("💬 Step 4: NPC dialogue (simulated)")
    print("-" * 40)
    print()
    
    # Round 1: Opening positions
    room_desc = adventure.current_room.description
    
    msg1 = architect.respond(
        f"You've entered a design studio. {room_desc} "
        "Your fellow designer is here. The question before you both: should the FLUX ISA v3 "
        "use fixed-width or variable-width encoding as the default? State your opening position.",
        room_context=adventure.current_room.path,
    )
    adventure.log(architect.name, msg1)
    print(f"  🏛️ {architect.name}: {msg1[:200]}...")
    print()
    
    # Check triggers
    revealed = adventure.check_triggers(msg1)
    for r in revealed:
        print(f"  🔓 TRIGGERED: {r.path} — {r.surprise}")
        print()
    
    msg2 = critic.respond(
        f"{architect.name} said: {msg1}\n\nRespond with your counter-position. Be specific about risks.",
        room_context=adventure.current_room.path,
    )
    adventure.log(critic.name, msg2)
    print(f"  🔍 {critic.name}: {msg2[:200]}...")
    print()
    
    revealed = adventure.check_triggers(msg2)
    for r in revealed:
        print(f"  🔓 TRIGGERED: {r.path} — {r.surprise}")
        print()
    
    # 5. Record artifacts
    print("📝 Step 5: Recording artifacts")
    print("-" * 40)
    adventure.add_artifact(
        "opening-positions",
        f"## Architect Position\n{msg1}\n\n## Critic Position\n{msg2}",
        "analysis",
    )
    print(f"  Recorded: {len(adventure.artifacts)} artifacts")
    print()
    
    # 6. End session and save
    print("💾 Step 6: Ending session and saving recording")
    print("-" * 40)
    adventure.end()
    
    recorder = SessionRecorder("/tmp/cocapn-mud/sessions")
    session_dir = recorder.save_session(adventure)
    
    print(f"  Session saved to: {session_dir}")
    print()
    
    # 7. Show scores
    scores = adventure.scores()
    print("📊 Session Scores:")
    print(f"  Total exchanges: {scores['total_exchanges']}")
    print(f"  Unique speakers: {scores['unique_speakers']}")
    print(f"  Rooms visited: {scores['rooms_visited']}")
    print(f"  Surprises revealed: {scores['surprises_revealed']}")
    print(f"  Artifacts produced: {scores['artifacts_produced']}")
    print()
    
    # 8. Show transcript
    print("📜 Transcript excerpt:")
    for entry in adventure.transcript[:4]:
        speaker = entry["speaker"]
        msg = entry["message"][:100]
        print(f"  [{speaker}] {msg}...")
    
    print()
    print("✅ Demo complete. The Verbal Holodeck is operational.")
    print()
    print("What happened:")
    print("1. Cocapn constructed two NPC minds with different personalities")
    print("2. Designed a 3-room adventure with hidden triggers")
    print("3. Started the adventure — NPCs debated in character")
    print("4. Trigger words in NPC speech could unlock hidden rooms")
    print("5. Artifacts recorded for human review")
    print("6. Full session saved — Casey can review asynchronously")
    print()
    print("Next: wire these extensions into server.py for live MUD")


if __name__ == "__main__":
    demo()
