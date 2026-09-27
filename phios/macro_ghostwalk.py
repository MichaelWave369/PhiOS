"""Ghost-walk demonstration recorder and zero-authority draft compiler.

v0.13 records demonstrated clicks as immutable observations, preserving both an
optional semantic target and the v0.12 guarded window-relative PixelAnchor.
Compilation proposes a MacroDefinition but never grants execution authority.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Mapping

from phios.macro_graph import DoStep, MacroDefinition, MacroGraphPlanner
from phios.macro_interaction_guard import PixelAnchor, WindowFrame
from phios.macro_runtime import (
    ExecutionMode,
    IdempotencyClass,
    Operation,
    ReplayClass,
    RollbackClass,
    SideEffectClass,
)
from phios.spine.ledger import RealityLedger

GHOSTWALK_SESSION_SCHEMA_VERSION = "phios.ghostwalk_session.v0.13"
GHOSTWALK_OBSERVATION_SCHEMA_VERSION = "phios.ghostwalk_observation.v0.13"
GHOSTWALK_SEMANTIC_TARGET_SCHEMA_VERSION = (
    "phios.ghostwalk_semantic_target.v0.13"
)
GHOSTWALK_DRAFT_RECEIPT_SCHEMA_VERSION = "phios.ghostwalk_draft_receipt.v0.13"
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class GhostWalkContractError(ValueError):
    """Raised when a demonstration or compiled draft cannot be trusted."""


class GhostWalkActionKind(StrEnum):
    CLICK = "CLICK"


class TargetStrategy(StrEnum):
    SEMANTIC = "SEMANTIC"
    WINDOW_RELATIVE_PIXEL = "WINDOW_RELATIVE_PIXEL"


def _require_text(
    value: object,
    field: str,
    *,
    maximum: int = 4096,
) -> str:
    if not isinstance(value, str) or not value:
        raise GhostWalkContractError(
            f"{field} must be a non-empty string"
        )
    if len(value) > maximum:
        raise GhostWalkContractError(
            f"{field} exceeds {maximum} characters"
        )
    if any(ord(char) < 32 for char in value):
        raise GhostWalkContractError(
            f"{field} contains control characters"
        )
    return value


def _require_sha256(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    if not _SHA256_RE.fullmatch(text):
        raise GhostWalkContractError(
            f"{field} must be a lowercase SHA-256 digest"
        )
    return text


def _require_timestamp(value: object, field: str) -> str:
    text = _require_text(value, field, maximum=64)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise GhostWalkContractError(
            f"{field} must be an ISO-8601 timestamp"
        ) from exc
    if parsed.tzinfo is None:
        raise GhostWalkContractError(
            f"{field} must include a timezone"
        )
    return text


def _require_int(
    value: object,
    field: str,
    *,
    minimum: int | None = 0,
) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GhostWalkContractError(
            f"{field} must be an integer"
        )
    if minimum is not None and value < minimum:
        raise GhostWalkContractError(
            f"{field} must be at least {minimum}"
        )
    return value


def _require_bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise GhostWalkContractError(
            f"{field} must be Boolean"
        )
    return value


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
        raise GhostWalkContractError(
            "ghost-walk payload must be canonical JSON"
        ) from exc


def _canonical_sha256(value: object) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class SemanticTarget:
    """Optional semantic UI identity observed during a demonstration."""

    provider: str
    selector: str
    role: str | None = None
    name_hint: str | None = None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_SEMANTIC_TARGET_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_SEMANTIC_TARGET_SCHEMA_VERSION:
            raise GhostWalkContractError(
                "unsupported semantic target schema"
            )
        _require_text(self.provider, "provider", maximum=256)
        _require_text(self.selector, "selector")
        if self.role is not None:
            _require_text(self.role, "role", maximum=256)
        if self.name_hint is not None:
            _require_text(self.name_hint, "name_hint", maximum=1024)
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkContractError(
                "SemanticTarget cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "provider": self.provider,
            "selector": self.selector,
            "role": self.role,
            "name_hint": self.name_hint,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def target_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["target_sha256"] = self.target_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "SemanticTarget":
        claimed = _require_sha256(
            payload.get("target_sha256"),
            "target_sha256",
        )
        role_raw = payload.get("role")
        name_raw = payload.get("name_hint")
        target = cls(
            provider=_require_text(
                payload.get("provider"),
                "provider",
                maximum=256,
            ),
            selector=_require_text(payload.get("selector"), "selector"),
            role=(
                None
                if role_raw is None
                else _require_text(role_raw, "role", maximum=256)
            ),
            name_hint=(
                None
                if name_raw is None
                else _require_text(
                    name_raw,
                    "name_hint",
                    maximum=1024,
                )
            ),
            operational_authority=_require_bool(
                payload.get("operational_authority"),
                "operational_authority",
            ),
            action_authority=_require_bool(
                payload.get("action_authority"),
                "action_authority",
            ),
            execution_authority=_require_bool(
                payload.get("execution_authority"),
                "execution_authority",
            ),
            schema_version=_require_text(
                payload.get("schema_version"),
                "schema_version",
            ),
        )
        if target.target_sha256 != claimed:
            raise GhostWalkContractError(
                "semantic target hash mismatch"
            )
        return target


@dataclass(frozen=True, slots=True)
class GhostWalkSession:
    session_id: str
    recorder_id: str
    started_at: str
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_SESSION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_SESSION_SCHEMA_VERSION:
            raise GhostWalkContractError(
                "unsupported ghost-walk session schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_text(self.recorder_id, "recorder_id", maximum=512)
        _require_timestamp(self.started_at, "started_at")
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkContractError(
                "GhostWalkSession cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "recorder_id": self.recorder_id,
            "started_at": self.started_at,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def session_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["session_sha256"] = self.session_sha256
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkSession":
        claimed = _require_sha256(
            payload.get("session_sha256"),
            "session_sha256",
        )
        session = cls(
            session_id=_require_text(
                payload.get("session_id"),
                "session_id",
                maximum=512,
            ),
            recorder_id=_require_text(
                payload.get("recorder_id"),
                "recorder_id",
                maximum=512,
            ),
            started_at=_require_timestamp(
                payload.get("started_at"),
                "started_at",
            ),
            operational_authority=_require_bool(
                payload.get("operational_authority"),
                "operational_authority",
            ),
            action_authority=_require_bool(
                payload.get("action_authority"),
                "action_authority",
            ),
            execution_authority=_require_bool(
                payload.get("execution_authority"),
                "execution_authority",
            ),
            schema_version=_require_text(
                payload.get("schema_version"),
                "schema_version",
            ),
        )
        if session.session_sha256 != claimed:
            raise GhostWalkContractError(
                "ghost-walk session hash mismatch"
            )
        return session


def _pixel_anchor_dict(anchor: PixelAnchor) -> dict[str, object]:
    payload = anchor.body_dict()
    payload["anchor_sha256"] = anchor.anchor_sha256
    return payload


def _pixel_anchor_from_dict(
    payload: Mapping[str, object],
) -> PixelAnchor:
    claimed = _require_sha256(
        payload.get("anchor_sha256"),
        "pixel anchor_sha256",
    )
    hint_raw = payload.get("semantic_hint")
    anchor = PixelAnchor(
        anchor_id=_require_text(
            payload.get("anchor_id"),
            "anchor_id",
            maximum=512,
        ),
        source_frame_sha256=_require_sha256(
            payload.get("source_frame_sha256"),
            "source_frame_sha256",
        ),
        process_id=_require_text(
            payload.get("process_id"),
            "process_id",
            maximum=512,
        ),
        window_title_sha256=_require_sha256(
            payload.get("window_title_sha256"),
            "window_title_sha256",
        ),
        x_ppm=_require_int(payload.get("x_ppm"), "x_ppm"),
        y_ppm=_require_int(payload.get("y_ppm"), "y_ppm"),
        observed_x_px=_require_int(
            payload.get("observed_x_px"),
            "observed_x_px",
            minimum=None,
        ),
        observed_y_px=_require_int(
            payload.get("observed_y_px"),
            "observed_y_px",
            minimum=None,
        ),
        semantic_hint=(
            None
            if hint_raw is None
            else _require_text(
                hint_raw,
                "semantic_hint",
                maximum=1024,
            )
        ),
        operational_authority=_require_bool(
            payload.get("operational_authority"),
            "operational_authority",
        ),
        action_authority=_require_bool(
            payload.get("action_authority"),
            "action_authority",
        ),
        execution_authority=_require_bool(
            payload.get("execution_authority"),
            "execution_authority",
        ),
        schema_version=_require_text(
            payload.get("schema_version"),
            "schema_version",
        ),
    )
    if anchor.anchor_sha256 != claimed:
        raise GhostWalkContractError(
            "pixel anchor hash mismatch"
        )
    return anchor


@dataclass(frozen=True, slots=True)
class GhostWalkObservation:
    session_id: str
    session_sha256: str
    sequence: int
    action_kind: GhostWalkActionKind
    observed_at: str
    frame_sha256: str
    pixel_anchor: PixelAnchor
    semantic_target: SemanticTarget | None
    previous_observation_sha256: str | None
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_OBSERVATION_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_OBSERVATION_SCHEMA_VERSION:
            raise GhostWalkContractError(
                "unsupported ghost-walk observation schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(self.session_sha256, "session_sha256")
        _require_int(self.sequence, "sequence")
        _require_timestamp(self.observed_at, "observed_at")
        _require_sha256(self.frame_sha256, "frame_sha256")
        if self.pixel_anchor.source_frame_sha256 != self.frame_sha256:
            raise GhostWalkContractError(
                "pixel anchor source frame does not match observation frame"
            )
        if self.sequence == 0:
            if self.previous_observation_sha256 is not None:
                raise GhostWalkContractError(
                    "first observation cannot reference prior observation"
                )
        else:
            if self.previous_observation_sha256 is None:
                raise GhostWalkContractError(
                    "later observation requires prior observation hash"
                )
            _require_sha256(
                self.previous_observation_sha256,
                "previous_observation_sha256",
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkContractError(
                "GhostWalkObservation cannot carry authority"
            )

    @property
    def preferred_strategy(self) -> TargetStrategy:
        if self.semantic_target is not None:
            return TargetStrategy.SEMANTIC
        return TargetStrategy.WINDOW_RELATIVE_PIXEL

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "session_sha256": self.session_sha256,
            "sequence": self.sequence,
            "action_kind": self.action_kind.value,
            "observed_at": self.observed_at,
            "frame_sha256": self.frame_sha256,
            "pixel_anchor": _pixel_anchor_dict(self.pixel_anchor),
            "semantic_target": (
                None
                if self.semantic_target is None
                else self.semantic_target.to_dict()
            ),
            "previous_observation_sha256": (
                self.previous_observation_sha256
            ),
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def observation_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["observation_sha256"] = self.observation_sha256
        payload["preferred_strategy"] = self.preferred_strategy.value
        return payload

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, object],
    ) -> "GhostWalkObservation":
        claimed = _require_sha256(
            payload.get("observation_sha256"),
            "observation_sha256",
        )
        anchor_raw = payload.get("pixel_anchor")
        if not isinstance(anchor_raw, dict):
            raise GhostWalkContractError(
                "pixel_anchor must be an object"
            )
        semantic_raw = payload.get("semantic_target")
        if semantic_raw is not None and not isinstance(semantic_raw, dict):
            raise GhostWalkContractError(
                "semantic_target must be object or null"
            )
        try:
            action_kind = GhostWalkActionKind(
                _require_text(
                    payload.get("action_kind"),
                    "action_kind",
                    maximum=64,
                )
            )
        except ValueError as exc:
            raise GhostWalkContractError(
                "unsupported ghost-walk action kind"
            ) from exc
        previous_raw = payload.get("previous_observation_sha256")
        observation = cls(
            session_id=_require_text(
                payload.get("session_id"),
                "session_id",
                maximum=512,
            ),
            session_sha256=_require_sha256(
                payload.get("session_sha256"),
                "session_sha256",
            ),
            sequence=_require_int(
                payload.get("sequence"),
                "sequence",
            ),
            action_kind=action_kind,
            observed_at=_require_timestamp(
                payload.get("observed_at"),
                "observed_at",
            ),
            frame_sha256=_require_sha256(
                payload.get("frame_sha256"),
                "frame_sha256",
            ),
            pixel_anchor=_pixel_anchor_from_dict(anchor_raw),
            semantic_target=(
                None
                if semantic_raw is None
                else SemanticTarget.from_dict(semantic_raw)
            ),
            previous_observation_sha256=(
                None
                if previous_raw is None
                else _require_sha256(
                    previous_raw,
                    "previous_observation_sha256",
                )
            ),
            operational_authority=_require_bool(
                payload.get("operational_authority"),
                "operational_authority",
            ),
            action_authority=_require_bool(
                payload.get("action_authority"),
                "action_authority",
            ),
            execution_authority=_require_bool(
                payload.get("execution_authority"),
                "execution_authority",
            ),
            schema_version=_require_text(
                payload.get("schema_version"),
                "schema_version",
            ),
        )
        if observation.observation_sha256 != claimed:
            raise GhostWalkContractError(
                "ghost-walk observation hash mismatch"
            )
        preferred_raw = payload.get("preferred_strategy")
        if preferred_raw is not None and preferred_raw != (
            observation.preferred_strategy.value
        ):
            raise GhostWalkContractError(
                "stored preferred strategy does not match observation"
            )
        return observation


@dataclass(frozen=True, slots=True)
class GhostWalkDraftReceipt:
    session_id: str
    session_sha256: str
    observation_count: int
    observation_head_sha256: str
    macro_id: str
    macro_version: str
    definition_sha256: str
    operation_hashes: tuple[str, ...]
    semantic_preferred_count: int
    pixel_fallback_count: int
    operational_authority: bool = False
    action_authority: bool = False
    execution_authority: bool = False
    schema_version: str = GHOSTWALK_DRAFT_RECEIPT_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.schema_version != GHOSTWALK_DRAFT_RECEIPT_SCHEMA_VERSION:
            raise GhostWalkContractError(
                "unsupported ghost-walk draft receipt schema"
            )
        _require_text(self.session_id, "session_id", maximum=512)
        _require_sha256(self.session_sha256, "session_sha256")
        _require_int(self.observation_count, "observation_count", minimum=1)
        _require_sha256(
            self.observation_head_sha256,
            "observation_head_sha256",
        )
        _require_text(self.macro_id, "macro_id", maximum=256)
        _require_text(self.macro_version, "macro_version", maximum=128)
        _require_sha256(self.definition_sha256, "definition_sha256")
        if len(self.operation_hashes) != self.observation_count:
            raise GhostWalkContractError(
                "operation hash count must equal observation count"
            )
        for item in self.operation_hashes:
            _require_sha256(item, "operation_hash")
        _require_int(
            self.semantic_preferred_count,
            "semantic_preferred_count",
        )
        _require_int(
            self.pixel_fallback_count,
            "pixel_fallback_count",
        )
        if (
            self.semantic_preferred_count
            + self.pixel_fallback_count
            != self.observation_count
        ):
            raise GhostWalkContractError(
                "target strategy counts must equal observation count"
            )
        if (
            self.operational_authority
            or self.action_authority
            or self.execution_authority
        ):
            raise GhostWalkContractError(
                "GhostWalkDraftReceipt cannot carry authority"
            )

    def body_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "session_id": self.session_id,
            "session_sha256": self.session_sha256,
            "observation_count": self.observation_count,
            "observation_head_sha256": (
                self.observation_head_sha256
            ),
            "macro_id": self.macro_id,
            "macro_version": self.macro_version,
            "definition_sha256": self.definition_sha256,
            "operation_hashes": list(self.operation_hashes),
            "semantic_preferred_count": self.semantic_preferred_count,
            "pixel_fallback_count": self.pixel_fallback_count,
            "operational_authority": self.operational_authority,
            "action_authority": self.action_authority,
            "execution_authority": self.execution_authority,
        }

    @property
    def receipt_sha256(self) -> str:
        return _canonical_sha256(self.body_dict())

    def to_dict(self) -> dict[str, object]:
        payload = self.body_dict()
        payload["receipt_sha256"] = self.receipt_sha256
        return payload


@dataclass(frozen=True, slots=True)
class GhostWalkDraft:
    definition: MacroDefinition
    receipt: GhostWalkDraftReceipt


class GhostWalkRecorder:
    """Persist immutable demonstration observations and compile draft macros."""

    def __init__(self, ledger: RealityLedger) -> None:
        if not isinstance(ledger, RealityLedger):
            raise GhostWalkContractError(
                "ledger must be a RealityLedger"
            )
        self._ledger = ledger

    def start(
        self,
        *,
        session_id: str,
        recorder_id: str,
        started_at: str,
    ) -> GhostWalkSession:
        if self._ledger.ghostwalk_sessions(session_id=session_id):
            raise GhostWalkContractError(
                "ghost-walk session_id already exists"
            )
        session = GhostWalkSession(
            session_id=session_id,
            recorder_id=recorder_id,
            started_at=started_at,
        )
        self._ledger.append_ghostwalk_session(session)
        return session

    def record_click(
        self,
        *,
        session_id: str,
        frame: WindowFrame,
        x_px: int,
        y_px: int,
        observed_at: str,
        semantic_target: SemanticTarget | None = None,
        semantic_hint: str | None = None,
    ) -> GhostWalkObservation:
        session = self._load_session(session_id)
        observations = self._load_observations(
            session=session,
        )
        sequence = len(observations)
        previous = (
            observations[-1].observation_sha256
            if observations
            else None
        )
        anchor = PixelAnchor.from_observed_click(
            anchor_id=f"{session_id}:click:{sequence}",
            frame=frame,
            x_px=x_px,
            y_px=y_px,
            semantic_hint=semantic_hint,
        )
        observation = GhostWalkObservation(
            session_id=session.session_id,
            session_sha256=session.session_sha256,
            sequence=sequence,
            action_kind=GhostWalkActionKind.CLICK,
            observed_at=observed_at,
            frame_sha256=frame.frame_sha256,
            pixel_anchor=anchor,
            semantic_target=semantic_target,
            previous_observation_sha256=previous,
        )
        self._ledger.append_ghostwalk_observation(observation)
        return observation

    def observations(
        self,
        *,
        session_id: str,
    ) -> tuple[GhostWalkObservation, ...]:
        session = self._load_session(session_id)
        return tuple(self._load_observations(session=session))

    def compile_draft(
        self,
        *,
        session_id: str,
        macro_id: str,
        macro_version: str,
    ) -> GhostWalkDraft:
        session = self._load_session(session_id)
        observations = self._load_observations(session=session)
        if not observations:
            raise GhostWalkContractError(
                "ghost-walk session requires at least one observation"
            )

        steps: list[DoStep] = []
        operation_hashes: list[str] = []
        semantic_count = 0
        pixel_count = 0

        for observation in observations:
            target = observation.semantic_target
            if target is not None:
                strategy = TargetStrategy.SEMANTIC
                semantic_count += 1
            else:
                strategy = TargetStrategy.WINDOW_RELATIVE_PIXEL
                pixel_count += 1

            inputs: dict[str, object] = {
                "observation_sha256": observation.observation_sha256,
                "preferred_strategy": strategy.value,
                "process_id": observation.pixel_anchor.process_id,
                "window_title_sha256": (
                    observation.pixel_anchor.window_title_sha256
                ),
                "pixel_anchor": _pixel_anchor_dict(
                    observation.pixel_anchor
                ),
                "semantic_target": (
                    None if target is None else target.to_dict()
                ),
                "absolute_pixel_is_evidence_only": True,
                "guard_required": True,
            }
            operation = Operation(
                operation_id=(
                    f"ghostwalk.click.{observation.sequence}"
                ),
                operation_version="0.13.0",
                adapter_id="desktop.interaction",
                action="click",
                inputs=inputs,
                required_capabilities=("ui.interact",),
                execution_modes_supported=(ExecutionMode.LIVE,),
                idempotency_class=IdempotencyClass.UNKNOWN,
                replay_class=ReplayClass.NON_REPLAYABLE,
                rollback_class=RollbackClass.NONE,
                side_effect_class=SideEffectClass.UNKNOWN,
            )
            operation_hashes.append(operation.operation_hash)
            steps.append(DoStep(operation))

        definition = MacroDefinition(
            macro_id=macro_id,
            macro_version=macro_version,
            steps=tuple(steps),
        )
        MacroGraphPlanner().validate(definition)
        receipt = GhostWalkDraftReceipt(
            session_id=session.session_id,
            session_sha256=session.session_sha256,
            observation_count=len(observations),
            observation_head_sha256=(
                observations[-1].observation_sha256
            ),
            macro_id=definition.macro_id,
            macro_version=definition.macro_version,
            definition_sha256=definition.definition_sha256,
            operation_hashes=tuple(operation_hashes),
            semantic_preferred_count=semantic_count,
            pixel_fallback_count=pixel_count,
        )
        self._ledger.append_ghostwalk_draft_receipt(receipt)
        return GhostWalkDraft(
            definition=definition,
            receipt=receipt,
        )

    def _load_session(self, session_id: str) -> GhostWalkSession:
        rows = self._ledger.ghostwalk_sessions(session_id=session_id)
        if len(rows) != 1:
            if not rows:
                raise GhostWalkContractError(
                    "ghost-walk session does not exist"
                )
            raise GhostWalkContractError(
                "ghost-walk session identity is not unique"
            )
        return GhostWalkSession.from_dict(rows[0])

    def _load_observations(
        self,
        *,
        session: GhostWalkSession,
    ) -> list[GhostWalkObservation]:
        rows = self._ledger.ghostwalk_observations(
            session_id=session.session_id
        )
        observations = [
            GhostWalkObservation.from_dict(row)
            for row in rows
        ]
        previous: GhostWalkObservation | None = None
        for expected_sequence, item in enumerate(observations):
            if item.session_id != session.session_id:
                raise GhostWalkContractError(
                    "ghost-walk session identity changed in observation chain"
                )
            if item.session_sha256 != session.session_sha256:
                raise GhostWalkContractError(
                    "ghost-walk observation session hash mismatch"
                )
            if item.sequence != expected_sequence:
                raise GhostWalkContractError(
                    "ghost-walk observation sequence is not contiguous"
                )
            expected_previous = (
                None
                if previous is None
                else previous.observation_sha256
            )
            if item.previous_observation_sha256 != expected_previous:
                raise GhostWalkContractError(
                    "ghost-walk observation hash chain mismatch"
                )
            previous = item
        return observations
