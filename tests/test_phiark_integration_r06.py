"""PhiARK R0.6 local observation tests. No remote network, no runtime execution."""
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from phios.apps.cli import main as phi_app_main
from phios.apps.manifest import AppManifest
from phios.apps.phiark_bridge import KIWIX, observe_phiark


def make_vault(root: Path, *, text: bytes = b"# Offline knowledge\n") -> str:
    root.mkdir()
    digest = hashlib.sha256(text).hexdigest()
    (root / "objects").mkdir()
    (root / "objects" / digest).write_bytes(text)
    (root / "catalog.json").write_text(json.dumps([{
        "id": digest, "title": "Knowledge", "bytes": len(text),
        "extension": ".md", "reviewStatus": "unreviewed",
    }]), encoding="utf-8")
    return digest


def test_zero_data_is_honestly_not_installed(tmp_path: Path) -> None:
    result = observe_phiark(tmp_path / "no-vault")
    assert result["status"] == "BLOCKED"
    assert result["issues"]
    assert result["catalog"]["hash_verified"] == 0
    assert result["loopback"]["status"] == "NOT_PROBED"
    assert not result["install_authority"] and not result["launch_authority"]


def test_real_content_hash_matches_and_never_approves_content(tmp_path: Path) -> None:
    make_vault(tmp_path / "vault")
    report = observe_phiark(tmp_path / "vault")
    assert report["status"] == "LOCAL_BYTES_OBSERVED"
    assert report["catalog"]["hash_verified"] == 1
    assert report["catalog"]["status"] == "BYTES_MATCHED"
    assert not report["content_review_verified"]
    assert not report["source_commit_attested"]
    assert not report["network_authority"]
    assert not report["data_mutation_authority"]


def test_missing_and_modified_documents_cannot_pass(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    digest = make_vault(root)
    (root / "objects" / digest).write_text("modification")
    bad = observe_phiark(root)
    assert bad["status"] == "BLOCKED"
    assert bad["catalog"]["failed"] == 1
    (root / "objects" / digest).unlink()
    missing = observe_phiark(root)
    assert missing["catalog"]["hash_verified"] == 0
    assert missing["status"] == "BLOCKED"


def test_symlinked_data_root_catalog_and_object_block(tmp_path: Path) -> None:
    original = tmp_path / "original"
    digest = make_vault(original)
    link = tmp_path / "redirected"
    link.symlink_to(original, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        observe_phiark(link)
    cat = original / "catalog.json"
    content = cat.read_bytes()
    cat.unlink()
    other = tmp_path / "external-catalog.json"
    other.write_bytes(content)
    cat.symlink_to(other)
    assert observe_phiark(original)["status"] == "BLOCKED"
    cat.unlink()
    cat.write_bytes(content)
    obj = original / "objects" / digest
    obj.unlink()
    obj.symlink_to(other)
    assert observe_phiark(original)["catalog"]["failed"] == 1


def test_kiwix_is_optional_and_hashes_saved_archive_bytes(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    make_vault(root)
    before = observe_phiark(root)
    assert before["kiwix"]["status"] == "NOT_SCANNED"
    folder = root / "kiwix" / "installed" / "chemistry"
    folder.mkdir(parents=True)
    filename = KIWIX["chemistry"]
    data = b"synthetic test ZIM bytes, not actual indexed articles"
    sha = hashlib.sha256(data).hexdigest()
    (folder / filename).write_bytes(data)
    (folder / (filename + ".sha256")).write_text(sha + "  " + filename + "\n")
    (folder / "receipt.json").write_text(json.dumps({
        "schema": "phiark-kiwix-intake-v1", "id": "chemistry",
        "filename": filename, "bytes": len(data), "sha256": sha,
    }))
    valid = observe_phiark(root, verify_kiwix=True)
    assert valid["kiwix"]["checksum_matched"] == 1
    assert valid["kiwix"]["failed"] == 0
    assert not valid["kiwix"]["rights_approved"]
    (folder / filename).write_bytes(b"bad")
    invalid = observe_phiark(root, verify_kiwix=True)
    assert invalid["status"] == "BLOCKED"
    assert invalid["kiwix"]["failed"] == 1


def test_opt_in_loopback_probe_remains_non_authoritative(tmp_path: Path) -> None:
    root = tmp_path / "vault"
    make_vault(root)
    with patch("phios.apps.phiark_bridge._probe", return_value={
        "status": "LOCAL_HTTP_OBSERVED", "reported_documents": 1,
        "process_identity_attested": False,
    }) as probe:
        assert observe_phiark(root)["loopback"]["status"] == "NOT_PROBED"
        assert probe.call_count == 0
        observed = observe_phiark(root, probe_loopback=True)
    assert probe.call_count == 1
    assert observed["loopback"]["status"] == "LOCAL_HTTP_OBSERVED"
    assert not observed["loopback"]["process_identity_attested"]
    assert not observed["launch_authority"]


def test_cli_outputs_observation_and_nonzero_missing_status(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "vault"
    make_vault(root)
    assert phi_app_main(["phiark-status", "--data-root", str(root)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["schema"] == "phios.phiark_observation.v0.1"
    assert report["status"] == "LOCAL_BYTES_OBSERVED"
    assert phi_app_main(["phiark-status", "--data-root", str(tmp_path / "absent")]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "BLOCKED"


def test_declared_compatibility_manifest_is_a_candidate_not_a_grant() -> None:
    candidate = json.loads((Path(__file__).parents[1] / "integrations" / "phiark" /
                            "manifest-candidate.json").read_text(encoding="utf-8"))
    manifest = AppManifest.from_dict(candidate)
    assert manifest.app_id == "phi.phiark"
    assert manifest.entrypoint.runtime == "node"
    assert manifest.entrypoint.target == "src/server.mjs"
    assert "runtime.network.inherit" not in manifest.permissions
    assert manifest.permissions == ("runtime.data.persist",)
    assert manifest.source.redistribution == "unknown"


def test_r08_source_pin_is_non_authoritative_and_tracks_exact_observed_commit() -> None:
    import re
    base = Path(__file__).parents[1] / "integrations" / "phiark"
    review = json.loads((base / "r08-install-review-candidate.json").read_text(encoding="utf-8"))
    manifest = AppManifest.from_dict(
        json.loads((base / "manifest-candidate.json").read_text(encoding="utf-8"))
    )
    assert review["schema"] == "phios.phiark_install_review.v0.1"
    assert review["status"] == "HELD_FOR_OPERATOR_REVIEW"
    assert review["app_id"] == manifest.app_id
    assert review["repository_url"] == manifest.source.repository_url
    assert re.fullmatch("[a-f0-9]{40}", review["observed_source_commit"])
    assert review["requested_network_mode"] == "deny"
    assert review["requested_permissions"] == list(manifest.permissions)
    assert "runtime.network.inherit" not in manifest.permissions
    assert review["required_guest_environment"] == {
        "PHIARK_DATA_DIR": "/phios/app-data",
        "PHIARK_SOCKET_PATH": "/phios/app-data/.phiark.sock",
    }
    assert review["open_blockers"]
    assert all(not value for key, value in review.items() if key.endswith(("_verified", "_attested", "_authority")))
