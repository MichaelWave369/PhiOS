from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

CONTROL_PLANE_SURFACE_MAP_SCHEMA_VERSION = "phios.control_plane_surface_map.v0.1"
CONTROL_PLANE_ISOLATION_RECEIPT_SCHEMA_VERSION = "phios.control_plane_isolation_receipt.v0.1"

ControlPlaneIsolationStatus = Literal["ISOLATED", "BLOCKED", "UNKNOWN"]
NetworkMode = Literal["deny", "inherit"]

_ENV_KEY_RE = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")


class ControlPlaneIsolationError(ValueError):
    """Raised when control-plane reachability evidence is malformed."""


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ControlPlaneIsolationError(
            "control-plane evidence must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _absolute_path(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ControlPlaneIsolationError(f"{label} must be a non-empty absolute path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ControlPlaneIsolationError(f"{label} must be absolute")
    return str(path.resolve(strict=False))


def _utc(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ControlPlaneIsolationError(
            "evaluated_at must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise ControlPlaneIsolationError("evaluated_at must be timezone-aware")
    return parsed.astimezone(UTC).isoformat()


def _paths_overlap(left: str, right: str) -> bool:
    a = Path(left)
    b = Path(right)
    try:
        a.relative_to(b)
        return True
    except ValueError:
        pass
    try:
        b.relative_to(a)
        return True
    except ValueError:
        return False


@dataclass(frozen=True)
class ControlPlaneSurfaceMap:
    """Explicit host surfaces capable of influencing PhiOS control state."""

    protected_paths: tuple[str, ...]
    protected_environment_keys: tuple[str, ...] = ()
    loopback_endpoints: tuple[str, ...] = ()
    source: str = "phios-default"
    schema_version: str = CONTROL_PLANE_SURFACE_MAP_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != CONTROL_PLANE_SURFACE_MAP_SCHEMA_VERSION:
            raise ControlPlaneIsolationError("unsupported control-plane surface-map schema")
        if not self.source.strip():
            raise ControlPlaneIsolationError("surface-map source must be non-empty")
        normalized_paths = tuple(
            sorted({_absolute_path(value, "protected path") for value in self.protected_paths})
        )
        if normalized_paths != self.protected_paths:
            raise ControlPlaneIsolationError(
                "protected_paths must be normalized, unique, and sorted"
            )
        normalized_keys = tuple(sorted(set(self.protected_environment_keys)))
        if normalized_keys != self.protected_environment_keys:
            raise ControlPlaneIsolationError(
                "protected_environment_keys must be unique and sorted"
            )
        for key in self.protected_environment_keys:
            if not _ENV_KEY_RE.fullmatch(key):
                raise ControlPlaneIsolationError(
                    f"invalid protected environment key: {key}"
                )
        if tuple(sorted(set(self.loopback_endpoints))) != self.loopback_endpoints:
            raise ControlPlaneIsolationError(
                "loopback_endpoints must be unique and sorted"
            )
        if any(not endpoint.strip() for endpoint in self.loopback_endpoints):
            raise ControlPlaneIsolationError("loopback endpoints must be non-empty")

    @classmethod
    def build(
        cls,
        *,
        protected_paths: tuple[Path | str, ...],
        protected_environment_keys: tuple[str, ...] = (),
        loopback_endpoints: tuple[str, ...] = (),
        source: str = "phios-default",
    ) -> "ControlPlaneSurfaceMap":
        return cls(
            protected_paths=tuple(
                sorted(
                    {
                        _absolute_path(str(value), "protected path")
                        for value in protected_paths
                    }
                )
            ),
            protected_environment_keys=tuple(
                sorted(set(protected_environment_keys))
            ),
            loopback_endpoints=tuple(sorted(set(loopback_endpoints))),
            source=source,
        )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "source": self.source,
            "protected_paths": list(self.protected_paths),
            "protected_environment_keys": list(self.protected_environment_keys),
            "loopback_endpoints": list(self.loopback_endpoints),
        }

    def sha256(self) -> str:
        return _sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["surface_map_sha256"] = self.sha256()
        return payload


@dataclass(frozen=True)
class SandboxReachabilitySnapshot:
    """Concrete actor-visible surfaces for one sandbox execution boundary."""

    source_root: str
    read_only_host_paths: tuple[str, ...]
    read_write_host_paths: tuple[str, ...]
    environment_keys: tuple[str, ...]
    network_mode: NetworkMode
    mount_namespace_enforced: bool
    user_namespace_enforced: bool
    pid_namespace_enforced: bool
    ipc_namespace_enforced: bool
    network_namespace_enforced: bool

    @classmethod
    def build(
        cls,
        *,
        source_root: Path | str,
        read_only_host_paths: tuple[Path | str, ...] = (),
        read_write_host_paths: tuple[Path | str, ...] = (),
        environment_keys: tuple[str, ...] = (),
        network_mode: NetworkMode,
        mount_namespace_enforced: bool,
        user_namespace_enforced: bool,
        pid_namespace_enforced: bool,
        ipc_namespace_enforced: bool,
        network_namespace_enforced: bool,
    ) -> "SandboxReachabilitySnapshot":
        if network_mode not in {"deny", "inherit"}:
            raise ControlPlaneIsolationError("network_mode must be deny or inherit")
        return cls(
            source_root=_absolute_path(str(source_root), "source_root"),
            read_only_host_paths=tuple(
                sorted(
                    {
                        _absolute_path(str(value), "read-only host path")
                        for value in read_only_host_paths
                    }
                )
            ),
            read_write_host_paths=tuple(
                sorted(
                    {
                        _absolute_path(str(value), "read-write host path")
                        for value in read_write_host_paths
                    }
                )
            ),
            environment_keys=tuple(sorted(set(environment_keys))),
            network_mode=network_mode,
            mount_namespace_enforced=bool(mount_namespace_enforced),
            user_namespace_enforced=bool(user_namespace_enforced),
            pid_namespace_enforced=bool(pid_namespace_enforced),
            ipc_namespace_enforced=bool(ipc_namespace_enforced),
            network_namespace_enforced=bool(network_namespace_enforced),
        )

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def sha256(self) -> str:
        return _sha256(self.to_dict())


@dataclass(frozen=True)
class ControlPlaneIsolationReceipt:
    schema_version: str
    receipt_id: str
    evaluated_at: str
    status: ControlPlaneIsolationStatus
    reason: str
    surface_map_sha256: str
    snapshot_sha256: str
    read_reachable_paths: tuple[str, ...]
    write_reachable_paths: tuple[str, ...]
    exposed_environment_keys: tuple[str, ...]
    reachable_loopback_endpoints: tuple[str, ...]
    namespace_gaps: tuple[str, ...]
    control_plane_reachable: bool
    mutation_reachable: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "evaluated_at": self.evaluated_at,
            "status": self.status,
            "reason": self.reason,
            "surface_map_sha256": self.surface_map_sha256,
            "snapshot_sha256": self.snapshot_sha256,
            "read_reachable_paths": list(self.read_reachable_paths),
            "write_reachable_paths": list(self.write_reachable_paths),
            "exposed_environment_keys": list(self.exposed_environment_keys),
            "reachable_loopback_endpoints": list(self.reachable_loopback_endpoints),
            "namespace_gaps": list(self.namespace_gaps),
            "control_plane_reachable": self.control_plane_reachable,
            "mutation_reachable": self.mutation_reachable,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


def default_phios_control_plane_surfaces() -> ControlPlaneSurfaceMap:
    """Current host control surfaces that a build sandbox must not observe."""

    env_reflex = os.getenv("PHIOS_REFLEX_HOME", "").strip()
    reflex_root = (
        Path(env_reflex).expanduser()
        if env_reflex
        else Path.home() / ".phios" / "reflex"
    )
    spine_ledger = Path.home() / ".phios" / "spine-v0.1" / "ledger"
    return ControlPlaneSurfaceMap.build(
        protected_paths=(reflex_root, spine_ledger),
        protected_environment_keys=("PHIOS_REFLEX_HOME",),
        source="phios-current-control-plane-v0.1",
    )


def evaluate_control_plane_isolation(
    *,
    surface_map: ControlPlaneSurfaceMap,
    snapshot: SandboxReachabilitySnapshot,
    evaluated_at: str,
) -> ControlPlaneIsolationReceipt:
    """Evaluate reachability only; this receipt grants no authority."""

    evaluated = _utc(evaluated_at)
    source_and_read = (
        snapshot.source_root,
        *snapshot.read_only_host_paths,
        *snapshot.read_write_host_paths,
    )
    source_and_write = (snapshot.source_root, *snapshot.read_write_host_paths)

    read_reachable = tuple(
        sorted(
            {
                protected
                for protected in surface_map.protected_paths
                if any(_paths_overlap(path, protected) for path in source_and_read)
            }
        )
    )
    write_reachable = tuple(
        sorted(
            {
                protected
                for protected in surface_map.protected_paths
                if any(_paths_overlap(path, protected) for path in source_and_write)
            }
        )
    )
    exposed_env = tuple(
        sorted(set(snapshot.environment_keys) & set(surface_map.protected_environment_keys))
    )
    reachable_loopback = (
        surface_map.loopback_endpoints
        if snapshot.network_mode == "inherit"
        else ()
    )

    namespace_gaps: list[str] = []
    if not snapshot.mount_namespace_enforced:
        namespace_gaps.append("mount_namespace")
    if not snapshot.user_namespace_enforced:
        namespace_gaps.append("user_namespace")
    if not snapshot.pid_namespace_enforced:
        namespace_gaps.append("pid_namespace")
    if not snapshot.ipc_namespace_enforced:
        namespace_gaps.append("ipc_namespace")
    if snapshot.network_mode == "deny" and not snapshot.network_namespace_enforced:
        namespace_gaps.append("network_namespace")

    control_plane_reachable = bool(
        read_reachable
        or write_reachable
        or exposed_env
        or reachable_loopback
    )
    mutation_reachable = bool(
        write_reachable
        or exposed_env
        or reachable_loopback
    )

    if control_plane_reachable:
        status: ControlPlaneIsolationStatus = "BLOCKED"
        reason = "declared_control_plane_surface_reachable"
    elif namespace_gaps:
        status = "UNKNOWN"
        reason = "required_namespace_evidence_incomplete"
    else:
        status = "ISOLATED"
        reason = "declared_control_plane_surfaces_unreachable"

    surface_sha = surface_map.sha256()
    snapshot_sha = snapshot.sha256()
    seed = _sha256(
        {
            "schema_version": CONTROL_PLANE_ISOLATION_RECEIPT_SCHEMA_VERSION,
            "surface_map_sha256": surface_sha,
            "snapshot_sha256": snapshot_sha,
            "evaluated_at": evaluated,
        }
    )
    receipt_id = str(
        uuid.uuid5(uuid.NAMESPACE_URL, f"phios.control-plane-isolation:{seed}")
    )
    body = {
        "schema_version": CONTROL_PLANE_ISOLATION_RECEIPT_SCHEMA_VERSION,
        "receipt_id": receipt_id,
        "evaluated_at": evaluated,
        "status": status,
        "reason": reason,
        "surface_map_sha256": surface_sha,
        "snapshot_sha256": snapshot_sha,
        "read_reachable_paths": list(read_reachable),
        "write_reachable_paths": list(write_reachable),
        "exposed_environment_keys": list(exposed_env),
        "reachable_loopback_endpoints": list(reachable_loopback),
        "namespace_gaps": namespace_gaps,
        "control_plane_reachable": control_plane_reachable,
        "mutation_reachable": mutation_reachable,
        "action_authority": False,
        "execution_authority": False,
    }
    return ControlPlaneIsolationReceipt(
        schema_version=CONTROL_PLANE_ISOLATION_RECEIPT_SCHEMA_VERSION,
        receipt_id=receipt_id,
        evaluated_at=evaluated,
        status=status,
        reason=reason,
        surface_map_sha256=surface_sha,
        snapshot_sha256=snapshot_sha,
        read_reachable_paths=read_reachable,
        write_reachable_paths=write_reachable,
        exposed_environment_keys=exposed_env,
        reachable_loopback_endpoints=reachable_loopback,
        namespace_gaps=tuple(namespace_gaps),
        control_plane_reachable=control_plane_reachable,
        mutation_reachable=mutation_reachable,
        action_authority=False,
        execution_authority=False,
        receipt_sha256=_sha256(body),
    )
