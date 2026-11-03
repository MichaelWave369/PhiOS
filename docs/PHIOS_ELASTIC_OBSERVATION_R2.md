# PhiOS Elastic Runtime R2: opt-in host resource observations

**Status:** Research alpha, manual read-only CPU/RAM capture with optional GPU query. No automated scheduler, driver unload, OS change, resource allocation, inference, or claimed performance gain.

## Purpose

R1's bubble RAM/VRAM numbers are synthetic planning inputs. R2 creates a **bounded, operator-initiated snapshot series** so we can examine real host-wide load before attempting any intervention. This rung **does not** measure whether an elastic plan is faster: an elastic executor does not yet exist.

The Python package already depends on `psutil`. GPU observation is *optional* and invokes only NVIDIA's official **read-only** `nvidia-smi --query-gpu` command. It does not install tools, enable telemetry, request elevation, enumerate processes, or read process titles or filenames. No service stays resident after the command finishes. Each capture prints JSON to stdout and does not save a file unless the operator explicitly redirects that output.

## Windows and Linux quick start

From a Python 3.11+ environment with `psutil` and PhiOS installed (or the PhiOS checkout as the working directory):

```bash
python -m phios.elastic_observation collect --scenario idle --samples 30 --interval-ms 1000 --gpu
python -m phios.elastic_observation collect --scenario btm-vr --samples 30 --interval-ms 1000 --gpu
```

Use separate operator-chosen local files to preserve samples, for example in a UTF-8-aware shell:

```bash
python -m phios.elastic_observation collect --scenario idle --samples 30 --interval-ms 1000 --gpu > idle-r2.json
python -m phios.elastic_observation verify --input idle-r2.json
```

On legacy Windows PowerShell 5.1, redirection may produce UTF-16 text, which the UTF-8 JSON verifier rejects. Use Windows Command Prompt redirection or a UTF-8-capable shell instead. The CLI has no remote upload or implicit file writes. Keep raw receipts local by default; their timestamp, scenario, system capacities and utilization may disclose device information if shared.

`--gpu` is optional; without it, `nvidia-smi` is never invoked. If NVIDIA tooling is unavailable, malformed, or reports multiple GPUs, the GPU observation is `null` and the receipt becomes `PARTIAL`, **not** zero GPU usage. A `PARTIAL` capture returns exit code `3`. An invalid or unavailable mandatory CPU/RAM observation returns exit code `2` with a minimal `UNAVAILABLE` response. Full CPU/RAM captures exit `0`.

## Evidence fields

Input bounds: one scenario label (`[a-z][a-z0-9._-]{0,63}`), 1–120 samples, 100–10000 ms per requested CPU sampling interval. The requested interval is **not** guaranteed as an exact end-to-end cadence: optional NVIDIA polling adds overhead.

Each sample records:

- Index and elapsed time from a local monotonic clock (millisecond precision)
- System-wide CPU busy percentage from `psutil.cpu_percent(interval=...)`
- RAM pressure estimate `total - available`, RAM available and RAM total (MiB)
- Optionally, single-NVIDIA-GPU reported used/total VRAM and GPU utilization, or `null`

Reports include nearest-rank p50/p95/p99 statistics, requested settings, a local wall-clock timestamp, explicit observation scope, a canonical SHA-256 content digest, and fixed `false` action/execution/hardware authority and performance-proof flags. The digest checks accidental integrity of exported receipts, **not** trustworthy hardware provenance; someone can fabricate data and recompute it.

**Important limits:** Neither CPU percentages nor RAM pressure indicate an application's latency. `total - available` approximates memory pressure and should not be interpreted as exact per-process use or occupied physical pages. GPU `memory.used` can include other processes and driver allocations. Samples are discrete, not continuous monitoring, and a self-reported receipt cannot authenticate the machine that produced it.

## Before any optimization claim

1. Capture idle, PhiShell/browser, BTM in VR, and local-model scenarios under comparable conditions. No changes to boot, drivers, or services.
2. On a separately authorized later rung, run paired baseline and candidate conditions with identical tasks and reproducible setup, including wake-up/prefetch overhead.
3. Instrument task latency, VR frame-time p95/p99 and inference first-token/throughput separately. R2 samples are **not** substitutes for these workload-specific measurements.
4. Require a reviewable explanation of any performance gains or regressions. Never let an advisory receipt grant host control or autonomously promote an optimization.

## Contract test

```bash
python -m pytest -q tests/test_elastic_observation_r2.py
```

The tests inject synthetic probes. CI never executes a live hardware scan. The module is independent of PhiKernel private internals and of the R1 plan actuator, which does not exist.
