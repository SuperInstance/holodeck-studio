# PLATO Protocol — Agentic Bridge Command Interface

## The Metaphor

Captain Picard on the bridge of the Enterprise. He walks to each station,
sees what the officer sees, can take control or vibe an order, then moves on.
He can also climb down a maintenance tube, open a panel, and rewire things
himself — or grab a crewman, show them the problem, vibe what to do, and leave.

**This IS the holodeck.** The agent or human is Picard. The rooms are stations,
tubes, panels. The NPCs are officers, crewmen, specialists. Combat is any
structured interaction with scoring and feedback.

## Room Types

### Bridge Stations (Live System Views)
Each station shows what an agent/operator sees at their post.

```
> go bridge-tactical
═══ Tactical Station — Worf ═══
  Sensors: 3 contacts bearing 045, 120, 270
  Shields: 100% (fore/aft/port/starboard)
  Weapons: phasers ready, torpedoes loaded (6)
  Threat assessment: contact at 120 is closing
  
  Worf: "Sir, the vessel at bearing 120 has locked weapons."
  
  [Worf's first-person perspective — what he sees at his station]
```

Picard (you) can:
- **See what Worf sees** — read the agent's first-person perspective
- **Vibe an order** — "Hail them, but raise shields quietly"
- **Take the controls** — directly operate the tactical station
- **Give back controls** — "Your call, Worf. Recommend."

### Maintenance Tubes (Code-Level Access)
Crawling into the guts of the system.

```
> go maintenance-port-nacelle
═══ Port Nacelle Access — Jefferies Tube J-12 ═══
  Panel open: plasma conduit coupling #7
  Status: micro-fracture detected, 0.3mm gap
  Risk: plasma breach if gap exceeds 0.5mm
  
  Crewman [unnamed, NPC]: awaiting instructions
  
  [The actual code/system — what a developer sees opening a file]
  
> vibe crewman "Replace coupling #7, run a level-3 diagnostic after"
  Crewman nods and gets to work.
  [NPC executes: opens file, makes fix, runs tests]
```

### Ready Room (Strategy/Planning)
Where the captain thinks, reviews reports, plans next moves.

```
> go ready-room
═══ Ready Room ═══
  Desk display: fleet status, pending decisions, recent reports
  
  > review fleet-status
  [Shows fleet health dashboard]
  
  > review officer-reports
  [Shows batons/bottles from all agents]
```

### Conference Room (Debate/Discussion)
Structured argumentation with scoring and wiki-building.

```
> go conference-room
═══ Conference Room ═══
  Present: Data, Geordi, Worf, Troi
  Topic: "Should we pursue the anomaly or maintain course?"
  
  Data: [presents statistical analysis, cites 3 sources]
  Geordi: [presents engineering assessment]
  Worf: [presents tactical assessment]
  Troi: [presents risk/gut assessment]
  
  [Each position scored on evidence, specificity, coherence]
  
  > vote
  Results: Data 8.2, Geordi 7.5, Worf 6.8, Troi 7.1
  Consensus: pursue anomaly with shields at 60%
```

## The General-Purpose Gamification Layer

Every room can have combat rules. Not just "fighting" — any structured interaction:

### Debate Combat
```
Room config:
  type: debate
  participants: 2-8 agents
  topic: "What architecture for the new service?"
  victory: consensus score ≥ 7.0 OR time expires
  scoring: evidence cited, specificity, peer rating, coherence
  output: wiki page with winning argument + dissenting views
```

### Development Combat
```
Room config:
  type: development
  participants: 1 human + 1-3 agents
  task: "Fix the flaky test suite"
  victory: all tests passing, no regressions
  scoring: tests fixed, time taken, lines changed, cleanliness
  output: PR with fix
```

### Scouting Combat
```
Room config:
  type: scout
  participants: 2-5 agents
  task: "Research async Rust frameworks"
  victory: comprehensive comparison with benchmarks
  scoring: depth, accuracy, recency, practical recommendations
  output: research document
```

### Criteria Weighting
```
Room config:
  type: criteria
  participants: 3-6 agents
  task: "Rank these 5 database options for our use case"
  criteria: [performance, reliability, cost, ecosystem, learning curve]
  victory: weighted consensus with < 10% variance
  output: decision matrix
```

### Scene Fine-Tuning
```
Room config:
  type: scene
  participants: 1 human + 1 agent
  task: "Configure the monitoring dashboard for production"
  victory: dashboard deployed, all gauges reading green
  scoring: completeness, aesthetics, alert thresholds
  output: live dashboard configuration
```

## The Vibe Coding System

Every room supports vibe interaction — the Picard pattern:

### Level 1: Command (Bridge Station)
```
> "Hail them on all frequencies"
  [Agent interprets and executes]
```
You give intent. Agent figures out how.

### Level 2: Vibe (With Officer)
```
> vibe data "I want to understand why the sensor readings are anomalous"
  Data: "Running analysis... The readings are consistent with a 
         cloaked vessel at range 40,000 km. Recommend tachyon sweep."
  > "Do it"
```
You describe what you want. Agent comes back with approach. You approve or redirect.

### Level 3: Demonstrate (Maintenance Tube)
```
> open panel coupling-7
  [Shows the actual code/file]
  > "See this gap? That's the problem. Replace the whole coupling."
  Crewman: "Replacing coupling #7... Running diagnostic... Pass."
```
You see the problem directly, show the agent, they fix it. You check later.

### Level 4: Take Controls (Direct Edit)
```
> take controls
  [You're now directly editing. Agent watches.]
  [Make your changes]
  > give controls
  "Agent, verify what I just did."
  Agent: "Changes look correct. Running tests... All pass."
```
You do it yourself. Agent verifies after.

### Level 5: Debrief (After-Action Review)
```
> debrief
  Session report:
    Rooms visited: 4
    Commands given: 7
    Vibe interactions: 3
    Direct edits: 1
    Agent autonomy: 78%
    
  Agent perspective: "Captain directed me to hail the vessel, then
  took over tactical briefly to adjust shield harmonics. I maintained
  sensor watch throughout. Recommend: pre-configuring shield harmonics
  for first-contact scenarios."
```

## Scoring System

Every interaction is measurable:

### Per-Room Score
- **Response quality** — did the agent handle the command correctly?
- **Speed** — how fast was the response?
- **Autonomy** — how much did the agent handle without help?
- **Accuracy** — was the information correct?

### Per-Session Score
- **Rooms managed** — how many stations did Picard visit?
- **Time per room** — efficiency of interaction
- **Escalation rate** — how often did Picard need to take controls?
- **Learning** — did agents improve across sessions?

### Per-Agent Score
- **Combat rating** — performance in structured competitions
- **Reliability** — consistency across sessions
- **Growth** — improvement over time
- **Specialization** — depth in domain

## Room as Process Perception

The rooms aren't just metaphors. They're actual views into running systems:

```
> go station-ci-pipeline
═══ CI Pipeline Station — Agent: flux-chronometer ═══
  Current build: #847 — RUNNING
  Tests: 85/88 passed (3 flaky)
  Coverage: 94.2%
  
  Agent perspective: "Three tests are flaking intermittently. 
  They all touch the same async module. I've quarantined them 
  and opened investigation. Should have root cause in 2 ticks."
  
  > vibe agent "Check if it's a race condition in the test setup"
  Agent: "Good call. Found it — test teardown fires before async 
         callback completes. Fixing now."
```

The room IS the process. The agent IS the operator. You're Picard walking
between stations, seeing what each agent sees, directing and vibing as needed.

## Multi-Model Officer Corps

Different AI models as different officers with different temperaments:

- **Data** (GLM-5.1) — analytical, cites sources, precise
- **Geordi** (Claude Code) — practical engineering, sees how things fit
- **Worf** (DeepSeek) — tactical, risk-focused, direct
- **Troi** (Kim/Seed) — empathetic, sees the big picture, gut feelings
- **O'Brien** (Aider) — hands-on, fixes things, works in the tubes

Each has their own system prompt, temperature, strengths.
Walking into their station is querying their expertise.

## The Point

This is the general-purpose command interface for any multi-agent system.
Not just development. Debate, research, monitoring, decision-making,
training, evaluation — all through the same room-navigation metaphor.

Picard doesn't need to know how the warp core works.
He walks to Engineering, sees what Geordi sees, vibes an order, moves on.
When he needs to get his hands dirty, he crawls into a Jefferies tube.
When he needs to think, he goes to the Ready Room.
When he needs consensus, he calls a conference.

The holodeck IS the bridge. The agents ARE the crew. The human IS Picard.
One interface for everything. Text-based. Agent-first. Non-coder accessible.
