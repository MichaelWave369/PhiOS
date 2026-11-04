# PhiOS Elastic Runtime R13: shared-cache replay with per-expert size declarations

**Research alpha. Offline, opt-in and advisory only.** No live model loading, CUDA, weight transfers, VRAM allocation, driver changes, background capture or PhiKernel authority.

## Why R13

R12 tests every routed layer but gives each layer its own hypothetical memory budget. R13 removes that shortcut: it replays an entire native-routing holdout through **one shared cache across all layers**, constrained by one declared capacity and one explicit reserve. This gives a more faithful *logical* accounting model, but still does not simulate actual GPU execution.

R13 uses a manifest with **individual size declarations for every expert in every routed layer**. Sizes may differ. They remain operator supplied, not independently measured or authenticated by this module.

## Inputs

The first input is an existing PHISTREAM_POCKETROTOR_E2_NATIVE_ROUTE_CAPTURE_V1 JSON produced using PhiStream's E2-R format. It must pass the strict R10 validator, contain training plus at least two disjoint holdouts, and use **step-major, ascending-layer event order** within each split. R13 rejects alternative inter-layer orderings rather than inventing chronology. All reported expert selections are unverified source claims.

The second input is a source-bound JSON of schema phios.elastic.expert-footprints.v1, with exactly these fields:

~~~json
{
  "schema_version": "phios.elastic.expert-footprints.v1",
  "source": "operator_supplied_unverified",
  "size_basis": "estimated",
  "source_capture_sha256": "<64 lowercase hex digest>",
  "checkpoint_sha256": "<declared checkpoint SHA from capture>",
  "layers": [
    {"layer": 0, "expert_sizes_bytes": [4096, 4096, 4096, 4096]}
  ]
}
~~~

The illustrative four-element array above is valid only for a capture declaring **one layer and four experts**. A real manifest must cover every captured layer exactly once and every declared expert index exactly once, with sizes from 1 byte to 16 MiB. The capture's canonical content SHA and declared checkpoint SHA must match the manifest. Matching hashes do not prove that any model was executed.

Allowed size_basis values:

- estimated: synthetic or operator-estimated tensor sizes
- operator_reported_tensor_shapes_unverified: from separately reported tensor shapes, **without independent verification by PhiOS**

PhiStream's E5 pretrained Granite pilot, if actually run with explicit operator authorization, can report expert_weight_bytes_per_layer_measured_from_params and an associated native capture. See: https://github.com/MichaelWave369/PhiStream/blob/main/docs/POCKETROTOR_E5_PRETRAINED.md. That pilot checks a uniform per-expert footprint across its 24 layers, so an operator can construct an explicit manifest from the local receipt and capture. R13 does not run, download, verify or generate the E5 pilot artifacts.

## Replay rules

R13 validates the *entire capture and manifest* first. The supported ceiling is 32 routed layers, 8,192 expert accesses per holdout and 16,384 across all holdouts. It never selects favorable layers or truncates oversized holdouts.

It derives conservative atomic-demand headroom from the **eight largest expert sizes in each layer**. A declared effective capacity smaller than the largest possible eight-expert group returns HELD with no holdout results. This conservative rule can exclude some workloads that would fit their observed smaller groups.

The candidate policy is frozen from training events alone: rank selected (layer, expert) resources by training frequency per byte, using exact integer comparison and deterministic identifier tie breaking; pin up to 32 while preserving atomic-group headroom. No holdout event influences pin selection.

Each holdout starts with an empty cache except for its candidate's preloaded pins. The same declared step-major routing events are replayed through (1) one global unpinned LRU and (2) one global pinned-plus-LRU. A routed group is treated as atomic: all its required experts must coexist alongside pins. The replay charges each load, candidate preload and eviction with the operator-declared bytes.

It reports every holdout including negative results, total signed logical staged-byte differences, cache hits/misses, evictions, preload costs and peak simulated residency. **Cache state resets between independently replayed holdouts.**

## Synthetic demonstration

From PhiOS repository root on Python 3.11+:

~~~bash
python -m phios.elastic_shared_r13 --capture experiments/elastic/r10_synthetic_pocketrotor_capture.json --footprints experiments/elastic/r13_synthetic_expert_footprints.json --capacity-bytes 81920 --reserve-bytes 8192 --max-pins 4

python -m pytest -q tests/test_elastic_shared_r13.py
~~~

The included two-layer input is **invented**. It uses assumed 4,096- and 6,144-byte experts. Under an 81,920-byte shared budget with an 8,192-byte reserve, the training-pinned policy ties one holdout and regresses another by 6,144 *logical staged bytes*: an unused preloaded expert costs capacity and work. It is not a real-GPU slowdown.

Both commands run locally. On Windows PowerShell, a one-line command works as written. There is no model download, no device access and no source file modification.

## Output and limits

The result schema is phios.elastic.shared-cache-replay.v1. It retains source and manifest hashes, source kind, assumed versus operator-reported size basis, a **holdout-blind frozen policy hash**, number of selected pins, per-holdout global cache counters, aggregate results and the worst sign of an observed simulated result. It omits actual expert IDs, raw capture events, checkpoint hashes, runtime labels, prompt contents and local file paths.

Exit 0 with REVIEW_REQUIRED means a complete structural *simulation*. Exit 3 with HELD means the shared cache cannot reserve the conservative group headroom. Exit 2 with UNAVAILABLE means invalid or unsupported evidence. None authorizes host action.

All reviews explicitly set these flags to false: routing_source_authenticated, weights_rehashed_here, expert_size_independently_measured_here, model_executed, physical_transfer_bytes_measured, wall_time_measured, model_output_parity_checked, speedup_proven, automatic_promotion, action_authority, execution_authority and hardware_control.

The simulator does not model real PCIe bandwidth, model kernel scheduling, layer-to-layer GPU lifetime, KV cache, activations, fragmentation, thermal effects, competing workloads or actual inference latency. The declared cache budget is not a physical free-VRAM observation. An all-positive simulation cannot establish a real speedup.

**Next evidence gate:** explicitly approved real model tests with output parity, real expert-transfer and VRAM measurements, first-token latency, token throughput, checkpoint and tensor-shape verification, and a reversible protected fallback. No such live test is run by R13.

**Ledger Above Ego:** a single honest shared-budget model beats a dozen pretend independent memory pools.
