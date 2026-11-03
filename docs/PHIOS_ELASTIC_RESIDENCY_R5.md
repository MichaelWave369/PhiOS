# PhiOS Elastic Runtime R5: read-only sparse file residency pilot

**Status:** Local opt-in research alpha. This is a real I/O *measurement mechanism*, not proof of improved PhiOS, PhiStream, model inference, VR performance, or any generalized advantage for memory mapping.

## Engineering question

For an explicitly selected, small local regular file, how does a baseline that **eagerly reads the whole file** compare with a candidate that uses **read-only memory mapping to retrieve selected windows** when both must return *exactly the same selected bytes*?

This isolates a useful model-weight residency analogy: loading a complete artifact vs retrieving a sparse subset. It does **not** model neural decoding, KV caches, VRAM residency, shader compilation, or a multi-layer weight streaming pipeline. mmap performance can vary by operating system, storage device, page cache, filesystem, and access pattern. Neither arm unloads a driver or changes the OS.

## Run on a trusted local test file

Use a PhiOS Python 3.11+ environment from the repository root. This command reads the selected file and prints the observation receipt to stdout.

```bash
python -m phios.elastic_residency_r5 --file "/path/to/trusted-test-data.bin" --pairs 6 --windows 16 --window-bytes 4096
python -m pytest -q tests/test_elastic_residency_r5.py
```

**No third-party weights or datasets are shipped.** Use a deliberately selected, non-sensitive test file of **at least 64 KiB and at most 64 MiB** for default parameters. The CLI rejects symlinks, directories, missing files, and files exceeding 64 MiB. Input is read only; the CLI does not write, install dependencies, start services, send telemetry, or attempt to manage resources.

Output goes to stdout. To save results, redirect to an operator-chosen local JSON file; do not post raw receipts publicly without checking whether the content fingerprint and environment label are sensitive.

## Experimental protocol

1. Open a manually chosen file in read-only mode; confirm it is a bounded regular file.
2. Hash the file and the selected access pattern to bind a self-declared `workload_sha256` (no filename recorded).
3. Select 2–64 fixed, evenly spaced **nonoverlapping** windows of 1–65536 bytes each.
4. Compute an **untimed reference digest** of the selected windows.
5. Execute 6–16 alternating **AB/BA** matched pairs, where **A is eager full-file read plus hashing the selected windows**, and **B is read-only mmap of the file plus hashing exactly those same windows**. Every arm returns its digest, which must match the reference. Times are measured in integer microseconds via R4 `measure_call`.
6. Check source-file metadata and SHA-256 again after all trials. Refuse results if source content or metadata changed.
7. Pass the actual microsecond timings through the R4 trace converter and R3 paired descriptive comparison.

Every report records the selected-window byte count, full-file size, raw paired timings, trace, R3 review, and a self-binding receipt digest. It does **not** record the source filename, raw file content, user identity, system credentials, or process lists.

The run only compares **one specific file, sparse access pattern, and warm-cache conditions**. Preflight hashing loads the file into the OS cache before timing, so it is *not a cold disk fetch*. An eager read and an mmap may have different memory-copy costs as well as page-fault behavior; the study does not isolate those effects. Timing noise, cache state, power management, and filesystem variation can dominate.

This is also **not an authorized background benchmark**. It runs only when the operator issues the CLI invocation.

## Safety and validity

- `REVIEW_REQUIRED` means structural and content checks succeeded; it does **not** mean the candidate is faster.
- An input, resource, or byte-integrity failure is `UNAVAILABLE` (exit 2); no fabricated measurement is emitted.
- A self-reported SHA-256 digest is useful for accidental-integrity checking, **not independent provenance**.
- `improvement_proven`, action authority, execution authority, and hardware control remain **false**.
- Results are not used to activate R1 bubble plans, tune GPU clocks, allocate VRAM, or unload kernel modules.
- The Python tests use disposable local files. GitHub Actions must not access operator datasets or perform live hardware benchmarking.

## Next meaningful validation

Run matched tests on the operator's system with a disposable file and repeat them across several sessions. Then move to a separately approved PhiStream adapter that benchmarks **genuine model layers, same model/outputs, actual first-token time and generation throughput**, including memory use and transfer cost. An mmap win on a sparse test file is not a reason to deploy a live weight pager.

**Design law:** a green CI run tests implementation safety and shape. Only real matched experiments with correctness and uncertainty checks can support performance claims.
