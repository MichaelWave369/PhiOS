# PhiOS Elastic Runtime R1: NBG-inspired residency advisor

**Status:** Research alpha, offline advisory only. **No new kernel, drivers, background daemon, hardware probing, or system changes.**

## Hypothesis

Explicit workload demand plus dependency-aware hot/warm/cold residency proposals may reduce idle overhead or peak contention compared with eager loading. That is a hypothesis to benchmark, **not an achieved speedup**. The NBG bubble/gear language here is an architectural analogy; no neural weight transfer, NBG mathematical result, or novel hardware primitive is claimed.

## Contract

- Input `phios.elastic.snapshot.v1`: explicit user-supplied *estimated* RAM/VRAM budgets and bubble manifests. No live collection.
- Bubble states: `cold`, `warm`, `active`, `pinned`. A pin is an externally declared, non-evictable floor. Warm uses RAM only; active/pinned use the declared RAM and VRAM amounts. These are *estimates*, not sampled hardware allocations.
- `demanded` and `pinned` bubble dependencies are transitively promoted to `active` in the **proposal**. Unneeded bubbles are eligible for `warm` only if prefetch was declared and RAM fits, otherwise `cold`.
- Optional warm candidates are sorted by priority, then stable bubble ID, so a lower-priority prefetch cannot displace a higher-priority one. This is a simple heuristic, not a trained or workload-adaptive router.
- A mandatory demand over budget returns `HELD` with **null suggested states** rather than silently evicting essential capabilities.
- Inputs are strictly bounded; cycles, missing dependencies, duplicate JSON keys, unexpected fields, and invalid quantities fail closed.
- Output `phios.elastic.advisory.v1` includes proposed residency, estimated totals, snapshot SHA-256, self-bound receipt SHA-256, and explicit false action/execution authority.

```bash
python -m phios.elastic_runtime --snapshot experiments/elastic/r1_snapshot.json
python -m pytest -q tests/test_elastic_runtime_r1.py
```

CLI exit codes: `0` advisory; `3` mandatory estimated budget overrun / held; `2` unavailable or malformed snapshot. It **reads** a specifically selected local JSON file and prints a deterministic report; it never writes the snapshot, contacts the network, enumerates processes, manipulates a driver, or imports another project runtime. The fixture describes fictional resource estimates, **not benchmark data**.

## Boundaries

This rung is independent of the existing PhiOS/PhiKernel authority decisions and does not confer any capability permission. It cannot launch, freeze, unload, swap, or prefetch real processes, services, weights, firmware, drivers, or memory pages. A green test run proves only the advisory contract. No Linux boot pathway is changed. Do not treat proposed savings in MiB as measured performance improvement.

## Planned R2 measurement gate

1. Collect opt-in, bounded host metrics using independent OS tools, with no authority changes (boot duration, idle RSS, resident working set, VR frame-time p95/p99, page faults, model first-token latency, repeated-token throughput, transfer bytes, actual peak VRAM). Prefer actual per-process/driver measurements over synthetic costs.
2. Replay identical cold/warm/active workloads with fixed input order, recorded hardware/software versions and matched environmental conditions. Compare eager/always-on, fixed prefetch, and advisory-selected plans; count total cost including wakeup and prefetch penalties.
3. Validate on Linux VM first, then explicitly approved non-critical hardware. Avoid driver unloading, service interference, or timing-sensitive Quest 3 pathways before separately proven safety gates.
4. Publish paired receipts and negative results as readily as positive results. Only measured improvement and no regression may justify a narrowly scoped, human-authorized actuator proposal in a *later* rung.

**No auto-promotion:** the eventual executor is a separate, explicitly authorized component. R1 has no execution hook.
