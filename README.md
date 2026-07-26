# 🌿 Eco-Loop Building Agents
**Autonomous AI-driven building energy optimization — closed-loop control between an open-source LLM and EnergyPlus.**

> A small office building in Mumbai, simulated with real weather data, optimized by an AI agent that reasons over real physics — not a mock, not a toy dataset.

---

## 🎯 Result at a Glance

| Metric | Baseline | Optimized | Change |
|---|---|---|---|
| **Annual electricity** | 78,057.8 kWh | 73,040.0 kWh | **↓ 6.4%** |
| **Cooling setpoint** | 24.0°C | 25.0°C | — |
| **Heating setpoint** | 21.0°C (fixed — negligible effect in this climate) | 21.0°C | — |
| **Comfort violations** | 38 zone-months | 45 zone-months | +7 (within 20% budget) |

📊 Full trade-off curve, rejected attempts, and reasoning: [`dashboard.html`](./dashboard.html) · [`ARCHITECTURE.md`](./ARCHITECTURE.md)

---

## 🧠 What This Actually Is

Most "AI + building energy" demos either fake the simulation or fake the AI. This project does neither:

- **Real physics**: [EnergyPlus](https://energyplus.net) 26.1.0, full annual hourly simulation (8,760 timesteps), real Mumbai weather (ISHRAE `.epw`), real PMV thermal comfort modeling (Fanger method).
- **Real agent**: an open-source LLM ([Llama 3.1](https://groq.com), via Groq) calls MCP-style tools to read simulation state and write setpoint changes back into the model — a genuine closed loop, not a scripted demo.
- **Real trade-offs, shown honestly**: this repo includes the failed attempts, not just the winning result. See [`agent_iteration_log.json`](./agent_iteration_log.json) for two agent runs that made both energy *and* comfort worse before the system converged on a validated, deterministic sweep ([`hillclimb_log.json`](./hillclimb_log.json)).

---

## 🔁 The Closed Loop

```
   EnergyPlus (physics)                     LLM Agent (Groq / Llama 3.1)
 ┌────────────────────┐                    ┌──────────────────────────┐
 │  8,760-hr annual    │ ──summarize────▶   │  Reads compact summary:  │
 │  simulation          │                    │  kWh + comfort violations│
 │  (zone temp, PMV,    │                    │  + trend vs. baseline    │
 │  energy, PMV)        │                    └──────────────────────────┘
 │                      │ ◀──setpoint────               │
 │  Schedule:Compact     │   edit (via eppy,             │ reasons, calls tool
 │  occupied-hours       │   safety-bounded)              ▼
 │  setpoint updated     │                    ┌──────────────────────────┐
 └────────────────────┘                    │  set_zone_setpoint()      │
                                             │  hard bounds enforced:   │
                                             │  16-24°C heat, 22-30°C   │
                                             │  cool, min 2°C deadband  │
                                             └──────────────────────────┘
```

Full breakdown of tool-calling design, prompt engineering iterations (including what *didn't* work and why), latency budget, and context-window management: **[`ARCHITECTURE.md`](./ARCHITECTURE.md)**

---

## 📁 Repository Guide

| File | What it does |
|---|---|
| `run_mumbai_baseline.py` | Fixes the reference IDF to run a real annual Mumbai simulation (not just 2 design days), adds PMV output, saves the baseline |
| `baseline_annual.csv` / `baseline_monthly_summary.json` | Ground-truth baseline: 8,760-row raw output + condensed monthly summary |
| `mcp_energyplus_server.py` | Tool server: `get_current_summary`, `list_zone_thermostats`, `set_zone_setpoint` (safety-bounded, setback-preserving), `run_simulation` |
| `run_agent_loop.py` | LLM agent doing open-ended trial-and-error setpoint search (Groq API) — includes the trend-feedback fix that taught the agent to reverse bad moves |
| `run_hillclimb_loop.py` | Deterministic cooling-setpoint sweep — the validated source of the final +6.4% result |
| `run_agent_decision.py` | Fast path: LLM reasons over the pre-computed sweep and produces a plain-language justified recommendation |
| `dashboard.html` | Quantitative savings dashboard (open directly in a browser) |
| `ARCHITECTURE.md` | Full technical writeup: tool-calling, prompt engineering, latency, context management |
| `check_idf_structure.py` | Diagnostic script used to validate real IDF thermostat/schedule structure before writing control code |
| `EcoLoop_Presentation.pptx` | Slide deck |
| `DEMO_VIDEO_SCRIPT.md` | Script for the recorded PoC walkthrough |

---

## 🚀 Quickstart

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 1. Generate the baseline (requires EnergyPlus installed locally)
python run_mumbai_baseline.py

# 2. Condense it for LLM consumption
python summarize_baseline.py

# 3. Run the deterministic sweep (produces the +6.4% result)
python run_hillclimb_loop.py

# 4. Get an LLM-reasoned recommendation over the sweep (requires GROQ_API_KEY)
export GROQ_API_KEY="your-key-here"
python run_agent_decision.py

# 5. Open the dashboard
open dashboard.html   # or just open the file in any browser
```

Requires [EnergyPlus 26.1.0+](https://energyplus.net/downloads) installed locally, and a free [Groq API key](https://console.groq.com) for the agent steps.

---

## ⚠️ Honest Limitations

- All 5 zones in this reference building share a single global setpoint schedule — there is no true per-zone control in this IDF, so `set_zone_setpoint` is building-wide.
- Control is **between-run** (edit setpoints → re-run full annual simulation), not live in-run EMS actuation — a simpler, more reliable architecture for a hackathon timeframe, documented as a deliberate trade-off in `ARCHITECTURE.md`.
- The open-ended LLM agent (`run_agent_loop.py`) required real debugging to behave sensibly — its early failures are left in the repo (`agent_iteration_log.json`) intentionally, as evidence of iterative, honest engineering rather than a cherry-picked success.

---

*Built for [hackathon name] — Physical AI / Autonomous Building Systems track.*
