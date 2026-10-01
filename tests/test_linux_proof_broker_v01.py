from __future__ import annotations

import copy
import importlib.util
import io
import os
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

FILE = Path(__file__).resolve().parents[1] / 'packaging/linux/proof/broker.py'
spec = importlib.util.spec_from_file_location('phios_proof_broker_test', FILE)
assert spec is not None and spec.loader is not None
broker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(broker)


@pytest.fixture
def setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Only unit-test temporary files use the CI test principal; production is UID 0.
    monkeypatch.setattr(broker, 'OWNER', os.getuid())
    monkeypatch.setattr(broker, 'STORE', tmp_path / 'store')
    now = datetime.now(UTC)
    observed = {'source_commit': 'a' * 40, 'boot_id': 'b' * 32, 'operator_uid': 1000, 'principal_uid': 1001}
    proposal = {'schema_version': 'phios.linux-proof-proposal.v1', 'principal_uid': 1001,
        'source_commit': observed['source_commit'], 'boot_id': observed['boot_id'], 'observed_at': now.isoformat(),
        'nonce': 'c' * 32, 'capability_id': 'linux.proof_note', 'text': broker.TEXT,
        'execution_authority': False, 'effect_performed': False}
    monkeypatch.setattr(broker, 'context', lambda: copy.deepcopy(observed))
    monkeypatch.setattr(broker, 'capture', lambda *_: copy.deepcopy(proposal))
    return now, observed, proposal


class Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


def approve(setup):
    _, observed, proposal = setup
    digest = broker.approve(proposal, observed,
        input_stream=Terminal('APPROVE ' + broker.sha(broker.review_plan(proposal, observed)) + '\n'),
        output_stream=Terminal())
    assert digest is not None
    return digest


def test_real_contract_chain_effect_independent_readback_and_replay(setup):
    now, observed, _ = setup
    digest = approve(setup)
    store = broker.Store(broker.STORE)
    try:
        value = broker.decode(store.read('approvals', digest))
        assert value['intent']['execution_authority'] is False
        assert value['lease']['max_uses'] == 1 and value['lease']['execution_authority'] is False
        result = broker.execute(store, digest, observed, now + timedelta(seconds=1))
        assert result['post_effect_verified'] is True and result['effect_performed'] is True
        assert store.read('notes', digest) == broker.TEXT.encode()
        assert broker.decode(store.read('receipts', digest)) == result
        with pytest.raises(ValueError, match='consumed'):
            broker.execute(store, digest, observed, now + timedelta(seconds=2))
    finally:
        store.close()


def test_cancel_and_nonterminal_create_no_store(setup):
    _, observed, proposal = setup
    assert broker.approve(proposal, observed, input_stream=Terminal('cancel\n'), output_stream=Terminal()) is None
    assert not broker.STORE.exists()
    with pytest.raises(ValueError, match='interactive'):
        broker.approve(proposal, observed, input_stream=io.StringIO('yes'), output_stream=Terminal())
    assert not broker.STORE.exists()


def test_stale_capture_after_exact_review_creates_no_authority(setup, monkeypatch):
    _, observed, proposal = setup
    changed = dict(proposal, nonce='e' * 32)
    monkeypatch.setattr(broker, 'capture', lambda *_: changed)
    with pytest.raises(ValueError, match='changed during review'):
        approve(setup)
    assert not broker.STORE.exists()


@pytest.mark.parametrize('field,value', [('text','run a shell'), ('capability_id','shell.execute'),
    ('execution_authority',True), ('principal_uid',1000), ('boot_id','d'*32),
    ('source_commit','e'*40), ('nonce','../escape'), ('unknown',None), ('observed_at','2000-01-01T00:00:00+00:00')])
def test_untrusted_proposal_is_not_an_authority_or_arbitrary_effect(setup, field, value):
    now, observed, proposal = setup
    with pytest.raises(ValueError):
        broker.validate_proposal(dict(proposal, **{field:value}), observed, now)


@pytest.mark.parametrize('kind', ['expired', 'new-boot', 'new-source', 'suspended-or-clock-rollback'])
def test_expired_or_restored_authority_cannot_create_note(setup, monkeypatch, kind):
    now, observed, _ = setup
    digest = approve(setup)
    if kind == 'expired':
        now += timedelta(seconds=61)
    elif kind == 'suspended-or-clock-rollback':
        monkeypatch.setattr(broker, 'boot_time_ns', lambda: 10**30)
    else:
        observed = dict(observed, **{'boot_id' if kind=='new-boot' else 'source_commit':'d'* (32 if kind=='new-boot' else 40)})
    store = broker.Store(broker.STORE)
    try:
        with pytest.raises(ValueError):
            broker.execute(store, digest, observed, now)
        assert not (broker.STORE / 'notes' / digest).exists()
        assert not (broker.STORE / 'consumed' / digest).exists()
    finally:
        store.close()


def test_consume_sync_failure_precedes_effect_and_never_reopens_lease(setup, monkeypatch):
    now, observed, _ = setup
    digest = approve(setup)
    store = broker.Store(broker.STORE)
    publish = store.publish
    def failure(kind, name, data):
        publish(kind, name, data)
        if kind == 'consumed':
            raise OSError('injected durable boundary failure')
    monkeypatch.setattr(store, 'publish', failure)
    try:
        with pytest.raises(OSError):
            broker.execute(store, digest, observed, now + timedelta(seconds=1))
        assert not (broker.STORE / 'notes' / digest).exists()
        monkeypatch.setattr(store, 'publish', publish)
        with pytest.raises(ValueError, match='consumed'):
            broker.execute(store, digest, observed, now + timedelta(seconds=2))
    finally:
        store.close()


def test_corrupt_or_linked_approval_held_before_consumption(setup):
    now, observed, _ = setup
    digest = approve(setup)
    path = broker.STORE / 'approvals' / digest
    data = path.read_bytes()
    path.write_bytes(data[:-3])
    store = broker.Store(broker.STORE)
    try:
        with pytest.raises(ValueError):
            broker.execute(store, digest, observed, now)
        path.write_bytes(data)
        os.link(path, path.with_name('extra-link'))
        with pytest.raises(ValueError, match='singly linked'):
            broker.execute(store, digest, observed, now)
        assert not (broker.STORE / 'notes' / digest).exists()
    finally:
        store.close()


def test_symlinked_note_directory_cannot_redirect_root_effect(setup, tmp_path):
    now, observed, _ = setup
    digest = approve(setup)
    outside = tmp_path / 'outside'
    outside.mkdir()
    (broker.STORE / 'notes').symlink_to(outside)
    store = broker.Store(broker.STORE)
    try:
        with pytest.raises(OSError):
            broker.execute(store, digest, observed, now + timedelta(seconds=1))
        assert list(outside.iterdir()) == []
        with pytest.raises(ValueError, match='consumed'):
            broker.execute(store, digest, observed, now + timedelta(seconds=2))
    finally:
        store.close()


def test_parser_rejects_duplicate_and_nonfinite_json():
    for value in [b'{"a":1,"a":2}', b'{"a":NaN}']:
        with pytest.raises(ValueError):
            broker.decode(value)


def test_two_processes_can_consume_only_once(setup):
    _, observed, _ = setup
    digest = approve(setup)
    code = '''
import importlib.util,json,os,sys
from pathlib import Path
from datetime import UTC,datetime
spec=importlib.util.spec_from_file_location('production_proof',sys.argv[1])
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.OWNER=os.getuid();module.STORE=Path(sys.argv[2])
store=module.Store(module.STORE)
try:
    module.execute(store,sys.argv[3],json.loads(sys.argv[4]),datetime.now(UTC))
except ValueError as error:
    if 'lease_consumed' not in str(error): raise
    raise SystemExit(2)
finally:
    store.close()
'''
    processes = [subprocess.Popen([sys.executable, '-c', code, str(FILE), str(broker.STORE), digest, json.dumps(observed)],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
    try:
        results = [process.communicate(timeout=15) for process in processes]
        assert sorted(process.returncode for process in processes) == [0, 2], results
        assert (broker.STORE / 'notes' / digest).read_bytes() == broker.TEXT.encode()
        assert len(list((broker.STORE / 'receipts').iterdir())) == 1
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill()
                process.wait()
