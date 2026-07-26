"""
Baseline runner: loads a sample EnergyPlus IDF, fixes it to run a full year
against the Mumbai .epw (instead of just the built-in Chicago design days),
adds PMV thermal comfort output, runs it, and prints a summary including
energy in kWh.

Usage:
    source myenv/bin/activate
    python run_mumbai_baseline_fixed.py
"""

from eppy.modeleditor import IDF
import pandas as pd
import os

# ---- EDIT THESE THREE PATHS FOR YOUR MACHINE ----
IDD_PATH = "/Applications/EnergyPlus-26-1-0/Energy+.idd"
IDF_PATH = "/Applications/EnergyPlus-26-1-0/ExampleFiles/RefBldgSmallOfficeNew2004_Chicago.idf"
EPW_PATH = "/Users/apple/Desktop/Honeywell2/IND_Mumbai.430030_ISHRAE.epw"
OUTPUT_DIR = "./output_mumbai_baseline"
# --------------------------------------------------

IDF.setiddname(IDD_PATH)
idf = IDF(IDF_PATH, EPW_PATH)

# 1. Fix RunPeriod(s) to run a full calendar year instead of just relying on
#    whatever design days are baked in. There is usually one RunPeriod object.
runperiods = idf.idfobjects["RUNPERIOD"]
print(f"Found {len(runperiods)} RunPeriod object(s).")

for rp in runperiods:
    rp.Begin_Month = 1
    rp.Begin_Day_of_Month = 1
    rp.End_Month = 12
    rp.End_Day_of_Month = 31
    rp.Use_Weather_File_Holidays_and_Special_Days = "Yes"
    rp.Use_Weather_File_Daylight_Saving_Period = "Yes"
    rp.Apply_Weekend_Holiday_Rule = "No"
    rp.Use_Weather_File_Rain_Indicators = "Yes"
    rp.Use_Weather_File_Snow_Indicators = "Yes"
    print("Updated RunPeriod to Jan 1 - Dec 31.")

# 1b. Critical fix: SimulationControl decides whether EnergyPlus actually runs
#     the weather-file RunPeriod above, or just the SizingPeriod:DesignDay
#     objects and stops.
sim_control = idf.idfobjects["SIMULATIONCONTROL"][0]
sim_control.Do_Zone_Sizing_Calculation = "Yes"
sim_control.Do_System_Sizing_Calculation = "Yes"
sim_control.Do_Plant_Sizing_Calculation = "Yes"
sim_control.Run_Simulation_for_Sizing_Periods = "No"
sim_control.Run_Simulation_for_Weather_File_Run_Periods = "Yes"
print("Updated SimulationControl to run the full weather-file year, not just sizing days.")

# 1c. Request PMV thermal comfort output — not included by default.
pmv_output = idf.newidfobject("OUTPUT:VARIABLE")
pmv_output.Key_Value = "*"
pmv_output.Variable_Name = "Zone Thermal Comfort Fanger Model PMV"
pmv_output.Reporting_Frequency = "Hourly"
print("Added PMV output variable request.")

# 1d. Make sure People objects actually calculate the Fanger PMV model —
#     the Output:Variable above does nothing if this isn't set.
people_objs = idf.idfobjects["PEOPLE"]
for p in people_objs:
    p.Thermal_Comfort_Model_1_Type = "Fanger"
print(f"Enabled Fanger comfort model on {len(people_objs)} People object(s).")

# 2. The SizingPeriod:DesignDay objects are still Chicago-specific (extreme
#    heating/cooling conditions used only for equipment sizing, not the main
#    simulation). Known simplification, revisit later if you want tighter sizing.
sizing_days = idf.idfobjects["SIZINGPERIOD:DESIGNDAY"]
print(f"Note: {len(sizing_days)} SizingPeriod:DesignDay object(s) still reference "
      f"Chicago design conditions. Leaving as-is for now (oversized HVAC sizing, "
      f"safe but not optimal).")

# 3. Save a copy (don't overwrite the original example file)
edited_idf_path = os.path.join(os.getcwd(), "RefBldgSmallOffice_Mumbai_baseline.idf")
idf.saveas(edited_idf_path)
print(f"Saved edited IDF to: {edited_idf_path}")

# 4. Run it
os.makedirs(OUTPUT_DIR, exist_ok=True)
idf.run(output_directory=OUTPUT_DIR, readvars=True)
print("EnergyPlus run complete.")

# 5. Load the output and report a summary — this is where df is created,
#    so any column math must happen AFTER this point.
csv_path = os.path.join(OUTPUT_DIR, "eplusout.csv")
if os.path.exists(csv_path):
    df = pd.read_csv(csv_path)
    print(f"\nOutput CSV shape: {df.shape}")
    print(f"Number of timesteps: {len(df)}  (a full year hourly run should have ~8760 rows)")

    # --- Energy: convert Joules -> kWh ---
    energy_col = "Electricity:Facility [J](Hourly)"
    if energy_col in df.columns:
        df["Electricity_Facility_kWh"] = df[energy_col] / 3_600_000
        total_kwh = df["Electricity_Facility_kWh"].sum()
        print(f"\nTotal annual facility electricity: {total_kwh:,.1f} kWh")
    else:
        print(f"\nWARNING: expected column '{energy_col}' not found.")

    # --- PMV: check it actually got produced ---
    pmv_cols = [c for c in df.columns if "PMV" in c]
    if pmv_cols:
        print(f"\nFound {len(pmv_cols)} PMV column(s):")
        for c in pmv_cols:
            print(f"  - {c}")
    else:
        print("\nWARNING: no PMV columns found in output. Check that the "
              "People object(s) actually have occupancy schedules driving them, "
              "and that Fanger was applied (see step 1d above).")

    print("\nAll column names:")
    for col in df.columns:
        print(f"  - {col}")

    # Save a clean copy as your official baseline
    baseline_path = "baseline_annual.csv"
    df.to_csv(baseline_path, index=False)
    print(f"\nSaved baseline copy to: {baseline_path}")
else:
    print("WARNING: eplusout.csv not found -- check eplusout.err in the output folder.")

err_path = os.path.join(OUTPUT_DIR, "eplusout.err")
if os.path.exists(err_path):
    with open(err_path) as f:
        err_text = f.read()
    severe = err_text.count("** Severe **")
    fatal = err_text.count("** Fatal **")
    print(f"\neplusout.err summary: {severe} Severe, {fatal} Fatal")
    if fatal > 0:
        print("FATAL ERRORS FOUND -- open eplusout.err and review before continuing.")