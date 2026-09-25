"""Append-only local storage for the PhiOS Curiosity Lane.

The store preserves curiosity artifacts, lineage, deterministic lookup, related
seed discovery, and return pointers. It does not grant factual, operational,
action, or execution authority.

Persistence is intentionally separate from governed execution. A caller that
writes to a CuriosityStore is responsible for obtaining any permissions
required by its hosting runtime.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from phios.curiosity import CuriosityArtifact

CURIOSITY_RETURN_POINTER_SCHEMA_VERSION = (
    "phios.curiosity_return_pointer.v0.2"
)
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_WORD_RE = re.compile(r"[a-z0-9]+(?:[_-][a-z0-9]+)*")


class CuriosityStoreError(ValueError):
    """Raised when persisted curiosity state violates the store contract."""


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CuriosityStoreError(f"{field} must be a non-empty string")
    if len(value) > maximum:
        raise CuriosityStoreError(f"{field} exceeds {maximum} characters")
    if any(ord(char) < 32 and char not in "\n\t" for char in value):
        raise CuriosityStoreError(
            f"{field} contains unsupported control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise CuriosityStoreError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CuriosityStoreError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise CuriosityStoreError(
            f"{field} must include a timezone offset"
        )
    return text


def _canonical_json(value: Mapping[str, Any]) -> str:
    try:
        return json.dumps(
            dict(value),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise CuriosityStoreError(
            "curiosity store payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        _canonical_json(value).encode("utf-8")
    ).hexdigest()


def _canonical_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(
        sorted({tag.strip().lower() for tag in tags if tag.strip()})
    )
    if len(normalized) > 64:
        raise CuriosityStoreError("tags exceeds 64 items")
    for tag in normalized:
        _require_text(tag, "tag", maximum=128)
    return normalized


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _tokens(value: str) -> set[str]:
    return set(_WORD_RE.findall(value.lower()))


@dataclass(frozen=True, slots=True)
class CuriosityReturnPointer:
    """Immutable marker describing where a curiosity thread should resume."""

    artifact_sha256: str
    created_at: str
    created_by: str
    return_prompt: str
    context: str = ""
    tags: tuple[str, ...] = ()
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = CURIOSITY_RETURN_POINTER_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if (
            self.schema_version
            != CURIOSITY_RETURN_POINTER_SCHEMA_VERSION
        ):
            raise CuriosityStoreError(
                "unsupported CuriosityReturnPointer schema"
            )
        _require_sha256(self.artifact_sha256, "artifact_sha256")
        _require_timestamp(self.created_at, "created_at")
        _require_text(
            self.created_by,
            "created_by",
            maximum=256,
        )
        _require_text(
            self.return_prompt,
            "return_prompt",
            maximum=4096,
        )
        if self.context:
            _require_text(self.context, "context", maximum=16384)
        if _canonical_tags(self.tags) != self.tags:
            raise CuriosityStoreError(
                "tags must be sorted, unique, and lowercase"
            )
        if self.effect_performed is not False:
            raise CuriosityStoreError(
                "CuriosityReturnPointer cannot claim an effect"
            )
        if (
            self.operational_authority is not False
            or self.action_authority is not False
            or self.execution_authority is not False
        ):
            raise CuriosityStoreError(
                "CuriosityReturnPointer cannot carry operational, "
                "action, or execution authority"
            )

    def body_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "artifact_sha256": self.artifact_sha256,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "return_prompt": self.return_prompt,
            "context": self.context,
            "tags": list(self.tags),
            "effect_performed": self.effect_performed,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def return_pointer_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, Any]:
        payload = self.body_dict()
        payload["return_pointer_sha256"] = (
            self.return_pointer_sha256
        )
        return payload

    @classmethod
    def build(
        cls,
        *,
        artifact_sha256: str,
        created_at: str,
        created_by: str,
        return_prompt: str,
        context: str = "",
        tags: tuple[str, ...] = (),
    ) -> "CuriosityReturnPointer":
        return cls(
            artifact_sha256=artifact_sha256,
            created_at=created_at,
            created_by=created_by,
            return_prompt=return_prompt,
            context=context,
            tags=_canonical_tags(tags),
        )

    @classmethod
    def from_dict(
        cls,
        value: object,
    ) -> "CuriosityReturnPointer":
        if not isinstance(value, dict):
            raise CuriosityStoreError(
                "CuriosityReturnPointer must be an object"
            )
        data = dict(value)
        expected = {
            "schema_version",
            "artifact_sha256",
            "created_at",
            "created_by",
            "return_prompt",
            "context",
            "tags",
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
            "return_pointer_sha256",
        }
        if set(data) != expected:
            missing = sorted(expected - set(data))
            unknown = sorted(set(data) - expected)
            raise CuriosityStoreError(
                "CuriosityReturnPointer fields mismatch: "
                f"missing={missing}; unknown={unknown}"
            )

        tags = data["tags"]
        if not isinstance(tags, list):
            raise CuriosityStoreError("tags must be an array")

        for field in (
            "effect_performed",
            "operational_authority",
            "action_authority",
            "execution_authority",
        ):
            if not isinstance(data[field], bool):
                raise CuriosityStoreError(
                    f"{field} must be Boolean"
                )

        pointer = cls(
            schema_version=_require_text(
                data["schema_version"],
                "schema_version",
                maximum=64,
            ),
            artifact_sha256=_require_sha256(
                data["artifact_sha256"],
                "artifact_sha256",
            ),
            created_at=_require_timestamp(
                data["created_at"],
                "created_at",
            ),
            created_by=_require_text(
                data["created_by"],
                "created_by",
                maximum=256,
            ),
            return_prompt=_require_text(
                data["return_prompt"],
                "return_prompt",
                maximum=4096,
            ),
            context=(
                ""
                if data["context"] == ""
                else _require_text(
                    data["context"],
                    "context",
                    maximum=16384,
                )
            ),
            tags=tuple(tags),
            effect_performed=data["effect_performed"],
            operational_authority=data["operational_authority"],
            action_authority=data["action_authority"],
            execution_authority=data["execution_authority"],
        )

        if (
            data["return_pointer_sha256"]
            != pointer.return_pointer_sha256
        ):
            raise CuriosityStoreError(
                "return_pointer_sha256 does not match canonical pointer"
            )
        return pointer


@dataclass(frozen=True, slots=True)
class CuriosityRelation:
    """Deterministic, zero-authority related-seed result."""

    artifact: CuriosityArtifact
    score: float
    reasons: tuple[str, ...]
    effect_performed: bool = False
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False


class CuriosityStore:
    """Append-only local store for curiosity artifacts and return pointers."""

    def __init__(self, root: Path) -> None:
        self.root = root.expanduser()
        self.artifacts_path = self.root / "artifacts.jsonl"
        self.return_pointers_path = self.root / "return-pointers.jsonl"

    @staticmethod
    def _append_json(path: Path, payload: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(_canonical_json(payload) + "\n")

    @staticmethod
    def _read_jsonl(path: Path) -> list[object]:
        if not path.exists():
            return []
        values: list[object] = []
        for index, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(),
            start=1,
        ):
            if not line.strip():
                raise CuriosityStoreError(
                    f"blank line in append-only store at line {index}"
                )
            try:
                values.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CuriosityStoreError(
                    f"invalid JSON at {path.name}:{index}"
                ) from exc
        return values

    def artifacts(self) -> list[CuriosityArtifact]:
        result: list[CuriosityArtifact] = []
        seen: set[str] = set()
        for raw in self._read_jsonl(self.artifacts_path):
            try:
                artifact = CuriosityArtifact.from_dict(raw)
            except ValueError as exc:
                raise CuriosityStoreError(
                    f"invalid curiosity artifact: {exc}"
                ) from exc
            digest = artifact.curiosity_artifact_sha256
            if digest in seen:
                raise CuriosityStoreError(
                    "duplicate curiosity artifact in append-only store"
                )
            seen.add(digest)
            result.append(artifact)
        return result

    def append_artifact(self, artifact: CuriosityArtifact) -> bool:
        """Append one artifact.

        Returns False when the exact immutable artifact is already present,
        making retry safe without rewriting history.
        """

        digest = artifact.curiosity_artifact_sha256
        if self.get_artifact(digest) is not None:
            return False
        self._append_json(self.artifacts_path, artifact.to_dict())
        return True

    def get_artifact(
        self,
        artifact_sha256: str,
    ) -> CuriosityArtifact | None:
        _require_sha256(artifact_sha256, "artifact_sha256")
        for artifact in self.artifacts():
            if (
                artifact.curiosity_artifact_sha256
                == artifact_sha256
            ):
                return artifact
        return None

    def children_of(
        self,
        artifact_sha256: str,
    ) -> list[CuriosityArtifact]:
        _require_sha256(artifact_sha256, "artifact_sha256")
        children = [
            artifact
            for artifact in self.artifacts()
            if artifact_sha256 in artifact.parent_artifact_sha256s
        ]
        return sorted(
            children,
            key=lambda item: (
                _parse_time(item.created_at),
                item.curiosity_artifact_sha256,
            ),
        )

    def lineage(
        self,
        artifact_sha256: str,
    ) -> list[CuriosityArtifact]:
        """Return locally known ancestors, oldest first, without guessing gaps."""

        artifact = self.get_artifact(artifact_sha256)
        if artifact is None:
            return []

        known = {
            item.curiosity_artifact_sha256: item
            for item in self.artifacts()
        }
        visited: set[str] = set()
        ordered: list[CuriosityArtifact] = []

        def visit(digest: str) -> None:
            if digest in visited:
                return
            visited.add(digest)
            item = known.get(digest)
            if item is None:
                return
            for parent in item.parent_artifact_sha256s:
                visit(parent)
            ordered.append(item)

        visit(artifact_sha256)
        return ordered

    def search(
        self,
        *,
        query: str = "",
        kinds: tuple[str, ...] = (),
        tags: tuple[str, ...] = (),
        limit: int = 20,
    ) -> list[CuriosityArtifact]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("search limit must be an integer")
        if limit < 0:
            raise ValueError("search limit must be non-negative")
        if limit == 0:
            return []

        normalized_kinds = {
            kind.strip().lower()
            for kind in kinds
            if kind.strip()
        }
        normalized_tags = {
            tag.strip().lower()
            for tag in tags
            if tag.strip()
        }
        query_tokens = _tokens(query)

        matches: list[CuriosityArtifact] = []
        for artifact in self.artifacts():
            if (
                normalized_kinds
                and artifact.artifact_kind not in normalized_kinds
            ):
                continue
            if (
                normalized_tags
                and not normalized_tags.issubset(set(artifact.tags))
            ):
                continue
            haystack = _tokens(
                " ".join(
                    (
                        artifact.title,
                        artifact.content,
                        " ".join(artifact.tags),
                    )
                )
            )
            if query_tokens and not query_tokens.issubset(haystack):
                continue
            matches.append(artifact)

        matches.sort(
            key=lambda item: (
                _parse_time(item.created_at),
                item.curiosity_artifact_sha256,
            ),
            reverse=True,
        )
        return matches[:limit]

    def related(
        self,
        artifact_sha256: str,
        *,
        limit: int = 10,
    ) -> list[CuriosityRelation]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("related limit must be an integer")
        if limit < 0:
            raise ValueError("related limit must be non-negative")
        if limit == 0:
            return []

        source = self.get_artifact(artifact_sha256)
        if source is None:
            return []

        source_tags = set(source.tags)
        source_tokens = _tokens(
            f"{source.title} {source.content}"
        )
        relations: list[CuriosityRelation] = []

        for candidate in self.artifacts():
            candidate_sha = candidate.curiosity_artifact_sha256
            if candidate_sha == artifact_sha256:
                continue

            score = 0.0
            reasons: list[str] = []

            shared_tags = sorted(source_tags.intersection(candidate.tags))
            if shared_tags:
                score += 2.0 * len(shared_tags)
                reasons.append(
                    "shared_tags:" + ",".join(shared_tags)
                )

            candidate_tokens = _tokens(
                f"{candidate.title} {candidate.content}"
            )
            union = source_tokens.union(candidate_tokens)
            overlap = source_tokens.intersection(candidate_tokens)
            lexical = (len(overlap) / len(union)) if union else 0.0
            if lexical > 0:
                score += lexical
                reasons.append(f"lexical_overlap:{lexical:.4f}")

            if candidate_sha in source.parent_artifact_sha256s:
                score += 4.0
                reasons.append("direct_parent")
            if artifact_sha256 in candidate.parent_artifact_sha256s:
                score += 4.0
                reasons.append("direct_child")

            if score <= 0:
                continue
            relations.append(
                CuriosityRelation(
                    artifact=candidate,
                    score=score,
                    reasons=tuple(reasons),
                )
            )

        relations.sort(
            key=lambda item: (
                item.score,
                _parse_time(item.artifact.created_at),
                item.artifact.curiosity_artifact_sha256,
            ),
            reverse=True,
        )
        return relations[:limit]

    def return_pointers(self) -> list[CuriosityReturnPointer]:
        result: list[CuriosityReturnPointer] = []
        seen: set[str] = set()
        for raw in self._read_jsonl(self.return_pointers_path):
            pointer = CuriosityReturnPointer.from_dict(raw)
            digest = pointer.return_pointer_sha256
            if digest in seen:
                raise CuriosityStoreError(
                    "duplicate return pointer in append-only store"
                )
            seen.add(digest)
            result.append(pointer)
        return result

    def append_return_pointer(
        self,
        pointer: CuriosityReturnPointer,
    ) -> bool:
        if self.get_artifact(pointer.artifact_sha256) is None:
            raise CuriosityStoreError(
                "return pointer target is not present in this store"
            )
        digest = pointer.return_pointer_sha256
        if any(
            item.return_pointer_sha256 == digest
            for item in self.return_pointers()
        ):
            return False
        self._append_json(
            self.return_pointers_path,
            pointer.to_dict(),
        )
        return True

    def latest_return_pointer(
        self,
        artifact_sha256: str,
    ) -> CuriosityReturnPointer | None:
        _require_sha256(artifact_sha256, "artifact_sha256")
        matches = [
            pointer
            for pointer in self.return_pointers()
            if pointer.artifact_sha256 == artifact_sha256
        ]
        if not matches:
            return None
        return max(
            matches,
            key=lambda item: (
                _parse_time(item.created_at),
                item.return_pointer_sha256,
            ),
        )

    def recent_return_pointers(
        self,
        *,
        limit: int = 10,
    ) -> list[CuriosityReturnPointer]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("return pointer limit must be an integer")
        if limit < 0:
            raise ValueError("return pointer limit must be non-negative")
        pointers = sorted(
            self.return_pointers(),
            key=lambda item: (
                _parse_time(item.created_at),
                item.return_pointer_sha256,
            ),
            reverse=True,
        )
        return pointers[:limit]
