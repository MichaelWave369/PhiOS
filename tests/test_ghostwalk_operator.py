from __future__ import annotations

import io
from dataclasses import replace
from pathlib import Path

import pytest

from phios.ghostwalk_operator import build_operator_console, main, review
from tests.test_macro_authorization_console_server import FakeConsole, REQUEST, TARGET


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def test_unattended_mutation_rejected_before_state_creation(tmp_path: Path) -> None:
    root = tmp_path / "absent"
    assert main(["--state-root", str(root), "--target", TARGET, "decide", "APPROVE"]) == 1
    assert not root.exists()


def test_cancel_creates_no_authority() -> None:
    console = FakeConsole()
    assert review(console, target=TARGET, action="decide", decision="APPROVE",  # type: ignore[arg-type]
                  input_stream=Terminal("cancel\n"), output_stream=Terminal()) == 2
    assert console.decision_calls == console.binding_calls == console.lease_calls == []


def test_exact_review_records_only_decision() -> None:
    console = FakeConsole()
    snapshot = console.snapshot(target_inference_receipt_sha256=TARGET)
    output = Terminal()
    assert review(console, target=TARGET, action="decide", decision="APPROVE",  # type: ignore[arg-type]
                  input_stream=Terminal(f"APPROVE {snapshot.snapshot_sha256}\n"),
                  output_stream=output) == 0
    assert len(console.decision_calls) == 1
    assert console.decision_calls[0]["expected_authority_request_sha256"] == REQUEST
    assert console.binding_calls == console.lease_calls == []
    assert '"effect_performed": false' in output.getvalue()


def test_changed_evidence_during_review_rejected() -> None:
    class ChangedConsole(FakeConsole):
        count = 0

        def snapshot(self, **kwargs):
            initial = super().snapshot(**kwargs)
            self.count += 1
            if self.count > 1:
                return replace(initial, authorization_readiness=replace(
                    initial.authorization_readiness, authority_request_sha256="f" * 64))
            return initial

    console = ChangedConsole()
    initial = FakeConsole().snapshot(target_inference_receipt_sha256=TARGET)
    with pytest.raises(ValueError, match="evidence changed"):
        review(console, target=TARGET, action="decide", decision="APPROVE",  # type: ignore[arg-type]
               input_stream=Terminal(f"APPROVE {initial.snapshot_sha256}\n"),
               output_stream=Terminal())
    assert console.decision_calls == console.binding_calls == console.lease_calls == []


@pytest.mark.skipif(__import__("os").name != "posix", reason="POSIX permissions")
def test_shared_writable_state_refused(tmp_path: Path) -> None:
    root = tmp_path / "state"
    root.mkdir(mode=0o777)
    root.chmod(0o777)
    with pytest.raises(ValueError, match="not shared-writable"):
        build_operator_console(root)


def test_symlinked_state_refused(tmp_path: Path) -> None:
    destination = tmp_path / "real"
    destination.mkdir()
    root = tmp_path / "state"
    root.symlink_to(destination, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        build_operator_console(root)
