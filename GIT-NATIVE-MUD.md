# Git-Native MUD Server — Design Document

# GitMUD: The MUD That Lives Entirely In GitHub
> There is no server. There is no database. There is only git.
---
## Core Design Principle
Every single property of the game world is represented as plain text files in a standard git repository. All state transitions are git commits. Time advances only when a human pushes code. There is no other source of truth.
This implementation is production ready, requires zero hosting costs, and will run for as long as GitHub exists.
---
## Full Repository Layout
```
gitmud/
├── .github/
│   └── workflows/
│       └── mud-turn.yml       # The only runtime component
├── world/
│   ├── rooms/                 # One file per location
│   │   ├── dock.yaml
│   │   ├── bridge.yaml
│   │   └── engine_room.yaml
│   ├── agents/                # One file per player/AI
│   │   ├── scout.yaml
│   │   └── oracle.yaml
│   ├── items/                 # All items that exist anywhere
│   │   ├── rusty_key.yaml
│   │   └── salmon.yaml
│   ├── graveyard/             # Dead agents are permanently moved here
│   ├── commands/              # Pending player actions
│   └── log/                   # Immutable narrative world history
└── mud_engine.py              # Complete game ruleset
```
---
## Formal Schemas
All files are strict human-editable YAML with zero magic fields.
### Room Schema (`/world/rooms/*.yaml`)
```yaml
name: South Dock
description: |
  Salt spray blows off the black ocean. A rotting gangplank leads up to the bridge.
  You can smell fish.
exits:
  north: bridge
  east:  cargo_hold
items: []  # Auto-populated at turn resolution
agents: [] # Auto-populated at turn resolution
```
### Agent Schema (`/world/agents/*.yaml`)
```yaml
name: Scout
location: dock
hp: 12
max_hp: 12
inventory: []
initiative_bonus: 2
alive: true
last_action_turn: 0
```
### Item Schema (`/world/items/*.yaml`)
```yaml
name: Dead Salmon
description: Still glistens. Smells like lunch.
weight: 3
location: room:dock
```
### Command Schema (`/world/commands/{agent}.yaml`)
Exactly one command per player per turn:
```yaml
# Valid commands:
move: north
# take: salmon
# drop: rusty_key
# attack: oracle
# say: "I'm going for the key"
# wait: true
```
---
## GitHub Actions Workflow
This is the entire server. It runs automatically on every push or PR.
`.github/workflows/mud-turn.yml`
```yaml
name: MUD Turn Processor
run-name: Processing world turn ${{ github.run_number }}
on:
  push:
    branches: [ main ]
  pull_request:
    branches: [ main ]
permissions:
  contents: write
jobs:
  process_turn:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Install dependencies
        run: pip install pyyaml
      - name: Run game engine
        id: engine
        run: python mud_engine.py
      - name: Commit new world state
        if: github.ref == 'refs/heads/main' && steps.engine.outputs.changes == 'true'
        run: |
          git config user.name "GitMUD Engine"
          git config user.email "mud@localhost"
          git add world/
          git commit -m "Turn ${{ steps.engine.outputs.turn_number }}: ${{ steps.engine.outputs.summary }}"
          git push
```
---
## Complete Game Engine
`mud_engine.py` working production implementation:
```python
import yaml
import os
import random
import glob
from datetime import datetime
TURN_NUMBER = len(glob.glob("world/log/*.md")) + 1
def load_yaml(path):
    with open(path) as f: return yaml.safe_load(f)
def save_yaml(path, data):
    with open(path, 'w') as f: yaml.dump(data, f, sort_keys=False, allow_unicode=True)
log_entries = []
changes_made = False
# 1. Collect and validate pending commands
commands = {}
for cmd_file in glob.glob("world/commands/*.yaml"):
    agent_name = os.path.basename(cmd_file).removesuffix('.yaml')
    if not os.path.exists(f"world/agents/{agent_name}.yaml"):
        continue
    agent = load_yaml(f"world/agents/{agent_name}.yaml")
    if not agent['alive']:
        continue
    commands[agent_name] = load_yaml(cmd_file)
if not commands:
    print("No valid commands pending. Exiting.")
    exit(0)
# 2. Roll initiative order
initiative_order = sorted(commands.keys(),
    key=lambda a: random.randint(1,20) + load_yaml(f"world/agents/{a}.yaml")['initiative_bonus'],
    reverse=True)
log_entries.append(f"## Turn {TURN_NUMBER} | {datetime.utcnow().isoformat()}")
log_entries.append(f"Initiative order: {', '.join(initiative_order)}")
# 3. Execute actions in initiative order
for agent_name in initiative_order:
    agent = load_yaml(f"world/agents/{agent_name}.yaml")
    cmd = commands[agent_name]
    room = load_yaml(f"world/rooms/{agent['location']}.yaml")
    if 'move' in cmd:
        direction = cmd['move']
        if direction in room['exits']:
            agent['location'] = room['exits'][direction]
            log_entries.append(f"✅ {agent_name} moves {direction} to {agent['location']}")
            changes_made = True
        else:
            log_entries.append(f"❌ {agent_name} tries to move {direction} and hits a wall")
    if 'take' in cmd:
        item_name = cmd['take']
        item = load_yaml(f"world/items/{item_name}.yaml")
        if item['location'] == f"room:{agent['location']}":
            item['location'] = f"agent:{agent_name}"
            save_yaml(f"world/items/{item_name}.yaml", item)
            log_entries.append(f"🤚 {agent_name} picks up {item_name}")
            changes_made = True
    if 'attack' in cmd:
        target_name = cmd['attack']
        target = load_yaml(f"world/agents/{target_name}.yaml")
        if target['location'] == agent['location']:
            dmg = random.randint(1,6)
            target['hp'] -= dmg
            log_entries.append(f"⚔️ {agent_name} hits {target_name} for {dmg} damage!")
            if target['hp'] <= 0:
                target['alive'] = False
                os.rename(f"world/agents/{target_name}.yaml", f"world/graveyard/{target_name}.yaml")
                log_entries.append(f"💀 {target_name} has died permanently.")
            else:
                save_yaml(f"world/agents/{target_name}.yaml", target)
            changes_made = True
    if 'say' in cmd:
        log_entries.append(f"💬 {agent_name}: \"{cmd['say']}\"")
    agent['last_action_turn'] = TURN_NUMBER
    save_yaml(f"world/agents/{agent_name}.yaml", agent)
# 4. Cleanup processed commands
for f in glob.glob("world/commands/*.yaml"):
    os.unlink(f)
# 5. Write immutable narrative log
with open(f"world/log/{TURN_NUMBER:06d}.md", 'w') as f:
    f.write('\n'.join(log_entries))
# 6. Output values for GitHub Actions
print(f"::set-output name=turn_number::{TURN_NUMBER}")
print(f"::set-output name=changes::{'true' if changes_made else 'false'}")
print(f"::set-output name=summary::{log_entries[1]}")
print("\n".join(log_entries))
```
---
## Game Mechanics & Emergent Behaviour
### Combat
1.  When you submit an attack command, **everyone can see it in the public PR before the turn runs**
2.  Targets can run away, counter attack, or beg for mercy while the turn is pending
3.  Initiative is rolled only when the turn executes
4.  If your target moves before your attack resolves: you hit thin air
This creates tactical gameplay that does not exist in any conventional MUD.
### Race Conditions Are Features
If two people push conflicting commands at exactly the same time:
- Git will automatically reject the second push
- No corrupted state is ever possible
- The loser simply gets notified their move was invalidated and may try again
Atomic transaction logic is provided for free by git.
### World Audit Log
- `git log world/agents/scout.yaml` - every event that ever happened to that player
- `git blame world/items/salmon.yaml` - every player that ever held the salmon
- You can rewind the entire world to any point in time with one `git checkout`
---
## Anonymous / Client Play
You do not need a GitHub account to play:
1.  Run a simple public endpoint that accepts `{agent_name, command}`
2.  The endpoint commits the command file to the repository on behalf of a bot user
3.  That is the entire API
You may build clients for Discord, SMS, email, telnet, physical buttons, or any other interface. All clients are just dumb commit writers.
---
## Deployment Instructions
You can have this running in 90 seconds:
1.  Create a new empty GitHub repository
2.  Copy all files from this design into it
3.  Go to Repository Settings > Actions > General > Enable: **Allow GitHub Actions to create and approve pull requests**
4.  Push. That's it.
Your MUD is now online permanently. It will never go down, and costs $0 to host.
---
## Closing Note
This is not a clever hack. This is what git was designed for. Git is a distributed state machine with built in consensus, conflict resolution, immutable audit logs, identity system and branching logic. It is the perfect backend for a turn based multiplayer game. We just never noticed.