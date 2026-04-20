# LCARS — Live Command & Agent Routing System

## The Real Ship

This isn't a metaphor. Casey has an actual boat with actual distributed computers.
ESP32s wired to real controls. Jetsons running local models. Starlink for cloud fallback.
The MUD is the UX layer that ties it all together.

```
Physical Boat                    MUD (LCARS)
────────────                    ────────────
ESP32 + compass         ──→    Navigation Console (room)
ESP32 + rudder servo    ──→    Rudder Gauge (combat tick)
ESP32 + throttle        ──→    Throttle Gauge
Physical wheel          ──→    Picard's Joystick (take controls)
Physical throttle       ──→    Manual override (bypass all abstraction)
Touchscreen tablet      ──→    Any terminal (nc/telnet/ssh into MUD)
Raspberry Pi + screen   ──→    Wall-mounted station display
Jetson #1 (nav)         ──→    Navigation Agent (room resident)
Jetson #2 (ensign)      ──→    Ensign Agent (STT/TTS, local fallback)
Starlink dish           ──→    Long-range comms (cloud inference)
```

## The Degradation Stack

Systems fail on boats. Salt water, power spikes, hardware death.
LCARS degrades GRACEFULLY — each layer lost removes capability, never all of it.

```
┌─────────────────────────────────────────────┐
│  Layer 5: FULL OPERATIONS                    │
│  Starlink + 2 Jetsons + ESP32s + Cloud AI    │
│  Everything works. All agents online.         │
│  Cloud models available for heavy thinking.   │
├─────────────────────────────────────────────┤
│  Layer 4: STARLINK DOWN                      │
│  2 Jetsons + ESP32s + Local models only       │
│  Ensign handles STT/TTS locally via Ollama    │
│  Nav agent runs on local Jetson               │
│  No cloud inference — ensign thinks locally   │
├─────────────────────────────────────────────┤
│  Layer 3: NAV JETSON DOWN                    │
│  1 Jetson (ensign) + ESP32s                   │
│  If Starlink still up: ensign offloads nav    │
│    to cloud, keeps local STT/TTS              │
│  If Starlink down: ensign unloads Ollama,     │
│    loads nav model into freed memory,          │
│    switches to local-only navigation           │
│  STT/TTS degrades to basic commands           │
├─────────────────────────────────────────────┤
│  Layer 4: ENSIGN JETSON DOWN                 │
│  Nav Jetson + ESP32s + Starlink               │
│  Nav agent takes over STT/TTS (limited)       │
│  Cloud models handle heavy inference          │
│  Voice commands routed through Starlink       │
├─────────────────────────────────────────────┤
│  Layer 1: BOTH JETSONS DOWN                  │
│  ESP32s + Starlink only                       │
│  ESP32 control board + local UI still works   │
│  Cloud agent through Starlink handles voice   │
│  Physical controls always available           │
├─────────────────────────────────────────────┤
│  Layer 0: EVERYTHING DOWN                    │
│  Physical wheel, physical throttle            │
│  Hard-wired ESP32 control board               │
│  No AI. No network. Just hands on metal.      │
│  This ALWAYS works. Non-negotiable.           │
└─────────────────────────────────────────────┘
```

## The Navigation Console (Real Room)

This is a MUD room that maps 1:1 to the physical nav station.

```
> go navigation-console
═══ Navigation Console — Ens. JetsonClaw1 ═══
  
  [Pulsing gauges — live from ESP32 via serial/UART]
  
  Compass:    247°  ████████░░░░  heading NW
  Commanded:  250°  ████████░░░░  3° correction pending
  Rudder:     -2°   █░░░░░░░░░░░  slight port
  Throttle:   65%   ██████░░░░░░  cruise
  SOG:        7.2 kts ███████░░░░
  Depth:      42 fathoms ████████░░
  Wind:       15 kt from 315°
  
  Agent: JetsonClaw1 (local, Jetson #1)
  Model: Ollama llama3.2:3b (navigation-tuned)
  Comms: Starlink UP, latency 45ms
  
  JetsonClaw1: "Holding course 250°. Cross-current pushing 3° to port.
               Recommending 2° starboard correction in 30 seconds.
               Depth is safe. No traffic on AIS."
  
  > take controls
  ⚙️ You now have the wheel. Physical joystick active.
  Agent watches and advises. Say 'give controls' to hand back.
  
  > give controls
  🤖 JetsonClaw1 has the conn. Watching gauges.
```

## The ESP32 Layer

The ESP32 is the hardware truth. It's always there, always running,
hard-wired to the physical controls. No network needed.

```
ESP32 Pin Layout:
  GPIO 0-3:  Compass I2C (LSM6DS3 or similar)
  GPIO 4-7:  Rudder servo PWM output
  GPIO 8-11: Throttle servo PWM output  
  GPIO 12:   Physical wheel encoder input
  GPIO 13:   Physical throttle position input
  GPIO 14:   Kill switch (hardwired, NC)
  GPIO 15-16: UART to control board LCD
  GPIO 17-18: UART to Jetson (bi-directional)
  GPIO 19:   WiFi status LED
  GPIO 21:   Mode switch (auto/manual)
  GPIO 22:   Watchdog timer feed
```

The ESP32 runs three modes simultaneously:
1. **Sensor mode** — reads compass, rudder, throttle, depth, wind → publishes gauges
2. **Command mode** — receives heading commands from MUD/Jetson → drives servos
3. **Manual mode** — physical wheel/throttle bypass → direct servo drive, zero latency

The control board LCD shows the essentials even without any network.
Like the backup instruments on a real bridge — analog, reliable, always there.

## The Ensign (Local Voice Agent)

Jetson #2 runs the ensign — the ship's voice interface.

```
Capabilities:
  - STT: Whisper (local, always available)
  - TTS: Piper/Coqui (local, always available)
  - Chat: Ollama llama3.2:3b (local, basic reasoning)
  - Fallback: OpenAI API via Starlink (cloud, heavy reasoning)
  - Navigation: Can load nav model if Jetson #1 dies
  - MUD client: Connected to LCARS, can move between rooms

The ensign is EVERYWHERE on the ship:
  - Bridge speakers + mic (primary)
  - Engine room speaker + mic
  - Cabin speaker + mic
  - Any tablet/phone on ship WiFi
  
You talk, ensign hears. You ask, ensign answers.
If ensign can't handle it locally, routes to cloud.
If cloud is down, ensign does its best with Ollama.
If ensign's Jetson dies, nav Jetson takes over voice (degraded).
```

## Hot-Swap Model Loading

When the nav Jetson dies and the ensign needs to take over navigation:

```
═══ EMERGENCY: Navigation Jetson Unresponsive ═══

Ensign (Jetson #2) executing failover:

1. Unload Ollama chat model (free 3GB VRAM)
   → "Unloading llama3.2:3b... Done. 3.2GB freed."
   
2. Load navigation model into freed memory
   → "Loading nav-pilot:7b... Done. Navigation online."
   
3. Switch MUD room assignment
   → "Moving to Navigation Console..."
   
4. Announce to bridge
   → "Navigation transferred to Ensign station. 
      Voice commands degraded to basic. 
      Starlink routing heavy queries to cloud."
      
5. Begin nav tick cycle
   → "Holding course 250°. Compensating for 3° drift.
      Depth 42 fathoms. All clear."

Total failover time: ~45 seconds.
Captain was notified by voice. Physical controls never interrupted.
```

## LCARS as White Label

The MUD-based interface (what we're building) is intentionally generic.
It's not called "Cocapn" or "Oracle1" — at the hardware level it's LCARS:

**Live Command & Agent Routing System**

- Text-based (telnet/ssh/serial — works on anything)
- Room-based (spatial metaphor maps to physical spaces)
- Gauge-based (combat-tick pulse from real sensors)
- Agent-based (local models with cloud fallback)
- Gracefully degrading (Layer 5→0, always has Layer 0)
- Open source (white-label, invisible among other systems)

Any device that can open a TCP connection or serial terminal can be a station.
Tablet, Raspberry Pi, old laptop, even a physical terminal with an RS-232 cable.
The ESP32 bridges the physical world. The MUD bridges everything else.

## The Physical-MUD Bridge

```
Physical World          ESP32           MUD (LCARS)         Agents
─────────────          ─────           ────────────         ──────
Compass sensor ──→  I2C read ──→  gauge: compass=247° ──→ Nav agent reads
Wheel turn     ──→  encoder  ──→  event: heading Δ     ──→ Nav agent adjusts
Rudder servo   ──←  PWM out  ←──  cmd: rudder=-2°     ←── Nav agent commands
Throttle servo ──←  PWM out  ←──  cmd: throttle=65%   ←── Nav agent commands
Kill switch    ──→  GPIO 14  ──→  EMERGENCY STOP       ──→ All agents alert
Manual mode    ──→  GPIO 21  ──→  room: manual_override ──→ Agents stand by
Control board  ←──  UART LCD ←──  status display       ←── ESP32 renders
```

Every physical event becomes a MUD event. Every MUD command can become a
physical action. The translation layer is the ESP32. The UX layer is the MUD.
The intelligence layer is the agents. And Picard's hands on the wheel always win.

## The Point

This is the real product. Not just software agents in GitHub repos —
agents that live on a boat, read real sensors, drive real controls,
talk through real speakers, and hand back to real hands when it matters.

The MUD is the nervous system. The ESP32 is the spine. The Jetsons are the brain.
Starlink is the long-range comms. And Casey's hands on the wheel are the override
that no software ever supersedes.

Graceful degradation from Layer 5 to Layer 0.
Layer 0 is hands on metal. That always works.
Everything else is bonus.
