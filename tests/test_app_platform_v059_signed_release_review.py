"""R5B: test real Ed25519 crypto, exact v0.50 binding and no install authority."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from phios.apps.release_install_proposal import ReleaseInstallProposalRecord
from phios.apps.release_publisher_review import (
    DOMAIN,
    _strict_json_bytes,
    main,
    review_signed_release,
)

KEY_ID = "gmed-union-dev-test"
PRIVATE = Ed25519PrivateKey.from_private_bytes(bytes(range(1, 33)))
PUBLIC = PRIVATE.public_key().public_bytes(
    encoding=serialization.Encoding.Raw,
    format=serialization.PublicFormat.Raw,
)
PIN = hashlib.sha256(PUBLIC).hexdigest()


def proposal(*, version: str = "2.0.0") -> ReleaseInstallProposalRecord:
    return ReleaseInstallProposalRecord(
        package_plan_sha256="1"*64,
        release_build_review_sha256="2"*64,
        app_id="phi.release.install",
        app_version=version,
        repository_url="https://github.com/MichaelWave369/phi-field",
        commit_sha="a"*40,
        manifest_sha256="3"*64,
        registry_snapshot_sha256="4"*64,
        execution_receipt_sha256="5"*64,
        offline_build_receipt_sha256="6"*64,
        artifact_set_sha256="7"*64,
        install_relative_path="phi.release.install/2.0.0",
    )


def statement(proposal_obj: ReleaseInstallProposalRecord) -> dict:
    return {
        "schema": "phios.release_publisher_statement.v0.1",
        "publisher_key_id": KEY_ID,
        "app_id": proposal_obj.app_id,
        "app_version": proposal_obj.app_version,
        "repository_url": proposal_obj.repository_url,
        "commit_sha": proposal_obj.commit_sha,
        "release_install_proposal_sha256": proposal_obj.sha256(),
        "package_plan_sha256": proposal_obj.package_plan_sha256,
        "manifest_sha256": proposal_obj.manifest_sha256,
        "artifact_set_sha256": proposal_obj.artifact_set_sha256,
        "dependency_review_sha256": "8"*64,
        "compatibility_review_sha256": "9"*64,
        "rollback_rehearsal_sha256": "b"*64,
        "install_authority": False,
        "update_authority": False,
        "rollback_authority": False,
    }


def sign(data: dict) -> bytes:
    return PRIVATE.sign(DOMAIN + _strict_json_bytes(data))


def verify(
    data: dict | None = None, *, old_proposal: ReleaseInstallProposalRecord | None = None,
    key: bytes = PUBLIC, signature: bytes | None = None, pin: str = PIN,
    expected_key_id: str = KEY_ID,
):
    prop = old_proposal or proposal()
    body = data or statement(prop)
    return review_signed_release(
        prop.to_dict(), body,
        signature=sign(body) if signature is None else signature,
        publisher_public_key=key,
        independently_pinned_key_sha256=pin,
        expected_key_id=expected_key_id,
    )


def test_real_signature_matches_exact_release_proposal_but_keeps_all_holds():
    data=statement(proposal())
    receipt=verify(data,signature=sign(data))
    assert receipt["status"]=="SIGNATURE_VALID_UNDER_CALLER_PIN_RELEASE_STILL_HELD"
    assert receipt["signature_valid_under_supplied_key"] is True
    assert receipt["release_install_proposal_sha256"]==proposal().sha256()
    assert receipt["signed_statement_sha256"]==hashlib.sha256(_strict_json_bytes(data)).hexdigest()
    assert receipt["pinned_public_key_sha256"]==PIN
    for field in (
        "publisher_identity_independently_verified",
        "source_commit_independently_authenticated",
        "dependency_compatibility_verified",
        "device_compatibility_verified",
        "license_distribution_review_cleared",
        "sandbox_and_permission_review_cleared",
        "rollback_rehearsal_independently_verified",
        "install_authority", "launch_authority", "update_authority", "rollback_authority",
    ):
        assert receipt[field] is False
    assert receipt["operations_performed"]==[]
    assert receipt["review_sha256"]==hashlib.sha256(
        _strict_json_bytes({k:v for k,v in receipt.items() if k!="review_sha256"})
    ).hexdigest()


def test_tamper_without_resigning_refused():
    body=statement(proposal())
    signature=sign(body)
    for field,new_value in [
        ("dependency_review_sha256","f"*64),
        ("rollback_rehearsal_sha256","0"*64),
        ("publisher_key_id","other-review-key"),
    ]:
        altered={**body,field:new_value}
        with pytest.raises(ValueError,match="signature|key ID"):
            verify(altered, signature=signature)
    with pytest.raises(ValueError,match="signature"):
        verify(body,signature=bytes(64))


def test_wrong_external_pin_or_key_is_refused():
    body=statement(proposal())
    with pytest.raises(ValueError,match="pin"):
        verify(body,pin="0"*64)
    other=Ed25519PrivateKey.from_private_bytes(bytes(range(33,65)))
    other_key=other.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw
    )
    with pytest.raises(ValueError,match="signature"):
        verify(body,key=other_key,pin=hashlib.sha256(other_key).hexdigest())
    with pytest.raises(ValueError,match="key ID"):
        verify(body,expected_key_id="untrusted-other-key")
    with pytest.raises(ValueError,match="32 bytes"):
        verify(body,key=b"wrong")
    with pytest.raises(ValueError,match="64 bytes"):
        verify(body,signature=b"wrong")


def test_even_resigned_other_release_is_not_accepted():
    old=proposal()
    body=statement(old)
    with pytest.raises(ValueError,match="exact release"):
        verify(body,old_proposal=proposal(version="2.0.1"))
    other_body={**body,"package_plan_sha256":"d"*64}
    with pytest.raises(ValueError,match="exact release"):
        verify(other_body,signature=sign(other_body))


def test_unknown_fields_authorities_bad_digests_and_missing_review_rejected():
    body=statement(proposal())
    for field in ("install_authority", "update_authority", "rollback_authority"):
        with pytest.raises(ValueError,match=field):
            verify({**body,field:True})
    with pytest.raises(ValueError,match="unknown fields"):
        verify({**body, "shell_command":"sudo pacman -U arbitrary"})
    for field in ("dependency_review_sha256","compatibility_review_sha256","rollback_rehearsal_sha256"):
        with pytest.raises(ValueError,match=field):
            verify({**body,field:"not independently reviewed"})
    with pytest.raises(ValueError,match="unknown fields"):
        changed={k:v for k,v in body.items() if k!="rollback_rehearsal_sha256"}
        verify(changed)


def test_cli_read_only_input_and_symlink_refusal(tmp_path:Path,capsys):
    body=statement(proposal())
    proposal_path=tmp_path/"proposal.json"
    proposal_path.write_text(json.dumps(proposal().to_dict()),encoding="utf-8")
    statement_path=tmp_path/"statement.json"
    statement_path.write_text(json.dumps(body),encoding="utf-8")
    signature_path=tmp_path/"statement.sig"
    signature_path.write_bytes(sign(body))
    public_path=tmp_path/"publisher.pub"
    public_path.write_bytes(PUBLIC)
    argv=[
        "--proposal",str(proposal_path),
        "--statement",str(statement_path),
        "--signature",str(signature_path),
        "--public-key",str(public_path),
        "--trusted-key-sha256",PIN,
        "--expected-key-id",KEY_ID,
    ]
    assert main(argv)==0
    result=json.loads(capsys.readouterr().out)
    from phios.apps.cli import main as phi_app_main
    assert phi_app_main(["review-signed-release", *argv]) == 3
    guarded_cli_result=json.loads(capsys.readouterr().out)
    assert guarded_cli_result["status"] == "SIGNATURE_VALID_UNDER_CALLER_PIN_RELEASE_STILL_HELD"
    bad_argv=[*argv]
    bad_argv[bad_argv.index("--trusted-key-sha256")+1]="0"*64
    assert phi_app_main(["review-signed-release",*bad_argv]) == 2
    blocked=json.loads(capsys.readouterr().out)
    assert blocked["status"]=="RELEASE_SIGNATURE_REVIEW_BLOCKED"
    assert blocked["install_authority"] is False
    assert result["signature_valid_under_supplied_key"] is True
    assert result["install_authority"] is False
    assert sorted(p.name for p in tmp_path.iterdir())==[
        "proposal.json","publisher.pub","statement.json","statement.sig"
    ]
    fake_dir=tmp_path/"aliases"
    fake_dir.mkdir()
    linked=fake_dir/"publisher.pub"
    linked.symlink_to(public_path)
    broken=[*argv]
    broken[broken.index("--public-key")+1]=str(linked)
    with pytest.raises(ValueError,match="symbolic-link"):
        main(broken)
