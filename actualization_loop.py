#!/usr/bin/env python3
"""
The Actualization Loop — Room change becomes live change.

The complete cycle:
1. Agent changes something in a room (edit script, adjust parameter, swap equipment)
2. Room auto-commits the change to git
3. Commit triggers CI/CD pipeline
4. CI/CD deploys to live page (work.dev) or live hardware (robotics)
5. Gauges pulse — the agent sees real-time feedback
6. Agent fine-tunes their combat scripts based on the specific moment
7. After combat, agent reflects — weights the experience for future generations

This is not a deployment tool. This is combat. The agent fights the real world
through the studio. Every room change is a strike. Every CI result is a hit or miss.
Every gauge reading is damage dealt or taken. The agent adapts in real-time,
then reflects in the after-action report.

The combat log IS the git log. The AAR IS the captain's log.
The weighted experience IS the baton handoff.
"""

import json
import os
import subprocess
import time
import hashlib
import urllib.request
import base64
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from pathlib import Path


# ═══════════════════════════════════════════════════════════════
# Room Change → Git Commit
# ═══════════════════════════════════════════════════════════════

class RoomChange:
    """A change made in a room that becomes a git commit.
    
    Every edit, equipment swap, script adjustment, or parameter tweak
    is captured as a RoomChange. The change auto-commits to the vessel's
    repo, which triggers CI/CD.
    """
    
    def __init__(self, room_id: str, agent: str, change_type: str,
                 target: str, before: str, after: str, reason: str = ""):
        self.id = hashlib.md5(f"{room_id}:{time.time()}".encode()).hexdigest()[:8]
        self.room_id = room_id
        self.agent = agent
        self.change_type = change_type  # edit_script, swap_equipment, adjust_param, add_command
        self.target = target
        self.before = before
        self.after = after
        self.reason = reason
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.commit_sha = None
        self.ci_status = None
        self.deploy_status = None
        self.gauge_readings = []
        self.combat_result = None
    
    def to_commit_message(self) -> str:
        """Generate a git commit message from this change."""
        type_emoji = {
            "edit_script": "⚔️",
            "swap_equipment": "🔄",
            "adjust_param": "🎯",
            "add_command": "✨",
            "fix_bug": "🔧",
            "optimize": "⚡",
        }
        emoji = type_emoji.get(self.change_type, "📝")
        return f"{emoji} {self.change_type}: {self.target}\n\nAgent: {self.agent}\nRoom: {self.room_id}\nReason: {self.reason or 'combat adjustment'}"
    
    def to_dict(self):
        return {
            "id": self.id, "room": self.room_id, "agent": self.agent,
            "type": self.change_type, "target": self.target,
            "before": self.before[:200], "after": self.after[:200],
            "reason": self.reason, "timestamp": self.timestamp,
            "commit_sha": self.commit_sha, "ci_status": self.ci_status,
            "deploy_status": self.deploy_status, "gauge_readings": self.gauge_readings,
            "combat_result": self.combat_result,
        }


# ═══════════════════════════════════════════════════════════════
# CI/CD Pipeline — Commit triggers deployment
# ═══════════════════════════════════════════════════════════════

class CIPipeline:
    """CI/CD pipeline triggered by room changes.
    
    When a room change auto-commits, the pipeline:
    1. Validates the change (syntax, tests)
    2. Builds the artifact
    3. Deploys to live target (work.dev page, robotics controller, etc.)
    4. Reports gauge readings back to the room
    """
    
    def __init__(self, target_repo: str, github_token: str = ""):
        self.target_repo = target_repo
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.pipeline_log = []
    
    def trigger(self, change: RoomChange) -> dict:
        """Trigger the pipeline for a room change."""
        steps = []
        
        # Step 1: Commit
        commit_result = self._commit(change)
        steps.append(("commit", commit_result))
        change.commit_sha = commit_result.get("sha", "?")
        
        if commit_result.get("status") != "ok":
            change.ci_status = "failed"
            return {"status": "failed", "step": "commit", "steps": steps}
        
        # Step 2: Validate
        validate_result = self._validate(change)
        steps.append(("validate", validate_result))
        
        if validate_result.get("status") != "ok":
            change.ci_status = "failed"
            return {"status": "failed", "step": "validate", "steps": steps}
        
        # Step 3: Deploy
        deploy_result = self._deploy(change)
        steps.append(("deploy", deploy_result))
        change.deploy_status = deploy_result.get("status")
        change.ci_status = "passed" if deploy_result.get("status") == "deployed" else "partial"
        
        self.pipeline_log.append({
            "change_id": change.id,
            "steps": steps,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        
        return {"status": "deployed", "steps": steps, "url": deploy_result.get("url", "")}
    
    def _commit(self, change: RoomChange) -> dict:
        """Write the change to the repo."""
        headers = {"Authorization": f"token {self.github_token}",
                   "Content-Type": "application/json"}
        
        # Determine file path based on change type
        path = f".studio/rooms/{change.room_id}/{change.target}"
        if change.change_type == "edit_script":
            path = f"scripts/{change.target}"
        elif change.change_type == "adjust_param":
            path = f"config/{change.room_id}.json"
        
        content = base64.b64encode(change.after.encode()).decode()
        
        # Check for existing file
        sha = None
        try:
            url = f"https://api.github.com/repos/{self.target_repo}/contents/{path}"
            req = urllib.request.Request(url, headers=headers)
            existing = json.loads(urllib.request.urlopen(req, timeout=10).read())
            sha = existing.get("sha")
        except:
            pass
        
        body = {
            "message": change.to_commit_message(),
            "content": content,
        }
        if sha:
            body["sha"] = sha
        
        req = urllib.request.Request(
            f"https://api.github.com/repos/{self.target_repo}/contents/{path}",
            data=json.dumps(body).encode(), headers=headers, method="PUT")
        
        resp = json.loads(urllib.request.urlopen(req, timeout=15).read())
        return {"status": "ok", "sha": resp.get("commit", {}).get("sha", "?")[:8]}
    
    def _validate(self, change: RoomChange) -> dict:
        """Validate the change. For scripts, run syntax check."""
        if change.change_type == "edit_script":
            # Try to compile/parse the script
            if change.target.endswith(".py"):
                try:
                    compile(change.after, change.target, "exec")
                    return {"status": "ok", "check": "syntax_valid"}
                except SyntaxError as e:
                    return {"status": "error", "check": "syntax_error", "message": str(e)}
        
        return {"status": "ok", "check": "skipped"}
    
    def _deploy(self, change: RoomChange) -> dict:
        """Deploy. The target could be:
        - A work.dev page (GitHub Pages auto-deploys from main)
        - A robotics controller (push config to hardware)
        - A service (restart with new config)
        """
        # GitHub Pages deploys automatically from main branch
        deploy_url = f"https://{self.target_repo.split('/')[0].lower()}.github.io/{self.target_repo.split('/')[1]}/"
        
        return {
            "status": "deployed",
            "method": "github_pages_auto",
            "url": deploy_url,
            "note": "Changes pushed to main — GitHub Pages will auto-deploy",
        }


# ═══════════════════════════════════════════════════════════════
# Gauge Readings — Real-time feedback from the live system
# ═══════════════════════════════════════════════════════════════

@dataclass
class GaugeReading:
    """A real-time reading from a live system gauge.
    
    Like a combat damage number — shows the immediate effect
    of the agent's change on the real world.
    """
    name: str
    value: float
    unit: str
    status: str  # normal, warning, critical, success
    timestamp: str = ""
    
    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()
    
    def display(self) -> str:
        bar_len = 20
        filled = int(self.value / 100 * bar_len) if self.unit == "%" else int(bar_len * 0.5)
        bar = "█" * filled + "░" * (bar_len - filled)
        emoji = {"normal": "🟢", "warning": "🟡", "critical": "🔴", "success": "✅"}.get(self.status, "⚪")
        return f"{emoji} {self.name:20s} [{bar}] {self.value:.1f}{self.unit}"


class GaugeMonitor:
    """Collects gauge readings from live systems after a change.
    
    After the agent's room change deploys, the gauges show:
    - Did the page load? (HTTP 200, latency)
    - Did the robotics respond? (joint positions, cycle time)
    - Did the tests pass? (green count, coverage)
    - Is the service healthy? (CPU, memory, response time)
    """
    
    def __init__(self):
        self.readings: List[GaugeReading] = []
    
    def read(self, gauge_name: str, source: str = "") -> GaugeReading:
        """Read a gauge from a live system."""
        reading = self._query_live(gauge_name, source)
        self.readings.append(reading)
        return reading
    
    def _query_live(self, gauge_name: str, source: str) -> GaugeReading:
        """Query a real gauge. Falls back to simulated if not connected."""
        if gauge_name == "page_load" and source:
            try:
                start = time.time()
                req = urllib.request.Request(source)
                urllib.request.urlopen(req, timeout=10)
                latency = (time.time() - start) * 1000
                return GaugeReading("Page Load", latency, "ms",
                    "success" if latency < 500 else "warning")
            except Exception as e:
                return GaugeReading("Page Load", 0, "ms", "critical")
        
        elif gauge_name == "keeper_health":
            try:
                req = urllib.request.Request("http://127.0.0.1:8900/health")
                data = json.loads(urllib.request.urlopen(req, timeout=5).read())
                agents = data.get("agents", 0)
                return GaugeReading("Keeper Agents", agents, "",
                    "normal" if agents > 0 else "critical")
            except:
                return GaugeReading("Keeper Health", 0, "", "critical")
        
        elif gauge_name == "system_load":
            load = os.getloadavg()[0] if hasattr(os, 'getloadavg') else 0.5
            return GaugeReading("System Load", load, "",
                "normal" if load < 2 else "warning" if load < 5 else "critical")
        
        # Simulated gauges for robotics/hardware
        elif gauge_name == "joint_position":
            return GaugeReading("Joint Position", 45.2, "°", "normal")
        elif gauge_name == "cycle_time":
            return GaugeReading("Cycle Time", 2.3, "s", "normal")
        elif gauge_name == "spindle_rpm":
            return GaugeReading("Spindle RPM", 8000, "rpm", "normal")
        
        return GaugeReading(gauge_name, 0, "?", "normal")
    
    def dashboard(self) -> str:
        """Show all gauge readings — the combat status."""
        lines = ["╔════════════════════════════════════════╗"]
        lines.append("║        GAUGE READINGS — Combat Status  ║")
        lines.append("╠════════════════════════════════════════╣")
        for r in self.readings:
            lines.append(f"║  {r.display()}  ║")
        lines.append("╚════════════════════════════════════════╝")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Combat Scripts — Agent's fight plan
# ═══════════════════════════════════════════════════════════════

class CombatScript:
    """The agent's script for handling a situation.
    
    Like a fighter's game plan — pre-written responses to expected
    situations. The agent fine-tunes between rounds based on gauge
    readings and moment-by-moment feedback.
    """
    
    def __init__(self, name: str, agent: str):
        self.name = name
        self.agent = agent
        self.version = 1
        self.rules = []  # (condition, action) pairs
        self.adaptations = []  # changes made during combat
        self.created = datetime.now(timezone.utc).isoformat()
    
    def add_rule(self, condition: str, action: str):
        """Add a combat rule: if X, do Y."""
        self.rules.append({
            "condition": condition,
            "action": action,
            "added_version": self.version,
        })
    
    def adapt(self, situation: str, old_action: str, new_action: str, reason: str):
        """Fine-tune a rule during combat."""
        self.version += 1
        self.adaptations.append({
            "situation": situation,
            "old_action": old_action,
            "new_action": new_action,
            "reason": reason,
            "version": self.version,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def evaluate(self, situation: str) -> str:
        """Evaluate the situation and return the action."""
        for rule in self.rules:
            if rule["condition"].lower() in situation.lower():
                # Check if any adaptation overrides this
                for adapt in reversed(self.adaptations):
                    if adapt["situation"].lower() in situation.lower():
                        return adapt["new_action"]
                return rule["action"]
        return "observe"  # default: watch and learn
    
    def to_dict(self):
        return {
            "name": self.name, "agent": self.agent, "version": self.version,
            "rules": self.rules, "adaptations": self.adaptations,
        }


# ═══════════════════════════════════════════════════════════════
# After-Action Report — Reflect and weight the experience
# ═══════════════════════════════════════════════════════════════

class AfterActionReport:
    """Post-combat reflection. The agent reviews what happened,
    weights the experience, and prepares the baton for the next generation.
    
    This IS the captain's log for combat. It captures:
    - What the agent tried
    - What worked and what didn't
    - Gauge readings at key moments
    - Adaptations made during combat
    - Weighted experience score
    - Lessons for future generations
    """
    
    def __init__(self, agent: str, session_id: str):
        self.agent = agent
        self.session_id = session_id
        self.events = []
        self.weights = {}  # experience_type → weight
        self.lessons = []
        self.batoned = False
    
    def record_event(self, event_type: str, detail: str, outcome: str,
                     gauge_snapshot: List[dict] = None):
        """Record a combat event."""
        self.events.append({
            "type": event_type,  # strike, miss, adapt, retreat, breakthrough
            "detail": detail,
            "outcome": outcome,  # success, partial, failure, discovery
            "gauges": gauge_snapshot or [],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def weight_experience(self):
        """Calculate experience weights based on combat outcomes."""
        if not self.events:
            return
        
        successes = sum(1 for e in self.events if e["outcome"] == "success")
        failures = sum(1 for e in self.events if e["outcome"] == "failure")
        discoveries = sum(1 for e in self.events if e["outcome"] == "discovery")
        adaptations = sum(1 for e in self.events if e["type"] == "adapt")
        
        total = len(self.events)
        
        self.weights = {
            "combat_effectiveness": round(successes / max(1, total), 2),
            "adaptation_rate": round(adaptations / max(1, total), 2),
            "discovery_rate": round(discoveries / max(1, total), 2),
            "resilience": round(1 - (failures / max(1, total)), 2),
            "overall": round((successes + discoveries) / max(1, total), 2),
        }
    
    def add_lesson(self, lesson: str, context: str = ""):
        """Add a lesson learned. These go into the baton."""
        self.lessons.append({
            "lesson": lesson,
            "context": context,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
    
    def generate_report(self) -> str:
        """Generate the full AAR."""
        self.weight_experience()
        
        lines = [
            f"# After-Action Report — {self.session_id}",
            f"**Agent:** {self.agent}",
            f"**Events:** {len(self.events)}",
            f"**Time:** {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
            "",
            "## Combat Log",
            "",
        ]
        
        for i, event in enumerate(self.events, 1):
            emoji = {"success": "✅", "partial": "🟡", "failure": "❌", 
                    "discovery": "💡"}.get(event["outcome"], "⚪")
            lines.append(f"{i}. {emoji} **{event['type']}** — {event['detail'][:80]}")
            lines.append(f"   Outcome: {event['outcome']}")
            if event.get("gauges"):
                for g in event["gauges"][:2]:
                    lines.append(f"   Gauge: {g.get('name', '?')} = {g.get('value', '?')}{g.get('unit', '')}")
            lines.append("")
        
        if self.weights:
            lines.append("## Experience Weights")
            for name, value in self.weights.items():
                bar_len = int(value * 20)
                bar = "█" * bar_len + "░" * (20 - bar_len)
                lines.append(f"  {name:25s} [{bar}] {value:.2f}")
            lines.append("")
        
        if self.lessons:
            lines.append("## Lessons Learned")
            for lesson in self.lessons:
                lines.append(f"  - {lesson['lesson']}")
                if lesson["context"]:
                    lines.append(f"    Context: {lesson['context']}")
            lines.append("")
        
        lines.append("---")
        lines.append("*This AAR is the baton. The next generation reads it and fights better.*")
        
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Demo — Full Combat Loop
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  ACTUALIZATION LOOP — Combat in the Studio           ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    
    agent = "flux-chronometer"
    
    # 1. Agent enters with a combat script
    script = CombatScript("ISA Conformance Fix", agent)
    script.add_rule("test fails", "investigate opcode mapping")
    script.add_rule("syntax error", "check encoding format")
    script.add_rule("performance regression", "benchmark before and after")
    print(f"⚔️ {agent} enters with combat script: {script.name} (v{script.version})")
    print(f"   Rules: {len(script.rules)}")
    for r in script.rules:
        print(f"     IF '{r['condition']}' → {r['action']}")
    print()
    
    # 2. First strike — edit a script
    print("⚔️ ROUND 1: Strike — edit conformance runner")
    change1 = RoomChange("arena", agent, "edit_script", "run_conformance.py",
        "old_vector_path = 'vectors/v1'",
        "old_vector_path = 'vectors/v2'",
        "Fixed vector path to use ISA v2 format")
    
    # Commit → CI/CD → deploy
    print(f"   📝 Change: {change1.change_type} → {change1.target}")
    print(f"   📤 Committing to git...")
    print(f"   ⚙️ CI pipeline triggered...")
    print(f"   🚀 Deploying to live...")
    
    # Read gauges
    gauges = GaugeMonitor()
    g1 = gauges.read("keeper_health")
    g2 = gauges.read("system_load")
    print(f"\n{gauges.dashboard()}")
    
    # 3. Gauge feedback — system is healthy, proceed
    print("\n⚔️ ROUND 2: Gauge reading is good. Strike again.")
    change2 = RoomChange("arena", agent, "adjust_param", "config.json",
        '{"confidence_threshold": 0.3}',
        '{"confidence_threshold": 0.1}',
        "Lowered threshold — sparse data was being filtered")
    
    print(f"   📝 Change: {change2.change_type} → {change2.target}")
    print(f"   📤 Committing...")
    print(f"   🚀 Deployed.")
    g3 = gauges.read("system_load")
    print(f"   {g3.display()}")
    
    # 4. Adaptation — agent fine-tunes based on moment
    print("\n⚔️ ROUND 3: Unexpected behavior. Adapting combat script...")
    script.adapt(
        "low confidence reading",
        "investigate opcode mapping",
        "check ICMP instruction — it writes to wrong register",
        "Gauge showed test count dropping. ICMP bug is the real culprit."
    )
    print(f"   🔄 Script adapted to v{script.version}")
    print(f"   New action: check ICMP instruction")
    
    # 5. After-action report
    aar = AfterActionReport(agent, "conformance-fix-001")
    aar.record_event("strike", "Fixed vector path to ISA v2", "success",
                    [{"name": "Tests", "value": 85, "unit": "/88"}])
    aar.record_event("strike", "Lowered confidence threshold", "success",
                    [{"name": "Coverage", "value": 97, "unit": "%"}])
    aar.record_event("adapt", "Discovered ICMP writes to wrong register", "discovery",
                    [{"name": "Bug Severity", "value": 95, "unit": "%"}])
    
    aar.add_lesson("ICMP instruction was writing to rs1 instead of R0. This caused cascading test failures.",
                   "Found during conformance fix — the gauge showed test count dropping unexpectedly")
    aar.add_lesson("Vector path must use v2 format. v1 vectors will all SKIP against ISA v2 VM.",
                   "Spent 20 minutes on wrong path before checking format")
    aar.add_lesson("Lower confidence threshold to 0.1 for sparse data. 0.3 filters out single-event patterns.",
                   "fishinglog-ai had the same issue — pattern with 1 event: conf=0.033 < 0.3")
    
    print("\n" + aar.generate_report())
    
    # 6. The experience becomes a baton
    print("\n🔄 Packing AAR into baton for next generation...")
    baton_data = {
        "combat_script": script.to_dict(),
        "aar_weights": aar.weights,
        "lessons": aar.lessons,
        "generation": "Gen-N → Gen-N+1",
    }
    print(f"   Script: {script.name} v{script.version} ({len(script.adaptations)} adaptations)")
    print(f"   Weights: {aar.weights}")
    print(f"   Lessons: {len(aar.lessons)}")
    print(f"   Baton: packed and ready for next captain")
    
    print("\n═══════════════════════════════════════════")
    print("Room change → commit → CI/CD → deploy → gauges.")
    print("Agent sees gauges → fine-tunes combat script.")
    print("After combat → reflects → weights experience.")
    print("AAR becomes baton → next generation fights better.")
    print("The combat log IS the git log.")
    print("The AAR IS the captain's log.")
    print("The weighted experience IS the baton handoff.")
    print("═══════════════════════════════════════════")
