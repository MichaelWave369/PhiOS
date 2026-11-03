# PhiOS Elastic Runtime R7 — PhiStream weight-stage evidence bridge

**Status:** Alpha, offline and read-only. No changes to PhiOS resource management, PhiKernel authority, GPU/CPU residency, model execution, Linux drivers or boot behavior.

## Motivation

The earlier R1–R6 stages gave PhiOS an advisory residency plan, read-only host measurements, trace comparison and reproducibility checks for synthetic/sparse local-file experiments.

[PhiStream's published weight-stage audit](https://github.com/MichaelWave369/PhiStream/blob/main/docs/WEIGHT_STAGE_AUDIT.md) covers something more directly relevant: **actual user-supplied SmolLM2-135M-Instruct CUDA decoder receipts** across four frozen prompt cases on an RTX 5070. Its timer reports that weight staging can dominate the measured decoder wall time. The staging timer explicitly includes file access, tensor materialization, CPU-to-GPU transfer, conversion, GPU synchronization and Python overhead. This is **not** pure PCIe bandwidth or proof of any attainable speedup.

R7 bridges this existing *public evidence format* into PhiOS without importing PhiStream implementation internals, loading the checkpoint, running a GPU workload or granting resource-control authority.

## What R7 accepts

`phios.elastic_phistream_r7` recognizes the public JSON schema `PHISTREAM_WEIGHT_STAGE_AUDIT_V1` emitted by PhiStream's `scripts.weight_stage_audit`.

It expects exactly four canonical cases:

| Case | Prompt tokens | Greedy generation steps |
| --- | ---: | ---: |
| `short_1` | 1 | 32 |
| `mixed_7` | 7 | 32 |
| `repeat_12` | 12 | 32 |
| `spread_24` | 24 | 32 |

The importer requires PhiStream's *reported* exact stage-counter linearity verdict, mandated source/provenance flags, and self-declared manifest/matrix hashes. It independently recalculates:

- Decoder steps = prompt length + 31.
- Staged bytes = decoder steps × per-step weight payload + fixed staged bytes.
- Weight load count = decoder steps × loads per step + initialization load operations.
- Incremental prompt-stage bytes relative to the one-token case.
- Stage-time fraction, nonstage-time difference, and cross-case median and maximum.

It rejects malformed, incomplete or inconsistent claims and refuses private/unknown fields. A PhiStream audit with a nonlinear counter status is **not upgraded** into a positive review.

A valid R7 output includes per-case staging milliseconds and percentages, per-step staged weight payload, an advisory next experiment and content fingerprints. It intentionally does **not** export raw checkpoint fingerprints, checkpoint paths, tokens, local filenames, source files, reference logits or actual weights.

**Important:** R7 reads an already-produced self-reported audit. It cannot authenticate the original model publisher, independently rehash the source checkpoint or confirm that the experiment took place. For that, use the original PhiStream audit with all of its frozen, local input evidence. PhiOS never describes a reviewed audit as verified real-machine provenance.

## Operator usage

In an installed PhiOS Python environment, after running the separate PhiStream audit using PhiStream's documented local procedure:

```bash
python -m phios.elastic_phistream_r7 --audit "/path/to/weight-stage-audit.json"
python -m pytest -q tests/test_elastic_phistream_r7.py
```

Windows PowerShell equivalent:

```powershell
py -m phios.elastic_phistream_r7 --audit "D:\PhiStream\Experiments\weight-stage-audit.json"
```

The path is illustrative; R7 creates no source audit file. It reads only one explicitly selected local JSON file of up to 128 KiB, rejects symlinks, duplicate JSON keys, unknown fields and nonfinite numbers, prints a deterministic report on stdout and never writes output unless the operator explicitly redirects stdout. Exit 0 means `REVIEW_REQUIRED`; exit 2 means `UNAVAILABLE`. Neither exit code authorizes a model run or OS change.

## R7 findings are not optimization claims

The high stage-time fraction makes **batched prefill, weight reuse, transfer overlap, or a carefully bounded warm/pinned layer policy** research hypotheses, not automatic actions. No one can infer a speedup proportional to the staging share because much of the timer covers work that might not be removable, and single-run timings are confounded by prompt length, caches, memory pressure and execution overhead.

R7 reports these permanent false flags:

```text
independent_source_verification
model_reexecuted
transfer_bandwidth_proven
speedup_proven
action_authority
execution_authority
hardware_control
```

The output can later be displayed by PhiMada or a PhiOS operator dashboard as an **advisory observation**. It does not activate any R1 residency proposal and does not read PhiKernel/TIEKAT private state.

## Next experimental gate

Use PhiStream's existing real-model paired-prefill controls and audit receipts as the measurement foundation, rather than inventing an unrelated toy runtime. Compare one fixed checkpoint and prompt set with exact outputs/greedy-token and sparse-logit parity, explicit VRAM constraints, repeated balanced A/B trials, and measurements of staging, first-token latency, decode throughput and system memory. Keep the baseline runnable and never grant automatic scheduling based on a positive descriptive percentage.

A CI-green R7 only proves the import contract. Real model performance must be measured and independently reviewed separately.
