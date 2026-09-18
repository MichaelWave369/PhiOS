from __future__ import annotations

from collections import Counter
import json
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
                "verification_method": "bounded-evidence-v0.4",
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
                verification_method="bounded-evidence-v0.4",
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
                verification_method="bounded-evidence-v0.4",
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
            verification_method="bounded-evidence-v0.4",
            promotion_status="not_promoted",
            limitations=(
                "lexical_source_support_is_not_world_state_verification",
                "source_content_support_does_not_establish_world_truth",
                "generic_world_state_requires_independent_verifier",
                "local_interface_state_uses_direct_host_observation",
                "local_tcp_listener_state_uses_direct_host_observation",
                "local_http_response_state_uses_provider_observation",
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
