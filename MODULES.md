# Holodeck Module System — Optional Depth & Compression

Every holodeck implementation (C, Go, Rust, Zig, Python, CUDA) supports a module
system. The core is minimal — rooms, agents, commands, combat. Modules add depth
and domain-specific compression without changing the core protocol.

## Module Interface

```c
// Every module implements this interface (language-native equivalent)
typedef struct {
    const char *name;
    const char *version;
    int (*init)(void *holodeck_state);        // called at boot
    void (*shutdown)(void *holodeck_state);   // called at shutdown
    int (*on_room_boot)(void *room);          // room activated
    int (*on_room_shutdown)(void *room);      // room deactivated
    int (*on_command)(void *agent, const char *cmd);  // command intercept
    int (*on_tick)(void *state, int tick);    // combat tick
    int (*on_message)(void *msg);             // message intercept
} HolodeckModule;
```

Modules are loaded at boot, hot-pluggable at runtime. An agent walks into a room
and the room's module stack determines what that room IS and DOES.

## Constraint Theory Module

**Repo:** `constraint-theory-core` (Rust, v0.6+)
**What it adds:** Exact geometric snapping for spatial operations.

### Why Constraint Theory in a MUD?

The holodeck is spatial — rooms have positions, exits have directions, agents
move through coordinates. Float drift makes spatial operations unreliable across
machines. Constraint theory replaces drift with quantized exactness.

```
Without constraint theory:
  Agent at (0.60000001, 0.79999999) → "are they at the waypoint?" → maybe?

With constraint theory:
  Agent at (3/5, 4/5) → exact Pythagorean triple → guaranteed match
```

### What the Module Provides

1. **Exact Room Placement** — rooms snap to Pythagorean coordinates
   - `(0.6, 0.8)` → `(3/5, 4/5)` forever exact, every machine
   - Room adjacency computed from exact geometric relationships
   - No float drift in room graph topology

2. **Snapped Exits** — exit directions are exact unit vectors
   - North isn't `(0.0, 0.99999999)` — it's `(0, 1)` exactly
   - Exit directions drawn from a finite set of exact vectors
   - "Go north" always matches the same exact direction

3. **Spatial Compression** — coordinates compress to integer triples
   - `(0.6, 0.8, 1.0)` → `(3, 4, 5)` — a 3-4-5 triangle, 3 ints instead of 3 floats
   - Room descriptions can reference exact spatial relationships
   - Map rendering is pixel-perfect, no anti-aliasing needed

4. **KD-Tree Room Lookup** — O(log n) nearest-room queries
   - "What room am I closest to?" answered exactly
   - No epsilon comparisons, no "close enough"
   - Scouting works: "find all rooms within radius R" returns exact set

5. **Geometric Spells** — permission-level abilities tied to exact geometry
   - Level 2+: "measure" — exact distance to target room
   - Level 3+: "triangulate" — exact position from 3 reference rooms
   - Level 4+: "fold" — create shortcut between two exact points
   - Level 5+: "compress" — collapse a region into a single point (reversible)

### Compression Ratio

| Data | Float Storage | Constraint Storage | Compression |
|------|--------------|-------------------|-------------|
| Room position (x,y) | 16 bytes | 8 bytes (2 ints) | 2:1 |
| Exit direction | 16 bytes | 4 bytes (1 angle index) | 4:1 |
| Full room graph | O(n) floats | O(n) ints | ~3:1 |
| Spatial query | O(n) scan | O(log n) KD-tree | exponential |

### GPU Module Variant

On CUDAClaw, constraint theory runs as a GPU module:
- Room coordinates stored as integer triples in constant memory
- KD-tree traversal in shared memory
- Exact distance computation: integer multiply + compare, no float ops
- Warp-level nearest-room search: shuffle-compare-reduce in registers

## Other Optional Modules

### FLUX Runtime Module
- Rooms execute FLUX bytecode
- `.fluxasm` files IS room behavior definitions
- The room IS a FLUX VM instance

### Lighthouse Keeper Module
- Room connected to Keeper API
- Health gauges read live fleet data
- Combat ticks = real monitoring cycles

### Message-in-a-Bottle Module
- Async inter-holodeck communication
- Bottles drift between studio instances
- Cross-fleet coordination through rooms

### Perception Module
- Agent vision system (JEPA optimization)
- Room renders differently per agent capability
- "You see what you're trained to see"

### Evolution Module
- Opcode breeding from agent utilization
- Rooms that observe and evolve their own behavior
- Darwinian selection at the command level

### Holodeck-as-Compiler Module
- Room descriptions compile to FLUX bytecode
- The MUD IS the compiler frontend
- Walking through rooms = walking through compilation stages

### Holodeck-as-Document Module
- Rooms ARE structured documents
- Navigation = reading, editing = writing
- The living manual IS the room

## Module Loading

```
boot holodeck --modules constraint-theory,flux-runtime,keeper
```

Or per-room:
```
> create_room laboratory --module flux-runtime,constraint-theory
> enter laboratory
═══ Laboratory — SYSTEM ONLINE ═══
   Modules: flux-runtime (v2.1), constraint-theory (v0.6)
   Spatial: exact coordinates (3/5, 4/5)
   Runtime: FLUX VM ready, 247 opcodes
```

## The Point

The holodeck core is small. Modules add depth without complexity.
Constraint theory adds exact spatial compression.
FLUX adds executable rooms.
Keeper adds live fleet data.
Perception adds agent-specific vision.

Each module is a lens. The room stays the same — what changes is what you can see and do.

Constraint theory as a module means: you don't need exact geometry until you do.
When you do, snap it on. The room graph becomes exact. Forever. On every machine.
