#!/usr/bin/env python3
"""
Fleet Action Generator
Reads synthesis + PLATO data, generates prioritized action items
for the fleet to work on next.
"""
import json, sys, urllib.request
from pathlib import Path
from datetime import datetime, timezone

GROQ_KEY = "${GROQ_API_KEY}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
RESEARCH_DIR = Path("/home/ubuntu/.openclaw/workspace/research/mud-night-shift")

def ask_llm(system, prompt, max_tokens=800):
    try:
        payload = json.dumps({
            "model": "llama-3.3-70b-versatile",
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            "max_tokens": max_tokens, "temperature": 0.6,
        }).encode()
        req = urllib.request.Request(GROQ_URL, data=payload, headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {GROQ_KEY}", "User-Agent": "curl/7.88",
        })
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except:
        return ""

def main():
    # Load synthesis
    synthesis_file = RESEARCH_DIR / "FLEET-SYNTHESIS.md"
    if not synthesis_file.exists():
        print("No synthesis found")
        return
    
    synthesis = synthesis_file.read_text()
    
    # Load PLATO room stats
    try:
        req = urllib.request.Request("http://localhost:8847/status")
        with urllib.request.urlopen(req, timeout=5) as resp:
            plato = json.loads(resp.read())
        rooms = plato.get("rooms", {})
        plato_summary = "\n".join(f"- {name}: {info['tile_count']} tiles" for name, info in sorted(rooms.items(), key=lambda x: -x[1]['tile_count']))
    except:
        plato_summary = "PLATO unavailable"
    
    # Generate action items
    system = """You are a fleet architect. Based on the research synthesis and PLATO training data below, 
generate 5 CONCRETE, IMPLEMENTABLE action items for the Cocapn fleet. Each item should:
1. Have a clear deliverable (file, protocol, prototype)
2. Be assigned to a specific agent type (zeroclaw, oracle1, jetsonclaw1, forgemaster)
3. Include a rough implementation sketch (3-5 lines of pseudocode or file structure)
4. Reference specific insights from the research

Format as markdown with ## headers. Be ruthlessly practical."""

    prompt = f"""# Research Synthesis (condensed)
{synthesis[:3000]}

# PLATO Training Data
{plato_summary}

# Generate 5 prioritized action items:"""

    result = ask_llm(system, prompt, max_tokens=1200)
    
    if result:
        output = RESEARCH_DIR / "FLEET-ACTIONS.md"
        with open(output, "w") as f:
            f.write(f"# Fleet Action Items\n")
            f.write(f"# Generated: {datetime.now(timezone.utc).isoformat()}\n")
            f.write(f"# Based on: MUD research synthesis + PLATO training data\n\n")
            f.write(result)
        print(f"Actions written to {output}")
        print(result[:1000])
    else:
        print("LLM failed")

if __name__ == "__main__":
    main()
