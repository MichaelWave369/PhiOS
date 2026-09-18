from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from phios.mandala import MandalaPacket, RealityReceipt

from .local_http import local_http_url_error
from .local_json import (
    JSON_TYPE_NAMES,
    JsonContractClause,
    JsonMixedContractClause,
    json_pointer_error,
    json_scalar_predicate_error,
    json_structural_predicate_error,
)


class RealityClaimKind(StrEnum):
    SOURCE_CONTAINS_TEXT = "source_contains_text"
    WORLD_STATE = "world_state"
    LOCAL_INTERFACE_STATE = "local_interface_state"
    LOCAL_TCP_LISTENER_STATE = "local_tcp_listener_state"
    LOCAL_HTTP_RESPONSE_STATE = "local_http_response_state"
    LOCAL_HTTP_JSON_CONTRACT = "local_http_json_contract"
    LOCAL_HTTP_JSON_PREDICATE = "local_http_json_predicate"
    LOCAL_HTTP_JSON_MULTI_CONTRACT = "local_http_json_multi_contract"
    LOCAL_HTTP_JSON_SCALAR_PREDICATE = "local_http_json_scalar_predicate"
    LOCAL_HTTP_JSON_MIXED_CONTRACT = "local_http_json_mixed_contract"
    LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT = "local_http_json_repeated_mixed_contract"
    LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT = "local_http_json_timed_mixed_contract"
    LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT = "local_http_json_cadenced_mixed_contract"


class RealityVerdict(StrEnum):
    SUPPORTED = "SUPPORTED"
    CONTRADICTED = "CONTRADICTED"
    UNRESOLVED = "UNRESOLVED"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True, kw_only=True)
class RealityClaim:
    claim_id: str
    kind: RealityClaimKind
    statement: str
    evidence_refs: tuple[str, ...] = ()
    expected_text: str | None = None
    case_sensitive: bool = False
    interface_name: str | None = None
    expected_is_up: bool | None = None
    local_port: int | None = None
    local_address: str | None = None
    expected_listening: bool | None = None
    http_url: str | None = None
    expected_http_status: int | None = None
    http_timeout_seconds: float = 2.0
    http_max_body_bytes: int = 65_536
    json_pointer: str | None = None
    expected_json_type: str | None = None
    json_predicate_kind: str | None = None
    json_predicate_bound: int | None = None
    json_contract_clauses: tuple[JsonContractClause, ...] = ()
    json_scalar_predicate_kind: str | None = None
    json_scalar_operand: str | None = None
    json_mixed_contract_clauses: tuple[JsonMixedContractClause, ...] = ()
    repeat_observation_count: int | None = None
    minimum_interval_seconds: float | None = None
    maximum_interval_seconds: float | None = None

    @classmethod
    def create(
        cls,
        *,
        kind: RealityClaimKind,
        statement: str,
        evidence_refs: tuple[str, ...] = (),
        expected_text: str | None = None,
        case_sensitive: bool = False,
        interface_name: str | None = None,
        expected_is_up: bool | None = None,
        local_port: int | None = None,
        local_address: str | None = None,
        expected_listening: bool | None = None,
        http_url: str | None = None,
        expected_http_status: int | None = None,
        http_timeout_seconds: float = 2.0,
        http_max_body_bytes: int = 65_536,
        json_pointer: str | None = None,
        expected_json_type: str | None = None,
        json_predicate_kind: str | None = None,
        json_predicate_bound: int | None = None,
        json_contract_clauses: tuple[JsonContractClause, ...] = (),
        json_scalar_predicate_kind: str | None = None,
        json_scalar_operand: str | None = None,
        json_mixed_contract_clauses: tuple[JsonMixedContractClause, ...] = (),
        repeat_observation_count: int | None = None,
        minimum_interval_seconds: float | None = None,
        maximum_interval_seconds: float | None = None,
    ) -> "RealityClaim":
        return cls(
            claim_id=str(uuid.uuid4()),
            kind=kind,
            statement=statement,
            evidence_refs=tuple(dict.fromkeys(evidence_refs)),
            expected_text=expected_text,
            case_sensitive=case_sensitive,
            interface_name=interface_name,
            expected_is_up=expected_is_up,
            local_port=local_port,
            local_address=local_address,
            expected_listening=expected_listening,
            http_url=http_url,
            expected_http_status=expected_http_status,
            http_timeout_seconds=http_timeout_seconds,
            http_max_body_bytes=http_max_body_bytes,
            json_pointer=json_pointer,
            expected_json_type=expected_json_type,
            json_predicate_kind=json_predicate_kind,
            json_predicate_bound=json_predicate_bound,
            json_contract_clauses=tuple(json_contract_clauses),
            json_scalar_predicate_kind=json_scalar_predicate_kind,
            json_scalar_operand=json_scalar_operand,
            json_mixed_contract_clauses=tuple(json_mixed_contract_clauses),
            repeat_observation_count=repeat_observation_count,
            minimum_interval_seconds=minimum_interval_seconds,
            maximum_interval_seconds=maximum_interval_seconds,
        )

    def validation_errors(self) -> tuple[str, ...]:
        errors: list[str] = []
        if not self.statement.strip():
            errors.append("empty_statement")

        if self.kind is RealityClaimKind.SOURCE_CONTAINS_TEXT:
            if not self.evidence_refs:
                errors.append("source_claim_requires_evidence")
            if self.expected_text is None or not self.expected_text.strip():
                errors.append("source_claim_requires_expected_text")

        if self.kind is RealityClaimKind.LOCAL_INTERFACE_STATE:
            if self.interface_name is None or not self.interface_name.strip():
                errors.append("local_interface_claim_requires_interface_name")
            if self.expected_is_up is None:
                errors.append("local_interface_claim_requires_expected_state")

        if self.kind is RealityClaimKind.LOCAL_TCP_LISTENER_STATE:
            if self.local_port is None:
                errors.append("local_tcp_claim_requires_port")
            elif not 1 <= self.local_port <= 65535:
                errors.append("local_tcp_claim_invalid_port")
            if self.local_address is not None and not self.local_address.strip():
                errors.append("local_tcp_claim_invalid_address")
            if self.expected_listening is None:
                errors.append("local_tcp_claim_requires_expected_state")

        if self.kind in {
            RealityClaimKind.LOCAL_HTTP_RESPONSE_STATE,
            RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
            RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE,
            RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT,
            RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
            RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
            RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
            RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT,
            RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
        }:
            url_error = local_http_url_error(self.http_url)
            if url_error is not None:
                errors.append(url_error)
            if self.expected_http_status is None:
                errors.append("local_http_claim_requires_expected_status")
            elif not 100 <= self.expected_http_status <= 599:
                errors.append("local_http_claim_invalid_expected_status")
            if not 0.1 <= self.http_timeout_seconds <= 10.0:
                errors.append("local_http_claim_invalid_timeout")
            if not 1 <= self.http_max_body_bytes <= 1_048_576:
                errors.append("local_http_claim_invalid_body_budget")

        if self.kind in {
            RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT,
            RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE,
            RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE,
        }:
            pointer_error = json_pointer_error(self.json_pointer)
            if pointer_error is not None:
                errors.append(pointer_error)

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_CONTRACT:
            if self.expected_json_type is None:
                errors.append("local_http_json_claim_requires_expected_type")
            elif self.expected_json_type not in JSON_TYPE_NAMES:
                errors.append("local_http_json_claim_invalid_expected_type")

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_PREDICATE:
            predicate_error = json_structural_predicate_error(
                self.json_predicate_kind,
                self.json_predicate_bound,
            )
            if predicate_error is not None:
                errors.append(predicate_error)

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE:
            scalar_error = json_scalar_predicate_error(
                self.json_scalar_predicate_kind,
                self.json_scalar_operand,
            )
            if scalar_error is not None:
                errors.append(scalar_error)
            if any(
                value is not None
                for value in (
                    self.expected_json_type,
                    self.json_predicate_kind,
                    self.json_predicate_bound,
                )
            ):
                errors.append("local_http_json_scalar_predicate_disallows_other_modes")

        if (
            self.kind is not RealityClaimKind.LOCAL_HTTP_JSON_SCALAR_PREDICATE
            and (
                self.json_scalar_predicate_kind is not None
                or self.json_scalar_operand is not None
            )
        ):
            errors.append("json_scalar_predicate_fields_only_for_scalar_claim")

        if (
            self.kind is not RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT
            and self.json_contract_clauses
        ):
            errors.append("json_contract_clauses_only_for_multi_contract")

        if (
            self.kind
            not in {
                RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT,
                RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
                RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT,
                RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
            }
            and self.json_mixed_contract_clauses
        ):
            errors.append("json_mixed_contract_clauses_only_for_mixed_contract")

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_MULTI_CONTRACT:
            if any(
                value is not None
                for value in (
                    self.json_pointer,
                    self.expected_json_type,
                    self.json_predicate_kind,
                    self.json_predicate_bound,
                )
            ):
                errors.append("local_http_json_multi_contract_disallows_single_fields")
            if not 1 <= len(self.json_contract_clauses) <= 8:
                errors.append("local_http_json_multi_contract_requires_1_to_8_clauses")
            for index, clause in enumerate(self.json_contract_clauses):
                for error in clause.validation_errors():
                    errors.append(f"json_clause_{index}:{error}")

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_MIXED_CONTRACT:
            if any(
                value is not None
                for value in (
                    self.json_pointer,
                    self.expected_json_type,
                    self.json_predicate_kind,
                    self.json_predicate_bound,
                    self.json_scalar_predicate_kind,
                    self.json_scalar_operand,
                )
            ) or self.json_contract_clauses:
                errors.append("local_http_json_mixed_contract_disallows_legacy_fields")
            if not 1 <= len(self.json_mixed_contract_clauses) <= 8:
                errors.append("local_http_json_mixed_contract_requires_1_to_8_clauses")
            for index, mixed_clause in enumerate(self.json_mixed_contract_clauses):
                for error in mixed_clause.validation_errors():
                    errors.append(f"json_mixed_clause_{index}:{error}")

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT:
            if any(
                value is not None
                for value in (
                    self.json_pointer,
                    self.expected_json_type,
                    self.json_predicate_kind,
                    self.json_predicate_bound,
                    self.json_scalar_predicate_kind,
                    self.json_scalar_operand,
                )
            ) or self.json_contract_clauses:
                errors.append(
                    "local_http_json_repeated_mixed_contract_disallows_legacy_fields"
                )
            if not 1 <= len(self.json_mixed_contract_clauses) <= 8:
                errors.append(
                    "local_http_json_repeated_mixed_contract_requires_1_to_8_clauses"
                )
            for index, repeated_clause in enumerate(
                self.json_mixed_contract_clauses
            ):
                for error in repeated_clause.validation_errors():
                    errors.append(f"json_repeated_mixed_clause_{index}:{error}")
            if (
                isinstance(self.repeat_observation_count, bool)
                or not isinstance(self.repeat_observation_count, int)
                or not 2 <= self.repeat_observation_count <= 5
            ):
                errors.append(
                    "local_http_json_repeated_mixed_contract_requires_2_to_5_observations"
                )

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT:
            if any(
                value is not None
                for value in (
                    self.json_pointer,
                    self.expected_json_type,
                    self.json_predicate_kind,
                    self.json_predicate_bound,
                    self.json_scalar_predicate_kind,
                    self.json_scalar_operand,
                )
            ) or self.json_contract_clauses:
                errors.append(
                    "local_http_json_timed_mixed_contract_disallows_legacy_fields"
                )
            if not 1 <= len(self.json_mixed_contract_clauses) <= 8:
                errors.append(
                    "local_http_json_timed_mixed_contract_requires_1_to_8_clauses"
                )
            for index, timed_clause in enumerate(
                self.json_mixed_contract_clauses
            ):
                for error in timed_clause.validation_errors():
                    errors.append(f"json_timed_mixed_clause_{index}:{error}")
            if (
                isinstance(self.repeat_observation_count, bool)
                or not isinstance(self.repeat_observation_count, int)
                or not 2 <= self.repeat_observation_count <= 5
            ):
                errors.append(
                    "local_http_json_timed_mixed_contract_requires_2_to_5_observations"
                )
            if (
                isinstance(self.minimum_interval_seconds, bool)
                or not isinstance(self.minimum_interval_seconds, (int, float))
                or not 0.05 <= float(self.minimum_interval_seconds) <= 10.0
            ):
                errors.append(
                    "local_http_json_timed_mixed_contract_requires_interval_0_05_to_10_seconds"
                )

        if self.kind is RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT:
            if any(
                value is not None
                for value in (
                    self.json_pointer,
                    self.expected_json_type,
                    self.json_predicate_kind,
                    self.json_predicate_bound,
                    self.json_scalar_predicate_kind,
                    self.json_scalar_operand,
                )
            ) or self.json_contract_clauses:
                errors.append(
                    "local_http_json_cadenced_mixed_contract_disallows_legacy_fields"
                )
            if not 1 <= len(self.json_mixed_contract_clauses) <= 8:
                errors.append(
                    "local_http_json_cadenced_mixed_contract_requires_1_to_8_clauses"
                )
            for index, cadenced_clause in enumerate(
                self.json_mixed_contract_clauses
            ):
                for error in cadenced_clause.validation_errors():
                    errors.append(f"json_cadenced_mixed_clause_{index}:{error}")
            if (
                isinstance(self.repeat_observation_count, bool)
                or not isinstance(self.repeat_observation_count, int)
                or not 2 <= self.repeat_observation_count <= 5
            ):
                errors.append(
                    "local_http_json_cadenced_mixed_contract_requires_2_to_5_observations"
                )
            min_interval = self.minimum_interval_seconds
            max_interval = self.maximum_interval_seconds
            min_valid = (
                not isinstance(min_interval, bool)
                and isinstance(min_interval, (int, float))
                and 0.05 <= float(min_interval) <= 10.0
            )
            max_valid = (
                not isinstance(max_interval, bool)
                and isinstance(max_interval, (int, float))
                and 0.05 <= float(max_interval) <= 10.0
            )
            if not min_valid:
                errors.append(
                    "local_http_json_cadenced_mixed_contract_requires_min_interval_0_05_to_10_seconds"
                )
            if not max_valid:
                errors.append(
                    "local_http_json_cadenced_mixed_contract_requires_max_interval_0_05_to_10_seconds"
                )
            if min_valid and max_valid:
                assert isinstance(min_interval, (int, float))
                assert isinstance(max_interval, (int, float))
                if float(max_interval) < float(min_interval):
                    errors.append(
                        "local_http_json_cadenced_mixed_contract_requires_max_interval_gte_min"
                    )

        if (
            self.kind
            not in {
                RealityClaimKind.LOCAL_HTTP_JSON_REPEATED_MIXED_CONTRACT,
                RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT,
                RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
            }
            and self.repeat_observation_count is not None
        ):
            errors.append(
                "repeat_observation_count_only_for_repeated_mixed_contract"
            )

        if (
            self.kind
            not in {
                RealityClaimKind.LOCAL_HTTP_JSON_TIMED_MIXED_CONTRACT,
                RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT,
            }
            and self.minimum_interval_seconds is not None
        ):
            errors.append(
                "minimum_interval_seconds_only_for_timed_mixed_contract"
            )

        if (
            self.kind is not RealityClaimKind.LOCAL_HTTP_JSON_CADENCED_MIXED_CONTRACT
            and self.maximum_interval_seconds is not None
        ):
            errors.append(
                "maximum_interval_seconds_only_for_cadenced_mixed_contract"
            )

        return tuple(errors)

    def to_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "kind": self.kind.value,
            "statement": self.statement,
            "evidence_refs": list(self.evidence_refs),
            "expected_text": self.expected_text,
            "case_sensitive": self.case_sensitive,
            "interface_name": self.interface_name,
            "expected_is_up": self.expected_is_up,
            "local_port": self.local_port,
            "local_address": self.local_address,
            "expected_listening": self.expected_listening,
            "http_url": self.http_url,
            "expected_http_status": self.expected_http_status,
            "http_timeout_seconds": self.http_timeout_seconds,
            "http_max_body_bytes": self.http_max_body_bytes,
            "json_pointer": self.json_pointer,
            "expected_json_type": self.expected_json_type,
            "json_predicate_kind": self.json_predicate_kind,
            "json_predicate_bound": self.json_predicate_bound,
            "json_contract_clauses": [
                clause.to_dict() for clause in self.json_contract_clauses
            ],
            "json_scalar_predicate_kind": self.json_scalar_predicate_kind,
            "json_scalar_operand": self.json_scalar_operand,
            "json_mixed_contract_clauses": [
                clause.to_dict() for clause in self.json_mixed_contract_clauses
            ],
            "repeat_observation_count": self.repeat_observation_count,
            "minimum_interval_seconds": self.minimum_interval_seconds,
            "maximum_interval_seconds": self.maximum_interval_seconds,
        }


@dataclass(frozen=True, kw_only=True)
class RealityVerificationResult:
    packet: MandalaPacket
    receipt: RealityReceipt
    claim_results: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "packet": self.packet.to_dict(),
            "receipt": self.receipt.to_dict(),
            "claim_results": [dict(item) for item in self.claim_results],
        }
