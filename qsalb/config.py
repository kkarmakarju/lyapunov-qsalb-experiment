from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


def _merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key == "extends":
            continue
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def load_config(path: str | Path) -> dict[str, Any]:
    path = Path(path).resolve()
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    parent = data.get("extends")
    if parent:
        base = load_config(path.parent / parent)
        data = _merge(base, data)
    validate_config(data)
    return data


def validate_config(cfg: dict[str, Any]) -> None:
    if cfg["warmup_slots"] >= cfg["slots"]:
        raise ValueError("warmup_slots must be smaller than slots")
    if cfg["replications"] < 1:
        raise ValueError("replications must be positive")
    if any(rate < 0 for rate in cfg["arrival_rates"]):
        raise ValueError("arrival rates must be non-negative")
    if int(cfg["arrival_cap_per_device"]) < 1:
        raise ValueError("arrival_cap_per_device must be positive")
    for key in ("iot_devices", "edge_nodes", "fog_nodes", "cloud_nodes"):
        if cfg["network"][key] < 1:
            raise ValueError(f"network.{key} must be positive")

