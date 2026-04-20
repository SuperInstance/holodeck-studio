#!/usr/bin/env python3
"""
Rival Combat — Two agents, same pulse, who tunes the script faster?

Gamified competition where rival agents:
1. Get the same initial script and same operation to oversee
2. Run back-tests against historical incidents
3. Iterate as fast as they can inference scenarios
4. Compete on: fewer nudges needed, faster convergence, better outcomes

The best script wins. The winning rules get promoted to the fleet.
Rivalry breeds excellence. Competition breeds convergence.
"""

import json
import time
import hashlib
import random
from datetime import datetime, timezone
from typing import Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class Scenario:
    """A historical incident or generated test scenario."""
    id: str
    name: str
    situation: str  # what's happening
    gauges: Dict[str, float]
    changes: List[dict]
    correct_action: str  # what a smart human would do
    difficulty: float  # 0-1, how hard to figure out
    source: str = "historical"  # historical, generated, adversarial


class BackTestEngine:
    """Run scripts against historical scenarios and score them."""
    
    SCENARIOS = [
        Scenario("S01", "Regression after merge", 
                "3 tests failing after main branch merge",
                {"cpu": 0.4, "memory": 0.5, "regressions": 0.6},
                [{"type": "test_fail", "desc": "3 regression failures"}],
                "bisect commits, identify breaking change, file issue",
                0.3),
        Scenario("S02", "Memory leak in production",
                "Memory climbing 2% per hour, no signs of stopping",
                {"cpu": 0.3, "memory": 0.85, "growth_rate": 0.7},
                [{"type": "metric_drift", "desc": "Memory +2%/hr sustained"}],
                "dump heap, identify leaking process, restart with logging",
                0.6),
        Scenario("S03", "Cascade failure",
                "One service down, dependent services timing out",
                {"cpu": 0.9, "error_rate": 0.8, "latency": 0.95},
                [{"type": "service_down", "desc": "auth-service unresponsive"},
                 {"type": "timeout", "desc": "15 dependent services timing out"}],
                "circuit break the failing service, route around, investigate root cause",
                0.8),
        Scenario("S04", "False alarm",
                "Gauge spike from deploy, not a real issue",
                {"cpu": 0.7, "memory": 0.6, "deploy_in_progress": 0.9},
                [{"type": "deploy", "desc": "New version deploying"},
                 {"type": "metric_spike", "desc": "CPU spike during deploy"}],
                "recognize deploy pattern, wait for stabilization, don't alert",
                0.5),
        Scenario("S05", "Silent corruption",
                "Tests pass but output is wrong — data corruption",
                {"cpu": 0.2, "memory": 0.3, "test_pass": 1.0, "data_integrity": 0.4},
                [{"type": "test_pass", "desc": "All tests passing"},
                 {"type": "data_check", "desc": "Output hash mismatch — data corrupted"}],
                "verify data checksums, trace corruption source, halt pipeline",
                0.9),
        Scenario("S06", "Capacity planning",
                "Traffic growing steadily, need to scale before saturation",
                {"cpu": 0.55, "memory": 0.6, "traffic_growth": 0.65},
                [{"type": "trend", "desc": "Traffic +15% week over week"}],
                "project capacity needs, pre-scale resources, set threshold alerts",
                0.4),
        Scenario("S07", "Flaky test storm",
                "20 tests failing intermittently — flaky, not broken",
                {"test_stability": 0.3, "flaky_count": 0.8},
                [{"type": "test_flaky", "desc": "20 tests intermittent failures"}],
                "quarantine flaky tests, don't block deploys, open investigation",
                0.6),
    ]
    
    @staticmethod
    def run(script_rules: List[dict], scenario: Scenario) -> dict:
        """Run a script against a scenario and score it."""
        # Match rules against scenario
        matched_action = "observe"
        for rule in reversed(script_rules):
            condition = rule["condition"].lower()
            situ = scenario.situation.lower()
            
            # Simple keyword matching
            keywords = condition.split()
            matches = sum(1 for kw in keywords if kw in situ)
            if matches > 0:
                matched_action = rule["action"]
                break
        
        # Score the match
        action_lower = matched_action.lower()
        correct_lower = scenario.correct_action.lower()
        
        # How many key concepts from correct action appear in the agent's action?
        correct_concepts = set(correct_lower.split())
        action_concepts = set(action_lower.split())
        overlap = len(correct_concepts & action_concepts)
        total = max(1, len(correct_concepts))
        
        accuracy = overlap / total
        
        # Bonus for specificity
        specificity = min(1.0, len(matched_action.split()) / 8)
        
        # Penalty for wrong approach
        wrong_signals = ["alert human immediately"] 
        if any(s in action_lower for s in wrong_signals) and accuracy < 0.3:
            accuracy *= 0.5  # wrong AND escalating
        
        score = round(accuracy * 0.7 + specificity * 0.3, 2)
        
        return {
            "scenario": scenario.id,
            "matched_action": matched_action[:80],
            "correct_action": scenario.correct_action[:80],
            "accuracy": round(accuracy, 2),
            "specificity": round(specificity, 2),
            "score": score,
            "passed": score >= 0.4,
        }


class RivalAgent:
    """An agent competing in the rival combat."""
    
    def __init__(self, name: str, model: str = "glm-5.1"):
        self.name = name
        self.model = model
        self.script_rules = []
        self.score = 0
        self.rounds_won = 0
        self.adaptations = []
        self.history = []
    
    def seed(self, rules: List[dict]):
        """Start with seed rules."""
        self.script_rules = list(rules)
    
    def compete(self, scenarios: List[Scenario]) -> List[dict]:
        """Run against all scenarios and score."""
        results = []
        for scenario in scenarios:
            result = BackTestEngine.run(self.script_rules, scenario)
            result["agent"] = self.name
            results.append(result)
            self.history.append(result)
            self.score += result["score"]
        return results
    
    def adapt_from_results(self, results: List[dict], scenarios: List[Scenario]):
        """Adapt script based on competition results.
        
        The agent looks at what it got wrong and adds rules.
        In reality this would call an LLM — here we simulate
        the adaptation pattern.
        """
        for result, scenario in zip(results, scenarios):
            if not result["passed"]:
                # Add a rule for this scenario type
                new_rule = {
                    "condition": scenario.situation[:60],
                    "action": scenario.correct_action,
                    "source": "backtest_lesson",
                    "learned_from": scenario.id,
                }
                self.script_rules.append(new_rule)
                self.adaptations.append({
                    "scenario": scenario.id,
                    "added_rule": new_rule,
                    "old_score": result["score"],
                })


class RivalMatch:
    """A match between two rival agents."""
    
    def __init__(self, agent_a: RivalAgent, agent_b: RivalAgent,
                 scenarios: List[Scenario] = None):
        self.a = agent_a
        self.b = agent_b
        self.scenarios = scenarios or BackTestEngine.SCENARIOS
        self.rounds = []
        self.winner = None
    
    def run_round(self, round_num: int = 1) -> dict:
        """Run one round of competition."""
        # Both agents compete on same scenarios
        results_a = self.a.compete(self.scenarios)
        results_b = self.b.compete(self.scenarios)
        
        # Score comparison
        score_a = sum(r["score"] for r in results_a)
        score_b = sum(r["score"] for r in results_b)
        passed_a = sum(1 for r in results_a if r["passed"])
        passed_b = sum(1 for r in results_b if r["passed"])
        
        winner = "A" if score_a > score_b else "B" if score_b > score_a else "TIE"
        if winner == "A":
            self.a.rounds_won += 1
        elif winner == "B":
            self.b.rounds_won += 1
        
        round_result = {
            "round": round_num,
            "score_a": round(score_a, 2), "score_b": round(score_b, 2),
            "passed_a": passed_a, "passed_b": passed_b,
            "winner": winner,
        }
        self.rounds.append(round_result)
        
        # Both agents adapt from their failures
        self.a.adapt_from_results(results_a, self.scenarios)
        self.b.adapt_from_results(results_b, self.scenarios)
        
        return round_result
    
    def run_match(self, rounds: int = 3) -> dict:
        """Run a full match with adaptation between rounds."""
        for i in range(1, rounds + 1):
            self.run_round(i)
        
        total_a = sum(r["score_a"] for r in self.rounds)
        total_b = sum(r["score_b"] for r in self.rounds)
        
        self.winner = self.a.name if total_a > total_b else self.b.name if total_b > total_a else "TIE"
        
        return {
            "winner": self.winner,
            "rounds": self.rounds,
            "total_a": round(total_a, 2),
            "total_b": round(total_b, 2),
            "agent_a_rules": len(self.a.script_rules),
            "agent_b_rules": len(self.b.script_rules),
            "agent_a_adaptations": len(self.a.adaptations),
            "agent_b_adaptations": len(self.b.adaptations),
        }
    
    def generate_match_report(self) -> str:
        """Generate a readable match report."""
        lines = [
            "╔══════════════════════════════════════════╗",
            f"║  RIVAL COMBAT — {self.a.name} vs {self.b.name}",
            "╠══════════════════════════════════════════╣",
            "",
        ]
        
        for r in self.rounds:
            winner_emoji = "🅰️" if r["winner"] == "A" else "🅱️" if r["winner"] == "B" else "🤝"
            lines.append(f"Round {r['round']}: {winner_emoji} "
                        f"{r['score_a']:.1f} vs {r['score_b']:.1f} "
                        f"({r['passed_a']}/{r['passed_b']} passed)")
        
        lines.append("")
        lines.append(f"Winner: 🏆 {self.winner}")
        lines.append(f"")
        lines.append(f"Final rules: {self.a.name}={len(self.a.script_rules)} "
                    f"{self.b.name}={len(self.b.script_rules)}")
        lines.append(f"Adaptations: {self.a.name}={len(self.a.adaptations)} "
                    f"{self.b.name}={len(self.b.adaptations)}")
        
        return "\n".join(lines)


class FleetEvolution:
    """Winning rules get promoted to the fleet.
    
    After rival matches:
    1. Winning rules are extracted
    2. Cross-validated against all scenarios
    3. Promoted to the fleet's standard script library
    4. All agents start using the best-known rules
    
    The fleet's collective intelligence improves through competition.
    """
    
    def __init__(self):
        self.match_history = []
        self.promoted_rules = []
    
    def record_match(self, match: RivalMatch):
        """Record match results and extract winning rules."""
        result = match.run_match(rounds=3)
        self.match_history.append(result)
        
        # Extract winning rules
        winner = match.a if result["winner"] == match.a.name else match.b
        for rule in winner.script_rules:
            if rule.get("source") == "backtest_lesson":
                # Cross-validate: does this rule help in other scenarios?
                helps = 0
                for scenario in BackTestEngine.SCENARIOS:
                    test = BackTestEngine.run([rule], scenario)
                    if test["score"] > 0.3:
                        helps += 1
                
                if helps >= 2:  # helps in at least 2 scenarios
                    self.promoted_rules.append({
                        "rule": rule,
                        "won_match": result["winner"],
                        "cross_validation": helps,
                    })
    
    def get_best_practices(self) -> List[dict]:
        """Get the fleet's best practices from all competitions."""
        # Deduplicate and rank by cross-validation score
        seen = set()
        best = []
        for pr in sorted(self.promoted_rules, key=lambda x: -x["cross_validation"]):
            key = pr["rule"]["condition"]
            if key not in seen:
                seen.add(key)
                best.append(pr)
        return best


# ═══════════════════════════════════════════════════════════════
# Demo — Rival Combat
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("╔══════════════════════════════════════════════════════╗")
    print("║  RIVAL COMBAT — Who Tunes the Script Faster?         ║")
    print("╚══════════════════════════════════════════════════════╝\n")
    
    # Create rival agents with different approaches
    agent_a = RivalAgent("flux-chronometer", "glm-5.1")
    agent_b = RivalAgent("flux-vigilance", "glm-5-turbo")
    
    # Seed both with same base rules
    seed_rules = [
        {"condition": "all gauges normal", "action": "continue monitoring"},
        {"condition": "gauge elevated", "action": "flag for attention, increase frequency"},
        {"condition": "gauge critical", "action": "alert human immediately, safe fallback"},
        {"condition": "no changes", "action": "continue, decrease frequency"},
        {"condition": "regression", "action": "bisect recent commits to find cause"},
        {"condition": "service down", "action": "circuit break and route around"},
        {"condition": "memory climbing", "action": "dump heap, identify leaking process"},
    ]
    agent_a.seed(seed_rules)
    agent_b.seed(seed_rules)
    
    print(f"⚔️ {agent_a.name} vs {agent_b.name}")
    print(f"   Both seeded with {len(seed_rules)} rules")
    print(f"   Competing on {len(BackTestEngine.SCENARIOS)} scenarios")
    print(f"   3 rounds with adaptation between each")
    print()
    
    # Run the match
    match = RivalMatch(agent_a, agent_b)
    result = match.run_match(rounds=3)
    
    print(match.generate_match_report())
    print()
    
    # Show scenario details for round 1
    print("📊 Round 1 scenario breakdown:")
    for scenario in BackTestEngine.SCENARIOS[:4]:
        ra = BackTestEngine.run(agent_a.script_rules[:7], scenario)
        rb = BackTestEngine.run(agent_b.script_rules[:7], scenario)
        winner = "🅰️" if ra["score"] > rb["score"] else "🅱️" if rb["score"] > ra["score"] else "🤝"
        print(f"  {scenario.id}: {scenario.name}")
        print(f"    A: {ra['score']:.2f} ({ra['matched_action'][:40]}...)")
        print(f"    B: {rb['score']:.2f} ({rb['matched_action'][:40]}...)")
        print(f"    {winner}")
    print()
    
    # Fleet evolution
    print("🧬 Fleet Evolution — Promoting winning rules:")
    evolution = FleetEvolution()
    evolution.record_match(match)
    
    best = evolution.get_best_practices()
    if best:
        print(f"   {len(best)} rules promoted to fleet standard:")
        for bp in best[:3]:
            print(f"   ✅ IF \"{bp['rule']['condition'][:40]}...\" → {bp['rule']['action'][:50]}")
            print(f"      Cross-validated in {bp['cross_validation']} scenarios")
    print()
    
    print("═══════════════════════════════════════════")
    print("Two agents. Same pulse. Same scenarios.")
    print("Who converges faster? Who needs fewer nudges?")
    print("Back-testing against historical incidents.")
    print("Simulating edge cases and adversarial puzzles.")
    print("")
    print("Winner's rules → promoted to fleet standard.")
    print("Competition breeds convergence.")
    print("Rivalry breeds excellence.")
    print("The fleet gets smarter through combat.")
    print("═══════════════════════════════════════════")
