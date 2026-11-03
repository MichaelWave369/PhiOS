# PhiOS Elastic Runtime R6 — Repeated-session residency review

**Status:** Experimental, offline, operator-controlled, zero-authority. This is a review of R5 result files, **not** a new benchmark mode, OS driver manager, scheduler, PhiStream weight loader, or proof of a speedup.

## Why R6 exists

R5 compares eager full-file reading with read-only memory-mapped sparse reads, using correct matching byte windows and alternating AB/BA trials. It pre-hashes the source file, which warms the operating-system cache. Timing noise can dominate one run, so **one R5 output must not be treated as a global performance conclusion**.

R6 reviews 3–12 **operator-selected** R5 receipts. It checks accidental integrity and reproducibility of the declared configuration, and summarizes whether the direction of the measured *within-session median paired improvements* appears consistently positive, negative, or mixed.

Three different hashes or filenames do **not** prove independent runs, different days, different hardware, correct measurements, or trustworthiness. R5 receipts have no trusted timestamp, so R6 does not invent one and sorts sessions by receipt hash rather than pretending to preserve chronology.

## Quick start: Windows or Linux

From an installed PhiOS Python 3.11+ environment, choose **one non-sensitive, trusted local file** of 64 KiB–64 MiB. Select a fixed configuration and keep it constant for all sessions.

On Windows in **Command Prompt** (not legacy PowerShell 5.1 UTF-16 redirection):

```bat
python -m phios.elastic_residency_r5 --file "C:\Temp\phios-test.bin" --pairs 6 --windows 16 --window-bytes 4096 --environment-id operator-local > r5-session-01.json
python -m phios.elastic_residency_r5 --file "C:\Temp\phios-test.bin" --pairs 6 --windows 16 --window-bytes 4096 --environment-id operator-local > r5-session-02.json
python -m phios.elastic_residency_r5 --file "C:\Temp\phios-test.bin" --pairs 6 --windows 16 --window-bytes 4096 --environment-id operator-local > r5-session-03.json

python -m phios.elastic_sessions_r6 --receipt r5-session-01.json --receipt r5-session-02.json --receipt r5-session-03.json
```

The named source file above is **an example path, not a file created by PhiOS**. The operator must supply the existing test file. On Linux/macOS, use local paths and normal UTF-8 shell redirection.

An ideal field study repeats this sequence under separately recorded, comparable conditions. Warm-cache effects remain in all R5 sessions. This tool performs no cache flush, sleep, process control, filesystem mutation, GPU query or network calls.

## Validation contract

R6 accepts **only exact** `phios.elastic.residency-study.v1` shapes. It refuses:

- Missing, malformed, duplicate, oversized or symlinked receipt files
- Modified/tampered self-report digest or an inconsistent nested R4/R3 trace
- Any unsupported authority, provenance, claim of proven improvement, or status
- Incorrect file size, window size or selected-byte arithmetic
- Different declared environment, source/workload SHA-256 or window configuration across receipts
- Repeated identical receipt hashes, which cannot represent additional evidence
- Any R5 result that was not already `REVIEW_REQUIRED`

The review re-runs R4 conversion and R3 comparison on each embedded R5 trace rather than trusting nested summary numbers. Each receipt is bounded to 256 KiB and there are at most 12 input files.

## Output interpretation

`phios.elastic.session-review.v1` contains per-session R5 digests, pair counts, win/tie/loss counts, median paired percentage improvements, and a median/range across those session medians. It reports `all_positive`, `all_negative`, `all_zero` or `mixed` **only as descriptive direction**. Do not equate `all_positive` with statistical significance or a worthwhile real-world speedup.

The tool never exports local receipt file paths or raw source-file content. However, R5's self-declared workload hash and resource estimates are included, so review output before public sharing.

The following flags are permanently false:

```text
independent_sessions_verified
host_provenance_authenticated
cold_cache_measured
performance_improvement_proven
action_authority
execution_authority
hardware_control
```

A structurally valid report exits 0 with `REVIEW_REQUIRED`. Invalid or incomparable evidence exits 2 with a minimal `UNAVAILABLE` JSON response. **Exit 0 never means permission to tune the host.**

## Test and future gate

```bash
python -m pytest -q tests/test_elastic_sessions_r6.py
```

Tests generate disposable data locally, then deliberately construct synthetic session variations to test correctness gates. They do not attest three independent real machine sessions.

**R7 evidence gate:** obtain real R5 runs under separately recorded conditions, inspect distribution and noise, then consider an explicitly approved PhiStream real-model pilot with matching model hash, outputs, token throughput, transfer overhead and VRAM residency. Do not implement automated resource eviction or infer that filesystem mmap wins guarantee useful weight streaming.
