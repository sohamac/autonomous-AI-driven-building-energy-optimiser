# Eco-Loop Building Agents — Demo Video Script
**Target length: 3:00.** Record your terminal + dashboard + slides; voiceover reads the script live or is recorded separately and synced.

---

## [0:00–0:20] Hook + Problem (screen: title slide)
**Show:** Slide 1 (title)

**Say:**
"Buildings burn 40% of global energy, run on rigid rule-based schedules, and never adapt to real conditions. We built a closed loop that changes that: EnergyPlus simulates a real small office in Mumbai, an AI reads its live performance, reasons about energy versus comfort, and pushes real setpoint changes back in — automatically."

---

## [0:20–0:50] Architecture (screen: slide 3, Technical Approach)
**Show:** Slide 3, then terminal: `cat mcp_energyplus_server.py` scrolled to the tool definitions

**Say:**
"The core is an MCP-style tool server sitting on top of EnergyPlus via eppy. Four tools: `get_current_summary` reads monthly energy and PMV thermal comfort data. `set_zone_setpoint` edits the building's heating and cooling setpoints — with hard safety bounds enforced in code, not left to the AI. And `run_simulation` re-runs a full annual EnergyPlus simulation and reports back. That's the whole loop: read, reason, act, verify."

---

## [0:50–1:40] Live agent run (screen: terminal, run_agent_loop.py)
**Show:** Terminal running `python run_agent_loop.py` — let real output scroll (speed up 2-3x in edit if needed), pause on the tool calls

**Say (over the scrolling log):**
"Here's the autonomous agent live: an open-source LLM — llama-3.1-8b-instant — calling these tools with no human writing code in between. It reads the baseline: 78,057 kilowatt-hours a year, 38 comfort violations. It calls `set_zone_setpoint`. It calls `run_simulation`. EnergyPlus actually re-runs — you can see it warming up, simulating the full year, writing results back out. Then the agent reads the new numbers and decides its next move."

**[Cut in close-up of the terminal moment where verdict field appears]**

"We gave it explicit trend feedback — 'you got worse, reverse direction' — and that's a real, honest finding from this build: the 8-billion-parameter model didn't always follow its own feedback. We documented that instead of hiding it."

---

## [1:40–2:20] Deterministic result (screen: terminal running the sweep, then dashboard)
**Show:** Terminal tail of `run_hillclimb_loop.py` output table, then cut to `dashboard.html` open in browser

**Say:**
"So alongside the learning agent, we built a deterministic supervisor — same MCP tools, same closed loop, but a transparent search instead of relying on the LLM's judgment for the final call. It swept the cooling setpoint, ran a full annual simulation at each point, and here's the real result."

**[Point at dashboard chart]**

"78,057.8 kilowatt-hours baseline, down to 73,040 — a 6.4% real, reproducible energy saving. Comfort violations did rise, from 38 to 45, and we're upfront about that trade-off — it's within an explicit 20% comfort budget we set, not hidden."

---

## [2:20–2:45] Closed loop, proven (screen: split — IDF diff or before/after setpoint values)
**Show:** Quick before/after of the .idf setpoint schedule values, or the dashboard table again

**Say:**
"This is a genuine forward-injection loop — the AI's decisions are written directly back into the active building model and take effect on the next run. Not a one-off recommendation. Not a static rule. A live, physics-grounded, closed loop."

---

## [2:45–3:00] Close (screen: slide 1 or artifacts slide)
**Say:**
"Eco-Loop Building Agents: EnergyPlus, MCP tool-calling, and an open-source LLM, proving a real 6.4% energy saving with an explicit comfort constraint — end to end, autonomously. Thank you."

---

## Recording checklist
- [ ] Terminal font size large enough to read on a shared screen (14pt+)
- [ ] Pre-run `run_agent_loop.py` once before recording so you know which iteration to keep in frame (don't record all 6 raw — cut to the interesting ones: first tool call, the verdict field, the setpoint apply)
- [ ] Have `dashboard.html` already open in a browser tab, zoomed to a readable size
- [ ] Cut EnergyPlus's verbose "Warming up / Updating Shadowing Calculations" spam down to ~2-3 seconds of real footage per run in the edit — keep just enough to prove it's really running
- [ ] Total runtime check: read the script aloud once with a timer before recording final take
