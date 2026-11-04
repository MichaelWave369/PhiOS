# PhiOS Elastic Runtime R11: frozen training-only expert pinning

**Status:** research-alpha, offline, opt-in, descriptive and **not hardware control**. This command never runs a language model, imports PhiStream, moves weights, allocates GPU memory, downloads checkpoints, or changes a running cache.

## Purpose

R10 introduced an offline bridge from a [PhiStream PocketRotor E2-R post-native-router capture](https://github.com/MichaelWave369/PhiStream/blob/main/docs/POCKETROTOR_E2_ROUTE_BRIDGE.md) to R9's bounded pinned+LRU shadow simulator. It allows a person to specify hypothetical pinned experts, but manually selecting them *after looking at holdout results* risks hindsight bias.

R11 creates and freezes its pin policy from **training events only**, before replaying **every declared holdout**. No holdout event contributes to expert selection. Comparisons are to a fair unpinned-LRU reference with **the same effective capacity and reserve**, not to an arbitrarily worse stream-on-every-use baseline.

## Frozen algorithm (not an inference improvement)

1. Accept a previously collected and operator-chosen `PHISTREAM_POCKETROTOR_E2_NATIVE_ROUTE_CAPTURE_V1` JSON trace using the existing R10 strict validator. The capture must have `train` and **at least two disjoint holdout splits**, all with the same routed layer set and contiguous per-layer steps.
2. Select exactly one routed layer via `--layer`. Count how often each expert was selected in that **layer's training steps**.
3. Rank expert IDs by descending training-use count; ties break by ascending expert ID. Select the highest-ranked experts up to `--max-pins` (default 2, maximum 16), **bounded by an explicit hypothetical cache capacity minus reserve and at least one free unpinned slot**. Zero pins is a supported no-change control.
4. Bind this frozen decision to a deterministic SHA-256 of the training selections, chosen IDs and budget configuration. The output does **not** disclose the chosen IDs. Changing holdout data changes the complete capture hash but must never change the frozen policy hash.
5. Replay **all declared holdouts** twice through R10/R9: an unpinned LRU baseline and the training-derived pinned+LRU candidate. Neither strategy alters or reorders the real native expert IDs.
6. Report each holdout's logical bytes staged, cache hits, candidate preload cost, hypothetical peak residency and signed staged-byte delta; aggregate improved/equal/regressed holdout counts and total signed byte delta. **Negative and mixed results remain visible**.

R11 refuses to cherry-pick one good holdout, exceed R9's 4096 expanded-access limit, or continue partially when any selected holdout is invalid.

## Command

From a PhiOS Python 3.11+ checkout, with an **already-existing, explicitly authorized** E2-R capture:

```bash
python -m phios.elastic_holdout_r11 \
  --capture /path/to/authorized-pocketrotor-capture.json \
  --layer 0 \
  --expert-bytes 4096 \
  --capacity-bytes 16384 \
  --reserve-bytes 4096 \
  --max-pins 2
```

On Windows PowerShell, put those options on one command line or use PowerShell backticks. Do not interpret the example paths or values as a real model's measured expert sizes.

To try the synthetic fixture already included in PhiOS (from the repository root):

```bash
python -m phios.elastic_holdout_r11 --capture experiments/elastic/r10_synthetic_pocketrotor_capture.json --layer 0 --expert-bytes 4096 --capacity-bytes 16384 --reserve-bytes 4096 --max-pins 2
python -m pytest -q tests/test_elastic_holdout_r11.py
```

This fixture is **invented routing data** from R10, not a pretrained IBM Granite or Qwen capture, not a field measurement, and not proof of any performance benefit.

## Budget and output interpretation

- `--expert-bytes` is an assumed **uniform** expert size, not a measured tensor layout; range 1 byte–16 MiB.
- `--capacity-bytes` is hypothetical, range 1 byte–2 GiB; reserve is 0–capacity. It is **not** observed free VRAM.
- If the effective capacity is smaller than two expert slots, the result is `HELD`, with no partially evaluated holdouts. When the capacity can hold more, pinned selection is capped so at least one slot remains for unpinned demand.
- Output `phios.elastic.train-holdout-cache-review.v1` contains selected-pin **count**, a blinded frozen-policy hash, the chosen layer, per-holdout accounting, and aggregate signed byte differences. It contains no selected expert-ID list, raw token steps, checkpoint fingerprint, user prompt, model output or local file path.
- Source kind `operator_asserted_native` is **not** independent proof of native routing, even if upstream measured it. No original checkpoint is verified in R11.
- Successful structural replay is `REVIEW_REQUIRED` (exit 0), budget hold is `HELD` (exit 3), unsupported or malformed input is `UNAVAILABLE` (exit 2). Neither 0 nor positive staged-byte delta means real performance improved.

All output routes remain hypothetical. The flags for authenticated provenance, model execution, actual weight transfers, output parity, speedup proof, automatic promotion, action authority, execution authority and hardware control **always remain false**.

## What this cannot establish

The simulator is not a GPU allocator, and its logical staged bytes aren't measured PCIe/SSD traffic. It does not model precise kernel scheduling, expert compute time, transfer/compute overlap, mixed-precision tensor sizes, different layer sizes, KV caches, fragmentation, or host contention. It has no timing measurement or confidence interval and no correction for training/holdout distribution shifts. More pinned hits can still cost more loading, so **preload cost is included**.

A training-only rule that saves logical bytes on every holdout is a candidate for a separate **operator-approved, reversible, real-model experiment**, not authorization to deploy an adaptive cache. If one holdout regresses, keep the result instead of filtering it away.

The next gate requires actual native model captures and fixed checkpoint/outputs with parity checks, measured transfers and latency, VRAM headroom, and separate explicit approval before hardware changes. Do not auto-run any PhiStream pretrained workflow simply because R11 merged.

**Ledger above ego:** saved logical bytes are not saved milliseconds.
