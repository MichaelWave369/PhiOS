# PhiOS Elastic Runtime R12: complete all-layer/all-holdout shadow census

**Status:** Offline research alpha. No live cache, GPU allocation, checkpoint read, model inference, hardware timing, operating-system action, network access, or scheduler promotion.

## The problem R12 solves

R11 uses the real **format** of PhiStream PocketRotor E2-R post-router captures to learn a frequency-ranked pinned-expert policy exclusively from each selected layer's **training** route IDs, then evaluates it on **all that layer's disjoint holdouts**.

But reporting a single good layer can be misleading. A routing strategy might reduce hypothetical staging for one layer while worsening it elsewhere. R12 runs the unmodified R11 experiment on **every** captured layer and **every** captured holdout, and refuses to report a partial census. The policy configuration is frozen upfront and identical across layers except for each layer's training-derived IDs.

The input is an explicitly selected file in the public `PHISTREAM_POCKETROTOR_E2_NATIVE_ROUTE_CAPTURE_V1` schema. No source claim, including `operator_asserted_native`, constitutes independent provenance verification. R12 never generates native routing choices itself.

## Method

1. Validate the entire source capture with R10's strict E2-R parser: complete and contiguous per-layer steps, training first, same layer set in every split, no user text, and 2–4096 steps per split.
2. Require **at least two holdouts**, and check the census will fit the bounds: **1–32 complete layers** and **no more than 96 layer×holdout cells**. A larger capture is rejected rather than silently sampled.
3. Accept one **hypothetical uniform expert byte size**, capacity, reserve and maximum pinned-expert count that apply to every layer. These are declarations, **not measured tensor sizes or free VRAM**.
4. Require capacity minus reserve to hold at least **two expert slots**. Otherwise return `HELD` before evaluating any layer.
5. For each layer, call R11: freeze a training-only frequency-ranked pin selection, then simulate **both** plain LRU and pinned+LRU on **every** holdout. R9 charges pinned preloads and cache misses, respects reserve, and allows negative results.
6. Preserve **every** individual layer/holdout result and summarize improved/tied/regressed cells, signed logical-byte deltas, worst individual regression, and positive/negative totals across layers.

**Important accounting boundary:** each layer is simulated with a **separate independent hypothetical cache**, and each holdout is separately replayed from an empty state. R12 aggregates simulated staged bytes for descriptive comparison, **not** a global shared VRAM allocation or production execution sequence. Each holdout's pin preload is counted separately.

R12 does **not** claim a 24-layer Granite model can simultaneously keep 24 different per-layer pin budgets in one GPU memory reservation. It does not account for activations, KV cache, kernel scratch, tensor alignment, fragmentation, quantization, shared layers, scheduling overhead, or physically measured transfers.

## Run with the included synthetic fixture

From the PhiOS repository root on Python 3.11+:

```bash
python -m phios.elastic_census_r12 \
  --capture experiments/elastic/r10_synthetic_pocketrotor_capture.json \
  --expert-bytes 4096 \
  --capacity-bytes 16384 \
  --reserve-bytes 4096 \
  --max-pins 2

python -m pytest -q tests/test_elastic_census_r12.py
```

On Windows PowerShell, put all options on one command line or use PowerShell backtick continuations instead of Unix shell backslashes.

The included route capture is **invented** with two layers and two holdouts. R12 tests also create a purely synthetic 24-layer case to ensure the entire census is covered. Neither is evidence of a real pretrained Granite or Qwen experiment.

For an operator-authorized genuine experiment, replace the `--capture` path with an already-existing E2-R JSON file produced by PhiStream's separately approved native post-router capture process. R12 does not initiate the capture, download weights or invoke a pretrained-model workflow.

## Interpret the report

`phios.elastic.all-layer-holdout-census.v1` contains:

- Source kind and a canonical input SHA-256, never model provenance attestation
- The declared number of layers, holdouts and expected cells, plus the **actual total of completed cells**
- A frozen training-derived policy digest and selected-pin **count** for each layer, without printing raw expert IDs
- Each layer×holdout's staged logical bytes under the same-budget plain LRU and pinned+LRU policies, its preload cost, hit counts and signed byte delta
- Total improved/tied/regressed cells, layer-level aggregate sign counts and **worst cell** signed delta
- A deterministic output digest and explicit no-execution/no-promotion/no-speedup flags

A `REVIEW_REQUIRED` report (exit 0) means the deterministic simulated census completed structurally, **not** that hardware is faster. `HELD` (exit 3) means the declared budget cannot provide the two-slot minimum. `UNAVAILABLE` (exit 2) means invalid or unrepresentable input. A failure never returns an apparently complete partial result.

No raw route event arrays, expert-ID selections, tokens, model weights, runtime labels or local input path appear in the output.

## Research integrity and next milestone

A single `positive total` can conceal losing layers or holdouts, so R12 presents both the aggregate and the cell-by-cell regressions. A positive simulated byte delta is **not** saved milliseconds, real cache hit rate, PCIe bandwidth improvement, GPU memory efficiency, parity proof, or production readiness.

Every output explicitly marks these false:

```text
routing_source_authenticated
model_executed
real_weight_transfers_measured
model_output_parity_checked
wall_time_measured
speedup_proven
statistical_significance_established
automatic_promotion
action_authority
execution_authority
hardware_control
```

**Next gate:** use separately approved native MoE instrumentation to collect actual, *per-layer expert sizes* and real routing captures, then compare a baseline and a reversible cache candidate on a *single shared VRAM budget* with full output parity, transfer timing, first-token latency, token throughput and protected fallback. None of that execution is performed by R12.

**Ledger above ego:** a complete simulated census is far more useful than a conveniently selected winning layer.
