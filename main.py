#!/usr/bin/env python3
"""
Eco-Loop Building Agents — Main Entry Point

This is a thin orchestration wrapper around the pipeline's real, individually
tested scripts (run_mumbai_baseline.py, run_hillclimb_loop.py,
run_agent_decision.py). It does not reimplement any simulation or agent
logic -- it just runs the existing pipeline in order with clearer terminal
output, and prints a final comparison summary from the real results
(hillclimb_log.json), which is itself generated from actual EnergyPlus runs.

Usage:
    python main.py run          # baseline -> sweep -> LLM recommendation
    python main.py baseline     # baseline simulation only
    python main.py sweep        # deterministic cooling setpoint sweep only
    python main.py decide       # LLM reasons over an existing sweep result
"""
import argparse
import json
import os
import subprocess
import sys
import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional -- GROQ_API_KEY can also be exported directly

CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

REQUIRED_FILES = {
    "run_mumbai_baseline.py": "baseline simulation script",
    "run_hillclimb_loop.py": "deterministic setpoint sweep script",
    "run_agent_decision.py": "LLM decision script",
}


def print_banner():
    print(f"""{CYAN}{BOLD}
╔══════════════════════════════════════════════════════════╗
║          🌿  ECO-LOOP BUILDING AGENTS  🌿                  ║
║   EnergyPlus + Open-Source LLM Closed-Loop Optimization    ║
╚══════════════════════════════════════════════════════════╝{RESET}
""")


def check_prereqs():
    missing = [f for f in REQUIRED_FILES if not os.path.exists(f)]
    if missing:
        print(f"{RED}ERROR: missing required file(s): {', '.join(missing)}{RESET}")
        print("  Run this from the project root, alongside the pipeline scripts.")
        sys.exit(1)


def run_step(label: str, script: str, extra_args=None):
    """Runs a real pipeline script as a subprocess and streams its output live."""
    print(f"\n{BOLD}━━━ {label} ━━━{RESET}")
    cmd = [sys.executable, script] + (extra_args or [])
    print(f"  {DIM}$ {' '.join(cmd)}{RESET}\n")

    start = time.time()
    result = subprocess.run(cmd)
    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"\n  {RED}✗ {label} failed (exit code {result.returncode}){RESET}")
        sys.exit(result.returncode)

    print(f"\n  {GREEN}✓ {label} complete{RESET} ({elapsed:.1f}s)")


def print_comparison():
    """Reads the real hillclimb_log.json (produced by actual EnergyPlus runs)
    and prints a formatted comparison table -- no numbers are invented here."""
    if not os.path.exists("hillclimb_log.json"):
        print(f"\n{YELLOW}No hillclimb_log.json found yet -- run the sweep step first.{RESET}")
        return

    with open("hillclimb_log.json") as f:
        data = json.load(f)

    baseline_kwh = data["baseline_kwh"]
    baseline_violations = data["baseline_violations"]
    rec = data["recommended"]
    savings_pct = rec["kwh_savings_pct"]
    color = GREEN if savings_pct > 0 else RED

    print(f"\n{BOLD}{'═' * 58}{RESET}")
    print(f"{BOLD}               📊 RESULTS COMPARISON{RESET}")
    print(f"{BOLD}{'═' * 58}{RESET}")
    rows = [
        ("Baseline Annual Energy", f"{baseline_kwh:,.1f} kWh"),
        ("Recommended Setpoint", f"{rec['cooling_c']}°C cool / {rec['heating_c']}°C heat"),
        ("Optimized Annual Energy", f"{rec['annual_kwh']:,.1f} kWh"),
        ("Energy Savings", f"{color}{savings_pct:+.1f}%{RESET}"),
        ("Baseline Comfort Violations", f"{baseline_violations}"),
        ("Optimized Comfort Violations", f"{rec['num_violations']} ({rec['violations_change']:+d})"),
    ]
    for label, value in rows:
        print(f"  {label:<32} {BOLD}{value}{RESET}")
    print(f"{BOLD}{'═' * 58}{RESET}")

    if os.path.exists("agent_final_recommendation.txt"):
        with open("agent_final_recommendation.txt") as f:
            print(f"\n{BOLD}🤖 Agent's reasoning:{RESET}\n  {f.read().strip()}\n")


def cmd_run(args):
    check_prereqs()
    run_step("Phase 1: Baseline Simulation", "run_mumbai_baseline.py")
    run_step("Phase 2: Summarize Baseline", "summarize_baseline.py")
    run_step("Phase 3: Deterministic Setpoint Sweep", "run_hillclimb_loop.py")

    if os.environ.get("GROQ_API_KEY"):
        run_step("Phase 4: LLM Reasoning Over Sweep", "run_agent_decision.py")
    else:
        print(f"\n{YELLOW}Skipping LLM decision step -- GROQ_API_KEY not set.{RESET}")
        print(f"  Get a free key at: {CYAN}https://console.groq.com{RESET}")
        print(f"  Then: {YELLOW}export GROQ_API_KEY='your-key-here'{RESET} (or copy .env.example to .env)")

    print_comparison()
    print(f"\n{BOLD}🎉 Pipeline complete!{RESET} Open {CYAN}dashboard.html{RESET} in a browser to view the full report.\n")


def cmd_baseline(args):
    check_prereqs()
    run_step("Baseline Simulation", "run_mumbai_baseline.py")
    run_step("Summarize Baseline", "summarize_baseline.py")


def cmd_sweep(args):
    check_prereqs()
    run_step("Deterministic Setpoint Sweep", "run_hillclimb_loop.py")
    print_comparison()


def cmd_decide(args):
    if not os.environ.get("GROQ_API_KEY"):
        print(f"{RED}ERROR: GROQ_API_KEY not set.{RESET}")
        print(f"  Get a free key at: {CYAN}https://console.groq.com{RESET}")
        sys.exit(1)
    run_step("LLM Reasoning Over Sweep", "run_agent_decision.py")


def main():
    parser = argparse.ArgumentParser(
        description="Eco-Loop Building Agents -- CLI orchestrator for the real EnergyPlus + LLM pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""{BOLD}Examples:{RESET}
  python main.py run          Full pipeline: baseline -> sweep -> LLM recommendation
  python main.py baseline     Baseline simulation only
  python main.py sweep        Deterministic setpoint sweep only (requires baseline)
  python main.py decide       LLM reasons over an existing sweep result
""",
    )
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("run", help="Run the full pipeline")
    subparsers.add_parser("baseline", help="Run baseline simulation only")
    subparsers.add_parser("sweep", help="Run the deterministic setpoint sweep only")
    subparsers.add_parser("decide", help="Run the LLM decision step only")

    args = parser.parse_args()
    print_banner()

    commands = {"run": cmd_run, "baseline": cmd_baseline, "sweep": cmd_sweep, "decide": cmd_decide}
    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()
        print(f"\n{YELLOW}Hint: start with '{BOLD}python main.py run{RESET}{YELLOW}'{RESET}\n")


if __name__ == "__main__":
    main()
