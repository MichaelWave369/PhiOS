"""Create only this disposable user's canonical data before a normal-ISO test."""
from pathlib import Path

from phios.memory import MemoryOperatorRuntime, MemoryRecord, MemoryRuntimeConfig
from phios.state_recovery import backup


def seed_normal() -> None:
    root = Path.home() / '.local/state/phios'
    runtime = MemoryOperatorRuntime(state_root=root / 'memory',
        config=MemoryRuntimeConfig(enabled=True, principal_id='operator', scopes=('private',),
            classifications=('operator',), retention_policy_id='retain'),
        allowed_permissions=('memory.write', 'memory.read'))
    record = MemoryRecord.build(record_id='installed-proof', revision=1, source_id='operator', source_kind='human',
        provenance_refs=(), created_at='2026-09-30T00:00:00+00:00', scope_id='private', classification='operator',
        retention_policy_id='retain', expires_at=None, epistemic_kind='source', text='Persist this acknowledged installed-OS record')
    assert runtime.put(record, operation_id='installed-proof-put', task_id='ci-only').status == 'ok'
    assert runtime.store.get('installed-proof') == record
    backup(root, root.parent / 'phios-ci-data-backup')
