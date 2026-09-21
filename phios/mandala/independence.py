from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from itertools import combinations
from typing import Iterable, Mapping

from .contracts import MandalaPacket, MandalaStatus
from .ledger import MandalaReceiptLedger
from .receipts import (
    DisagreementDecompositionReceipt,
    IndependenceReceipt,
    receipt_meta,
)

INDEPENDENCE_POLICY_SCHEMA_VERSION = "phios.independence_policy.v0.1"
_ALLOWED_STANCES = ("SUPPORTS", "CONTRADICTS", "UNCERTAIN")
_ALLOWED_RELATIONS = ("INDEPENDENT", "DEPENDENT", "UNKNOWN")


class IndependenceContractError(ValueError):
    """Raised when evidence-path independence cannot be assessed safely."""


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
        raise IndependenceContractError(
            "independence evidence must be canonical JSON"
        ) from exc


def _sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _require_text(value: str, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise IndependenceContractError(f"{label} must be non-empty")
    return value.strip()


def _require_sha(value: str, label: str) -> str:
    value = _require_text(value, label).lower()
    if len(value) != 64:
        raise IndependenceContractError(f"{label} must be SHA-256 hex")
    try:
        int(value, 16)
    except ValueError as exc:
        raise IndependenceContractError(f"{label} must be SHA-256 hex") from exc
    return value


def _labels(values: Iterable[str], label: str) -> tuple[str, ...]:
    return tuple(sorted({_require_text(value, label) for value in values}))


@dataclass(frozen=True, slots=True)
class EvidencePathDeclaration:
    path_id: str
    claim_id: str
    actor_id: str
    stance: str
    output_sha256: str
    evidence_refs: tuple[str, ...] = ()
    root_source_refs: tuple[str, ...] = ()
    parent_path_ids: tuple[str, ...] = ()
    transformation_lineage_sha256s: tuple[str, ...] = ()
    context_sha256: str | None = None
    method: str = "unspecified"

    def normalized(self) -> "EvidencePathDeclaration":
        stance = _require_text(self.stance, "stance").upper()
        if stance not in _ALLOWED_STANCES:
            raise IndependenceContractError(
                f"stance must be one of {_ALLOWED_STANCES}"
            )
        context = (
            _require_sha(self.context_sha256, "context_sha256")
            if self.context_sha256 is not None
            else None
        )
        return EvidencePathDeclaration(
            path_id=_require_text(self.path_id, "path_id"),
            claim_id=_require_text(self.claim_id, "claim_id"),
            actor_id=_require_text(self.actor_id, "actor_id"),
            stance=stance,
            output_sha256=_require_sha(self.output_sha256, "output_sha256"),
            evidence_refs=_labels(self.evidence_refs, "evidence_ref"),
            root_source_refs=_labels(self.root_source_refs, "root_source_ref"),
            parent_path_ids=_labels(self.parent_path_ids, "parent_path_id"),
            transformation_lineage_sha256s=tuple(
                sorted(
                    {
                        _require_sha(value, "transformation_lineage_sha256")
                        for value in self.transformation_lineage_sha256s
                    }
                )
            ),
            context_sha256=context,
            method=_require_text(self.method, "method"),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "path_id": self.path_id,
            "claim_id": self.claim_id,
            "actor_id": self.actor_id,
            "stance": self.stance,
            "output_sha256": self.output_sha256,
            "evidence_refs": list(self.evidence_refs),
            "root_source_refs": list(self.root_source_refs),
            "parent_path_ids": list(self.parent_path_ids),
            "transformation_lineage_sha256s": list(
                self.transformation_lineage_sha256s
            ),
            "context_sha256": self.context_sha256,
            "method": self.method,
        }


@dataclass(frozen=True, slots=True)
class IndependenceAssertion:
    left_path_id: str
    right_path_id: str
    relation: str
    basis_refs: tuple[str, ...] = ()
    reason: str = ""

    def normalized(self) -> "IndependenceAssertion":
        left = _require_text(self.left_path_id, "left_path_id")
        right = _require_text(self.right_path_id, "right_path_id")
        if left == right:
            raise IndependenceContractError(
                "independence assertion requires two distinct paths"
            )
        relation = _require_text(self.relation, "relation").upper()
        if relation not in _ALLOWED_RELATIONS:
            raise IndependenceContractError(
                f"relation must be one of {_ALLOWED_RELATIONS}"
            )
        return IndependenceAssertion(
            left_path_id=min(left, right),
            right_path_id=max(left, right),
            relation=relation,
            basis_refs=_labels(self.basis_refs, "basis_ref"),
            reason=self.reason.strip(),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "left_path_id": self.left_path_id,
            "right_path_id": self.right_path_id,
            "relation": self.relation,
            "basis_refs": list(self.basis_refs),
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class DeliberationEvidenceResult:
    independence_receipt: IndependenceReceipt
    disagreement_receipt: DisagreementDecompositionReceipt


class DeliberationEvidenceAssessor:
    """Assess evidence-path independence without treating agreement as authority."""

    def __init__(self, ledger: MandalaReceiptLedger | None = None) -> None:
        self.ledger = ledger

    def assess(
        self,
        *,
        packet: MandalaPacket,
        claim_id: str,
        paths: tuple[EvidencePathDeclaration, ...],
        assertions: tuple[IndependenceAssertion, ...] = (),
    ) -> DeliberationEvidenceResult:
        claim_id = _require_text(claim_id, "claim_id")
        normalized_paths = tuple(path.normalized() for path in paths)
        if not normalized_paths:
            raise IndependenceContractError("at least one evidence path is required")
        ids = tuple(path.path_id for path in normalized_paths)
        if len(set(ids)) != len(ids):
            raise IndependenceContractError("path_id values must be unique")
        if any(path.claim_id != claim_id for path in normalized_paths):
            raise IndependenceContractError(
                "all evidence paths must bind the assessed claim_id"
            )
        known_ids = set(ids)
        for path in normalized_paths:
            if path.path_id in path.parent_path_ids:
                raise IndependenceContractError("path cannot be its own parent")
            if not set(path.parent_path_ids).issubset(known_ids):
                raise IndependenceContractError(
                    "parent_path_ids must reference paths in the same assessment"
                )

        assertion_map: dict[tuple[str, str], IndependenceAssertion] = {}
        for raw in assertions:
            normalized_assertion = raw.normalized()
            key = (
                normalized_assertion.left_path_id,
                normalized_assertion.right_path_id,
            )
            if key[0] not in known_ids or key[1] not in known_ids:
                raise IndependenceContractError(
                    "independence assertion references unknown path"
                )
            if key in assertion_map:
                raise IndependenceContractError(
                    "duplicate independence assertion for path pair"
                )
            assertion_map[key] = normalized_assertion

        path_map = {path.path_id: path for path in normalized_paths}
        pairwise: list[dict[str, object]] = []
        relations: dict[tuple[str, str], str] = {}
        for left_id, right_id in combinations(sorted(ids), 2):
            left = path_map[left_id]
            right = path_map[right_id]
            key = (left_id, right_id)
            forced_reasons = self._forced_dependency_reasons(left, right)
            assertion = assertion_map.get(key)

            if forced_reasons:
                if assertion is not None and assertion.relation == "INDEPENDENT":
                    raise IndependenceContractError(
                        "path pair cannot be asserted independent while a shared "
                        "dependency is present"
                    )
                relation = "DEPENDENT"
                basis_refs = (
                    assertion.basis_refs if assertion is not None else ()
                )
                reasons = tuple(sorted(set(forced_reasons)))
            elif assertion is not None and assertion.relation == "INDEPENDENT":
                if not assertion.basis_refs:
                    raise IndependenceContractError(
                        "INDEPENDENT assertions require explicit basis_refs"
                    )
                if not left.root_source_refs or not right.root_source_refs:
                    raise IndependenceContractError(
                        "INDEPENDENT assertions require explicit root_source_refs "
                        "on both paths"
                    )
                relation = "INDEPENDENT"
                basis_refs = assertion.basis_refs
                reasons = (
                    (assertion.reason,)
                    if assertion.reason
                    else ("explicit_independence_basis",)
                )
            elif assertion is not None and assertion.relation == "DEPENDENT":
                relation = "DEPENDENT"
                basis_refs = assertion.basis_refs
                reasons = (
                    (assertion.reason,)
                    if assertion.reason
                    else ("explicit_dependency_assertion",)
                )
            else:
                relation = "UNKNOWN"
                basis_refs = assertion.basis_refs if assertion is not None else ()
                reasons = (
                    (assertion.reason,)
                    if assertion is not None and assertion.reason
                    else ("independence_not_demonstrated",)
                )

            relations[key] = relation
            pairwise.append(
                {
                    "left_path_id": left_id,
                    "right_path_id": right_id,
                    "relation": relation,
                    "basis_refs": list(basis_refs),
                    "reasons": list(reasons),
                }
            )

        independent_pairs = sum(
            1 for relation in relations.values() if relation == "INDEPENDENT"
        )
        dependent_pairs = sum(
            1 for relation in relations.values() if relation == "DEPENDENT"
        )
        unknown_pairs = sum(
            1 for relation in relations.values() if relation == "UNKNOWN"
        )
        if not relations:
            independence_status = "SINGLE_PATH"
        elif unknown_pairs:
            independence_status = "UNRESOLVED"
        elif independent_pairs == len(relations):
            independence_status = "INDEPENDENT"
        elif dependent_pairs == len(relations):
            independence_status = "DEPENDENT"
        else:
            independence_status = "MIXED"

        groups = self._conservative_groups(tuple(sorted(ids)), relations)
        stance_values = tuple(path.stance for path in normalized_paths)
        unanimous = len(set(stance_values)) == 1
        agreement_without_independence = (
            unanimous and len(groups) < len(normalized_paths)
        )

        assessment_payload = {
            "schema_version": INDEPENDENCE_POLICY_SCHEMA_VERSION,
            "claim_id": claim_id,
            "paths": [path.to_dict() for path in sorted(normalized_paths, key=lambda p: p.path_id)],
            "pairwise": pairwise,
            "independence_status": independence_status,
            "independent_pair_count": independent_pairs,
            "dependent_pair_count": dependent_pairs,
            "unknown_pair_count": unknown_pairs,
            "demonstrated_independent_group_count": len(groups),
            "groups": [list(group) for group in groups],
            "agreement_without_independence": agreement_without_independence,
        }
        assessment_sha = _sha256(assessment_payload)
        status = (
            MandalaStatus.DEGRADED
            if independence_status == "UNRESOLVED"
            else MandalaStatus.ACCEPTED
        )
        independence = IndependenceReceipt(
            **receipt_meta(
                packet,
                status=status,
                produced_by="phios.deliberation_evidence",
            ),
            claim_id=claim_id,
            evidence_paths=tuple(
                path.to_dict()
                for path in sorted(normalized_paths, key=lambda p: p.path_id)
            ),
            pairwise_relations=tuple(pairwise),
            independence_status=independence_status,
            independent_pair_count=independent_pairs,
            dependent_pair_count=dependent_pairs,
            unknown_pair_count=unknown_pairs,
            demonstrated_independent_group_count=len(groups),
            dependency_groups=groups,
            agreement_without_independence=agreement_without_independence,
            assessment_sha256=assessment_sha,
        )
        independence = self._with_receipt_sha(independence)

        disagreement = self._disagreement_receipt(
            packet=packet,
            claim_id=claim_id,
            paths=normalized_paths,
            groups=groups,
            independence=independence,
        )

        if self.ledger is not None:
            self.ledger.append(independence)
            self.ledger.append(disagreement)
        return DeliberationEvidenceResult(
            independence_receipt=independence,
            disagreement_receipt=disagreement,
        )

    @staticmethod
    def _forced_dependency_reasons(
        left: EvidencePathDeclaration,
        right: EvidencePathDeclaration,
    ) -> tuple[str, ...]:
        reasons: list[str] = []
        if left.actor_id == right.actor_id:
            reasons.append("same_actor")
        if set(left.evidence_refs).intersection(right.evidence_refs):
            reasons.append("shared_evidence_ref")
        if set(left.root_source_refs).intersection(right.root_source_refs):
            reasons.append("shared_root_source")
        if set(left.transformation_lineage_sha256s).intersection(
            right.transformation_lineage_sha256s
        ):
            reasons.append("shared_transformation_lineage")
        if left.path_id in right.parent_path_ids or right.path_id in left.parent_path_ids:
            reasons.append("direct_path_derivation")
        return tuple(reasons)

    @staticmethod
    def _conservative_groups(
        path_ids: tuple[str, ...],
        relations: Mapping[tuple[str, str], str],
    ) -> tuple[tuple[str, ...], ...]:
        parent = {path_id: path_id for path_id in path_ids}

        def find(item: str) -> str:
            while parent[item] != item:
                parent[item] = parent[parent[item]]
                item = parent[item]
            return item

        def union(left: str, right: str) -> None:
            lroot, rroot = find(left), find(right)
            if lroot != rroot:
                parent[max(lroot, rroot)] = min(lroot, rroot)

        # UNKNOWN does not earn independence credit, so it collapses conservatively.
        for (left, right), relation in relations.items():
            if relation != "INDEPENDENT":
                union(left, right)

        grouped: dict[str, list[str]] = {}
        for path_id in path_ids:
            grouped.setdefault(find(path_id), []).append(path_id)
        return tuple(
            tuple(sorted(values))
            for _, values in sorted(grouped.items())
        )

    def _disagreement_receipt(
        self,
        *,
        packet: MandalaPacket,
        claim_id: str,
        paths: tuple[EvidencePathDeclaration, ...],
        groups: tuple[tuple[str, ...], ...],
        independence: IndependenceReceipt,
    ) -> DisagreementDecompositionReceipt:
        path_map = {path.path_id: path for path in paths}
        stance_counts = {
            stance: sum(1 for path in paths if path.stance == stance)
            for stance in _ALLOWED_STANCES
        }
        group_records: list[dict[str, object]] = []
        independent_stance_group_counts = {stance: 0 for stance in _ALLOWED_STANCES}
        contested_group_count = 0
        for index, group in enumerate(groups):
            stances = tuple(sorted({path_map[path_id].stance for path_id in group}))
            if len(stances) == 1:
                independent_stance_group_counts[stances[0]] += 1
            else:
                contested_group_count += 1
            group_records.append(
                {
                    "group_id": f"group-{index + 1}",
                    "path_ids": list(group),
                    "stances": list(stances),
                }
            )

        nonzero_stances = tuple(
            stance for stance, count in stance_counts.items() if count > 0
        )
        if len(paths) == 1:
            disagreement_status = "SINGLE_PATH"
        elif len(nonzero_stances) == 1:
            disagreement_status = "UNANIMOUS_PARTICIPANTS"
        else:
            disagreement_status = "DISAGREEMENT"

        independence_qualified_agreement = (
            disagreement_status == "UNANIMOUS_PARTICIPANTS"
            and independence.independence_status == "INDEPENDENT"
        )
        payload = {
            "schema_version": "phios.disagreement_decomposition.v0.1",
            "claim_id": claim_id,
            "independence_assessment_sha256": independence.assessment_sha256,
            "stance_counts": stance_counts,
            "independent_stance_group_counts": independent_stance_group_counts,
            "contested_group_count": contested_group_count,
            "groups": group_records,
            "disagreement_status": disagreement_status,
            "independence_qualified_agreement": independence_qualified_agreement,
            "consensus_authority": False,
            "promotion_status": "not_promoted",
        }
        receipt = DisagreementDecompositionReceipt(
            **receipt_meta(
                packet,
                status=independence.status,
                produced_by="phios.deliberation_evidence",
                parent_receipt_id=independence.receipt_id,
            ),
            claim_id=claim_id,
            independence_receipt_sha256=independence.receipt_sha256,
            stance_counts=stance_counts,
            independent_stance_group_counts=independent_stance_group_counts,
            contested_group_count=contested_group_count,
            dependency_groups=tuple(group_records),
            disagreement_status=disagreement_status,
            independence_qualified_agreement=independence_qualified_agreement,
            consensus_authority=False,
            promotion_status="not_promoted",
            assessment_sha256=_sha256(payload),
        )
        return self._with_receipt_sha(receipt)

    @staticmethod
    def _with_receipt_sha(receipt):
        data = receipt.to_dict()
        data["receipt_sha256"] = ""
        return replace(receipt, receipt_sha256=_sha256(data))
