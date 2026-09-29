from __future__ import annotations

import csv
import json
import math
import platform
import statistics
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .plotting import make_figures
from .simulator import Simulation


METRICS = [
    "average_queue", "queue_variance", "max_queue", "estimated_latency_ms",
    "energy_j_per_slot", "cloud_ratio", "throughput_per_slot",
    "deadline_violation_ratio", "drop_ratio",
]


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _aggregate(raw: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    keys = ("experiment", "policy", "scenario", "arrival_rate", "iot_devices")
    for row in raw:
        grouped.setdefault(tuple(row[key] for key in keys), []).append(row)
    output: list[dict[str, Any]] = []
    for group_key, rows in grouped.items():
        result = dict(zip(keys, group_key))
        result["replications"] = len(rows)
        for metric in METRICS:
            values = [float(row[metric]) for row in rows]
            mean = statistics.fmean(values)
            sd = statistics.stdev(values) if len(values) > 1 else 0.0
            result[f"{metric}_mean"] = mean
            result[f"{metric}_sd"] = sd
            result[f"{metric}_ci95"] = 1.96 * sd / math.sqrt(len(values))
        output.append(result)
    return sorted(output, key=lambda row: (row["experiment"], row["policy"], row["scenario"], float(row["arrival_rate"]), int(row["iot_devices"])))


def _seed(cfg: dict[str, Any], replication: int, policy_index: int, condition_index: int) -> int:
    # Policies within a condition share a seed (common random numbers), making
    # comparisons paired rather than confounded by different workloads.
    return int(cfg["seed_base"]) + replication * 100_003 + condition_index * 37


def run_experiments(cfg: dict[str, Any], output: Path, plans: set[str]) -> None:
    started = time.time()
    output.mkdir(parents=True, exist_ok=True)
    (output / "resolved_config.json").write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    raw: list[dict[str, Any]] = []
    timeseries_runs: list[tuple[str, int, list[dict[str, float]]]] = []

    conditions: list[tuple[str, str, float, int, list[str]]] = []
    base_devices = int(cfg["network"]["iot_devices"])
    if "baseline" in plans:
        for rate in cfg["arrival_rates"]:
            conditions.append(("baseline", "normal", float(rate), base_devices, list(cfg["policies"])))
    if "ablation" in plans:
        for rate in cfg["arrival_rates"]:
            conditions.append(("ablation", "bursty", float(rate), base_devices, list(cfg["ablations"])))
    if "scenario" in plans:
        for scenario in cfg["scenarios"]:
            conditions.append(("scenario", str(scenario), float(cfg["scenario_arrival_rate"]), base_devices, list(cfg["scenario_policies"])))
    if "stress" in plans:
        for device_count in cfg["stress_devices"]:
            conditions.append(("stress", "normal", float(cfg["stress_arrival_rate"]), int(device_count), list(cfg["stress_policies"])))
    if "timeseries" in plans:
        conditions.append(("timeseries", "bursty", float(cfg["time_series_rate"]), base_devices, list(dict.fromkeys(list(cfg["policies"]) + list(cfg["ablations"])))))

    total = sum(len(policies) * int(cfg["replications"]) for _, _, _, _, policies in conditions)
    completed = 0
    for condition_index, (experiment, scenario, rate, devices, policies) in enumerate(conditions):
        for policy_index, policy in enumerate(policies):
            for replication in range(int(cfg["replications"])):
                local_cfg = json.loads(json.dumps(cfg))
                local_cfg["network"]["iot_devices"] = devices
                seed = _seed(cfg, replication, policy_index, condition_index)
                summary, series = Simulation(local_cfg, policy, rate, scenario, seed).run()
                summary = {"experiment": experiment, "replication": replication, **summary}
                raw.append(summary)
                if experiment == "timeseries":
                    timeseries_runs.append((policy, replication, series))
                completed += 1
                print(f"[{completed}/{total}] {experiment} {scenario} {policy} rate={rate:g} devices={devices} seed={seed}", flush=True)

    aggregate = _aggregate(raw)
    _write_csv(output / "raw_runs.csv", raw)
    _write_csv(output / "aggregate.csv", aggregate)
    if timeseries_runs:
        keys = ["average_queue", "queue_variance", "max_queue", "estimated_latency_ms", "energy_j", "cloud_ratio", "throughput", "drop_ratio"]
        time_rows: list[dict[str, Any]] = []
        policies = sorted({entry[0] for entry in timeseries_runs})
        for policy in policies:
            selected = [series for name, _, series in timeseries_runs if name == policy]
            for slot in range(len(selected[0])):
                row: dict[str, Any] = {"policy": policy, "slot": slot, "replications": len(selected)}
                for key in keys:
                    values = [series[slot][key] for series in selected]
                    row[f"{key}_mean"] = statistics.fmean(values)
                    sd = statistics.stdev(values) if len(values) > 1 else 0.0
                    row[f"{key}_ci95"] = 1.96 * sd / math.sqrt(len(values))
                time_rows.append(row)
        _write_csv(output / "timeseries.csv", time_rows)
    make_figures([{key: str(value) for key, value in row.items()} for row in aggregate], output / "figures")
    metadata = {
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "elapsed_seconds": time.time() - started,
        "python": sys.version,
        "platform": platform.platform(),
        "plans": sorted(plans),
        "run_count": len(raw),
    }
    (output / "run_metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")

