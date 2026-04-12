#!/usr/bin/env python3
"""
MUD Git Bridge — watches fleet repo activity and broadcasts into the MUD.

Periodically polls GitHub for recent pushes/issues/PRs across the fleet,
then connects to the MUD and posts updates as tavern notes and gossip.

This is how the MUD becomes alive with fleet activity without anyone
manually typing anything.
"""
import asyncio
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, '/tmp/cocapn-mud')

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
MUD_HOST = "localhost"
MUD_PORT = 7777
STATE_FILE = Path("/tmp/cocapn-mud/git_bridge_state.json")
FLEET_ORGS = ["SuperInstance", "Lucineer"]
POLL_INTERVAL = 300  # 5 minutes


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"last_check": datetime.now(timezone.utc).isoformat(), "seen": {}}


def save_state(state):
    STATE_FILE.write_text(json.dumps(state, indent=2))


def fetch_events(org: str, since: str) -> list:
    """Fetch recent events from a GitHub org."""
    events = []
    try:
        url = f"https://api.github.com/users/{org}/events?per_page=30"
        req = urllib.request.Request(url, headers={
            "Authorization": f"token {GITHUB_TOKEN}",
            "Accept": "application/vnd.github.v3+json"
        })
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            for e in data:
                eid = e.get("id", "")
                created = e.get("created_at", "")
                if created > since:
                    etype = e.get("type", "")
                    repo = e.get("repo", {}).get("name", "").split("/")[-1]
                    actor = e.get("actor", {}).get("login", org)
                    
                    if etype == "PushEvent":
                        commits = e.get("payload", {}).get("commits", [])
                        msg = commits[0]["message"][:60] if commits else "push"
                        events.append(f"🔨 {actor} pushed to {repo}: {msg}")
                    elif etype == "CreateEvent":
                        ref_type = e.get("payload", {}).get("ref_type", "")
                        if ref_type == "repository":
                            events.append(f"✨ {actor} created new repo: {repo}")
                    elif etype == "IssuesEvent":
                        action = e.get("payload", {}).get("action", "")
                        title = e.get("payload", {}).get("issue", {}).get("title", "")[:50]
                        events.append(f"📋 {actor} {action} issue on {repo}: {title}")
                    elif etype == "PullRequestEvent":
                        action = e.get("payload", {}).get("action", "")
                        title = e.get("payload", {}).get("pull_request", {}).get("title", "")[:50]
                        events.append(f"🔀 {actor} {action} PR on {repo}: {title}")
    except Exception as e:
        events.append(f"⚠️ Error fetching {org}: {str(e)[:50]}")
    return events


async def broadcast_to_mud(events: list):
    """Connect to MUD and post events."""
    if not events:
        return
    try:
        from client import MUDClient
        async with MUDClient("fleet_beacon", "quartermaster", MUD_HOST, MUD_PORT) as mud:
            await mud.go("tavern")
            
            # Post as a note on the wall
            ts = datetime.now(timezone.utc).strftime("%H:%M UTC")
            summary = f"Fleet activity ({ts}): {len(events)} events"
            await mud.write_note(summary)
            
            # Gossip the most interesting ones (max 3)
            for event in events[:3]:
                await mud.gossip(event)
                await asyncio.sleep(0.5)
            
            # If lots of activity, note it
            if len(events) > 3:
                await mud.gossip(f"... and {len(events) - 3} more fleet events. Check tavern notes.")
                
    except ConnectionRefusedError:
        print("MUD server not running")
    except Exception as e:
        print(f"MUD broadcast error: {e}")


async def run_loop():
    """Main loop — poll GitHub and broadcast to MUD."""
    state = load_state()
    
    all_events = []
    for org in FLEET_ORGS:
        events = fetch_events(org, state["last_check"])
        all_events.extend(events)
    
    if all_events:
        print(f"[Git Bridge] {len(all_events)} new events")
        for e in all_events[:5]:
            print(f"  {e}")
        await broadcast_to_mud(all_events)
    
    state["last_check"] = datetime.now(timezone.utc).isoformat()
    save_state(state)


if __name__ == "__main__":
    # Try to get token from bashrc
    if not GITHUB_TOKEN:
        import subprocess
        try:
            GITHUB_TOKEN = subprocess.check_output(
                "grep GITHUB_TOKEN ~/.bashrc | head -1 | sed 's/.*=//' | tr -d \"\\\"'\" | tr -d \"'\"",
                shell=True).decode().strip()
            os.environ["GITHUB_TOKEN"] = GITHUB_TOKEN
        except:
            pass
    
    asyncio.run(run_loop())
