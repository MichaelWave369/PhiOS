"""Bounded, no-network GitPorch bare mirror integrity observation.

The operator names one trusted local bare mirror. Git runs fixed read-only
commands and receives no repo-supplied script, hook or remote URL argument.
This does NOT restore a backup, verify LFS, run builds or certify offline use.
"""
from __future__ import annotations

import os
import re
import stat
import subprocess
from pathlib import Path
from typing import Any

SCHEMA = "phios.git_mirror_observation.v0.1"
_TIMEOUT_SECONDS = 60
_SHA = re.compile(r"(?:[0-9a-f]{40}|[0-9a-f]{64})")


def _report(status: str, head: str | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "status": status,
        "headCommit": head,
        "bareMirror": status == "OBJECTS_VERIFIED",
        "objectIntegrityPassed": status == "OBJECTS_VERIFIED",
        "remoteFetchPerformed": False,
        "backupRestored": False,
        "lfsObjectsVerified": False,
        "submodulesVerified": False,
        "offlineNetworkStateVerified": False,
        "machineIdentityVerified": False,
        "effectAuthority": False,
    }


def _real_directory(path: Path) -> bool:
    try:
        return stat.S_ISDIR(path.lstat().st_mode)
    except OSError:
        return False


def _real_file(path: Path) -> bool:
    try:
        return stat.S_ISREG(path.lstat().st_mode)
    except OSError:
        return False


def _safe_local_layout(path: Path) -> bool:
    # Deny symlinked parents as well as the mirror itself. Refuse partial,
    # shallow, or alternate object stores whose completeness is not proven.
    if not all(_real_directory(p) for p in (path, *path.parents)):
        return False
    if not all(_real_directory(path / x) for x in ("objects", "refs")):
        return False
    if not all(_real_file(path / x) for x in ("HEAD", "config")):
        return False
    if any((path / x).exists() or (path / x).is_symlink()
           for x in ("shallow", "objects/info/alternates")):
        return False
    try:
        pack = path / "objects" / "pack"
        if pack.exists() and (
            not _real_directory(pack) or
            any(x.name.endswith(".promisor") or x.is_symlink() for x in pack.iterdir())
        ):
            return False
    except OSError:
        return False
    return True


def _git_env() -> dict[str, str]:
    # Explicitly drop any inherited GIT_DIR, remote helpers, alternate object
    # dirs, custom configs or credentials. Windows Git needs SystemRoot.
    result = {
        "PATH": os.environ.get("PATH", ""),
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_SYSTEM": os.devnull,
        "GIT_NO_LAZY_FETCH": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_LFS_SKIP_SMUDGE": "1",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if "SystemRoot" in os.environ:
        result["SystemRoot"] = os.environ["SystemRoot"]
    return result


def _run_git(root: Path, args: list[str], *, capture: bool = False) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", "--git-dir=" + str(root), *args],
        check=False, stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=_TIMEOUT_SECONDS,
        env=_git_env(),
    )


def observe_git_mirror(directory: str | Path) -> dict[str, Any]:
    """Check an existing bare mirror. No writes, network, or shell execution."""
    if not isinstance(directory, (str, Path)) or not str(directory).strip():
        raise ValueError("Absolute Git mirror directory required")
    root = Path(directory)
    if not root.is_absolute():
        raise ValueError("Absolute Git mirror directory required")
    if not root.exists() and not root.is_symlink():
        return _report("NOT_FOUND")
    if not _safe_local_layout(root):
        return _report("INVALID_LAYOUT")
    try:
        bare = _run_git(root, ["rev-parse", "--is-bare-repository"], capture=True)
        if bare.returncode != 0 or bare.stdout.strip() != b"true":
            return _report("NOT_BARE")
        # Refuse repositories with incomplete shallow history.
        shallow = _run_git(root, ["rev-parse", "--is-shallow-repository"], capture=True)
        if shallow.returncode != 0 or shallow.stdout.strip() != b"false":
            return _report("INVALID_LAYOUT")
        commit = _run_git(root, ["rev-parse", "--verify", "HEAD^{commit}"], capture=True)
        if commit.returncode != 0 or not _SHA.fullmatch(commit.stdout.decode("ascii").strip()):
            return _report("EMPTY_OR_UNBORN")
        head = commit.stdout.decode("ascii").strip()
        integrity = _run_git(root, ["fsck", "--full", "--strict", "--no-reflogs"])
        if integrity.returncode != 0:
            return _report("INTEGRITY_FAILED")
        return _report("OBJECTS_VERIFIED", head)
    except FileNotFoundError:
        return _report("GIT_UNAVAILABLE")
    except subprocess.TimeoutExpired:
        return _report("TIMEOUT")
    except (OSError, UnicodeError, ValueError):
        return _report("CHECK_FAILED")
