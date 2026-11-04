# PhiOS Elastic Runtime R10: PocketRotor native-routing holdout replay

**Status:** Offline, opt-in, read-only research bridge. It does not execute PhiStream, run a model, download weights, transfer actual experts, allocate GPU/CPU caches, change live residency, or authorize PhiKernel resource placement.

## Connection

PhiStream [PocketRotor E2-R](https://github.com/MichaelWave369/PhiStream/blob/main/docs/POCKETROTOR_E2_ROUTE_BRIDGE.md) already has a strict **post-native-router expert selection** capture format, and its E5 Granite pilot can produce captures inside a separately approved run. R9 simulates a byte-bounded pinned+LRU residency strategy.

R10 connects these existing public contracts:

**Explicit E2-R capture → one chosen layer + one chosen holdout → flattened recorded expert IDs → R9 shadow cache replay.**

R10 never invents or changes routing choices. It does not import or execute PhiStream. It never uses the **training** split as the evaluation trace, never connects different layers as if they shared a cache and never silently truncates long access sequences.

## Supported source file

An existing `PHISTREAM_POCKETROTOR_E2_NATIVE_ROUTE_CAPTURE_V1` JSON with exactly `schema`, `expert_count`, `source` and `events`. The `source` requires `kind` (either `synthetic` or `operator_asserted_native`), runtime/model labels, declared checkpoint SHA-256, `route_semantics=POST_NATIVE_ROUTER_SELECTED_EXPERT_IDS` and `token_text_recorded=false`.

Each event contains exactly split, layer, step and selected expert IDs. R10 validates contiguous per-layer step numbers, uniform layer coverage across train and holdout splits, identical split lengths for every captured layer, 1–8 unique experts per step, maximum 256 declared experts and 1–128 routed layers, with 2–4096 steps per split. Captures are limited to 16,384 events or 2 MiB of local JSON. Filenames and source runtime/model labels are not exported.

**No provenance authentication:** A source value of `operator_asserted_native` is an operator's statement, not a cryptographic proof of actual model execution. A pinned checkpoint digest binds the asserted identity but R10 cannot verify it against real model weights.

## How to run

From a PhiOS checkout with Python 3.11+ and an **already-existing, authorized** local PocketRotor E2-R route capture:

```bash
python -m phios.elastic_router_r10 \
  --capture /path/to/pocketrotor-native-capture.json \
  --layer 0 \
  --holdout holdout_a \
  --expert-bytes 4096 \
  --capacity-bytes 16384 \
  --reserve-bytes 4096
```

On Windows PowerShell, use a one-line command or PowerShell backtick continuations. All paths are examples. The capture must already exist: R10 does not enable any pretrained model download or recording workflow.

For an explicit **hypothetical** pin, append `--pin-expert 7` (repeat for more pins). R10 counts the preload cost even when the pinned expert is never used.

`--expert-bytes` is an **operator-supplied uniform expert size**, 1 byte–16 MiB, not a measured value. `--capacity-bytes` is a hypothetical budget from 1 byte–2 GiB; reserve must fit and is never spent. No actual GPU VRAM is inspected. Only a maximum of 128 **distinct experts selected in the holdout or explicitly pinned** can be represented by R9. The selected layer's holdout may expand to at most 4096 individual routed-expert accesses. Larger traces **fail closed** rather than returning a potentially misleading sample.

The included `experiments/elastic/r10_synthetic_pocketrotor_capture.json` is invented fixture data with two layers and two holdouts. No model was run and no native routes were captured to produce this fixture.

## Outputs

The `phios.elastic.pocketrotor-cache-bridge.v1` receipt includes:

- Exact input capture content SHA-256 (not proof of provenance), source kind and selected layer/holdout.
- Holdout step count, flattened number of selected expert accesses, distinct expert count and assumed uniform expert size.
- R9's nested shadow receipt: stream-every-use baseline versus hypothetical pinned+LRU candidate, *logical* staged bytes, hit/miss/eviction counts, optional pin preload costs and reserved headroom.
- Explicit **false** flags for authenticated routing provenance, hardware timing, real transfers, output parity, model execution, performance proof, action authority, execution authority and hardware control.

No prompt text, tokens, output logits, local file paths, raw router events, raw expert ID lists, checkpoint fingerprints or source model name are included. Treat R9's simulated byte reduction only as an **algorithmic estimate under the declared trace and sizes**, never as measured throughput, GPU memory savings, SSD/PCIe bandwidth or latency.

The CLI is local and stdout-only. Exit 0 = `REVIEW_REQUIRED` (structural replay valid); exit 3 = `HELD` (mandatory simulated pins exceed effective budget); exit 2 = `UNAVAILABLE` (invalid, unsupported or unavailable capture). No code path grants live control.

## Testing

```bash
python -m pytest -q tests/test_elastic_router_r10.py
```

The tests use only the synthetic fixture, which is **not** pretrained evidence.

## Next gate

Obtain an independently checked, operator-authorized native MoE capture under a fixed checkpoint and disjoint holdout workload. Use R10 to identify candidate policies, then run separately approved matched tests of **real expert staging** with exact model-output parity, pinned VRAM headroom, transfer timings, cache overhead, power/thermals and a rollback option. A favorable shadow byte count alone must never promote a cache strategy.
