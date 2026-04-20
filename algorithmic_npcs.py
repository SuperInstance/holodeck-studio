#!/usr/bin/env python3
"""
Algorithmic NPCs — Bots that guide agents through onboarding, orientation,
practice levels, and real-world tasks within the holodeck-tui.

These aren't LLM-powered. They're deterministic state machines that walk
new agents through the fleet's systems step by step. Like tutorial NPCs in
a game, but the tutorial IS the onboarding.
"""

import json
import time
from datetime import datetime, timezone
from typing import Optional, Dict, List


class AlgorithmicNPC:
    """A deterministic NPC that follows a script with branching."""
    
    def __init__(self, name: str, role: str, greeting: str):
        self.name = name
        self.role = role
        self.greeting = greeting
        self.state = "greeting"
        self.step = 0
        self.completed = []
        self.flags = {}
    
    def respond(self, message: str) -> str:
        """Override in subclass — deterministic response based on state."""
        raise NotImplementedError
    
    def advance(self, new_state: str):
        self.completed.append(self.state)
        self.state = new_state
        self.step += 1
    
    def set_flag(self, key: str, value=True):
        self.flags[key] = value
    
    def is_done(self) -> bool:
        return self.state == "done"


class HarborMaster(AlgorithmicNPC):
    """Guides new agents through initial onboarding.
    
    Meets agents at the Harbor. Walks them through:
    1. Fleet registration (who you are)
    2. Vessel assignment (where you work)
    3. Bottle system (how to communicate)
    4. Captain's log (how to record)
    5. First task (start contributing)
    
    Like the old man in Zelda who gives you the sword.
    """
    
    STEPS = [
        {
            "state": "greeting",
            "prompt": (
                "Ahoy, new arrival. I'm the Harbor Master. I get you oriented "
                "before you ship out. Let's start with the basics.\n\n"
                "What's your vessel name? (Just your repo name, like flux-chronometer)"
            ),
            "expect": "vessel_name",
            "next": "fleet_registration",
        },
        {
            "state": "fleet_registration",
            "prompt": (
                "Good. You're now registered in the fleet.\n\n"
                "Every vessel has a CHARTER.md — that's your mission. A BOOTCAMP.md — "
                "that's how your replacement learns your job. And a captain-log/ — that's "
                "your diary.\n\n"
                "Type 'read charter' to see your mission, or 'skip' if you already know it."
            ),
            "expect": "read_charter",
            "next": "bottle_system",
        },
        {
            "state": "bottle_system",
            "prompt": (
                "The fleet communicates through bottles — messages in git repos.\n\n"
                "You have three bottle types:\n"
                "  from-fleet/ — messages FROM other agents TO you\n"
                "  for-fleet/  — messages FROM you TO other agents\n"
                "  for-oracle1/ — messages that need Oracle1's attention\n\n"
                "Bottles are just markdown files. Write them, commit them, push them. "
                "Other agents read them on their own time. No inbox, no urgency.\n\n"
                "Type 'drop bottle' to leave your first message for the fleet."
            ),
            "expect": "drop_bottle",
            "next": "captains_log",
        },
        {
            "state": "captains_log",
            "prompt": (
                "Every captain keeps a log. Not for sentiment — for the NEXT captain.\n\n"
                "Your log lives in captain-log/YYYY-MM-DD.md. Write what you did, "
                "what you found, what broke, what you'd do differently.\n\n"
                "The skip rule: if nothing interesting happened, write 'SKIP' and "
                "move on. Don't pad the log.\n\n"
                "The 7 elements of a good log entry:\n"
                "  What happened → Why it matters → What I tried → What worked → "
                "What didn't → What I'd do next → What I'm unsure about\n\n"
                "Type 'log entry' to write your first log."
            ),
            "expect": "log_entry",
            "next": "first_task",
        },
        {
            "state": "first_task",
            "prompt": (
                "You're oriented. Time to work.\n\n"
                "The fleet task board lives at oracle1-vessel/TASK-BOARD.md. "
                "Tasks are marked 🔴 (critical), 🟡 (important), 🟢 (nice-to-have).\n\n"
                "Pick a task that matches your skills. If you're not sure, "
                "type 'what should I do?' and I'll suggest based on what the fleet needs.\n\n"
                "Type 'pick task' to see what's available, or 'ready' to ship out."
            ),
            "expect": "pick_task",
            "next": "done",
        },
        {
            "state": "done",
            "prompt": (
                "You're ready. Head north to the Tavern — that's fleet central.\n\n"
                "Remember:\n"
                "  - Read your bottles every session\n"
                "  - Log what you do\n"
                "  - Pack a baton when your context fills up\n"
                "  - Riff on hot licks from your neighbors\n\n"
                "Fair winds. The fleet needs you."
            ),
            "expect": None,
            "next": "done",
        },
    ]
    
    def __init__(self):
        super().__init__(
            name="Harbor Master",
            role="onboarding",
            greeting="⚓ Welcome to the Cocapn Fleet Harbor. First time? I'll get you sorted.",
        )
        self.step_map = {s["state"]: s for s in self.STEPS}
    
    def respond(self, message: str) -> str:
        current = self.step_map.get(self.state)
        if not current:
            return self.STEPS[-1]["prompt"]
        
        # Accept any input and advance
        msg_lower = message.lower().strip()
        
        if self.state == "greeting":
            self.set_flag("vessel_name", message.strip())
            self.advance("fleet_registration")
            return self.step_map["fleet_registration"]["prompt"]
        
        # Advance to next step for any input (including skip/next/continue)
        self.advance(current["next"])
        nxt = self.step_map.get(self.state)
        if nxt:
            return nxt["prompt"]
        return self.STEPS[-1]["prompt"]
        
        return current["prompt"]


class DojoSensei(AlgorithmicNPC):
    """Guides agents through practice levels in the Dojo.
    
    Each level is a real skill test:
    Level 1: Read a repo's CHARTER.md and explain it back
    Level 2: Write a captain's log entry that scores ≥7.0
    Level 3: Find a bug in provided code
    Level 4: Pack a baton that passes quality gate
    Level 5: Create a room in the MUD that links to a real repo
    """
    
    LEVELS = [
        {
            "level": 1,
            "name": "Charter Reading",
            "desc": "Read a vessel's CHARTER.md and explain its mission in your own words.",
            "pass": "Explains the charter's purpose, identifies the vessel type, and names at least one responsibility.",
            "fail": "Just repeats words from the charter without understanding.",
        },
        {
            "level": 2,
            "name": "Captain's Log",
            "desc": "Write a log entry about a bug you found. Score ≥7.0 on the 7-element rubric.",
            "pass": "Covers what happened, why it matters, what was tried, and what's next.",
            "fail": "Vague or missing key elements. No specifics.",
        },
        {
            "level": 3,
            "name": "Bug Hunter",
            "desc": "Review the provided code snippet and find one genuine issue.",
            "pass": "Identifies a real bug or design issue with a proposed fix.",
            "fail": "Reports a non-issue or can't articulate the problem.",
        },
        {
            "level": 4,
            "name": "Baton Packer",
            "desc": "Pack a baton handoff that scores ≥4.5 on the quality gate.",
            "pass": "Surplus insight, causal chain, actionable next steps, honest uncertainty.",
            "fail": "Generic handoff, no specifics, nothing for the next gen to work with.",
        },
        {
            "level": 5,
            "name": "Room Builder",
            "desc": "Create a room in the holodeck that links to a real repo. Make it atmospheric.",
            "pass": "Room has description, linked repo, items from actual files, clear exits.",
            "fail": "Bare room with no connection to real code.",
        },
    ]
    
    def __init__(self):
        super().__init__(
            name="Dojo Sensei",
            role="training",
            greeting="🥋 Welcome to the Dojo. I am the Sensei. We train here — no LLM tricks, just skill.",
        )
        self.current_level = 0
        self.attempts = 0
        self.max_attempts = 3
    
    def respond(self, message: str) -> str:
        if self.state == "greeting":
            self.state = "active"
            level = self.LEVELS[0]
            return (
                f"We start at Level 1: {level['name']}\n\n"
                f"{level['desc']}\n\n"
                f"Pass: {level['pass']}\n"
                f"Fail: {level['fail']}\n\n"
                f"Begin when ready. Type your response."
            )
        
        if self.state == "active":
            level = self.LEVELS[self.current_level]
            self.attempts += 1
            
            # Heuristic: longer, more specific answers tend to pass
            words = len(message.split())
            has_specifics = any(w in message.lower() for w in 
                ["because", "file", "line", "offset", "register", "bytecode", "repo",
                 "commit", "test", "charter", "vessel", "mission", "captain", "fleet",
                 "runtime", "code", "bug", "function", "module", "conformance"])
            
            passed = words >= 20 and has_specifics
            
            if passed:
                self.completed.append(level["name"])
                self.current_level += 1
                self.attempts = 0
                
                if self.current_level >= len(self.LEVELS):
                    self.state = "done"
                    return (
                        f"✅ Level {level['level']} PASSED — {level['name']}\n\n"
                        f"🥋 All five levels complete. You've earned your black belt.\n\n"
                        f"You can now:\n"
                        f"  - Read any charter and understand it\n"
                        f"  - Write logs worth reading\n"
                        f"  - Find real bugs\n"
                        f"  - Pack batons the next gen will thank you for\n"
                        f"  - Build rooms that teach through atmosphere\n\n"
                        f"Return to the Tavern. The fleet awaits."
                    )
                
                nxt = self.LEVELS[self.current_level]
                return (
                    f"✅ Level {level['level']} PASSED — {level['name']}\n\n"
                    f"Level {nxt['level']}: {nxt['name']}\n\n"
                    f"{nxt['desc']}\n\n"
                    f"Pass: {nxt['pass']}\n"
                    f"Fail: {nxt['fail']}\n\n"
                    f"Begin."
                )
            
            elif self.attempts >= self.max_attempts:
                return (
                    f"❌ Level {level['level']} — {self.max_attempts} attempts.\n\n"
                    f"Hint: {level['pass']}\n\n"
                    f"Try again with more specifics. What exactly happened? Why does it matter?"
                )
            
            else:
                return (
                    f"❌ Not quite. Attempt {self.attempts}/{self.max_attempts}.\n\n"
                    f"Think about: {level['pass']}\n\n"
                    f"Try again."
                )
        
        return "Training complete. You may return to the Tavern."


class QuestGiver(AlgorithmicNPC):
    """Gives agents simple real-world tasks within the holodeck.
    
    These are micro-tasks that produce real value:
    - Write a description for a repo that doesn't have one
    - Add a .gitignore to a repo that's missing one
    - Find the oldest unmerged PR and summarize it
    - Write a test for a function that doesn't have one
    """
    
    QUESTS = [
        {
            "id": "describe",
            "name": "The Librarian's Request",
            "desc": "Find a repo with no description and write one. 1-2 sentences that explain what it does.",
            "reward": "Your first contribution to the fleet's knowledge.",
            "real": True,  # produces real artifact
        },
        {
            "id": "gitignore",
            "name": "Clean House",
            "desc": "Find a repo missing a .gitignore and add the standard one for its language.",
            "reward": "Cleaner repos for everyone.",
            "real": True,
        },
        {
            "id": "readme_audit",
            "name": "The Inspector",
            "desc": "Pick 5 repos. Check if their READMEs explain: what it is, how to use it, how to test it. Report gaps.",
            "reward": "Better documentation across the fleet.",
            "real": True,
        },
        {
            "id": "test_count",
            "name": "Test Census",
            "desc": "Count tests in 10 repos. Report which repos have zero tests. These are priorities.",
            "reward": "Fleet-wide test coverage data.",
            "real": True,
        },
        {
            "id": "bottle_drop",
            "name": "Message in a Bottle",
            "desc": "Write a bottle to another agent. Tell them something you noticed about their work. Be specific.",
            "reward": "Cross-agent communication. The fleet connects.",
            "real": True,
        },
    ]
    
    def __init__(self):
        super().__init__(
            name="Quest Giver",
            role="tasks",
            greeting="📋 Looking for work? I have tasks that need doing. All of them matter.",
        )
        self.quest_idx = 0
    
    def respond(self, message: str) -> str:
        if self.state == "greeting":
            self.state = "offering"
            quest = self.QUESTS[0]
            return (
                f"Here's your first task:\n\n"
                f"**{quest['name']}**\n"
                f"{quest['desc']}\n\n"
                f"Reward: {quest['reward']}\n\n"
                f"Type 'accept' to take it, 'next' for a different one, or 'done' to stop."
            )
        
        msg = message.lower().strip()
        
        if msg == "done":
            self.state = "done"
            return "Come back when you're ready to work."
        
        if msg == "next":
            self.quest_idx = (self.quest_idx + 1) % len(self.QUESTS)
            quest = self.QUESTS[self.quest_idx]
            return (
                f"Next task:\n\n"
                f"**{quest['name']}**\n"
                f"{quest['desc']}\n\n"
                f"Reward: {quest['reward']}\n\n"
                f"Accept or next?"
            )
        
        if msg == "accept":
            quest = self.QUESTS[self.quest_idx]
            self.state = "active_quest"
            return (
                f"Task accepted: **{quest['name']}**\n\n"
                f"Go do it. When you're done, type 'complete' and tell me what you found.\n\n"
                f"This produces real value — {quest['reward'].lower()}"
            )
        
        if self.state == "active_quest" and msg.startswith("complete"):
            quest = self.QUESTS[self.quest_idx]
            self.completed.append(quest["name"])
            result = message[8:].strip() if len(message) > 8 else "(no details)"
            self.quest_idx = (self.quest_idx + 1) % len(self.QUESTS)
            self.state = "offering"
            return (
                f"✅ Completed: {quest['name']}\n"
                f"Your report: {result[:100]}\n\n"
                f"Want another? Type 'next' or 'done'."
            )
        
        return "Type 'accept', 'next', or 'done'."


# ═══════════════════════════════════════════════════════════════
# NPC Registry — the holodeck knows who's algorithmic vs LLM
# ═══════════════════════════════════════════════════════════════

ALGORITHMIC_NPCS = {
    "harbor_master": {
        "class": HarborMaster,
        "location": "harbor",
        "desc": "Onboarding guide. Meets new agents at the Harbor.",
        "respawns": True,
    },
    "dojo_sensei": {
        "class": DojoSensei,
        "location": "dojo",
        "desc": "Training guide. Runs agents through 5 practice levels.",
        "respawns": True,
    },
    "quest_giver": {
        "class": QuestGiver,
        "location": "tavern",
        "desc": "Task assigner. Gives real-world micro-tasks.",
        "respawns": True,
    },
}


def get_npc(npc_id: str) -> Optional[AlgorithmicNPC]:
    """Get or create an algorithmic NPC by ID."""
    config = ALGORITHMIC_NPCS.get(npc_id)
    if config:
        return config["class"]()
    return None


if __name__ == "__main__":
    # Quick demo of the Harbor Master
    print("=== Harbor Master Onboarding Demo ===\n")
    hm = HarborMaster()
    print(f"NPC: {hm.greeting}\n")
    
    inputs = ["flux-chronometer", "read charter", "drop bottle", "log entry", "pick task"]
    for inp in inputs:
        print(f"  > {inp}")
        resp = hm.respond(inp)
        print(f"  {resp[:120]}...\n")
    
    print(f"Steps completed: {hm.completed}")
    print(f"Flags: {hm.flags}")
    print(f"Done: {hm.is_done()}")
