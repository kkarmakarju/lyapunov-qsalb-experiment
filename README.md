# QSALB experiment reconstruction

This directory contains a clean-room, reproducible implementation of the
experiments described in the manuscript **Lyapunov-Driven Load Balancing for
Queue Stability in IoT-Edge-Fog-Cloud Systems**.

The code is a reconstruction, not the unavailable original Colab notebook.
Every quantity stated by the manuscript is represented in
`config/manuscript.json`. Values that the manuscript does not state are marked
as reconstruction assumptions in `ASSUMPTIONS.md` and kept configurable.

## What is implemented

- A slotted IoT-Edge-Fog-Cloud simulator with finite FCFS queues.
- Poisson, MMPP bursty, and trace-inspired arrivals.
- Mobility-driven links, regional fog congestion, and 100-1000-device stress
  scenarios.
- QSALB's prediction-adjusted queue differential and drift-plus-penalty score.
- Baselines: LEO, GMQ, LFO, EAO, and CFOP.
- Ablations: NoPred, NoEnergy, and NoQueue.
- Twenty independent replications, warm-up removal, deterministic seeds,
  per-run raw CSVs, aggregates, 95% confidence intervals, and SVG figures.
- No third-party dependency is required for simulation, CSV export, or SVG
  figures. When Pillow is available, matching PNG figures are also generated.

## Run

From this directory:

```powershell
python run_experiments.py --config config/manuscript.json --output results/manuscript
```

The full manuscript configuration is intentionally substantial. For a quick
validation run:

```powershell
python run_experiments.py --config config/smoke.json --output results/smoke
```

Select only some experiment families with, for example:

```powershell
python run_experiments.py --config config/manuscript.json --output results/manuscript --plan baseline,ablation
```

## Outputs

- `raw_runs.csv`: one row per policy/load/scenario/seed.
- `aggregate.csv`: means, sample standard deviations, and 95% confidence
  intervals across independent runs.
- `timeseries.csv`: averaged slot-level trajectories for the time-series run.
- `figures/*.svg` and optional `figures/*.png`: publication-ready plots
  generated directly from aggregates and time-series data.
- `resolved_config.json`: the exact configuration copied into the result.
- `run_metadata.json`: timestamp, Python version, platform, and elapsed time.

The principal metrics are time-average backlog per node, queue variance, estimated
end-to-end latency, energy per slot, cloud-use ratio, throughput, deadline
violation ratio, and drop ratio. Latency is evaluated for every admitted task
using the manuscript's communication + queue-wait + processing expression;
this avoids survivorship bias when a policy becomes unstable.

## Test

```powershell
python -m unittest discover -s tests -v
```

## Reproducibility note

The figures already embedded in the manuscript cannot be exactly regenerated
from the paper alone. Several required values and seeds are absent, and some
plotted trends conflict with the accompanying claims. This implementation is
therefore designed to make assumptions visible and to regenerate scientifically
auditable results, rather than hard-code the existing plot coordinates.

