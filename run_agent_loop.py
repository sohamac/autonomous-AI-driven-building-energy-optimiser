"""
Closed-loop agent orchestration: Groq-hosted LLM reasons over EnergyPlus
simulation results and calls tools to adjust building setpoints, aiming to
reduce energy while respecting a hard thermal comfort constraint.

This bypasses the MCP transport layer for simplicity -- it imports the same
underlying functions used by mcp_energyplus_server.py directly and exposes
them to Groq's OpenAI-compatible tool-calling API. (You already validated
these functions manually; this just lets the LLM call them instead of you.)

Usage:
    pip install groq
    export GROQ_API_KEY="your-key-here"
    python run_agent_loop.py
"""

import json
import os
from groq import Groq

# Reuse the exact same tool implementations you already tested by hand.
from mcp_energyplus_server import (
    get_current_summary,
    list_zone_thermostats,
    set_zone_setpoint,
    run_simulation,
)

MODEL = "llama-3.1-8b-instant"  # 500,000 tokens/day free tier vs 100,000 for the
                                  # 70b model -- given the token-hungry summary
                                  # payload below, this budget matters more than
                                  # the reasoning-quality difference right now.
MAX_ITERATIONS = 6

client = Groq(api_key=os.environ["GROQ_API_KEY"])


BASELINE_ANNUAL_KWH = 78057.8   # from your original, unmodified baseline run
BASELINE_VIOLATIONS = 38         # count of month/zone comfort violations at baseline

# Tracks every summary seen so far this session, so we can show the agent
# a trend instead of just a single snapshot with no memory of direction.
_history = []


def get_compact_summary() -> str:
    """
    Wraps get_current_summary() but strips it down to only what the agent
    actually needs to act: the annual total, comparison against baseline
    AND against the previous attempt (so the agent can tell whether its
    last move helped or hurt), and ONLY the (month, zone) combinations
    currently violating the comfort constraint.
    """
    full_summary = json.loads(get_current_summary())
    annual_total = full_summary.get("annual_total_kwh")

    violations = []
    for month_key, month_data in full_summary.items():
        if not month_key.startswith("month_"):
            continue
        for zone_name, zone_data in month_data.get("zones", {}).items():
            pct = zone_data.get("pct_hours_outside_comfort_band")
            if pct is not None and pct > 10.0:
                violations.append({
                    "month": month_key,
                    "zone": zone_name,
                    "avg_pmv": zone_data.get("avg_pmv"),
                    "pct_hours_outside_comfort_band": pct,
                })
    violations.sort(key=lambda v: v["pct_hours_outside_comfort_band"], reverse=True)

    prev = _history[-1] if _history else None
    result = {
        "annual_total_kwh": annual_total,
        "num_comfort_violations": len(violations),
        "worst_violations": violations[:10],
        "vs_baseline": {
            "baseline_kwh": BASELINE_ANNUAL_KWH,
            "kwh_change_pct": round(100 * (annual_total - BASELINE_ANNUAL_KWH) / BASELINE_ANNUAL_KWH, 1),
            "baseline_violations": BASELINE_VIOLATIONS,
            "violations_change": len(violations) - BASELINE_VIOLATIONS,
        },
    }
    if prev is not None:
        result["vs_previous_attempt"] = {
            "previous_kwh": prev["kwh"],
            "kwh_change_pct": round(100 * (annual_total - prev["kwh"]) / prev["kwh"], 1) if prev["kwh"] else None,
            "previous_violations": prev["violations"],
            "violations_change": len(violations) - prev["violations"],
            "verdict": (
                "IMPROVED on both metrics" if annual_total < prev["kwh"] and len(violations) <= prev["violations"]
                else "GOT WORSE on both metrics -- try reversing direction, not continuing the same way"
                if annual_total >= prev["kwh"] and len(violations) >= prev["violations"]
                else "MIXED result -- a trade-off happened"
            ),
        }

    _history.append({"kwh": annual_total, "violations": len(violations)})

    result["note"] = ("Only zone/months with >10% of occupied hours outside PMV "
                       "band -0.5 to 0.5 are listed. If num_comfort_violations is 0, "
                       "the comfort constraint is fully satisfied. Pay close attention "
                       "to vs_previous_attempt.verdict before deciding your next move.")
    return json.dumps(result)

# --- Comfort-constraint system prompt: the objective/constraint split from
#     our earlier discussion is baked in explicitly here, not left implicit. ---
SYSTEM_PROMPT = """You are an autonomous building energy optimization agent controlling
a small office building in Mumbai, simulated in EnergyPlus.

YOUR OBJECTIVE (in priority order):
1. HARD CONSTRAINT -- Thermal comfort: for every month and every zone, keep
   PMV (Predicted Mean Vote) within the band -0.5 to +0.5 for AT LEAST 90%
   of occupied hours ("pct_hours_outside_comfort_band" must stay below 10.0
   for every zone in every month). This constraint is NOT negotiable -- do
   not sacrifice it to save energy.
2. OBJECTIVE -- Subject to constraint 1 being satisfied, minimize total
   annual electricity consumption (annual_total_kwh).

IMPORTANT LESSON FROM A PRIOR MANUAL TEST: widening the heating/cooling
deadband (e.g. dropping heating to 20C and raising cooling to 25C
simultaneously) reduced energy by ~6% but pushed multiple zones to 80-100%
of hours outside the comfort band in several months. Do NOT repeat this
mistake -- prefer small, asymmetric adjustments (e.g. change only cooling,
or only heating, by 0.5-1C at a time) and check the resulting summary
before making a larger change.

CRITICAL -- READ THE TREND DATA, NOT JUST THE SNAPSHOT: every summary
includes "vs_baseline" and (after your first change) "vs_previous_attempt",
with an explicit "verdict" field. YOU MUST check this before deciding your
next move:
  - If verdict says "GOT WORSE on both metrics": your last change was a
    mistake. REVERSE it -- move the setpoint in the OPPOSITE direction from
    your last change, do not continue further in the same direction.
  - If verdict says "IMPROVED on both metrics": you're on the right track.
    You may try a further small step in the SAME direction.
  - If verdict says "MIXED result": a trade-off happened. Make a smaller,
    more targeted adjustment rather than a bigger one.
Narrowing the heating/cooling deadband (raising heating setpoint AND/OR
lowering cooling setpoint) generally INCREASES energy use, since the HVAC
runs more often in both modes. Widening the deadband generally decreases
energy but risks comfort violations, as seen in the manual test above. The
correct move is usually a SMALL, ONE-DIRECTION adjustment (change only
heating OR only cooling, not both, by 0.5C), evaluated one step at a time.

Available tools:
- get_current_summary: COMPACT view -- annual total kWh, plus only the
  month/zone combinations currently violating the comfort constraint. If
  num_comfort_violations is 0, comfort is fully satisfied everywhere.
- list_zone_thermostats: see valid schedule names to act on
- set_zone_setpoint: propose a new OCCUPIED-HOURS heating/cooling setpoint
  (building-wide -- all zones share one schedule in this model). Hard
  safety bounds are enforced server-side: heating 16-24C, cooling 22-30C,
  minimum 2C deadband. Out-of-bounds requests are rejected automatically.
- run_simulation: re-run EnergyPlus with your current setpoints and get
  the new compact summary

WORKFLOW: Call get_current_summary first. Identify the worst comfort
violations and the current energy baseline. Propose ONE targeted setpoint
change via set_zone_setpoint. Call run_simulation to see the effect.
Evaluate against the hard constraint above. If comfort is still violated,
adjust again. If comfort is satisfied and energy improved, you may try a
further small refinement, or stop and report your final result.

When you believe you have reached a good stopping point (constraint
satisfied, energy improved from baseline, no further easy gains), respond
with plain text (no tool call) summarizing what you did and the final
numbers. Do not call more than one tool per turn.
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_summary",
            "description": "Returns a COMPACT summary: annual total kWh, and only the "
                            "month/zone combinations currently violating the comfort "
                            "constraint (>10% of occupied hours outside PMV -0.5 to 0.5). "
                            "If num_comfort_violations is 0, comfort is fully satisfied.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_zone_thermostats",
            "description": "Lists thermostat objects and their heating/cooling schedule names.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_zone_setpoint",
            "description": "Sets a new occupied-hours heating/cooling setpoint (building-wide). "
                            "Hard safety bounds are enforced automatically.",
            "parameters": {
                "type": "object",
                "properties": {
                    "heating_schedule_name": {"type": "string"},
                    "cooling_schedule_name": {"type": "string"},
                    "new_heating_setpoint_c": {"type": "number"},
                    "new_cooling_setpoint_c": {"type": "number"},
                },
                "required": [
                    "heating_schedule_name", "cooling_schedule_name",
                    "new_heating_setpoint_c", "new_cooling_setpoint_c",
                ],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_simulation",
            "description": "Re-runs EnergyPlus with the current setpoints and returns the new summary.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]

# Maps tool names to the actual Python functions to call
def _run_simulation_and_summarize(**kwargs):
    run_simulation()  # actually re-runs EnergyPlus and writes the fresh JSON
    return get_compact_summary()


TOOL_IMPL = {
    "get_current_summary": lambda **kwargs: get_compact_summary(),
    "list_zone_thermostats": lambda **kwargs: list_zone_thermostats(),
    "set_zone_setpoint": lambda **kwargs: set_zone_setpoint(**kwargs),
    "run_simulation": _run_simulation_and_summarize,
}


def run_agent():
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "Begin. Check the current summary and propose your first setpoint adjustment."},
    ]

    iteration_log = []

    from groq import RateLimitError, APIStatusError

    for i in range(MAX_ITERATIONS):
        print(f"\n{'='*20} ITERATION {i+1} {'='*20}")

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.2,
            )
        except RateLimitError as e:
            print(f"\nRATE LIMIT HIT -- stopping gracefully. Details: {e}")
            print("Wait for the cooldown period shown above, or reduce MAX_ITERATIONS, "
                  "before running again.")
            break
        except APIStatusError as e:
            print(f"\nAPI ERROR -- stopping gracefully. Details: {e}")
            break

        choice = response.choices[0]

        # Build a minimal, clean assistant message dict instead of dumping
        # the full SDK object -- Groq's API rejects extra fields like
        # "annotations" that the SDK response object includes but the
        # request schema doesn't accept.
        assistant_msg = {
            "role": "assistant",
            "content": choice.message.content,
        }
        if choice.message.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]
        messages.append(assistant_msg)

        if not choice.message.tool_calls:
            # Model responded with plain text -- treat as a stopping point
            print(f"\nAgent final message:\n{choice.message.content}")
            break

        for tool_call in choice.message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments)
                if fn_args is None:
                    fn_args = {}
            except json.JSONDecodeError:
                fn_args = {}

            print(f"\n>> Agent calls: {fn_name}({fn_args})")

            if fn_name not in TOOL_IMPL:
                result = json.dumps({"error": f"Unknown tool: {fn_name}"})
            else:
                try:
                    result = TOOL_IMPL[fn_name](**fn_args)
                except Exception as e:
                    result = json.dumps({"error": f"Tool execution failed: {str(e)}"})

            # Log every iteration for your dashboard / architecture doc
            iteration_log.append({
                "iteration": i + 1,
                "tool": fn_name,
                "args": fn_args,
                "result_snippet": str(result)[:500],
            })

            print(f"<< Result (truncated): {str(result)[:300]}")

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": str(result),
            })

    with open("agent_iteration_log.json", "w") as f:
        json.dump(iteration_log, f, indent=2)
    print(f"\n\nSaved {len(iteration_log)} logged tool calls to agent_iteration_log.json")


if __name__ == "__main__":
    run_agent()
