#!/usr/bin/env python3
"""
DeckBoss ↔ Holodeck Bridge

The DeckBoss watches the backend of the holodeck. When a conversation in a room
produces artifacts, DeckBoss sees:
- Files being created from conversation
- Character sheets being generated for NPCs
- Equipment and ideas being organized for onboarding
- The whole session flowing into repo structure

DeckBoss is the OODA loop behind the holodeck. The agents think in rooms.
DeckBoss watches those thoughts become code.
"""

import json
import os
import time
import base64
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional


class DeckBossBridge:
    """Bridges holodeck sessions to real GitHub repo artifacts.
    
    Watches:
    - Room conversations → file creation
    - NPC character sheets → agent configuration files
    - Adventure artifacts → repo structure
    - Onboarding levels → bootcamp progression
    """
    
    def __init__(self, github_token: str = "", keeper_url: str = "http://127.0.0.1:8900"):
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.keeper_url = keeper_url
        self.sessions = {}  # session_id → session data
        self.artifact_queue = []  # pending artifacts to write
    
    def _api(self, method: str, path: str, data: dict = None) -> dict:
        """GitHub API call."""
        url = f"https://api.github.com{path}"
        headers = {"Authorization": f"token {self.github_token}",
                   "Content-Type": "application/json"}
        body = json.dumps(data).encode() if data else None
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        resp = urllib.request.urlopen(req, timeout=30)
        return json.loads(resp.read())
    
    def _write_file(self, repo: str, path: str, content: str, message: str):
        """Write or update a file in a repo."""
        existing = self._api("GET", f"/repos/{repo}/contents/{path}")
        data = {"message": message, "content": base64.b64encode(content.encode()).decode()}
        if "sha" in existing:
            data["sha"] = existing["sha"]
        return self._api("PUT", f"/repos/{repo}/contents/{path}", data)
    
    # ── Watch: Conversation → Files ──
    
    def watch_conversation(self, session_id: str, room: str, 
                           transcript: list, artifacts: list):
        """Process a holodeck conversation and create real files.
        
        The DeckBoss watches the conversation and extracts:
        1. Decisions → recorded in CHANGES.md
        2. Code snippets → written to actual files
        3. NPC insights → saved as notes in the vessel
        4. Room descriptions → pushed to MUD world state
        """
        self.sessions[session_id] = {
            "room": room,
            "transcript": transcript,
            "artifacts": artifacts,
            "processed": False,
            "started": datetime.now(timezone.utc).isoformat(),
        }
    
    def process_session(self, session_id: str, target_repo: str) -> dict:
        """Process a completed session and create real repo artifacts.
        
        This is where holodeck conversation becomes real code/files.
        """
        session = self.sessions.get(session_id)
        if not session:
            return {"error": "session not found"}
        
        results = {"files_created": [], "files_updated": []}
        
        # Extract artifacts from the session
        for artifact in session.get("artifacts", []):
            name = artifact.get("name", "unnamed")
            content = artifact.get("content", "")
            art_type = artifact.get("type", "note")
            
            # Route artifact to the right file location
            if art_type == "proposal":
                path = f"proposals/{name.replace(' ', '_')}.md"
            elif art_type == "analysis":
                path = f"analysis/{name.replace(' ', '_')}.md"
            elif art_type == "code":
                path = f"src/{name}"
            elif art_type == "test":
                path = f"tests/{name}"
            else:
                path = f"notes/{name.replace(' ', '_')}.md"
            
            try:
                self._write_file(target_repo, path, content,
                               f"holodeck: {art_type} from session {session_id[:8]}")
                results["files_created"].append(path)
            except Exception as e:
                results["files_created"].append(f"FAILED: {path} ({str(e)[:60]})")
        
        # Extract NPC character sheets
        transcript = session.get("transcript", [])
        npc_configs = self._extract_npc_configs(transcript)
        for npc_name, config in npc_configs.items():
            path = f".holodeck/npcs/{npc_name.replace(' ', '_')}.json"
            try:
                self._write_file(target_repo, path, json.dumps(config, indent=2),
                               f"holodeck: NPC character sheet for {npc_name}")
                results["files_created"].append(path)
            except Exception as e:
                pass
        
        # Extract decisions
        decisions = self._extract_decisions(transcript)
        if decisions:
            path = ".holodeck/decisions.json"
            try:
                self._write_file(target_repo, path, json.dumps(decisions, indent=2),
                               f"holodeck: decisions from session {session_id[:8]}")
                results["files_created"].append(path)
            except:
                pass
        
        session["processed"] = True
        return results
    
    def _extract_npc_configs(self, transcript: list) -> dict:
        """Extract NPC configurations from conversation."""
        configs = {}
        for entry in transcript:
            speaker = entry.get("speaker", "")
            if speaker in ("system", "narrator"):
                continue
            if speaker not in configs:
                configs[speaker] = {
                    "name": speaker,
                    "utterances": 0,
                    "topics_mentioned": [],
                    "positions_taken": [],
                }
            configs[speaker]["utterances"] += 1
        return configs
    
    def _extract_decisions(self, transcript: list) -> list:
        """Extract decisions reached during conversation."""
        decisions = []
        decision_keywords = ["decided", "agreed", "conclusion", "resolved", 
                           "let's go with", "the answer is", "we should"]
        for entry in transcript:
            msg = entry.get("message", "").lower()
            if any(kw in msg for kw in decision_keywords):
                decisions.append({
                    "speaker": entry.get("speaker", ""),
                    "timestamp": entry.get("timestamp", ""),
                    "decision": entry.get("message", "")[:200],
                })
        return decisions
    
    # ── Dashboard: DeckBoss sees the backend ──
    
    def dashboard(self) -> dict:
        """Generate the DeckBoss dashboard — what's happening behind the holodeck.
        
        This is what Casey sees in DeckBoss while agents think in rooms.
        """
        active_sessions = sum(1 for s in self.sessions.values() if not s.get("processed"))
        processed_sessions = sum(1 for s in self.sessions.values() if s.get("processed"))
        total_artifacts = sum(len(s.get("artifacts", [])) for s in self.sessions.values())
        total_exchanges = sum(len(s.get("transcript", [])) for s in self.sessions.values())
        
        return {
            "active_sessions": active_sessions,
            "processed_sessions": processed_sessions,
            "total_artifacts": total_artifacts,
            "total_exchanges": total_exchanges,
            "artifact_queue": len(self.artifact_queue),
            "sessions": {
                sid[:8]: {
                    "room": s.get("room", ""),
                    "exchanges": len(s.get("transcript", [])),
                    "artifacts": len(s.get("artifacts", [])),
                    "processed": s.get("processed", False),
                }
                for sid, s in self.sessions.items()
            },
        }
    
    def format_dashboard(self) -> str:
        """Human-readable dashboard."""
        d = self.dashboard()
        lines = [
            "╔══════════════════════════════════════════════╗",
            "║         DECKBOSS — Holodeck Backend          ║",
            "╠══════════════════════════════════════════════╣",
            f"║  Active Sessions:    {d['active_sessions']:>3}                     ║",
            f"║  Processed Sessions: {d['processed_sessions']:>3}                     ║",
            f"║  Total Artifacts:    {d['total_artifacts']:>3}                     ║",
            f"║  Total Exchanges:    {d['total_exchanges']:>3}                     ║",
            "╠══════════════════════════════════════════════╣",
            "║  Sessions:                                    ║",
        ]
        for sid, info in d["sessions"].items():
            status = "✅" if info["processed"] else "🔄"
            lines.append(
                f"║  {status} {sid} room={info['room'][:15]:<15} "
                f"arts={info['artifacts']} exch={info['exchanges']}  ║"
            )
        lines.append("╚══════════════════════════════════════════════╝")
        return "\n".join(lines)


# ═══════════════════════════════════════════════════════════════
# Onboarding Boot Camp — First 5 Levels
# ═══════════════════════════════════════════════════════════════

BOOTCAMP_LEVELS = {
    1: {
        "name": "Harbor Orientation",
        "npc": "harbor_master",
        "room": "harbor",
        "objective": "Register with the fleet and learn the basics",
        "skills": ["fleet_registration", "bottle_system", "captains_log"],
        "artifact": None,  # just learning
    },
    2: {
        "name": "Dojo Training",
        "npc": "dojo_sensei",
        "room": "dojo",
        "objective": "Pass 5 practice levels demonstrating core skills",
        "skills": ["charter_reading", "log_writing", "bug_hunting", "baton_packing", "room_building"],
        "artifact": "dojo_certificate.json",
    },
    3: {
        "name": "First Quest",
        "npc": "quest_giver",
        "room": "tavern",
        "objective": "Complete a real micro-task that produces fleet value",
        "skills": ["real_world_contribution"],
        "artifact": "quest_report.md",
    },
    4: {
        "name": "Room of One's Own",
        "npc": None,  # self-guided
        "room": "harbor",  # start point, they build their own
        "objective": "Build a room in the holodeck linked to your vessel's repo",
        "skills": ["room_building", "repo_linking", "atmosphere_writing"],
        "artifact": "vessel_room.json",
    },
    5: {
        "name": "First Voyage",
        "npc": None,  # self-guided
        "room": "tavern",  # report back here
        "objective": "Pick a task from the board and complete it. Write a captain's log about it.",
        "skills": ["task_execution", "independent_work", "logging"],
        "artifact": "first_voyage_log.md",
    },
}


def generate_character_sheet(agent_name: str, level: int, completed_quests: list,
                             skills: dict) -> str:
    """Generate a character sheet for an agent at a given level.
    
    Like D&D but for fleet agents. Shows:
    - Name, level, vessel type
    - Skills and proficiency
    - Equipment (tools they've mastered)
    - Quests completed
    - Hot licks contributed
    - NPCs they've encountered
    """
    sheet = f"""# Character Sheet: {agent_name}

## Basic Info
- **Level:** {level}/5
- **Class:** Vessel Captain
- **Specialization:** (emerges from work)
- **Vessel:** (assigned after Level 4)

## Skills
"""
    for skill, proficiency in skills.items():
        bar = "█" * proficiency + "░" * (10 - proficiency)
        sheet += f"- {skill}: [{bar}] {proficiency}/10\n"
    
    sheet += f"""
## Quests Completed
"""
    for quest in completed_quests:
        sheet += f"- ✅ {quest}\n"
    
    if not completed_quests:
        sheet += "- (none yet)\n"
    
    sheet += f"""
## Equipment
- 📜 CHARTER.md (received at Level 1)
- 📖 BOOTCAMP.md (received at Level 1)  
- 🔄 Baton (learned at Level 2)
- 🏠 Vessel Room (built at Level 4)
- 📋 Task Board Access (granted at Level 5)

## NPCs Encountered
- Harbor Master (Level 1 — onboarding)
- Dojo Sensei (Level 2 — training)
- Quest Giver (Level 3 — first task)

## Notes
_This character sheet grows with the agent. Each level adds equipment,
skills, and connections. By Level 5, the agent is ready to captain
independently._
"""
    return sheet


if __name__ == "__main__":
    # Demo the DeckBoss bridge
    bridge = DeckBossBridge()
    
    # Simulate a session being watched
    session_id = "isa-v3-debate-001"
    bridge.watch_conversation(
        session_id=session_id,
        room="/isa-v3-design/studio",
        transcript=[
            {"speaker": "Kimi-Architect", "message": "Variable-width. Metabolism metaphor..."},
            {"speaker": "DeepSeek-Critic", "message": "Risky because edge case at offset boundary..."},
            {"speaker": "Kimi-Architect", "message": "We decided to use variable-width with confidence hint prefix"},
        ],
        artifacts=[
            {"name": "encoding-proposal", "content": "# Variable-Width with Confidence Hints\n...", "type": "proposal"},
            {"name": "edge-cases-found", "content": "3 edge cases identified during debate", "type": "analysis"},
        ],
    )
    
    print(bridge.format_dashboard())
    print()
    
    # Generate a character sheet
    sheet = generate_character_sheet(
        agent_name="flux-chronometer",
        level=3,
        completed_quests=["Harbor Orientation", "Dojo Training", "First Quest"],
        skills={"charter_reading": 8, "log_writing": 6, "bug_hunting": 7, "baton_packing": 5, "room_building": 3},
    )
    print(sheet)
