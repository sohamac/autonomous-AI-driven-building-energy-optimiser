# Eco-Loop Building Agents — System Architecture

## 1. System Overview

A closed-loop pipeline connecting EnergyPlus (physics-based building simulation) to an
autonomous control layer via MCP-style tool-calling. The building is a small office in
Mumbai (ISHRAE weather data), simulated over a full calendar year (8760 hourly timesteps).

```
EnergyPlus (.idf + .epw)
      │  eppy
      ▼
MCP Tool Server (mcp_energyplus_server.py)
   ├─ get_current_summary()      → monthly kWh + PMV comfort summary (JSON)
   ├─ list_zone_thermostats()    → discoverable schedule names
   ├─ set_zone_setpoint(...)     → edits occupied-hours setpoint, safety-bounded
   └─ run_simulation()           → re-runs EnergyPlus, regenerates summary
      ▲
      │  tool calls
Control Layer  (two implementations, both using the same tool server)
   ├─ run_agent_loop.py      — LLM agent (Groq / llama-3.1-8b-instant)
   └─ run_hillclimb_loop.py  — deterministic setpoint sweep
```

Both control layers call the identical underlying tool functions — the LLM path exercises
real tool-calling/MCP-style autonomy; the deterministic path is the fallback that produced
the reported energy savings. Both are part of the delivered system.

## 2. Tool-Calling Architecture

Four tools are exposed, matching the MCP tool-server pattern (`FastMCP`), and mirrored
directly into Groq's OpenAI-compatible function-calling schema for the LLM agent:

| Tool | Purpose | Safety bounds |
|---|---|---|
| `get_current_summary` | Compact monthly energy + PMV comfort summary | — |
| `list_zone_thermostats` | Lists valid schedule names | — |
| `set_zone_setpoint` | Edits occupied-hours heating/cooling setpoint | heating 16–24°C, cooling 22–30°C, min 2°C deadband — enforced server-side, not left to the LLM |
| `run_simulation` | Re-runs EnergyPlus, regenerates summary | ~10s runtime |

**Design choice — edit-then-rerun rather than live EMS actuation:** the agent edits the IDF's
`Schedule:Compact` setpoint objects between full annual runs, rather than actuating mid-simulation
via EnergyPlus EMS. This is a legitimate, simpler closed loop for this stage: the agent sees a
real before/after annual result for every action, at the cost of ~10s per iteration instead of
continuous real-time control.

**Setback-preserving setpoint edits:** `set_zone_setpoint` never overwrites an entire schedule.
It parses each `For:` block's `Until:` markers and only replaces the *middle* (occupied-hours)
value, leaving the night/weekend setback values untouched. An earlier naive approach that
overwrote every value would have deleted the building's existing energy-saving setback strategy
and made the "optimized" building run one constant setpoint 24/7 — this was caught and fixed
before the first agent run.

## 3. Prompt Engineering Strategy

The LLM agent (`run_agent_loop.py`) went through three iterations of prompt design, each fixing
a concrete, observed failure:

1. **Objective/constraint framing.** The system prompt explicitly separates a *hard constraint*
   (PMV comfort within -0.5 to +0.5 for ≥90% of occupied hours, non-negotiable) from the
   *objective* (minimize kWh subject to the constraint). This mirrors how a human facilities
   engineer would be briefed, rather than asking the model to balance two competing goals
   implicitly.

2. **Trend-feedback verdicts.** After the first two agent runs both moved setpoints *worse* on
   both metrics (kWh +4.2% and +8.6%, violations +15 and +13 vs. baseline), the summary payload
   was extended with `vs_baseline`, `vs_previous_attempt`, and an explicit `verdict` field
   ("IMPROVED on both metrics" / "GOT WORSE on both metrics — reverse direction" / "MIXED
   result"), with the system prompt instructing the agent to reverse direction on a bad verdict.

3. **Exact schedule names hardcoded into the prompt.** The agent's very first tool call
   hallucinated schedule names (`heating_schedule_1`, `cooling_schedule_1`) instead of using the
   real ones (`HTGSETP_SCH`, `CLGSETP_SCH`) it had just seen in a prior tool result — wasting a
   full LLM call. The fix was to state the two literal, invariant schedule names directly in the
   system prompt rather than relying on the 8B model to extract them correctly from JSON.

**Documented finding — the verdict fix did not fully work.** Even after all three fixes, the
agent's third live setpoint change (iteration 3, cooling 23.5→23.0°C) continued in the same
failing direction instead of reversing, despite `vs_previous_attempt.verdict` correctly reporting
"GOT WORSE on both metrics" one step earlier. This is reported as a finding, not hidden: an 8B
open-source model reliably executes single-step tool calls but does not reliably act on multi-turn
directional feedback. This is the direct justification for the deterministic fallback described
below.

## 4. Latency Management

Each full annual EnergyPlus run takes ~9–16 seconds. Two latency-related failure modes were
encountered and fixed:

- **Groq rate limiting (6000 TPM, free tier).** Message history grows every iteration (the full
  conversation is resent each call), so token cost per call increases over a run. A live run hit
  a 429 mid-loop, immediately after a real setpoint change had been applied but before its
  result could be evaluated. Fix: a fixed inter-iteration delay plus a single retry-with-backoff
  on a 429, so a transient rate limit doesn't abort a run that already made real progress.
- **Wasted iterations.** One agent run spent an iteration calling `run_simulation()` with no
  pending change (because the prior `set_zone_setpoint` call had errored), re-confirming the
  baseline for no new information. Documented as a known inefficiency; not fixed in the fallback
  path since the deterministic sweep never issues a no-op simulation call.

## 5. Handling Lengthy Simulation Logs

EnergyPlus's raw hourly output is 8760 rows/year with dozens of columns. Two summarization layers
keep this tractable for both the LLM context window and human review:

1. `summarize_baseline.py` collapses the 8760-row CSV into a **monthly** JSON summary (kWh,
   avg outdoor/zone temp, avg PMV, % of occupied hours outside the comfort band per zone) —
   roughly a 700x reduction in payload size.
2. `get_compact_summary()` (in `run_agent_loop.py`) further strips this down for the LLM to
   *only* the annual total and the (month, zone) pairs currently violating the comfort
   constraint, plus the trend/verdict fields — the model never sees zones that are already
   comfortable, keeping each tool-call payload small and directly actionable.

## 6. From Agent Autonomy to Deterministic Search

Given the documented limitation in §3, the final reported energy savings come from
`run_hillclimb_loop.py`, a deterministic sweep over the cooling setpoint (heating held fixed —
empirically shown to have no measurable effect on this Mumbai-climate model, since PMV is
positive/warm in nearly every month and heating rarely activates).

The sweep tests a fixed range (24.0°C → 26.0°C in 0.5°C steps), runs a full annual simulation at
each point, and selects the point with the best energy savings among those keeping comfort
violations within a 20% budget above baseline — an explicit, inspectable rule rather than an
opaque model judgment call.

**Result:** cooling=25.0°C, heating=21.0°C → **78,057.8 → 73,040.0 kWh (+6.4% savings)**,
comfort violations 38 → 45 (+18.4%, within the 20% budget). Full curve and methodology in
`hillclimb_log.json` and the accompanying dashboard.

## 7. Summary of What Autonomous vs. Deterministic Each Contribute

- The **LLM agent** demonstrates genuine MCP-style tool-calling autonomy: it reads simulation
  state, reasons about a stated objective/constraint, and issues real control actions back into
  EnergyPlus without human code modification per step — satisfying the hackathon's core
  "AI ingests data, reasons, injects control actions" loop. Its documented failure to act on its
  own trend feedback is reported as an empirical finding about small-model tool-use reliability,
  not concealed.
- The **deterministic sweep** guarantees the quantitative savings claim is real, reproducible,
  and defensible under the "Energy Efficiency Realized" and "Thermal Comfort & Constraints"
  evaluation criteria, using the same underlying MCP tool interface as the agent.
