from pathlib import Path

from phios.spine.runtime import PhiOSSpine


def test_capability_is_registered(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    ids = [item.id for item in spine.registry.list()]
    assert ids == ["commons.text_artifact"]


def test_fail_closed_denial_is_receipted(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path)
    receipt = spine.run("commons.text_artifact", {"text": "blocked", "name": "nope"})
    assert receipt.permission_status == "denied"
    assert receipt.execution_status == "not_executed"
    assert not (tmp_path / "artifacts" / "nope.txt").exists()
    recent = spine.ledger.recent(1)
    assert recent[0]["receipt_id"] == receipt.receipt_id


def test_authorized_run_creates_hashed_artifact_and_receipt(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, allowed_permissions=["artifact.write"])
    receipt = spine.run("commons.text_artifact", {"text": "PhiOS Spine", "name": "proof"})
    assert receipt.permission_status == "allowed"
    assert receipt.execution_status == "succeeded"
    path = Path(receipt.artifact_path or "")
    assert path.read_text(encoding="utf-8") == "PhiOS Spine"
    assert receipt.artifact_sha256
    assert spine.ledger.recent(1)[0]["artifact_sha256"] == receipt.artifact_sha256


def test_filename_is_bounded_to_artifact_root(tmp_path: Path) -> None:
    spine = PhiOSSpine(state_root=tmp_path, allowed_permissions=["artifact.write"])
    receipt = spine.run("commons.text_artifact", {"text": "safe", "name": "../../escape"})
    assert receipt.execution_status == "succeeded"
    assert Path(receipt.artifact_path or "").parent == (tmp_path / "artifacts").resolve()
