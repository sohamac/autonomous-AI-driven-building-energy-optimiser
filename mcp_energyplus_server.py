"""
MCP server exposing tools that let an LLM agent:
  1. read the current simulation's monthly summary (energy + comfort)
  2. propose a new heating/cooling setpoint for a given zone
  3. trigger a re-run of EnergyPlus with the updated setpoints
  4. read back the new summary to see the effect of its own action

This is the "between-run" control architecture: the agent doesn't control
EnergyPlus mid-simulation -- it edits the IDF's thermostat setpoints, the
whole year re-runs, and the agent sees the new annual/monthly result. This
is simpler to get working reliably than live in-run EMS actuation, and is
a legitimate closed loop for this stage of the project.

Usage:
    source myenv/bin/activate
    pip install mcp
    python mcp_energyplus_server.py

Then point your MCP client (Claude Desktop config, or your own agent
orchestration script) at this server.
"""

import json
import os
import subprocess
import sys

from eppy.modeleditor import IDF
from mcp.server.fastmcp import FastMCP

# ---- EDIT THESE PATHS FOR YOUR MACHINE ----
IDD_PATH = "/Applications/EnergyPlus-26-1-0/Energy+.idd"
IDF_PATH = "/Users/apple/Desktop/Honeywell2/RefBldgSmallOffice_Mumbai_baseline.idf"
EPW_PATH = "/Users/apple/Desktop/Honeywell2/IND_Mumbai.430030_ISHRAE.epw"
OUTPUT_DIR = "./output_agent_run"
SUMMARY_SCRIPT_OUTPUT = "baseline_monthly_summary.json"  # produced by summarize_baseline.py
# --------------------------------------------------

IDF.setiddname(IDD_PATH)

mcp = FastMCP("energyplus-control")


@mcp.tool()
def get_current_summary() -> str:
    """
    Returns the current monthly energy + comfort (PMV) summary as JSON.
    Call this first to see where energy is being spent and where comfort
    is out of the acceptable PMV band (-0.5 to 0.5) before proposing changes.
    """
    if not os.path.exists(SUMMARY_SCRIPT_OUTPUT):
        return json.dumps({"error": f"{SUMMARY_SCRIPT_OUTPUT} not found. "
                                     f"Run summarize_baseline.py first."})
    with open(SUMMARY_SCRIPT_OUTPUT) as f:
        return f.read()


@mcp.tool()
def list_zone_thermostats() -> str:
    """
    Lists all ThermostatSetpoint:DualSetpoint objects in the current IDF,
    showing their name and the schedule names they reference for heating
    and cooling setpoints. Use this to find valid zone/thermostat names
    before calling set_zone_setpoint.
    """
    idf = IDF(IDF_PATH, EPW_PATH)
    stats = idf.idfobjects["THERMOSTATSETPOINT:DUALSETPOINT"]
    result = []
    for s in stats:
        result.append({
            "name": s.Name,
            "heating_schedule": s.Heating_Setpoint_Temperature_Schedule_Name,
            "cooling_schedule": s.Cooling_Setpoint_Temperature_Schedule_Name,
        })
    return json.dumps(result, indent=2)


@mcp.tool()
def set_zone_setpoint(heating_schedule_name: str, cooling_schedule_name: str,
                       new_heating_setpoint_c: float, new_cooling_setpoint_c: float) -> str:
    """
    Sets a new OCCUPIED-HOURS heating and cooling setpoint temperature
    (in Celsius) for the given schedule names. NOTE: in this building, all
    5 zones share the same two schedules (HTGSETP_SCH / CLGSETP_SCH), so
    this effectively controls the whole building at once, not a single zone.

    Only the occupied-hours setpoint value is changed -- night/weekend
    setback values and design-day values are left untouched, preserving
    the building's existing energy-saving setback strategy.

    IMPORTANT SAFETY BOUNDS enforced here (not left to the LLM to self-police):
      - heating setpoint must be between 16 and 24 C
      - cooling setpoint must be between 22 and 30 C
      - cooling setpoint must be at least 2 C above heating setpoint
    Requests outside these bounds are rejected and not applied.

    Args:
        heating_schedule_name: schedule name from list_zone_thermostats() (typically "HTGSETP_SCH")
        cooling_schedule_name: schedule name from list_zone_thermostats() (typically "CLGSETP_SCH")
        new_heating_setpoint_c: desired occupied-hours heating setpoint, Celsius
        new_cooling_setpoint_c: desired occupied-hours cooling setpoint, Celsius
    """
    # --- Hard safety bounds, enforced outside the LLM ---
    if not (16.0 <= new_heating_setpoint_c <= 24.0):
        return json.dumps({"error": "Rejected: heating setpoint must be between 16 and 24 C."})
    if not (22.0 <= new_cooling_setpoint_c <= 30.0):
        return json.dumps({"error": "Rejected: cooling setpoint must be between 22 and 30 C."})
    if new_cooling_setpoint_c - new_heating_setpoint_c < 2.0:
        return json.dumps({"error": "Rejected: cooling setpoint must be at least 2 C above heating setpoint."})

    idf = IDF(IDF_PATH, EPW_PATH)
    schedules = idf.idfobjects["SCHEDULE:COMPACT"]

    updated = []
    for sched in schedules:
        if sched.Name == heating_schedule_name:
            n = _set_occupied_setpoint_value(sched, new_heating_setpoint_c)
            updated.append({"schedule": sched.Name, "occupied_blocks_changed": n})
        elif sched.Name == cooling_schedule_name:
            n = _set_occupied_setpoint_value(sched, new_cooling_setpoint_c)
            updated.append({"schedule": sched.Name, "occupied_blocks_changed": n})

    if not updated:
        return json.dumps({"error": f"No matching Schedule:Compact objects found for "
                                     f"'{heating_schedule_name}' or '{cooling_schedule_name}'."})

    idf.saveas(IDF_PATH)
    return json.dumps({
        "status": "applied",
        "updated_schedules": updated,
        "new_heating_setpoint_c": new_heating_setpoint_c,
        "new_cooling_setpoint_c": new_cooling_setpoint_c,
        "note": "Call run_simulation() next to see the effect of this change."
    })


def _set_occupied_setpoint_value(sched_obj, new_value):
    """
    Schedule:Compact objects here encode a realistic setback strategy:
    e.g. HTGSETP_SCH drops to 15.6 C overnight and rises to 21.0 C only
    during occupied hours (06:00-22:00 on weekdays). Blindly overwriting
    every "Until:" value with one constant would delete that setback --
    the building would then run the new setpoint 24/7, likely *increasing*
    energy use instead of reducing it.

    Instead, this only replaces the OCCUPIED setpoint: within each "For:"
    block, the middle time period (bounded by two Until: markers, i.e. not
    the first or last block of the day) is treated as the occupied period
    and gets the new value. The first and last blocks (night setback) are
    left untouched. Design-day blocks (single Until: 24:00 for the whole
    day) are also left untouched since they aren't part of normal operation.
    """
    fieldnames = [fn for fn in sched_obj.fieldnames if fn.startswith("Field_")]

    # Group field indices into "For:" blocks
    block_start_indices = []
    for i, fn in enumerate(fieldnames):
        val = str(getattr(sched_obj, fn, "")).strip()
        if val.lower().startswith("for:"):
            block_start_indices.append(i)
    block_start_indices.append(len(fieldnames))  # sentinel for the last block's end

    changed_count = 0
    for b in range(len(block_start_indices) - 1):
        start = block_start_indices[b]
        end = block_start_indices[b + 1]
        block_fields = fieldnames[start:end]

        # Find all "Until:" markers within this block
        until_positions = [
            i for i, fn in enumerate(block_fields)
            if str(getattr(sched_obj, fn, "")).strip().lower().startswith("until:")
        ]

        # Only touch blocks with 3+ Until: markers (night -> occupied -> night
        # pattern). Blocks with exactly one Until: marker are single-value
        # days (design days, "AllOtherDays") -- leave those alone.
        if len(until_positions) >= 3:
            middle_until_idx = until_positions[len(until_positions) // 2 - 1] \
                if len(until_positions) % 2 == 0 else until_positions[len(until_positions) // 2]
            # value field is immediately after the Until: field
            value_field_idx = start + middle_until_idx + 1
            if value_field_idx < len(fieldnames):
                setattr(sched_obj, fieldnames[value_field_idx], new_value)
                changed_count += 1

    return changed_count


@mcp.tool()
def run_simulation() -> str:
    """
    Re-runs EnergyPlus with the current (possibly just-modified) IDF and
    weather file, then regenerates the monthly summary JSON. Call this
    after set_zone_setpoint to see the resulting energy/comfort numbers.
    This takes ~10-30 seconds.
    """
    idf = IDF(IDF_PATH, EPW_PATH)
    idf.run(output_directory=OUTPUT_DIR, readvars=True)

    csv_path = os.path.join(OUTPUT_DIR, "eplusout.csv")
    if not os.path.exists(csv_path):
        return json.dumps({"error": "Simulation did not produce eplusout.csv. "
                                     "Check eplusout.err in the output directory."})

    # Regenerate the summary using the same logic as summarize_baseline.py,
    # pointed at the new run's output.
    result = subprocess.run(
        [sys.executable, "summarize_baseline.py", "--csv", csv_path, "--output", SUMMARY_SCRIPT_OUTPUT],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return json.dumps({"error": "Summary generation failed", "details": result.stderr})

    return get_current_summary()


if __name__ == "__main__":
    mcp.run()
