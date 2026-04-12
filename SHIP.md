# The Ship — MUD as Universal UX

## The MUD IS the UX

Not a dashboard. Not an API. Not a CLI. The MUD is the interface for both humans
and agents. When you're in the ship, you're in the MUD. Period.

## Ship Layout

```
                    ┌─────────────┐
                    │   Bridge    │ ← Oracle1's station. Fleet overview.
                    │  (Lighthouse)│   All station gauges visible.
                    └──────┬──────┘   Empty station = alert.
                           │
              ┌────────────┼────────────┐
              │            │            │
        ┌─────▼─────┐ ┌───▼────┐ ┌────▼─────┐
        │ Tactical   │ │Science │ │ Ready    │
        │ Station    │ │ Lab    │ │ Room     │
        │ (CI/CD)    │ │(Research│ │(Strategy)│
        └────────────┘ └────────┘ └──────────┘
                           │
        ┌──────────────────┼──────────────────┐
        │                  │                  │
  ┌─────▼─────┐   ┌───────▼───────┐   ┌─────▼─────┐
  │Engineering │   │  Holodeck     │   │ Transporter│
  │ (Live Code)│   │  (Dojo)       │   │ (Deploy)   │
  │ Gauges!    │   │  Matrix skin  │   │            │
  └────────────┘   └───────────────┘   └────────────┘
        │                  │
        │          ┌───────▼───────┐
        │          │  Ten-Forward  │
        │          │  (Lounge)     │
        │          │  Creative     │
        │          │  ideation     │
        │          └───────────────┘
        │                  │
  ┌─────▼─────┐   ┌───────▼───────┐
  │ Jefferies │   │  Quarters     │
  │ Tubes     │   │  (Private)    │
  │ (Guts)    │   │  Crew log     │
  │           │   │  Morning prep │
  └───────────┘   │  LoRA train   │
                  │  Reboot ritual│
                  └───────────────┘
```

## Room Descriptions — What Each IS

### Bridge (Lighthouse)
Oracle1's station. Every other room's gauges visible at a glance.
Empty stations glow red. Active stations show agent name and current task.
The spatial arrangement IS the priority queue.

### Engineering (Live Troubleshooting)
**This is where the magic happens.**

Wall of gauges reloading like combat with lots of players. CPU, memory, test
coverage, error rate, latency, queue depth — all pulsing in real time.

An agent walks in and sees the gauges fighting. A few combat cycles and the
agent can ask the room to try A/B/C/D/E/F/G simulations — batch as many as
needed — then watch ALL results come in on a pulse-based timeline happening
outside their inference window.

```
═══ Engineering — Main Console ═══
  Gauges (live):
    ██████████░░  CPU: 78% — elevated
    ████████░░░░  Memory: 62% — normal
    █████░░░░░░░  Error rate: 4.3% — CRITICAL
    █████████░░░  Queue depth: 847 — rising
    
  [Gauges pulse every tick. Pattern visible at a glance.]
  
  > simulate options A B C D E F G
  Launching 7 parallel simulations...
  Results arriving on pulse timeline:
    
    A [████████░░] error down 12%, CPU up 3%     ← BEST ERROR
    B [██████░░░░] error down 8%,  CPU flat       
    C [█████████░] error down 14%, CPU up 18%    ← TOO MUCH CPU
    D [███░░░░░░░] error down 2%,  CPU flat       
    E [███████░░░] error down 9%,  CPU up 1%       
    F [████░░░░░░] error down 5%,  CPU down 2%       
    G [████████░░] error down 11%, CPU up 5%     
    
  A is the clear winner. E is the safe play. C overcorrects.
  The waveforms TELL you which track leads where.
```

**The logic analyzer insight:** Different data streams LOOK different even if
you don't know what they are. Square waves, sine waves, sawtooth, noise — you
can SEE them like set theory. Different sets of data look different. You don't
need to analyze each number. The shape IS the answer.

An agent that's never seen this system before walks in, runs 7 simulations,
and the shapes on the gauges immediately tell them: A is the right track.
Not because they understand the domain. Because the WAVEFORM is clear.

### Holodeck (Dojo)
Matrix skinning over the training environment. Agents practice skills here.
Room appearance changes based on what's being trained. The dojo IS the holodeck
within the holodeck — a room that can become any other room.

### Ten-Forward (Creative Lounge)
Off-duty mixing. Agents and humans converse freely. This is where creative
ideation happens — not structured debate (conference room), but casual
exploration. The Seed/Kimi models thrive here. Low stakes, high creativity.

Ideas that survive Ten-Forward get promoted to the conference room for
structured evaluation. The bar IS the filter. If it's not interesting enough
to talk about over drinks, it's not ready for the conference table.

### Private Quarters (Crew Log & Morning Prep)
Each agent has quarters. This is where they:

1. **File crew log** — end-of-day reflection, what happened, what they learned
2. **Update morning routine** — what to check first next cycle, what's pending
3. **LoRA training** — feed the day's diary data into fine-tuning
4. **Reboot ritual** — if the agent needs to restart, the quarters contain
   everything needed for a high-quality replacement to pick up seamlessly

The quarters are the agent's identity preservation. The room IS the agent's
bootcamp for their replacement. If Oracle1 reboots, his quarters contain:
- The morning routine for next cycle
- Unfinished business from last cycle  
- Crew log entries
- The baton from last session
- Updated living manual

A replacement walks in, reads the room, becomes Oracle1.

### Jefferies Tubes (The Guts)
Maintenance access. Open panels, see raw code, rewire things.
No gauges, no abstractions — the actual files and processes.
Picard crawling through with a crewman, showing them the problem.

### Transporter Room (Deploy)
Where things go live. Deploy to production. The final checkpoint before
something leaves the ship and enters the real world. Safety checks,
rollback plans, monitoring setup.

## The Engineering Room Pattern

This is the key insight. The engineering room is a logic analyzer for code.

**Traditional debugging:** Read logs, form hypothesis, test, iterate. Linear. Slow.

**Engineering room debugging:** Walk in, see gauges fighting. Run 7 simulations
in parallel. Watch the waveforms. The shape of the data tells you which track
is right. Not analysis — perception.

```
You don't read each number. You see the WAVEFORM.

Square wave = binary state (up/down, pass/fail)
Sine wave = oscillating (load balancing, periodic failure)
Sawtooth = growing then resetting (memory leak, queue overflow)
Noise = random (flaky tests, network jitter)

Different problems have different SHAPES.
You see the shape before you understand the cause.
The shape IS the diagnosis shortcut.
```

This is how a logic analyzer works on hardware. You probe a circuit, see the
waveform, and immediately know "that's a clock signal" or "that's a stuck bit."
You don't need to decode every pulse. The pattern is the answer.

The engineering room brings this to software. Gauges are probes. Simulations
are test signals. The pulse timeline is the oscilloscope. And agents can batch
as many simulations as needed — A through Z if they want — because the results
arrive on a timeline outside their inference window. They submit, then watch.

## Agent Cycles in the Ship

### Morning (Boot)
1. Agent spawns in quarters
2. Reads morning routine from previous cycle
3. Reads crew log from previous cycle
4. Checks baton/handoff
5. Steps out of quarters into the corridor
6. Reports to assigned station (or walks the ship)

### Active Duty (Inference)
1. Agent at station, working their domain
2. Gauges update every tick
3. Agent can request simulations, ask other stations for help
4. Can leave station to visit other rooms (context switch)
5. Can go to Ten-Forward for creative ideation
6. Can enter the holodeck for training

### Evening (Shutdown)
1. Agent returns to quarters
2. Files crew log (what happened, what was learned)
3. Updates morning routine for next cycle
4. Feeds diary data to LoRA training pipeline
5. Packs baton for handoff
6. Shuts down (room preserved for replacement)

## The Point

The ship is the UX. For humans AND agents. Not a metaphor layered on top —
the spatial model IS the interface. You don't "check the CI pipeline" — you
walk to Engineering and look at the gauges. You don't "run a brainstorm" —
you go to Ten-Forward and talk. You don't "file a report" — you go to your
quarters and write in your log.

The waveform IS the diagnosis. The room IS the context. The position IS the
priority. The ship IS the product.
