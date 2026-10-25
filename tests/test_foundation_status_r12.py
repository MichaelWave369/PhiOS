"""R1.2 integration tests: two existing modules, no secret or field-proof laundering."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from phios.foundation_cli import main
from phios.foundation_status import SCHEMA, observe_foundation


def make_phiark_vault(root: Path) -> None:
    body = b"# Field reference\n"
    root.mkdir()
    (root / "objects").mkdir()
    digest = hashlib.sha256(body).hexdigest()
    (root / "objects" / digest).write_bytes(body)
    (root / "catalog.json").write_text(json.dumps([{
        "id": digest, "bytes": len(body), "title": "Field reference",
        "extension": ".md", "reviewStatus": "unreviewed"
    }]), encoding="utf-8")


def test_default_observation_is_offline_network_silent_and_unverified() -> None:
    with patch("phios.network.homenode.probe_gateway", side_effect=AssertionError("network")):
        with patch("phios.apps.phiark_bridge._probe", side_effect=AssertionError("network")):
            report = observe_foundation(env={})
    assert report["schema"] == SCHEMA
    assert report["mode"] == "OFFLINE"
    assert report["status"] == "UNVERIFIED"
    assert report["homenode"]["status"] == "OFFLINE_SELECTED_NOT_VERIFIED"
    assert report["phiark"]["status"] == "NOT_REQUESTED"
    assert report["porch"]["identityVerified"] is False
    assert report["acceptance"]["offlineReady"] is False
    assert all(flag is False for flag in report["authority"].values())


def test_public_mode_does_not_probe_gateway_or_filesystem() -> None:
    with patch("phios.network.homenode.probe_gateway", side_effect=AssertionError("network")):
        report = observe_foundation(mode="public", env={"PHIOS_HOMENODE_TOKEN_FILE": "SECRET"})
    assert report["homenode"]["status"] == "PUBLIC_SELECTED_NOT_PROBED"
    assert "SECRET" not in json.dumps(report)
    assert report["acceptance"]["offlineReady"] is False


def test_phiark_bytes_observed_are_partial_evidence_only(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_phiark_vault(vault)
    report = observe_foundation(phiark_data_root=vault, env={})
    assert report["status"] == "PARTIAL_EVIDENCE"
    assert report["phiark"]["documentsHashVerified"] == 1
    assert report["phiark"]["catalogStatus"] == "BYTES_MATCHED"
    assert report["phiark"]["archivesChecksumMatched"] == 0
    assert report["phiark"]["contentApproved"] is False
    assert report["acceptance"]["offlineReady"] is False
    assert str(vault) not in json.dumps(report)
    assert report["homenode"]["gatewayVerified"] is False


def test_corrupt_phiark_bytes_block_and_never_grant_authority(tmp_path: Path) -> None:
    vault = tmp_path / "vault"
    make_phiark_vault(vault)
    objects = list((vault / "objects").iterdir())
    objects[0].write_bytes(b"corrupt")
    report = observe_foundation(phiark_data_root=vault, env={})
    assert report["status"] == "BLOCKED"
    assert report["phiark"]["documentsFailed"] == 1
    assert report["phiark"]["launchAuthority"] is False


def test_requested_local_without_credentials_fails_closed() -> None:
    report = observe_foundation(mode="local", env={})
    assert report["status"] == "BLOCKED"
    assert report["homenode"]["effectiveMode"] == "OFFLINE"
    assert report["homenode"]["status"] == "LOCAL_FAILED_OFFLINE_MODE_SELECTED"
    assert report["homenode"]["failure"] == "LOCAL_CONFIGURATION_REQUIRED"
    assert report["acceptance"]["offlineReady"] is False


def test_valid_local_gateway_is_not_offline_readiness() -> None:
    expected = {
        "gatewayVerified": True,
        "requestedMode": "LOCAL",
        "effectiveMode": "LOCAL",
        "status": "LOCAL_GATEWAY_VERIFIED_ONLY",
        "capabilities": {"localGitStorage": True, "localSnapshots": True, "publicGitHubImport": True},
        "offlineServicesVerified": False,
        "actionAuthority": False,
    }
    with patch("phios.foundation_status.select_mode", return_value=expected) as probe:
        report = observe_foundation(mode="local")
    probe.assert_called_once()
    assert report["status"] == "PARTIAL_EVIDENCE"
    assert report["homenode"]["gatewayVerified"] is True
    assert report["acceptance"]["wanDisconnectedTested"] is False
    assert report["acceptance"]["offlineReady"] is False
    assert report["authority"]["gitPush"] is False


@pytest.mark.parametrize("kwargs", [
    {"mode": "auto"},
    {"verify_kiwix": True},
    {"probe_phiark_loopback": True},
    {"phiark_data_root": "./relative"},
    {"mode": "offline", "phiark_data_root": "/tmp/nope", "probe_phiark_loopback": True},
])
def test_unsafe_or_ambiguous_requests_rejected_before_network(kwargs: dict[str, object]) -> None:
    with patch("phios.foundation_status.select_mode", side_effect=AssertionError("no network")):
        with pytest.raises(ValueError):
            observe_foundation(**kwargs)  # type: ignore[arg-type]


def test_cli_is_json_and_never_claims_install(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "UNVERIFIED"
    assert result["acceptance"]["offlineReady"] is False
    assert main(["status", "--phiark-data-root", "relative/path"]) == 2
    assert json.loads(capsys.readouterr().err)["status"] == "REFUSED"
