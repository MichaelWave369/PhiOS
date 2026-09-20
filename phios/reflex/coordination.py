"""Cross-process coordination primitives for governed PhiReflex state."""

from __future__ import annotations

import os
from functools import wraps
from pathlib import Path
from typing import Any, Callable, ParamSpec, TypeVar


class ReflexCoordinationError(RuntimeError):
    """Raised when the local runtime coordination lock cannot be used."""


class CrossProcessFileLock:
    """Re-entrant per-instance advisory lock backed by the host OS."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._depth = 0
        self._handle: Any | None = None

    def __enter__(self) -> "CrossProcessFileLock":
        if self._depth > 0:
            self._depth += 1
            return self

        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                    os.fsync(handle.fileno())
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
            elif os.name == "posix":
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            else:
                raise ReflexCoordinationError(
                    f"unsupported platform for runtime locking: {os.name}"
                )
        except Exception:
            handle.close()
            raise

        self._handle = handle
        self._depth = 1
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._depth <= 0:
            raise ReflexCoordinationError("runtime lock released without acquire")
        self._depth -= 1
        if self._depth:
            return

        handle = self._handle
        self._handle = None
        if handle is None:
            raise ReflexCoordinationError("runtime lock handle missing")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            elif os.name == "posix":
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


P = ParamSpec("P")
R = TypeVar("R")


def runtime_locked(method: Callable[P, R]) -> Callable[P, R]:
    """Serialize a ReflexRuntimeControlPlane public operation."""

    @wraps(method)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        if not args:
            raise ReflexCoordinationError("runtime_locked method missing self")
        instance = args[0]
        lock = getattr(instance, "_runtime_lock", None)
        if not isinstance(lock, CrossProcessFileLock):
            raise ReflexCoordinationError("runtime control lock is unavailable")
        with lock:
            return method(*args, **kwargs)

    return wrapper
