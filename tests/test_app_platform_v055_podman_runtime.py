from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_plan import AcquisitionBinding, BuildPlan, plan_build_from_payloads
from phios.apps.manifest import AppManifest
from phios.apps.podman_runtime import (
    PODMAN_ROOTLESS_ADAPTER_ID,
    PodmanCommandResult,
    PodmanRootlessOciRunner,
)
from phios.apps.sandbox import BuildSandboxPolicy
from phios.apps.toolchain_acquisition import CapsuleAcquisitionReceipt
from phios.apps.toolchain_attestation import (
    ToolProbeObservation,
    attest_toolchain,
    plan_toolchain_sandbox,
)
from phios.apps.toolchain_capsule import (
    ToolchainCapsule,
    ToolchainTool,
    bind_toolchain_capsule,
    derive_toolchain_requirement,
)
from phios.apps.toolchain_runtime import (
    ToolchainRuntimeRequest,
    ToolchainRuntimeService,
)


def _probe_digest(stdout: bytes, stderr: bytes = b"") -> str:
    stdout_sha = hashlib.sha256(stdout).hexdigest()
    stderr_sha = hashlib.sha256(stderr).hexdigest()
    combined = hashlib.sha256()
    combined.update(stdout_sha.encode("ascii"))
    combined.update(stderr_sha.encode("ascii"))
    return combined.hexdigest()


def _manifest() -> AppManifest:
    return AppManifest.from_dict(
        {
            "schema_version": "phios.app_manifest.v0.1",
            "app_id": "phi.v055-example",
            "name": "v0.55 Example",
            "version": "1.0.0",
            "description": "Rootless Podman runtime fixture",
            "source": {
                "repository_url": "https://github.com/example/v055-example",
                "license_expression": "MIT",
                "redistribution": "unknown",
            },
            "entrypoint": {"runtime": "node", "target": "package.json"},
            "permissions": [],
        }
    )


def _intake(manifest: AppManifest) -> dict[str, Any]:
    return {
        "evidence": {
            "repository_url": manifest.source.repository_url,
            "head_sha": "a" * 40,
        },
        "proposal": {
            "status": "inferred_candidate",
            "repository_url": manifest.source.repository_url,
            "app_id": manifest.app_id,
            "permissions_source": "not_declared",
        },
        "manifest_candidate": manifest.to_dict(),
    }


def _source_receipt(root: Path, manifest: AppManifest) -> dict[str, Any]:
    files = [path for path in root.rglob("*") if path.is_file()]
    return {
        "schema_version": "phios.source_acquisition_receipt.v0.1",
        "receipt_id": "11111111-1111-1111-1111-111111111111",
        "timestamp_utc": "2026-10-04T00:00:00+00:00",
        "app_id": manifest.app_id,
        "repository_url": manifest.source.repository_url,
        "commit_sha": "a" * 40,
        "manifest_sha256": manifest.sha256(),
        "archive_sha256": "b" * 64,
        "tree_sha256": "c" * 64,
        "file_count": len(files),
        "total_bytes": sum(path.stat().st_size for path in files),
        "workspace_path": str(root.resolve()),
        "status": "acquired",
    }


def _plan_digest(data: dict[str, Any]) -> str:
    body = dict(data)
    body.pop("plan_sha256", None)
    payload = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _plan(root: Path) -> tuple[BuildPlan, AcquisitionBinding]:
    root.mkdir(parents=True, exist_ok=True)
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
    receipt = _source_receipt(root, manifest)
    original = plan_build_from_payloads(_intake(manifest), receipt)

    data = original.to_dict()
    for step in data["steps"]:
        step["requires_network"] = False
    data["requested_build_permissions"] = [
        permission
        for permission in data["requested_build_permissions"]
        if permission != "build.network.dependencies"
    ]
    data["plan_sha256"] = _plan_digest(data)
    return BuildPlan.from_dict(data), AcquisitionBinding.from_dict(receipt)


def _observations() -> tuple[ToolProbeObservation, ...]:
    return (
        ToolProbeObservation(
            name="node",
            probe_argv=("node", "--version"),
            observed_version="22.0.0",
            subject_locator="/usr/bin/node",
            subject_sha256="1" * 64,
            probe_output_sha256=_probe_digest(b"22.0.0\n"),
        ),
        ToolProbeObservation(
            name="npm",
            probe_argv=("npm", "--version"),
            observed_version="10.0.0",
            subject_locator="/usr/bin/npm",
            subject_sha256="3" * 64,
            probe_output_sha256=_probe_digest(b"10.0.0\n"),
        ),
    )


def _lineage(tmp_path: Path):
    plan, source = _plan(tmp_path / "source")
    payload = b"v0.55-fixture-oci-archive"
    digest = hashlib.sha256(payload).hexdigest()
    storage = tmp_path / "capsule.oci"
    storage.write_bytes(payload)
    capsule = ToolchainCapsule(
        capsule_id="phios.node-npm.v055",
        family="node_npm",
        platform="linux_x86_64",
        artifact_kind="oci_image",
        artifact_ref=f"registry.example/phios/node-npm@sha256:{digest}",
        artifact_sha256=digest,
        tools=(
            ToolchainTool("node", "22.0.0"),
            ToolchainTool("npm", "10.0.0"),
        ),
    )
    requirement = derive_toolchain_requirement(plan)
    binding = bind_toolchain_capsule(requirement, capsule)
    acquisition = CapsuleAcquisitionReceipt(
        receipt_id="22222222-2222-2222-2222-222222222222",
        timestamp_utc="2026-10-04T00:00:00+00:00",
        app_id=plan.app_id,
        commit_sha=plan.commit_sha,
        plan_sha256=plan.sha256(),
        requirement_sha256=requirement.sha256(),
        capsule_sha256=capsule.sha256(),
        binding_sha256=binding.sha256(),
        capsule_id=capsule.capsule_id,
        family=capsule.family,
        artifact_kind=capsule.artifact_kind,
        artifact_ref=capsule.artifact_ref,
        artifact_sha256=capsule.artifact_sha256,
        artifact_bytes=len(payload),
        storage_path=str(storage.resolve()),
        storage_state="created",
    )
    attestation = attest_toolchain(
        plan,
        capsule,
        acquisition,
        _observations(),
        inspector_id="phios.fixture-inspector",
        inspector_version="0.1.0",
    )
    sandbox = plan_toolchain_sandbox(
        plan,
        capsule,
        acquisition,
        attestation,
        sandbox_policy=BuildSandboxPolicy(network_mode="deny"),
    )
    request = ToolchainRuntimeRequest(
        build_plan=plan,
        source_acquisition=source,
        capsule=capsule,
        capsule_acquisition=acquisition,
        attestation=attestation,
        sandbox_plan=sandbox,
        approved_sandbox_plan_sha256=sandbox.sha256(),
        approved_attestation_sha256=attestation.sha256(),
        approved_source_snapshot_sha256=plan.source_snapshot_sha256,
        approved_build_permissions=plan.requested_build_permissions,
        execution_approval_id="55555555-5555-5555-5555-555555555555",
    )
    return request


class FakePodmanExecutor:
    image_id = "a" * 64

    def __init__(self) -> None:
        self.calls: list[tuple[str, ...]] = []

    @staticmethod
    def _result(
        *,
        stdout: bytes = b"",
        stderr: bytes = b"",
        exit_code: int = 0,
    ) -> PodmanCommandResult:
        return PodmanCommandResult(
            exit_code=exit_code,
            timed_out=False,
            duration_ms=3,
            stdout=stdout,
            stderr=stderr,
        )

    @staticmethod
    def _mount_source(argv: tuple[str, ...]) -> Path | None:
        for index, value in enumerate(argv):
            if value == "--mount" and index + 1 < len(argv):
                spec = argv[index + 1]
                for item in spec.split(","):
                    if item.startswith("src="):
                        return Path(item.removeprefix("src="))
        return None

    def run(
        self,
        argv: tuple[str, ...],
        *,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> PodmanCommandResult:
        del env, timeout_seconds
        self.calls.append(argv)

        if argv[-1] == "--version" and "run" not in argv:
            return self._result(stdout=b"podman version 6.1.3\n")
        if "info" in argv and "json" in argv:
            return self._result(
                stdout=json.dumps(
                    {"host": {"security": {"rootless": True}}}
                ).encode("utf-8")
            )
        if "load" in argv:
            return self._result(stdout=b"")
        if "images" in argv:
            return self._result(stdout=(self.image_id + "\n").encode("ascii"))

        if "run" in argv:
            if "sha256sum" in argv:
                subject = argv[-1]
                digest = "1" * 64 if subject == "/usr/bin/node" else "3" * 64
                return self._result(
                    stdout=f"{digest}  {subject}\n".encode("ascii")
                )
            if argv[-2:] == ("node", "--version"):
                return self._result(stdout=b"22.0.0\n")
            if argv[-2:] == ("npm", "--version"):
                return self._result(stdout=b"10.0.0\n")
            if argv[-2:] == ("npm", "ci"):
                return self._result()
            if argv[-3:] == ("npm", "run", "build"):
                source = self._mount_source(argv)
                assert source is not None
                dist = source / "dist"
                dist.mkdir(parents=True, exist_ok=True)
                (dist / "index.js").write_text("podman-built", encoding="utf-8")
                return self._result()

        return self._result(stderr=b"unexpected fake podman command", exit_code=9)


def _fake_podman_binary(tmp_path: Path) -> Path:
    path = tmp_path / "podman"
    path.write_bytes(b"fixture-podman-binary")
    path.chmod(0o755)
    return path


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="requires POSIX uid semantics")
def test_rootless_podman_runner_executes_exact_v054_request(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    request = _lineage(tmp_path)
    executor = FakePodmanExecutor()
    runner = PodmanRootlessOciRunner(
        capsule=request.capsule,
        acquisition=request.capsule_acquisition,
        sandbox_plan=request.sandbox_plan,
        reviewed_attestation=request.attestation,
        state_root=tmp_path / "podman-state",
        podman_path=str(_fake_podman_binary(tmp_path)),
        executor=executor,
    )

    result = ToolchainRuntimeService(runner=runner).execute(
        request,
        execution_root=tmp_path / "executions",
    )

    assert result.execution.status == "success"
    assert result.runtime.runtime_identity.adapter_id == PODMAN_ROOTLESS_ADAPTER_ID
    assert result.runtime.controls.network_namespace_enforced is True
    assert result.runtime.controls.rootfs_read_only is True
    assert result.runtime.reusable_execution_authority is False
    assert any("--network=none" in call for call in executor.calls)
    assert any("--read-only" in call for call in executor.calls)
    assert any("--cap-drop=all" in call for call in executor.calls)
    assert any("--security-opt=no-new-privileges" in call for call in executor.calls)
    assert all("--pull=never" in call for call in executor.calls if "run" in call)


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="requires POSIX uid semantics")
def test_podman_preflight_refuses_non_rootless_info(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    request = _lineage(tmp_path)

    class NonRootless(FakePodmanExecutor):
        def run(
            self,
            argv: tuple[str, ...],
            *,
            env: dict[str, str],
            timeout_seconds: int,
        ) -> PodmanCommandResult:
            if "info" in argv and "json" in argv:
                return self._result(
                    stdout=json.dumps(
                        {"host": {"security": {"rootless": False}}}
                    ).encode("utf-8")
                )
            return super().run(argv, env=env, timeout_seconds=timeout_seconds)

    runner = PodmanRootlessOciRunner(
        capsule=request.capsule,
        acquisition=request.capsule_acquisition,
        sandbox_plan=request.sandbox_plan,
        reviewed_attestation=request.attestation,
        state_root=tmp_path / "podman-state",
        podman_path=str(_fake_podman_binary(tmp_path)),
        executor=NonRootless(),
    )

    with pytest.raises(ValueError, match="non-rootless"):
        runner.preflight()


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="requires POSIX uid semantics")
def test_podman_preflight_refuses_reused_state_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    request = _lineage(tmp_path)
    state = tmp_path / "podman-state"
    state.mkdir()
    (state / "stale").write_text("stale", encoding="utf-8")

    runner = PodmanRootlessOciRunner(
        capsule=request.capsule,
        acquisition=request.capsule_acquisition,
        sandbox_plan=request.sandbox_plan,
        reviewed_attestation=request.attestation,
        state_root=state,
        podman_path=str(_fake_podman_binary(tmp_path)),
        executor=FakePodmanExecutor(),
    )

    with pytest.raises(ValueError, match="fresh empty state root"):
        runner.preflight()


@pytest.mark.skipif(not hasattr(os, "geteuid"), reason="requires POSIX uid semantics")
def test_podman_runner_refuses_python_module_locator(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(os, "geteuid", lambda: 1000)
    request = _lineage(tmp_path)
    observations = list(request.attestation.observations)
    observations[0] = ToolProbeObservation(
        name="node",
        probe_argv=("node", "--version"),
        observed_version="22.0.0",
        subject_locator="python-module:node",
        subject_sha256="1" * 64,
        probe_output_sha256=_probe_digest(b"22.0.0\n"),
    )
    attestation = replace_attestation(request, tuple(observations))

    runner = PodmanRootlessOciRunner(
        capsule=request.capsule,
        acquisition=request.capsule_acquisition,
        sandbox_plan=replace_sandbox(request, attestation),
        reviewed_attestation=attestation,
        state_root=tmp_path / "state",
        podman_path=str(_fake_podman_binary(tmp_path)),
        executor=FakePodmanExecutor(),
    )
    runner.preflight()

    with pytest.raises(ValueError, match="absolute subject locator"):
        runner.runtime_observations()

def replace_attestation(
    request: ToolchainRuntimeRequest,
    observations: tuple[ToolProbeObservation, ...],
):
    return attest_toolchain(
        request.build_plan,
        request.capsule,
        request.capsule_acquisition,
        observations,
        inspector_id=request.attestation.inspector_id,
        inspector_version=request.attestation.inspector_version,
    )


def replace_sandbox(
    request: ToolchainRuntimeRequest,
    attestation,
):
    return plan_toolchain_sandbox(
        request.build_plan,
        request.capsule,
        request.capsule_acquisition,
        attestation,
        sandbox_policy=request.sandbox_plan.sandbox_policy,
    )
