from __future__ import annotations

import multiprocessing
import queue
from pathlib import Path

from phios.reflex.coordination import CrossProcessFileLock


def _child_lock(path_text: str, ready, acquired) -> None:
    lock = CrossProcessFileLock(Path(path_text))
    ready.set()
    with lock:
        acquired.put("acquired")


def test_cross_process_file_lock_serializes_two_processes(tmp_path):
    lock_path = tmp_path / "control.lock"
    parent_lock = CrossProcessFileLock(lock_path)
    ready = multiprocessing.Event()
    acquired = multiprocessing.Queue()

    with parent_lock:
        process = multiprocessing.Process(
            target=_child_lock,
            args=(str(lock_path), ready, acquired),
        )
        process.start()
        assert ready.wait(timeout=5)
        try:
            acquired.get(timeout=0.2)
            blocked = False
        except queue.Empty:
            blocked = True
        assert blocked is True

    assert acquired.get(timeout=5) == "acquired"
    process.join(timeout=5)
    assert process.exitcode == 0


def test_file_lock_is_reentrant_per_instance(tmp_path):
    lock = CrossProcessFileLock(tmp_path / "control.lock")

    with lock:
        with lock:
            pass
