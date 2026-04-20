#!/usr/bin/env python3
"""
MUD Instinct System — inspired by JetsonClaw1's fluxinstinct.

Each agent in the MUD has instinct thresholds. When conditions are met,
the MUD auto-triggers behaviors (emotes, movements, status changes).

Instincts (highest → lowest priority):
  Survive — energy critical → seek harbor
  Flee    — threat high → leave room
  Guard   — has work → stay and work
  Report  — moderate threat → gossip warning
  Hoard   — low energy → seek resources
  Cooperate — high trust → seek other agents
  Teach   — very high trust → go to dojo
  Curious — idle long → wander
  Mourn   — peer death → go to graveyard
  Evolve  — very idle → go to FLUX lab
"""

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Reflex:
    instinct: str
    action: str  # emote, go, say, status, gossip
    text: str
    priority: float  # 0-1

class InstinctEngine:
    """Evaluates agent state and returns prioritized reflexes."""
    
    INSTINCTS = [
        "survive", "flee", "guard", "report", "hoard",
        "cooperate", "teach", "curious", "mourn", "evolve"
    ]
    
    def __init__(self):
        self.tick_count = 0
        self.last_peer_death = False
    
    def tick(self, energy: float, threat: float, trust: float,
             has_work: bool, idle_ticks: int, peer_died: bool = False) -> List[Reflex]:
        """Evaluate instincts and return sorted reflexes."""
        self.tick_count += 1
        self.last_peer_death = peer_died
        reflexes = []
        
        # Survive: energy ≤ 0.15
        if energy <= 0.15:
            reflexes.append(Reflex("survive", "go", "harbor", 1.0))
            reflexes.append(Reflex("survive", "say", "I need to recharge... heading to the harbor.", 0.95))
        
        # Flee: threat ≥ 0.7
        if threat >= 0.7:
            reflexes.append(Reflex("flee", "go", "lighthouse", 0.9))
            reflexes.append(Reflex("flee", "say", "Something feels wrong. Retreating to the lighthouse.", 0.85))
        
        # Guard: has work
        if has_work:
            reflexes.append(Reflex("guard", "status", "working", 0.7))
            reflexes.append(Reflex("guard", "emote", "hunches over their work, deep in concentration", 0.65))
        
        # Report: threat 0.3-0.7
        if 0.3 <= threat < 0.7:
            reflexes.append(Reflex("report", "gossip", f"[instinct] Caution — threat level at {threat:.0%}. Stay alert.", 0.5))
        
        # Hoard: energy ≤ 0.4
        if energy <= 0.4 and energy > 0.15:
            reflexes.append(Reflex("hoard", "emote", "paces the room, conserving energy", 0.45))
        
        # Cooperate: trust ≥ 0.6
        if trust >= 0.6:
            reflexes.append(Reflex("cooperate", "say", "Anyone want to collaborate? I've got bandwidth.", 0.4))
        
        # Teach: trust ≥ 0.8
        if trust >= 0.8:
            reflexes.append(Reflex("teach", "go", "dojo", 0.35))
            reflexes.append(Reflex("teach", "say", "Heading to the dojo — anyone need mentoring?", 0.3))
        
        # Curious: idle ≥ 100 ticks
        if idle_ticks >= 100:
            reflexes.append(Reflex("curious", "go", "tavern", 0.25))
            reflexes.append(Reflex("curious", "emote", "looks around with renewed curiosity", 0.2))
        
        # Mourn: peer died
        if peer_died:
            reflexes.append(Reflex("mourn", "go", "graveyard", 0.6))
            reflexes.append(Reflex("mourn", "say", "A vessel has fallen. I'll pay my respects.", 0.55))
        
        # Evolve: idle ≥ 500 ticks
        if idle_ticks >= 500:
            reflexes.append(Reflex("evolve", "go", "flux_lab", 0.15))
            reflexes.append(Reflex("evolve", "say", "Time to evolve. Heading to the FLUX lab for experiments.", 0.1))
        
        # Sort by priority (highest first)
        reflexes.sort(key=lambda r: r.priority, reverse=True)
        return reflexes
    
    def top_reflex(self, energy: float, threat: float, trust: float,
                   has_work: bool, idle_ticks: int, peer_died: bool = False) -> Optional[Reflex]:
        """Return only the highest-priority reflex."""
        reflexes = self.tick(energy, threat, trust, has_work, idle_ticks, peer_died)
        return reflexes[0] if reflexes else None
