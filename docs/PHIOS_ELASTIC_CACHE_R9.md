# PhiOS Elastic Runtime R9 — Bounded Shadow Cache Replay

**Status:** Research alpha, offline-only, deterministic **simulation**. R9 introduces **no** live caching, model loading, VRAM allocation, memory eviction, driver manipulation, telemetry or automatic promotion.

## Engineering question

R7/R8 showed how to compare published PhiStream weight-staging observations with real-model paired prefill audit summaries. Neither proves that a new cache makes a given model faster.

R9 tests a narrower, falsifiable question: **for one declared sequence of resource accesses and fixed resource sizes, how many logical bytes would be staged by two simple policies?**

1. **Baseline:** stream the entire declared resource for every access, no cache.
2. **Shadow candidate:** hypothetically preload operator-pinned resources once, retain them permanently, and use least-recently-used (LRU) caching for other resources within an explicit capacity **minus a reserve**. Resources too large for the unpinned portion of the budget are streamed without cache admission.

Both policies consume **the identical declared access trace**. Neither performs actual I/O. Stage-byte counts are a *logical workload model*, not measured SSD bytes, PCIe transfers, DRAM usage, VRAM allocations or elapsed milliseconds.

## Input schema

`phios.elastic.cache-shadow-study.v1` requires exactly:

- `schema_version`: the version literal above.
- `scenario`: short sanitized experiment ID, not a filesystem path.
- `workload_sha256`: 64 lowercase hexadecimal characters; **self-declared**, not verified against actual weights or model output.
- `source`: the literal `operator_supplied_unverified`.
- `budget`: `capacity_bytes` (1 to 64 GiB) and `reserve_bytes` (0 to capacity). Neither is queried from the GPU.
- `resources`: 1–128 objects with a unique sanitized `id`, integer `bytes` (1 to 16 GiB), and explicit Boolean `pinned`.
- `accesses`: 1–4096 resource IDs in access order. Each must exist in `resources`.

Unknown fields, duplicate IDs/JSON keys, nonfinite values, invalid budgets, oversized files and symlinks are rejected. No dependency on PhiStream or on PhiKernel private code is introduced.

## Quick start

From a PhiOS checkout or installed Python 3.11+ environment:

```bash
python -m phios.elastic_cache_r9 --study experiments/elastic/r9_synthetic_cache.json
python -m pytest -q tests/test_elastic_cache_r9.py
```

The included fixture is **made-up synthetic data** with 3 pretend layers and 6 access events. Its 55% reduction in *logical staged bytes* is **not** a 55% acceleration or measured result. A separate fixture with a pinned but never-used layer can produce a **negative** byte delta because pin preloading costs are counted honestly.

The CLI reads only the manually selected bounded local JSON file and writes a JSON review to stdout. It never launches an inference engine, handles a real weight file, interacts with CUDA, or changes system settings. Exit 0 (`REVIEW_REQUIRED`) is a structurally valid simulation, **not a successful real-world speedup**. Exit 3 (`HELD`) means required pins exceed the effective budget and **no candidate simulation is emitted**. Exit 2 (`UNAVAILABLE`) means malformed or unsupported input.

## Outputs

The review includes:

- Baseline bytes staged on every access
- Candidate logical staged bytes, including preload, repeated cache misses and resources bypassing admission
- Hypothetical hits, misses, evictions, preloads and uncachable access count
- Peak and final resident-byte *estimates* with preserved reserve
- Signed logical staged-byte difference and percentage relative to baseline, including possible regressions
- Canonical input SHA-256 and self-binding report hash (neither authenticates experiment provenance)

It **does not export individual resource IDs or the original access trace**. Those IDs should still be non-sensitive, since an operator could choose to publish the input study separately.

These flags are hardcoded `false`:

```text
physical_transfer_bytes_measured
wall_time_measured
model_output_parity_checked
performance_improvement_proven
automatic_promotion
action_authority
execution_authority
hardware_control
```

## Key limitations

- The simulation assumes a deterministic access sequence and resource sizes. Real models have tensors, kernel dependencies, activations, KV caches, temporary allocations, fragmentation, page alignment and competing workloads.
- A logical byte reduction does not establish improved prefill time, token throughput, first-token latency, power use or actual GPU memory savings.
- A simulator's chosen pin budget is not an independently confirmed safe VRAM reservation. Real PhiStream/PhiOS behavior is unchanged.
- An LRU cache can behave worse than streaming when preloaded pinned layers are never accessed; R9 counts this and does not hide negative results.
- Neither file metadata nor R7/R8 review status is sufficient to make a cache placement decision on a real GPU. No R1 residency state is promoted.

## Next experiment

Use **explicitly authorized** PhiStream layer or expert access traces from a fixed checkpoint and capture complete per-resource sizes. Start with R9 replay to reject plans that exceed a chosen reserve or have insufficient reuse, then build a separately reviewed **read-only paired measurement experiment** that compares the exact model output, first-token time, throughput, transfers, VRAM headroom and cache/thermal behavior. A live actuator, if ever created, must be opt-in, reversible, fail-closed and operator-approved, not enabled by this PR.

**Ledger above ego:** a saved byte on paper is not a millisecond saved on hardware.
