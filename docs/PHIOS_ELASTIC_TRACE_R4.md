# PhiOS Elastic Runtime R4: workload trace-to-R3 bridge

**Status:** Alpha; offline, opt-in, advisory only. No live PhiOS scheduling, model-weight transfer, driver handling, background capture, or performance proof.

## Why this rung exists

R1 models a residency plan from estimated budgets, R2 observes bounded host-wide CPU/RAM/GPU utilization, and R3 compares operator-entered paired summaries. R4 adds a constrained path for *individual time samples* collected by a workload to become the R3 comparison input. It allows timing variability to remain inspectable before aggregation, rather than requiring humans to type p95 or elapsed-time values into a manifest.

R4 **does not** record GPU rendering timestamps automatically. It does not claim Quest 3 frame presentation timing, CPU frame time, or network latency. A browser `requestAnimationFrame` interval is only a proxy for frame pacing. A trace file can be fabricated or inaccurately labeled; neither hashes nor tests authenticate measurements.

## Trace contract

The `phios.elastic.trace-study.v1` JSON document has exactly `schema_version`, `experiment`, and `pairs`. The experiment carries the existing R3 fields: `scenario`, `environment_id`, `protocol_id`, self-declared `workload_sha256`, `metric`, and `declared_source` (fixed to `operator_supplied_unverified`).

Metrics supported in R4:

- `frame_time_p95_ms`: nearest-rank p95 of 100–2048 positive frame-duration samples per arm, each in *integer microseconds*.
- `startup_ms`, `first_token_ms`, `task_elapsed_ms`: median of 1–2048 positive elapsed-duration samples, in *integer microseconds*.

Each experiment requires **6–64 matched pairs**, with balanced AB (baseline-first) and BA (candidate-first) orders. Each pair has `pair_id`, `order`, `baseline`, and `candidate`. Each arm carries exactly `durations_us`, `passed` (the operator's correctness assertion), and `r2_receipt_sha256` (nullable, unverified). Durations must be between 1 microsecond and 1 hour; the JSON file is limited to 2 MiB. Unknown fields, nonfinite JSON numbers, symlinks, duplicate JSON keys, missing/invalid durations, and invalid R3 pairing contracts are refused.

## Run the offline converter

```bash
python -m phios.elastic_trace --trace experiments/elastic/r4_illustrative_trace.json
python -m pytest -q tests/test_elastic_trace_r4.py
```

Exit 0: valid data with `REVIEW_REQUIRED` (not a successful performance result). Exit 3: `HELD` due to correctness failure. Exit 2: `UNAVAILABLE` due to invalid or unavailable trace.

The included `r4_illustrative_trace.json` is deliberately **invented synthetic data** for compatibility testing; it represents no PhiOS/BTM/RTX measurements. It has 100 repeated durations per arm, not realistic variance. Do not draw performance conclusions from it.

Output `phios.elastic.trace-comparison.v1` contains a hash of the complete input, the derived R3 comparison, a receipt hash, and explicit `false` flags for provenance authentication, performance proof, action authority, execution authority, and hardware control. All data is local and untrusted. No network or machine probing occurs; the CLI prints to stdout and does not write a file.

## Recording real measurements

To time a **caller-owned synchronous Python task**, use `phios.elastic_trace.measure_call`:

```python
from phios.elastic_trace import measure_call

outcome, duration_us = measure_call(lambda: my_existing_read_only_task())
# Store duration_us in a separately reviewed, operator-chosen trace.
# Decide 'passed' based on actual correctness tests, not mere completion.
```

The function calls the supplied callable exactly once and measures elapsed time with `time.perf_counter_ns`; it does not invoke unspecified workloads. **Caller functions may themselves have side effects.** Exceptions propagate and generate no falsely successful sample. A one-off duration cannot establish an improvement: record matched repeated conditions and environmental metadata separately.

For a WebXR app such as Break the Matrix, a future explicitly approved integration could record `performance.now()` timestamp differences as integer microseconds:

```js
const deltaUs = Math.round((currentFrameTimestampMs - lastFrameTimestampMs) * 1000);
// Record only positive bounded intervals; do not claim GPU frame-time precision.
```

Such capture is **not implemented** in BTM by this PR. No automatic collection, upload, or telemetry is enabled. Do not include personal input content, headset identifiers, filenames, or absolute filesystem paths in public benchmark traces.

## Controls and next gate

R4 reuses the R3 validator and never automatically promotes a result. R1 residency states remain proposals only. For meaningful testing, first freeze a real workload (fixed assets, model weights and prompts where applicable), capture cold/warm conditions in alternating order, record device/OS versions independently, and assess p95/p99 variance and correctness. Only after those steps is a separate, operator-approved, reversible residency actuator justified as an experiment. Do **not** enable host driver unloading or bypass existing PhiOS/PhiKernel authority gates.
