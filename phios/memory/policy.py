from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from phios.mandala import AuthorityContext

from .models import MemoryAccessDecision, MemoryRecord
from .validation import require_nonempty, require_utc_timestamp, sha256_json


@dataclass(frozen=True, kw_only=True)
class MemoryPolicyRule:
    principal_id: str
    scopes: tuple[str, ...]
    classifications: tuple[str, ...]
    operations: tuple[str, ...] = ("memory.read", "memory.write", "memory.delete")

    def __post_init__(self) -> None:
        require_nonempty(self.principal_id, "principal_id")
        if not self.scopes or not self.classifications:
            raise ValueError("memory policy rules require scopes and classifications")


class MemoryAccessPolicy:
    """Deny-default record policy layered under PhiOS authority."""

    def __init__(self, rules: tuple[MemoryPolicyRule, ...], *, revision: str = "v0.1") -> None:
        self._rules = {rule.principal_id: rule for rule in rules}
        self.revision = require_nonempty(revision, "revision")
        self.policy_sha256 = sha256_json(
            {
                "revision": self.revision,
                "rules": [
                    {
                        "principal_id": r.principal_id,
                        "scopes": list(r.scopes),
                        "classifications": list(r.classifications),
                        "operations": list(r.operations),
                    }
                    for r in sorted(rules, key=lambda item: item.principal_id)
                ],
            }
        )

    def resolve(
        self,
        *,
        principal_id: str,
        task_id: str,
        operation: str,
        authority: AuthorityContext,
        expires_at: str | None = None,
    ) -> MemoryAccessDecision | None:
        principal_id = require_nonempty(principal_id, "principal_id")
        task_id = require_nonempty(task_id, "task_id")
        operation = require_nonempty(operation, "operation")
        if not authority.allows(operation):
            return None
        rule = self._rules.get(principal_id)
        if rule is None or operation not in rule.operations:
            return None
        if expires_at:
            expires_at = require_utc_timestamp(expires_at, "expires_at")
            if datetime.fromisoformat(expires_at).astimezone(UTC) <= datetime.now(UTC):
                return None
        return MemoryAccessDecision(
            principal_id=principal_id,
            task_id=task_id,
            operation=operation,
            allowed_scopes=rule.scopes,
            allowed_classifications=rule.classifications,
            policy_sha256=self.policy_sha256,
            expires_at=expires_at,
        )

    @staticmethod
    def permits(decision: MemoryAccessDecision, record: MemoryRecord) -> bool:
        return (
            record.scope_id in decision.allowed_scopes
            and record.classification in decision.allowed_classifications
        )
