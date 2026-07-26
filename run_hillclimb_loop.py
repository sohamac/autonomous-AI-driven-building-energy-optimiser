"""
Deterministic closed-loop optimizer: sweeps the COOLING setpoint across a
fixed range and reports the full energy-vs-comfort trade-off curve (a Pareto
frontier), instead of stopping at the first point that adds any violations.

Why this design: an earlier "stop on first violation increase" version
discarded a genuinely useful result -- 24.5C cut annual energy by 3.7%
while adding only 7 more comfort violations (38 -> 45). That is a real,
defensible trade-off, not a failure. The hackathon's own evaluation
criteria reward "intelligently balancing both" energy and comfort, not
hitting exactly zero violations, so the right output is the full curve,
with an explicit rule selecting one recommended operating point on it.

Heating is held fixed at 21C throughout -- proven to have no measurable
effect on this Mumbai-climate model (PMV is positive/warm in nearly every
month, so heating rarely activates; see run_agent_loop.py iteration log).

Usage:
    python run_hillclimb_loop.py
"""

import json

from mcp_energyplus_server import (
    get_current_summary,
    set_zone_setpoint,
    run_simulation,
)

HEATING_FIXED_C = 21.0
COOLING_SWEEP_C = [24.0, 24.5, 25.0, 25.5, 26.0]  # baseline through the manual test's known-bad extreme

BASELINE_KWH = 78057.8
BASELINE_VIOLATIONS = 38
COMFORT_VIOLATION_THRESHOLD_PCT = 10.0


def evaluate(cooling_c: float, heating_c: float = HEATING_FIXED_C) -> dict:
    """Applies a setpoint, re-runs EnergyPlus, and returns a parsed compact result."""
    set_result = json.loads(set_zone_setpoint(
        heating_schedule_name="HTGSETP_SCH",
        cooling_schedule_name="CLGSETP_SCH",
        new_heating_setpoint_c=heating_c,
        new_cooling_setpoint_c=cooling_c,
    ))
    if "error" in set_result:
        return {"error": set_result["error"], "cooling_c": cooling_c, "heating_c": heating_c}

    run_simulation()
    full_summary = json.loads(get_current_summary())

    violations = []
    for month_key, month_data in full_summary.items():
        if not month_key.startswith("month_"):
            continue
        for zone_name, zone_data in month_data.get("zones", {}).items():
            pct = zone_data.get("pct_hours_outside_comfort_band")
            if pct is not None and pct > COMFORT_VIOLATION_THRESHOLD_PCT:
                violations.append({
                    "month": month_key, "zone": zone_name,
                    "avg_pmv": zone_data.get("avg_pmv"),
                    "pct_hours_outside_comfort_band": pct,
                })

    annual_kwh = full_summary.get("annual_total_kwh")
    return {
        "cooling_c": cooling_c,
        "heating_c": heating_c,
        "annual_kwh": annual_kwh,
        "num_violations": len(violations),
        "kwh_savings_pct": round(100 * (BASELINE_KWH - annual_kwh) / BASELINE_KWH, 1),
        "violations_change": len(violations) - BASELINE_VIOLATIONS,
        "worst_violations": sorted(
            violations, key=lambda v: v["pct_hours_outside_comfort_band"], reverse=True
        )[:5],
    }


def pick_recommended(curve: list) -> dict:
    """
    Selects a single recommended operating point from the full curve: the
    point with the best savings among those that keep violations from
    growing more than 20% above baseline (a deliberately explicit,
    inspectable rule instead of an opaque LLM judgment call).
    """
    max_allowed_violations = BASELINE_VIOLATIONS * 1.20  # 20% comfort-degradation budget
    candidates = [p for p in curve if "error" not in p and p["num_violations"] <= max_allowed_violations]
    if not candidates:
        return curve[0]  # fall back to the first (baseline) point
    return max(candidates, key=lambda p: p["kwh_savings_pct"])


def run_sweep():
    print("=" * 60)
    print("COOLING SETPOINT SWEEP -- full energy/comfort trade-off curve")
    print(f"Baseline: {BASELINE_KWH} kWh, {BASELINE_VIOLATIONS} violations")
    print("=" * 60)

    curve = []
    for cooling_c in COOLING_SWEEP_C:
        print(f"\n--- Testing cooling={cooling_c}C, heating={HEATING_FIXED_C}C ---")
        result = evaluate(cooling_c, HEATING_FIXED_C)
        if "error" in result:
            print(f"REJECTED by safety bounds: {result['error']}")
            curve.append(result)
            continue
        print(f"Result: {result['annual_kwh']} kWh ({result['kwh_savings_pct']:+.1f}% vs baseline), "
              f"{result['num_violations']} violations ({result['violations_change']:+d} vs baseline)")
        curve.append(result)

    recommended = pick_recommended(curve)

    print("\n" + "=" * 60)
    print("FULL TRADE-OFF CURVE")
    print("=" * 60)
    print(f"{'Cooling C':>10} | {'kWh':>10} | {'Savings %':>10} | {'Violations':>10} | {'vs Baseline':>12}")
    for p in curve:
        if "error" in p:
            print(f"{p.get('cooling_c', '?'):>10} | REJECTED: {p['error']}")
            continue
        marker = "  <-- RECOMMENDED" if p is recommended else ""
        print(f"{p['cooling_c']:>10} | {p['annual_kwh']:>10} | {p['kwh_savings_pct']:>+9.1f}% | "
              f"{p['num_violations']:>10} | {p['violations_change']:>+11d}{marker}")

    print(f"\nRecommended operating point: cooling={recommended['cooling_c']}C, "
          f"heating={HEATING_FIXED_C}C")
    print(f"  -> {recommended['kwh_savings_pct']:+.1f}% energy vs baseline, "
          f"{recommended['num_violations']} violations "
          f"({recommended['violations_change']:+d} vs baseline's {BASELINE_VIOLATIONS})")
    print("  Selection rule: best energy savings among points that keep comfort "
          "violations within 20% of baseline.")

    # Leave the IDF set to the recommended point as the final demo state.
    set_zone_setpoint(
        heating_schedule_name="HTGSETP_SCH",
        cooling_schedule_name="CLGSETP_SCH",
        new_heating_setpoint_c=HEATING_FIXED_C,
        new_cooling_setpoint_c=recommended["cooling_c"],
    )
    run_simulation()

    with open("hillclimb_log.json", "w") as f:
        json.dump({
            "baseline_kwh": BASELINE_KWH,
            "baseline_violations": BASELINE_VIOLATIONS,
            "full_curve": curve,
            "recommended": recommended,
        }, f, indent=2)
    print("\nSaved full trade-off curve to hillclimb_log.json")


if __name__ == "__main__":
    run_sweep()
