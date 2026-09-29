# Reconstruction assumptions and manuscript ambiguities

## Parameters supplied by the manuscript

- 100-1000 IoT devices; 5-20 edge nodes; 2-4 fog nodes; one cloud tier.
- Edge processing: 5-10 GFLOPS; fog: 20-50 GFLOPS; cloud: 100-500 GFLOPS.
- IoT-edge bandwidth: 2-10 Mbps and propagation delay: 5-20 ms.
- Regional bandwidth: 100-500 Mbps; cloud propagation delay: 40-80 ms.
- Input size: 50 KB-2 MB; demand: 0.5-4 billion cycles; deadline: 50-500 ms.
- Poisson, MMPP, and trace-inspired arrivals; 20 independent runs; warm-up
  samples removed.
- QSALB score: `-queue_difference + V*(alpha*delay + beta*energy + gamma*cloud_cost)`.

## Values absent from the manuscript

The paper does not state IoT processing rates, queue capacities, slot duration,
energy coefficients, battery voltage, the cloud price, objective weights,
Lyapunov `V`, prediction sensitivity, predictor definition, CFOP thresholds,
MMPP transitions, simulation length, warm-up length, topology mapping, random
seeds, or error-bar definition. Defaults for all of these are in
`config/manuscript.json`; none are buried in source code.

## Explicit modeling decisions

1. **Units.** One slot is one second. Arrival rates in plots are interpreted as
   tasks per device per slot, because the figures use that label even though the
   setup paragraph says tasks per minute.
2. **Service.** The queue model serves an integer number of tasks per slot. A
   node's service limit is derived from its GFLOPS and the configured reference
   cycles per task. Actual task cycles remain in the processing-delay estimate.
3. **Slot order.** Arrivals are assigned and then service is applied. This follows
   the prose and Algorithm 1. The printed equation instead places `I(t)` after
   service; choose the alternative with `arrivals_eligible_same_slot=false`.
4. **Source pressure.** Newly generated tasks form a transient source backlog
   during sequential assignment. This makes the paper's source-destination
   differential meaningful even though all arrivals are routed immediately.
5. **Prediction.** The one-step predictor is an exponentially weighted blend of
   the previous arrival and its running mean.
6. **Latency.** The reported estimate follows the manuscript exactly:
   communication + `Q/(mu+epsilon)` slots + processing. It is recorded for all
   admitted tasks, not only completed tasks.
7. **Energy.** Battery capacity in mAh is converted to joules using the configured
   voltage. Processing and radio energy coefficients are standard, configurable
   reconstruction values.
8. **Feasibility.** A task missing its deadline at every destination is assigned
   to the least-cost destination that still has buffer and energy, and is marked
   as a deadline violation. It is dropped only when no destination is admissible.
9. **Confidence intervals.** Error bars are normal-approximation 95% intervals
   (`1.96*s/sqrt(n)`) across independent seeded replications.
10. **Policy comparisons.** Policies within each scenario/load/replication use
    common random-number seeds, so differences are paired on the same topology,
    tasks, and link samples.

## Known manuscript inconsistencies

- The existing high-load queue figure shows LEO below QSALB, while the text says
  LEO develops fast/unbounded backlog.
- The existing LEO energy curve is exactly zero although local execution uses
  processing energy in the model.
- Several captions say "over time" while the surrounding text says increasing
  load.
- Queue update prose, Algorithm 1, and the displayed queue equation imply two
  different within-slot event orders.

The reconstruction does not encode those existing coordinates. It derives every
result from simulated arrivals, queues, routing, service, and energy accounting.

