"""Trusted local PhiVessel execution mount for bridge v0.2.

The default Ghost-Walk host may mount the already-governed v0.35 execution
handoff only when a local, content-addressed execution manifest is present and
valid. The manifest is trusted local configuration; browser/model callers
cannot supply or mutate it through the bridge.

No manifest -> no execution mount.
Invalid manifest -> fail closed.
Changed static trust configuration -> current AuthorityEpoch becomes unavailable
until the host is restarted against the new manifest.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping

from phios.authority_epoch import AuthorityEpoch, AuthorityEpochContractError
from phios.enforcement_profile import (
    EnforcementProfileContractError,
    EnforcementRule,
)
from phios.macro_action_lease_service import (
    GhostWalkActionLeaseError,
    GhostWalkActionLeaseService,
    GhostWalkLeasePolicy,
    GhostWalkLeasePolicyRegistry,
)
from phios.macro_authorization_decision import (
    GhostWalkAuthorizationDecisionService,
)
from phios.macro_capability_binding import (
    GhostWalkCapabilityBindingError,
    GhostWalkCapabilityBindingService,
    GhostWalkCapabilityMapping,
    GhostWalkCapabilityMappingRegistry,
)
from phios.macro_desktop_interaction import (
    GovernedDesktopClickExecutor,
    install_desktop_click_capability,
)
from phios.macro_lease_execution_handoff import (
    GhostWalkLeaseExecutionHandoff,
)
from phios.macro_authority_request import GhostWalkAuthorityRequestService
from phios.spine.ledger import RealityLedger
from phios.spine.runtime import PhiOSSpine

PHIVESSEL_LOCAL_EXECUTION_MANIFEST_SCHEMA_VERSION = (
    "phios.phivessel_local_execution_manifest.v0.1"
)
DEFAULT_EXECUTION_MANIFEST_RELATIVE_PATH = Path(
    "config/phivessel-execution.json"
)
EXECUTION_MANIFEST_ENV = "PHIOS_PHIVESSEL_EXECUTION_MANIFEST"


class PhiVesselLocalExecutionError(ValueError):
    """Raised when trusted local execution configuration is invalid."""


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
        raise PhiVesselLocalExecutionError(
            "local execution manifest must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 512,
) -> str:
    if not isinstance(value, str) or not value:
        raise PhiVesselLocalExecutionError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise PhiVesselLocalExecutionError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise PhiVesselLocalExecutionError(
            f"{field} contains control characters"
        )
    return value


def _require_string_array(
    value: object,
    field: str,
    *,
    maximum_items: int = 64,
) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise PhiVesselLocalExecutionError(
            f"{field} must be an array"
        )
    if len(value) > maximum_items:
        raise PhiVesselLocalExecutionError(
            f"{field} exceeds {maximum_items} items"
        )
    items = tuple(
        _require_text(item, f"{field} item", maximum=256)
        for item in value
    )
    if tuple(sorted(set(items))) != items:
        raise PhiVesselLocalExecutionError(
            f"{field} must be sorted and unique"
        )
    return items


def _parse_lease_policy(value: object) -> GhostWalkLeasePolicy:
    if not isinstance(value, Mapping):
        raise PhiVesselLocalExecutionError(
            "lease policy must be an object"
        )
    data = dict(value)
    expected = {
        "schema_version",
        "policy_id",
        "principal_id",
        "issuer_id",
        "capability_id",
        "capability_version",
        "permissions_authorized",
        "effects_declared",
        "enforcement_rules",
        "accepted_unenforced_effects",
        "max_lease_seconds",
        "effect_performed",
        "operational_authority",
        "action_authority",
        "execution_authority",
        "policy_sha256",
    }
    if set(data) != expected:
        raise PhiVesselLocalExecutionError(
            "lease policy fields do not match contract"
        )

    rules_raw = data["enforcement_rules"]
    if not isinstance(rules_raw, list):
        raise PhiVesselLocalExecutionError(
            "enforcement_rules must be an array"
        )
    try:
        rules = tuple(
            EnforcementRule.from_dict(item)
            for item in rules_raw
        )
    except EnforcementProfileContractError as exc:
        raise PhiVesselLocalExecutionError(
            "lease policy contains invalid enforcement rule"
        ) from exc

    bool_fields = (
        "effect_performed",
        "operational_authority",
        "action_authority",
        "execution_authority",
    )
    for field in bool_fields:
        if not isinstance(data[field], bool):
            raise PhiVesselLocalExecutionError(
                f"{field} must be Boolean"
            )
    seconds = data["max_lease_seconds"]
    if isinstance(seconds, bool) or not isinstance(seconds, int):
        raise PhiVesselLocalExecutionError(
            "max_lease_seconds must be an integer"
        )
    policy = GhostWalkLeasePolicy(
        schema_version=_require_text(
            data["schema_version"],
            "schema_version",
            maximum=128,
        ),
        policy_id=_require_text(
            data["policy_id"],
            "policy_id",
            maximum=128,
        ),
        principal_id=_require_text(
            data["principal_id"],
            "principal_id",
            maximum=256,
        ),
        issuer_id=_require_text(
            data["issuer_id"],
            "issuer_id",
            maximum=256,
        ),
        capability_id=_require_text(
            data["capability_id"],
            "capability_id",
            maximum=256,
        ),
        capability_version=_require_text(
            data["capability_version"],
            "capability_version",
            maximum=128,
        ),
        permissions_authorized=_require_string_array(
            data["permissions_authorized"],
            "permissions_authorized",
        ),
        effects_declared=_require_string_array(
            data["effects_declared"],
            "effects_declared",
        ),
        enforcement_rules=rules,
        accepted_unenforced_effects=_require_string_array(
            data["accepted_unenforced_effects"],
            "accepted_unenforced_effects",
        ),
        max_lease_seconds=seconds,
        effect_performed=data["effect_performed"],
        operational_authority=data["operational_authority"],
        action_authority=data["action_authority"],
        execution_authority=data["execution_authority"],
    )
    claimed = _require_text(
        data["policy_sha256"],
        "policy_sha256",
        maximum=64,
    )
    if claimed != policy.policy_sha256:
        raise PhiVesselLocalExecutionError(
            "lease policy SHA-256 mismatch"
        )
    return policy


@dataclass(frozen=True, slots=True)
class PhiVesselLocalExecutionManifest:
    enabled: bool
    desktop_executor_enabled: bool
    mappings: tuple[GhostWalkCapabilityMapping, ...]
    lease_policies: tuple[GhostWalkLeasePolicy, ...]
    authority_epoch: AuthorityEpoch
    manifest_sha256: str
    schema_version: str = (
        PHIVESSEL_LOCAL_EXECUTION_MANIFEST_SCHEMA_VERSION
    )

    @classmethod
    def build(
        cls,
        *,
        enabled: bool,
        desktop_executor_enabled: bool,
        mappings: tuple[GhostWalkCapabilityMapping, ...],
        lease_policies: tuple[GhostWalkLeasePolicy, ...],
        authority_epoch: AuthorityEpoch,
    ) -> "PhiVesselLocalExecutionManifest":
        body = {
            "schema_version": (
                PHIVESSEL_LOCAL_EXECUTION_MANIFEST_SCHEMA_VERSION
            ),
            "enabled": enabled,
            "desktop_executor_enabled": desktop_executor_enabled,
            "mappings": [
                item.to_dict() for item in mappings
            ],
            "lease_policies": [
                item.to_dict() for item in lease_policies
            ],
            "authority_epoch": authority_epoch.to_dict(),
        }
        item = cls(
            enabled=enabled,
            desktop_executor_enabled=desktop_executor_enabled,
            mappings=mappings,
            lease_policies=lease_policies,
            authority_epoch=authority_epoch,
            manifest_sha256=_canonical_sha256(body),
        )
        item._validate_cross_contract()
        return item

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> "PhiVesselLocalExecutionManifest":
        if not isinstance(value, Mapping):
            raise PhiVesselLocalExecutionError(
                "local execution manifest must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "enabled",
            "desktop_executor_enabled",
            "mappings",
            "lease_policies",
            "authority_epoch",
            "manifest_sha256",
        }
        if set(data) != expected:
            raise PhiVesselLocalExecutionError(
                "local execution manifest fields do not match contract"
            )
        if not isinstance(data["enabled"], bool):
            raise PhiVesselLocalExecutionError(
                "enabled must be Boolean"
            )
        if not isinstance(data["desktop_executor_enabled"], bool):
            raise PhiVesselLocalExecutionError(
                "desktop_executor_enabled must be Boolean"
            )

        mappings_raw = data["mappings"]
        if not isinstance(mappings_raw, list):
            raise PhiVesselLocalExecutionError(
                "mappings must be an array"
            )
        try:
            mappings = tuple(
                GhostWalkCapabilityMapping.from_dict(item)
                for item in mappings_raw
            )
        except GhostWalkCapabilityBindingError as exc:
            raise PhiVesselLocalExecutionError(
                "manifest contains invalid capability mapping"
            ) from exc

        policies_raw = data["lease_policies"]
        if not isinstance(policies_raw, list):
            raise PhiVesselLocalExecutionError(
                "lease_policies must be an array"
            )
        policies = tuple(
            _parse_lease_policy(item)
            for item in policies_raw
        )
        try:
            epoch = AuthorityEpoch.from_dict(
                data["authority_epoch"]
            )
        except AuthorityEpochContractError as exc:
            raise PhiVesselLocalExecutionError(
                "manifest contains invalid AuthorityEpoch"
            ) from exc

        body = {
            "schema_version": data["schema_version"],
            "enabled": data["enabled"],
            "desktop_executor_enabled": (
                data["desktop_executor_enabled"]
            ),
            "mappings": [item.to_dict() for item in mappings],
            "lease_policies": [
                item.to_dict() for item in policies
            ],
            "authority_epoch": epoch.to_dict(),
        }
        claimed = _require_text(
            data["manifest_sha256"],
            "manifest_sha256",
            maximum=64,
        )
        actual = _canonical_sha256(body)
        if claimed != actual:
            raise PhiVesselLocalExecutionError(
                "local execution manifest SHA-256 mismatch"
            )

        manifest = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=128,
            ),
            enabled=data["enabled"],
            desktop_executor_enabled=(
                data["desktop_executor_enabled"]
            ),
            mappings=mappings,
            lease_policies=policies,
            authority_epoch=epoch,
            manifest_sha256=claimed,
        )
        manifest._validate_cross_contract()
        return manifest

    @classmethod
    def read(
        cls,
        path: Path,
    ) -> "PhiVesselLocalExecutionManifest":
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
        except FileNotFoundError:
            raise
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PhiVesselLocalExecutionError(
                "local execution manifest could not be read safely"
            ) from exc
        return cls.from_dict(value)

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "enabled": self.enabled,
            "desktop_executor_enabled": self.desktop_executor_enabled,
            "mappings": [
                item.to_dict() for item in self.mappings
            ],
            "lease_policies": [
                item.to_dict() for item in self.lease_policies
            ],
            "authority_epoch": self.authority_epoch.to_dict(),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        actual = _canonical_sha256(payload)
        if actual != self.manifest_sha256:
            raise PhiVesselLocalExecutionError(
                "manifest identity differs from canonical body"
            )
        payload["manifest_sha256"] = self.manifest_sha256
        return payload

    @property
    def static_config_sha256(self) -> str:
        return _canonical_sha256(
            {
                "schema_version": self.schema_version,
                "enabled": self.enabled,
                "desktop_executor_enabled": (
                    self.desktop_executor_enabled
                ),
                "mappings": [
                    item.to_dict() for item in self.mappings
                ],
                "lease_policies": [
                    item.to_dict() for item in self.lease_policies
                ],
            }
        )

    def _validate_cross_contract(self) -> None:
        if self.schema_version != (
            PHIVESSEL_LOCAL_EXECUTION_MANIFEST_SCHEMA_VERSION
        ):
            raise PhiVesselLocalExecutionError(
                "unsupported local execution manifest schema"
            )
        if self.enabled:
            if not self.mappings:
                raise PhiVesselLocalExecutionError(
                    "enabled execution manifest requires a mapping"
                )
            if not self.lease_policies:
                raise PhiVesselLocalExecutionError(
                    "enabled execution manifest requires a lease policy"
                )
        principals = {
            policy.principal_id
            for policy in self.lease_policies
        }
        if len(principals) > 1:
            raise PhiVesselLocalExecutionError(
                "all lease policies must share one principal"
            )
        if principals and self.authority_epoch.principal_id not in principals:
            raise PhiVesselLocalExecutionError(
                "AuthorityEpoch principal differs from lease policy principal"
            )
        ceiling = set(self.authority_epoch.ceiling)
        for policy in self.lease_policies:
            if not set(policy.permissions_authorized).issubset(
                ceiling
            ):
                raise PhiVesselLocalExecutionError(
                    "lease policy permission exceeds AuthorityEpoch ceiling"
                )


class ManifestAuthorityEpochProvider:
    """Re-read current authority while freezing static execution trust config."""

    def __init__(
        self,
        *,
        path: Path,
        expected_static_config_sha256: str,
    ) -> None:
        self.path = path
        self.expected_static_config_sha256 = (
            expected_static_config_sha256
        )

    def current(self) -> AuthorityEpoch | None:
        try:
            manifest = PhiVesselLocalExecutionManifest.read(
                self.path
            )
        except FileNotFoundError:
            return None
        except PhiVesselLocalExecutionError as exc:
            raise AuthorityEpochContractError(str(exc)) from exc
        if not manifest.enabled:
            return None
        if (
            manifest.static_config_sha256
            != self.expected_static_config_sha256
        ):
            raise AuthorityEpochContractError(
                "local execution static trust configuration changed; "
                "restart is required"
            )
        return manifest.authority_epoch


@dataclass(frozen=True, slots=True)
class PhiVesselLocalExecutionMount:
    manifest_path: Path
    manifest_sha256: str
    spine: PhiOSSpine
    authorization_decisions: GhostWalkAuthorizationDecisionService
    capability_bindings: GhostWalkCapabilityBindingService
    lease_policies: GhostWalkLeasePolicyRegistry
    authority_epochs: ManifestAuthorityEpochProvider
    action_leases: GhostWalkActionLeaseService
    execution_handoff: GhostWalkLeaseExecutionHandoff


def execution_manifest_path(
    *,
    state_root: Path,
    environ: Mapping[str, str] | None = None,
) -> Path:
    env = os.environ if environ is None else environ
    configured = env.get(EXECUTION_MANIFEST_ENV)
    if configured:
        return Path(configured).expanduser()
    return state_root.expanduser() / DEFAULT_EXECUTION_MANIFEST_RELATIVE_PATH


def build_local_execution_mount(
    *,
    state_root: Path,
    ledger: RealityLedger,
    authority_requests: GhostWalkAuthorityRequestService,
    authorizer_id: str,
    manifest_path: Path,
    desktop_executor_factory: (
        Callable[[PhiOSSpine], GovernedDesktopClickExecutor] | None
    ) = None,
) -> PhiVesselLocalExecutionMount | None:
    """Build the real v0.35 executor only from trusted local manifest state."""

    try:
        manifest = PhiVesselLocalExecutionManifest.read(
            manifest_path
        )
    except FileNotFoundError:
        return None
    if not manifest.enabled:
        return None
    if not manifest.desktop_executor_enabled:
        raise PhiVesselLocalExecutionError(
            "enabled manifest must explicitly enable desktop executor"
        )

    mapping_registry = GhostWalkCapabilityMappingRegistry(
        manifest.mappings
    )
    policy_registry = GhostWalkLeasePolicyRegistry(
        manifest.lease_policies
    )
    authority_provider = ManifestAuthorityEpochProvider(
        path=manifest_path,
        expected_static_config_sha256=(
            manifest.static_config_sha256
        ),
    )

    authorization_decisions = GhostWalkAuthorizationDecisionService(
        ledger=ledger,
        authority_requests=authority_requests,
        authorizer_id=authorizer_id,
    )
    capability_bindings = GhostWalkCapabilityBindingService(
        ledger=ledger,
        authorization_decisions=authorization_decisions,
        registry=mapping_registry,
    )

    spine = PhiOSSpine(
        state_root=state_root,
        allowed_permissions=manifest.authority_epoch.grants,
    )
    factory = desktop_executor_factory or (
        lambda runtime: GovernedDesktopClickExecutor.from_windows(
            spine=runtime
        )
    )
    desktop_executor = factory(spine)
    install_desktop_click_capability(
        spine=spine,
        executor=desktop_executor,
    )

    action_leases = GhostWalkActionLeaseService(
        ledger=ledger,
        capability_bindings=capability_bindings,
        policies=policy_registry,
        authority_epochs=authority_provider,
    )
    execution_handoff = GhostWalkLeaseExecutionHandoff(
        ledger=ledger,
        capability_bindings=capability_bindings,
        policies=policy_registry,
        authority_epochs=authority_provider,
        spine=spine,
    )
    return PhiVesselLocalExecutionMount(
        manifest_path=manifest_path,
        manifest_sha256=manifest.manifest_sha256,
        spine=spine,
        authorization_decisions=authorization_decisions,
        capability_bindings=capability_bindings,
        lease_policies=policy_registry,
        authority_epochs=authority_provider,
        action_leases=action_leases,
        execution_handoff=execution_handoff,
    )
