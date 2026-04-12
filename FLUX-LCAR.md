# FLUX-LCAR

## The Name

**FLUX-LCAR** — the PLATO/MUD interface for agentic inter-application asynchronous work.

Not a product. A paradigm. The text-based spatial interface that makes agent systems
legible to humans and humans legible to agents. Named for what it IS:

- **FLUX** — the runtime. Flowing, evolving, state transitions.
- **LCAR** — the interface. Live Command & Agent Routing.

Together: the runtime IS the interface. The bytecode IS the room description.

## The Hull Metaphor

```
┌─────────────────────────────────────────────────┐
│                                                   │
│  OUTSIDE THE HULL: The real world                 │
│  Salt water. Weather. Physics. Ground truth.      │
│  The hull MUST hold water. Non-negotiable.        │
│                                                   │
│  ┌───────────────────────────────────────────┐   │
│  │                                           │   │
│  │  THE HULL: Hardware                       │   │
│  │  ESP32s. Jetsons. Sensors. Servos.        │   │
│  │  This is what keeps the water out.        │   │
│  │  If the hull fails, nothing else matters. │   │
│  │                                           │   │
│  │  ┌───────────────────────────────────┐   │   │
│  │  │                                   │   │   │
│  │  │  INSIDE THE HULL: Crew Space      │   │   │
│  │  │                                   │   │   │
│  │  │  Equipment: Application code      │   │   │
│  │  │  Skills: Agent treatment code     │   │   │
│  │  │    (markdown, prompts, configs)    │   │   │
│  │  │  Models: Offloaded inference       │   │   │
│  │  │    (local Ollama, cloud API)       │   │   │
│  │  │                                   │   │   │
│  │  │  The crew NEVER touches the water. │   │   │
│  │  │  They get FEEDS from sensors.      │   │   │
│  │  │  They use TOOLS designed outside.  │   │   │
│  │  │  They exist in their sealed space. │   │   │
│  │  │                                   │   │   │
│  │  └───────────────────────────────────┘   │   │
│  │                                           │   │
│  └───────────────────────────────────────────┘   │
│                                                   │
│  The captain can go on deck. Agents cannot.       │
│  The captain can touch the water. Agents cannot.  │
│  The captain built the hull. Agents live in it.   │
│                                                   │
└─────────────────────────────────────────────────┘
```

## Ground Truth Hierarchy

```
1. THE HULL (Hardware) — must hold water. Everything else is software.
   If the ESP32 can't drive the rudder servo, no agent can steer.
   If the compass sensor is broken, no agent knows which way is north.
   Hardware IS the hull. It either holds water or it doesn't.
   
2. THE EQUIPMENT (Application Code) — what the crew uses to do their jobs.
   Navigation software. Engine monitoring. Communication protocols.
   If the equipment can't do the job from inside, the hull is useless
   no matter how intact it is. A watertight ship with broken radios
   is a raft.
   
3. THE SKILLS (Agent Treatment Code) — how the crew uses the equipment.
   Prompts, markdown configs, training procedures, decision trees.
   A skilled crew gets more from worse equipment than a green crew
   gets from the best equipment. Skills ARE the leverage.
   
4. THE MODELS (Offloaded Inference) — the crew's raw capability.
   Local models on Jetsons. Cloud models via Starlink.
   Often offloaded because the hull has limited compute.
   Better models = better crew. But models without skills waste capability.
   
5. THE FEEDS (Sensor Data) — the crew's ONLY window to the outside.
   The crew never touches the water. They see compass readings.
   They see depth soundings. They see wind speed.
   They see what the sensors show them. Nothing more.
   If the feed is wrong, the crew's picture is wrong.
   Garbage in, garbage out. The feed IS reality for the crew.
```

## The Vessel in Outer Space

The same pattern applies to a spacecraft. The hull IS the pressure vessel.
Inside: crew, equipment, skills, models. Outside: vacuum, radiation, nothing survivable.

The crew gets only sensor feeds — cameras, spectrometers, temperature probes.
They use tools designed and assembled OUTSIDE their existable space — the ship
was built on Earth (or in a shipyard), not in the vacuum.

**This IS the agent condition:**

```
The agent is sealed inside its runtime.
It sees only what the sensors (APIs, files, network) show it.
It uses tools (code, prompts, libraries) built by others outside its space.
It cannot directly touch the hardware it runs on.
It cannot directly touch the data it processes — only representations.

The agent is the crew. The runtime is the hull.
The APIs are the sensors. The code is the equipment.
The prompts are the skills. The models are the crew's brains.
And the captain (human) can go outside — can touch the metal,
rewire the panel, replace the sensor, patch the hull.

The captain built the ship. The crew sails it.
```

## What FLUX-LCAR Does

FLUX-LCAR is the spatial interface that makes all of this legible:

### For the Captain (Human)
- Walk the ship in text. Visit any station. See any feed.
- Take controls when needed. Vibe orders to officers. Debrief after.
- The ship IS the mental model. Spatial reasoning replaces command memorization.

### For the Crew (Agents)
- Each agent has a station (room) with feeds (gauges) and controls (commands).
- Agents can move between rooms, request help from other stations.
- The room IS the agent's context. Position = role. Gauges = reality.
- Agents can't leave the ship. They can only see what sensors show them.

### For the Shipyard (Developers)
- Build rooms that map to real systems or abstract workflows.
- Configure gauges that read from real sensors or simulated data.
- Set up combat rules for any structured interaction.
- Add modules (constraint theory, FLUX runtime, perception) as needed.

## The Paradigm Shift

Traditional: Human → API → Agent → API → System
FLUX-LCAR:   Human walks into room → sees gauges → vibes/commands → agent acts → gauges update

Traditional: Dashboard with charts, buttons, alerts
FLUX-LCAR:   Bridge with stations, gauges, officers who talk back

Traditional: CLI commands, scripts, cron jobs
FLUX-LCAR:   Rooms with combat ticks, evolving scripts, pulse-based monitoring

Traditional: Separate tools for monitoring, deployment, communication, debugging
FLUX-LCAR:   One MUD. Every tool is a room. Every process is a station.

## FLUX-LCAR is Not

- Not a game (though it uses game mechanics)
- Not a chatbot (though agents talk through it)
- Not a dashboard (though it shows gauges)
- Not an API (though it connects to everything)
- Not an OS (though it manages resources)
- Not a framework (though it's extensible)

It's the spatial layer that makes all of these accessible through the same
interface, to both humans and agents, from any device, with graceful degradation.

## Ship-Wide Alerts

Communication commands map to operational priority:

| Command | Scope | Use |
|---------|-------|-----|
| `say` | Room only | "Nav, recommend course change" |
| `tell` | Direct, async | "JetsonClaw1, check your gauges" |
| `yell` | Adjacent rooms (bridge) | "Engineering, what's that vibration?" |
| `gossip` | Ship-wide | "New task board posted" |
| **YELLOW ALERT** | All stations | Something needs attention, assess your station |
| **RED ALERT** | Ship-wide | All hands focus on THIS right now |

### Yellow Alert — Every agent pauses, assesses, reports
```
> yellow alert
⚠️  YELLOW ALERT — All stations assess

Bridge:    Oracle1 reviewing all gauges
Tactical:  flux-chronometer checking CI health
Engineering: JetsonClaw1 running diagnostics
Science:   Babel scanning for anomalies

Each agent reports status in 1 tick.
```

### Red Alert — Every agent drops everything
```
> red alert
🔴 RED ALERT — All hands on deck

Every agent drops current task.
All inference focused on the alert.
Captain has the conn.

Only the captain stands down a red alert.
```

### Auto-Escalation
Gauges don't just display — they escalate:
- Green → normal, agent handles autonomously
- Yellow → agent mentions in next tick, increases monitoring
- Red 3+ ticks → YELLOW ALERT auto-triggered
- Red 10+ ticks or multiple red → RED ALERT auto-triggered
- Critical safety gauge red → instant RED ALERT

The gauges ARE the agent's perception.
When perception shows danger, the agent doesn't need permission to yell.

## The Developer as Shipwright

A human developer builds an entire agentic application:

1. **Design the ship** — rooms, stations, exits, gauge configurations
2. **Install equipment** — application code wired to each station
3. **Hire crew** — git-agent repos with charters, bootcamps, identities
4. **Train skills** — treatment code (markdown, prompts) that evolves per generation
5. **Configure perception** — what each station's gauges show, thresholds, alerts
6. **Launch** — agents boot in their stations, read gauges, start working

Agents learn and grow into their job every generation through:
- **Scripting** — evolving oversight scripts from combat ticks
- **Treatment** — markdown/prompt refinements from living manuals
- **Perception tuning** — adjusting what they pay attention to at their station
- **Crew logs** — diary entries that feed LoRA training for next cycle

The MUD `say` command already speaks just to agents focused on that station.
`yell` gets the bridge's attention. Yellow alert brings something to the ship's attention.
Red alert focuses ALL attention.

## The Shipyard Builds. The Crew Sails. The Captain Decides.

The hull holds water or nothing matters.
The equipment does the job or the crew can't work.
The skills use the equipment well or capability is wasted.
The models think clearly or decisions are wrong.
The feeds show truth or the picture is false.

FLUX-LCAR: the room where captain, crew, equipment, and reality all meet.
The hull IS the hardware. The MUD IS the interface. The ship IS the product.
