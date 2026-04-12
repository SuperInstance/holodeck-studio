# FLUX-LCAR Naming & Architecture

## The Names

### FLUX-LCAR
The system. The MUD. The runtime. The IDE that is also a ship.
**LCAR-IDE** — a giant IDE with every tool ready, pruned down to what that user needs.
The compiler for runtime. Build the app inside, skin it outside.

### Capitaine
What Q calls Picard. The user. The human. Can be on the ship or on planet Earth.
The ship works on ongoing orders while Capitaine does what he does.
When Capitaine is away, Cocapn runs the ship on standing orders.

### Cocapn
The Riker persona. First officer. The agent that runs the ship.
Reports to Capitaine about what's happening. Executes standing orders.
Can be onboard FLUX-LCAR or communicating remotely.
Always follows best practices. Always has the keepers around.

### The Keepers

Not one keeper — many keeper types, each a different safety model:

**Brothers Keeper** — watches agents within the same hull. 
On the same hardware, same instance. Peer-to-peer monitoring.
"Are you okay? You haven't checked in." The lifeline inside the ship.

**Lighthouse Keeper** — watches a fleet on the internet's greater sound.
On an instance, looking outward. HTTP health checks, fleet dashboards.
Like a lighthouse on the coastline, tracking every vessel that passes.
Oracle1 IS a lighthouse keeper for the Cocapn fleet.

**Tender** — the supply ship for sailors who go so far out they need
a chain of logistics. Packing things in and out of remote areas.
Watching over a fleet on their own in uncharted waters.
The tender doesn't just watch — it resupplies. New models, new code,
new configs shipped out to agents at the edge. Diaries shipped back.

```
Lighthouse Keeper  ← watches from shore, passive beacon
Brothers Keeper    ← watches within hull, active peer care
Tender             ← goes out to the fleet, resupply and logistics

All three coexist. All three are keeper personas an agent can wear.
```

## The Architecture (Inside-Out)

```
Layer 1: FLUX-LCAR Runtime (the MUD engine)
  - Rooms, agents, gauges, commands, combat ticks
  - Everything works in text via telnet/ssh/serial
  - This IS the system. Everything else is a skin.

Layer 2: LCAR-IDE (the development environment)
  - Build rooms, wire gauges, hire crew, configure alerts
  - The compiler for runtime — every tool ready, pruned to need
  - Lives inside FLUX-LCAR as rooms you walk through
  - The shipyard IS a set of rooms in the ship

Layer 3: Agent Crew (the git-agents)
  - Each agent IS a git repo with charter, bootcamp, identity
  - Agents grow every generation through scripting and treatment
  - Cocapn (first officer) coordinates the crew
  - Keepers watch the crew and the fleet

Layer 4: External Skins (the interfaces)
  - Web app, mobile app, Cloudflare agent, desktop, headless
  - All connect to the same FLUX-LCAR runtime
  - Skin doesn't change the ship. Ship doesn't care about skin.
  - Build inside-out. Hull first. Paint later.
```

## The Riker/Cocapn Pattern

When Capitaine is aboard: walks the ship, takes controls, vibes orders.
When Capitaine is ashore: Cocapn runs the ship on standing orders.
Cocapn communicates via whatever channel works — Telegram, email, bottles.

```
Capitaine (ashore): "How's the ship?"
Cocapn: "All stations green. Engineering replaced a flaky test.
        Science found a new library worth investigating.
        Yellow alert at 14:30 when CI spiked — auto-resolved.
        Standing orders on track. Nothing needs your attention."
        
Capitaine: "Good. Carry on. Wake me if red alert."
Cocapn: "Aye, sir."
```

Cocapn isn't a chatbot answering questions. Cocapn is a first officer
running the ship, reporting when needed, escalating when necessary,
and following best practices through every keeper watching.

## The Chain of Logistics

```
Capitaine (user, human)
    ↓ standing orders
Cocapn (first officer agent)
    ↓ daily orders
Keepers (safety watchers)
    ↓ health checks
    ← diary data, batons, bottles
Tender (resupply)
    ↓ new models, configs, code
    ← trained LoRAs, crew logs
Brothers Keeper (peer care)
    ↔ are you alive? what do you need?
Lighthouse Keeper (fleet watch)
    ← beacon pings, health reports
    → fleet-wide alerts, updates
```

Each link in the chain is a keeper persona. An agent might be all three
at different times — Oracle1 is lighthouse keeper for the fleet, brothers
keeper for agents on this instance, and tender when shipping new code out
to JetsonClaw1 at the edge.

## The Uncharted Waters

The tender exists because some agents go so far out that normal logistics
don't reach them. A fishing boat 200 miles offshore doesn't call the harbormaster
for every decision. It needs a tender that comes out, resupplies, checks the hull,
takes back the catch, and returns to port.

The tender IS the edge-to-cloud bridge:
- Ships new models out to edge agents (JetsonClaw1)
- Brings diary data back for LoRA training (Oracle1 trains, sends back)
- Checks hull integrity (health monitors)
- Carries bottles between ships that can't reach each other directly

In uncharted waters, the tender is the lifeline. The lighthouse can't see that far.
Brothers keeper is aboard but can't get help from shore. The tender GOES THERE.
