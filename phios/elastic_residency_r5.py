"""PhiOS Elastic R5: explicit local, read-only sparse-file residency experiment.

Compares eager whole-file reading with memory-mapped sparse-window reading for
the SAME requested byte windows. This is not weight inference or OS scheduling.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import mmap
import os
import re
import stat
import sys
from pathlib import Path
from typing import BinaryIO, Sequence

from phios.elastic_trace import TraceError, convert_trace, measure_call

SCHEMA = "phios.elastic.residency-study.v1"
PROTOCOL = "phios-sparse-window-r5"
MAX_FILE_BYTES = 64 * 1024 * 1024
MIN_PAIRS = 6
MAX_PAIRS = 16
MIN_WINDOWS = 2
MAX_WINDOWS = 64
MAX_WINDOW_BYTES = 65536
_ID = re.compile(r"[a-z][a-z0-9._:-]{0,63}\Z")


class ResidencyError(ValueError):
    """The requested experiment is unsafe, incomparable, or unavailable."""


def _hash_json(value: object) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=True, allow_nan=False).encode("ascii")
    return hashlib.sha256(raw).hexdigest()


def _validate(pairs: int, windows: int, window_bytes: int, environment_id: str) -> None:
    if type(pairs) is not int or not MIN_PAIRS <= pairs <= MAX_PAIRS:
        raise ResidencyError("pairs must be between 6 and 16")
    if type(windows) is not int or not MIN_WINDOWS <= windows <= MAX_WINDOWS:
        raise ResidencyError("windows must be between 2 and 64")
    if type(window_bytes) is not int or not 1 <= window_bytes <= MAX_WINDOW_BYTES:
        raise ResidencyError("invalid window byte count")
    if not isinstance(environment_id, str) or not _ID.fullmatch(environment_id):
        raise ResidencyError("invalid environment id")


def _open_readonly(path: Path) -> BinaryIO:
    try:
        if path.is_symlink():
            raise ResidencyError("symlink input refused")
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        try:
            handle = os.fdopen(descriptor, "rb")
        except BaseException:
            os.close(descriptor)
            raise
    except OSError as exc:
        raise ResidencyError("input file unavailable") from exc
    info = os.fstat(handle.fileno())
    if not stat.S_ISREG(info.st_mode) or not 1 <= info.st_size <= MAX_FILE_BYTES:
        handle.close()
        raise ResidencyError("input must be a regular file of at most 64 MiB")
    return handle


def _digest_file(handle: BinaryIO) -> str:
    handle.seek(0)
    digest = hashlib.sha256()
    while True:
        block = handle.read(1024 * 1024)
        if not block:
            break
        digest.update(block)
    return digest.hexdigest()


def _sparse_digest(handle: BinaryIO, *, size: int, positions: tuple[int, ...],
                   window_bytes: int, mapped: bool) -> str:
    digest = hashlib.sha256()
    if mapped:
        with mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view:
            for start in positions:
                digest.update(view[start:start + window_bytes])
    else:
        handle.seek(0)
        full = handle.read(size + 1)
        if len(full) != size:
            raise ResidencyError("file changed during eager read")
        for start in positions:
            digest.update(full[start:start + window_bytes])
    return digest.hexdigest()


def benchmark(path: Path, *, pairs: int = 6, windows: int = 16,
              window_bytes: int = 4096, environment_id: str = "operator-local"
              ) -> dict[str, object]:
    """Benchmark one explicit file and convert real timings into R3/R4 evidence.

    Entire-file hashing before and after the trials warms the OS page cache.
    Results therefore do NOT represent cold storage, model inference, startup,
    GPU transfers, or any generalized PhiOS performance benefit.
    """
    _validate(pairs, windows, window_bytes, environment_id)
    with _open_readonly(path) as handle:
        before = os.fstat(handle.fileno())
        size = before.st_size
        if size < windows * window_bytes:
            raise ResidencyError("file too small for the requested nonoverlapping windows")
        step = (size - window_bytes) // (windows - 1)
        if step < window_bytes:
            raise ResidencyError("requested windows overlap")
        positions = tuple(index * step for index in range(windows))
        file_digest = _digest_file(handle)
        manifest = {
            "protocol": PROTOCOL, "file_sha256": file_digest,
            "size_bytes": size, "windows": windows, "window_bytes": window_bytes,
            "offsets": positions,
        }
        workload_sha256 = _hash_json(manifest)
        trace_pairs: list[dict[str, object]] = []
        for index in range(pairs):
            order = "AB" if index % 2 == 0 else "BA"
            arms: dict[str, dict[str, object]] = {}
            for arm in ("baseline", "candidate") if order == "AB" else ("candidate", "baseline"):
                is_mapped = arm == "candidate"
                result, duration_us = measure_call(
                    lambda: _sparse_digest(
                        handle, size=size, positions=positions,
                        window_bytes=window_bytes, mapped=is_mapped
                    )
                )
                arms[arm] = {"durations_us": [duration_us],
                             "passed": isinstance(result, str) and len(result) == 64,
                             "r2_receipt_sha256": None}
                # A digest mismatch is a correctness failure, not a faster run.
                if isinstance(result, str):
                    arms[arm]["passed"] = result == expected_digest(handle, positions,
                                                                     window_bytes)
                if not arms[arm]["passed"]:
                    raise ResidencyError("sparse-window content mismatch")
            trace_pairs.append({
                "pair_id": f"pair-{index + 1:02d}", "order": order,
                "baseline": arms["baseline"], "candidate": arms["candidate"],
            })
        after = os.fstat(handle.fileno())
        if ((before.st_size, before.st_mtime_ns, before.st_ctime_ns) !=
                (after.st_size, after.st_mtime_ns, after.st_ctime_ns)):
            raise ResidencyError("source file metadata changed during benchmark")
        if _digest_file(handle) != file_digest:
            raise ResidencyError("source file contents changed during benchmark")

    trace = {
        "schema_version": "phios.elastic.trace-study.v1",
        "experiment": {
            "scenario": "residency-sparse-read",
            "environment_id": environment_id,
            "workload_sha256": workload_sha256,
            "protocol_id": PROTOCOL,
            "metric": "task_elapsed_ms",
            "declared_source": "operator_supplied_unverified",
        },
        "pairs": trace_pairs,
    }
    review = convert_trace(trace)
    report: dict[str, object] = {
        "schema_version": SCHEMA,
        "status": review["status"],
        "study": "eager_full_file_vs_read_only_mmap_sparse_windows",
        "scope": "operator_local_unverified_warm_cache",
        "source_filename_recorded": False,
        "file_bytes": size,
        "windows": windows, "window_bytes": window_bytes,
        "per_arm_selected_bytes": windows * window_bytes,
        "baseline_whole_file_bytes_per_run": size,
        "candidate_selected_bytes_per_run": windows * window_bytes,
        "trace": trace,
        "comparison": review,
        "improvement_proven": False,
        "action_authority": False, "execution_authority": False,
        "hardware_control": False,
    }
    report["receipt_sha256"] = _hash_json(report)
    return report


def expected_digest(handle: BinaryIO, positions: tuple[int, ...],
                    window_bytes: int) -> str:
    """Untimed reference using direct reads; does not trust either measured arm."""
    digest = hashlib.sha256()
    for start in positions:
        handle.seek(start)
        data = handle.read(window_bytes)
        if len(data) != window_bytes:
            raise ResidencyError("file changed during correctness verification")
        digest.update(data)
    return digest.hexdigest()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="PhiOS R5 manual sparse file residency benchmark")
    parser.add_argument("--file", required=True, type=Path,
                        help="explicitly selected local file; read only")
    parser.add_argument("--pairs", type=int, default=6)
    parser.add_argument("--windows", type=int, default=16)
    parser.add_argument("--window-bytes", type=int, default=4096)
    parser.add_argument("--environment-id", default="operator-local")
    args = parser.parse_args(argv)
    try:
        result = benchmark(args.file, pairs=args.pairs, windows=args.windows,
                           window_bytes=args.window_bytes,
                           environment_id=args.environment_id)
    except (OSError, ResidencyError, TraceError, RecursionError, OverflowError):
        print(json.dumps({"schema_version": SCHEMA, "status": "UNAVAILABLE",
                          "action_authority": False, "execution_authority": False},
                         sort_keys=True))
        return 2
    print(json.dumps(result, sort_keys=True, indent=2, allow_nan=False))
    return 0 if result["status"] == "REVIEW_REQUIRED" else 3


if __name__ == "__main__":
    sys.exit(main())
