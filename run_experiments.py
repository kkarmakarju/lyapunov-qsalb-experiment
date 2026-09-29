from __future__ import annotations

import argparse
from pathlib import Path

from qsalb.config import load_config
from qsalb.experiment import run_experiments


def main() -> None:
    parser = argparse.ArgumentParser(description="Run reconstructed QSALB experiments")
    parser.add_argument("--config", default="config/manuscript.json", help="JSON configuration file")
    parser.add_argument("--output", default="results/manuscript", help="Output directory")
    parser.add_argument("--plan", default="baseline,ablation,scenario,stress,timeseries",
                        help="Comma-separated: baseline,ablation,scenario,stress,timeseries")
    args = parser.parse_args()
    allowed = {"baseline", "ablation", "scenario", "stress", "timeseries"}
    plans = {part.strip() for part in args.plan.split(",") if part.strip()}
    unknown = plans - allowed
    if unknown:
        parser.error(f"unknown plans: {', '.join(sorted(unknown))}")
    run_experiments(load_config(args.config), Path(args.output).resolve(), plans)


if __name__ == "__main__":
    main()

