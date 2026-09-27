from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

from .models import ExecutionReceipt

if TYPE_CHECKING:
    from phios.execution_outcome import ExecutionReconciliationReceipt
    from phios.macro_desktop_interaction import DesktopInteractionReceipt
    from phios.macro_baseline_refresh_service import BaselineRefreshReceipt
    from phios.macro_dispatcher import DoDispatchReceipt
    from phios.macro_ghostwalk import (
        GhostWalkDraftReceipt,
        GhostWalkObservation,
        GhostWalkSession,
    )
    from phios.macro_ghostwalk_capture import GhostWalkCaptureReceipt
    from phios.macro_ghostwalk_listener import GhostWalkListenerReceipt
    from phios.macro_ghostwalk_host_service import GhostWalkHostReceipt
    from phios.macro_ghostwalk_control_surface import GhostWalkControlReceipt
    from phios.macro_uia_revalidation import SemanticRevalidationReceipt
    from phios.macro_uia_state_observer import UiaStateObservationReceipt
    from phios.macro_windows_uia import (
        UiaElementSnapshot,
        UiaLookupReceipt,
    )
    from phios.macro_interaction_guard import InteractionGuardReceipt
    from phios.macro_journal import MacroRunJournalEntry, MacroRunResumeReceipt
    from phios.macro_operator_log import OperatorLogRevision
    from phios.macro_accepted_intent import GhostWalkAcceptedIntentRevision
    from phios.macro_policy_admission import GhostWalkPolicyAdmissionReceipt
    from phios.macro_authority_request import GhostWalkAuthorityRequest
    from phios.macro_post_action_verification import (
        PostActionVerificationReceipt,
    )
    from phios.macro_transition_inference import (
        GhostWalkUiStateSnapshot,
        TransitionInferenceReceipt,
    )
    from phios.macro_transition_coordinator import (
        TransitionCoordinatorReceipt,
    )
    from phios.macro_schedule_service import (
        ScheduleServicePollReceipt,
        ScheduleServiceStateEntry,
    )
    from phios.macro_schedule_worker import (
        ScheduleWorkerLease,
        ScheduleWorkerLeaseEvent,
        ScheduleWorkerTickReceipt,
    )
    from phios.macro_spine_bridge import MacroSpineReceipt
    from phios.macro_start import RunStartReceipt
    from phios.reality_reconciliation import RealityBoundReconciliationReceipt


class RealityLedger:
    """Append-only JSONL receipt ledger for the first PhiOS spine."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()

    def append(self, receipt: ExecutionReceipt) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent(self, limit: int = 10) -> list[dict[str, object]]:
        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("recent limit must be an integer")
        if limit < 0:
            raise ValueError("recent limit must be non-negative")
        if limit == 0 or not self.path.exists():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_macro_receipt(self, receipt: "MacroSpineReceipt") -> None:
        """Append one immutable macro-to-Spine execution receipt."""

        path = self.path.parent / "macro-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_macro_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest append-only macro execution receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("recent macro receipt limit must be an integer")
        if limit < 0:
            raise ValueError("recent macro receipt limit must be non-negative")
        path = self.path.parent / "macro-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_macro_dispatch_receipt(
        self,
        receipt: "DoDispatchReceipt",
    ) -> None:
        """Append one immutable governed DO dispatch receipt."""

        path = self.path.parent / "macro-dispatch-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_macro_dispatch_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest append-only governed DO dispatch receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent macro dispatch receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent macro dispatch receipt limit must be non-negative"
            )
        path = self.path.parent / "macro-dispatch-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_macro_run_journal_entry(
        self,
        entry: "MacroRunJournalEntry",
    ) -> None:
        """Append one immutable MacroRunState journal entry."""

        path = self.path.parent / "macro-run-journal.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def macro_run_journal_entries(
        self,
        *,
        run_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order MacroRun journal entries, optionally by run."""

        path = self.path.parent / "macro-run-journal.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if run_id is None:
            return rows
        return [row for row in rows if row.get("run_id") == run_id]

    def append_macro_run_resume_receipt(
        self,
        receipt: "MacroRunResumeReceipt",
    ) -> None:
        """Append evidence for one validated MacroRun reconstruction."""

        path = self.path.parent / "macro-run-resume-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_macro_run_resume_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest MacroRun resume receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent macro run resume receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent macro run resume receipt limit must be non-negative"
            )
        path = self.path.parent / "macro-run-resume-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_macro_run_start_receipt(
        self,
        receipt: "RunStartReceipt",
    ) -> None:
        """Append one immutable macro run-start admission receipt."""

        path = self.path.parent / "macro-run-start-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_macro_run_start_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest macro run-start admission receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent macro run start receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent macro run start receipt limit must be non-negative"
            )
        path = self.path.parent / "macro-run-start-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def claim_macro_start_dedupe(self, dedupe_sha256: str) -> bool:
        """Atomically reserve one trigger/macro admission identity."""

        self._validate_sha256(dedupe_sha256, "dedupe_sha256")
        claim_dir = self.path.parent / "macro-start-dedupe-claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim_path = claim_dir / f"{dedupe_sha256}.claim"
        try:
            fd = os.open(
                claim_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(dedupe_sha256 + "\n")
        return True

    def release_macro_start_dedupe_claim(self, dedupe_sha256: str) -> None:
        """Release a start dedupe claim when no run was admitted."""

        self._validate_sha256(dedupe_sha256, "dedupe_sha256")
        claim_path = (
            self.path.parent
            / "macro-start-dedupe-claims"
            / f"{dedupe_sha256}.claim"
        )
        claim_path.unlink(missing_ok=True)

    def claim_macro_run_id(self, run_id_sha256: str) -> bool:
        """Atomically reserve one requested macro run identity."""

        self._validate_sha256(run_id_sha256, "run_id_sha256")
        claim_dir = self.path.parent / "macro-run-id-claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim_path = claim_dir / f"{run_id_sha256}.claim"
        try:
            fd = os.open(
                claim_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(run_id_sha256 + "\n")
        return True

    def release_macro_run_id_claim(self, run_id_sha256: str) -> None:
        """Release a run-ID claim when coordination never created the run."""

        self._validate_sha256(run_id_sha256, "run_id_sha256")
        claim_path = (
            self.path.parent
            / "macro-run-id-claims"
            / f"{run_id_sha256}.claim"
        )
        claim_path.unlink(missing_ok=True)

    def append_schedule_service_state(
        self,
        entry: "ScheduleServiceStateEntry",
    ) -> None:
        """Append one immutable schedule-service cursor/state entry."""

        path = self.path.parent / "schedule-service-state.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry.to_dict(), sort_keys=True) + "\n")

    def schedule_service_state_entries(
        self,
        *,
        service_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order schedule-service state entries."""

        path = self.path.parent / "schedule-service-state.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if service_id is None:
            return rows
        return [row for row in rows if row.get("service_id") == service_id]

    def append_schedule_service_poll_receipt(
        self,
        receipt: "ScheduleServicePollReceipt",
    ) -> None:
        """Append one immutable schedule-service poll receipt."""

        path = self.path.parent / "schedule-service-poll-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_schedule_service_poll_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest schedule-service poll receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent schedule service poll receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent schedule service poll receipt limit must be non-negative"
            )
        path = self.path.parent / "schedule-service-poll-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_schedule_worker_lease(
        self,
        lease: "ScheduleWorkerLease",
    ) -> None:
        """Append one immutable schedule-worker lease snapshot."""

        path = self.path.parent / "schedule-worker-leases.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(lease.to_dict(), sort_keys=True) + "\n")

    def latest_schedule_worker_lease(
        self,
        *,
        service_id: str,
    ) -> dict[str, object] | None:
        """Return the latest persisted worker lease for one service."""

        path = self.path.parent / "schedule-worker-leases.jsonl"
        if not path.exists():
            return None
        latest: dict[str, object] | None = None
        for line in path.read_text(encoding="utf-8").splitlines():
            row = json.loads(line)
            if row.get("service_id") == service_id:
                latest = row
        return latest

    def append_schedule_worker_event(
        self,
        event: "ScheduleWorkerLeaseEvent",
    ) -> None:
        """Append one immutable worker ownership lifecycle event."""

        path = self.path.parent / "schedule-worker-events.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), sort_keys=True) + "\n")

    def schedule_worker_events(
        self,
        *,
        service_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order schedule-worker ownership events."""

        path = self.path.parent / "schedule-worker-events.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if service_id is None:
            return rows
        return [row for row in rows if row.get("service_id") == service_id]

    def append_schedule_worker_tick_receipt(
        self,
        receipt: "ScheduleWorkerTickReceipt",
    ) -> None:
        """Append one immutable schedule-worker cycle receipt."""

        path = self.path.parent / "schedule-worker-ticks.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def schedule_worker_tick_receipts(
        self,
        *,
        service_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order schedule-worker cycle receipts."""

        path = self.path.parent / "schedule-worker-ticks.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if service_id is None:
            return rows
        return [row for row in rows if row.get("service_id") == service_id]

    def next_schedule_worker_cycle_index(
        self,
        *,
        service_id: str,
    ) -> int:
        """Derive the next worker cycle index from persisted receipts."""

        rows = self.schedule_worker_tick_receipts(service_id=service_id)
        if not rows:
            return 0
        indices: list[int] = []
        for row in rows:
            value = row.get("cycle_index")
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError("persisted worker cycle_index must be integer")
            indices.append(value)
        expected = list(range(len(indices)))
        if indices != expected:
            raise ValueError("persisted worker cycle indices are not contiguous")
        return len(indices)

    def append_operator_log_revision(
        self,
        revision: "OperatorLogRevision",
    ) -> None:
        """Append one immutable operator-log revision."""

        path = self.path.parent / "operator-log-revisions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(revision.to_dict(), sort_keys=True) + "\n"
            )

    def operator_log_revisions(
        self,
        *,
        note_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order operator-log revisions."""

        path = self.path.parent / "operator-log-revisions.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if note_id is None:
            return rows
        return [row for row in rows if row.get("note_id") == note_id]

    def append_ghostwalk_accepted_intent_revision(
        self,
        revision: "GhostWalkAcceptedIntentRevision",
    ) -> None:
        """Append one immutable Ghost-Walk accepted-intent revision."""

        path = (
            self.path.parent
            / "ghostwalk-accepted-intent-revisions.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(revision.to_dict(), sort_keys=True) + "\n"
            )

    def ghostwalk_accepted_intent_revisions(
        self,
        *,
        target_inference_receipt_sha256: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order Ghost-Walk accepted-intent revisions."""

        path = (
            self.path.parent
            / "ghostwalk-accepted-intent-revisions.jsonl"
        )
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if target_inference_receipt_sha256 is None:
            return rows
        return [
            row
            for row in rows
            if row.get("target_inference_receipt_sha256")
            == target_inference_receipt_sha256
        ]

    def append_ghostwalk_policy_admission_receipt(
        self,
        receipt: "GhostWalkPolicyAdmissionReceipt",
    ) -> None:
        """Append one immutable Ghost-Walk policy-admission receipt."""

        path = (
            self.path.parent
            / "ghostwalk-policy-admission-receipts.jsonl"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(receipt.to_dict(), sort_keys=True) + "\n"
            )

    def ghostwalk_policy_admission_receipts(
        self,
        *,
        target_inference_receipt_sha256: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order Ghost-Walk policy-admission receipts."""

        path = (
            self.path.parent
            / "ghostwalk-policy-admission-receipts.jsonl"
        )
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if target_inference_receipt_sha256 is None:
            return rows
        return [
            row
            for row in rows
            if row.get("target_inference_receipt_sha256")
            == target_inference_receipt_sha256
        ]

    def append_ghostwalk_authority_request(
        self,
        request: "GhostWalkAuthorityRequest",
    ) -> None:
        """Append one immutable Ghost-Walk authority request."""

        path = self.path.parent / "ghostwalk-authority-requests.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(request.to_dict(), sort_keys=True) + "\n"
            )

    def ghostwalk_authority_requests(
        self,
        *,
        target_inference_receipt_sha256: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order Ghost-Walk AuthorityRequests."""

        path = self.path.parent / "ghostwalk-authority-requests.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if target_inference_receipt_sha256 is None:
            return rows
        return [
            row
            for row in rows
            if row.get("target_inference_receipt_sha256")
            == target_inference_receipt_sha256
        ]

    def append_interaction_guard_receipt(
        self,
        receipt: "InteractionGuardReceipt",
    ) -> None:
        """Append one immutable GUI interaction guard receipt."""

        path = self.path.parent / "interaction-guard-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(receipt.to_dict(), sort_keys=True) + "\n"
            )

    def recent_interaction_guard_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest interaction guard receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent interaction guard receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent interaction guard receipt limit must be non-negative"
            )
        path = self.path.parent / "interaction-guard-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_ghostwalk_session(
        self,
        session: "GhostWalkSession",
    ) -> None:
        """Append one immutable ghost-walk demonstration session."""

        path = self.path.parent / "ghostwalk-sessions.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(session.to_dict(), sort_keys=True) + "\n")

    def ghostwalk_sessions(
        self,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return persisted ghost-walk sessions."""

        path = self.path.parent / "ghostwalk-sessions.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if session_id is None:
            return rows
        return [row for row in rows if row.get("session_id") == session_id]

    def append_ghostwalk_observation(
        self,
        observation: "GhostWalkObservation",
    ) -> None:
        """Append one immutable ghost-walk observation."""

        path = self.path.parent / "ghostwalk-observations.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(
                json.dumps(observation.to_dict(), sort_keys=True) + "\n"
            )

    def ghostwalk_observations(
        self,
        *,
        session_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order ghost-walk observations."""

        path = self.path.parent / "ghostwalk-observations.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if session_id is None:
            return rows
        return [row for row in rows if row.get("session_id") == session_id]

    def append_ghostwalk_draft_receipt(
        self,
        receipt: "GhostWalkDraftReceipt",
    ) -> None:
        """Append one immutable ghost-walk draft compilation receipt."""

        path = self.path.parent / "ghostwalk-draft-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_ghostwalk_draft_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest ghost-walk draft compilation receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent ghost-walk draft receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent ghost-walk draft receipt limit must be non-negative"
            )
        path = self.path.parent / "ghostwalk-draft-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_ghostwalk_capture_receipt(
        self,
        receipt: "GhostWalkCaptureReceipt",
    ) -> None:
        """Append one immutable ghost-walk OS capture receipt."""

        path = self.path.parent / "ghostwalk-capture-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_ghostwalk_capture_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest ghost-walk OS capture receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent ghost-walk capture receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent ghost-walk capture receipt limit must be non-negative"
            )
        path = self.path.parent / "ghostwalk-capture-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_ghostwalk_listener_receipt(
        self,
        receipt: "GhostWalkListenerReceipt",
    ) -> None:
        """Append one immutable Windows ghost-walk listener receipt."""

        path = self.path.parent / "ghostwalk-listener-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def ghostwalk_listener_receipts(
        self,
        *,
        listener_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order listener provenance receipts."""

        path = self.path.parent / "ghostwalk-listener-receipts.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if listener_id is None:
            return rows
        return [
            row
            for row in rows
            if row.get("listener_id") == listener_id
        ]

    def next_ghostwalk_listener_sequence(
        self,
        *,
        listener_id: str,
    ) -> int:
        """Derive next listener event sequence from persisted receipts."""

        rows = self.ghostwalk_listener_receipts(
            listener_id=listener_id
        )
        if not rows:
            return 0
        indices: list[int] = []
        for row in rows:
            value = row.get("listener_sequence")
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    "persisted listener_sequence must be integer"
                )
            indices.append(value)
        if indices != list(range(len(indices))):
            raise ValueError(
                "persisted listener sequences are not contiguous"
            )
        return len(indices)

    def append_uia_element_snapshot(
        self,
        snapshot: "UiaElementSnapshot",
    ) -> None:
        """Append one immutable privacy-bounded UIA element snapshot."""

        path = self.path.parent / "uia-element-snapshots.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n")

    def uia_element_snapshots(
        self,
        *,
        snapshot_sha256: str | None = None,
    ) -> list[dict[str, object]]:
        """Return persisted UIA element identity snapshots."""

        path = self.path.parent / "uia-element-snapshots.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if snapshot_sha256 is None:
            return rows
        return [
            row
            for row in rows
            if row.get("snapshot_sha256") == snapshot_sha256
        ]

    def append_uia_lookup_receipt(
        self,
        receipt: "UiaLookupReceipt",
    ) -> None:
        """Append one immutable Windows UIA semantic lookup receipt."""

        path = self.path.parent / "uia-lookup-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_uia_lookup_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest Windows UIA semantic lookup receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent UIA lookup receipt limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent UIA lookup receipt limit must be non-negative"
            )
        path = self.path.parent / "uia-lookup-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_semantic_revalidation_receipt(
        self,
        receipt: "SemanticRevalidationReceipt",
    ) -> None:
        """Append one immutable semantic selector replay receipt."""

        path = self.path.parent / "semantic-revalidation-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_semantic_revalidation_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest semantic selector replay receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent semantic revalidation limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent semantic revalidation limit must be non-negative"
            )
        path = self.path.parent / "semantic-revalidation-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_desktop_interaction_receipt(
        self,
        receipt: "DesktopInteractionReceipt",
    ) -> None:
        """Append one immutable governed desktop interaction receipt."""

        path = self.path.parent / "desktop-interaction-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_desktop_interaction_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest governed desktop interaction receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent desktop interaction limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent desktop interaction limit must be non-negative"
            )
        path = self.path.parent / "desktop-interaction-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_post_action_verification_receipt(
        self,
        receipt: "PostActionVerificationReceipt",
    ) -> None:
        """Append one immutable post-action verification receipt."""

        path = self.path.parent / "post-action-verification-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_post_action_verification_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest post-action verification receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent post-action verification limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent post-action verification limit must be non-negative"
            )
        path = self.path.parent / "post-action-verification-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_ghostwalk_state_snapshot(
        self,
        snapshot: "GhostWalkUiStateSnapshot",
    ) -> None:
        """Append one immutable before/after Ghost-Walk UI state snapshot."""

        path = self.path.parent / "ghostwalk-ui-state-snapshots.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n")

    def ghostwalk_state_snapshots(
        self,
        *,
        action_observation_sha256: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order Ghost-Walk UI state snapshots."""

        path = self.path.parent / "ghostwalk-ui-state-snapshots.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if action_observation_sha256 is None:
            return rows
        return [
            row
            for row in rows
            if row.get("action_observation_sha256")
            == action_observation_sha256
        ]

    def append_transition_inference_receipt(
        self,
        receipt: "TransitionInferenceReceipt",
    ) -> None:
        """Append one immutable Ghost-Walk transition inference receipt."""

        path = self.path.parent / "transition-inference-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_transition_inference_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest Ghost-Walk transition inference receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent transition inference limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent transition inference limit must be non-negative"
            )
        path = self.path.parent / "transition-inference-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def transition_inference_receipt(
        self,
        *,
        receipt_sha256: str,
    ) -> dict[str, object] | None:
        """Return one transition inference receipt by its claimed hash."""

        path = self.path.parent / "transition-inference-receipts.jsonl"
        if not path.exists():
            return None
        for line in reversed(path.read_text(encoding="utf-8").splitlines()):
            row = json.loads(line)
            if row.get("receipt_sha256") == receipt_sha256:
                return row
        return None

    def append_uia_state_observation_receipt(
        self,
        receipt: "UiaStateObservationReceipt",
    ) -> None:
        """Append one immutable bounded UIA state-observer receipt."""

        path = self.path.parent / "uia-state-observer-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_uia_state_observation_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest bounded UIA state-observer receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent UIA state-observer limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent UIA state-observer limit must be non-negative"
            )
        path = self.path.parent / "uia-state-observer-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_transition_coordinator_receipt(
        self,
        receipt: "TransitionCoordinatorReceipt",
    ) -> None:
        """Append one immutable Ghost-Walk transition coordinator receipt."""

        path = self.path.parent / "transition-coordinator-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_transition_coordinator_receipts(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return newest Ghost-Walk transition coordinator receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError(
                "recent transition coordinator limit must be an integer"
            )
        if limit < 0:
            raise ValueError(
                "recent transition coordinator limit must be non-negative"
            )
        path = self.path.parent / "transition-coordinator-receipts.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def append_baseline_refresh_receipt(
        self,
        receipt: "BaselineRefreshReceipt",
    ) -> None:
        """Append one immutable Ghost-Walk baseline refresh receipt."""

        path = self.path.parent / "baseline-refresh-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def baseline_refresh_receipts(
        self,
        *,
        service_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order baseline refresh receipts."""

        path = self.path.parent / "baseline-refresh-receipts.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if service_id is None:
            return rows
        return [row for row in rows if row.get("service_id") == service_id]

    def next_baseline_refresh_sequence(
        self,
        *,
        service_id: str,
    ) -> int:
        """Derive the next contiguous baseline refresh service sequence."""

        rows = self.baseline_refresh_receipts(service_id=service_id)
        if not rows:
            return 0
        sequences: list[int] = []
        previous_sha: str | None = None
        for row in rows:
            value = row.get("sequence")
            if isinstance(value, bool) or not isinstance(value, int):
                raise TypeError(
                    "persisted baseline refresh sequence must be integer"
                )
            sequences.append(value)
            receipt_sha = row.get("receipt_sha256")
            if not isinstance(receipt_sha, str) or len(receipt_sha) != 64:
                raise TypeError(
                    "persisted baseline refresh receipt hash is invalid"
                )
            claimed_previous = row.get("previous_receipt_sha256")
            if claimed_previous != previous_sha:
                raise ValueError(
                    "persisted baseline refresh receipt hash chain mismatch"
                )
            previous_sha = receipt_sha
        if sequences != list(range(len(sequences))):
            raise ValueError(
                "persisted baseline refresh sequences are not contiguous"
            )
        return len(sequences)

    def latest_baseline_refresh_receipt_sha256(
        self,
        *,
        service_id: str,
    ) -> str | None:
        """Return the latest receipt hash for one baseline refresh service."""

        rows = self.baseline_refresh_receipts(service_id=service_id)
        if not rows:
            return None
        value = rows[-1].get("receipt_sha256")
        if not isinstance(value, str):
            raise TypeError(
                "persisted baseline refresh receipt hash must be string"
            )
        return value

    def append_ghostwalk_host_receipt(
        self,
        receipt: "GhostWalkHostReceipt",
    ) -> None:
        """Append one immutable Ghost-Walk host lifecycle receipt."""

        path = self.path.parent / "ghostwalk-host-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def ghostwalk_host_receipts(
        self,
        *,
        host_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order Ghost-Walk host lifecycle receipts."""

        path = self.path.parent / "ghostwalk-host-receipts.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if host_id is None:
            return rows
        return [row for row in rows if row.get("host_id") == host_id]

    def next_ghostwalk_host_sequence(
        self,
        *,
        host_id: str,
    ) -> int:
        """Return next sequence only when persisted host history is intact."""

        rows = self.ghostwalk_host_receipts(host_id=host_id)
        if not rows:
            return 0
        sequences: list[int] = []
        previous_sha: str | None = None
        for row in rows:
            sequence = row.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise TypeError(
                    "persisted Ghost-Walk host sequence must be integer"
                )
            receipt_sha = row.get("receipt_sha256")
            if not isinstance(receipt_sha, str) or len(receipt_sha) != 64:
                raise TypeError(
                    "persisted Ghost-Walk host receipt hash is invalid"
                )
            claimed_previous = row.get("previous_receipt_sha256")
            if claimed_previous != previous_sha:
                raise ValueError(
                    "persisted Ghost-Walk host receipt hash chain mismatch"
                )
            sequences.append(sequence)
            previous_sha = receipt_sha
        if sequences != list(range(len(sequences))):
            raise ValueError(
                "persisted Ghost-Walk host sequences are not contiguous"
            )
        return len(sequences)

    def latest_ghostwalk_host_receipt_sha256(
        self,
        *,
        host_id: str,
    ) -> str | None:
        """Return latest receipt hash for one Ghost-Walk host."""

        rows = self.ghostwalk_host_receipts(host_id=host_id)
        if not rows:
            return None
        value = rows[-1].get("receipt_sha256")
        if not isinstance(value, str):
            raise TypeError(
                "persisted Ghost-Walk host receipt hash must be string"
            )
        return value

    def append_ghostwalk_control_receipt(
        self,
        receipt: "GhostWalkControlReceipt",
    ) -> None:
        """Append one immutable Ghost-Walk control-surface receipt."""

        path = self.path.parent / "ghostwalk-control-receipts.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def ghostwalk_control_receipts(
        self,
        *,
        surface_id: str | None = None,
    ) -> list[dict[str, object]]:
        """Return append-order Ghost-Walk control receipts."""

        path = self.path.parent / "ghostwalk-control-receipts.jsonl"
        if not path.exists():
            return []
        rows = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
        ]
        if surface_id is None:
            return rows
        return [
            row
            for row in rows
            if row.get("surface_id") == surface_id
        ]

    def next_ghostwalk_control_sequence(
        self,
        *,
        surface_id: str,
    ) -> int:
        """Return next control sequence when persisted history is intact."""

        rows = self.ghostwalk_control_receipts(surface_id=surface_id)
        if not rows:
            return 0
        sequences: list[int] = []
        previous_sha: str | None = None
        for row in rows:
            sequence = row.get("sequence")
            if isinstance(sequence, bool) or not isinstance(sequence, int):
                raise TypeError(
                    "persisted Ghost-Walk control sequence must be integer"
                )
            receipt_sha = row.get("receipt_sha256")
            if not isinstance(receipt_sha, str) or len(receipt_sha) != 64:
                raise TypeError(
                    "persisted Ghost-Walk control receipt hash is invalid"
                )
            claimed_previous = row.get("previous_receipt_sha256")
            if claimed_previous != previous_sha:
                raise ValueError(
                    "persisted Ghost-Walk control receipt hash chain mismatch"
                )
            sequences.append(sequence)
            previous_sha = receipt_sha
        if sequences != list(range(len(sequences))):
            raise ValueError(
                "persisted Ghost-Walk control sequences are not contiguous"
            )
        return len(sequences)

    def latest_ghostwalk_control_receipt_sha256(
        self,
        *,
        surface_id: str,
    ) -> str | None:
        """Return latest receipt hash for one Ghost-Walk control surface."""

        rows = self.ghostwalk_control_receipts(surface_id=surface_id)
        if not rows:
            return None
        value = rows[-1].get("receipt_sha256")
        if not isinstance(value, str):
            raise TypeError(
                "persisted Ghost-Walk control receipt hash must be string"
            )
        return value

    def append_reconciliation(
        self,
        receipt: "ExecutionReconciliationReceipt | RealityBoundReconciliationReceipt",
    ) -> None:
        """Append one immutable reconciliation receipt beside execution history."""

        path = self.path.parent / "execution-reconciliations.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt.to_dict(), sort_keys=True) + "\n")

    def recent_reconciliations(
        self,
        limit: int = 10,
    ) -> list[dict[str, object]]:
        """Return the newest append-only execution reconciliation receipts."""

        if isinstance(limit, bool) or not isinstance(limit, int):
            raise TypeError("recent reconciliation limit must be an integer")
        if limit < 0:
            raise ValueError("recent reconciliation limit must be non-negative")
        path = self.path.parent / "execution-reconciliations.jsonl"
        if limit == 0 or not path.exists():
            return []
        lines = path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines[-limit:]]

    def claim_binding(self, binding_sha256: str) -> bool:
        """Atomically reserve one governed binding for an execution attempt."""

        self._validate_binding_sha256(binding_sha256)
        claim_dir = self.path.parent / "binding-claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim_path = claim_dir / f"{binding_sha256}.claim"
        try:
            fd = os.open(
                claim_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(binding_sha256 + "\n")
        return True

    def release_binding_claim(self, binding_sha256: str) -> None:
        """Release a claim only when the executor was never entered."""

        self._validate_binding_sha256(binding_sha256)
        claim_path = (
            self.path.parent
            / "binding-claims"
            / f"{binding_sha256}.claim"
        )
        claim_path.unlink(missing_ok=True)

    def has_consumed_binding(self, binding_sha256: str) -> bool:
        """Return true once a bound action reached an allowed executor attempt."""

        if not self.path.exists():
            return False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            provenance = entry.get("governed_provenance")
            if not isinstance(provenance, dict):
                continue
            if provenance.get("action_binding_sha256") != binding_sha256:
                continue
            if entry.get("permission_status") != "allowed":
                continue
            if entry.get("execution_status") in {"succeeded", "failed", "outcome_unknown"}:
                return True
        return False

    def claim_action_lease(self, lease_sha256: str) -> bool:
        """Atomically reserve one ActionLease for an execution attempt."""

        self._validate_sha256(lease_sha256, "lease_sha256")
        claim_dir = self.path.parent / "action-lease-claims"
        claim_dir.mkdir(parents=True, exist_ok=True)
        claim_path = claim_dir / f"{lease_sha256}.claim"
        try:
            fd = os.open(
                claim_path,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(lease_sha256 + "\n")
        return True

    def release_action_lease_claim(self, lease_sha256: str) -> None:
        """Release a lease claim only when the executor was never entered."""

        self._validate_sha256(lease_sha256, "lease_sha256")
        claim_path = (
            self.path.parent
            / "action-lease-claims"
            / f"{lease_sha256}.claim"
        )
        claim_path.unlink(missing_ok=True)

    def has_consumed_action_lease(self, lease_sha256: str) -> bool:
        """Return true once an ActionLease reached an allowed executor attempt."""

        self._validate_sha256(lease_sha256, "lease_sha256")
        if not self.path.exists():
            return False
        for line in self.path.read_text(encoding="utf-8").splitlines():
            entry = json.loads(line)
            provenance = entry.get("governed_provenance")
            if not isinstance(provenance, dict):
                continue
            if provenance.get("action_lease_sha256") != lease_sha256:
                continue
            if entry.get("permission_status") != "allowed":
                continue
            if entry.get("execution_status") in {"succeeded", "failed", "outcome_unknown"}:
                return True
        return False

    @staticmethod
    def _validate_sha256(value: str, label: str) -> None:
        normalized = value.strip().lower()
        if len(normalized) != 64:
            raise ValueError(f"{label} must be a SHA-256 hex digest")
        try:
            int(normalized, 16)
        except ValueError as exc:
            raise ValueError(
                f"{label} must be a SHA-256 hex digest"
            ) from exc

    @staticmethod
    def _validate_binding_sha256(binding_sha256: str) -> None:
        RealityLedger._validate_sha256(
            binding_sha256,
            "binding_sha256",
        )
