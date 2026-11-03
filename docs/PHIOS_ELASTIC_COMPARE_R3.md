# PhiOS Elastic Runtime R3 — Paired Workload Comparisons

**Status:** alpha, offline, read-only, descriptive. This is not an operating-system scheduler or evidence of a performance improvement.

## Purpose

R1 plans bubble residency with estimated RAM/VRAM costs; R2 samples real host-wide utilization. Neither measures whether a user workload is faster. R3 accepts separately observed matched baseline/candidate workload results and generates a bounded comparison for human review. The example file is **synthetic illustrative data**, not measurements of Break the Matrix, Quest 3, PhiOS, or any GPU. No elastic actuator is enabled.

## Contract

Input schema `phios.elastic.paired-study.v1` has exactly `schema_version`, `experiment`, `pairs`. The experiment declares a scenario, pseudonymous environment label, operator-supplied `workload_sha256`, `protocol_id`, metric and `declared_source=operator_supplied_unverified`. These identifiers are self-declared, not verified against actual workload files, hardware or protocols.

Supported metrics: `frame_time_p95_ms`, `startup_ms`, `first_token_ms`, `task_elapsed_ms` (lower is better), `tokens_per_second`, `throughput_ops_per_second` (higher is better). The unit is derived from the metric name, not an independently supplied field.

Each study requires 6–64 uniquely named pairs, with AB (baseline first) / BA (candidate first) orders balanced within one trial. Each baseline/candidate arm includes a positive finite value, an integer `samples`, a Boolean `passed` flag, and a nullable `r2_receipt_sha256` digest label. Frame-time p95 requires at least 100 samples per run. R3 does not dereference or authenticate R2 hashes. Order balancing is a guard against a simplistic test-order bias, not a guarantee of comparable conditions.

## CLI

```bash
python -m phios.elastic_compare --study experiments/elastic/r3_pairs.json
python -m pytest -q tests/test_elastic_compare_r3.py
```

R3 reads only the selected bounded local JSON file and prints results. It does not run workloads, sample hardware, contact a network, modify drivers or write files. Exit `0` is `REVIEW_REQUIRED` (structural checks passed, all declared correctness flags true), exit `3` is `HELD` (any declared correctness failure), and exit `2` is malformed/unavailable. Exit 0 is **not** a performance-success assertion.

## Output and interpretation

The `phios.elastic.paired-comparison.v1` report includes the raw per-arm values and counts, paired directional percentages, medians for baseline and candidate, **median of paired percentage changes**, best/worst percentage changes, win/tie/loss counts, correctness failures, number of R2 digest labels, and deterministic SHA-256 hashes for normalized study content and report. A positive paired percentage means only that candidate did better on the declared metric for that pair. The hashes detect accidental edits, not forged evidence.

All output flags for action authority, execution authority, hardware control, statistical-significance claims and proven performance improvement remain **false**. The report never promotes a candidate or gives a scheduler permission to modify resource residency.

## Next measurement gate

1. Freeze and independently inspect a workload/protocol, actual hardware/software versions, and correctness criteria.
2. Collect real startup, VR frame-time, or inference timing evidence from external approved tools; interleave at least six matched AB/BA pairs under comparable conditions. Capture R2 CPU/RAM/GPU observations separately.
3. Preserve failures and regressions. Do not cherry-pick candidate results or compare unmatched workloads. A correctness failure holds review regardless of speed.
4. Evaluate noise, uncertainty, repeated sessions, thermal/power effects and user-visible regressions before any optimization claim or human-authorized actuation experiment.

## Boundaries

R3 rejects unknown/duplicate JSON fields, unknown metrics, duplicate pair IDs, unbalanced AB/BA orders, invalid values, untrusted source assertions, insufficient sample counts, oversized files and symlink inputs. This tool **cannot** verify that operator-entered numbers are real measurements. A user can fabricate inputs and hashes; provenance remains unverified.
