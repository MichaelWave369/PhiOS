# Durable state and data recovery

The packaged session selects `PHIOS_STATE_ROOT=$HOME/.local/state/phios`.
Memory uses `memory/canonical.sqlite3`, Spine uses `spine-v0.1/ledger`, and
Curiosity uses `curiosity`. Memory configuration is
`$XDG_CONFIG_HOME/phios/memory.json` (normally `~/.config/phios/memory.json`).
CLI processes inherit the same root. Outside the session, the existing
`~/.phios` location remains the legacy default. A relative or empty state-root
environment is an error. Legacy data is copied through backup/restore into a
new root; it is never silently moved or enabled.

New files use mode 0600 and new directories 0700. Existing permissions are not
silently changed. Files must be caller-owned, regular, singly linked and not
writable by other users. POSIX traversal refuses symlinks at every ancestor.
These checks do not authenticate a human, isolate a malicious same-user process,
attest Windows ACLs or encrypt data.

## Acknowledged writes

Spine, Mandala and Curiosity JSONL writers hold an exclusive process lock,
validate history, write a complete record and sync file/directory before
returning. Readers hold a shared lock and reject malformed, duplicate-key,
non-finite, oversize and incomplete records. The per-record bound is 16 MiB.
Reading never repairs or discards evidence. A caught failed write truncates only
that unacknowledged append; a killed writer can leave an incomplete tail that
blocks normal reads and later writes.

Memory transactions reserve the SQLite writer before reading idempotency keys
or revision heads, use FULL synchronization and close each connection. Outbox
publication is idempotent under the ledger lock. Publishing an older revision
cannot mark a newer pending revision readable. Binding, lease and run claim
files are synced before an executor can be entered. No permission or adapter
promotion follows from these changes.

## Backup and restore

Backups are private, unencrypted directories with a versioned manifest and
exact file hashes. Keep them under operator-controlled storage. The manifest
establishes internal integrity, not external authenticity. SQLite's online
backup API captures canonical database state; ledger capture can span a later
moment, recorded by the manifest's capture window.

```sh
phi-state backup --state-root "$PHIOS_STATE_ROOT" --output "$HOME/phios-backup-001"
phi-state verify "$HOME/phios-backup-001"
phi-state restore "$HOME/phios-backup-001" --new-state-root "$HOME/.local/state/phios-restored"
```

Both operations require a new destination, including refusal of an existing
empty directory. Restore verifies all file hashes, SQLite structure, canonical
record hashes and exact published memory receipts before creating output.
Unknown backup/database schemas are held without speculative migration.
Failure preserves partial output for review and returns a nonzero status.

| Data | Restore behavior |
| --- | --- |
| Canonical memory | New memory database; pending outbox stays pending |
| Published memory receipts | Exact receipts in the active Mandala ledger |
| Curiosity artifacts/pointers | Active data paths after zero-authority validation |
| Effect, approval, binding, lease and session history | `recovered-audit/`, outside active lookup paths |
| Claims, enabled configuration, credentials, caches and vector indexes | Excluded; no replay or enabling |

Stop the old session before selecting a restored root. Review a disabled memory
configuration before enabling readers or reconciling a pending memory outbox.
Rebuild derived indexes explicitly. Historical authority stays historical;
restore creates no active decision, binding, lease or executor.

## Interrupted final records

Normal backup holds an incomplete tail. This explicit option preserves a
verified complete prefix and all original bytes in a new backup:

```sh
phi-state backup --state-root "$PHIOS_STATE_ROOT" \
  --output "$HOME/phios-recovery-001" --preserve-incomplete-tail
phi-state verify "$HOME/phios-recovery-001"
```

The manifest lists incomplete audit files; original bytes are archived as
`.jsonl.bin` outside active paths. The original root remains untouched and held.
Malformed complete rows still fail. Published memory must retain its exact
valid receipt. After restore into a fresh root, a reviewed memory runtime can
reconcile pending canonical memory publication once. The option never resumes
an uncertain effect, infers a missing receipt or releases an old claim. Preserve
the original root and assess uncertain operations separately.

## Qualification limits

Focused tests cover contention, duplicate publication, disk-full interruption,
SIGKILL, backup/restore, hash tampering, authority injection and unknown schemas.
An installed-system lane must still prove no-ISO reboot and abrupt power-loss
recovery. Whole-OS recovery, hardware storage behavior, Windows custody and
agent isolation remain separate gates. A volatile live image loses its state
on reboot unless a verified backup has been copied off the image.

References: [Python SQLite APIs](https://docs.python.org/3/library/sqlite3.html),
[SQLite transactions](https://www.sqlite.org/lang_transaction.html), and
[SQLite synchronization](https://www.sqlite.org/pragma.html#pragma_synchronous).
