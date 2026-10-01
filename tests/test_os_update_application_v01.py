from __future__ import annotations

import importlib.util
import json
import os
from functools import partial
from pathlib import Path
from typing import Any

import pytest

FILE = Path(__file__).resolve().parents[1] / 'packaging/linux/updates/apply.py'
spec = importlib.util.spec_from_file_location('phios_os_application', FILE)
assert spec is not None and spec.loader is not None
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)


@pytest.fixture(autouse=True)
def metadata_owner_for_unprivileged_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply.recover, 'regular', partial(apply.recover.regular, owner=os.getuid()))


def write_counter(path: Path, sequence: Any, *, schema: str, source: str = 'a' * 40) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_text(json.dumps({'schema_version': schema, 'sequence': sequence, 'source_commit': source}))
    path.chmod(0o600)


def test_recovery_counter_survives_missing_active_root_and_older_snapshot(tmp_path: Path) -> None:
    write_counter(tmp_path / '@snapshots/os-update-counter.json', 8, schema='phios.os-update-counter.v1')
    saved = tmp_path / 'saved-root'
    write_counter(saved / 'var/lib/phios/os-update-generation.json', 2, schema='phios.os-update-generation.v1')
    assert apply.recover.recovery_sequence(tmp_path, saved) == 9
    assert not (tmp_path / '@root').exists()


@pytest.mark.parametrize('case', ['missing-root-counter', 'missing-anchor', 'mismatch', 'wrong-source', 'boolean', 'unknown-schema'])
def test_update_holds_inconsistent_or_unrecognized_persistent_counters(tmp_path: Path, case: str) -> None:
    root_counter = tmp_path / '@root/var/lib/phios/os-update-generation.json'
    anchor = tmp_path / '@snapshots/os-update-counter.json'
    write_counter(root_counter, 3, schema='phios.os-update-generation.v1')
    write_counter(anchor, 3, schema='phios.os-update-counter.v1')
    assert apply.sequence(tmp_path, 'a' * 40) == 3
    if case == 'missing-root-counter':
        root_counter.unlink()
    elif case == 'missing-anchor':
        anchor.unlink()
    elif case == 'mismatch':
        write_counter(anchor, 4, schema='phios.os-update-counter.v1')
    elif case == 'wrong-source':
        write_counter(anchor, 3, schema='phios.os-update-counter.v1', source='b' * 40)
    elif case == 'boolean':
        write_counter(anchor, True, schema='phios.os-update-counter.v1')
    else:
        write_counter(anchor, 3, schema='unknown')
    before = {p: p.read_bytes() for p in [root_counter, anchor] if p.exists()}
    with pytest.raises(ValueError):
        apply.sequence(tmp_path, 'a' * 40)
    assert {p: p.read_bytes() for p in before} == before


def test_initial_installation_has_counter_zero(tmp_path: Path) -> None:
    assert apply.sequence(tmp_path, 'a' * 40) == 0


def test_counter_alias_cannot_hide_a_consumed_transition(tmp_path: Path) -> None:
    target = tmp_path / 'unsafe'
    write_counter(target, 9, schema='phios.os-update-counter.v1')
    (tmp_path / '@snapshots').mkdir(mode=0o700)
    (tmp_path / '@snapshots/os-update-counter.json').symlink_to(target)
    with pytest.raises(ValueError):
        apply.recover.recovery_sequence(tmp_path, tmp_path / 'saved')


def test_trust_change_after_confirmation_cannot_create_a_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(apply.verify, 'load_trust', lambda: ({'primary_fingerprint': 'B' * 40}, b'changed'))
    effects = []
    monkeypatch.setattr(apply.recover, 'execute', lambda *args: effects.append(args))
    with pytest.raises(ValueError, match='trust changed'):
        apply.execute({'disk': {}, 'checkpoint_generation': 'c' * 32}, {}, tmp_path,
                      ({'primary_fingerprint': 'A' * 40}, b'reviewed'))
    assert effects == []


def test_expiration_after_confirmation_cannot_create_a_checkpoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    trust = ({'primary_fingerprint': 'A' * 40}, b'reviewed')
    monkeypatch.setattr(apply.verify, 'load_trust', lambda: trust)
    def expired(*args: Any, **kwargs: Any) -> None:
        raise ValueError('expired validity window')
    monkeypatch.setattr(apply.verify, 'validate_manifest', expired)
    effects = []
    monkeypatch.setattr(apply.recover, 'execute', lambda *args: effects.append(args))
    plan = {'disk': {}, 'checkpoint_generation': 'c' * 32, 'installed': {'source_commit': 'a' * 40},
            'base_sequence': 0, 'base_packages': [{'name': 'linux', 'version': '2-1'}]}
    with pytest.raises(ValueError, match='expired'):
        apply.execute(plan, {}, tmp_path, trust)
    assert effects == []


def test_native_version_comparison_holds_downgrades_but_allows_reinstall(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []
    def compare(*args: str) -> str:
        seen.append(args)
        return '-1\n' if args[1] == '1-1' else '0\n'
    monkeypatch.setattr(apply.recover, 'run', compare)
    baseline = [{'name': 'linux', 'version': '2-1'}]
    with pytest.raises(ValueError, match='downgrades'):
        apply.supported_versions({'packages': [{'name': 'linux', 'version': '1-1'}]}, baseline)
    apply.supported_versions({'packages': [{'name': 'linux', 'version': '2-1'}, {'name': 'new', 'version': '1-1'}]}, baseline)
    assert seen == [('vercmp', '1-1', '2-1'), ('vercmp', '2-1', '2-1')]


def test_command_failure_preserves_stdout_hook_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    from subprocess import CompletedProcess
    monkeypatch.setattr(apply.recover.shutil, 'which', lambda *args, **kwargs: '/usr/bin/mkinitcpio')
    monkeypatch.setattr(apply.recover.subprocess, 'run', lambda *args, **kwargs:
                        CompletedProcess(args, 0, stdout='==> ERROR: boot image failed\n', stderr=''))
    with pytest.raises(RuntimeError, match='boot image failed'):
        apply.recover.run('mkinitcpio', '-P')
