# Bounded installed Linux proof workflow

This candidate demonstrates one harmless real Linux filesystem effect. It
creates one fixed 57-byte proof note inside an independent protected store.
It is not a desktop automation API, AI agent, shell executor or generic file
writer. The existing Ghost Walk browser decision/binding/lease routes remain
held. Public EffectIntent, EnforcementProfile, AuthorityEpoch and ActionLease
contracts are reused without modifying private PhiKernel/TIEKAT internals.

## Operator sequence

Use an experimental installed PhiOS system, with the installer-created UID
1000 account and its ordinary password-authenticated sudo administration.
The public volatile live account cannot run this broker. There is no new
NOPASSWD rule and no unattended approval flag.

```bash
sudo systemctl start phios-proof-proposer.service
sudo phios-linux-proof inspect
sudo phios-linux-proof approve
sudo phios-linux-proof execute --approval APPROVAL_SHA256
```

Replace `APPROVAL_SHA256` with the exact identity returned by approval. Review
the captured proposal, actual source/boot identity, fixed note hash, protected
store, single use and 60-second lifetime. Approval requires typing the complete
`APPROVE SHA256` review phrase. Anything else cancels before creating an
approval, binding, lease or effect. The proposal and actual OS identity are
checked again after review. Run the separately requested effect within 60
seconds. If it expires, make and review a new approval; do not edit records.

The static one-shot proposer runs as UID 1001 `phios-agent`, with a nologin
account, no sudo, no capabilities, no privilege escalation, a private network,
protected home/system paths and one writable private proposal directory. It
is not enabled at boot. It observes public source/boot identity and writes an
untrusted, zero-authority proposal for the fixed note. A browser, pseudo-TTY
or agent-owned proposal is never approval. A malicious process running as the
installed administrator, cached administrator sudo or arbitrary root remains
outside this principal-separation boundary; TTY access alone is not human
authentication. Sudo/PAM separates the installed administrator from the
agent principal, rather than authenticating an AI judgment.

The root-owned Python-isolated broker accepts only that fixed proposal path,
principal, capability and text. It opens bounded regular singly linked input
without following links and captures bytes before review. It binds the actual
source and boot to the decision, exact intent, enforcement profile, capability
binding and canonical single-use ActionLease. The note destination cannot be
supplied by the agent or caller. Root-owned directory descriptors, exclusive
creation and fixed bytes constrain this effect; signed administrator code is
trusted, and a compromised root is not sandboxed by these checks.

## Consumption, verification and recovery

`/.snapshots/phios-linux-proof` stores immutable SHA-256-named approvals,
consumption records, notes and post-effect receipts. It is in the independent
`@snapshots` subvolume, outside `@root` rollback snapshots and user data-only
backups. Records are root-owned; directories are created 0700 and files 0600.
The broker flushes the consumption record before creating a note. A failure or
interruption may leave a consumed lease and incomplete effect requiring review;
it never silently makes that lease reusable. It flushes the note, independently
opens and verifies its exact bytes, then flushes a separate linked receipt.
No executable authority follows from viewing a receipt.

Both wall-clock validity and Linux `CLOCK_BOOTTIME` expiry are enforced, including
time spent suspended. A new boot or source identity invalidates old approvals.
OS recovery preserves the independent ledger; it cannot reinstate a rolled-back
lease. Canonical user data and its zero-authority history stay separate. This
extends the maintenance boundary only for this fixed broker store; custom
authority stores still need an explicit reviewed recovery procedure. Losing
the disk loses this ledger, and copying files is not authority enrollment.

Twenty-one focused tests passed for exact binding/readback, cancellation, changed
review, scope/principal/source/boot denial, expiry including clock rollback,
replay, corrupt/linked records, symlink redirection and durable consumption
failure. The external installed-VM fixture uses ordinary sudo/PAM, the actual
UID 1001 service and production commands. It must prove agent store/broker
denial, cancellation, one verified note, replay and real 60-second expiry, then
historical-authority refusal after restart and matched OS recovery. End-to-end
VM qualification passed on both the separate signed-update QA image and the
exact normal image in runs 36812104411 and 36812104386. The normal receipt is
`docs/os/evidence/normal-installed-5145b4da.json`; it records actual UID/PAM,
effect/readback, refusals and three distinct installed boots including matched
recovery. Physical hardware and final release readiness remain unqualified.
