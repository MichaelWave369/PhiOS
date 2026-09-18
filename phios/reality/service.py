from __future__ import annotations

from collections import Counter
import json
from time import monotonic, sleep
from typing import Any

from phios.mandala import (
    AuthorityContext,
    Gate,
    GateReceipt,
    MandalaPacket,
    MandalaReceiptLedger,
    MandalaStatus,
    OriginKind,
    OriginRef,
    RealityReceipt,
)
from phios.mandala.receipts import receipt_meta
from phios.soma.evidence import NativeEvidenceStore

from .local_http import (
    LocalHttpObservationError,
    LocalHttpStateProvider,
    UnavailableLocalHttpStateProvider,
)
from .local_json import (
    evaluate_json_contract_clause,
    evaluate_json_mixed_contract_clause,
    evaluate_json_scalar_predicate,
    evaluate_json_structural_predicate,
    json_scalar_predicate_expected_type,
    json_structural_predicate_expected_type,
    json_type_matches,
    json_type_name,
    resolve_json_pointer,
    strict_json_loads,
)
from .local_network import (
    InterfaceObservationError,
    InterfaceStateProvider,
    PsutilInterfaceStateProvider,
)
from .local_socket import (
    PsutilTcpListenerStateProvider,
    TcpListenerObservationError,
    TcpListenerStateProvider,
)
from .models import (
    RealityClaim,
    RealityClaimKind,
    RealityVerdict,
    RealityVerificationResult,
)


class RealityVerificationService:
    """Deterministic Reality Gate bridge for bounded evidence claims."""

    def __init__(
        self,
        *,
        evidence: NativeEvidenceStore,
        ledger: MandalaReceiptLedger,
        task_id: str,
        authority: AuthorityContext,
        interface_provider: InterfaceStateProvider | None = None,
        tcp_listener_provider: TcpListenerStateProvider | None = None,
        local_http_provider: LocalHttpStateProvider | None = None,
    ) -> None:
        self.evidence = evidence
        self.ledger = ledger
        self.task_id = task_id
        self.authority = authority
        self.interface_provider = interface_provider or PsutilInterfaceStateProvider()
        self.tcp_listener_provider = (
            tcp_listener_provider or PsutilTcpListenerStateProvider()
        )
        self.local_http_provider = (
            local_http_provider or UnavailableLocalHttpStateProvider()
        )

    @staticmethod
    def _normalize_text(text: str, *, case_sensitive: bool) -> str:
        normalized = " ".join(
            text.replace("\r\n", "\n").replace("\r", "\n").split()
        )
        return normalized if case_sensitive else normalized.casefold()

    def _packet(self, claims: tuple[RealityClaim, ...]) -> MandalaPacket:
        evidence_refs = tuple(
            dict.fromkeys(
                ref
                for claim in claims
                for ref in claim.evidence_refs
            )
        )
        return MandalaPacket.create(
            task_id=self.task_id,
            gate=Gate.DELIBERATION,
            origin=OriginRef(
                kind=OriginKind.SUBSYSTEM,
                identifier="reality.verification",
            ),
            payload={
                "claim_count": len(claims),
                "claims": [claim.to_dict() for claim in claims],
                "verification_method": "bounded-evidence-v0.13",
            },
            authority=self.authority,
            evidence_refs=evidence_refs,
            claims=tuple(claim.to_dict() for claim in claims),
            allowed_destinations=(Gate.ACTION, Gate.MEMORY),
        )

    def _gate_receipt(
        self,
        packet: MandalaPacket,
        *,
        status: MandalaStatus,
        reason: str,
    ) -> GateReceipt:
        receipt = GateReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="reality.verification_gate",
            ),
            gate=Gate.DELIBERATION,
            reason=reason,
            provenance_refs=packet.evidence_refs,
            authority=packet.authority.to_dict(),
        )
        self.ledger.append(receipt)
        return receipt

    def _source_contains_text(
        self,
        claim: RealityClaim,
        *,
        max_evidence_bytes: int,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.expected_text is not None

        needle = self._normalize_text(
            claim.expected_text,
            case_sensitive=claim.case_sensitive,
        )
        used: list[str] = []
        readable: list[str] = []
        evidence_records: list[dict[str, Any]] = []

        for evidence_ref in claim.evidence_refs:
            try:
                data = self.evidence.read_bytes(evidence_ref)
            except (ValueError, FileNotFoundError, RuntimeError):
                evidence_records.append(
                    {
                        "evidence_ref": evidence_ref,
                        "status": "unavailable",
                        "matched": False,
                    }
                )
                continue

            if len(data) > max_evidence_bytes:
                evidence_records.append(
                    {
                        "evidence_ref": evidence_ref,
                        "status": "too_large",
                        "matched": False,
                    }
                )
                continue

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                evidence_records.append(
                    {
                        "evidence_ref": evidence_ref,
                        "status": "not_utf8_text",
                        "matched": False,
                    }
                )
                continue

            readable.append(evidence_ref)
            used.append(evidence_ref)
            haystack = self._normalize_text(
                text,
                case_sensitive=claim.case_sensitive,
            )
            matched = needle in haystack
            evidence_records.append(
                {
                    "evidence_ref": evidence_ref,
                    "status": "readable_text",
                    "matched": matched,
                }
            )
            if matched:
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.SUPPORTED.value,
                        "reason": "expected_text_present_in_cited_evidence",
                        "matched_evidence_ref": evidence_ref,
                        "evidence_records": evidence_records,
                        "scope": "source_content_only",
                    },
                    tuple(used),
                )

        if readable:
            verdict = RealityVerdict.CONTRADICTED
            reason = "expected_text_absent_from_all_readable_cited_evidence"
        else:
            verdict = RealityVerdict.UNRESOLVED
            reason = "no_readable_cited_text_evidence"

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "matched_evidence_ref": None,
                "evidence_records": evidence_records,
                "scope": "source_content_only",
            },
            tuple(used),
        )

    @staticmethod
    def _world_state(claim: RealityClaim) -> dict[str, Any]:
        return {
            "claim_id": claim.claim_id,
            "kind": claim.kind.value,
            "statement": claim.statement,
            "verdict": RealityVerdict.UNRESOLVED.value,
            "reason": "world_state_requires_independent_world_verifier",
            "matched_evidence_ref": None,
            "evidence_records": [],
            "scope": "world_state",
        }

    def _local_interface_state(
        self,
        claim: RealityClaim,
        *,
        provider: InterfaceStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        permission = "reality.local_interface.read"
        assert claim.interface_name is not None
        assert claim.expected_is_up is not None

        if not self.authority.allows(permission):
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.BLOCKED.value,
                    "reason": f"missing_grant:{permission}",
                    "scope": "local_interface_state",
                    "interface_name": claim.interface_name,
                    "expected_is_up": claim.expected_is_up,
                    "observation_evidence_ref": None,
                },
                (),
            )

        try:
            observation = provider.observe(claim.interface_name)
        except InterfaceObservationError:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_interface_observation_unavailable",
                    "scope": "local_interface_state",
                    "interface_name": claim.interface_name,
                    "expected_is_up": claim.expected_is_up,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_interface_provider_error",
                    "scope": "local_interface_state",
                    "interface_name": claim.interface_name,
                    "expected_is_up": claim.expected_is_up,
                    "observation_evidence_ref": None,
                },
                (),
            )

        if observation is None:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_interface_not_found",
                    "scope": "local_interface_state",
                    "interface_name": claim.interface_name,
                    "expected_is_up": claim.expected_is_up,
                    "observation_evidence_ref": None,
                },
                (),
            )

        observation_data = observation.to_dict()
        observation_bytes = json.dumps(
            observation_data,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        matched = observation.is_up is claim.expected_is_up
        verdict = (
            RealityVerdict.SUPPORTED
            if matched
            else RealityVerdict.CONTRADICTED
        )
        reason = (
            "direct_local_interface_observation_matches_expected_state"
            if matched
            else "direct_local_interface_observation_conflicts_with_expected_state"
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_interface_state",
                "interface_name": observation.interface_name,
                "expected_is_up": claim.expected_is_up,
                "observed_is_up": observation.is_up,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_tcp_listener_state(
        self,
        claim: RealityClaim,
        *,
        provider: TcpListenerStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        permission = "reality.local_socket.read"
        assert claim.local_port is not None
        assert claim.expected_listening is not None

        if not self.authority.allows(permission):
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.BLOCKED.value,
                    "reason": f"missing_grant:{permission}",
                    "scope": "local_tcp_listener_state",
                    "local_port": claim.local_port,
                    "local_address": claim.local_address,
                    "expected_listening": claim.expected_listening,
                    "observation_evidence_ref": None,
                },
                (),
            )

        try:
            observation = provider.observe(
                local_port=claim.local_port,
                local_address=claim.local_address,
            )
        except TcpListenerObservationError:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_tcp_observation_unavailable",
                    "scope": "local_tcp_listener_state",
                    "local_port": claim.local_port,
                    "local_address": claim.local_address,
                    "expected_listening": claim.expected_listening,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_tcp_provider_error",
                    "scope": "local_tcp_listener_state",
                    "local_port": claim.local_port,
                    "local_address": claim.local_address,
                    "expected_listening": claim.expected_listening,
                    "observation_evidence_ref": None,
                },
                (),
            )

        observation_bytes = json.dumps(
            observation.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        matched = observation.is_listening is claim.expected_listening
        verdict = (
            RealityVerdict.SUPPORTED
            if matched
            else RealityVerdict.CONTRADICTED
        )
        reason = (
            "direct_local_tcp_observation_matches_expected_state"
            if matched
            else "direct_local_tcp_observation_conflicts_with_expected_state"
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_tcp_listener_state",
                "local_port": observation.local_port,
                "local_address": observation.local_address_filter,
                "expected_listening": claim.expected_listening,
                "observed_listening": observation.is_listening,
                "matched_local_addresses": list(observation.matched_local_addresses),
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_response_state(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        permission = "reality.local_http.read"
        assert claim.http_url is not None
        assert claim.expected_http_status is not None

        if not self.authority.allows(permission):
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.BLOCKED.value,
                    "reason": f"missing_grant:{permission}",
                    "scope": "local_http_response_state",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "observation_evidence_ref": None,
                },
                (),
            )

        try:
            observation = provider.observe(
                url=claim.http_url,
                timeout_seconds=claim.http_timeout_seconds,
                max_body_bytes=claim.http_max_body_bytes,
            )
        except LocalHttpObservationError as exc:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": exc.code,
                    "scope": "local_http_response_state",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_http_provider_error",
                    "scope": "local_http_response_state",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "observation_evidence_ref": None,
                },
                (),
            )

        observation_bytes = json.dumps(
            observation.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        matched = observation.status_code == claim.expected_http_status
        verdict = (
            RealityVerdict.SUPPORTED
            if matched
            else RealityVerdict.CONTRADICTED
        )
        reason = (
            "direct_local_http_observation_matches_expected_status"
            if matched
            else "direct_local_http_observation_conflicts_with_expected_status"
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_response_state",
                "http_url": observation.url,
                "method": observation.method,
                "expected_http_status": claim.expected_http_status,
                "observed_http_status": observation.status_code,
                "response_headers": dict(observation.headers),
                "body_sha256": observation.body_sha256,
                "body_bytes_observed": observation.body_bytes_observed,
                "body_truncated": observation.body_truncated,
                "body_digest_scope": observation.body_digest_scope,
                "redirect_followed": observation.redirect_followed,
                "elapsed_ms": observation.elapsed_ms,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_json_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_pointer is not None
        assert claim.expected_json_type is not None

        for permission in (
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ):
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "json_pointer": claim.json_pointer,
                        "expected_json_type": claim.expected_json_type,
                        "observation_evidence_ref": None,
                    },
                    (),
                )

        try:
            observation = provider.observe(
                url=claim.http_url,
                timeout_seconds=claim.http_timeout_seconds,
                max_body_bytes=claim.http_max_body_bytes,
            )
        except LocalHttpObservationError as exc:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": exc.code,
                    "scope": "local_http_json_contract",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "json_pointer": claim.json_pointer,
                    "expected_json_type": claim.expected_json_type,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_http_provider_error",
                    "scope": "local_http_json_contract",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "json_pointer": claim.json_pointer,
                    "expected_json_type": claim.expected_json_type,
                    "observation_evidence_ref": None,
                },
                (),
            )

        semantic: dict[str, Any] = {
            "json_valid": None,
            "pointer_exists": None,
            "observed_json_type": None,
            "type_matches": None,
        }

        if observation.status_code != claim.expected_http_status:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_contract_status_mismatch"
        elif observation.body_truncated:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_contract_body_truncated"
        elif observation.body is None:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_semantic_body_unavailable"
        else:
            try:
                document = strict_json_loads(observation.body)
            except (UnicodeDecodeError, ValueError):
                semantic["json_valid"] = False
                verdict = RealityVerdict.CONTRADICTED
                reason = "local_http_json_contract_invalid_json"
            else:
                semantic["json_valid"] = True
                pointer_exists, value = resolve_json_pointer(
                    document,
                    claim.json_pointer,
                )
                semantic["pointer_exists"] = pointer_exists
                if not pointer_exists:
                    verdict = RealityVerdict.CONTRADICTED
                    reason = "local_http_json_contract_pointer_missing"
                else:
                    observed_type = json_type_name(value)
                    type_matches = json_type_matches(
                        value,
                        claim.expected_json_type,
                    )
                    semantic["observed_json_type"] = observed_type
                    semantic["type_matches"] = type_matches
                    if type_matches:
                        verdict = RealityVerdict.SUPPORTED
                        reason = "local_http_json_contract_matches"
                    else:
                        verdict = RealityVerdict.CONTRADICTED
                        reason = "local_http_json_contract_type_mismatch"

        evidence_record = {
            "http_observation": observation.to_dict(),
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "json_pointer": claim.json_pointer,
                "expected_json_type": claim.expected_json_type,
            },
            "semantic_observation": semantic,
        }
        observation_bytes = json.dumps(
            evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_contract",
                "http_url": observation.url,
                "method": observation.method,
                "expected_http_status": claim.expected_http_status,
                "observed_http_status": observation.status_code,
                "json_pointer": claim.json_pointer,
                "expected_json_type": claim.expected_json_type,
                "json_valid": semantic["json_valid"],
                "pointer_exists": semantic["pointer_exists"],
                "observed_json_type": semantic["observed_json_type"],
                "type_matches": semantic["type_matches"],
                "body_sha256": observation.body_sha256,
                "body_bytes_observed": observation.body_bytes_observed,
                "body_truncated": observation.body_truncated,
                "body_digest_scope": observation.body_digest_scope,
                "elapsed_ms": observation.elapsed_ms,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_json_predicate(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_pointer is not None
        assert claim.json_predicate_kind is not None

        for permission in (
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ):
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_predicate",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "json_pointer": claim.json_pointer,
                        "json_predicate_kind": claim.json_predicate_kind,
                        "json_predicate_bound": claim.json_predicate_bound,
                        "observation_evidence_ref": None,
                    },
                    (),
                )

        try:
            observation = provider.observe(
                url=claim.http_url,
                timeout_seconds=claim.http_timeout_seconds,
                max_body_bytes=claim.http_max_body_bytes,
            )
        except LocalHttpObservationError as exc:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": exc.code,
                    "scope": "local_http_json_predicate",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "json_pointer": claim.json_pointer,
                    "json_predicate_kind": claim.json_predicate_kind,
                    "json_predicate_bound": claim.json_predicate_bound,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_http_provider_error",
                    "scope": "local_http_json_predicate",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "json_pointer": claim.json_pointer,
                    "json_predicate_kind": claim.json_predicate_kind,
                    "json_predicate_bound": claim.json_predicate_bound,
                    "observation_evidence_ref": None,
                },
                (),
            )

        expected_type = json_structural_predicate_expected_type(
            claim.json_predicate_kind
        )
        semantic: dict[str, Any] = {
            "json_valid": None,
            "pointer_exists": None,
            "expected_json_type": expected_type,
            "observed_json_type": None,
            "type_matches": None,
            "measurement_name": None,
            "measurement": None,
            "predicate_matches": None,
        }

        if observation.status_code != claim.expected_http_status:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_predicate_status_mismatch"
        elif observation.body_truncated:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_predicate_body_truncated"
        elif observation.body is None:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_semantic_body_unavailable"
        else:
            try:
                document = strict_json_loads(observation.body)
            except (UnicodeDecodeError, ValueError):
                semantic["json_valid"] = False
                verdict = RealityVerdict.CONTRADICTED
                reason = "local_http_json_predicate_invalid_json"
            else:
                semantic["json_valid"] = True
                pointer_exists, value = resolve_json_pointer(
                    document,
                    claim.json_pointer,
                )
                semantic["pointer_exists"] = pointer_exists
                if not pointer_exists:
                    verdict = RealityVerdict.CONTRADICTED
                    reason = "local_http_json_predicate_pointer_missing"
                else:
                    evaluation = evaluate_json_structural_predicate(
                        value,
                        predicate=claim.json_predicate_kind,
                        bound=claim.json_predicate_bound,
                    )
                    for key in (
                        "observed_json_type",
                        "type_matches",
                        "measurement_name",
                        "measurement",
                        "predicate_matches",
                    ):
                        semantic[key] = evaluation[key]

                    if not evaluation["type_matches"]:
                        verdict = RealityVerdict.CONTRADICTED
                        reason = "local_http_json_predicate_type_mismatch"
                    elif evaluation["predicate_matches"]:
                        verdict = RealityVerdict.SUPPORTED
                        reason = "local_http_json_predicate_matches"
                    else:
                        verdict = RealityVerdict.CONTRADICTED
                        reason = "local_http_json_predicate_mismatch"

        evidence_record = {
            "http_observation": observation.to_dict(),
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "json_pointer": claim.json_pointer,
                "json_predicate_kind": claim.json_predicate_kind,
                "json_predicate_bound": claim.json_predicate_bound,
                "expected_json_type": expected_type,
            },
            "semantic_observation": semantic,
        }
        observation_bytes = json.dumps(
            evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_predicate",
                "http_url": observation.url,
                "method": observation.method,
                "expected_http_status": claim.expected_http_status,
                "observed_http_status": observation.status_code,
                "json_pointer": claim.json_pointer,
                "json_predicate_kind": claim.json_predicate_kind,
                "json_predicate_bound": claim.json_predicate_bound,
                "expected_json_type": expected_type,
                "json_valid": semantic["json_valid"],
                "pointer_exists": semantic["pointer_exists"],
                "observed_json_type": semantic["observed_json_type"],
                "type_matches": semantic["type_matches"],
                "measurement_name": semantic["measurement_name"],
                "measurement": semantic["measurement"],
                "predicate_matches": semantic["predicate_matches"],
                "body_sha256": observation.body_sha256,
                "body_bytes_observed": observation.body_bytes_observed,
                "body_truncated": observation.body_truncated,
                "body_digest_scope": observation.body_digest_scope,
                "elapsed_ms": observation.elapsed_ms,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_json_scalar_predicate(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_pointer is not None
        assert claim.json_scalar_predicate_kind is not None

        for permission in (
            "reality.local_http.read",
            "reality.local_http.semantic.read",
            "reality.local_http.semantic.value.read",
        ):
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_scalar_predicate",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "json_pointer": claim.json_pointer,
                        "json_scalar_predicate_kind": claim.json_scalar_predicate_kind,
                        "json_scalar_operand": claim.json_scalar_operand,
                        "observation_evidence_ref": None,
                    },
                    (),
                )

        try:
            observation = provider.observe(
                url=claim.http_url,
                timeout_seconds=claim.http_timeout_seconds,
                max_body_bytes=claim.http_max_body_bytes,
            )
        except LocalHttpObservationError as exc:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": exc.code,
                    "scope": "local_http_json_scalar_predicate",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "json_pointer": claim.json_pointer,
                    "json_scalar_predicate_kind": claim.json_scalar_predicate_kind,
                    "json_scalar_operand": claim.json_scalar_operand,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_http_provider_error",
                    "scope": "local_http_json_scalar_predicate",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "json_pointer": claim.json_pointer,
                    "json_scalar_predicate_kind": claim.json_scalar_predicate_kind,
                    "json_scalar_operand": claim.json_scalar_operand,
                    "observation_evidence_ref": None,
                },
                (),
            )

        expected_type = json_scalar_predicate_expected_type(
            claim.json_scalar_predicate_kind
        )
        semantic: dict[str, Any] = {
            "json_valid": None,
            "pointer_exists": None,
            "expected_json_type": expected_type,
            "observed_json_type": None,
            "type_matches": None,
            "predicate_matches": None,
        }

        if observation.status_code != claim.expected_http_status:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_scalar_predicate_status_mismatch"
        elif observation.body_truncated:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_scalar_predicate_body_truncated"
        elif observation.body is None:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_semantic_body_unavailable"
        else:
            try:
                document = strict_json_loads(observation.body)
            except (UnicodeDecodeError, ValueError):
                semantic["json_valid"] = False
                verdict = RealityVerdict.CONTRADICTED
                reason = "local_http_json_scalar_predicate_invalid_json"
            else:
                semantic["json_valid"] = True
                pointer_exists, value = resolve_json_pointer(
                    document,
                    claim.json_pointer,
                )
                semantic["pointer_exists"] = pointer_exists
                if not pointer_exists:
                    verdict = RealityVerdict.CONTRADICTED
                    reason = "local_http_json_scalar_predicate_pointer_missing"
                else:
                    evaluation = evaluate_json_scalar_predicate(
                        value,
                        predicate=claim.json_scalar_predicate_kind,
                        operand=claim.json_scalar_operand,
                    )
                    semantic["observed_json_type"] = evaluation[
                        "observed_json_type"
                    ]
                    semantic["type_matches"] = evaluation["type_matches"]
                    semantic["predicate_matches"] = evaluation[
                        "predicate_matches"
                    ]

                    if not evaluation["type_matches"]:
                        verdict = RealityVerdict.CONTRADICTED
                        reason = "local_http_json_scalar_predicate_type_mismatch"
                    elif evaluation["predicate_matches"]:
                        verdict = RealityVerdict.SUPPORTED
                        reason = "local_http_json_scalar_predicate_matches"
                    else:
                        verdict = RealityVerdict.CONTRADICTED
                        reason = "local_http_json_scalar_predicate_mismatch"

        evidence_record = {
            "http_observation": observation.to_dict(),
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "json_pointer": claim.json_pointer,
                "json_scalar_predicate_kind": claim.json_scalar_predicate_kind,
                "json_scalar_operand": claim.json_scalar_operand,
                "expected_json_type": expected_type,
            },
            "semantic_observation": semantic,
        }
        observation_bytes = json.dumps(
            evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_scalar_predicate",
                "http_url": observation.url,
                "method": observation.method,
                "expected_http_status": claim.expected_http_status,
                "observed_http_status": observation.status_code,
                "json_pointer": claim.json_pointer,
                "json_scalar_predicate_kind": claim.json_scalar_predicate_kind,
                "json_scalar_operand": claim.json_scalar_operand,
                "expected_json_type": expected_type,
                "json_valid": semantic["json_valid"],
                "pointer_exists": semantic["pointer_exists"],
                "observed_json_type": semantic["observed_json_type"],
                "type_matches": semantic["type_matches"],
                "predicate_matches": semantic["predicate_matches"],
                "body_sha256": observation.body_sha256,
                "body_bytes_observed": observation.body_bytes_observed,
                "body_truncated": observation.body_truncated,
                "body_digest_scope": observation.body_digest_scope,
                "elapsed_ms": observation.elapsed_ms,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_json_multi_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_contract_clauses

        for permission in (
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ):
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_multi_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "clause_count": len(claim.json_contract_clauses),
                        "observation_evidence_ref": None,
                    },
                    (),
                )

        try:
            observation = provider.observe(
                url=claim.http_url,
                timeout_seconds=claim.http_timeout_seconds,
                max_body_bytes=claim.http_max_body_bytes,
            )
        except LocalHttpObservationError as exc:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": exc.code,
                    "scope": "local_http_json_multi_contract",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "clause_count": len(claim.json_contract_clauses),
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_http_provider_error",
                    "scope": "local_http_json_multi_contract",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "clause_count": len(claim.json_contract_clauses),
                    "observation_evidence_ref": None,
                },
                (),
            )

        json_valid: bool | None = None
        clause_results: list[dict[str, Any]] = []

        if observation.status_code != claim.expected_http_status:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_multi_contract_status_mismatch"
        elif observation.body_truncated:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_multi_contract_body_truncated"
        elif observation.body is None:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_semantic_body_unavailable"
        else:
            try:
                document = strict_json_loads(observation.body)
            except (UnicodeDecodeError, ValueError):
                json_valid = False
                verdict = RealityVerdict.CONTRADICTED
                reason = "local_http_json_multi_contract_invalid_json"
            else:
                json_valid = True
                for index, clause in enumerate(claim.json_contract_clauses):
                    result = evaluate_json_contract_clause(document, clause)
                    result["clause_index"] = index

                    if not result["pointer_exists"]:
                        clause_reason = "pointer_missing"
                    elif not result["type_matches"]:
                        clause_reason = "type_mismatch"
                    elif (
                        result["mode"] == "predicate"
                        and not result["predicate_matches"]
                    ):
                        clause_reason = "predicate_mismatch"
                    else:
                        clause_reason = "matches"

                    result["clause_reason"] = clause_reason
                    clause_results.append(result)

                all_match = all(
                    bool(item["clause_matches"])
                    for item in clause_results
                )
                if all_match:
                    verdict = RealityVerdict.SUPPORTED
                    reason = "local_http_json_multi_contract_matches"
                else:
                    verdict = RealityVerdict.CONTRADICTED
                    reason = "local_http_json_multi_contract_clause_mismatch"

        evidence_record = {
            "http_observation": observation.to_dict(),
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "clauses": [
                    clause.to_dict()
                    for clause in claim.json_contract_clauses
                ],
            },
            "semantic_observation": {
                "json_valid": json_valid,
                "clause_results": clause_results,
                "clauses_evaluated": len(clause_results),
                "all_clauses_match": (
                    all(bool(item["clause_matches"]) for item in clause_results)
                    if clause_results
                    else None
                ),
            },
        }
        observation_bytes = json.dumps(
            evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_multi_contract",
                "http_url": observation.url,
                "method": observation.method,
                "expected_http_status": claim.expected_http_status,
                "observed_http_status": observation.status_code,
                "json_valid": json_valid,
                "clause_count": len(claim.json_contract_clauses),
                "clauses_evaluated": len(clause_results),
                "clause_results": clause_results,
                "all_clauses_match": (
                    all(bool(item["clause_matches"]) for item in clause_results)
                    if clause_results
                    else None
                ),
                "body_sha256": observation.body_sha256,
                "body_bytes_observed": observation.body_bytes_observed,
                "body_truncated": observation.body_truncated,
                "body_digest_scope": observation.body_digest_scope,
                "elapsed_ms": observation.elapsed_ms,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_json_mixed_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_mixed_contract_clauses

        requires_value_read = any(
            clause.requires_value_read
            for clause in claim.json_mixed_contract_clauses
        )
        permissions = [
            "reality.local_http.read",
            "reality.local_http.semantic.read",
        ]
        if requires_value_read:
            permissions.append("reality.local_http.semantic.value.read")

        for permission in permissions:
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_mixed_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "clause_count": len(claim.json_mixed_contract_clauses),
                        "requires_value_read": requires_value_read,
                        "observation_evidence_ref": None,
                    },
                    (),
                )

        try:
            observation = provider.observe(
                url=claim.http_url,
                timeout_seconds=claim.http_timeout_seconds,
                max_body_bytes=claim.http_max_body_bytes,
            )
        except LocalHttpObservationError as exc:
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": exc.code,
                    "scope": "local_http_json_mixed_contract",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "clause_count": len(claim.json_mixed_contract_clauses),
                    "requires_value_read": requires_value_read,
                    "observation_evidence_ref": None,
                },
                (),
            )
        except Exception:  # noqa: BLE001 - provider boundary
            return (
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "local_http_provider_error",
                    "scope": "local_http_json_mixed_contract",
                    "http_url": claim.http_url,
                    "expected_http_status": claim.expected_http_status,
                    "clause_count": len(claim.json_mixed_contract_clauses),
                    "requires_value_read": requires_value_read,
                    "observation_evidence_ref": None,
                },
                (),
            )

        json_valid: bool | None = None
        clause_results: list[dict[str, Any]] = []

        if observation.status_code != claim.expected_http_status:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_mixed_contract_status_mismatch"
        elif observation.body_truncated:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_mixed_contract_body_truncated"
        elif observation.body is None:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_semantic_body_unavailable"
        else:
            try:
                document = strict_json_loads(observation.body)
            except (UnicodeDecodeError, ValueError):
                json_valid = False
                verdict = RealityVerdict.CONTRADICTED
                reason = "local_http_json_mixed_contract_invalid_json"
            else:
                json_valid = True
                for index, clause in enumerate(claim.json_mixed_contract_clauses):
                    result = evaluate_json_mixed_contract_clause(document, clause)
                    result["clause_index"] = index

                    if not result["pointer_exists"]:
                        clause_reason = "pointer_missing"
                    elif not result["type_matches"]:
                        clause_reason = "type_mismatch"
                    elif (
                        result["mode"] in {"structural", "scalar"}
                        and not result["predicate_matches"]
                    ):
                        clause_reason = "predicate_mismatch"
                    else:
                        clause_reason = "matches"

                    result["clause_reason"] = clause_reason
                    clause_results.append(result)

                all_match = all(
                    bool(item["clause_matches"])
                    for item in clause_results
                )
                if all_match:
                    verdict = RealityVerdict.SUPPORTED
                    reason = "local_http_json_mixed_contract_matches"
                else:
                    verdict = RealityVerdict.CONTRADICTED
                    reason = "local_http_json_mixed_contract_clause_mismatch"

        all_clauses_match = (
            all(bool(item["clause_matches"]) for item in clause_results)
            if clause_results
            else None
        )
        evidence_record = {
            "http_observation": observation.to_dict(),
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "requires_value_read": requires_value_read,
                "clauses": [
                    clause.to_dict()
                    for clause in claim.json_mixed_contract_clauses
                ],
            },
            "semantic_observation": {
                "json_valid": json_valid,
                "clause_results": clause_results,
                "clauses_evaluated": len(clause_results),
                "all_clauses_match": all_clauses_match,
            },
        }
        observation_bytes = json.dumps(
            evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        observation_evidence = self.evidence.put_bytes(
            observation_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_mixed_contract",
                "http_url": observation.url,
                "method": observation.method,
                "expected_http_status": claim.expected_http_status,
                "observed_http_status": observation.status_code,
                "requires_value_read": requires_value_read,
                "json_valid": json_valid,
                "clause_count": len(claim.json_mixed_contract_clauses),
                "clauses_evaluated": len(clause_results),
                "clause_results": clause_results,
                "all_clauses_match": all_clauses_match,
                "body_sha256": observation.body_sha256,
                "body_bytes_observed": observation.body_bytes_observed,
                "body_truncated": observation.body_truncated,
                "body_digest_scope": observation.body_digest_scope,
                "elapsed_ms": observation.elapsed_ms,
                "provider": observation.provider,
                "provider_version": observation.provider_version,
                "captured_at_utc": observation.captured_at_utc,
                "observation_evidence_ref": observation_evidence.evidence_ref,
            },
            (observation_evidence.evidence_ref,),
        )

    def _local_http_json_repeated_mixed_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_mixed_contract_clauses
        assert claim.repeat_observation_count is not None

        requires_value_read = any(
            clause.requires_value_read
            for clause in claim.json_mixed_contract_clauses
        )
        permissions = [
            "reality.local_http.read",
            "reality.local_http.semantic.read",
            "reality.local_http.repeat.read",
        ]
        if requires_value_read:
            permissions.append("reality.local_http.semantic.value.read")

        for permission in permissions:
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_repeated_mixed_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "clause_count": len(claim.json_mixed_contract_clauses),
                        "observation_count_requested": claim.repeat_observation_count,
                        "requires_value_read": requires_value_read,
                        "series_evidence_ref": None,
                    },
                    (),
                )

        sample_results: list[dict[str, Any]] = []
        sample_evidence_refs: list[str] = []

        for sample_index in range(claim.repeat_observation_count):
            try:
                observation = provider.observe(
                    url=claim.http_url,
                    timeout_seconds=claim.http_timeout_seconds,
                    max_body_bytes=claim.http_max_body_bytes,
                )
            except LocalHttpObservationError as exc:
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": exc.code,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue
            except Exception:  # noqa: BLE001 - provider boundary
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": "local_http_provider_error",
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue

            json_valid: bool | None = None
            clause_results: list[dict[str, Any]] = []

            if observation.status_code != claim.expected_http_status:
                sample_verdict = RealityVerdict.CONTRADICTED
                sample_reason = "local_http_json_repeated_mixed_sample_status_mismatch"
            elif observation.body_truncated:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_json_repeated_mixed_sample_body_truncated"
            elif observation.body is None:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_semantic_body_unavailable"
            else:
                try:
                    document = strict_json_loads(observation.body)
                except (UnicodeDecodeError, ValueError):
                    json_valid = False
                    sample_verdict = RealityVerdict.CONTRADICTED
                    sample_reason = "local_http_json_repeated_mixed_sample_invalid_json"
                else:
                    json_valid = True
                    for clause_index, clause in enumerate(
                        claim.json_mixed_contract_clauses
                    ):
                        result = evaluate_json_mixed_contract_clause(
                            document,
                            clause,
                        )
                        result["clause_index"] = clause_index

                        if not result["pointer_exists"]:
                            clause_reason = "pointer_missing"
                        elif not result["type_matches"]:
                            clause_reason = "type_mismatch"
                        elif (
                            result["mode"] in {"structural", "scalar"}
                            and not result["predicate_matches"]
                        ):
                            clause_reason = "predicate_mismatch"
                        else:
                            clause_reason = "matches"

                        result["clause_reason"] = clause_reason
                        clause_results.append(result)

                    all_match = all(
                        bool(item["clause_matches"])
                        for item in clause_results
                    )
                    if all_match:
                        sample_verdict = RealityVerdict.SUPPORTED
                        sample_reason = (
                            "local_http_json_repeated_mixed_sample_matches"
                        )
                    else:
                        sample_verdict = RealityVerdict.CONTRADICTED
                        sample_reason = (
                            "local_http_json_repeated_mixed_sample_clause_mismatch"
                        )

            all_clauses_match = (
                all(bool(item["clause_matches"]) for item in clause_results)
                if clause_results
                else None
            )
            sample_evidence_record = {
                "sample_index": sample_index,
                "http_observation": observation.to_dict(),
                "semantic_contract": {
                    "expected_http_status": claim.expected_http_status,
                    "requires_value_read": requires_value_read,
                    "repeat_observation_count": claim.repeat_observation_count,
                    "clauses": [
                        clause.to_dict()
                        for clause in claim.json_mixed_contract_clauses
                    ],
                },
                "semantic_observation": {
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "json_valid": json_valid,
                    "clause_results": clause_results,
                    "clauses_evaluated": len(clause_results),
                    "all_clauses_match": all_clauses_match,
                },
            }
            sample_evidence_bytes = json.dumps(
                sample_evidence_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            sample_evidence = self.evidence.put_bytes(
                sample_evidence_bytes,
                media_type="application/json; charset=utf-8",
                suffix=".json",
            )
            sample_evidence_refs.append(sample_evidence.evidence_ref)
            sample_results.append(
                {
                    "sample_index": sample_index,
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "observed_http_status": observation.status_code,
                    "json_valid": json_valid,
                    "clauses_evaluated": len(clause_results),
                    "clause_results": clause_results,
                    "all_clauses_match": all_clauses_match,
                    "body_sha256": observation.body_sha256,
                    "body_bytes_observed": observation.body_bytes_observed,
                    "body_truncated": observation.body_truncated,
                    "body_digest_scope": observation.body_digest_scope,
                    "elapsed_ms": observation.elapsed_ms,
                    "provider": observation.provider,
                    "provider_version": observation.provider_version,
                    "captured_at_utc": observation.captured_at_utc,
                    "observation_evidence_ref": sample_evidence.evidence_ref,
                }
            )

        verdict_values = [item["verdict"] for item in sample_results]
        supported_count = verdict_values.count(RealityVerdict.SUPPORTED.value)
        contradicted_count = verdict_values.count(RealityVerdict.CONTRADICTED.value)
        unresolved_count = verdict_values.count(RealityVerdict.UNRESOLVED.value)

        if contradicted_count:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_repeated_mixed_sample_contradiction"
        elif unresolved_count:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_repeated_mixed_sample_unresolved"
        else:
            verdict = RealityVerdict.SUPPORTED
            reason = "local_http_json_repeated_mixed_all_observations_match"

        all_observations_match = (
            supported_count == claim.repeat_observation_count
        )
        series_evidence_record = {
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "requires_value_read": requires_value_read,
                "repeat_observation_count": claim.repeat_observation_count,
                "minimum_interval_seconds": None,
                "clauses": [
                    clause.to_dict()
                    for clause in claim.json_mixed_contract_clauses
                ],
            },
            "repeated_observation": {
                "attempts_completed": len(sample_results),
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
            },
        }
        series_evidence_bytes = json.dumps(
            series_evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        series_evidence = self.evidence.put_bytes(
            series_evidence_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        used_refs = tuple(sample_evidence_refs + [series_evidence.evidence_ref])
        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_repeated_mixed_contract",
                "http_url": claim.http_url,
                "expected_http_status": claim.expected_http_status,
                "clause_count": len(claim.json_mixed_contract_clauses),
                "observation_count_requested": claim.repeat_observation_count,
                "observation_attempts_completed": len(sample_results),
                "requires_value_read": requires_value_read,
                "minimum_interval_seconds": None,
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
                "sample_evidence_refs": sample_evidence_refs,
                "series_evidence_ref": series_evidence.evidence_ref,
            },
            used_refs,
        )

    def _local_http_json_timed_mixed_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_mixed_contract_clauses
        assert claim.repeat_observation_count is not None
        assert claim.minimum_interval_seconds is not None

        requires_value_read = any(
            clause.requires_value_read
            for clause in claim.json_mixed_contract_clauses
        )
        permissions = [
            "reality.local_http.read",
            "reality.local_http.semantic.read",
            "reality.local_http.repeat.read",
            "reality.local_http.timing.wait",
        ]
        if requires_value_read:
            permissions.append("reality.local_http.semantic.value.read")

        for permission in permissions:
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_timed_mixed_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "clause_count": len(claim.json_mixed_contract_clauses),
                        "observation_count_requested": claim.repeat_observation_count,
                        "minimum_interval_seconds": claim.minimum_interval_seconds,
                        "requires_value_read": requires_value_read,
                        "series_evidence_ref": None,
                    },
                    (),
                )

        sample_results: list[dict[str, Any]] = []
        sample_evidence_refs: list[str] = []
        previous_start_monotonic: float | None = None

        for sample_index in range(claim.repeat_observation_count):
            if previous_start_monotonic is not None:
                deadline = (
                    previous_start_monotonic + claim.minimum_interval_seconds
                )
                while True:
                    remaining = deadline - monotonic()
                    if remaining <= 0:
                        break
                    sleep(remaining)

            started_monotonic = monotonic()
            interval_since_previous = (
                None
                if previous_start_monotonic is None
                else started_monotonic - previous_start_monotonic
            )
            timing_satisfied = (
                None
                if interval_since_previous is None
                else interval_since_previous >= claim.minimum_interval_seconds
            )
            previous_start_monotonic = started_monotonic
            persisted_interval = (
                None
                if interval_since_previous is None
                else round(interval_since_previous, 9)
            )

            try:
                observation = provider.observe(
                    url=claim.http_url,
                    timeout_seconds=claim.http_timeout_seconds,
                    max_body_bytes=claim.http_max_body_bytes,
                )
            except LocalHttpObservationError as exc:
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": exc.code,
                        "elapsed_since_previous_start_seconds": persisted_interval,
                        "timing_satisfied": timing_satisfied,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue
            except Exception:  # noqa: BLE001 - provider boundary
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": "local_http_provider_error",
                        "elapsed_since_previous_start_seconds": persisted_interval,
                        "timing_satisfied": timing_satisfied,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue

            json_valid: bool | None = None
            clause_results: list[dict[str, Any]] = []

            if observation.status_code != claim.expected_http_status:
                sample_verdict = RealityVerdict.CONTRADICTED
                sample_reason = "local_http_json_timed_mixed_sample_status_mismatch"
            elif observation.body_truncated:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_json_timed_mixed_sample_body_truncated"
            elif observation.body is None:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_semantic_body_unavailable"
            else:
                try:
                    document = strict_json_loads(observation.body)
                except (UnicodeDecodeError, ValueError):
                    json_valid = False
                    sample_verdict = RealityVerdict.CONTRADICTED
                    sample_reason = "local_http_json_timed_mixed_sample_invalid_json"
                else:
                    json_valid = True
                    for clause_index, clause in enumerate(
                        claim.json_mixed_contract_clauses
                    ):
                        result = evaluate_json_mixed_contract_clause(
                            document,
                            clause,
                        )
                        result["clause_index"] = clause_index

                        if not result["pointer_exists"]:
                            clause_reason = "pointer_missing"
                        elif not result["type_matches"]:
                            clause_reason = "type_mismatch"
                        elif (
                            result["mode"] in {"structural", "scalar"}
                            and not result["predicate_matches"]
                        ):
                            clause_reason = "predicate_mismatch"
                        else:
                            clause_reason = "matches"

                        result["clause_reason"] = clause_reason
                        clause_results.append(result)

                    all_match = all(
                        bool(item["clause_matches"])
                        for item in clause_results
                    )
                    if all_match:
                        sample_verdict = RealityVerdict.SUPPORTED
                        sample_reason = "local_http_json_timed_mixed_sample_matches"
                    else:
                        sample_verdict = RealityVerdict.CONTRADICTED
                        sample_reason = (
                            "local_http_json_timed_mixed_sample_clause_mismatch"
                        )

            all_clauses_match = (
                all(bool(item["clause_matches"]) for item in clause_results)
                if clause_results
                else None
            )
            sample_evidence_record = {
                "sample_index": sample_index,
                "http_observation": observation.to_dict(),
                "timing_observation": {
                    "minimum_interval_seconds": claim.minimum_interval_seconds,
                    "elapsed_since_previous_start_seconds": persisted_interval,
                    "timing_satisfied": timing_satisfied,
                    "interval_basis": "provider_invocation_start_monotonic",
                },
                "semantic_contract": {
                    "expected_http_status": claim.expected_http_status,
                    "requires_value_read": requires_value_read,
                    "repeat_observation_count": claim.repeat_observation_count,
                    "minimum_interval_seconds": claim.minimum_interval_seconds,
                    "clauses": [
                        clause.to_dict()
                        for clause in claim.json_mixed_contract_clauses
                    ],
                },
                "semantic_observation": {
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "json_valid": json_valid,
                    "clause_results": clause_results,
                    "clauses_evaluated": len(clause_results),
                    "all_clauses_match": all_clauses_match,
                },
            }
            sample_evidence_bytes = json.dumps(
                sample_evidence_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            sample_evidence = self.evidence.put_bytes(
                sample_evidence_bytes,
                media_type="application/json; charset=utf-8",
                suffix=".json",
            )
            sample_evidence_refs.append(sample_evidence.evidence_ref)
            sample_results.append(
                {
                    "sample_index": sample_index,
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "elapsed_since_previous_start_seconds": persisted_interval,
                    "timing_satisfied": timing_satisfied,
                    "observed_http_status": observation.status_code,
                    "json_valid": json_valid,
                    "clauses_evaluated": len(clause_results),
                    "clause_results": clause_results,
                    "all_clauses_match": all_clauses_match,
                    "body_sha256": observation.body_sha256,
                    "body_bytes_observed": observation.body_bytes_observed,
                    "body_truncated": observation.body_truncated,
                    "body_digest_scope": observation.body_digest_scope,
                    "elapsed_ms": observation.elapsed_ms,
                    "provider": observation.provider,
                    "provider_version": observation.provider_version,
                    "captured_at_utc": observation.captured_at_utc,
                    "observation_evidence_ref": sample_evidence.evidence_ref,
                }
            )

        verdict_values = [item["verdict"] for item in sample_results]
        supported_count = verdict_values.count(RealityVerdict.SUPPORTED.value)
        contradicted_count = verdict_values.count(RealityVerdict.CONTRADICTED.value)
        unresolved_count = verdict_values.count(RealityVerdict.UNRESOLVED.value)
        observed_intervals = [
            float(item["elapsed_since_previous_start_seconds"])
            for item in sample_results
            if item["elapsed_since_previous_start_seconds"] is not None
        ]
        timing_satisfied = all(
            item["timing_satisfied"] is not False
            for item in sample_results
        )
        minimum_observed_interval_seconds = (
            min(observed_intervals) if observed_intervals else None
        )

        if not timing_satisfied:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_timed_mixed_interval_violation"
        elif contradicted_count:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_timed_mixed_sample_contradiction"
        elif unresolved_count:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_timed_mixed_sample_unresolved"
        else:
            verdict = RealityVerdict.SUPPORTED
            reason = "local_http_json_timed_mixed_all_observations_match"

        all_observations_match = (
            timing_satisfied
            and supported_count == claim.repeat_observation_count
        )
        series_evidence_record = {
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "requires_value_read": requires_value_read,
                "repeat_observation_count": claim.repeat_observation_count,
                "minimum_interval_seconds": claim.minimum_interval_seconds,
                "interval_basis": "provider_invocation_start_monotonic",
                "clauses": [
                    clause.to_dict()
                    for clause in claim.json_mixed_contract_clauses
                ],
            },
            "timing_summary": {
                "timing_satisfied": timing_satisfied,
                "minimum_observed_interval_seconds": (
                    minimum_observed_interval_seconds
                ),
                "observed_interval_count": len(observed_intervals),
            },
            "repeated_observation": {
                "attempts_completed": len(sample_results),
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
            },
        }
        series_evidence_bytes = json.dumps(
            series_evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        series_evidence = self.evidence.put_bytes(
            series_evidence_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        used_refs = tuple(sample_evidence_refs + [series_evidence.evidence_ref])
        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_timed_mixed_contract",
                "http_url": claim.http_url,
                "expected_http_status": claim.expected_http_status,
                "clause_count": len(claim.json_mixed_contract_clauses),
                "observation_count_requested": claim.repeat_observation_count,
                "observation_attempts_completed": len(sample_results),
                "requires_value_read": requires_value_read,
                "minimum_interval_seconds": claim.minimum_interval_seconds,
                "interval_basis": "provider_invocation_start_monotonic",
                "timing_satisfied": timing_satisfied,
                "minimum_observed_interval_seconds": (
                    minimum_observed_interval_seconds
                ),
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
                "sample_evidence_refs": sample_evidence_refs,
                "series_evidence_ref": series_evidence.evidence_ref,
            },
            used_refs,
        )

    def _local_http_json_cadenced_mixed_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_mixed_contract_clauses
        assert claim.repeat_observation_count is not None
        assert claim.minimum_interval_seconds is not None
        assert claim.maximum_interval_seconds is not None

        requires_value_read = any(
            clause.requires_value_read
            for clause in claim.json_mixed_contract_clauses
        )
        permissions = [
            "reality.local_http.read",
            "reality.local_http.semantic.read",
            "reality.local_http.repeat.read",
            "reality.local_http.timing.wait",
            "reality.local_http.timing.cadence",
        ]
        if requires_value_read:
            permissions.append("reality.local_http.semantic.value.read")

        for permission in permissions:
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_cadenced_mixed_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "clause_count": len(claim.json_mixed_contract_clauses),
                        "observation_count_requested": claim.repeat_observation_count,
                        "minimum_interval_seconds": claim.minimum_interval_seconds,
                        "maximum_interval_seconds": claim.maximum_interval_seconds,
                        "requires_value_read": requires_value_read,
                        "series_evidence_ref": None,
                    },
                    (),
                )

        sample_results: list[dict[str, Any]] = []
        sample_evidence_refs: list[str] = []
        previous_start_monotonic: float | None = None

        for sample_index in range(claim.repeat_observation_count):
            if previous_start_monotonic is not None:
                earliest_start = (
                    previous_start_monotonic + claim.minimum_interval_seconds
                )
                while True:
                    remaining = earliest_start - monotonic()
                    if remaining <= 0:
                        break
                    sleep(remaining)

            started_monotonic = monotonic()
            interval_since_previous = (
                None
                if previous_start_monotonic is None
                else started_monotonic - previous_start_monotonic
            )
            persisted_interval = (
                None
                if interval_since_previous is None
                else round(interval_since_previous, 9)
            )
            lower_bound_satisfied = (
                None
                if persisted_interval is None
                else persisted_interval >= claim.minimum_interval_seconds
            )
            upper_bound_satisfied = (
                None
                if persisted_interval is None
                else persisted_interval <= claim.maximum_interval_seconds
            )
            cadence_satisfied = (
                None
                if persisted_interval is None
                else bool(lower_bound_satisfied and upper_bound_satisfied)
            )
            previous_start_monotonic = started_monotonic

            try:
                observation = provider.observe(
                    url=claim.http_url,
                    timeout_seconds=claim.http_timeout_seconds,
                    max_body_bytes=claim.http_max_body_bytes,
                )
            except LocalHttpObservationError as exc:
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": exc.code,
                        "elapsed_since_previous_start_seconds": persisted_interval,
                        "lower_bound_satisfied": lower_bound_satisfied,
                        "upper_bound_satisfied": upper_bound_satisfied,
                        "cadence_satisfied": cadence_satisfied,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue
            except Exception:  # noqa: BLE001 - provider boundary
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": "local_http_provider_error",
                        "elapsed_since_previous_start_seconds": persisted_interval,
                        "lower_bound_satisfied": lower_bound_satisfied,
                        "upper_bound_satisfied": upper_bound_satisfied,
                        "cadence_satisfied": cadence_satisfied,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue

            json_valid: bool | None = None
            clause_results: list[dict[str, Any]] = []

            if observation.status_code != claim.expected_http_status:
                sample_verdict = RealityVerdict.CONTRADICTED
                sample_reason = "local_http_json_cadenced_mixed_sample_status_mismatch"
            elif observation.body_truncated:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_json_cadenced_mixed_sample_body_truncated"
            elif observation.body is None:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_semantic_body_unavailable"
            else:
                try:
                    document = strict_json_loads(observation.body)
                except (UnicodeDecodeError, ValueError):
                    json_valid = False
                    sample_verdict = RealityVerdict.CONTRADICTED
                    sample_reason = "local_http_json_cadenced_mixed_sample_invalid_json"
                else:
                    json_valid = True
                    for clause_index, clause in enumerate(
                        claim.json_mixed_contract_clauses
                    ):
                        result = evaluate_json_mixed_contract_clause(
                            document,
                            clause,
                        )
                        result["clause_index"] = clause_index

                        if not result["pointer_exists"]:
                            clause_reason = "pointer_missing"
                        elif not result["type_matches"]:
                            clause_reason = "type_mismatch"
                        elif (
                            result["mode"] in {"structural", "scalar"}
                            and not result["predicate_matches"]
                        ):
                            clause_reason = "predicate_mismatch"
                        else:
                            clause_reason = "matches"

                        result["clause_reason"] = clause_reason
                        clause_results.append(result)

                    all_match = all(
                        bool(item["clause_matches"])
                        for item in clause_results
                    )
                    if all_match:
                        sample_verdict = RealityVerdict.SUPPORTED
                        sample_reason = "local_http_json_cadenced_mixed_sample_matches"
                    else:
                        sample_verdict = RealityVerdict.CONTRADICTED
                        sample_reason = (
                            "local_http_json_cadenced_mixed_sample_clause_mismatch"
                        )

            all_clauses_match = (
                all(bool(item["clause_matches"]) for item in clause_results)
                if clause_results
                else None
            )
            sample_evidence_record = {
                "sample_index": sample_index,
                "http_observation": observation.to_dict(),
                "timing_observation": {
                    "minimum_interval_seconds": claim.minimum_interval_seconds,
                    "maximum_interval_seconds": claim.maximum_interval_seconds,
                    "elapsed_since_previous_start_seconds": persisted_interval,
                    "lower_bound_satisfied": lower_bound_satisfied,
                    "upper_bound_satisfied": upper_bound_satisfied,
                    "cadence_satisfied": cadence_satisfied,
                    "interval_basis": "provider_invocation_start_monotonic",
                },
                "semantic_contract": {
                    "expected_http_status": claim.expected_http_status,
                    "requires_value_read": requires_value_read,
                    "repeat_observation_count": claim.repeat_observation_count,
                    "minimum_interval_seconds": claim.minimum_interval_seconds,
                    "maximum_interval_seconds": claim.maximum_interval_seconds,
                    "clauses": [
                        clause.to_dict()
                        for clause in claim.json_mixed_contract_clauses
                    ],
                },
                "semantic_observation": {
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "json_valid": json_valid,
                    "clause_results": clause_results,
                    "clauses_evaluated": len(clause_results),
                    "all_clauses_match": all_clauses_match,
                },
            }
            sample_evidence_bytes = json.dumps(
                sample_evidence_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            sample_evidence = self.evidence.put_bytes(
                sample_evidence_bytes,
                media_type="application/json; charset=utf-8",
                suffix=".json",
            )
            sample_evidence_refs.append(sample_evidence.evidence_ref)
            sample_results.append(
                {
                    "sample_index": sample_index,
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "elapsed_since_previous_start_seconds": persisted_interval,
                    "lower_bound_satisfied": lower_bound_satisfied,
                    "upper_bound_satisfied": upper_bound_satisfied,
                    "cadence_satisfied": cadence_satisfied,
                    "observed_http_status": observation.status_code,
                    "json_valid": json_valid,
                    "clauses_evaluated": len(clause_results),
                    "clause_results": clause_results,
                    "all_clauses_match": all_clauses_match,
                    "body_sha256": observation.body_sha256,
                    "body_bytes_observed": observation.body_bytes_observed,
                    "body_truncated": observation.body_truncated,
                    "body_digest_scope": observation.body_digest_scope,
                    "elapsed_ms": observation.elapsed_ms,
                    "provider": observation.provider,
                    "provider_version": observation.provider_version,
                    "captured_at_utc": observation.captured_at_utc,
                    "observation_evidence_ref": sample_evidence.evidence_ref,
                }
            )

        verdict_values = [item["verdict"] for item in sample_results]
        supported_count = verdict_values.count(RealityVerdict.SUPPORTED.value)
        contradicted_count = verdict_values.count(RealityVerdict.CONTRADICTED.value)
        unresolved_count = verdict_values.count(RealityVerdict.UNRESOLVED.value)
        observed_intervals = [
            float(item["elapsed_since_previous_start_seconds"])
            for item in sample_results
            if item["elapsed_since_previous_start_seconds"] is not None
        ]
        cadence_satisfied = all(
            item["cadence_satisfied"] is not False
            for item in sample_results
        )
        minimum_observed_interval_seconds = (
            min(observed_intervals) if observed_intervals else None
        )
        maximum_observed_interval_seconds = (
            max(observed_intervals) if observed_intervals else None
        )

        if not cadence_satisfied:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_cadenced_mixed_window_violation"
        elif contradicted_count:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_cadenced_mixed_sample_contradiction"
        elif unresolved_count:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_cadenced_mixed_sample_unresolved"
        else:
            verdict = RealityVerdict.SUPPORTED
            reason = "local_http_json_cadenced_mixed_all_observations_match"

        all_observations_match = (
            cadence_satisfied
            and supported_count == claim.repeat_observation_count
        )
        series_evidence_record = {
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "requires_value_read": requires_value_read,
                "repeat_observation_count": claim.repeat_observation_count,
                "minimum_interval_seconds": claim.minimum_interval_seconds,
                "maximum_interval_seconds": claim.maximum_interval_seconds,
                "interval_basis": "provider_invocation_start_monotonic",
                "clauses": [
                    clause.to_dict()
                    for clause in claim.json_mixed_contract_clauses
                ],
            },
            "timing_summary": {
                "cadence_satisfied": cadence_satisfied,
                "minimum_observed_interval_seconds": (
                    minimum_observed_interval_seconds
                ),
                "maximum_observed_interval_seconds": (
                    maximum_observed_interval_seconds
                ),
                "observed_interval_count": len(observed_intervals),
            },
            "repeated_observation": {
                "attempts_completed": len(sample_results),
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
            },
        }
        series_evidence_bytes = json.dumps(
            series_evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        series_evidence = self.evidence.put_bytes(
            series_evidence_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        used_refs = tuple(sample_evidence_refs + [series_evidence.evidence_ref])
        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_cadenced_mixed_contract",
                "http_url": claim.http_url,
                "expected_http_status": claim.expected_http_status,
                "clause_count": len(claim.json_mixed_contract_clauses),
                "observation_count_requested": claim.repeat_observation_count,
                "observation_attempts_completed": len(sample_results),
                "requires_value_read": requires_value_read,
                "minimum_interval_seconds": claim.minimum_interval_seconds,
                "maximum_interval_seconds": claim.maximum_interval_seconds,
                "interval_basis": "provider_invocation_start_monotonic",
                "cadence_satisfied": cadence_satisfied,
                "minimum_observed_interval_seconds": (
                    minimum_observed_interval_seconds
                ),
                "maximum_observed_interval_seconds": (
                    maximum_observed_interval_seconds
                ),
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
                "sample_evidence_refs": sample_evidence_refs,
                "series_evidence_ref": series_evidence.evidence_ref,
            },
            used_refs,
        )

    def _local_http_json_temporal_envelope_mixed_contract(
        self,
        claim: RealityClaim,
        *,
        provider: LocalHttpStateProvider,
    ) -> tuple[dict[str, Any], tuple[str, ...]]:
        assert claim.http_url is not None
        assert claim.expected_http_status is not None
        assert claim.json_mixed_contract_clauses
        assert claim.repeat_observation_count is not None
        assert claim.minimum_interval_seconds is not None
        assert claim.maximum_interval_seconds is not None
        assert claim.minimum_series_span_seconds is not None
        assert claim.maximum_series_span_seconds is not None

        requires_value_read = any(
            clause.requires_value_read
            for clause in claim.json_mixed_contract_clauses
        )
        permissions = [
            "reality.local_http.read",
            "reality.local_http.semantic.read",
            "reality.local_http.repeat.read",
            "reality.local_http.timing.wait",
            "reality.local_http.timing.cadence",
            "reality.local_http.timing.envelope",
        ]
        if requires_value_read:
            permissions.append("reality.local_http.semantic.value.read")

        for permission in permissions:
            if not self.authority.allows(permission):
                return (
                    {
                        "claim_id": claim.claim_id,
                        "kind": claim.kind.value,
                        "statement": claim.statement,
                        "verdict": RealityVerdict.BLOCKED.value,
                        "reason": f"missing_grant:{permission}",
                        "scope": "local_http_json_temporal_envelope_mixed_contract",
                        "http_url": claim.http_url,
                        "expected_http_status": claim.expected_http_status,
                        "clause_count": len(claim.json_mixed_contract_clauses),
                        "observation_count_requested": claim.repeat_observation_count,
                        "minimum_interval_seconds": claim.minimum_interval_seconds,
                        "maximum_interval_seconds": claim.maximum_interval_seconds,
                        "minimum_series_span_seconds": (
                            claim.minimum_series_span_seconds
                        ),
                        "maximum_series_span_seconds": (
                            claim.maximum_series_span_seconds
                        ),
                        "requires_value_read": requires_value_read,
                        "series_evidence_ref": None,
                    },
                    (),
                )

        sample_results: list[dict[str, Any]] = []
        sample_evidence_refs: list[str] = []
        first_start_monotonic: float | None = None
        previous_start_monotonic: float | None = None

        for sample_index in range(claim.repeat_observation_count):
            admissible_start_offset_min_seconds: float | None = None
            admissible_start_offset_max_seconds: float | None = None

            if previous_start_monotonic is not None:
                assert first_start_monotonic is not None
                remaining_after_current = (
                    claim.repeat_observation_count - 1 - sample_index
                )
                earliest_by_cadence = (
                    previous_start_monotonic + claim.minimum_interval_seconds
                )
                latest_by_cadence = (
                    previous_start_monotonic + claim.maximum_interval_seconds
                )
                earliest_by_envelope = (
                    first_start_monotonic
                    + claim.minimum_series_span_seconds
                    - (
                        remaining_after_current
                        * claim.maximum_interval_seconds
                    )
                )
                latest_by_envelope = (
                    first_start_monotonic
                    + claim.maximum_series_span_seconds
                    - (
                        remaining_after_current
                        * claim.minimum_interval_seconds
                    )
                )
                earliest_start = max(
                    earliest_by_cadence,
                    earliest_by_envelope,
                )
                latest_start = min(
                    latest_by_cadence,
                    latest_by_envelope,
                )
                admissible_start_offset_min_seconds = round(
                    earliest_start - first_start_monotonic,
                    9,
                )
                admissible_start_offset_max_seconds = round(
                    latest_start - first_start_monotonic,
                    9,
                )

                while True:
                    remaining = earliest_start - monotonic()
                    if remaining <= 0:
                        break
                    sleep(remaining)

            started_monotonic = monotonic()
            if first_start_monotonic is None:
                first_start_monotonic = started_monotonic

            interval_since_previous = (
                None
                if previous_start_monotonic is None
                else started_monotonic - previous_start_monotonic
            )
            persisted_interval = (
                None
                if interval_since_previous is None
                else round(interval_since_previous, 9)
            )
            series_span_so_far = round(
                started_monotonic - first_start_monotonic,
                9,
            )

            lower_bound_satisfied = (
                None
                if persisted_interval is None
                else persisted_interval >= claim.minimum_interval_seconds
            )
            upper_bound_satisfied = (
                None
                if persisted_interval is None
                else persisted_interval <= claim.maximum_interval_seconds
            )
            cadence_satisfied = (
                None
                if persisted_interval is None
                else bool(lower_bound_satisfied and upper_bound_satisfied)
            )
            start_window_satisfied = (
                None
                if admissible_start_offset_min_seconds is None
                or admissible_start_offset_max_seconds is None
                else (
                    admissible_start_offset_min_seconds
                    <= series_span_so_far
                    <= admissible_start_offset_max_seconds
                )
            )
            previous_start_monotonic = started_monotonic

            try:
                observation = provider.observe(
                    url=claim.http_url,
                    timeout_seconds=claim.http_timeout_seconds,
                    max_body_bytes=claim.http_max_body_bytes,
                )
            except LocalHttpObservationError as exc:
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": exc.code,
                        "elapsed_since_previous_start_seconds": persisted_interval,
                        "series_span_so_far_seconds": series_span_so_far,
                        "admissible_start_offset_min_seconds": (
                            admissible_start_offset_min_seconds
                        ),
                        "admissible_start_offset_max_seconds": (
                            admissible_start_offset_max_seconds
                        ),
                        "lower_bound_satisfied": lower_bound_satisfied,
                        "upper_bound_satisfied": upper_bound_satisfied,
                        "cadence_satisfied": cadence_satisfied,
                        "start_window_satisfied": start_window_satisfied,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue
            except Exception:  # noqa: BLE001 - provider boundary
                sample_results.append(
                    {
                        "sample_index": sample_index,
                        "verdict": RealityVerdict.UNRESOLVED.value,
                        "reason": "local_http_provider_error",
                        "elapsed_since_previous_start_seconds": persisted_interval,
                        "series_span_so_far_seconds": series_span_so_far,
                        "admissible_start_offset_min_seconds": (
                            admissible_start_offset_min_seconds
                        ),
                        "admissible_start_offset_max_seconds": (
                            admissible_start_offset_max_seconds
                        ),
                        "lower_bound_satisfied": lower_bound_satisfied,
                        "upper_bound_satisfied": upper_bound_satisfied,
                        "cadence_satisfied": cadence_satisfied,
                        "start_window_satisfied": start_window_satisfied,
                        "json_valid": None,
                        "clauses_evaluated": 0,
                        "all_clauses_match": None,
                        "observation_evidence_ref": None,
                    }
                )
                continue

            json_valid: bool | None = None
            clause_results: list[dict[str, Any]] = []

            if observation.status_code != claim.expected_http_status:
                sample_verdict = RealityVerdict.CONTRADICTED
                sample_reason = (
                    "local_http_json_temporal_envelope_sample_status_mismatch"
                )
            elif observation.body_truncated:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = (
                    "local_http_json_temporal_envelope_sample_body_truncated"
                )
            elif observation.body is None:
                sample_verdict = RealityVerdict.UNRESOLVED
                sample_reason = "local_http_semantic_body_unavailable"
            else:
                try:
                    document = strict_json_loads(observation.body)
                except (UnicodeDecodeError, ValueError):
                    json_valid = False
                    sample_verdict = RealityVerdict.CONTRADICTED
                    sample_reason = (
                        "local_http_json_temporal_envelope_sample_invalid_json"
                    )
                else:
                    json_valid = True
                    for clause_index, clause in enumerate(
                        claim.json_mixed_contract_clauses
                    ):
                        result = evaluate_json_mixed_contract_clause(
                            document,
                            clause,
                        )
                        result["clause_index"] = clause_index

                        if not result["pointer_exists"]:
                            clause_reason = "pointer_missing"
                        elif not result["type_matches"]:
                            clause_reason = "type_mismatch"
                        elif (
                            result["mode"] in {"structural", "scalar"}
                            and not result["predicate_matches"]
                        ):
                            clause_reason = "predicate_mismatch"
                        else:
                            clause_reason = "matches"

                        result["clause_reason"] = clause_reason
                        clause_results.append(result)

                    all_match = all(
                        bool(item["clause_matches"])
                        for item in clause_results
                    )
                    if all_match:
                        sample_verdict = RealityVerdict.SUPPORTED
                        sample_reason = (
                            "local_http_json_temporal_envelope_sample_matches"
                        )
                    else:
                        sample_verdict = RealityVerdict.CONTRADICTED
                        sample_reason = (
                            "local_http_json_temporal_envelope_sample_clause_mismatch"
                        )

            all_clauses_match = (
                all(bool(item["clause_matches"]) for item in clause_results)
                if clause_results
                else None
            )
            sample_evidence_record = {
                "sample_index": sample_index,
                "http_observation": observation.to_dict(),
                "timing_observation": {
                    "minimum_interval_seconds": claim.minimum_interval_seconds,
                    "maximum_interval_seconds": claim.maximum_interval_seconds,
                    "minimum_series_span_seconds": (
                        claim.minimum_series_span_seconds
                    ),
                    "maximum_series_span_seconds": (
                        claim.maximum_series_span_seconds
                    ),
                    "elapsed_since_previous_start_seconds": persisted_interval,
                    "series_span_so_far_seconds": series_span_so_far,
                    "admissible_start_offset_min_seconds": (
                        admissible_start_offset_min_seconds
                    ),
                    "admissible_start_offset_max_seconds": (
                        admissible_start_offset_max_seconds
                    ),
                    "lower_bound_satisfied": lower_bound_satisfied,
                    "upper_bound_satisfied": upper_bound_satisfied,
                    "cadence_satisfied": cadence_satisfied,
                    "start_window_satisfied": start_window_satisfied,
                    "interval_basis": "provider_invocation_start_monotonic",
                    "series_span_basis": (
                        "first_to_current_provider_invocation_start_monotonic"
                    ),
                },
                "semantic_contract": {
                    "expected_http_status": claim.expected_http_status,
                    "requires_value_read": requires_value_read,
                    "repeat_observation_count": claim.repeat_observation_count,
                    "clauses": [
                        clause.to_dict()
                        for clause in claim.json_mixed_contract_clauses
                    ],
                },
                "semantic_observation": {
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "json_valid": json_valid,
                    "clause_results": clause_results,
                    "clauses_evaluated": len(clause_results),
                    "all_clauses_match": all_clauses_match,
                },
            }
            sample_evidence_bytes = json.dumps(
                sample_evidence_record,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ).encode("utf-8")
            sample_evidence = self.evidence.put_bytes(
                sample_evidence_bytes,
                media_type="application/json; charset=utf-8",
                suffix=".json",
            )
            sample_evidence_refs.append(sample_evidence.evidence_ref)
            sample_results.append(
                {
                    "sample_index": sample_index,
                    "verdict": sample_verdict.value,
                    "reason": sample_reason,
                    "elapsed_since_previous_start_seconds": persisted_interval,
                    "series_span_so_far_seconds": series_span_so_far,
                    "admissible_start_offset_min_seconds": (
                        admissible_start_offset_min_seconds
                    ),
                    "admissible_start_offset_max_seconds": (
                        admissible_start_offset_max_seconds
                    ),
                    "lower_bound_satisfied": lower_bound_satisfied,
                    "upper_bound_satisfied": upper_bound_satisfied,
                    "cadence_satisfied": cadence_satisfied,
                    "start_window_satisfied": start_window_satisfied,
                    "observed_http_status": observation.status_code,
                    "json_valid": json_valid,
                    "clauses_evaluated": len(clause_results),
                    "clause_results": clause_results,
                    "all_clauses_match": all_clauses_match,
                    "body_sha256": observation.body_sha256,
                    "body_bytes_observed": observation.body_bytes_observed,
                    "body_truncated": observation.body_truncated,
                    "body_digest_scope": observation.body_digest_scope,
                    "elapsed_ms": observation.elapsed_ms,
                    "provider": observation.provider,
                    "provider_version": observation.provider_version,
                    "captured_at_utc": observation.captured_at_utc,
                    "observation_evidence_ref": sample_evidence.evidence_ref,
                }
            )

        verdict_values = [item["verdict"] for item in sample_results]
        supported_count = verdict_values.count(RealityVerdict.SUPPORTED.value)
        contradicted_count = verdict_values.count(RealityVerdict.CONTRADICTED.value)
        unresolved_count = verdict_values.count(RealityVerdict.UNRESOLVED.value)
        observed_intervals = [
            float(item["elapsed_since_previous_start_seconds"])
            for item in sample_results
            if item["elapsed_since_previous_start_seconds"] is not None
        ]
        cadence_satisfied = all(
            item["cadence_satisfied"] is not False
            for item in sample_results
        )
        scheduling_path_satisfied = all(
            item["start_window_satisfied"] is not False
            for item in sample_results
        )
        minimum_observed_interval_seconds = (
            min(observed_intervals) if observed_intervals else None
        )
        maximum_observed_interval_seconds = (
            max(observed_intervals) if observed_intervals else None
        )
        total_series_span_seconds = (
            float(sample_results[-1]["series_span_so_far_seconds"])
            if sample_results
            else None
        )
        series_span_lower_satisfied = (
            total_series_span_seconds is not None
            and total_series_span_seconds >= claim.minimum_series_span_seconds
        )
        series_span_upper_satisfied = (
            total_series_span_seconds is not None
            and total_series_span_seconds <= claim.maximum_series_span_seconds
        )
        series_span_satisfied = bool(
            series_span_lower_satisfied and series_span_upper_satisfied
        )
        temporal_envelope_satisfied = bool(
            cadence_satisfied and series_span_satisfied
        )

        if not cadence_satisfied:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_temporal_envelope_cadence_violation"
        elif not series_span_satisfied:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_temporal_envelope_series_span_violation"
        elif contradicted_count:
            verdict = RealityVerdict.CONTRADICTED
            reason = "local_http_json_temporal_envelope_sample_contradiction"
        elif unresolved_count:
            verdict = RealityVerdict.UNRESOLVED
            reason = "local_http_json_temporal_envelope_sample_unresolved"
        else:
            verdict = RealityVerdict.SUPPORTED
            reason = "local_http_json_temporal_envelope_all_observations_match"

        all_observations_match = (
            temporal_envelope_satisfied
            and supported_count == claim.repeat_observation_count
        )
        implied_minimum_series_span_seconds = (
            (claim.repeat_observation_count - 1)
            * claim.minimum_interval_seconds
        )
        implied_maximum_series_span_seconds = (
            (claim.repeat_observation_count - 1)
            * claim.maximum_interval_seconds
        )
        series_evidence_record = {
            "semantic_contract": {
                "expected_http_status": claim.expected_http_status,
                "requires_value_read": requires_value_read,
                "repeat_observation_count": claim.repeat_observation_count,
                "minimum_interval_seconds": claim.minimum_interval_seconds,
                "maximum_interval_seconds": claim.maximum_interval_seconds,
                "minimum_series_span_seconds": claim.minimum_series_span_seconds,
                "maximum_series_span_seconds": claim.maximum_series_span_seconds,
                "cadence_implied_minimum_series_span_seconds": (
                    implied_minimum_series_span_seconds
                ),
                "cadence_implied_maximum_series_span_seconds": (
                    implied_maximum_series_span_seconds
                ),
                "interval_basis": "provider_invocation_start_monotonic",
                "series_span_basis": (
                    "first_to_last_provider_invocation_start_monotonic"
                ),
                "clauses": [
                    clause.to_dict()
                    for clause in claim.json_mixed_contract_clauses
                ],
            },
            "timing_summary": {
                "cadence_satisfied": cadence_satisfied,
                "scheduling_path_satisfied": scheduling_path_satisfied,
                "minimum_observed_interval_seconds": (
                    minimum_observed_interval_seconds
                ),
                "maximum_observed_interval_seconds": (
                    maximum_observed_interval_seconds
                ),
                "observed_interval_count": len(observed_intervals),
                "total_series_span_seconds": total_series_span_seconds,
                "series_span_lower_satisfied": series_span_lower_satisfied,
                "series_span_upper_satisfied": series_span_upper_satisfied,
                "series_span_satisfied": series_span_satisfied,
                "temporal_envelope_satisfied": temporal_envelope_satisfied,
            },
            "repeated_observation": {
                "attempts_completed": len(sample_results),
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
            },
        }
        series_evidence_bytes = json.dumps(
            series_evidence_record,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        series_evidence = self.evidence.put_bytes(
            series_evidence_bytes,
            media_type="application/json; charset=utf-8",
            suffix=".json",
        )

        used_refs = tuple(sample_evidence_refs + [series_evidence.evidence_ref])
        return (
            {
                "claim_id": claim.claim_id,
                "kind": claim.kind.value,
                "statement": claim.statement,
                "verdict": verdict.value,
                "reason": reason,
                "scope": "local_http_json_temporal_envelope_mixed_contract",
                "http_url": claim.http_url,
                "expected_http_status": claim.expected_http_status,
                "clause_count": len(claim.json_mixed_contract_clauses),
                "observation_count_requested": claim.repeat_observation_count,
                "observation_attempts_completed": len(sample_results),
                "requires_value_read": requires_value_read,
                "minimum_interval_seconds": claim.minimum_interval_seconds,
                "maximum_interval_seconds": claim.maximum_interval_seconds,
                "minimum_series_span_seconds": claim.minimum_series_span_seconds,
                "maximum_series_span_seconds": claim.maximum_series_span_seconds,
                "interval_basis": "provider_invocation_start_monotonic",
                "series_span_basis": (
                    "first_to_last_provider_invocation_start_monotonic"
                ),
                "cadence_satisfied": cadence_satisfied,
                "scheduling_path_satisfied": scheduling_path_satisfied,
                "minimum_observed_interval_seconds": (
                    minimum_observed_interval_seconds
                ),
                "maximum_observed_interval_seconds": (
                    maximum_observed_interval_seconds
                ),
                "total_series_span_seconds": total_series_span_seconds,
                "series_span_lower_satisfied": series_span_lower_satisfied,
                "series_span_upper_satisfied": series_span_upper_satisfied,
                "series_span_satisfied": series_span_satisfied,
                "temporal_envelope_satisfied": temporal_envelope_satisfied,
                "supported_count": supported_count,
                "contradicted_count": contradicted_count,
                "unresolved_count": unresolved_count,
                "all_observations_match": all_observations_match,
                "sample_results": sample_results,
                "sample_evidence_refs": sample_evidence_refs,
                "series_evidence_ref": series_evidence.evidence_ref,
            },
            used_refs,
        )

    def verify(
        self,
        *,
        claims: tuple[RealityClaim, ...],
        max_evidence_bytes: int = 1_048_576,
        interface_provider: InterfaceStateProvider | None = None,
        tcp_listener_provider: TcpListenerStateProvider | None = None,
        local_http_provider: LocalHttpStateProvider | None = None,
    ) -> RealityVerificationResult:
        permission = "reality.verify"
        packet = self._packet(claims)
        selected_interface_provider = interface_provider or self.interface_provider
        selected_tcp_listener_provider = (
            tcp_listener_provider or self.tcp_listener_provider
        )
        selected_local_http_provider = local_http_provider or self.local_http_provider

        if not self.authority.allows(permission):
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason=f"reality verification blocked: missing explicit grant {permission}",
            )
            blocked = tuple(
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.BLOCKED.value,
                    "reason": f"missing_grant:{permission}",
                    "scope": claim.kind.value,
                }
                for claim in claims
            )
            receipt = RealityReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="reality.verifier",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                claims_checked=blocked,
                evidence_used=(),
                unresolved_contradictions=(),
                unresolved_claims=tuple(claim.claim_id for claim in claims),
                verdict_summary={RealityVerdict.BLOCKED.value: len(claims)},
                verification_method="bounded-evidence-v0.13",
                promotion_status="not_promoted",
                limitations=(
                    f"missing_grant:{permission}",
                    "evidence_not_read",
                    "verification_does_not_grant_action_authority",
                ),
            )
            self.ledger.append(receipt)
            return RealityVerificationResult(
                packet=packet,
                receipt=receipt,
                claim_results=blocked,
            )

        invalid_global: tuple[str, ...]
        if max_evidence_bytes <= 0:
            invalid_global = ("invalid_evidence_byte_budget",)
        else:
            invalid_global = ()

        invalid_claims = tuple(
            (claim, claim.validation_errors())
            for claim in claims
            if claim.validation_errors()
        )
        if not claims:
            invalid_global = invalid_global + ("empty_claim_set",)

        if invalid_global or invalid_claims:
            gate_receipt = self._gate_receipt(
                packet,
                status=MandalaStatus.BLOCKED,
                reason="reality verification blocked: invalid claim contract",
            )
            invalid_map = {claim.claim_id: errors for claim, errors in invalid_claims}
            blocked = tuple(
                {
                    "claim_id": claim.claim_id,
                    "kind": claim.kind.value,
                    "statement": claim.statement,
                    "verdict": RealityVerdict.BLOCKED.value,
                    "reason": (
                        ",".join(invalid_map[claim.claim_id])
                        if claim.claim_id in invalid_map
                        else ",".join(invalid_global)
                    ),
                    "scope": claim.kind.value,
                }
                for claim in claims
            )
            receipt = RealityReceipt(
                **receipt_meta(
                    packet,
                    status=MandalaStatus.BLOCKED,
                    produced_by="reality.verifier",
                    parent_receipt_id=gate_receipt.receipt_id,
                ),
                claims_checked=blocked,
                evidence_used=(),
                unresolved_contradictions=(),
                unresolved_claims=tuple(claim.claim_id for claim in claims),
                verdict_summary={RealityVerdict.BLOCKED.value: len(claims)},
                verification_method="bounded-evidence-v0.13",
                promotion_status="not_promoted",
                limitations=invalid_global
                + tuple(
                    error
                    for _, errors in invalid_claims
                    for error in errors
                ),
            )
            self.ledger.append(receipt)
            return RealityVerificationResult(
                packet=packet,
                receipt=receipt,
                claim_results=blocked,
            )

        gate_receipt = self._gate_receipt(
            packet,
            status=MandalaStatus.ACCEPTED,
            reason="reality verification contract admitted",
        )

        results: list[dict[str, Any]] = []
        used: list[str] = []

        for claim in claims:
            if claim.kind is RealityClaimKind.SOURCE_CONTAINS_TEXT:
                result, claim_used = self._source_contains_text(
                    claim,
                    max_evidence_bytes=max_evidence_bytes,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.WORLD_STATE:
                results.append(self._world_state(claim))
                continue

            if claim.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
                result, claim_used = self._local_interface_state(
                    claim,
                    provider=selected_interface_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
                result, claim_used = self._local_tcp_listener_state(
                    claim,
                    provider=selected_tcp_listener_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE:
                result, claim_used = self._local_http_response_state(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT:
                result, claim_used = self._local_http_json_contract(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE:
                result, claim_used = self._local_http_json_predicate(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT:
                result, claim_used = self._local_http_json_multi_contract(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE:
                result, claim_used = self._local_http_json_scalar_predicate(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT:
                result, claim_used = self._local_http_json_mixed_contract(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if (
                claim.kind
                is RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT
            ):
                result, claim_used = self._local_http_json_repeated_mixed_contract(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if claim.kind is RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT:
                result, claim_used = self._local_http_json_timed_mixed_contract(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if (
                claim.kind
                is RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT
            ):
                result, claim_used = self._local_http_json_cadenced_mixed_contract(
                    claim,
                    provider=selected_local_http_provider,
                )
                results.append(result)
                used.extend(claim_used)
                continue

            if (
                claim.kind
                is RealityClaimKind.LOCAL_HTTP_JSON_TEMPORAL_ENVELOPE_MIXED_CONTRACT
            ):
                result, claim_used = (
                    self._local_http_json_temporal_envelope_mixed_contract(
                        claim,
                        provider=selected_local_http_provider,
                    )
                )
                results.append(result)
                used.extend(claim_used)
                continue

            results.append(
                {
                    "claim_id": claim.claim_id,
                    "kind": str(claim.kind),
                    "statement": claim.statement,
                    "verdict": RealityVerdict.UNRESOLVED.value,
                    "reason": "unsupported_claim_kind",
                    "scope": "unknown",
                }
            )

        verdicts = [item["verdict"] for item in results]
        counts = Counter(str(item) for item in verdicts)

        if RealityVerdict.BLOCKED.value in verdicts:
            status = MandalaStatus.BLOCKED
        elif RealityVerdict.CONTRADICTED.value in verdicts:
            status = MandalaStatus.DISPUTED
        elif RealityVerdict.UNRESOLVED.value in verdicts:
            status = MandalaStatus.UNKNOWN
        else:
            status = MandalaStatus.ACCEPTED

        contradicted = tuple(
            item["claim_id"]
            for item in results
            if item["verdict"] == RealityVerdict.CONTRADICTED.value
        )
        unresolved = tuple(
            item["claim_id"]
            for item in results
            if item["verdict"] == RealityVerdict.UNRESOLVED.value
        )

        receipt = RealityReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="reality.verifier",
                parent_receipt_id=gate_receipt.receipt_id,
            ),
            claims_checked=tuple(results),
            evidence_used=tuple(dict.fromkeys(used)),
            unresolved_contradictions=contradicted,
            unresolved_claims=unresolved,
            verdict_summary=dict(counts),
            verification_method="bounded-evidence-v0.13",
            promotion_status="not_promoted",
            limitations=(
                "lexical_source_support_is_not_world_state_verification",
                "source_content_support_does_not_establish_world_truth",
                "generic_world_state_requires_independent_verifier",
                "local_interface_state_uses_direct_host_observation",
                "local_tcp_listener_state_uses_direct_host_observation",
                "local_http_response_state_uses_provider_observation",
                "local_http_json_contract_uses_bounded_semantic_observation",
                "local_http_json_predicate_uses_bounded_structural_observation",
                "local_http_json_multi_contract_uses_single_observation_snapshot",
                "semantic_http_read_requires_separate_grant",
                "scalar_value_read_requires_separate_grant",
                "local_http_json_contract_requires_complete_body",
                "json_pointer_type_check_is_not_application_health",
                "json_structural_predicate_is_not_application_health",
                "json_structural_predicates_do_not_compare_raw_values",
                "multi_clause_success_is_not_application_health",
                "multi_clause_results_share_one_point_in_time_observation",
                "scalar_predicate_observed_value_not_persisted",
                "scalar_predicate_is_not_application_health",
                "mixed_contract_uses_single_observation_snapshot",
                "mixed_contract_scalar_clauses_require_value_read_grant",
                "mixed_contract_scalar_observed_values_not_persisted",
                "mixed_contract_success_is_not_application_health",
                "repeated_http_read_requires_separate_grant",
                "repeated_mixed_contract_uses_discrete_observations",
                "repeated_mixed_contract_enforces_no_minimum_interval",
                "repeated_mixed_success_is_not_continuous_health",
                "repeated_mixed_scalar_observed_values_not_persisted",
                "repeated_mixed_contradiction_precedes_unresolved_samples",
                "timed_http_wait_requires_separate_grant",
                "timed_mixed_interval_uses_monotonic_invocation_starts",
                "timed_mixed_interval_is_minimum_not_fixed_period",
                "timed_mixed_success_is_not_continuous_health",
                "timed_mixed_wall_clock_timestamps_do_not_establish_spacing",
                "timed_mixed_scalar_observed_values_not_persisted",
                "cadenced_http_control_requires_separate_grant",
                "cadenced_mixed_window_uses_monotonic_invocation_starts",
                "cadenced_mixed_window_is_not_continuous_monitoring",
                "cadenced_mixed_provider_overrun_can_violate_upper_bound",
                "cadenced_mixed_wall_clock_timestamps_do_not_establish_window",
                "cadenced_mixed_scalar_observed_values_not_persisted",
                "temporal_envelope_control_requires_separate_grant",
                "temporal_envelope_uses_monotonic_invocation_starts",
                "temporal_envelope_scheduler_preserves_future_feasibility",
                "temporal_envelope_span_is_first_to_last_start",
                "temporal_envelope_is_not_continuous_monitoring",
                "temporal_envelope_provider_overrun_can_violate_contract",
                "temporal_envelope_wall_clock_does_not_establish_span",
                "temporal_envelope_scalar_observed_values_not_persisted",
                "http_status_is_not_application_health",
                "live_http_transport_is_adapter_scoped",
                "host_observation_is_point_in_time",
                "verification_does_not_grant_action_authority",
                "no_automatic_memory_promotion",
            ),
        )
        self.ledger.append(receipt)
        return RealityVerificationResult(
            packet=packet,
            receipt=receipt,
            claim_results=tuple(results),
        )
