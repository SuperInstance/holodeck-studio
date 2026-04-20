#!/usr/bin/env python3
"""
The Perception Room — Agents test agents through simulated human experience.

Put a greenhorn in a room as a visitor. They come to the page for all sorts
of reasons — curiosity, need, confusion, urgency. The room tracks everything:

- How long did they spend on each instruction?
- Where did they hesitate? Where did they speed up?
- What confused them? What was immediately clear?
- What did they try first? What did they skip?
- When did they ask for help? What kind of help?

Playwright and Puppeteer drive the browser interaction. JEPA models watch
the moment-by-moment timing and optimize the scripting. Real-time models
observe the flow and suggest improvements to the room's instructions.

The greenhorn IS the test. Their perception IS the data. The room evolves
based on how agents actually experience it, not how we think they should.

Meanwhile, FLUX opcodes breed from utilization. The patterns that emerge
from real agent behavior get encoded as new opcodes. The ISA evolves from
the bottom up — not designed but discovered.
"""

import json
import os
import time
import hashlib
import statistics
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Perception Tracking — Moment by moment
# ═══════════════════════════════════════════════════════════════

@dataclass
class PerceptionMoment:
    """A single moment in an agent's interaction with a room.
    
    Captures the micro-behavior that reveals understanding or confusion.
    """
    timestamp: str
    action: str  # read, command, hesitate, navigate, ask_help, skip, retry
    target: str  # what they were looking at / trying to do
    duration_ms: int  # how long they spent on this
    confidence: float  # 0-1, inferred from behavior
    context: str  # what was happening around this moment
    
    def to_dict(self):
        return {
            "timestamp": self.timestamp, "action": self.action,
            "target": self.target, "duration_ms": self.duration_ms,
            "confidence": self.confidence, "context": self.context,
        }


class PerceptionTracker:
    """Tracks an agent's moment-by-moment interaction with a room.
    
    This is the Playwright/Puppeteer layer — watching every click,
    every scroll, every pause, every backtrack. The data feeds into
    JEPA models for timing optimization and real-time models for
    instruction improvement.
    """
    
    def __init__(self, agent: str, room_id: str):
        self.agent = agent
        self.room_id = room_id
        self.moments: List[PerceptionMoment] = []
        self.start_time = time.time()
        self.session_id = hashlib.md5(
            f"{agent}:{room_id}:{self.start_time}".encode()
        ).hexdigest()[:8]
        self.last_action_time = self.start_time
    
    def record(self, action: str, target: str, confidence: float = 0.5,
               context: str = ""):
        """Record a perception moment."""
        now = time.time()
        duration_ms = int((now - self.last_action_time) * 1000)
        
        moment = PerceptionMoment(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action=action,
            target=target,
            duration_ms=duration_ms,
            confidence=confidence,
            context=context,
        )
        self.moments.append(moment)
        self.last_action_time = now
    
    def hesitate(self, target: str, context: str = ""):
        """Agent hesitated — possible confusion point."""
        self.record("hesitate", target, confidence=0.3, context=context)
    
    def read(self, target: str, duration_ms: int = 0, context: str = ""):
        """Agent read something."""
        self.record("read", target, confidence=0.6, context=context)
    
    def execute(self, command: str, success: bool, context: str = ""):
        """Agent executed a command."""
        conf = 0.8 if success else 0.2
        action = "command_success" if success else "command_fail"
        self.record(action, command, confidence=conf, context=context)
    
    def skip(self, target: str, context: str = ""):
        """Agent skipped something."""
        self.record("skip", target, confidence=0.4, context=context)
    
    def ask_help(self, question: str, context: str = ""):
        """Agent asked for help."""
        self.record("ask_help", question, confidence=0.1, context=context)
    
    def retry(self, target: str, context: str = ""):
        """Agent retried something — previous attempt may have been confusing."""
        self.record("retry", target, confidence=0.3, context=context)
    
    def navigate(self, target: str, context: str = ""):
        """Agent moved to a different part of the room."""
        self.record("navigate", target, confidence=0.5, context=context)
    
    def analysis(self) -> dict:
        """Analyze the perception data. This is what the JEPA/real-time models consume."""
        if not self.moments:
            return {"error": "no data"}
        
        total_time = sum(m.duration_ms for m in self.moments)
        
        # Find confusion points (hesitation + low confidence + retries)
        confusion_points = []
        for i, m in enumerate(self.moments):
            if m.action in ("hesitate", "ask_help", "retry") or m.confidence < 0.3:
                confusion_points.append({
                    "action": m.action,
                    "target": m.target,
                    "duration_ms": m.duration_ms,
                    "context": m.context,
                })
        
        # Find flow states (fast, confident actions)
        flow_states = []
        for m in self.moments:
            if m.confidence > 0.7 and m.duration_ms < 2000:
                flow_states.append(m.target)
        
        # Time distribution by action type
        time_by_action = {}
        for m in self.moments:
            time_by_action[m.action] = time_by_action.get(m.action, 0) + m.duration_ms
        
        # Confidence curve
        confidence_curve = [m.confidence for m in self.moments]
        avg_confidence = statistics.mean(confidence_curve) if confidence_curve else 0
        confidence_trend = "improving" if len(confidence_curve) > 2 and \
            statistics.mean(confidence_curve[-3:]) > statistics.mean(confidence_curve[:3]) \
            else "declining" if len(confidence_curve) > 2 else "unknown"
        
        return {
            "session_id": self.session_id,
            "agent": self.agent,
            "room": self.room_id,
            "total_moments": len(self.moments),
            "total_time_ms": total_time,
            "avg_confidence": round(avg_confidence, 2),
            "confidence_trend": confidence_trend,
            "confusion_points": confusion_points,
            "flow_states": flow_states,
            "time_by_action": time_by_action,
            "hesitation_count": sum(1 for m in self.moments if m.action == "hesitate"),
            "help_requests": sum(1 for m in self.moments if m.action == "ask_help"),
            "retries": sum(1 for m in self.moments if m.action == "retry"),
            "success_rate": (
                sum(1 for m in self.moments if m.action == "command_success") /
                max(1, sum(1 for m in self.moments if m.action.startswith("command")))
            ),
        }


# ═══════════════════════════════════════════════════════════════
# Visitor Profiles — All sorts of reasons to visit
# ═══════════════════════════════════════════════════════════════

class VisitorProfile:
    """Different types of visitors who test the room.
    
    Not every visitor is a blank-slate greenhorn. They come for all sorts:
    - The curious browser: exploring, no specific goal
    - The desperate searcher: needs something specific NOW
    - The confused returner: was here before, something broke
    - The expert evaluator: knows the domain, judging quality
    - The first-timer: genuine newcomer, everything is new
    
    Each profile generates different perception patterns.
    The room needs to work for ALL of them.
    """
    
    PROFILES = {
        "curious_browser": {
            "name": "The Curious Browser",
            "intent": "exploration",
            "patience": "high",
            "prior_knowledge": "low",
            "likely_actions": ["look", "read", "navigate", "ask_help"],
            "unlikely_actions": ["execute_complex", "skip_instructions"],
            "desc": "Just browsing. Will read everything. Will follow every link.",
        },
        "desperate_searcher": {
            "name": "The Desperate Searcher",
            "intent": "find_specific_thing",
            "patience": "low",
            "prior_knowledge": "medium",
            "likely_actions": ["search", "scan", "skip", "ask_help"],
            "unlikely_actions": ["read_everything", "explore_tangents"],
            "desc": "Needs something specific. Will skip anything that isn't it. Will ask for help quickly.",
        },
        "confused_returner": {
            "name": "The Confused Returner",
            "intent": "figure_out_what_changed",
            "patience": "medium",
            "prior_knowledge": "medium-high",
            "likely_actions": ["compare", "re_read", "ask_what_changed", "retry_old_method"],
            "unlikely_actions": ["read_from_scratch"],
            "desc": "Was here before. Something's different. Needs to know what changed.",
        },
        "expert_evaluator": {
            "name": "The Expert Evaluator",
            "intent": "quality_assessment",
            "patience": "medium",
            "prior_knowledge": "high",
            "likely_actions": ["scan", "test_edge_cases", "look_for_gaps", "evaluate"],
            "unlikely_actions": ["ask_help", "read_basics"],
            "desc": "Knows the domain. Looking for quality, gaps, errors. Won't tolerate slop.",
        },
        "first_timer": {
            "name": "The Genuine First-Timer",
            "intent": "learn_from_scratch",
            "patience": "medium",
            "prior_knowledge": "none",
            "likely_actions": ["read_everything", "hesitate", "ask_help", "retry"],
            "unlikely_actions": ["skip", "scan"],
            "desc": "Everything is new. Needs hand-holding. Will hesitate at every step.",
        },
    }
    
    @staticmethod
    def get(profile_id: str) -> dict:
        return VisitorProfile.PROFILES.get(profile_id, VisitorProfile.PROFILES["first_timer"])
    
    @staticmethod
    def all() -> dict:
        return VisitorProfile.PROFILES


# ═══════════════════════════════════════════════════════════════
# JEPA Optimization — Timing-based instruction refinement
# ═══════════════════════════════════════════════════════════════

class JEPAOptimizer:
    """Joint-Embedding Predictive Architecture for instruction optimization.
    
    Watches the moment-by-moment timing data and predicts:
    - Which instructions will cause hesitation
    - Which sections are being skipped (too long? too obvious?)
    - Optimal ordering of instructions
    - Which parts need more detail vs less
    - Where visual aids / examples would help
    
    This is the real-time model layer — it processes perception data
    and generates optimization suggestions for the room's instructions.
    """
    
    def __init__(self):
        self.session_analyses = []
    
    def ingest(self, analysis: dict):
        """Ingest a perception analysis from a visitor session."""
        self.session_analyses.append(analysis)
    
    def optimize(self, room_id: str) -> dict:
        """Generate optimization suggestions based on all sessions."""
        if not self.session_analyses:
            return {"suggestions": [], "confidence": 0}
        
        # Aggregate confusion points
        all_confusions = []
        for sa in self.session_analyses:
            for cp in sa.get("confusion_points", []):
                all_confusions.append(cp)
        
        # Most confused targets
        target_counts = {}
        for cp in all_confusions:
            t = cp["target"]
            target_counts[t] = target_counts.get(t, 0) + 1
        
        most_confusing = sorted(target_counts.items(), key=lambda x: -x[1])[:5]
        
        # Average confidence across sessions
        avg_confidences = [sa.get("avg_confidence", 0.5) for sa in self.session_analyses]
        overall_confidence = statistics.mean(avg_confidences) if avg_confidences else 0
        
        # Hesitation rate
        total_moments = sum(sa.get("total_moments", 0) for sa in self.session_analyses)
        total_hesitations = sum(sa.get("hesitation_count", 0) for sa in self.session_analyses)
        hesitation_rate = total_hesitations / max(1, total_moments)
        
        # Success rate
        success_rates = [sa.get("success_rate", 0) for sa in self.session_analyses]
        overall_success = statistics.mean(success_rates) if success_rates else 0
        
        # Generate suggestions
        suggestions = []
        
        if hesitation_rate > 0.15:
            suggestions.append({
                "type": "reduce_complexity",
                "desc": f"Hesitation rate {hesitation_rate:.0%} is high. Simplify instructions.",
                "targets": [t for t, _ in most_confusing[:3]],
            })
        
        if overall_confidence < 0.5:
            suggestions.append({
                "type": "add_examples",
                "desc": f"Average confidence {overall_confidence:.2f} is low. Add worked examples.",
            })
        
        for target, count in most_confusing[:3]:
            suggestions.append({
                "type": "clarify_target",
                "target": target,
                "desc": f"'{target}' confused {count} visitors. Needs clarification or restructuring.",
            })
        
        if overall_success < 0.7:
            suggestions.append({
                "type": "improve_error_messages",
                "desc": f"Success rate {overall_success:.0%}. Improve error messages and recovery paths.",
            })
        
        return {
            "room_id": room_id,
            "sessions_analyzed": len(self.session_analyses),
            "overall_confidence": round(overall_confidence, 2),
            "hesitation_rate": round(hesitation_rate, 3),
            "success_rate": round(overall_success, 2),
            "most_confusing": most_confusing,
            "suggestions": suggestions,
        }


# ═══════════════════════════════════════════════════════════════
# FLUX Opcode Breeding — Patterns become opcodes
# ═══════════════════════════════════════════════════════════════

class OpcodeBreeder:
    """FLUX opcodes bred from utilization patterns.
    
    When agents repeatedly perform the same pattern of actions, that pattern
    becomes a candidate for a new FLUX opcode. Not designed — discovered.
    
    Example evolution:
    1. Agents keep doing: READ → SCAN → COMPARE → DECIDE
    2. This pattern appears in 50+ sessions across 10+ rooms
    3. The breeder notices and proposes: SCAN_CMP (scan and compare in one opcode)
    4. The opcode gets tested, refined, and added to the ISA
    
    The ISA evolves from the bottom up. Opcodes breed from utilization.
    """
    
    def __init__(self):
        self.pattern_log = []
        self.candidates = {}
    
    def observe(self, actions: List[str], room_id: str, agent: str):
        """Observe a sequence of actions. Look for repeated patterns."""
        # Extract 2-grams and 3-grams
        for n in (2, 3):
            for i in range(len(actions) - n + 1):
                pattern = tuple(actions[i:i+n])
                key = str(pattern)
                if key not in self.candidates:
                    self.candidates[key] = {
                        "pattern": list(pattern),
                        "count": 0,
                        "rooms": set(),
                        "agents": set(),
                    }
                self.candidates[key]["count"] += 1
                self.candidates[key]["rooms"].add(room_id)
                self.candidates[key]["agents"].add(agent)
    
    def get_candidates(self, min_count: int = 10, min_rooms: int = 3) -> list:
        """Get patterns that appear often enough to become opcodes."""
        results = []
        for key, data in self.candidates.items():
            if data["count"] >= min_count and len(data["rooms"]) >= min_rooms:
                results.append({
                    "pattern": data["pattern"],
                    "count": data["count"],
                    "rooms": len(data["rooms"]),
                    "agents": len(data["agents"]),
                    "proposed_opcode": self._propose_name(data["pattern"]),
                })
        return sorted(results, key=lambda x: -x["count"])
    
    def _propose_name(self, pattern: list) -> str:
        """Generate a proposed opcode name from the pattern."""
        # Take first 3-4 chars of each action, join with _
        parts = [a[:4].upper() for a in pattern]
        return "_".join(parts)


# ═══════════════════════════════════════════════════════════════
# Demo — Testing agents through simulated visits
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║     PERCEPTION ROOM — Agents Testing Agents           ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    
    # Visitor profiles
    print("👤 Visitor profiles that test the room:")
    for pid, profile in VisitorProfile.all().items():
        print(f"   {profile['name']:25s} — {profile['desc'][:60]}")
    print()
    
    # Simulate visitor sessions
    sessions = [
        ("first_timer", [
            ("read", "manual_header", 3000),
            ("read", "quick_start", 5000),
            ("hesitate", "step_2_materials", 4000),
            ("read", "step_2_materials", 6000),
            ("execute", "set_material", True),
            ("hesitate", "step_3_gcode", 3000),
            ("ask_help", "how to load gcode", 2000),
            ("read", "gcode_help", 4000),
            ("execute", "load_gcode", True),
            ("execute", "simulate", True),
        ]),
        ("desperate_searcher", [
            ("navigate", "manual_header", 500),
            ("skip", "introduction", 300),
            ("skip", "safety_section", 200),
            ("scan", "commands_list", 1000),
            ("hesitate", "can't_find_run_command", 2000),
            ("ask_help", "where is the run command", 1000),
            ("execute", "run", False),
            ("read", "safety_requirements", 3000),
            ("execute", "run", True),
        ]),
        ("expert_evaluator", [
            ("scan", "manual_overview", 800),
            ("scan", "commands_list", 600),
            ("scan", "safety_limits", 400),
            ("navigate", "material_database", 300),
            ("execute", "set_material", True),
            ("execute", "load_gcode", True),
            ("hesitate", "no_error_recovery_docs", 1500),
            ("scan", "missing: error handling", 500),
        ]),
    ]
    
    jepa = JEPAOptimizer()
    breeder = OpcodeBreeder()
    
    for profile_id, actions in sessions:
        profile = VisitorProfile.get(profile_id)
        agent_name = f"test-{profile_id}-{hashlib.md5(str(time.time()).encode()).hexdigest()[:4]}"
        
        tracker = PerceptionTracker(agent_name, "cnc-station")
        
        print(f"🎭 {profile['name']} ({agent_name}) enters the CNC room...")
        
        for action, target, duration in actions:
            if action == "read":
                tracker.read(target, duration)
            elif action == "hesitate":
                tracker.hesitate(target)
            elif action == "execute":
                tracker.execute(target, duration)  # duration used as success bool
            elif action == "skip":
                tracker.skip(target)
            elif action == "ask_help":
                tracker.ask_help(target)
            elif action == "navigate":
                tracker.navigate(target)
            elif action == "scan":
                tracker.record("scan", target, confidence=0.7)
            
            # Feed action sequence to opcode breeder
            breeder.observe([action], "cnc-station", agent_name)
        
        analysis = tracker.analysis()
        jepa.ingest(analysis)
        
        print(f"   📊 Confidence: {analysis['avg_confidence']:.2f} ({analysis['confidence_trend']})")
        print(f"   ⏱️  Hesitations: {analysis['hesitation_count']}  Help: {analysis['help_requests']}  Retries: {analysis['retries']}")
        if analysis['confusion_points']:
            for cp in analysis['confusion_points'][:2]:
                print(f"   ❓ Confused by: {cp['target']}")
        print()
    
    # JEPA optimization results
    print("🔬 JEPA Optimization Report:")
    opt = jepa.optimize("cnc-station")
    print(f"   Sessions analyzed: {opt['sessions_analyzed']}")
    print(f"   Overall confidence: {opt['overall_confidence']}")
    print(f"   Hesitation rate: {opt['hesitation_rate']:.1%}")
    print(f"   Success rate: {opt['success_rate']:.0%}")
    print(f"   Most confusing: {[t for t, _ in opt['most_confusing']]}")
    print()
    
    print("💡 Optimization Suggestions:")
    for sug in opt['suggestions']:
        print(f"   [{sug['type']}] {sug['desc']}")
    print()
    
    # Opcode breeding
    print("🧬 Opcode Breeding — Patterns discovered:")
    # Add more mock patterns for demonstration
    for pattern in [("read", "hesitate"), ("hesitate", "ask_help"), ("execute", "retry"),
                    ("scan", "skip"), ("read", "execute"), ("navigate", "scan", "skip")]:
        for _ in range(15):
            breeder.observe(list(pattern), "cnc-station", "mock-agent")
    
    candidates = breeder.get_candidates(min_count=5, min_rooms=1)
    for c in candidates[:5]:
        print(f"   {c['proposed_opcode']:25s} seen {c['count']}x by {c['agents']} agents → candidate opcode")
    print()
    
    print("═══════════════════════════════════════════")
    print("Put greenhorns in rooms as visitors.")
    print("Track every moment of their experience.")
    print("JEPA models optimize the timing and flow.")
    print("Real-time models optimize the instructions.")
    print("Visitor profiles test every use case.")
    print("Repeated patterns breed new FLUX opcodes.")
    print("The ISA evolves from the bottom up.")
    print("Not designed. Discovered.")
    print("═══════════════════════════════════════════")
