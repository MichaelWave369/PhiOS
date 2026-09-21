from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from typing import Any, Literal, Mapping

from .models import RealityClaim, RealityClaimKind, RealityVerdict

OBSERVATION_FRONTIER_SCHEMA_VERSION = "phios.observation_frontier.v0.1"
OBSERVABILITY_BOUNDARY_RECEIPT_SCHEMA_VERSION = (
    "phios.observability_boundary_receipt.v0.1"
)

CoverageStatus = Literal["COVERED", "PARTIAL", "UNOBSERVED"]
FrontierStatus = Literal["COVERED", "PARTIAL", "UNOBSERVED"]
ObservabilityStatus = Literal["BOUNDED", "PARTIAL", "OUTSIDE_FRONTIER"]

_HTTP_SINGLE_KINDS = {
    RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE,
    RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE,
    RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
    RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
}

_HTTP_SERIES_KINDS = {
    RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_TEMPORAL_ENVELOPE_MIXED_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_NUMERIC_TRANSITION_CONTRACT,
}

_SEMANTIC_HTTP_KINDS = {
    RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE,
    RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT,
    RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
    RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
    *_HTTP_SERIES_KINDS,
}


class ObservationFrontierContractError(ValueError):
    """Raised when observation-frontier evidence is malformed."""


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
        raise ObservationFrontierContractError(
            "observation-frontier evidence must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _provider_name(provider: object | None, fallback: str) -> str:
    if provider is None:
        return fallback
    value = getattr(provider, "name", None)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def _claim_target(claim: RealityClaim) -> str:
    if claim.kind is RealityClaimKind.SOURCE_CONTAINS_TEXT:
        return "cited_evidence_set:" + _sha256(list(claim.evidence_refs))
    if claim.kind is RealityClaimKind.WORLD_STATE:
        return "unbounded_world_state"
    if claim.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
        return f"interface:{claim.interface_name or '<missing>'}"
    if claim.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
        address = claim.local_address or "*"
        return f"tcp-listener:{address}:{claim.local_port}"
    if claim.kind in _HTTP_SINGLE_KINDS | _HTTP_SERIES_KINDS:
        return f"local-http:{claim.http_url or '<missing>'}"
    return f"claim-kind:{claim.kind.value}"


def _claim_surface(claim: RealityClaim) -> str:
    if claim.kind is RealityClaimKind.SOURCE_CONTAINS_TEXT:
        return "source_content"
    if claim.kind is RealityClaimKind.WORLD_STATE:
        return "world_state"
    if claim.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
        return "local_interface_state"
    if claim.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
        return "local_tcp_listener_state"
    if claim.kind is RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE:
        return "local_http_response_state"
    if claim.kind in _SEMANTIC_HTTP_KINDS:
        return "local_http_semantic_state"
    return "unknown"


def _is_explicit_negative_state_claim(claim: RealityClaim) -> bool:
    if claim.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
        return claim.expected_is_up is False
    if claim.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
        return claim.expected_listening is False
    return False


@dataclass(frozen=True, slots=True)
class ObservationCoverage:
    claim_id: str
    claim_kind: str
    surface: str
    target: str
    observer_id: str
    observer_version: str | None
    coverage_kind: str
    status: CoverageStatus
    evidence_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    explicit_negative_state_claim: bool
    bounded_negative_state_support: bool

    def body_dict(self) -> dict[str, object]:
        return {
            "claim_id": self.claim_id,
            "claim_kind": self.claim_kind,
            "surface": self.surface,
            "target": self.target,
            "observer_id": self.observer_id,
            "observer_version": self.observer_version,
            "coverage_kind": self.coverage_kind,
            "status": self.status,
            "evidence_refs": list(self.evidence_refs),
            "limitations": list(self.limitations),
            "explicit_negative_state_claim": self.explicit_negative_state_claim,
            "bounded_negative_state_support": self.bounded_negative_state_support,
        }

    @property
    def coverage_sha256(self) -> str:
        return _sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["coverage_sha256"] = self.coverage_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ObservationFrontier:
    schema_version: str
    status: FrontierStatus
    entries: tuple[ObservationCoverage, ...]
    covered_claim_ids: tuple[str, ...]
    partial_claim_ids: tuple[str, ...]
    unobserved_claim_ids: tuple[str, ...]
    frontier_sha256: str

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "entries": [entry.to_dict() for entry in self.entries],
            "covered_claim_ids": list(self.covered_claim_ids),
            "partial_claim_ids": list(self.partial_claim_ids),
            "unobserved_claim_ids": list(self.unobserved_claim_ids),
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["frontier_sha256"] = self.frontier_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ObservabilityBoundaryReceipt:
    schema_version: str
    receipt_id: str
    packet_id: str
    task_id: str
    status: ObservabilityStatus
    observation_frontier_sha256: str
    covered_claim_ids: tuple[str, ...]
    partial_claim_ids: tuple[str, ...]
    unobserved_claim_ids: tuple[str, ...]
    explicit_negative_state_claim_ids: tuple[str, ...]
    bounded_negative_state_claim_ids: tuple[str, ...]
    unbounded_negative_state_claim_ids: tuple[str, ...]
    limitations: tuple[str, ...]
    operational_authority: bool
    action_authority: bool
    execution_authority: bool
    receipt_sha256: str

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "receipt_id": self.receipt_id,
            "packet_id": self.packet_id,
            "task_id": self.task_id,
            "status": self.status,
            "observation_frontier_sha256": self.observation_frontier_sha256,
            "covered_claim_ids": list(self.covered_claim_ids),
            "partial_claim_ids": list(self.partial_claim_ids),
            "unobserved_claim_ids": list(self.unobserved_claim_ids),
            "explicit_negative_state_claim_ids": list(
                self.explicit_negative_state_claim_ids
            ),
            "bounded_negative_state_claim_ids": list(
                self.bounded_negative_state_claim_ids
            ),
            "unbounded_negative_state_claim_ids": list(
                self.unbounded_negative_state_claim_ids
            ),
            "limitations": list(self.limitations),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


class ObservationFrontierBuilder:
    """Build bounded observation coverage from evidence actually produced."""

    def build(
        self,
        *,
        claims: tuple[RealityClaim, ...],
        results: tuple[Mapping[str, Any], ...],
        interface_provider: object | None,
        tcp_listener_provider: object | None,
        local_http_provider: object | None,
    ) -> ObservationFrontier:
        result_map = {
            str(result.get("claim_id")): result
            for result in results
            if isinstance(result.get("claim_id"), str)
        }
        entries: list[ObservationCoverage] = []

        for claim in claims:
            result = result_map.get(claim.claim_id, {})
            entries.append(
                self._coverage(
                    claim,
                    result,
                    interface_provider=interface_provider,
                    tcp_listener_provider=tcp_listener_provider,
                    local_http_provider=local_http_provider,
                )
            )

        covered = tuple(
            entry.claim_id for entry in entries if entry.status == "COVERED"
        )
        partial = tuple(
            entry.claim_id for entry in entries if entry.status == "PARTIAL"
        )
        unobserved = tuple(
            entry.claim_id for entry in entries if entry.status == "UNOBSERVED"
        )

        if not entries:
            status: FrontierStatus = "UNOBSERVED"
        elif len(covered) == len(entries):
            status = "COVERED"
        elif len(unobserved) == len(entries):
            status = "UNOBSERVED"
        else:
            status = "PARTIAL"

        body = {
            "schema_version": OBSERVATION_FRONTIER_SCHEMA_VERSION,
            "status": status,
            "entries": [entry.to_dict() for entry in entries],
            "covered_claim_ids": list(covered),
            "partial_claim_ids": list(partial),
            "unobserved_claim_ids": list(unobserved),
        }
        return ObservationFrontier(
            schema_version=OBSERVATION_FRONTIER_SCHEMA_VERSION,
            status=status,
            entries=tuple(entries),
            covered_claim_ids=covered,
            partial_claim_ids=partial,
            unobserved_claim_ids=unobserved,
            frontier_sha256=_sha256(body),
        )

    def boundary_receipt(
        self,
        *,
        packet_id: str,
        task_id: str,
        frontier: ObservationFrontier,
    ) -> ObservabilityBoundaryReceipt:
        negative = tuple(
            entry.claim_id
            for entry in frontier.entries
            if entry.explicit_negative_state_claim
        )
        bounded_negative = tuple(
            entry.claim_id
            for entry in frontier.entries
            if entry.bounded_negative_state_support
        )
        unbounded_negative = tuple(
            claim_id for claim_id in negative if claim_id not in bounded_negative
        )

        if frontier.status == "COVERED":
            status: ObservabilityStatus = "BOUNDED"
        elif frontier.status == "UNOBSERVED":
            status = "OUTSIDE_FRONTIER"
        else:
            status = "PARTIAL"

        limitations = (
            "negative_claims_apply_only_within_declared_observation_frontier",
            "absence_of_observation_is_not_observation_of_global_absence",
            "point_in_time_observation_is_not_continuous_monitoring",
            "observer_coverage_does_not_grant_operational_authority",
        )
        receipt_seed = {
            "schema_version": OBSERVABILITY_BOUNDARY_RECEIPT_SCHEMA_VERSION,
            "packet_id": packet_id,
            "task_id": task_id,
            "observation_frontier_sha256": frontier.frontier_sha256,
        }
        receipt_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "phios.observability-boundary:" + _sha256(receipt_seed),
            )
        )
        body = {
            "schema_version": OBSERVABILITY_BOUNDARY_RECEIPT_SCHEMA_VERSION,
            "receipt_id": receipt_id,
            "packet_id": packet_id,
            "task_id": task_id,
            "status": status,
            "observation_frontier_sha256": frontier.frontier_sha256,
            "covered_claim_ids": list(frontier.covered_claim_ids),
            "partial_claim_ids": list(frontier.partial_claim_ids),
            "unobserved_claim_ids": list(frontier.unobserved_claim_ids),
            "explicit_negative_state_claim_ids": list(negative),
            "bounded_negative_state_claim_ids": list(bounded_negative),
            "unbounded_negative_state_claim_ids": list(unbounded_negative),
            "limitations": list(limitations),
            "operational_authority": False,
            "action_authority": False,
            "execution_authority": False,
        }
        return ObservabilityBoundaryReceipt(
            schema_version=OBSERVABILITY_BOUNDARY_RECEIPT_SCHEMA_VERSION,
            receipt_id=receipt_id,
            packet_id=packet_id,
            task_id=task_id,
            status=status,
            observation_frontier_sha256=frontier.frontier_sha256,
            covered_claim_ids=frontier.covered_claim_ids,
            partial_claim_ids=frontier.partial_claim_ids,
            unobserved_claim_ids=frontier.unobserved_claim_ids,
            explicit_negative_state_claim_ids=negative,
            bounded_negative_state_claim_ids=bounded_negative,
            unbounded_negative_state_claim_ids=unbounded_negative,
            limitations=limitations,
            operational_authority=False,
            action_authority=False,
            execution_authority=False,
            receipt_sha256=_sha256(body),
        )

    def annotate_results(
        self,
        *,
        results: tuple[Mapping[str, Any], ...],
        frontier: ObservationFrontier,
    ) -> tuple[dict[str, Any], ...]:
        coverage_by_claim = {
            entry.claim_id: entry for entry in frontier.entries
        }
        annotated: list[dict[str, Any]] = []
        for raw in results:
            item = dict(raw)
            claim_id = item.get("claim_id")
            coverage = (
                coverage_by_claim.get(claim_id)
                if isinstance(claim_id, str)
                else None
            )
            if coverage is not None:
                item["observation_coverage"] = coverage.to_dict()
                if coverage.bounded_negative_state_support:
                    item["negative_state_support_scope"] = (
                        "supported_only_within_observation_frontier"
                    )
            annotated.append(item)
        return tuple(annotated)

    def _coverage(
        self,
        claim: RealityClaim,
        result: Mapping[str, Any],
        *,
        interface_provider: object | None,
        tcp_listener_provider: object | None,
        local_http_provider: object | None,
    ) -> ObservationCoverage:
        if claim.kind is RealityClaimKind.SOURCE_CONTAINS_TEXT:
            return self._source_coverage(claim, result)

        if claim.kind is RealityClaimKind.WORLD_STATE:
            return self._entry(
                claim=claim,
                observer_id="none",
                observer_version=None,
                coverage_kind="none",
                status="UNOBSERVED",
                evidence_refs=(),
                limitations=("independent_world_verifier_not_installed",),
                result=result,
            )

        if claim.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
            evidence_refs = self._evidence_refs(result)
            observed = isinstance(result.get("observed_is_up"), bool)
            if observed and evidence_refs:
                status: CoverageStatus = "COVERED"
                limitations: tuple[str, ...] = (
                    "exact_interface_point_in_time_only",
                )
            elif result.get("reason") == "local_interface_not_found":
                status = "PARTIAL"
                limitations = (
                    "provider_lookup_completed_without_persisted_absence_observation",
                    "exact_interface_point_in_time_only",
                )
            else:
                status = "UNOBSERVED"
                limitations = ("local_interface_observation_not_completed",)
            return self._entry(
                claim=claim,
                observer_id=str(
                    result.get("provider")
                    or _provider_name(interface_provider, "local-interface-provider")
                ),
                observer_version=self._optional_string(
                    result.get("provider_version")
                ),
                coverage_kind="exact_point",
                status=status,
                evidence_refs=evidence_refs,
                limitations=limitations,
                result=result,
            )

        if claim.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
            evidence_refs = self._evidence_refs(result)
            observed = isinstance(result.get("observed_listening"), bool)
            status = "COVERED" if observed and evidence_refs else "UNOBSERVED"
            limitations = (
                ("exact_listener_filter_point_in_time_only",)
                if status == "COVERED"
                else ("local_tcp_observation_not_completed",)
            )
            return self._entry(
                claim=claim,
                observer_id=str(
                    result.get("provider")
                    or _provider_name(tcp_listener_provider, "local-tcp-provider")
                ),
                observer_version=self._optional_string(
                    result.get("provider_version")
                ),
                coverage_kind="exact_point",
                status=status,
                evidence_refs=evidence_refs,
                limitations=limitations,
                result=result,
            )

        if claim.kind in _HTTP_SINGLE_KINDS:
            return self._http_single_coverage(
                claim,
                result,
                provider=local_http_provider,
            )

        if claim.kind in _HTTP_SERIES_KINDS:
            return self._http_series_coverage(
                claim,
                result,
                provider=local_http_provider,
            )

        return self._entry(
            claim=claim,
            observer_id="none",
            observer_version=None,
            coverage_kind="none",
            status="UNOBSERVED",
            evidence_refs=(),
            limitations=("claim_kind_has_no_observation_frontier_adapter",),
            result=result,
        )

    def _source_coverage(
        self,
        claim: RealityClaim,
        result: Mapping[str, Any],
    ) -> ObservationCoverage:
        records = result.get("evidence_records")
        readable_refs: list[str] = []
        if isinstance(records, list):
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                if record.get("status") != "readable_text":
                    continue
                ref = record.get("evidence_ref")
                if isinstance(ref, str) and ref:
                    readable_refs.append(ref)

        status: CoverageStatus = (
            "COVERED" if readable_refs else "UNOBSERVED"
        )
        limitations = (
            ("cited_readable_text_evidence_only",)
            if status == "COVERED"
            else ("no_readable_cited_text_evidence",)
        )
        return self._entry(
            claim=claim,
            observer_id="native-evidence-store",
            observer_version=None,
            coverage_kind="bounded_set",
            status=status,
            evidence_refs=tuple(dict.fromkeys(readable_refs)),
            limitations=limitations,
            result=result,
        )

    def _http_single_coverage(
        self,
        claim: RealityClaim,
        result: Mapping[str, Any],
        *,
        provider: object | None,
    ) -> ObservationCoverage:
        evidence_refs = self._evidence_refs(result)
        if not evidence_refs:
            status: CoverageStatus = "UNOBSERVED"
            limitations: tuple[str, ...] = (
                "local_http_observation_not_completed",
            )
        elif (
            claim.kind in _SEMANTIC_HTTP_KINDS
            and result.get("body_truncated") is True
        ):
            status = "PARTIAL"
            limitations = (
                "http_response_observed_but_semantic_body_truncated",
                "single_request_point_in_time_only",
            )
        else:
            status = "COVERED"
            limitations = ("single_request_point_in_time_only",)

        return self._entry(
            claim=claim,
            observer_id=str(
                result.get("provider")
                or _provider_name(provider, "local-http-provider")
            ),
            observer_version=self._optional_string(result.get("provider_version")),
            coverage_kind="exact_point",
            status=status,
            evidence_refs=evidence_refs,
            limitations=limitations,
            result=result,
        )

    def _http_series_coverage(
        self,
        claim: RealityClaim,
        result: Mapping[str, Any],
        *,
        provider: object | None,
    ) -> ObservationCoverage:
        sample_results = result.get("sample_results")
        samples = sample_results if isinstance(sample_results, list) else []
        requested_raw = result.get("observation_count_requested")
        requested = (
            requested_raw
            if isinstance(requested_raw, int) and not isinstance(requested_raw, bool)
            else None
        )
        evidence_refs: list[str] = []
        providers: list[str] = []
        versions: list[str] = []
        unresolved = 0

        for sample in samples:
            if not isinstance(sample, Mapping):
                continue
            ref = sample.get("observation_evidence_ref")
            if isinstance(ref, str) and ref:
                evidence_refs.append(ref)
            provider_name = sample.get("provider")
            if isinstance(provider_name, str) and provider_name:
                providers.append(provider_name)
            version = sample.get("provider_version")
            if isinstance(version, str) and version:
                versions.append(version)
            if sample.get("verdict") == RealityVerdict.UNRESOLVED.value:
                unresolved += 1

        series_ref = result.get("series_evidence_ref")
        if isinstance(series_ref, str) and series_ref:
            evidence_refs.append(series_ref)

        observed_sample_count = sum(
            1
            for sample in samples
            if isinstance(sample, Mapping)
            and isinstance(sample.get("observation_evidence_ref"), str)
            and bool(sample.get("observation_evidence_ref"))
        )

        timing_failed = any(
            result.get(field) is False
            for field in (
                "timing_satisfied",
                "cadence_satisfied",
                "series_span_satisfied",
                "temporal_envelope_satisfied",
            )
        )

        if not samples or observed_sample_count == 0:
            status: CoverageStatus = "UNOBSERVED"
            limitations: tuple[str, ...] = ("series_observation_not_completed",)
        elif (
            requested is not None
            and observed_sample_count == requested
            and unresolved == 0
            and not timing_failed
        ):
            status = "COVERED"
            limitations = (
                "bounded_discrete_series_only",
                "series_is_not_continuous_monitoring",
            )
        else:
            status = "PARTIAL"
            limitations = (
                "series_observation_incomplete_or_unresolved",
                "series_is_not_continuous_monitoring",
            )

        observer_id = (
            sorted(set(providers))[0]
            if providers
            else _provider_name(provider, "local-http-provider")
        )
        observer_version = sorted(set(versions))[0] if versions else None
        return self._entry(
            claim=claim,
            observer_id=observer_id,
            observer_version=observer_version,
            coverage_kind="bounded_series",
            status=status,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            limitations=limitations,
            result=result,
        )

    def _entry(
        self,
        *,
        claim: RealityClaim,
        observer_id: str,
        observer_version: str | None,
        coverage_kind: str,
        status: CoverageStatus,
        evidence_refs: tuple[str, ...],
        limitations: tuple[str, ...],
        result: Mapping[str, Any],
    ) -> ObservationCoverage:
        negative = _is_explicit_negative_state_claim(claim)
        bounded_negative = bool(
            negative
            and status == "COVERED"
            and result.get("verdict") == RealityVerdict.SUPPORTED.value
        )
        return ObservationCoverage(
            claim_id=claim.claim_id,
            claim_kind=claim.kind.value,
            surface=_claim_surface(claim),
            target=_claim_target(claim),
            observer_id=observer_id,
            observer_version=observer_version,
            coverage_kind=coverage_kind,
            status=status,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            limitations=limitations,
            explicit_negative_state_claim=negative,
            bounded_negative_state_support=bounded_negative,
        )

    @staticmethod
    def _evidence_refs(result: Mapping[str, Any]) -> tuple[str, ...]:
        refs: list[str] = []
        ref = result.get("observation_evidence_ref")
        if isinstance(ref, str) and ref:
            refs.append(ref)
        series_ref = result.get("series_evidence_ref")
        if isinstance(series_ref, str) and series_ref:
            refs.append(series_ref)
        return tuple(dict.fromkeys(refs))

    @staticmethod
    def _optional_string(value: object) -> str | None:
        if isinstance(value, str) and value:
            return value
        return None
