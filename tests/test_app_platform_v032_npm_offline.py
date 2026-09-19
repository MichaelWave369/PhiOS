from __future__ import annotations

import base64
import hashlib
import json
import shutil
import subprocess
import tarfile
import uuid
from pathlib import Path
from typing import Any

import pytest

from phios.apps.build_execution import ProcessResult, StreamCapture, ToolIdentity
from phios.apps.build_plan import plan_build_from_payloads
from phios.apps.dependency_broker import DependencyReceipt, StagedDependencyArtifact
from phios.apps.manifest import AppManifest
from phios.apps.npm_offline import (
    NpmCachePreparationRequest,
    NpmCacheReceipt,
    NpmOfflineBuildRequest,
    NpmOfflineBuildService,
    NpmOfflineCacheService,
    NpmOfflineBuildPlan,
    derive_npm_offline_build_plan,
    review_npm_offline_build_plan,
)
from phios.apps.sandbox import (
    BuildSandboxPolicy,
    BubblewrapSandboxRunner,
    SandboxBackendIdentity,
    SandboxControlEvidence,
)


def _manifest() -> AppManifest:
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
            "entrypoint": {"runtime": "node", "target": "package.json"},
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


def _acquisition(root: Path, manifest: AppManifest) -> dict[str, Any]:
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


def _build_plan(root: Path) -> tuple[dict[str, Any], Any]:
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
    (root / "package-lock.json").write_text(
        json.dumps({"lockfileVersion": 3, "packages": {}}),
        encoding="utf-8",
    )
    (root / "vite.config.js").write_text("export default {}", encoding="utf-8")
    receipt = _acquisition(root, manifest)
    return receipt, plan_build_from_payloads(_intake(manifest), receipt)


def _sri(content: bytes) -> str:
    return base64.b64encode(hashlib.sha512(content).digest()).decode("ascii")


def _dependency_receipt(
    root: Path,
    plan: Any,
    *,
    content: bytes = b"npm-package-tarball",
) -> DependencyReceipt:
    store = root / "dependency-store"
    digest = hashlib.sha256(content).hexdigest()
    cas = store / "cas" / "sha256" / digest[:2] / f"{digest}.blob"
    cas.parent.mkdir(parents=True)
    cas.write_bytes(content)
    artifact = StagedDependencyArtifact(
        resolved_url="https://registry.npmjs.org/dep/-/dep-1.0.0.tgz",
        host="registry.npmjs.org",
        integrity_algorithm="sha512",
        integrity_digest_base64=_sri(content),
        byte_count=len(content),
        sha256=digest,
        cas_path=str(cas.resolve()),
        lock_keys=("node_modules/dep",),
        version="1.0.0",
    )
    return DependencyReceipt(
        receipt_id=str(uuid.uuid4()),
        timestamp_utc="2026-09-19T00:00:00+00:00",
        app_id=plan.app_id,
        repository_url=plan.repository_url,
        commit_sha=plan.commit_sha,
        package_manager="npm",
        lockfile_version=3,
        build_plan_sha256=plan.sha256(),
        source_snapshot_sha256=plan.source_snapshot_sha256,
        dependency_plan_sha256="d" * 64,
        lockfile_path="package-lock.json",
        lockfile_sha256=hashlib.sha256(
            (root / "source" / "package-lock.json").read_bytes()
        ).hexdigest(),
        approved_hosts=("registry.npmjs.org",),
        artifacts=(artifact,),
        total_bytes=len(content),
        store_root=str(store.resolve()),
    )


class FakeNpmRunner:
    def __init__(self) -> None:
        self.commands: list[tuple[str, ...]] = []

    def probe(self, *, cwd: Path, env: dict[str, str]) -> ToolIdentity:
        assert env["NPM_CONFIG_OFFLINE"] == "true"
        return ToolIdentity(
            logical_tool="npm",
            executable_path="/usr/bin/npm",
            version="11.test",
            version_output_sha256=hashlib.sha256(b"11.test").hexdigest(),
        )

    def run(
        self,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        env: dict[str, str],
        timeout_seconds: int,
    ) -> Any:
        self.commands.append(argv)
        cache = Path(env["NPM_CONFIG_CACHE"])
        cache.mkdir(parents=True, exist_ok=True)
        if argv[:3] == ("npm", "cache", "add"):
            source = Path(argv[3])
            target = cache / "_cacache" / "content" / source.name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())
        elif argv[:3] == ("npm", "cache", "verify"):
            marker = cache / "_cacache" / "verified"
            marker.parent.mkdir(parents=True, exist_ok=True)
            marker.write_text("verified", encoding="utf-8")
        return type(
            "FakeNpmResult",
            (),
            {"exit_code": 0, "timed_out": False, "duration_ms": 1},
        )()


def _empty_capture() -> StreamCapture:
    return StreamCapture(
        byte_count=0,
        sha256=hashlib.sha256(b"").hexdigest(),
        preview="",
        preview_truncated=False,
    )


class FakeOfflineSandboxRunner:
    isolation_mode = "fake_v032_network_denied"

    def __init__(self, policy: BuildSandboxPolicy, cache_path: Path) -> None:
        self.policy = policy
        self.cache_path = cache_path
        self.network_sandbox_enforced = True
        self.steps: list[Any] = []
        self.preflight_calls = 0

    def preflight(self) -> SandboxBackendIdentity:
        self.preflight_calls += 1
        return SandboxBackendIdentity(
            backend="bubblewrap",
            executable_path="/usr/bin/bwrap",
            version="bubblewrap test",
            version_output_sha256=hashlib.sha256(b"bwrap").hexdigest(),
            platform_system="Linux",
            platform_machine="x86_64",
        )

    def control_evidence(self) -> SandboxControlEvidence:
        return SandboxControlEvidence(
            mount_namespace_enforced=True,
            user_namespace_enforced=True,
            pid_namespace_enforced=True,
            ipc_namespace_enforced=True,
            uts_namespace_enforced=True,
            cgroup_namespace_requested=False,
            private_proc=True,
            private_dev=True,
            private_tmp=True,
            private_home=True,
            workspace_only_writable_mount=False,
            host_system_roots_read_only=True,
            network_namespace_enforced=True,
            host_network_inherited=False,
            wall_clock_timeout_enforced=True,
            cpu_rlimit_enforced=True,
            address_space_rlimit_enforced=True,
            open_files_rlimit_enforced=True,
            file_size_rlimit_enforced=True,
            process_count_limit_enforced=False,
            seccomp_enforced=False,
            network_allowlist_enforced=False,
            parent_death_enforced=True,
        )

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
        assert self.cache_path.is_dir()
        return ToolIdentity(
            logical_tool=logical_tool,
            executable_path=f"/usr/bin/{executable_tool}",
            version=f"{logical_tool} test",
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
        self.steps.append(step)
        if step.phase == "dependencies":
            assert step.requires_network is False
            assert step.argv == (
                "npm",
                "ci",
                "--offline",
                "--cache",
                "/phios/npm-cache",
            )
        if step.step_id == "build":
            dist = cwd / "dist"
            dist.mkdir(parents=True, exist_ok=True)
            (dist / "index.js").write_text("offline-built", encoding="utf-8")
        return ProcessResult(
            exit_code=0,
            timed_out=False,
            duration_ms=3,
            stdout=_empty_capture(),
            stderr=_empty_capture(),
        )


def _prepare_cache(tmp_path: Path) -> tuple[dict[str, Any], Any, DependencyReceipt, NpmCacheReceipt]:
    source = tmp_path / "source"
    source.mkdir()
    acquisition, plan = _build_plan(source)
    dependency = _dependency_receipt(tmp_path, plan)
    runner = FakeNpmRunner()
    cache_receipt = NpmOfflineCacheService(runner=runner).prepare(
        NpmCachePreparationRequest.from_payload(
            dependency.to_dict(),
            approved_dependency_receipt_sha256=dependency.sha256(),
        ),
        cache_root=tmp_path / "npm-caches",
    )
    return acquisition, plan, dependency, cache_receipt


def test_prepare_cache_uses_local_tarballs_and_npm_offline(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan = _build_plan(source)
    dependency = _dependency_receipt(tmp_path, plan)
    runner = FakeNpmRunner()

    receipt = NpmOfflineCacheService(runner=runner).prepare(
        NpmCachePreparationRequest.from_payload(
            dependency.to_dict(),
            approved_dependency_receipt_sha256=dependency.sha256(),
        ),
        cache_root=tmp_path / "npm-caches",
    )

    assert receipt.dependency_receipt_sha256 == dependency.sha256()
    assert receipt.population_network_control == "npm_offline_flag"
    assert receipt.os_network_namespace_enforced is False
    assert Path(receipt.cache_path).is_dir()
    assert receipt.cache_file_count >= 2
    assert runner.commands[-1][0:3] == ("npm", "cache", "verify")
    for command in runner.commands:
        assert "--offline" in command
    assert NpmCacheReceipt.from_dict(receipt.to_dict()) == receipt


def test_cache_preparation_requires_exact_dependency_receipt_approval(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan = _build_plan(source)
    dependency = _dependency_receipt(tmp_path, plan)

    with pytest.raises(ValueError, match="Approved dependency receipt"):
        NpmCachePreparationRequest.from_payload(
            dependency.to_dict(),
            approved_dependency_receipt_sha256="0" * 64,
        )


def test_cache_preparation_reverifies_cas_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _, plan = _build_plan(source)
    dependency = _dependency_receipt(tmp_path, plan)
    Path(dependency.artifacts[0].cas_path).write_bytes(b"tampered")

    with pytest.raises(ValueError):
        NpmOfflineCacheService(runner=FakeNpmRunner()).prepare(
            NpmCachePreparationRequest.from_payload(
                dependency.to_dict(),
                approved_dependency_receipt_sha256=dependency.sha256(),
            ),
            cache_root=tmp_path / "npm-caches",
        )


def test_offline_plan_removes_network_authority_and_rewrites_npm_ci(
    tmp_path: Path,
) -> None:
    _, plan, _, cache = _prepare_cache(tmp_path)

    offline = derive_npm_offline_build_plan(plan.to_dict(), cache.to_dict())
    derived = offline.derived_build_plan
    dependency_step = derived.steps[0]

    assert offline.original_build_plan_sha256 == plan.sha256()
    assert offline.npm_cache_receipt_sha256 == cache.sha256()
    assert dependency_step.requires_network is False
    assert "--offline" in dependency_step.argv
    assert dependency_step.argv[-1] == "/phios/npm-cache"
    assert "build.network.dependencies" not in derived.requested_build_permissions
    assert derived.requested_build_permissions == (
        "build.process.execute",
        "build.workspace.write",
    )
    review = review_npm_offline_build_plan(offline.to_dict())
    assert review.network_required is False
    assert review.npm_offline_plan_sha256 == offline.sha256()


def test_offline_plan_tampering_is_rejected(tmp_path: Path) -> None:
    _, plan, _, cache = _prepare_cache(tmp_path)
    offline = derive_npm_offline_build_plan(plan.to_dict(), cache.to_dict())
    payload = offline.to_dict()
    payload["cache_tree_sha256"] = "0" * 64

    with pytest.raises(ValueError):
        NpmOfflineBuildPlan.from_dict(payload)


def test_auxiliary_cache_bind_is_explicit_in_bubblewrap_command(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    runner = BubblewrapSandboxRunner(
        BuildSandboxPolicy(network_mode="deny"),
        bwrap_path="/usr/bin/bwrap",
        prlimit_path="/usr/bin/prlimit",
        extra_read_write_binds=((cache, "/phios/npm-cache"),),
        extra_environment={
            "NPM_CONFIG_CACHE": "/phios/npm-cache",
            "NPM_CONFIG_OFFLINE": "true",
        },
    )

    command = runner.command_for(
        executable_path="/usr/bin/python3",
        argv_tail=("--version",),
        source_root=tmp_path,
        cwd=tmp_path,
    )

    cache_index = command.index(str(cache.resolve()))
    assert command[cache_index - 1] == "--bind"
    assert command[cache_index + 1] == "/phios/npm-cache"
    assert "--unshare-net" in command
    assert "NPM_CONFIG_CACHE" in command
    assert runner.control_evidence().workspace_only_writable_mount is False


def test_auxiliary_mounts_cannot_escape_phios_namespace(tmp_path: Path) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()

    with pytest.raises(ValueError, match="/phios/"):
        BubblewrapSandboxRunner(
            BuildSandboxPolicy(),
            bwrap_path="/usr/bin/bwrap",
            prlimit_path="/usr/bin/prlimit",
            extra_read_write_binds=((cache, "/home/user/.npm"),),
        )


def test_offline_build_executes_derived_plan_with_network_denied(tmp_path: Path) -> None:
    acquisition, plan, _, cache = _prepare_cache(tmp_path)
    offline = derive_npm_offline_build_plan(plan.to_dict(), cache.to_dict())
    request = NpmOfflineBuildRequest.from_payloads(
        offline.to_dict(),
        acquisition,
        cache.to_dict(),
        approved_offline_plan_sha256=offline.sha256(),
    )
    created: list[FakeOfflineSandboxRunner] = []

    def factory(
        policy: BuildSandboxPolicy,
        working_cache: Path,
    ) -> FakeOfflineSandboxRunner:
        runner = FakeOfflineSandboxRunner(policy, working_cache)
        created.append(runner)
        return runner

    result = NpmOfflineBuildService(runner_factory=factory).execute(
        request,
        execution_root=tmp_path / "executions",
    )

    assert result.sandboxed_build.execution.status == "success"
    assert result.sandboxed_build.execution.network_sandbox_enforced is True
    assert result.sandboxed_build.sandbox.controls.network_namespace_enforced is True
    assert result.sandboxed_build.sandbox.controls.host_network_inherited is False
    assert result.offline_receipt.network_mode == "deny"
    assert result.offline_receipt.npm_offline_plan_sha256 == offline.sha256()
    assert result.offline_receipt.npm_cache_receipt_sha256 == cache.sha256()
    assert result.offline_receipt.build_execution_receipt_sha256 == (
        result.sandboxed_build.execution.sha256()
    )
    assert result.offline_receipt.sandbox_receipt_sha256 == (
        result.sandboxed_build.sandbox.sha256()
    )
    assert result.offline_receipt_persisted is True
    assert result.offline_receipt_path is not None
    assert Path(result.offline_receipt_path).is_file()
    assert created[0].preflight_calls == 1
    assert [step.step_id for step in created[0].steps] == ["dependencies", "build"]


def test_offline_execution_requires_exact_offline_plan_approval(tmp_path: Path) -> None:
    acquisition, plan, _, cache = _prepare_cache(tmp_path)
    offline = derive_npm_offline_build_plan(plan.to_dict(), cache.to_dict())

    with pytest.raises(ValueError, match="Approved npm offline plan"):
        NpmOfflineBuildRequest.from_payloads(
            offline.to_dict(),
            acquisition,
            cache.to_dict(),
            approved_offline_plan_sha256="0" * 64,
        )


def test_offline_execution_reverifies_receipted_cache(tmp_path: Path) -> None:
    acquisition, plan, _, cache = _prepare_cache(tmp_path)
    offline = derive_npm_offline_build_plan(plan.to_dict(), cache.to_dict())
    first_file = next(
        path for path in Path(cache.cache_path).rglob("*") if path.is_file()
    )
    first_file.write_bytes(first_file.read_bytes() + b"mutation")
    request = NpmOfflineBuildRequest.from_payloads(
        offline.to_dict(),
        acquisition,
        cache.to_dict(),
        approved_offline_plan_sha256=offline.sha256(),
    )

    with pytest.raises(ValueError, match="cache tree changed"):
        NpmOfflineBuildService(
            runner_factory=lambda policy, path: FakeOfflineSandboxRunner(policy, path)
        ).execute(
            request,
            execution_root=tmp_path / "executions",
        )


def test_real_npm_cache_can_feed_lockfile_offline_install(tmp_path: Path) -> None:
    npm = shutil.which("npm")
    if npm is None:
        pytest.skip("npm is unavailable on this test host")

    package_root = tmp_path / "fixture-package"
    package_root.mkdir()
    (package_root / "package.json").write_text(
        json.dumps(
            {
                "name": "phios-offline-fixture",
                "version": "1.0.0",
                "main": "index.js",
            }
        ),
        encoding="utf-8",
    )
    (package_root / "index.js").write_text("module.exports = 42;\n", encoding="utf-8")
    tarball = tmp_path / "phios-offline-fixture-1.0.0.tgz"
    with tarfile.open(tarball, "w:gz") as archive:
        archive.add(package_root / "package.json", arcname="package/package.json")
        archive.add(package_root / "index.js", arcname="package/index.js")

    content = tarball.read_bytes()
    integrity = "sha512-" + base64.b64encode(
        hashlib.sha512(content).digest()
    ).decode("ascii")

    consumer = tmp_path / "consumer"
    consumer.mkdir()
    (consumer / "package.json").write_text(
        json.dumps(
            {
                "name": "consumer",
                "version": "1.0.0",
                "dependencies": {"phios-offline-fixture": "1.0.0"},
            }
        ),
        encoding="utf-8",
    )
    (consumer / "package-lock.json").write_text(
        json.dumps(
            {
                "name": "consumer",
                "version": "1.0.0",
                "lockfileVersion": 3,
                "requires": True,
                "packages": {
                    "": {
                        "name": "consumer",
                        "version": "1.0.0",
                        "dependencies": {"phios-offline-fixture": "1.0.0"},
                    },
                    "node_modules/phios-offline-fixture": {
                        "version": "1.0.0",
                        "resolved": (
                            "https://registry.npmjs.org/phios-offline-fixture/"
                            "-/phios-offline-fixture-1.0.0.tgz"
                        ),
                        "integrity": integrity,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    cache = tmp_path / "real-npm-cache"
    common_env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": str(tmp_path / "home"),
        "NPM_CONFIG_AUDIT": "false",
        "NPM_CONFIG_FUND": "false",
        "NPM_CONFIG_UPDATE_NOTIFIER": "false",
        "NPM_CONFIG_OFFLINE": "true",
    }
    Path(common_env["HOME"]).mkdir()

    add = subprocess.run(
        (npm, "cache", "add", str(tarball), "--cache", str(cache), "--offline"),
        cwd=tmp_path,
        env=common_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=30,
        check=False,
    )
    assert add.returncode == 0, add.stderr.decode("utf-8", errors="replace")

    verify = subprocess.run(
        (npm, "cache", "verify", "--cache", str(cache), "--offline"),
        cwd=tmp_path,
        env=common_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=30,
        check=False,
    )
    assert verify.returncode == 0, verify.stderr.decode("utf-8", errors="replace")

    install = subprocess.run(
        (npm, "ci", "--offline", "--cache", str(cache), "--ignore-scripts"),
        cwd=consumer,
        env=common_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        shell=False,
        timeout=30,
        check=False,
    )
    assert install.returncode == 0, install.stderr.decode("utf-8", errors="replace")
    assert (consumer / "node_modules" / "phios-offline-fixture" / "index.js").is_file()
