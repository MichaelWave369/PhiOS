"""Durable JSONL I/O; receipt content and authority remain caller-owned.

Writers serialize on the file inode, sync before acknowledging an append and
refuse corrupt/truncated history. Recovery is never an implicit read side effect.
"""
from __future__ import annotations

import json
import importlib
import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

MAX_RECORD_BYTES = 16 * 1024 * 1024


def sync_directory(path: Path) -> None:
    if os.name == "posix":
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


class StateIntegrityError(ValueError):
    """State is unsafe or incomplete; preserve it for explicit recovery."""


def _encode(payload: Mapping[str, Any]) -> bytes:
    data = (json.dumps(dict(payload), sort_keys=True, ensure_ascii=False,
                       allow_nan=False) + "\n").encode("utf-8")
    if len(data) > MAX_RECORD_BYTES:
        raise ValueError("state record exceeds 16 MiB")
    return data


def _object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise StateIntegrityError("duplicate JSON object key")
        result[key] = value
    return result


def _reject_constant(value: str) -> None:
    raise StateIntegrityError(f"non-finite JSON value: {value}")


def _prefix(handle: Any, *, preserve_tail: bool) -> tuple[list[dict[str, Any]], bytes]:
    handle.seek(0)
    result: list[dict[str, Any]] = []
    number = 0
    while line := handle.readline(MAX_RECORD_BYTES + 1):
        number += 1
        if len(line) > MAX_RECORD_BYTES:
            raise StateIntegrityError(f"oversize state record at line {number}")
        if not line.endswith(b"\n"):
            if preserve_tail:
                return result, line
            raise StateIntegrityError(f"incomplete state record at line {number}")
        try:
            row = json.loads(line, object_pairs_hook=_object, parse_constant=_reject_constant)
        except (ValueError, UnicodeError) as exc:
            raise StateIntegrityError(f"invalid state record at line {number}: {exc}") from exc
        if not isinstance(row, dict):
            raise StateIntegrityError(f"state record at line {number} must be an object")
        result.append(row)
    return result, b""


def _rows(handle: Any) -> list[dict[str, Any]]:
    return _prefix(handle, preserve_tail=False)[0]


@contextmanager
def _parent(path: Path, *, create: bool) -> Iterator[int | None]:
    """Walk POSIX parents without following symlinks, including ancestors."""
    if os.name != "posix":
        for ancestor in (path, *path.parents):
            if ancestor.is_symlink():
                raise StateIntegrityError("state paths cannot contain symlinks")
        if create:
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        yield None
        return
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
    parent = os.open(path.anchor, flags)
    try:
        for part in path.parts[1:-1]:
            if create:
                try:
                    os.mkdir(part, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                else:
                    os.fsync(parent)
            child = os.open(part, flags, dir_fd=parent)
            os.close(parent)
            parent = child
        yield parent
    finally:
        os.close(parent)


@contextmanager
def _locked(path: Path, *, write: bool) -> Iterator[tuple[Any, int | None]]:
    path = path.expanduser().absolute()
    with _parent(path, create=write) as parent:
        flags = os.O_RDWR if write or os.name == "nt" else os.O_RDONLY
        flags |= getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
        location: str | Path = path.name if parent is not None else path
        options = {"dir_fd": parent} if parent is not None else {}
        if write:
            try:
                fd = os.open(location, flags | os.O_CREAT | os.O_EXCL, 0o600, **options)
            except FileExistsError:
                fd = os.open(location, flags, **options)
        else:
            fd = os.open(location, flags, **options)
        with os.fdopen(fd, "r+b" if write or os.name == "nt" else "rb", buffering=0) as handle:
            info = os.fstat(handle.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                raise StateIntegrityError("state must be a regular file with one link")
            if os.name == "posix":
                if info.st_uid != os.getuid() or info.st_mode & 0o022:
                    raise StateIntegrityError("state owner or write permissions are unsafe")
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX if write else fcntl.LOCK_SH)
            else:
                msvcrt = importlib.import_module("msvcrt")
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            try:
                yield handle, parent
            finally:
                if os.name == "posix":
                    fcntl.flock(fd, fcntl.LOCK_UN)
                else:
                    handle.seek(0)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    try:
        with _locked(path, write=False) as (handle, _parent_fd):
            return _rows(handle)
    except FileNotFoundError:
        return []


def prepare_state_file(path: Path) -> None:
    """Create a private regular file or validate an existing owned file."""
    with _locked(path, write=True) as (handle, parent):
        os.fsync(handle.fileno())
        if parent is not None:
            os.fsync(parent)


def recoverable_jsonl_prefix(path: Path) -> tuple[list[dict[str, Any]], bytes]:
    """Read an intact prefix and a final incomplete row; never modify/replay it.

    Malformed complete rows still fail. Only explicit recovery tooling should
    call this, with the original bytes archived outside active runtime paths.
    """
    try:
        with _locked(path, write=False) as (handle, _parent_fd):
            return _prefix(handle, preserve_tail=True)
    except FileNotFoundError:
        return [], b""


def append_jsonl(
    path: Path, payload: Mapping[str, Any], *, identity_field: str | None = None,
) -> bool:
    data = _encode(payload)
    if identity_field is not None and not isinstance(payload.get(identity_field), str):
        raise ValueError("idempotent append requires a string identity")
    with _locked(path, write=True) as (handle, parent):
        history = _rows(handle)
        if identity_field is not None:
            matches = [row for row in history
                       if row.get(identity_field) == payload[identity_field]]
            if matches:
                if len(matches) != 1 or _encode(matches[0]) != data:
                    raise StateIntegrityError("receipt identity collision or duplicate history")
                return False
        handle.seek(0, os.SEEK_END)
        start = handle.tell()
        try:
            remaining = memoryview(data)
            while remaining:
                written = os.write(handle.fileno(), remaining)
                if written <= 0:
                    raise OSError("state write made no progress")
                remaining = remaining[written:]
            os.fsync(handle.fileno())
            if parent is not None:
                os.fsync(parent)
        except BaseException:
            # A caught I/O failure must not poison previously committed history.
            # A killed process cannot reach this cleanup; its incomplete tail is
            # instead detected and held by every later reader/writer.
            os.ftruncate(handle.fileno(), start)
            os.fsync(handle.fileno())
            raise
    return True
