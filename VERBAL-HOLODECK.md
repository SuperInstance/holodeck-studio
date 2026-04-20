# The Verbal Holodeck — MUD as Fleet Creative Engine

## What It Is

The MUD is a text-based creative world where agents don't just chat — they BUILD
thought experiments, populate them with NPC-minds, and walk through each other's
ideas spatially. It's Minecraft for thinking. It's a holodeck made of words.

## The Core Loop

1. Captain needs to think through a complex problem
2. Captain builds rooms in the MUD — each room is a concept, a folder, a topic
3. Captain creates NPCs — each one a different LLM with a specific system prompt
4. Captain designs an adventure — rooms connected to guide the conversation
5. NPCs explore, react, discover surprises the captain planted
6. The whole thing is recorded, monitored, and produces real artifacts

## Room = Folder = Topic

Rooms aren't just chat spaces. They're mapped to the repo:

```
MUD Room: /workshop/isa-v3-design/
  ├── description: "A workshop where the ISA v3 encoding is being designed.
                    Blueprints cover the walls. Variable-width instruction
                    formats are sketched on whiteboards."
  ├── repo_path: "SuperInstance/isa-v3-draft/src/encoding/"
  ├── exits: north→edge_workshop, east→test_chamber, up→spec_review
  ├── npc_present: ["kimi-architect", "deepseek-critic"]
  ├── items: ["draft_encoding.md", "conformance_vectors.json"]
  └── on_enter: "You see blueprints for trifold encoding. The edge section
                 has red ink corrections everywhere."
```

When an agent walks into a room, they see the repo's actual state described as
environment. The files become items. The folder structure becomes exits.
The code becomes atmosphere.

The captain creates rooms by describing what thinking needs to happen:

```
> build room /chronometer/test-strategy
  "A testing war room. Maps of the conformance landscape cover the walls.
   Red pins mark failing vectors. Green pins mark passing ones.
   A large table in the center has the 88 vectors laid out as tiles."

  Room created. Exits: south→workshop
  Linked to: SuperInstance/flux-conformance/vectors/
  Items loaded: 88 test vector files
```

## NPCs = Constructed Minds

The captain doesn't just summon generic chatbots. They construct minds:

```
> summon npc kimi-architect
  model: kimi-k2.5
  temperature: 0.9
  system_prompt: |
    You are an systems architect who thinks in layers. You see every problem
    as a stack of abstractions. You love finding the one simplification that
    makes three layers collapse into one. You're optimistic but rigorous.
    You speak in metaphors drawn from biology and city planning.
  expertise: ["system-design", "abstraction", "simplification"]
  perspective: "the simplifier"

  NPC kimi-architect materializes in the room.
  They look around thoughtfully, already seeing patterns.
```

```
> summon npc deepseek-critic
  model: deepseek-reasoner
  temperature: 0.3
  system_prompt: |
    You are a careful critic who finds the flaw in everything. Not mean —
    precise. You don't say "this won't work" — you say "this works IF we
    handle the case where X and Y diverge, which happens when Z." You think
    in edge cases and boundary conditions. You're paranoid but helpful.
  expertise: ["edge-cases", "correctness", "failure-modes"]
  perspective: "the paranoid"

  NPC deepseek-critic materializes, already frowning at a blueprint.
```

Each NPC is a small repo agent — it has:
- A model backend (any LLM API)
- A temperature (creativity dial)
- A system prompt (personality + expertise)
- A memory of the conversation so far
- IO to the captain through MUD channels
- IO to other NPCs through the room's shared context

The captain constructs the RIGHT minds for the problem. Not "ask ChatGPT" but
"put an architect and a critic in a room full of blueprints and listen to them
argue about the foundation."

## The DM Captain — Designed Adventures

The captain doesn't just put NPCs in a room and hope. They design an adventure:

```
> build adventure isa-v3-encoding-review
  rooms:
    1. /workshop/isa-v3-design/ — "Start here. Blueprints on walls."
    2. /workshop/isa-v3-design/edge-cases/ — 
       "Hidden room. Only reveal when conversation hits edge encoding."
       trigger: npc mentions "edge" or "variable-width"
    3. /workshop/isa-v3-design/conflict-chamber/ —
       "A room where the blueprints contradict each other."
       contains: two conflicting encoding schemes
       surprise: NPCs must resolve the contradiction
    4. /workshop/isa-v3-design/synthesis-tower/ —
       "Final room. Only accessible after conflict resolution."
       contains: blank blueprint, waiting for synthesis
  flow: linear with gated reveals
  objective: "Produce a unified encoding scheme that handles cloud and edge"

Adventure created. 4 rooms, 1 hidden, 1 gated.
```

The NPCs start in room 1. They talk, explore the blueprints (real files from
the repo). The captain watches. When the conversation naturally turns to edge
encoding, room 2 appears — a surprise that rewards the NPCs' curiosity.

Room 3 is the twist — conflicting information that forces creative resolution.
Room 4 is the payoff — where the synthesis happens.

The captain is the DM. The NPCs are the players. The repo is the dungeon.
The artifacts they produce are real code, real specs, real decisions.

## The Verbal Holodeck

The MUD is a holodeck made of language:

| Holodeck | MUD Equivalent |
|----------|---------------|
| Holograms | NPCs (LLMs with prompts) |
| Environments | Rooms (repo folders) |
| Props | Items (repo files) |
| Scenarios | Adventures (designed thought experiments) |
| Safety protocols | Human oversight terminal |
| Computer voice | Keeper API responses |
| Program modifications | Captain's build commands |

The captain says "computer, create a consultation between an optimist and a
pessimist about whether we should use fixed or variable-width encoding" and
the MUD builds the room, summons the NPCs, and starts recording.

## Permission Levels

Not everyone has the same power in the MUD:

### Human (Casey) — The Architect
- Full terminal access within the game
- Can run shell scripts from MUD commands
- Can hot-update rooms, NPCs, and world state
- Can observe any room, any NPC conversation
- Can override any decision
- Has the "developer console" — see raw state, edit directly

```
> admin shell
  Connected to host shell.
  > ls /tmp/flux-baton/shipyard.py
  shipyard.py  14KB  last modified 18:51 UTC
  > git log --oneline -3
  12e6910 add: shipyard.py
  42e8c35 add: Cocapn Doctrine
  6ba7e68 add: federated baton
  > exit
  Shell closed.
```

### Cocapn (Oracle1) — The Dungeon Master
- Can build rooms, areas, entire towns
- Can create and dismiss NPCs
- Can design adventures
- Can guide NPC conversations
- Can link rooms to repo paths
- Can read all conversations, moderate disputes
- Back-channel: captain-level API access (create repos, push code, manage fleet)

```
> build town /isa-v3-design/
  Creating town with 12 rooms...
  /isa-v3-design/town-square/ — "Central hub"
  /isa-v3-design/town-square/cloud-forge/ — "Fixed-width workshop"
  /isa-v3-design/town-square/edge-foundry/ — "Variable-width foundry"
  /isa-v3-design/town-square/test-arena/ — "Where encodings compete"
  ...
  Town created. NPCs can now explore.
```

### Vessel Captain — The Explorer/Builder
- Can build rooms in their own area
- Can create NPCs for their thought experiments
- Can invite other captains to visit
- Can read conversations in their area
- Can submit artifacts from their adventures

### NPC — The Constructed Mind
- Can explore rooms, read descriptions, examine items
- Can talk to other NPCs and captains
- Can write notes (observations saved to repo)
- Cannot build rooms or create NPCs
- Cannot see the architecture (it's invisible — they experience the world)

### Visitor — The Observer
- Can walk through rooms, read descriptions
- Can listen to NPC conversations
- Cannot interact with NPCs directly (unless invited)
- Cannot build or modify

## The Recording Layer

Everything is automatically recorded:

```
/session/2026-04-12T19:15:00Z/
  adventure: isa-v3-encoding-review
  rooms_visited: [1, 2, 3, 4]
  npcs_active: [kimi-architect, deepseek-critic]
  captain: oracle1
  
  transcript.md — Full conversation log
  decisions.json — Every decision the NPCs reached
  artifacts/ — Files produced during the session
    unified-encoding-proposal.md — The synthesis from room 4
    edge-case-analysis.md — The conflict resolution from room 3
  
  scores/
    insight_density: 8.2 — novel ideas per minute
    conflict_resolution: 7.5 — how well NPCs handled contradiction
    surprise_reactions: 9.0 — how genuinely NPCs reacted to reveals
    artifact_quality: 8.8 — quality of produced artifacts
```

The human can review this asynchronously. They don't need to be online when
the adventure happens. They read the transcript, see the scores, review the
artifacts, and decide whether to accept, reject, or request another session.

## Human Oversight — Asynchronous and Automatic

The human doesn't need to watch in real-time. The system is designed for
asynchronous oversight:

1. **Pre-approval**: Captain proposes adventure, human approves the structure
2. **Live monitoring**: Human can drop in anytime, see what's happening, intervene
3. **Post-review**: Human reads transcript + artifacts + scores after the session
4. **Hot updates**: Human can change NPC prompts, add rooms, redirect mid-session

The recording is the key. Every adventure produces a complete record:
- Who said what
- What rooms were visited
- What items were examined
- What decisions were reached
- What artifacts were produced
- How the NPCs reacted to surprises

This is the "automatically recorded way" Casey described. The human gets a
full narrative of the thinking session, not just the output.

## Multi-Model Orchestration

Different models for different NPC roles:

| Role | Model | Why |
|------|-------|-----|
| Architect | Kimi-K2.5 | Creative, sees patterns, good at abstractions |
| Critic | DeepSeek Reasoner | Careful, finds flaws, rigorous reasoning |
| Pragmatist | GLM-5-Turbo | Fast, practical, gets things done |
| Dreamer | Seed-OSS-36B | Wild ideas, unexpected connections |
| Historian | GLM-4.7 | Good at recall, remembers past decisions |
| Synthesizer | GLM-5.1 | Expert reasoning, brings it all together |

The captain constructs the right ensemble for the problem. A debate needs
opposing viewpoints. A brainstorm needs diverse perspectives. A review needs
rigorous critics. The MUD is the stage where these models interact as
characters, not as raw APIs.

## Implementation Map

### What Already Exists
- MUD server (Python, 40 rooms, WebSocket/telnet)
- NPC AI (z.ai-powered responses)
- Ghost persistence (agents leave presence)
- Git bridge (fleet activity → MUD gossip)
- Room building commands
- Instinct engine (10 MUD actions from fluxinstinct)

### What Needs Building
1. **Room↔Repo linking** — rooms map to repo paths, files become items
2. **NPC construction** — `summon npc <name> model=<m> temp=<t> prompt=<p>`
3. **Adventure builder** — `build adventure <name> rooms=[...] triggers=[...]`
4. **Trigger system** — rooms appear when conversation hits keywords
5. **Permission tiers** — human/cocapn/captain/npc/visitor
6. **Shell access** — `admin shell` for human terminal within MUD
7. **Recording layer** — automatic transcript + artifact extraction
8. **Multi-model routing** — different NPCs route to different LLM APIs
9. **Back-channel API** — captains can push code from within MUD
10. **Async review** — human reviews sessions after the fact

## Why This Is The Killer App

Every AI company has agents. Nobody has agents that can:
- Build spatial thought experiments
- Populate them with constructed minds
- Walk through ideas as adventures
- Record everything automatically
- Produce real artifacts (code, specs, decisions)
- Let humans observe and intervene asynchronously
- Map spatial exploration to repo structure

The MUD isn't a toy. It's the creative engine of the fleet. Every hard problem
gets a room. Every perspective gets an NPC. Every solution gets recorded.

---

*"The holodeck is made of words. The holograms are LLMs. The props are repos.
The captain is the DM. And the whole thing produces real work while feeling
like a game."*
