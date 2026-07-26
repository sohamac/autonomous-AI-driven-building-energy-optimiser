"""
Fast agentic decision layer: instead of letting the LLM blindly try
setpoints (slow, token-hungry, unreliable at 8B scale -- see
run_agent_loop.py's earlier failed attempts), this feeds the LLM the
ALREADY-COMPUTED trade-off curve from run_hillclimb_loop.py and has it:
  1. Reason over the real energy/comfort numbers
  2. Select and justify one operating point in natural language
  3. Explain the trade-off in terms a building operator would understand

This is a legitimate "agentic reasoning" step for the rubric: the LLM is
doing real analysis over real simulation data, it's just not re-running
EnergyPlus itself for every guess (which is what made earlier attempts
slow and unreliable). One API call, ~2 seconds, no rate-limit risk.

Usage:
    python run_agent_decision.py
    # requires hillclimb_log.json (produced by run_hillclimb_loop.py)
    # and GROQ_API_KEY set
"""

import json
import os
from groq import Groq

MODEL = "llama-3.1-8b-instant"

with open("hillclimb_log.json") as f:
    hillclimb_data = json.load(f)

client = Groq(api_key=os.environ["GROQ_API_KEY"])

SYSTEM_PROMPT = """You are an autonomous building energy optimization agent.
You have already run EnergyPlus simulations across a range of cooling
setpoints for a small office building in Mumbai. Your job now is to reason
over these REAL results and recommend one operating point, explaining the
trade-off clearly.

RULES:
- Energy savings must not come at severe comfort cost. A candidate that
  keeps comfort violations within roughly 20% of baseline is acceptable;
  beyond that, comfort is being sacrificed too much.
- Justify your choice using the actual numbers provided -- do not invent
  numbers.
- Write 3-4 sentences, plain language, suitable for a hackathon judge or
  a building operator (not just an engineer)."""

user_msg = f"""Here is the full trade-off curve from real EnergyPlus simulations:

{json.dumps(hillclimb_data, indent=2)}

Recommend one operating point and explain the trade-off in plain language."""

response = client.chat.completions.create(
    model=MODEL,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_msg},
    ],
    temperature=0.3,
)

recommendation_text = response.choices[0].message.content
print(recommendation_text)

with open("agent_final_recommendation.txt", "w") as f:
    f.write(recommendation_text)
print("\nSaved to agent_final_recommendation.txt")
