from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Deque


@dataclass(slots=True)
class Task:
    task_id: int
    source: int
    arrival_slot: int
    size_bits: float
    cycles: float
    deadline_s: float
    destination: int = -1
    estimated_latency_s: float = 0.0
    energy_j: float = 0.0
    cloud_cost: float = 0.0


@dataclass(slots=True)
class Node:
    node_id: int
    layer: str
    gflops: float
    service_limit: int
    queue_capacity: int
    residual_energy_j: float
    minimum_energy_j: float
    queue: Deque[Task] = field(default_factory=deque)

    @property
    def queue_ratio(self) -> float:
        return len(self.queue) / self.queue_capacity


@dataclass(slots=True)
class Topology:
    nodes: list[Node]
    iot_ids: list[int]
    edge_ids: list[int]
    fog_ids: list[int]
    cloud_ids: list[int]
    candidates: dict[int, list[int]]
    primary_edge: dict[int, int]
    primary_fog: dict[int, int]

