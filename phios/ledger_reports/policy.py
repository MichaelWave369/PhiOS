from __future__ import annotations

from dataclasses import dataclass

from phios.mandala import AuthorityContext

from .validation import sha256_json


@dataclass(frozen=True, kw_only=True)
class LedgerSnapshotPolicy:
    """Closed projection policy for snapshot export.

    This is a visibility/projection policy, not a grant. AuthorityContext remains the
    permission gate for whether export may occur.
    """

    include_execution_artifact_sha256: bool = True
    include_execution_error: bool = False
    include_execution_artifact_path: bool = False
    include_mandala_reason: bool = True
    policy_version: str = "phios.snapshot_policy.v0.1"

    def authorize(self, authority: AuthorityContext) -> bool:
        return authority.allows("ledger.snapshot.export")

    @property
    def policy_sha256(self) -> str:
        return sha256_json(
            {
                "policy_version": self.policy_version,
                "include_execution_artifact_sha256": self.include_execution_artifact_sha256,
                "include_execution_error": self.include_execution_error,
                "include_execution_artifact_path": self.include_execution_artifact_path,
                "include_mandala_reason": self.include_mandala_reason,
            }
        )
