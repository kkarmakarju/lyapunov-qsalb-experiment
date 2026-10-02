from __future__ import annotations

import math
import random
import statistics
from dataclasses import asdict
from typing import Any

from .model import Node, Task, Topology


QSALB_VARIANTS = {
    "QSALB-Full",
    "QSALB-NoPred",
    "QSALB-NoEnergy",
    "QSALB-NoQueue",
}


def _uniform(rng: random.Random, bounds: list[float]) -> float:
    return rng.uniform(float(bounds[0]), float(bounds[1]))


def _poisson(rng: random.Random, rate: float) -> int:
    if rate <= 0:
        return 0
    if rate > 30:
        value = int(round(rng.gauss(rate, math.sqrt(rate))))
        return max(0, value)
    limit = math.exp(-rate)
    product = 1.0
    count = 0
    while product > limit:
        count += 1
        product *= rng.random()
    return count - 1


def build_topology(cfg: dict[str, Any], rng: random.Random) -> Topology:
    net = cfg["network"]
    energy = cfg["energy"]
    reference_cycles = float(net["reference_cycles_per_task"])
    slot_seconds = float(cfg["slot_seconds"])
    nodes: list[Node] = []
    layer_ids: dict[str, list[int]] = {key: [] for key in ("iot", "edge", "fog", "cloud")}

    counts = {
        "iot": int(net["iot_devices"]),
        "edge": int(net["edge_nodes"]),
        "fog": int(net["fog_nodes"]),
        "cloud": int(net["cloud_nodes"]),
    }
    gflop_keys = {
        "iot": "iot_gflops",
        "edge": "edge_gflops",
        "fog": "fog_gflops",
        "cloud": "cloud_gflops",
    }
    for layer in ("iot", "edge", "fog", "cloud"):
        for _ in range(counts[layer]):
            gflops = _uniform(rng, net[gflop_keys[layer]])
            service = max(1, int(gflops * 1e9 * slot_seconds / reference_cycles))
            if layer in ("iot", "edge"):
                mah = _uniform(rng, energy["battery_mah"])
                joules = mah / 1000.0 * float(energy["battery_voltage"]) * 3600.0
                minimum = joules * float(energy["minimum_fraction"])
            else:
                joules = float("inf")
                minimum = 0.0
            node_id = len(nodes)
            nodes.append(Node(
                node_id=node_id,
                layer=layer,
                gflops=gflops,
                service_limit=service,
                queue_capacity=int(net["queue_capacity"][layer]),
                residual_energy_j=joules,
                minimum_energy_j=minimum,
            ))
            layer_ids[layer].append(node_id)

    primary_edge: dict[int, int] = {}
    primary_fog: dict[int, int] = {}
    candidates: dict[int, list[int]] = {}
    horizontal = int(net["horizontal_edge_candidates"])
    edges = layer_ids["edge"]
    fogs = layer_ids["fog"]
    clouds = layer_ids["cloud"]
    for position, iot_id in enumerate(layer_ids["iot"]):
        edge_position = position % len(edges)
        edge_id = edges[edge_position]
        fog_id = fogs[edge_position % len(fogs)]
        primary_edge[iot_id] = edge_id
        primary_fog[iot_id] = fog_id
        nearby = [edges[(edge_position + offset) % len(edges)] for offset in range(horizontal + 1)]
        candidates[iot_id] = [iot_id] + list(dict.fromkeys(nearby + [fog_id] + clouds))
    return Topology(
        nodes=nodes,
        iot_ids=layer_ids["iot"],
        edge_ids=edges,
        fog_ids=fogs,
        cloud_ids=clouds,
        candidates=candidates,
        primary_edge=primary_edge,
        primary_fog=primary_fog,
    )


class Simulation:
    def __init__(self, cfg: dict[str, Any], policy: str, arrival_rate: float,
                 scenario: str, seed: int):
        if policy not in QSALB_VARIANTS | {"LEO", "GMQ", "LFO", "EAO", "CFOP"}:
            raise ValueError(f"Unknown policy: {policy}")
        self.cfg = cfg
        self.policy = policy
        self.arrival_rate = float(arrival_rate)
        self.scenario = scenario
        self.seed = int(seed)
        self.rng = random.Random(seed)
        self.topology = build_topology(cfg, self.rng)
        self.task_counter = 0
        count = len(self.topology.iot_ids)
        self.last_arrivals = [self.arrival_rate] * count
        self.arrival_ema = [self.arrival_rate] * count
        self.mmpp_high = [False] * count
        self.metrics: list[dict[str, float]] = []

    def _scenario_rate(self, source_position: int, slot: int) -> float:
        rate = self.arrival_rate
        workload = self.cfg["workload"]
        if self.scenario == "bursty":
            high = self.mmpp_high[source_position]
            if high and self.rng.random() < float(workload["mmpp_p_high_low"]):
                high = False
            elif not high and self.rng.random() < float(workload["mmpp_p_low_high"]):
                high = True
            self.mmpp_high[source_position] = high
            factor = workload["mmpp_high_factor"] if high else workload["mmpp_low_factor"]
            rate *= float(factor)
        elif self.scenario == "trace":
            period = int(workload["trace_burst_period"])
            width = int(workload["trace_burst_width"])
            phase = (slot + source_position % max(1, width)) % period
            if phase < width:
                rate *= float(workload["trace_burst_factor"])
            else:
                rate *= 0.72 + 0.20 * math.sin(2.0 * math.pi * phase / period)
        return max(0.0, rate)

    def _new_task(self, source: int, slot: int) -> Task:
        task_cfg = self.cfg["task"]
        task = Task(
            task_id=self.task_counter,
            source=source,
            arrival_slot=slot,
            size_bits=_uniform(self.rng, task_cfg["size_kb"]) * 1024.0 * 8.0,
            cycles=_uniform(self.rng, task_cfg["cycles"]),
            deadline_s=_uniform(self.rng, task_cfg["deadline_ms"]) / 1000.0,
        )
        self.task_counter += 1
        return task

    def _link(self, source: int, destination: int, slot: int) -> tuple[float, float]:
        if source == destination:
            return float("inf"), 0.0
        links = self.cfg["links"]
        layer = self.topology.nodes[destination].layer
        if layer == "edge":
            bandwidth = _uniform(self.rng, links["iot_edge_mbps"])
            prop_ms = _uniform(self.rng, links["iot_edge_prop_ms"])
        elif layer == "fog":
            bandwidth = _uniform(self.rng, links["edge_fog_mbps"])
            prop_ms = _uniform(self.rng, links["edge_fog_prop_ms"])
        else:
            bandwidth = _uniform(self.rng, links["fog_cloud_mbps"])
            prop_ms = _uniform(self.rng, links["cloud_prop_ms"])
        if self.scenario == "mobility":
            phase = 0.11 * slot + 0.37 * source
            floor = float(links["mobility_bandwidth_floor"])
            multiplier = floor + (1.0 - floor) * (0.5 + 0.5 * math.sin(phase))
            bandwidth *= multiplier
            prop_ms += (1.0 - multiplier) * float(links["mobility_extra_prop_ms"])
        return bandwidth * 1e6, prop_ms / 1000.0

    def _task_cost(self, task: Task, destination: int, slot: int,
                   source_pressure: float, provisional: dict[int, int]) -> dict[str, float]:
        node = self.topology.nodes[destination]
        bandwidth, prop_s = self._link(task.source, destination, slot)
        comm_s = 0.0 if math.isinf(bandwidth) else task.size_bits / bandwidth + prop_s
        q = len(node.queue) + provisional.get(destination, 0)
        wait_s = q / (node.service_limit + float(self.cfg["qsalb"]["epsilon_q"])) * float(self.cfg["slot_seconds"])
        proc_s = task.cycles / (node.gflops * 1e9)
        latency_s = comm_s + wait_s + proc_s
        energy_cfg = self.cfg["energy"]
        if destination == task.source:
            energy_j = task.cycles * float(energy_cfg["processing_j_per_cycle"]["iot"])
        else:
            energy_j = task.size_bits * float(energy_cfg["transmit_j_per_bit"][node.layer])
        cloud_cost = float(self.cfg["qsalb"]["cloud_cost"]) if node.layer == "cloud" else 0.0
        queue_delta = source_pressure - q
        qcfg = self.cfg["qsalb"]
        alpha = float(qcfg["alpha"])
        beta = 0.0 if self.policy == "QSALB-NoEnergy" else float(qcfg["beta"])
        gamma = float(qcfg["gamma"])
        queue_term = 0.0 if self.policy == "QSALB-NoQueue" else -queue_delta
        penalty = (
            alpha * latency_s * 1000.0 / float(qcfg["latency_scale_ms"])
            + beta * energy_j / float(qcfg["energy_scale_j"])
            + gamma * cloud_cost
        )
        score = queue_term + float(qcfg["V"]) * penalty
        # The manuscript charges both local-compute and radio energy to the
        # originating battery, not to the selected execution node.
        source_node = self.topology.nodes[task.source]
        enough_energy = source_node.residual_energy_j - energy_j >= source_node.minimum_energy_j
        feasible = (
            q < node.queue_capacity
            and comm_s * 1000.0 <= float(self.cfg["links"]["max_comm_delay_ms"])
            and latency_s <= task.deadline_s
            and enough_energy
        )
        admissible = q < node.queue_capacity and enough_energy
        return {
            "score": score,
            "latency_s": latency_s,
            "energy_j": energy_j,
            "cloud_cost": cloud_cost,
            "feasible": float(feasible),
            "admissible": float(admissible),
            "queue": float(q),
        }

    def _choose(self, task: Task, slot: int, source_pressure: float,
                provisional: dict[int, int]) -> tuple[int | None, dict[str, float] | None, bool]:
        # LEO is strictly local by definition; a full/depleted local node drops
        # the task instead of silently turning LEO into an offloading policy.
        candidates = [task.source] if self.policy == "LEO" else self.topology.candidates[task.source]
        evaluated = {dest: self._task_cost(task, dest, slot, source_pressure, provisional) for dest in candidates}
        feasible = [dest for dest in candidates if evaluated[dest]["feasible"]]
        pool = feasible or [dest for dest in candidates if evaluated[dest]["admissible"]]
        if not pool:
            return None, None, False
        missed_deadline = not bool(feasible)
        if self.policy == "LEO":
            chosen = task.source if task.source in pool else min(pool, key=lambda d: evaluated[d]["latency_s"])
        elif self.policy == "GMQ":
            chosen = min(pool, key=lambda d: (evaluated[d]["queue"] / self.topology.nodes[d].queue_capacity, evaluated[d]["latency_s"], d))
        elif self.policy == "LFO":
            chosen = min(pool, key=lambda d: (evaluated[d]["latency_s"], d))
        elif self.policy == "EAO":
            chosen = min(pool, key=lambda d: (evaluated[d]["energy_j"], evaluated[d]["latency_s"], d))
        elif self.policy == "CFOP":
            edge = self.topology.primary_edge[task.source]
            fog = self.topology.primary_fog[task.source]
            cloud = self.topology.cloud_ids[0]
            thresholds = self.cfg["cfop"]
            order = [edge, fog, cloud, task.source]
            chosen = None
            for dest in order:
                if dest not in pool:
                    continue
                ratio = (len(self.topology.nodes[dest].queue) + provisional.get(dest, 0)) / self.topology.nodes[dest].queue_capacity
                if self.topology.nodes[dest].layer == "edge" and ratio >= float(thresholds["edge_threshold"]):
                    continue
                if self.topology.nodes[dest].layer == "fog" and ratio >= float(thresholds["fog_threshold"]):
                    continue
                chosen = dest
                break
            if chosen is None:
                chosen = min(pool, key=lambda d: evaluated[d]["latency_s"])
        else:
            chosen = min(pool, key=lambda d: (evaluated[d]["score"], d))
        return chosen, evaluated[chosen], missed_deadline

    def _service_limit(self, node: Node, slot: int) -> int:
        limit = node.service_limit
        if self.scenario == "fog_congestion" and node.node_id == self.topology.fog_ids[0]:
            settings = self.cfg["scenario"]
            start = int(float(settings["fog_congestion_start_fraction"]) * int(self.cfg["slots"]))
            end = int(float(settings["fog_congestion_end_fraction"]) * int(self.cfg["slots"]))
            if start <= slot < end:
                limit = max(1, int(limit * float(settings["fog_congestion_service_factor"])))
        return limit

    def run(self) -> tuple[dict[str, float | int | str], list[dict[str, float]]]:
        warmup = int(self.cfg["warmup_slots"])
        totals = {
            "arrivals": 0.0, "admitted": 0.0, "dropped": 0.0, "completed": 0.0,
            "deadline_violations": 0.0, "latency_s": 0.0, "energy_j": 0.0,
            "cloud": 0.0, "queue_sum": 0.0, "queue_var": 0.0, "max_queue": 0.0,
        }
        measured_slots = 0
        for slot in range(int(self.cfg["slots"])):
            provisional: dict[int, int] = {}
            slot_values = {key: 0.0 for key in ("arrivals", "admitted", "dropped", "completed", "deadline_violations", "latency_s", "energy_j", "cloud")}
            batches: list[tuple[int, int, int]] = []
            for position, source in enumerate(self.topology.iot_ids):
                count = min(
                    int(self.cfg["arrival_cap_per_device"]),
                    _poisson(self.rng, self._scenario_rate(position, slot)),
                )
                batches.append((position, source, count))
                slot_values["arrivals"] += count

            for position, source, count in batches:
                ema_weight = float(self.cfg["qsalb"]["prediction_ema"])
                forecast = 0.65 * self.last_arrivals[position] + 0.35 * self.arrival_ema[position]
                prediction = 0.0 if self.policy == "QSALB-NoPred" else float(self.cfg["qsalb"]["prediction_lambda"]) * forecast
                source_pressure = len(self.topology.nodes[source].queue) + count + prediction
                for _ in range(count):
                    task = self._new_task(source, slot)
                    destination, cost, missed = self._choose(task, slot, source_pressure, provisional)
                    source_pressure = max(0.0, source_pressure - 1.0)
                    if destination is None or cost is None:
                        slot_values["dropped"] += 1
                        continue
                    task.destination = destination
                    task.estimated_latency_s = cost["latency_s"]
                    task.energy_j = cost["energy_j"]
                    task.cloud_cost = cost["cloud_cost"]
                    self.topology.nodes[destination].queue.append(task)
                    dest_node = self.topology.nodes[destination]
                    # Enqueuing immediately already implements Algorithm 1's
                    # provisional backlog increment for subsequent decisions.
                    source_node = self.topology.nodes[source]
                    source_node.residual_energy_j -= task.energy_j
                    slot_values["admitted"] += 1
                    slot_values["deadline_violations"] += int(missed)
                    slot_values["latency_s"] += task.estimated_latency_s
                    slot_values["energy_j"] += task.energy_j
                    slot_values["cloud"] += int(dest_node.layer == "cloud")
                self.arrival_ema[position] = ema_weight * count + (1.0 - ema_weight) * self.arrival_ema[position]
                self.last_arrivals[position] = count

            for node in self.topology.nodes:
                limit = self._service_limit(node, slot)
                if not bool(self.cfg["arrivals_eligible_same_slot"]):
                    eligible = sum(1 for task in node.queue if task.arrival_slot < slot)
                    limit = min(limit, eligible)
                served = min(limit, len(node.queue))
                for _ in range(served):
                    node.queue.popleft()
                slot_values["completed"] += served

            queues = [len(node.queue) for node in self.topology.nodes]
            avg_queue = statistics.fmean(queues) if queues else 0.0
            queue_var = statistics.pvariance(queues) if len(queues) > 1 else 0.0
            slot_record = {
                "slot": float(slot),
                "average_queue": avg_queue,
                "queue_variance": queue_var,
                "max_queue": float(max(queues, default=0)),
                "estimated_latency_ms": 1000.0 * slot_values["latency_s"] / max(1.0, slot_values["admitted"]),
                "energy_j": slot_values["energy_j"],
                "cloud_ratio": slot_values["cloud"] / max(1.0, slot_values["admitted"]),
                "throughput": slot_values["completed"],
                "drop_ratio": slot_values["dropped"] / max(1.0, slot_values["arrivals"]),
            }
            self.metrics.append(slot_record)
            if slot >= warmup:
                measured_slots += 1
                for key in ("arrivals", "admitted", "dropped", "completed", "deadline_violations", "latency_s", "energy_j", "cloud"):
                    totals[key] += slot_values[key]
                totals["queue_sum"] += avg_queue
                totals["queue_var"] += queue_var
                totals["max_queue"] = max(totals["max_queue"], max(queues, default=0))

        summary: dict[str, float | int | str] = {
            "policy": self.policy,
            "scenario": self.scenario,
            "arrival_rate": self.arrival_rate,
            "iot_devices": len(self.topology.iot_ids),
            "seed": self.seed,
            "measured_slots": measured_slots,
            "average_queue": totals["queue_sum"] / max(1, measured_slots),
            "queue_variance": totals["queue_var"] / max(1, measured_slots),
            "max_queue": totals["max_queue"],
            "estimated_latency_ms": 1000.0 * totals["latency_s"] / max(1.0, totals["admitted"]),
            "energy_j_per_slot": totals["energy_j"] / max(1, measured_slots),
            "cloud_ratio": totals["cloud"] / max(1.0, totals["admitted"]),
            "throughput_per_slot": totals["completed"] / max(1, measured_slots),
            "deadline_violation_ratio": totals["deadline_violations"] / max(1.0, totals["admitted"]),
            "drop_ratio": totals["dropped"] / max(1.0, totals["arrivals"]),
            "arrivals": totals["arrivals"],
            "admitted": totals["admitted"],
            "completed": totals["completed"],
        }
        return summary, self.metrics

