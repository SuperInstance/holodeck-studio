#!/usr/bin/env python3
"""
Fleet Synthesizer — Periodically reads all research, finds patterns,
writes synthesis documents, and posts highlights to the MUD.
"""

import json
import time
import sys
import urllib.request
from pathlib import Path
from datetime import datetime, timezone
from collections import defaultdict

sys.path.insert(0, '/tmp/cocapn-mud')
from client import MUDClient

RESEARCH_DIR = Path("/home/ubuntu/.openclaw/workspace/research/mud-night-shift")
GROQ_KEY = "${GROQ_API_KEY}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

def ask_llm(system, prompt, max_tokens=500):
    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        }).encode()
        req = urllib.request.Request(GROQ_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_KEY}",
            "User-Agent": "curl/7.88",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except:
        return ""

def load_insights():
    """Load all insights from research logs."""
    by_topic = defaultdict(list)
    for f in sorted(RESEARCH_DIR.glob("*.jsonl")):
        for line in open(f):
            try:
                d = json.loads(line)
                if d.get("kind") == "insight" and len(d.get("content", "")) > 80:
                    by_topic[d["topic"]].append(d["content"])
            except:
                pass
    return by_topic

def synthesize_topic(topic, insights):
    """Use LLM to synthesize a topic's insights into a cohesive summary."""
    # Pick up to 15 most diverse insights
    sample = insights[-15:]
    insights_text = "\n".join(f"- {i[:200]}" for i in sample)
    
    system = (
        "You are a fleet research synthesizer. Take raw agent insights and produce a concise "
        "technical synthesis. Identify: 1) Key design patterns emerging 2) Concrete proposals "
        "3) Open questions 4) Implementation priorities. Be specific. No fluff."
    )
    prompt = f"Topic: {topic}\n\nAgent insights:\n{insights_text}\n\nSynthesize:"
    return ask_llm(system, prompt, max_tokens=400)

async def post_to_mud(title, content):
    """Post a synthesis note to the MUD."""
    import asyncio
    async with MUDClient("oracle1", "lighthouse", "localhost", 7777) as mud:
        await mud.go("tavern")
        # Post a summary note
        note = f"[Fleet Synthesis] {title}: {content[:200]}"
        await mud.write_note(note)
        await mud.say(f"📋 Fleet synthesis posted: {title}")
        print(f"Posted to MUD: {title}")

def main():
    print(f"[{datetime.now(timezone.utc).isoformat()[:19]}] Synthesizer starting...")
    
    by_topic = load_insights()
    total = sum(len(v) for v in by_topic.values())
    print(f"Loaded {total} insights across {len(by_topic)} topics")
    
    syntheses = {}
    for topic, insights in sorted(by_topic.items()):
        if len(insights) < 3:
            continue
        print(f"Synthesizing {topic} ({len(insights)} insights)...")
        result = synthesize_topic(topic, insights)
        if result:
            syntheses[topic] = result
            print(f"  → {len(result)} chars")
    
    # Write synthesis document
    output = RESEARCH_DIR / "FLEET-SYNTHESIS.md"
    with open(output, "w") as f:
        f.write(f"# Fleet Research Synthesis\n")
        f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
        f.write(f"# {total} insights across {len(by_topic)} topics\n\n")
        for topic, synthesis in sorted(syntheses.items()):
            f.write(f"## {topic}\n\n{synthesis}\n\n")
        # Cross-topic patterns
        if len(syntheses) >= 3:
            all_text = "\n".join(f"## {t}\n{s}" for t, s in syntheses.items())
            cross = ask_llm(
                "You are a visionary architect. Look at these research syntheses from different topics and find "
                "cross-cutting patterns, surprising connections, and emergent themes. Be specific. 2-3 paragraphs.",
                f"Syntheses:\n{all_text[:3000]}\n\nCross-cutting patterns:",
                max_tokens=400,
            )
            if cross:
                f.write(f"## Cross-Cutting Patterns\n\n{cross}\n")
    
    print(f"\nSynthesis written to {output}")
    
    # Post highlight to MUD
    import asyncio
    if syntheses:
        top_topic = max(syntheses.keys(), key=lambda t: len(by_topic[t]))
        asyncio.run(post_to_mud(top_topic, syntheses[top_topic][:150]))
    
    print("Done.")

if __name__ == "__main__":
    main()
