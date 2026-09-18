from __future__ import annotations

import hashlib
import os
import stat
from dataclasses import dataclass
from pathlib import Path


DEFAULT_TEXT_SUFFIXES = (
    ".txt",
    ".md",
    ".json",
    ".csv",
    ".yaml",
    ".yml",
    ".toml",
    ".py",
    ".log",
)


class FileAcquisitionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True, kw_only=True)
class FileSourcePolicy:
    root: Path
    max_bytes: int = 1_048_576
    allowed_suffixes: tuple[str, ...] = DEFAULT_TEXT_SUFFIXES

    def root_ref(self) -> str:
        normalized = self.root.expanduser().resolve(strict=False)
        digest = hashlib.sha256(str(normalized).encode("utf-8")).hexdigest()
        return f"source-root:sha256:{digest}"


@dataclass(frozen=True, kw_only=True)
class AcquiredFile:
    relative_path: str
    data: bytes
    media_type: str
    suffix: str
    size_bytes: int


_MEDIA_TYPES = {
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/markdown; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".csv": "text/csv; charset=utf-8",
    ".yaml": "application/yaml; charset=utf-8",
    ".yml": "application/yaml; charset=utf-8",
    ".toml": "application/toml; charset=utf-8",
    ".py": "text/x-python; charset=utf-8",
    ".log": "text/plain; charset=utf-8",
}


class BoundedTextFileAdapter:
    """Read one bounded text-like file beneath an explicit source root."""

    def __init__(self, policy: FileSourcePolicy) -> None:
        if policy.max_bytes <= 0:
            raise ValueError("max_bytes must be positive")
        self.policy = policy

    def acquire(self, relative_path: str) -> AcquiredFile:
        requested = Path(relative_path)
        if not relative_path.strip():
            raise FileAcquisitionError("empty_path", "relative path must not be empty")
        if requested.is_absolute():
            raise FileAcquisitionError(
                "absolute_path_disallowed",
                "file acquisition requires a path relative to the configured root",
            )
        if ".." in requested.parts:
            raise FileAcquisitionError(
                "parent_traversal_disallowed",
                "parent traversal is not allowed",
            )

        try:
            root = self.policy.root.expanduser().resolve(strict=True)
        except OSError as exc:
            raise FileAcquisitionError(
                "source_root_unavailable",
                "source root is unavailable",
            ) from exc

        if not root.is_dir():
            raise FileAcquisitionError("source_root_not_directory", "source root is not a directory")

        cursor = root
        for part in requested.parts:
            cursor = cursor / part
            try:
                if cursor.is_symlink():
                    raise FileAcquisitionError(
                        "symlink_disallowed",
                        "symlinked source paths are not allowed",
                    )
            except OSError as exc:
                raise FileAcquisitionError(
                    "source_path_unavailable",
                    "source path could not be inspected",
                ) from exc

        candidate = root / requested
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise FileAcquisitionError("source_not_found", "source file is unavailable") from exc

        if not resolved.is_relative_to(root):
            raise FileAcquisitionError(
                "outside_source_root",
                "resolved source escaped the configured root",
            )

        suffix = resolved.suffix.lower()
        if suffix not in self.policy.allowed_suffixes:
            raise FileAcquisitionError(
                "unsupported_media_type",
                f"file suffix {suffix or '<none>'} is not allowed",
            )

        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(resolved, flags)
        except OSError as exc:
            raise FileAcquisitionError("source_open_failed", "source file could not be opened") from exc

        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode):
                raise FileAcquisitionError(
                    "source_not_regular_file",
                    "source must be a regular file",
                )
            if info.st_size > self.policy.max_bytes:
                raise FileAcquisitionError(
                    "source_too_large",
                    f"source exceeds max_bytes={self.policy.max_bytes}",
                )

            remaining = self.policy.max_bytes + 1
            chunks: list[bytes] = []
            while remaining > 0:
                chunk = os.read(fd, min(64 * 1024, remaining))
                if not chunk:
                    break
                chunks.append(chunk)
                remaining -= len(chunk)
            data = b"".join(chunks)
            if len(data) > self.policy.max_bytes:
                raise FileAcquisitionError(
                    "source_too_large",
                    f"source exceeds max_bytes={self.policy.max_bytes}",
                )
        finally:
            os.close(fd)

        return AcquiredFile(
            relative_path=requested.as_posix(),
            data=data,
            media_type=_MEDIA_TYPES[suffix],
            suffix=suffix,
            size_bytes=len(data),
        )
