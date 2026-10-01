"""Installed-only root broker for one boot-bound, single-use proof-note effect."""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pwd
import re
import stat
import sys
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Iterator, TextIO

from phios.action_lease import ActionLease, evaluate_action_lease
from phios.authority_epoch import AuthorityEpoch
from phios.effect_intent import EffectIntent
from phios.enforcement_profile import EnforcementProfile, EnforcementRule
from phios.mandala import AuthoritativeAuthorityEvent, AuthorityEventKind

OWNER = 0
STORE = Path('/.snapshots/phios-linux-proof')
PROPOSAL = Path('/var/lib/phios-agent/proposal.json')
SOURCE = Path('/usr/share/phios/source-commit')
TEXT = 'PhiOS verified one explicitly approved Linux proof note.\n'
LIMIT = 65536
TTL = 60


def boot_time_ns() -> int:
    return time.clock_gettime_ns(time.CLOCK_BOOTTIME)


def encode(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()


def sha(value: Any) -> str:
    return hashlib.sha256(encode(value)).hexdigest()


def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in values:
        if key in result:
            raise ValueError('duplicate JSON field')
        result[key] = value
    return result


def reject_constant(value: str) -> None:
    raise ValueError('non-finite JSON: ' + value)


def decode(data: bytes) -> Any:
    return json.loads(data, object_pairs_hook=pairs, parse_constant=reject_constant)


def check_info(info: os.stat_result, *, owner: int = 0, directory: bool = False) -> None:
    kind = stat.S_ISDIR if directory else stat.S_ISREG
    if not kind(info.st_mode) or info.st_uid != owner or info.st_mode & 0o022:
        raise ValueError('protected owned directory/regular file required')
    if not directory and (info.st_nlink != 1 or info.st_size > LIMIT):
        raise ValueError('bounded singly linked regular file required')


def read_fd(fd: int, *, owner: int) -> bytes:
    before = os.fstat(fd)
    check_info(before, owner=owner)
    data = os.read(fd, LIMIT + 1)
    after = os.fstat(fd)
    def stable(row: os.stat_result) -> tuple[int, ...]:
        return (row.st_dev, row.st_ino, row.st_uid, row.st_mode, row.st_nlink, row.st_size, row.st_mtime_ns, row.st_ctime_ns)
    if len(data) > LIMIT or len(data) != before.st_size or stable(before) != stable(after):
        raise ValueError('captured file changed or exceeded bounds')
    return data


def read_path(path: Path, *, owner: int, protected_parents: bool = True) -> bytes:
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = child
            if protected_parents:
                check_info(os.fstat(fd), owner=OWNER, directory=True)
        child = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            return read_fd(child, owner=owner)
        finally:
            os.close(child)
    finally:
        os.close(fd)


def context() -> dict[str, Any]:
    if os.getuid() != 0 or os.geteuid() != 0 or os.environ.get('SUDO_UID') != '1000':
        raise ValueError('installed UID 1000 administrator must invoke this broker through sudo')
    if Path('/run/archiso/bootmnt').exists():
        raise ValueError('proof effects are disabled in the public volatile live account')
    user = pwd.getpwuid(1000)
    receipt = decode(read_path(Path('/var/lib/phios/install-receipt.json'), owner=OWNER))
    source = read_path(SOURCE, owner=OWNER).decode().strip()
    boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip().replace('-', '')
    if (receipt.get('schema_version') != 'phios.blank-disk-install.v1' or receipt.get('installed') is not True
            or receipt.get('plan', {}).get('username') != user.pw_name
            or not re.fullmatch('[0-9a-f]{40}', source) or not re.fullmatch('[0-9a-f]{32}', boot)):
        raise ValueError('installed identity/account receipt required')
    mounted = [line.split(' - ', 1) for line in Path('/proc/self/mountinfo').read_text().splitlines()]
    if not any(len(row) == 2 and row[0].split()[4] == '/.snapshots' and
               row[1].split()[0] == 'btrfs' and '/@snapshots' == row[0].split()[3] for row in mounted):
        raise ValueError('independent installed Btrfs snapshot store must be mounted')
    check_info(Path('/.snapshots').lstat(), owner=OWNER, directory=True)
    return {'source_commit': source, 'boot_id': boot, 'operator_uid': 1000, 'principal_uid': 1001}


def validate_proposal(value: Any, observed: dict[str, Any], now: datetime) -> dict[str, Any]:
    required = {'schema_version', 'principal_uid', 'source_commit', 'boot_id', 'observed_at', 'nonce',
                'capability_id', 'text', 'execution_authority', 'effect_performed'}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError('exact bounded proposal fields required')
    if (value['schema_version'] != 'phios.linux-proof-proposal.v1' or type(value['principal_uid']) is not int
            or value['principal_uid'] != 1001 or value['source_commit'] != observed['source_commit']
            or value['boot_id'] != observed['boot_id'] or value['capability_id'] != 'linux.proof_note'
            or value['text'] != TEXT or value['execution_authority'] is not False or value['effect_performed'] is not False
            or not isinstance(value['nonce'], str) or not re.fullmatch('[0-9a-f]{32}', value['nonce'])):
        raise ValueError('proposal identity/effect/scope differs from the fixed capability')
    stamp = datetime.fromisoformat(value['observed_at'])
    if stamp.tzinfo is None or not timedelta(0) <= now - stamp <= timedelta(minutes=10):
        raise ValueError('proposal observation is stale or from the future')
    return value


def capture(observed: dict[str, Any], now: datetime) -> dict[str, Any]:
    # Every ancestor is opened without following links. Agent-owned ancestry
    # is untrusted; only captured bytes, never a later read, enter the effect.
    return validate_proposal(decode(read_path(PROPOSAL, owner=1001, protected_parents=False)), observed, now)


class Store:
    def __init__(self, root: Path) -> None:
        check_info(root.parent.lstat(), owner=OWNER, directory=True)
        parent = os.open(root.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            try:
                os.mkdir(root.name, mode=0o700, dir_fd=parent)
                os.fsync(parent)
            except FileExistsError:
                pass
            self.fd = os.open(root.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                check_info(os.fstat(self.fd), owner=OWNER, directory=True)
            except BaseException:
                os.close(self.fd)
                raise
        finally:
            os.close(parent)
        self.root = root

    def close(self) -> None:
        os.close(self.fd)

    @contextmanager
    def directory(self, name: str) -> Iterator[int]:
        if name not in {'approvals', 'consumed', 'notes', 'receipts'}:
            raise ValueError('unsupported broker directory')
        try:
            os.mkdir(name, mode=0o700, dir_fd=self.fd)
            os.fsync(self.fd)
        except FileExistsError:
            pass
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=self.fd)
        try:
            check_info(os.fstat(fd), owner=OWNER, directory=True)
            yield fd
        finally:
            os.close(fd)

    @contextmanager
    def locked(self) -> Iterator[None]:
        fd = os.open('lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=self.fd)
        try:
            check_info(os.fstat(fd), owner=OWNER)
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)

    def publish(self, kind: str, digest: str, data: bytes) -> None:
        if not re.fullmatch('[0-9a-f]{64}', digest) or len(data) > LIMIT:
            raise ValueError('bounded named broker record required')
        with self.directory(kind) as directory:
            fd = os.open(digest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            try:
                view = memoryview(data)
                while view:
                    count = os.write(fd, view)
                    if count <= 0:
                        raise OSError('short broker write')
                    view = view[count:]
                os.fsync(fd)
            finally:
                os.close(fd)
            os.fsync(directory)

    def read(self, kind: str, digest: str) -> bytes:
        if not re.fullmatch('[0-9a-f]{64}', digest):
            raise ValueError('exact SHA-256 broker identity required')
        with self.directory(kind) as directory:
            fd = os.open(digest, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            try:
                return read_fd(fd, owner=OWNER)
            finally:
                os.close(fd)


def contracts(proposal: dict[str, Any], observed: dict[str, Any], decision: dict[str, Any]) -> dict[str, Any]:
    start = decision['approved_at']
    until = (datetime.fromisoformat(start) + timedelta(seconds=TTL)).isoformat()
    intent = EffectIntent.build(capability_id='linux.proof_note', capability_version='0.1.0',
        payload_sha256=hashlib.sha256(TEXT.encode()).hexdigest(), declared_at=proposal['observed_at'],
        effects_declared=('filesystem.change',), evidence_ref_sha256s=(sha(proposal),))
    policy = {'source_commit': observed['source_commit'], 'boot_id': observed['boot_id'],
        'principal_uid': 1001, 'operator_uid': 1000, 'capability_id': 'linux.proof_note',
        'fixed_store': str(STORE), 'max_uses': 1, 'ttl_seconds': TTL}
    enforcement = EnforcementProfile.build(intent=intent, rules=(EnforcementRule.build(
        rule_id='root-owned-single-note', effect_scope=('filesystem.change',),
        constraint='Only a new SHA-256-named proof note inside the protected independent store',
        layer='broker', boundary='kernel_boundary', status='enforced',
        mechanism='UID-separated root-owned broker; no-follow directory FDs; fixed bytes; exclusive creation',
        evidence_ref_sha256s=(sha(policy),)),))
    binding = {'schema_version': 'phios.linux-proof-binding.v1', 'decision_sha256': sha(decision),
        'proposal_sha256': sha(proposal), 'intent_sha256': intent.effect_intent_sha256,
        'enforcement_sha256': enforcement.profile_sha256, 'policy_sha256': sha(policy), 'principal_uid': 1001}
    epoch = AuthorityEpoch.build(principal_id='linux-uid:1001', policy_sha256=sha(policy),
        ceiling=('artifact.write',), events=(AuthoritativeAuthorityEvent(
            event_id='proof-' + decision['nonce'], sequence=1, kind=AuthorityEventKind.GRANT,
            permission='artifact.write', authority_source='installed-sudo-operator:1000',
            effective_at=start, expires_at=until),), observed_at=start)
    lease = ActionLease.issue(principal_id='linux-uid:1001', issuer_id='linux-proof-broker',
        authorization_receipt_sha256=sha(binding), intent=intent, enforcement=enforcement,
        authority_epoch=epoch, permissions_authorized=('artifact.write',), accepted_unenforced_effects=(),
        issued_at=start, valid_from=start, valid_until=until)
    return {'intent': intent.to_dict(), 'enforcement': enforcement.to_dict(), 'binding': binding,
            'authority_epoch': epoch.to_dict(), 'lease': lease.to_dict()}


def review_plan(proposal: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    return {'schema_version': 'phios.linux-proof-review.v1', 'observation': observed, 'proposal': proposal,
        'proposal_sha256': sha(proposal), 'note_sha256': hashlib.sha256(TEXT.encode()).hexdigest(),
        'store': str(STORE), 'max_uses': 1, 'ttl_seconds': TTL, 'execution_authority': False}


def approve(proposal: dict[str, Any], observed: dict[str, Any], *, input_stream: TextIO, output_stream: TextIO) -> str | None:
    review = review_plan(proposal, observed)
    print(json.dumps(review, indent=2, ensure_ascii=True), file=output_stream, flush=True)
    if not input_stream.isatty() or not output_stream.isatty():
        raise ValueError('approval requires an interactive installed sudo operator')
    print('Type exactly APPROVE ' + sha(review) + ' or anything else to cancel:', file=output_stream, flush=True)
    if input_stream.readline().strip() != 'APPROVE ' + sha(review):
        print('Cancelled; no approval, binding, lease or effect created.', file=output_stream)
        return None
    now = datetime.now(UTC)
    if context() != observed or capture(observed, now) != proposal:
        raise ValueError('proposal/OS identity changed during review')
    decision = {'schema_version': 'phios.linux-proof-decision.v1', 'kind': 'APPROVE', 'operator_uid': 1000,
        'review_sha256': sha(review), 'proposal_sha256': sha(proposal), 'approved_at': now.isoformat(),
        'expires_boot_ns': boot_time_ns() + TTL * 10**9, 'nonce': uuid.uuid4().hex}
    value = {'schema_version': 'phios.linux-proof-approval.v1', 'observation': observed, 'proposal': proposal,
             'decision': decision, **contracts(proposal, observed, decision)}
    digest = sha(value)
    store = Store(STORE)
    try:
        with store.locked():
            store.publish('approvals', digest, encode(value))
    finally:
        store.close()
    print(json.dumps({'approval_sha256': digest, 'lease_sha256': value['lease']['action_lease_sha256'],
        'execution_authority': False, 'effect_performed': False}), file=output_stream, flush=True)
    return digest


def execute(store: Store, digest: str, observed: dict[str, Any], now: datetime) -> dict[str, Any]:
    with store.locked():
        value = decode(store.read('approvals', digest))
        fields = {'schema_version', 'observation', 'proposal', 'decision', 'intent', 'enforcement', 'binding', 'authority_epoch', 'lease'}
        if not isinstance(value, dict) or set(value) != fields or sha(value) != digest:
            raise ValueError('approval record integrity/schema mismatch')
        if value['schema_version'] != 'phios.linux-proof-approval.v1' or value['observation'] != observed:
            raise ValueError('approval belongs to another boot/source/principal')
        proposal = validate_proposal(value['proposal'], observed, now)
        decision = value['decision']
        if (set(decision) != {'schema_version', 'kind', 'operator_uid', 'review_sha256', 'proposal_sha256', 'approved_at', 'expires_boot_ns', 'nonce'}
                or decision['schema_version'] != 'phios.linux-proof-decision.v1' or decision['kind'] != 'APPROVE'
                or type(decision['operator_uid']) is not int or decision['operator_uid'] != 1000
                or decision['proposal_sha256'] != sha(proposal) or decision['review_sha256'] != sha(review_plan(proposal, observed))
                or type(decision['expires_boot_ns']) is not int or decision['expires_boot_ns'] <= 0
                or not re.fullmatch('[0-9a-f]{32}', decision['nonce'])):
            raise ValueError('exact operator decision required')
        if decision['expires_boot_ns'] <= boot_time_ns():
            raise ValueError('effect held: lease_expired')
        expected = contracts(proposal, observed, decision)
        if any(value[key] != expected[key] for key in expected):
            raise ValueError('exact intent/binding/enforcement/epoch/lease mismatch')
        lease = ActionLease.from_dict(value['lease'])
        try:
            store.read('consumed', digest)
            used = 1
        except FileNotFoundError:
            used = 0
        evaluated = evaluate_action_lease(lease=lease, checked_at=now.isoformat(),
            current_authority_epoch_sha256=expected['authority_epoch']['authority_epoch_sha256'], uses_consumed=used)
        if not evaluated.usable:
            raise ValueError('effect held: ' + evaluated.reason)
        # Consume and sync BEFORE the effect. A crash/failure may leave an
        # uncompleted note, but never reopens this lease for a second effect.
        store.publish('consumed', digest, encode({'schema_version': 'phios.linux-proof-consumption.v1',
            'approval_sha256': digest, 'lease_sha256': lease.action_lease_sha256, 'consumed_at': now.isoformat(),
            'boot_id': observed['boot_id'], 'effect_performed': False}))
        store.publish('notes', digest, TEXT.encode())
        actual = store.read('notes', digest)  # Independent descriptor/readback.
        if actual != TEXT.encode():
            raise ValueError('post-effect content verification failed; lease remains consumed')
        receipt = {'schema_version': 'phios.linux-proof-receipt.v1', 'approval_sha256': digest,
            'decision_sha256': sha(decision), 'binding_sha256': sha(value['binding']),
            'lease_sha256': lease.action_lease_sha256, 'source_commit': observed['source_commit'],
            'boot_id': observed['boot_id'], 'principal_uid': 1001, 'operator_uid': 1000,
            'note_sha256': hashlib.sha256(actual).hexdigest(), 'note_bytes': len(actual),
            'post_effect_verified': True, 'effect_performed': True, 'execution_authority': False,
            'authority_replayable': False, 'release_ready': False}
        store.publish('receipts', digest, encode(receipt))
        return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('inspect')
    commands.add_parser('approve')
    run = commands.add_parser('execute')
    run.add_argument('--approval', required=True)
    args = parser.parse_args()
    try:
        observed = context()
        if args.command == 'execute':
            store = Store(STORE)
            try:
                print(json.dumps(execute(store, args.approval, observed, datetime.now(UTC)), indent=2))
            finally:
                store.close()
        else:
            proposal = capture(observed, datetime.now(UTC))
            if args.command == 'inspect':
                print(json.dumps({'observation': observed, 'proposal': proposal, 'execution_authority': False}, indent=2))
            else:
                return 0 if approve(proposal, observed, input_stream=sys.stdin, output_stream=sys.stdout) else 2
        return 0
    except (OSError, ValueError, TypeError, KeyError, EOFError) as exc:
        print('Linux proof held: ' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
