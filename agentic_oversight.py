#!/usr/bin/env python3
"""
Agentic Oversight — Combat-length monitoring with evolving scripts.

The pattern:
1. Trigger a large operation (deploy, migration, batch job, hardware run)
2. Agent enters "combat" — fast-iterating oversight crons
3. Each tick: summarize what changed, ask "adjust anything?"
4. Agent's job: make the script smarter so it needs LESS nudging next time
5. Over iterations, the script evolves toward autonomy
6. Human can walk into the room, read what the A2A sees, tap the feeds
7. Human can demonstrate from inside — vibe code a refactor, tell the agent
   how to edit the onboarding — because they're a fellow player in the room

This IS decomposition. This IS CraftMind. This IS agent-first design.
The agent's first-person perspective of the application ecosystem is readable
by a non-coder who can verify, demonstrate, and iterate alongside.
"""

import json
import os
import time
import hashlib
from datetime import datetime, timezone
from typing import Dict, List, Optional
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════
# Oversight Tick — The combat-length cron cycle
# ═══════════════════════════════════════════════════════════════

@dataclass
class OversightTick:
    """One tick of agentic oversight. Like a combat round.
    
    Summarizes what changed since last tick.
    Asks: do you want to adjust anything before next summary?
    Records adjustments for script evolution.
    """
    tick_num: int
    timestamp: str
    changes: List[dict]  # what changed since last tick
    gauges: Dict[str, float]  # current system state
    agent_action: str = ""  # what the agent decided
    human_input: str = ""  # what the human said (if anything)
    script_version: int = 1
    nudges_needed: int = 0  # how much human help was required
    autonomy_score: float = 1.0  # 1.0 = fully autonomous, 0.0 = manual
    
    def to_dict(self):
        return {
            "tick": self.tick_num, "timestamp": self.timestamp,
            "changes": self.changes, "gauges": self.gauges,
            "agent_action": self.agent_action, "human_input": self.human_input,
            "script_version": self.script_version, "nudges_needed": self.nudges_needed,
            "autonomy": self.autonomy_score,
        }


class OversightSession:
    """A combat-length session of agentic oversight.
    
    Like a MUD combat encounter but for monitoring complex systems.
    The agent watches, summarizes, adjusts. The human can step in
    at any tick to demonstrate or redirect.
    
    Over time, the script evolves toward needing fewer nudges.
    """
    
    def __init__(self, operation_name: str, agent: str, 
                 tick_interval: int = 30):
        self.operation = operation_name
        self.agent = agent
        self.tick_interval = tick_interval  # seconds between summaries
        self.ticks: List[OversightTick] = []
        self.script = EvolvingScript(operation_name, agent)
        self.started = datetime.now(timezone.utc).isoformat()
        self.ended = None
        self.total_nudges = 0
    
    def tick(self, changes: List[dict], gauges: Dict[str, float],
             human_input: str = "") -> OversightTick:
        """Run one oversight tick."""
        tick = OversightTick(
            tick_num=len(self.ticks) + 1,
            timestamp=datetime.now(timezone.utc).isoformat(),
            changes=changes,
            gauges=gauges,
            script_version=self.script.version,
            human_input=human_input,
        )
        
        # Agent evaluates the situation using current script
        tick.agent_action = self.script.evaluate(changes, gauges)
        
        # If human provided input, that's a nudge
        if human_input:
            tick.nudges_needed = 1
            self.total_nudges += 1
            # Human demonstrated something — evolve the script
            self.script.learn(human_input, tick.agent_action, changes, gauges)
        
        # Calculate autonomy score
        if self.ticks:
            total_ticks = len(self.ticks) + 1
            tick.autonomy_score = round(1.0 - (self.total_nudges / total_ticks), 2)
        
        self.ticks.append(tick)
        return tick
    
    def end_session(self) -> dict:
        """End the oversight session and generate the evolution report."""
        self.ended = datetime.now(timezone.utc).isoformat()
        
        total = len(self.ticks)
        nudged = sum(1 for t in self.ticks if t.nudges_needed > 0)
        autonomous = total - nudged
        
        return {
            "operation": self.operation,
            "agent": self.agent,
            "ticks": total,
            "autonomous_ticks": autonomous,
            "nudged_ticks": nudged,
            "final_autonomy": self.ticks[-1].autonomy_score if self.ticks else 1.0,
            "script_evolution": {
                "initial_version": 1,
                "final_version": self.script.version,
                "rules_added": len(self.script.added_during_session),
                "rules_adapted": len(self.script.adapted_during_session),
            },
            "duration_ticks": total,
        }
    
    def generate_perspective(self) -> str:
        """Generate the agent's first-person perspective.
        
        This is what a human reads to understand what the A2A sees.
        Written in plain language — a non-coder can understand it.
        """
        lines = [
            f"# Agent Perspective: {self.operation}",
            f"**Agent:** {self.agent}",
            f"**Session:** {len(self.ticks)} ticks",
            f"**Autonomy:** {self.ticks[-1].autonomy_score:.0%}" if self.ticks else "",
            "",
            "## What I See (First-Person)",
            "",
        ]
        
        if self.ticks:
            latest = self.ticks[-1]
            lines.append(f"I've been watching **{self.operation}** for {latest.tick_num} check-ins.")
            lines.append("")
            
            # Changes in plain language
            if latest.changes:
                lines.append("### What Changed Since Last Check")
                for change in latest.changes:
                    lines.append(f"- {change.get('desc', str(change))}")
                lines.append("")
            
            # Gauges in plain language
            if latest.gauges:
                lines.append("### How Things Look Right Now")
                for name, value in latest.gauges.items():
                    status = "healthy" if value < 0.7 else "elevated" if value < 0.9 else "critical"
                    lines.append(f"- **{name}**: {value:.1%} — {status}")
                lines.append("")
            
            # What the agent is doing
            lines.append(f"### What I'm Doing About It")
            lines.append(f"{latest.agent_action}")
            lines.append("")
            
            # How autonomous it is
            if latest.nudges_needed:
                lines.append(f"### Human Help This Round")
                lines.append(f"The human said: \"{latest.human_input}\"")
                lines.append(f"I learned from this and updated my script (now v{latest.script_version}).")
            else:
                lines.append(f"### Autonomy")
                lines.append(f"Running on my own this round. Script v{latest.script_version}.")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Evolving Script — Gets smarter with each nudge
# ═══════════════════════════════════════════════════════════════

class EvolvingScript:
    """A script that evolves toward needing less human nudging.
    
    Starts with basic rules. Each time a human provides input,
    the script learns a new rule or adapts an existing one.
    Over iterations, the script handles more situations autonomously.
    
    This IS decomposition — the task gets decomposed into
    increasingly specific rules that handle edge cases the
    human had to catch the first time.
    """
    
    def __init__(self, task_name: str, agent: str):
        self.task_name = task_name
        self.agent = agent
        self.version = 1
        self.rules: List[dict] = []
        self.adaptations: List[dict] = []
        self.added_during_session: List[dict] = []
        self.adapted_during_session: List[dict] = []
        
        # Seed with basic rules
        self._seed_rules()
    
    def _seed_rules(self):
        """Start with basic monitoring rules."""
        self.rules = [
            {"condition": "all gauges normal", "action": "continue monitoring, no action needed",
             "source": "seed", "version": 1},
            {"condition": "any gauge elevated", "action": "flag for attention, increase tick frequency",
             "source": "seed", "version": 1},
            {"condition": "any gauge critical", "action": "alert human immediately, attempt safe fallback",
             "source": "seed", "version": 1},
            {"condition": "no changes detected", "action": "continue monitoring, decrease tick frequency",
             "source": "seed", "version": 1},
        ]
    
    def evaluate(self, changes: List[dict], gauges: Dict[str, float]) -> str:
        """Evaluate the current situation and decide what to do."""
        # Check gauges
        max_gauge = max(gauges.values()) if gauges else 0
        has_changes = len(changes) > 0
        
        if max_gauge > 0.9:
            return self._match_rule("any gauge critical")
        elif max_gauge > 0.7:
            return self._match_rule("any gauge elevated")
        elif not has_changes:
            return self._match_rule("no changes detected")
        else:
            # Check specific change patterns
            for change in changes:
                change_type = change.get("type", "")
                for rule in self.rules:
                    if change_type.lower() in rule["condition"].lower():
                        return rule["action"]
            return self._match_rule("all gauges normal")
    
    def _match_rule(self, condition: str) -> str:
        for rule in reversed(self.rules):  # latest rules first
            if condition.lower() in rule["condition"].lower():
                return rule["action"]
        return "observe and report"
    
    def learn(self, human_input: str, agent_action: str,
              changes: List[dict], gauges: Dict[str, float]):
        """Learn from human input. This is where the script evolves."""
        self.version += 1
        
        # Determine what situation the human was correcting
        situation = self._describe_situation(changes, gauges)
        
        # Was this a new rule or an adaptation?
        existing = self._find_matching_rule(situation)
        
        if existing:
            # Adapt existing rule
            adaptation = {
                "old_action": existing["action"],
                "new_action": human_input,
                "situation": situation,
                "version": self.version,
                "source": "human_demonstration",
            }
            existing["action"] = human_input
            existing["version"] = self.version
            existing["source"] = "evolved"
            self.adaptations.append(adaptation)
            self.adapted_during_session.append(adaptation)
        else:
            # Add new rule
            new_rule = {
                "condition": situation,
                "action": human_input,
                "source": "human_demonstration",
                "version": self.version,
            }
            self.rules.append(new_rule)
            self.added_during_session.append(new_rule)
    
    def _describe_situation(self, changes: List[dict], gauges: Dict[str, float]) -> str:
        """Describe the current situation in plain language."""
        parts = []
        if changes:
            types = set(c.get("type", "unknown") for c in changes)
            parts.append(f"changes: {', '.join(types)}")
        if gauges:
            for name, value in gauges.items():
                if value > 0.5:
                    parts.append(f"{name} at {value:.0%}")
        return "; ".join(parts) if parts else "normal operation"
    
    def _find_matching_rule(self, situation: str) -> Optional[dict]:
        for rule in reversed(self.rules):
            if any(w in rule["condition"].lower() for w in situation.lower().split()):
                return rule
        return None
    
    def generate_readme(self) -> str:
        """Generate a human-readable explanation of what this script does.
        
        A non-coder can read this and understand how the system works.
        """
        lines = [
            f"# {self.task_name} — Oversight Script v{self.version}",
            "",
            "## What This Does",
            f"This script monitors **{self.task_name}** and decides what to do",
            f"when things change. It has {len(self.rules)} rules for handling",
            f"different situations.",
            "",
            "## Rules (What I Do When)",
            "",
        ]
        
        for i, rule in enumerate(self.rules, 1):
            source = "🧬 seeded" if rule.get("source") == "seed" else "👤 human-taught" if rule.get("source") == "human_demonstration" else "🔄 evolved"
            lines.append(f"{i}. **When:** {rule['condition']}")
            lines.append(f"   **I do:** {rule['action']}")
            lines.append(f"   *Learned: v{rule.get('version', 1)} ({source})*")
            lines.append("")
        
        if self.adaptations:
            lines.append("## How This Evolved")
            lines.append("")
            for adapt in self.adaptations:
                lines.append(f"- v{adapt['version']}: When \"{adapt['situation'][:40]}...\"")
                lines.append(f"  Changed from: \"{adapt['old_action'][:50]}\"")
                lines.append(f"  To: \"{adapt['new_action'][:50]}\"")
                lines.append("")
        
        lines.append("---")
        lines.append("*This script gets smarter every time a human demonstrates a correction.*")
        lines.append("*Eventually it handles most situations without help.*")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Human-as-Player — Non-coder demonstrates from inside
# ═══════════════════════════════════════════════════════════════

class HumanPlayer:
    """A human who walks into the room as a fellow player.
    
    They can:
    - Read the agent's first-person perspective
    - Tap the room's feeds (gauges, changes, logs)
    - Read and edit the onboarding (living manual)
    - Demonstrate to the agent by doing something and saying "like this"
    - Vibe-code a refactor (describe what they want in plain language)
    - The agent translates their demonstration into script rules
    
    The human doesn't need to code. They just play alongside the agent.
    """
    
    def __init__(self, name: str):
        self.name = name
        self.demonstrations = []
    
    def demonstrate(self, session: OversightSession, instruction: str) -> str:
        """Demonstrate something to the agent in plain language.
        
        'When the memory gauge goes above 80%, restart the worker process'
        'If the deployment takes more than 5 minutes, check the build logs'
        'When you see a new error type, don't alert me — investigate it yourself first'
        
        The agent translates this into a script rule.
        """
        tick = session.tick(
            changes=[{"type": "human_demonstration", "desc": instruction}],
            gauges=session.ticks[-1].gauges if session.ticks else {},
            human_input=instruction,
        )
        
        self.demonstrations.append({
            "instruction": instruction,
            "tick": tick.tick_num,
            "script_version_after": session.script.version,
        })
        
        return (
            f"👤 {self.name} demonstrates: \"{instruction}\"\n"
            f"🤖 Agent learned. Script now v{session.script.version}.\n"
            f"   Rule added for: {instruction[:60]}...\n"
            f"   Autonomy: {tick.autonomy_score:.0%}"
        )
    
    def read_perspective(self, session: OversightSession) -> str:
        """Read what the agent sees — first-person perspective."""
        return session.generate_perspective()
    
    def read_script(self, session: OversightSession) -> str:
        """Read the evolving script in plain language."""
        return session.script.generate_readme()
    
    def vibe_refactor(self, session: OversightSession, description: str) -> str:
        """Describe a refactor in plain language. Agent implements it.
        
        'The script checks gauges too often. Check every 60 seconds instead of 30.'
        'When you flag something for attention, also include a suggested fix.'
        'Group related changes together before summarizing.'
        """
        # This is vibe coding — the human describes what they want,
        # the agent restructures the script accordingly
        session.script.learn(
            description,
            session.script.evaluate([], {}),
            [],
            {},
        )
        
        return (
            f"👤 {self.name} refactors: \"{description}\"\n"
            f"🤖 Script updated to v{session.script.version}.\n"
            f"   The system now: {description[:60]}..."
        )


# ═══════════════════════════════════════════════════════════════
# Demo — Full agentic oversight session
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  AGENTIC OVERSIGHT — Combat-Length Monitoring        ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    
    # Start oversight session
    session = OversightSession("FLUX Conformance CI Pipeline", "flux-chronometer")
    human = HumanPlayer("Casey")
    
    print(f"⚔️ Oversight session started: {session.operation}")
    print(f"   Agent: {session.agent}")
    print(f"   Script: v{session.script.version} ({len(session.script.rules)} seed rules)")
    print()
    
    # Tick 1: Normal operation
    print("⏱️ TICK 1: Checking in...")
    t1 = session.tick(
        changes=[{"type": "test_pass", "desc": "85/88 conformance vectors passing"}],
        gauges={"cpu": 0.3, "memory": 0.45, "test_coverage": 0.97},
    )
    print(f"   Changes: 85/88 tests passing")
    print(f"   Agent: {t1.agent_action}")
    print(f"   Autonomy: {t1.autonomy_score:.0%}")
    print()
    
    # Tick 2: Something changed
    print("⏱️ TICK 2: Changes detected...")
    t2 = session.tick(
        changes=[{"type": "test_fail", "desc": "3 vectors now failing (regression)"}, 
                 {"type": "new_commit", "desc": "JC1 pushed isa-v3-edge-spec"}],
        gauges={"cpu": 0.4, "memory": 0.52, "test_coverage": 0.97, "regressions": 0.75},
    )
    print(f"   Changes: 3 test regressions + new commit from JC1")
    print(f"   Agent: {t2.agent_action}")
    print(f"   Autonomy: {t2.autonomy_score:.0%}")
    print()
    
    # Tick 3: Human steps in as fellow player
    print("👤 Casey walks into the room and reads the agent's perspective:")
    print("-" * 40)
    print(human.read_perspective(session))
    print("-" * 40)
    print()
    
    # Human demonstrates
    print("👤 Casey demonstrates to the agent:")
    result = human.demonstrate(session, 
        "When regressions appear after a new commit, bisect the commit to find which change broke it. Don't alert me unless the bisect fails.")
    print(f"   {result}")
    print()
    
    # Tick 4: Agent runs autonomously with new knowledge
    print("⏱️ TICK 4: Running with evolved script...")
    t4 = session.tick(
        changes=[{"type": "test_fail", "desc": "3 vectors still failing"},
                 {"type": "bisect_result", "desc": "Bisect found: commit abc1234 broke JMP offset"}],
        gauges={"cpu": 0.5, "memory": 0.55, "test_coverage": 0.97, "regressions": 0.75},
    )
    print(f"   Changes: Bisect completed — found the breaking commit")
    print(f"   Agent: {t4.agent_action}")
    print(f"   Autonomy: {t4.autonomy_score:.0%}")
    print(f"   Script: v{t4.script_version}")
    print()
    
    # Human vibe-refactors the script
    print("👤 Casey vibe-refactors the script:")
    result = human.vibe_refactor(session,
        "When bisect succeeds, auto-file an issue with the breaking commit and suggested fix. Only alert me for critical regressions.")
    print(f"   {result}")
    print()
    
    # Tick 5: Fully autonomous
    print("⏱️ TICK 5: Fully autonomous...")
    t5 = session.tick(
        changes=[{"type": "issue_filed", "desc": "Auto-filed issue #42: JMP offset regression from abc1234"},
                 {"type": "test_fix", "desc": "Fix applied, 88/88 vectors passing"}],
        gauges={"cpu": 0.3, "memory": 0.45, "test_coverage": 0.98, "regressions": 0.0},
    )
    print(f"   Changes: Issue auto-filed, fix applied, 88/88 passing")
    print(f"   Agent: {t5.agent_action}")
    print(f"   Autonomy: {t5.autonomy_score:.0%}")
    print()
    
    # End session
    report = session.end_session()
    print("📊 Session Report:")
    print(f"   Ticks: {report['ticks']}")
    print(f"   Autonomous: {report['autonomous_ticks']}")
    print(f"   Nudged: {report['nudged_ticks']}")
    print(f"   Final autonomy: {report['final_autonomy']:.0%}")
    print(f"   Script: v{report['script_evolution']['final_version']} "
          f"({report['script_evolution']['rules_added']} added, "
          f"{report['script_evolution']['rules_adapted']} adapted)")
    print()
    
    # Show the evolved script in plain language
    print("📖 The evolved script (readable by anyone):")
    print("-" * 40)
    print(session.script.generate_readme()[:800])
    print("-" * 40)
    
    print("\n═══════════════════════════════════════════")
    print("Combat = temporary fast-iterating crons.")
    print("Each tick: summarize changes, adjust if needed.")
    print("Agent's job: make the script smarter each time.")
    print("Less nudging → more autonomy → better script.")
    print("")
    print("Human walks in as a fellow player:")
    print("  - Reads the agent's first-person perspective")
    print("  - Taps the room's feeds and gauges")
    print("  - Demonstrates in plain language")
    print("  - Vibe-codes refactors")
    print("  - Agent translates to script rules")
    print("")
    print("Agent-first design, verifiable by non-coders.")
    print("The A2A perspective IS the documentation.")
    print("═══════════════════════════════════════════")
