"""GitPorch R1.3 read-only mirror checking, integrated with PhiOS foundation."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from phios.foundation_cli import main as foundation_cli
from phios.foundation_status import observe_foundation
from phios.git_mirror_observer import observe_git_mirror


def git(*args: str) -> None:
    subprocess.run(
        ["git", *args], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        timeout=20,
    )


@pytest.fixture
def mirror(tmp_path: Path) -> Path:
    if not shutil.which("git"):
        pytest.skip("Git executable unavailable on runner")
    work = tmp_path / "work"
    bare = tmp_path / "GitPorch" / "data" / "repos" / "PhiOS.git"
    bare.parent.mkdir(parents=True)
    git("init", "--initial-branch=main", str(work))
    git("-C", str(work), "config", "user.email", "field@example.invalid")
    git("-C", str(work), "config", "user.name", "Field Fixture")
    (work / "README.md").write_text("Local-only proof bytes\n", encoding="utf-8")
    git("-C", str(work), "add", "README.md")
    git("-C", str(work), "commit", "-m", "field test")
    git("clone", "--mirror", str(work), str(bare))
    return bare


def test_existing_real_bare_mirror_objects_checked(mirror: Path) -> None:
    result = observe_git_mirror(mirror)
    assert result["status"] == "OBJECTS_VERIFIED"
    assert result["bareMirror"] is True
    assert result["objectIntegrityPassed"] is True
    assert result["remoteFetchPerformed"] is False
    assert result["backupRestored"] is False
    assert result["lfsObjectsVerified"] is False
    assert len(result["headCommit"]) in (40, 64)
    assert str(mirror) not in json.dumps(result)


def test_foundation_composes_git_and_phiark_without_offline_promotion(
    tmp_path: Path, mirror: Path,
) -> None:
    vault = tmp_path / "vault"
    vault.mkdir()
    (vault / "objects").mkdir()
    body = b"# Offline field guide\n"
    digest = hashlib.sha256(body).hexdigest()
    (vault / "objects" / digest).write_bytes(body)
    (vault / "catalog.json").write_text(json.dumps([{
        "id": digest, "bytes": len(body), "title": "Guide",
        "extension": ".md", "reviewStatus": "unreviewed",
    }]), encoding="utf-8")
    with patch("phios.network.homenode.probe_gateway", side_effect=AssertionError("network")):
        report = observe_foundation(
            mode="offline", git_mirror=mirror, phiark_data_root=vault, env={},
        )
    assert report["status"] == "PARTIAL_EVIDENCE"
    assert report["gitMirror"]["status"] == "OBJECTS_VERIFIED"
    assert report["phiark"]["documentsHashVerified"] == 1
    assert report["homenode"]["gatewayVerified"] is False
    assert report["acceptance"]["gitMirrorRestoredOffline"] is False
    assert report["acceptance"]["offlineReady"] is False
    assert report["authority"]["gitPush"] is False
    assert str(vault) not in json.dumps(report)
    assert str(mirror) not in json.dumps(report)


def test_absent_and_empty_git_repos_fail_closed(tmp_path: Path) -> None:
    assert observe_git_mirror(tmp_path / "missing")["status"] == "NOT_FOUND"
    empty = tmp_path / "empty.git"
    if not shutil.which("git"):
        pytest.skip("Git executable unavailable")
    git("init", "--bare", str(empty))
    assert observe_git_mirror(empty)["status"] == "EMPTY_OR_UNBORN"
    result = observe_foundation(mode="offline", git_mirror=empty, env={})
    assert result["status"] == "BLOCKED"
    assert result["acceptance"]["offlineReady"] is False


def test_symlinked_mirror_and_critical_layout_rejected(
    tmp_path: Path, mirror: Path,
) -> None:
    link = tmp_path / "point-to-mirror.git"
    try:
        link.symlink_to(mirror, target_is_directory=True)
    except (NotImplementedError, OSError):
        pytest.skip("Symlink not permitted on this host")
    assert observe_git_mirror(link)["status"] == "INVALID_LAYOUT"
    # Even if a parent is replaced by a redirect, the helper rejects it.
    (mirror / "objects" / "info" / "alternates").parent.mkdir(exist_ok=True)
    (mirror / "objects" / "info" / "alternates").write_text("/other/path\n")
    assert observe_git_mirror(mirror)["status"] == "INVALID_LAYOUT"


def test_corruption_does_not_result_in_verified_mirror(mirror: Path) -> None:
    loose = [p for p in (mirror / "objects").glob("*/*")
             if p.is_file() and len(p.parent.name) == 2]
    if loose:
        loose[0].write_bytes(b"corrupted")
    else:
        packs = list((mirror / "objects" / "pack").glob("*.pack"))
        assert packs
        original = packs[0].read_bytes()
        packs[0].write_bytes(b"BAD!" + original[4:])
    failed = observe_git_mirror(mirror)
    assert failed["objectIntegrityPassed"] is False
    assert failed["status"] != "OBJECTS_VERIFIED"


def test_fixed_git_commands_only_no_remote_fetch(mirror: Path) -> None:
    from phios import git_mirror_observer as observer
    original = observer._run_git
    calls: list[list[str]] = []

    def checked(root: Path, args: list[str], *, capture: bool = False):
        assert root == mirror
        assert args[0] in ("rev-parse", "fsck")
        assert all("fetch" not in a and "push" not in a for a in args)
        calls.append(args)
        return original(root, args, capture=capture)

    with patch.object(observer, "_run_git", side_effect=checked):
        report = observe_git_mirror(mirror)
    assert report["status"] == "OBJECTS_VERIFIED"
    assert calls == [
        ["rev-parse", "--is-bare-repository"],
        ["rev-parse", "--is-shallow-repository"],
        ["rev-parse", "--verify", "HEAD^{commit}"],
        ["fsck", "--full", "--strict", "--no-reflogs"],
    ]


def test_cli_and_invalid_arguments_are_sanitized(
    tmp_path: Path, mirror: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    assert foundation_cli(["status", "--mode", "offline", "--git-mirror", str(mirror)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["gitMirror"]["objectIntegrityPassed"] is True
    assert data["acceptance"]["offlineReady"] is False
    assert str(mirror) not in json.dumps(data)
    assert foundation_cli(["status", "--git-mirror", "./not-absolute"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSED"
    with patch("phios.foundation_status.select_mode", side_effect=AssertionError("network")):
        with pytest.raises(ValueError):
            observe_foundation(git_mirror="./not-absolute")
