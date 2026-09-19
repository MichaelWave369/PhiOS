from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_execution import (
    BuildExecutionRequest,
    BuildExecutionService,
    ProcessResult,
    StreamCapture,
    ToolIdentity,
)
from phios.apps.build_plan import plan_build_from_payloads
from phios.apps.manifest import AppManifest


def _manifest(runtime: str = "node", target: str = "package.json") -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.example",
            "name": "Example",
            "version": "1.0.0",
            "description": "Example app",
            "source": {
                "repository_url": "https://github.com/example/example",
                "license_expression": "MIT",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": runtime, "target": target},
            "permissions": [],
        }
    )


def _intake(manifest: AppManifest) -> dict[str, Any]:
    return {
        "evidence": {
            "repository_url": "https://github.com/example/example",
            "head_sha": "a" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": "https://github.com/example/example",
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }


def _receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-09-19T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": "https://github.com/example/example",
        "commit_sha": "a" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "b" * 64,
        "tree_sha256": "c" * 64,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def _empty_capture() -> StreamCapture:
    return StreamCapture(
        byte_count=0,
        sha256=hashlib.sha256(b"").hexdigest(),
        preview="",
        preview_truncated=False,
    )


class FakeRunner:
    def __init__(
        self,
        *,
        fail_step: str | None = None,
        produce_dist: bool = True,
    ) -> None:
        self.fail_step = fail_step
        self.produce_dist = produce_dist
        self.probes: list[str] = []
        self.runs: list[tuple[str, tuple[str, ...], Path]] = []

    def probe(
        self,
        *,
        logical_tool: str,
        executable_tool: str,
        argv: tuple[str, ...],
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ToolIdentity:
        self.probes.append(logical_tool)
        assert env["PHIOS_BUILD_EXECUTION"] == "1"
        assert timeout_seconds > 0
        return ToolIdentity(
            logical_tool=logical_tool,
            executable_path=f"/fake/{executable_tool}",
            version=f"{logical_tool} test-version",
            version_output_sha256=hashlib.sha256(logical_tool.encode()).hexdigest(),
        )

    def run(
        self,
        step: Any,
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> ProcessResult:
        self.runs.append((step.step_id, step.argv, cwd))
        assert env["PHIOS_BUILD_EXECUTION"] == "1"
        assert timeout_seconds > 0

        if step.step_id == "build" and self.produce_dist:
            dist = cwd / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.js").write_text("built", encoding="utf-8")

        exit_code = 9 if step.step_id == self.fail_step else 0
        return ProcessResult(
            exit_code=exit_code,
            timed_out=False,
            duration_ms=12,
            stdout=_empty_capture(),
            stderr=_empty_capture(),
        )


def _locked_node_plan(root: Path) -> tuple[dict[str, Any], dict[str, Any], Any]:
    manifest = _manifest()
    (root / "package.json").write_text(
        json.dumps(
            {
                "name": "example",
                "scripts": {"build": "vite build"},
                "devDependencies": {"vite": "^7.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text("{}", encoding="utf-8")
    (root / "vite.config.js").write_text("export default {}", encoding="utf-8")
    receipt = _receipt(root, manifest)
    intake = _intake(manifest)
    plan = plan_build_from_payloads(intake, receipt)
    return intake, receipt, plan


def _request(plan: Any, receipt: dict[str, Any]) -> BuildExecutionRequest:
    return BuildExecutionRequest.from_payloads(
        plan.to_dict(),
        receipt,
        approved_plan_sha256=plan.sha256(),
        approved_source_snapshot_sha256=plan.source_snapshot_sha256,
        approved_permissions=plan.requested_build_permissions,
    )


def test_execution_request_binds_exact_plan_digest(tmp_path: Path) -> None:
    _, receipt, plan = _locked_node_plan(tmp_path)

    with pytest.raises(ValueError, match="Approved plan SHA-256"):
        BuildExecutionRequest.from_payloads(
            plan.to_dict(),
            receipt,
            approved_plan_sha256="0" * 64,
            approved_source_snapshot_sha256=plan.source_snapshot_sha256,
            approved_permissions=plan.requested_build_permissions,
        )


def test_execution_request_binds_exact_source_snapshot(tmp_path: Path) -> None:
    _, receipt, plan = _locked_node_plan(tmp_path)

    with pytest.raises(ValueError, match="Approved source snapshot"):
        BuildExecutionRequest.from_payloads(
            plan.to_dict(),
            receipt,
            approved_plan_sha256=plan.sha256(),
            approved_source_snapshot_sha256="0" * 64,
            approved_permissions=plan.requested_build_permissions,
        )


def test_execution_permissions_must_exactly_match_reviewed_plan(tmp_path: Path) -> None:
    _, receipt, plan = _locked_node_plan(tmp_path)
    permissions = tuple(
        item
        for item in plan.requested_build_permissions
        if item != "build.network.dependencies"
    )

    with pytest.raises(ValueError, match="exactly match"):
        BuildExecutionRequest.from_payloads(
            plan.to_dict(),
            receipt,
            approved_plan_sha256=plan.sha256(),
            approved_source_snapshot_sha256=plan.source_snapshot_sha256,
            approved_permissions=permissions,
        )


def test_review_required_plan_is_not_executable(tmp_path: Path) -> None:
    manifest = _manifest()
    (tmp_path / "package.json").write_text(
        json.dumps({"name": "example", "scripts": {"build": "vite build"}}),
        encoding="utf-8",
    )
    receipt = _receipt(tmp_path, manifest)
    plan = plan_build_from_payloads(_intake(manifest), receipt)

    assert plan.status == "review_required"
    with pytest.raises(ValueError, match="not executable"):
        _request(plan, receipt)


def test_source_drift_blocks_before_any_process_runs(tmp_path: Path) -> None:
    _, receipt, plan = _locked_node_plan(tmp_path)
    request = _request(plan, receipt)
    (tmp_path / "package.json").write_text(
        (tmp_path / "package.json").read_text(encoding="utf-8").replace("example", "changed"),
        encoding="utf-8",
    )
    runner = FakeRunner()

    with pytest.raises(ValueError, match="Source snapshot changed"):
        BuildExecutionService(runner=runner).execute(
            request,
            execution_root=tmp_path / "executions",
        )

    assert runner.probes == []
    assert runner.runs == []


def test_successful_locked_node_build_emits_artifact_receipt(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, receipt, plan = _locked_node_plan(source)
    runner = FakeRunner()
    service = BuildExecutionService(runner=runner)

    execution = service.execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    assert execution.status == "success"
    assert execution.failure_reason is None
    assert [step.status for step in execution.steps] == ["succeeded", "succeeded"]
    assert [item.logical_tool for item in execution.tool_identities] == list(plan.required_tools)
    assert runner.runs[0][1] == ("npm", "ci")
    assert runner.runs[1][1] == ("npm", "run", "build")
    assert execution.isolation_mode == "isolated_working_copy_no_os_sandbox"
    assert execution.network_sandbox_enforced is False
    assert [artifact.path for artifact in execution.artifacts] == ["dist/index.js"]
    assert execution.artifacts[0].sha256 == hashlib.sha256(b"built").hexdigest()
    assert execution.to_dict()["receipt_sha256"] == execution.sha256()

    receipt_files = list((tmp_path / "executions" / ".phios-receipts").glob("*.json"))
    assert len(receipt_files) == 1
    persisted = json.loads(receipt_files[0].read_text(encoding="utf-8"))
    assert persisted["receipt_sha256"] == execution.sha256()


def test_failed_step_stops_pipeline_and_is_receipted(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, receipt, plan = _locked_node_plan(source)
    runner = FakeRunner(fail_step="build")

    execution = BuildExecutionService(runner=runner).execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    assert execution.status == "failed"
    assert execution.failure_reason == "step build exited with code 9"
    assert [step.step_id for step in execution.steps] == ["dependencies", "build"]
    assert execution.steps[-1].status == "failed"
    assert execution.artifacts == ()


def test_missing_expected_output_turns_successful_processes_into_failed_receipt(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, receipt, plan = _locked_node_plan(source)
    runner = FakeRunner(produce_dist=False)

    execution = BuildExecutionService(runner=runner).execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    assert execution.status == "failed"
    assert execution.failure_reason == "Expected build output was not produced: dist/"
    assert execution.artifacts == ()


def test_static_no_build_plan_copies_and_hashes_source_artifact_without_process(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    manifest = _manifest(runtime="static_web", target="index.html")
    (source / "index.html").write_text("<html>phi</html>", encoding="utf-8")
    receipt = _receipt(source, manifest)
    plan = plan_build_from_payloads(_intake(manifest), receipt)
    runner = FakeRunner()

    execution = BuildExecutionService(runner=runner).execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    assert plan.status == "no_build_required"
    assert execution.status == "no_build_required"
    assert runner.probes == []
    assert runner.runs == []
    assert [artifact.path for artifact in execution.artifacts] == ["index.html"]


def test_build_runs_only_inside_isolated_execution_copy(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, receipt, plan = _locked_node_plan(source)
    runner = FakeRunner()

    execution = BuildExecutionService(runner=runner).execute(
        _request(plan, receipt),
        execution_root=tmp_path / "executions",
    )

    execution_source = Path(execution.execution_workspace_path)
    assert execution_source != source.resolve()
    assert execution_source.is_dir()
    assert all(cwd == execution_source for _, _, cwd in runner.runs)
    assert not (source / "dist").exists()


def test_receipt_root_cannot_be_inside_execution_source(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, receipt, plan = _locked_node_plan(source)
    request = _request(plan, receipt)
    execution_root = tmp_path / "executions"
    nested_receipts = execution_root / plan.app_id / plan.sha256() / "placeholder" / "source"

    with pytest.raises(ValueError):
        BuildExecutionService(runner=FakeRunner()).execute(
            request,
            execution_root=execution_root,
            receipt_root=nested_receipts,
        )
