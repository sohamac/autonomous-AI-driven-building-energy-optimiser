# Eco-Loop Building Agents — Demo Video Script
**Target length: 3:00.** Record screen + voiceover (live or dubbed after). Exact instructions for where each shot comes from are under each beat — follow them in order and you can record this in one pass.

---

## Before you hit record — get everything open and ready

Open these in order, in this layout, before you press record:
1. **Terminal**, `cd` into your project folder, font size bumped to 16–18pt (⌘+ a few times), window sized to fill most of the screen
2. **`EcoLoop_Presentation.pptx`** open in a slides viewer, on Slide 1 (title)
3. **`dashboard.html`** already open in a browser tab (double-click the file, or `open dashboard.html` on Mac) — zoom the browser to ~125% so text is readable on a recording
4. Run `python main.py run` **once, all the way through, before recording**, so nothing crashes live and you know exactly which terminal moments to keep in the final cut

You'll be switching between the terminal and the browser/slides — have both windows already open so switching is a clean screen-swap, not an alt-tab hunt.

---

## [0:00–0:20] Hook + Problem
**Screen:** Slide 1 of `EcoLoop_Presentation.pptx` (title slide) — full screen, no other windows visible.

**Say:**
> "Buildings burn 40% of global energy, running on rigid, rule-based schedules that never adapt to real conditions. We built a closed loop that changes that: EnergyPlus simulates a real small office in Mumbai, an AI reads its live performance, reasons about energy versus comfort, and pushes real setpoint changes back in — automatically."

---

## [0:20–0:50] Architecture
**Screen:** Switch to Terminal. Type and run:
```
cat mcp_energyplus_server.py
```
Let it print, then **scroll (using your mouse/trackpad, slowly)** down to the four `@mcp.tool()` function definitions — pause scrolling there so viewers can read the function names on screen while you talk.

**Say:**
> "The core is an MCP-style tool server sitting on top of EnergyPlus, via a Python library called eppy. Four tools: `get_current_summary` reads monthly energy and thermal-comfort data. `set_zone_setpoint` edits the building's heating and cooling setpoints, with hard safety bounds enforced in code — not left to the AI to decide. And `run_simulation` re-runs a full annual EnergyPlus simulation and reports back. Read, reason, act, verify — that's the whole loop."

---

## [0:50–1:40] Live agent run
**Screen:** Terminal. Type and run:
```
python run_agent_loop.py
```
Since you already ran this once before recording, you know what's coming — **let it run live for real** for the first ~15 seconds (viewers need to see it's not faked), then, if editing afterward, speed up the plain EnergyPlus scrolling text (the "Warming up" spam) by 2–3x, and cut back to normal speed exactly when a tool call or the `verdict` field appears in the output.

**Say (while the log scrolls):**
> "Here's the agent running live: an open-source LLM — llama-3.1-8b-instant — calling these tools with no human writing code in between. It reads the baseline: 78,057 kilowatt-hours a year, 38 comfort violations. It calls `set_zone_setpoint`. It calls `run_simulation`. EnergyPlus actually re-runs — you can see it warming up, simulating the full year, writing results back out. Then it reads the new numbers and decides its next move."

**[Cut to a close-up / zoomed crop of the terminal, right where the `verdict` field text appears in your saved output]**

**Say:**
> "We gave it explicit trend feedback — 'you got worse, reverse direction.' That's a real, honest finding from building this: the 8-billion-parameter model didn't always follow its own feedback perfectly. We documented that instead of hiding it."

---

## [1:40–2:20] Deterministic result
**Screen:** Terminal. Type and run:
```
python run_hillclimb_loop.py
```
Let it scroll briefly (speed up in edit if long), then **cut to the printed results table at the very end of the output** — pause there for 2–3 seconds so it's readable. Then **switch windows to the already-open `dashboard.html` browser tab.**

**Say:**
> "Alongside the learning agent, we built a deterministic supervisor — same tools, same closed loop, but a transparent search instead of relying purely on the LLM's judgment for the final call. It swept the cooling setpoint, ran a full annual simulation at each point, and here's the real result."

**[On the dashboard: point your cursor at the trade-off chart and the KPI numbers at the top]**

**Say:**
> "78,057.8 kilowatt-hours baseline, down to 73,040 — a real, reproducible 6.4% energy saving. Comfort violations did rise, from 38 to 45, and we're upfront about that — it's within an explicit 20% comfort budget we set, not hidden."

---

## [2:20–2:45] Closed loop, proven
**Screen:** Terminal. Type and run:
```
git diff HEAD~3 -- RefBldgSmallOffice_Mumbai_baseline.idf | grep -A2 "CLGSETP_SCH\|HTGSETP_SCH"
```
(This shows the actual setpoint schedule lines that changed in the IDF file — a real before/after diff, not a mockup. If this specific diff command doesn't show clean output on your machine, an acceptable substitute is opening the `.idf` file in a text editor and highlighting the `Schedule:Compact` setpoint values directly.)

**Say:**
> "This is a genuine forward-injection loop — the AI's decisions are written directly back into the active building model and take effect on the next run. Not a one-off recommendation. Not a static rule. A live, physics-grounded, closed loop."

---

## [2:45–3:00] Close
**Screen:** Switch back to the slides — Slide 1 (title) or your Artifacts slide, whichever looks cleaner as a closing frame.

**Say:**
> "Eco-Loop Building Agents: EnergyPlus, MCP tool-calling, and an open-source LLM, proving a real 6.4% energy saving with an explicit comfort constraint — end to end, autonomously. Thank you."

---

## Recording checklist
- [ ] Terminal font size 16–18pt, window filling most of the screen
- [ ] Pre-ran `run_agent_loop.py` and `run_hillclimb_loop.py` once before recording, so you already know which exact moments to keep/cut and nothing surprises you live
- [ ] `dashboard.html` already open in a browser tab, zoomed to ~125%, before you start recording
- [ ] `EcoLoop_Presentation.pptx` already open on Slide 1 before you start recording
- [ ] In editing: speed up EnergyPlus's "Warming up / Updating Shadowing Calculations" spam by 2–3x, cut back to normal speed at tool calls and the `verdict` field
- [ ] Read the full script aloud once, with a timer, before your final take — trim wherever you run long
- [ ] Do one full dry run of switching windows (terminal → dashboard → slides) so the actual recording has no fumbled alt-tabs
