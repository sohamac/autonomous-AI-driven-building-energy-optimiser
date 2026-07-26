"""
Standalone sanity check -- run this BEFORE testing the MCP server or LLM.
Confirms the IDF actually has the objects the MCP tools expect, and prints
their real structure so we can fix any mismatched assumptions early.

Usage:
    python check_idf_structure.py
"""

from eppy.modeleditor import IDF

IDD_PATH = "/Applications/EnergyPlus-26-1-0/Energy+.idd"
IDF_PATH = "/Users/apple/Desktop/Honeywell2/RefBldgSmallOffice_Mumbai_baseline.idf"
EPW_PATH = "/Users/apple/Desktop/Honeywell2/IND_Mumbai.430030_ISHRAE.epw"

IDF.setiddname(IDD_PATH)
idf = IDF(IDF_PATH, EPW_PATH)

print("=" * 60)
print("THERMOSTATSETPOINT:DUALSETPOINT objects")
print("=" * 60)
stats = idf.idfobjects["THERMOSTATSETPOINT:DUALSETPOINT"]
print(f"Found {len(stats)} object(s)\n")
for s in stats:
    print(f"Name: {s.Name}")
    print(f"  Heating schedule: {s.Heating_Setpoint_Temperature_Schedule_Name}")
    print(f"  Cooling schedule: {s.Cooling_Setpoint_Temperature_Schedule_Name}")
    print()

print("=" * 60)
print("SCHEDULE:COMPACT objects referenced by those thermostats")
print("=" * 60)
schedule_names_of_interest = set()
for s in stats:
    schedule_names_of_interest.add(s.Heating_Setpoint_Temperature_Schedule_Name)
    schedule_names_of_interest.add(s.Cooling_Setpoint_Temperature_Schedule_Name)

all_schedules = idf.idfobjects["SCHEDULE:COMPACT"]
print(f"Total Schedule:Compact objects in file: {len(all_schedules)}\n")

for sched in all_schedules:
    if sched.Name in schedule_names_of_interest:
        print(f"--- {sched.Name} ---")
        print(sched)
        print()

print("=" * 60)
print("ZONECONTROL:THERMOSTAT objects (links zones to the setpoints above)")
print("=" * 60)
zone_controls = idf.idfobjects["ZONECONTROL:THERMOSTAT"]
print(f"Found {len(zone_controls)} object(s)\n")
for zc in zone_controls:
    print(f"Zone: {zc.Zone_or_ZoneList_Name}")
    print(f"  Control type schedule: {zc.Control_Type_Schedule_Name}")
    print(f"  Control 1 object type: {zc.Control_1_Object_Type}")
    print(f"  Control 1 name: {zc.Control_1_Name}")
    print()
