"""
Summarizes the full 8760-row baseline_annual.csv into a compact monthly
summary -- small enough to hand to an LLM as context, instead of feeding
it 8760 raw hourly rows.

For each month, computes:
  - Total facility electricity (kWh)
  - Average outdoor air temperature (C)
  - Average zone temperature per zone (C)
  - Average PMV per zone
  - % of occupied hours where PMV was outside comfortable range (-0.5 to 0.5)

Usage:
    python summarize_baseline.py
    # writes baseline_monthly_summary.json and prints it
"""

import pandas as pd
import json
import re
import argparse

CSV_PATH = "baseline_annual.csv"
OUTPUT_JSON = "baseline_monthly_summary.json"

# EnergyPlus's default hourly Date/Time format looks like " 01/01  01:00:00"
# (leading space, two spaces before the time). We parse the month out of it
# directly with a regex rather than trusting pandas to parse the full string,
# since the day "24:00:00" hour EnergyPlus uses breaks normal datetime parsing.
def extract_month(date_str):
    match = re.search(r"(\d{2})/(\d{2})", date_str.strip())
    if match:
        return int(match.group(1))
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default=CSV_PATH, help="Path to the EnergyPlus hourly CSV output")
    parser.add_argument("--output", default=OUTPUT_JSON, help="Path to write the JSON summary to")
    args = parser.parse_args()

    df = pd.read_csv(args.csv)
    df["Month"] = df["Date/Time"].apply(extract_month)

    energy_col = "Electricity:Facility [J](Hourly)"
    outdoor_temp_col = "Environment:Site Outdoor Air Drybulb Temperature [C](Hourly)"

    zone_temp_cols = [c for c in df.columns if "Zone Mean Air Temperature" in c]
    pmv_cols = [c for c in df.columns if "PMV" in c]

    summary = {}

    for month in range(1, 13):
        month_df = df[df["Month"] == month]
        if month_df.empty:
            continue

        month_summary = {
            "total_electricity_kwh": round(month_df[energy_col].sum() / 3_600_000, 1)
                if energy_col in df.columns else None,
            "avg_outdoor_temp_c": round(month_df[outdoor_temp_col].mean(), 1)
                if outdoor_temp_col in df.columns else None,
            "zones": {}
        }

        for zone_temp_col in zone_temp_cols:
            zone_name = zone_temp_col.split(":")[0]
            zone_entry = {
                "avg_zone_temp_c": round(month_df[zone_temp_col].mean(), 1)
            }

            # match the PMV column for this zone, e.g. "CORE_ZN PEOPLE:..."
            matching_pmv = next((c for c in pmv_cols if c.startswith(zone_name + " ")), None)
            if matching_pmv:
                pmv_series = month_df[matching_pmv]
                zone_entry["avg_pmv"] = round(pmv_series.mean(), 2)
                # % of hours outside the comfortable PMV band (-0.5 to 0.5),
                # only counting hours where PMV was actually calculated
                # (occupied hours -- unoccupied hours often report 0 or NaN)
                occupied = pmv_series.dropna()
                occupied = occupied[occupied != 0]
                if len(occupied) > 0:
                    out_of_range = occupied[(occupied < -0.5) | (occupied > 0.5)]
                    zone_entry["pct_hours_outside_comfort_band"] = round(
                        100 * len(out_of_range) / len(occupied), 1
                    )
                else:
                    zone_entry["pct_hours_outside_comfort_band"] = None

            month_summary["zones"][zone_name] = zone_entry

        summary[f"month_{month:02d}"] = month_summary

    # Also compute a single annual total for quick reference
    annual_total_kwh = round(df[energy_col].sum() / 3_600_000, 1) if energy_col in df.columns else None
    summary["annual_total_kwh"] = annual_total_kwh

    with open(args.output, "w") as f:
        json.dump(summary, f, indent=2)

    print(f"Wrote monthly summary to {args.output}")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
