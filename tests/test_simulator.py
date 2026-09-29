from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from qsalb.config import load_config
from qsalb.simulator import Simulation


class SimulatorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cfg = load_config(ROOT / "config" / "smoke.json")

    def test_same_seed_is_deterministic(self) -> None:
        first, _ = Simulation(copy.deepcopy(self.cfg), "QSALB-Full", 1.2, "bursty", 42).run()
        second, _ = Simulation(copy.deepcopy(self.cfg), "QSALB-Full", 1.2, "bursty", 42).run()
        self.assertEqual(first, second)

    def test_all_policies_produce_finite_metrics(self) -> None:
        for policy in ["QSALB-Full", "LEO", "GMQ", "LFO", "EAO", "CFOP"]:
            summary, series = Simulation(copy.deepcopy(self.cfg), policy, 0.8, "normal", 101).run()
            self.assertGreater(len(series), 0)
            self.assertGreaterEqual(float(summary["average_queue"]), 0.0)
            self.assertGreaterEqual(float(summary["estimated_latency_ms"]), 0.0)
            self.assertTrue(0.0 <= float(summary["drop_ratio"]) <= 1.0)

    def test_high_load_cannot_exceed_buffers(self) -> None:
        cfg = copy.deepcopy(self.cfg)
        cfg["network"]["queue_capacity"] = {"iot": 2, "edge": 3, "fog": 4, "cloud": 5}
        summary, series = Simulation(cfg, "LEO", 8.0, "normal", 77).run()
        self.assertGreater(float(summary["drop_ratio"]), 0.0)
        self.assertLessEqual(max(row["max_queue"] for row in series), 5.0)

    def test_leo_never_uses_cloud(self) -> None:
        summary, _ = Simulation(copy.deepcopy(self.cfg), "LEO", 3.0, "normal", 91).run()
        self.assertEqual(float(summary["cloud_ratio"]), 0.0)


if __name__ == "__main__":
    unittest.main()

