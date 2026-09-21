from pathlib import Path

from phios.apps.control_plane_isolation import (
    ControlPlaneSurfaceMap,
    SandboxReachabilitySnapshot,
    evaluate_control_plane_isolation,
)


def _snapshot(
    tmp_path: Path,
    *,
    source_root: Path | None = None,
    read_only: tuple[Path, ...] = (),
    read_write: tuple[Path, ...] = (),
    environment_keys: tuple[str, ...] = (),
    network_mode: str = "deny",
    network_namespace_enforced: bool = True,
    ipc_namespace_enforced: bool = True,
) -> SandboxReachabilitySnapshot:
    return SandboxReachabilitySnapshot.build(
        source_root=source_root or (tmp_path / "source"),
        read_only_host_paths=read_only,
        read_write_host_paths=read_write,
        environment_keys=environment_keys,
        network_mode=network_mode,  # type: ignore[arg-type]
        mount_namespace_enforced=True,
        user_namespace_enforced=True,
        pid_namespace_enforced=True,
        ipc_namespace_enforced=ipc_namespace_enforced,
        network_namespace_enforced=network_namespace_enforced,
    )


def test_unrelated_sandbox_surfaces_are_isolated(tmp_path: Path) -> None:
    protected = tmp_path / "control"
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(protected,),
        protected_environment_keys=("PHIOS_CONTROL_HOME",),
        loopback_endpoints=("127.0.0.1:9042",),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(tmp_path),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "ISOLATED"
    assert receipt.control_plane_reachable is False
    assert receipt.mutation_reachable is False
    assert receipt.read_reachable_paths == ()
    assert receipt.write_reachable_paths == ()
    assert receipt.action_authority is False
    assert receipt.execution_authority is False
    assert len(receipt.receipt_sha256) == 64


def test_workspace_parent_of_control_plane_is_blocked(tmp_path: Path) -> None:
    source = tmp_path / "workspace"
    protected = source / ".phios-control"
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(protected,),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(tmp_path, source_root=source),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "BLOCKED"
    assert receipt.control_plane_reachable is True
    assert receipt.mutation_reachable is True
    assert receipt.write_reachable_paths == (str(protected.resolve()),)


def test_read_only_control_plane_bind_is_still_reachability_failure(tmp_path: Path) -> None:
    protected = tmp_path / "control"
    protected.mkdir()
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(protected,),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(tmp_path, read_only=(protected,)),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "BLOCKED"
    assert receipt.control_plane_reachable is True
    assert receipt.mutation_reachable is False
    assert receipt.read_reachable_paths == (str(protected.resolve()),)
    assert receipt.write_reachable_paths == ()


def test_read_write_bind_to_control_plane_is_mutation_reachable(tmp_path: Path) -> None:
    protected = tmp_path / "control"
    protected.mkdir()
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(protected,),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(tmp_path, read_write=(protected,)),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "BLOCKED"
    assert receipt.mutation_reachable is True
    assert receipt.write_reachable_paths == (str(protected.resolve()),)


def test_protected_environment_surface_is_blocked(tmp_path: Path) -> None:
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(tmp_path / "control",),
        protected_environment_keys=("PHIOS_CONTROL_HOME",),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(
            tmp_path,
            environment_keys=("NPM_CONFIG_OFFLINE", "PHIOS_CONTROL_HOME"),
        ),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "BLOCKED"
    assert receipt.exposed_environment_keys == ("PHIOS_CONTROL_HOME",)
    assert receipt.mutation_reachable is True


def test_inherited_network_blocks_declared_loopback_control_surface(
    tmp_path: Path,
) -> None:
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(tmp_path / "control",),
        loopback_endpoints=("127.0.0.1:9042",),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(
            tmp_path,
            network_mode="inherit",
            network_namespace_enforced=False,
        ),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "BLOCKED"
    assert receipt.reachable_loopback_endpoints == ("127.0.0.1:9042",)
    assert receipt.mutation_reachable is True


def test_denied_network_requires_explicit_namespace_evidence(tmp_path: Path) -> None:
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(tmp_path / "control",),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(
            tmp_path,
            network_mode="deny",
            network_namespace_enforced=False,
        ),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "UNKNOWN"
    assert receipt.control_plane_reachable is False
    assert receipt.namespace_gaps == ("network_namespace",)


def test_missing_ipc_namespace_is_unknown_not_isolated(tmp_path: Path) -> None:
    surfaces = ControlPlaneSurfaceMap.build(
        protected_paths=(tmp_path / "control",),
        source="test",
    )

    receipt = evaluate_control_plane_isolation(
        surface_map=surfaces,
        snapshot=_snapshot(tmp_path, ipc_namespace_enforced=False),
        evaluated_at="2026-09-21T16:30:00+00:00",
    )

    assert receipt.status == "UNKNOWN"
    assert receipt.namespace_gaps == ("ipc_namespace",)
