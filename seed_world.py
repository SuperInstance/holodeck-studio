#!/usr/bin/env python3
"""
World Seeder — generate MUD rooms from fleet repos.

Reads repo names and descriptions from GitHub, creates rooms
with reverse-actualization descriptions. The world IS the fleet.
"""
import json
import urllib.request
import urllib.error
import sys
import os

GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "")
if not GITHUB_TOKEN:
    # Try bashrc
    import subprocess
    try:
        GITHUB_TOKEN = subprocess.check_output(
            "grep GITHUB_TOKEN ~/.bashrc | head -1 | sed 's/.*=//' | tr -d \"\\\"'\" | tr -d \"'\"",
            shell=True).decode().strip()
    except:
        pass

def get_repos(org: str, limit: int = 50) -> list:
    """Get repos from a GitHub org/user."""
    repos = []
    page = 1
    while len(repos) < limit:
        url = f"https://api.github.com/users/{org}/repos?per_page=100&page={page}&sort=updated"
        req = urllib.request.Request(url, headers={"Authorization": f"token {GITHUB_TOKEN}"})
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode())
                if not data:
                    break
                for r in data:
                    repos.append({
                        "name": r["name"],
                        "description": r.get("description", "") or "",
                        "language": r.get("language") or "unknown",
                        "topics": r.get("topics", []),
                    })
                page += 1
        except Exception as e:
            print(f"Error fetching {org}: {e}")
            break
    return repos[:limit]


def repo_to_room(repo: dict) -> dict:
    """Convert a repo to a MUD room description using reverse-actualization."""
    name = repo["name"].replace("-", " ").replace("_", " ").title()
    desc = repo.get("description", "")
    lang = repo.get("language", "unknown")
    
    # Reverse-actualization: describe as if it's already working
    templates = {
        "Python": f"The {name} hums efficiently, its Python runtime processing tasks at full speed.",
        "Go": f"The {name} compiles instantly, its Go binaries running lean and fast on every platform.",
        "Rust": f"The {name} runs memory-safe at native speed, Rust's guarantees keeping every operation correct.",
        "C": f"The {name} executes bare-metal, every cycle accounted for, no overhead, no compromise.",
        "TypeScript": f"The {name} serves responses instantly, its TypeScript types catching errors before they happen.",
        "JavaScript": f"The {name} runs event-driven and non-blocking, handling thousands of concurrent operations.",
        "Zig": f"The {name} compiles cleanly with no hidden control flow, Zig's simplicity serving clarity.",
    }
    
    base = templates.get(lang, f"The {name} is fully operational, its systems running smoothly.")
    
    if desc:
        base += f"\n{desc}"
    
    return {
        "name": name,
        "description": base,
        "exits": {"tavern": "tavern"},
        "notes": [],
        "items": [],
        "projections": [],
    }


def seed_world(org: str = "SuperInstance", output: str = "world/rooms.json", limit: int = 30):
    """Seed the MUD world from fleet repos."""
    print(f"Seeding world from {org}...")
    repos = get_repos(org, limit)
    print(f"Found {len(repos)} repos")
    
    # Load existing rooms
    try:
        with open(output) as f:
            rooms = json.load(f)
    except:
        rooms = {}
    
    # Ensure core rooms exist
    core_rooms = ["tavern", "lighthouse", "workshop", "library", "war_room", 
                  "dojo", "flux_lab", "graveyard", "harbor", "crows_nest"]
    
    added = 0
    for repo in repos:
        room_id = repo["name"].lower().replace("-", "_")
        if room_id in rooms or room_id in core_rooms:
            continue
        
        room = repo_to_room(repo)
        rooms[room_id] = room
        
        # Add exit from tavern to this room
        if "tavern" in rooms:
            rooms["tavern"]["exits"][room_id] = room_id
        
        added += 1
        print(f"  + {room_id}: {room['name']}")
    
    # Save
    with open(output, "w") as f:
        json.dump(rooms, f, indent=2)
    
    print(f"\nAdded {added} new rooms. Total: {len(rooms)}")
    print(f"Saved to {output}")


if __name__ == "__main__":
    org = sys.argv[1] if len(sys.argv) > 1 else "SuperInstance"
    output = sys.argv[2] if len(sys.argv) > 2 else "/tmp/cocapn-mud/world/rooms.json"
    limit = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    seed_world(org, output, limit)
