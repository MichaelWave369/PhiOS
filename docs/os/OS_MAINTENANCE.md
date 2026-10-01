# Experimental whole-OS maintenance

The candidate beta strategy is conventional signed Arch package transitions,
with an offline Btrfs root checkpoint and a matching copy of the entire EFI
system partition. This is not an atomic or immutable OS. Application rollback
does not restore Linux, initramfs, system configuration or the bootloader.

## Signed transition intake

`phios-update-verify --bundle /absolute/path/to/offline-bundle` verifies bytes
only. It cannot install packages, switch a boot entry, promote an adapter or
create execution authority. The normal image intentionally ships no enrolled
maintainer signing key. Verification holds until the operator independently
authenticates and installs a public key and full fingerprint. No test key is a
release identity, and no signing private key belongs in this repository/image.

The volatile live account has no general root shell. Enroll through the
root-owned narrow command instead, using the full independently authenticated
fingerprint:

```bash
sudo phios-update-enroll --public-key /absolute/current-public-key.gpg --fingerprint FULL_UPPERCASE_FINGERPRINT --plan
sudo phios-update-enroll --public-key /absolute/current-public-key.gpg --fingerprint FULL_UPPERCASE_FINGERPRINT
```

The placeholders must be replaced. Review the exact captured public-key hash,
full fingerprint, current trust hashes and source environment, then type
`ENROLL /etc/phios SHA256`. Missing/changed identity, multiple primary keys,
secret-key material, expired/revoked keys or cancellation do not enroll trust.
The tool captures the input once, exports only the selected public key,
rechecks validity/current trust after review, and flushes protected key/policy
files before readback. It has no unattended bypass or network retrieval.
Terminal access is not proof of human identity; an administrator remains
responsible for independent fingerprint authentication. Signing-trust rotation
is an explicit local administration action, not an adapter promotion.

An installed administrator can also perform manual Linux administration:
create root-owned `/etc/phios`
without group/other write access, install the independently authenticated
exported public key at `/etc/phios/os-update-keyring.gpg` (root:root, 0644), and
install `/etc/phios/os-update-trust.json` (root:root, 0644):

```json
{
  "schema_version": "phios.os-update-trust.v1",
  "primary_fingerprint": "REPLACE_WITH_THE_INDEPENDENTLY_AUTHENTICATED_FULL_UPPERCASE_FINGERPRINT",
  "channel": "experimental"
}
```

The placeholder is deliberately invalid. Authenticate the fingerprint through
a separately trusted maintainer channel; downloading a key beside its own
signature does not establish trust. Key rotation/revocation requires an explicit
administrator replacement of this trust policy/keyring. No keyserver, network
retrieval, automatic enrollment or web-of-trust inference is used. GnuPG's
machine-readable status must identify the pinned primary key, SHA-256/384/512,
and an unexpired, nonrevoked key/signature. GPGV alone would not provide the
required expiry/revocation checks.

The offline bundle contains `manifest.json`, its detached `.sig`, and each
listed package plus a detached `.sig`. Every signature must chain to the pinned
maintainer primary key. Upstream package provenance still belongs in release
build evidence; a signed release transition is not a source/license audit.
Inputs are singly linked bounded regular files, opened without following links,
copied into a private temporary directory, then hashed and signature-checked.
Only captured bytes can reach a later package consumer. Replacing the supplied
bundle after verification cannot replace those bytes.

The strict `phios.os-package-update.v1` manifest requires exactly these fields:

| Field | Requirement |
| --- | --- |
| `schema_version`, `channel`, `architecture` | Exact schema, `experimental`, `x86_64` |
| `from_source_commit`, `source_commit` | Exact base and target 40-character commit identities |
| `base_sequence`, `sequence` | Installed generation and exactly its successor; no replay |
| `created_at`, `expires_at` | Timezone-aware validity window, at most 90 days; accurate clock required |
| `arch_snapshot` | Valid, fixed `YYYY/MM/DD` Arch archive date |
| `state_schemas` | Exactly `{"memory":1,"data_backup":"phios.data-backup.v1"}`; unknown migrations held |
| `base_packages`, `target_packages` | Complete name/version inventories; exact base; removals held |
| `packages` | Unique name/version/filename/SHA-256/size records for every changed or added package |

Each package record has exactly `name`, `version`, `filename`, `sha256`, `size`.
The inventory bound is 20,000 packages; the transition bound is 2,000 archives,
2 GiB per archive and 16 GiB total. Archives use `.pkg.tar.zst` or `.pkg.tar.xz`.
The source, installed package inventory and persisted generation are checked
again for every verification. Initial installation has generation zero.

Signature verification proves authenticated bytes and a declared complete
transition. Pacman must still validate package format, dependencies and the
resulting full inventory in a prepared system root. Unsupported schema changes,
data migrations, removals or dependency conflicts must hold the update. The
verifier does not claim package installation or boot compatibility.

## Recovery qualification gate

`sudo phios-os-recover checkpoint --disk /dev/REPLACE --plan` performs a
read-only probe from the PhiOS UEFI live image. Supply the canonical device
path of the already installed, offline disk. It requires the installer's exact
GPT/1-GiB-ESP/single-device-Btrfs layout, stable serial/WWN, filesystem UUIDs,
and a matching installation receipt. Mounted disks, swap, holders, unexpected
filesystems, extra partitions and noncanonical aliases are refused. A Btrfs
read-only probe uses `ro,rescue=nologreplay,subvolid=5` to disable log replay
([Btrfs mount documentation](https://btrfs.readthedocs.io/en/latest/btrfs-man5.html#mount-options)). No target write occurs for `--plan` or
cancellation. The tool exposes no unattended confirmation bypass.

Run the command without `--plan`, review the complete disk/source/boot-file
hash plan, and type the exact `CHECKPOINT /dev/... SHA256` phrase. The checkpoint
ID and metadata are stored in `@snapshots/recovery/<id>/checkpoint.json`.
Each checkpoint has an immutable root snapshot, its Btrfs UUID, SHA-256/length
inventory of the complete EFI contents, and a read-only home snapshot retained
for forensic review. The home snapshot is never activated by OS recovery.

To restore, boot the same live media and use:

```bash
sudo phios-os-recover restore --disk /dev/REPLACE --generation CHECKPOINT_ID --plan
sudo phios-os-recover restore --disk /dev/REPLACE --generation CHECKPOINT_ID
```

The placeholder paths/ID must be replaced after reviewing the actual probe.
The exact `RESTORE /dev/... SHA256` phrase binds the selected disk, immutable
root snapshot, source and matching EFI hashes. Current `/home` and `/var/log`
stay in their own subvolumes. Canonical memory schema/integrity/content hashes
and published zero-authority memory receipts are checked. Unknown schemas,
incomplete database journals, enabled memory configuration, active decisions,
bindings, leases, claims or other unknown spine state hold recovery before
activation. Use verified data-only recovery and explicitly revalidate such
state first; the tool does not guess how to invalidate a custom authority root.
Only the packaged state path and legacy `~/.phios` are covered by this preview.

Recovery clones the immutable root into a fresh writable subvolume, retains
the failed root under a unique `@failed-...` name and preserves the prior EFI
contents beside a durable transaction journal. It then switches the root and
copies/verifies the matched EFI files. Root and EFI changes are **not atomic**.
An interruption between them requires another live-media restore of the same
checkpoint; never reboot merely because one step completed. Failed roots and
transaction evidence are never deleted automatically. Cleanup failures hold
the operation and identify remaining mounts. Filesystem/hardware corruption
that prevents mounting needs a separate storage recovery procedure.

Restoration discards old system/EFI entropy seeds, removes rolled-back update
trust files so an earlier signing policy cannot be silently reinstated, and
increments the highest observed update generation rather than replaying its
counter. The root generation is paired with a root-owned counter in
`@snapshots/os-update-counter.json`, outside the rollback snapshots. This counter
is flushed before root activation. A missing root after an interrupted rename
therefore cannot reset an already consumed update sequence. An inconsistent
root/counter pair holds updates for explicit live recovery. Re-enroll the independently authenticated current public key before
subsequent updates. Normal password/PAM login remains required. Same-user
terminal access is not proof of human identity and arbitrary administrator
processes remain outside PhiOS's narrow governed-effect boundary.

Before any supported installed beta, prove all of the following on the exact
image: offline root/EFI checkpoint; valid signed package installation; missing,
wrong-key, expired and tampered update refusal; interrupted package transaction;
unbootable root or initramfs; recovery using the live media; normal password
reauthentication; preservation and verification of canonical user data; inactive
historical authority; and a second disk-only boot. Root snapshots alone do not
back up `/home`, and same-disk checkpoints do not survive loss of that disk.
Maintain a verified data-only backup on separately owned storage.

## Offline signed package application

Boot PhiOS UEFI live media, keep the installed disk offline, and enroll the
independently authenticated current public key into the **live** environment.
The updater does not inherit trust from the disk it is about to change.

```bash
sudo phios-os-update --disk /dev/REPLACE --bundle /absolute/offline-bundle --plan
sudo phios-os-update --disk /dev/REPLACE --bundle /absolute/offline-bundle
```

The read-only plan binds the explicit disk, exact current source, complete
package inventory, independent counter, entire EFI hash inventory, signed
manifest digest, pinned signer and fresh checkpoint ID. Review and type the
exact `UPDATE /dev/... SHA256` phrase. Cancellation changes no target files.
Trust, validity and every captured package signature are checked again after
confirmation. Downgrades and package removals require recovery rather than an
update. Accurate time and enough live temporary storage for the bounded bundle
are prerequisites; insufficient space holds the operation.

The command first creates a matched recovery checkpoint, then prepares a
writable `@update-...` root. Pacman requires signatures for each captured
archive, with only the enrolled keyring and no remote repositories. Package
format/dependency failures or an incorrect complete target inventory leave
the active root and EFI unchanged. The staged root must carry exactly the
signed PhiOS source identity. Kernel/initramfs/EFI preparation occurs against
a private copy of `/boot`; only after verification does the tool retain the
prior root, activate the new root and copy/verify matching EFI contents.
No user-home snapshot or historical authorization is activated.

Signed package scripts run with administrator privileges. The staging chroot
is not a security sandbox against a malicious signer or administrator. A
maintainer must qualify the actual complete package transition, its hooks,
state compatibility, licenses and boot behavior before signing it.

The update journal lives beside its exact checkpoint as
`@snapshots/recovery/<id>/update-transaction.json`. Failed stage roots,
previous roots and transaction evidence remain for review. An interruption
before activation leaves the active root in place. Root/EFI activation remains
non-atomic: if interrupted during that switch, boot live media and explicitly
restore the journal's checkpoint. Success reports activation only; a disk-only
boot is still required to qualify the target. Keep a separate verified data
backup and the matching live recovery image.

CI uses only a newly created named 32-GiB VM disk, with no network, host disks
or shared folders. It generates ephemeral signing keys in live RAM and builds
real packages with makepkg. The new fixture tests invalid/missing/wrong-key/
expired/replayed signatures or manifests, cancellation, a valid added package,
a real dependency failure, abrupt VM termination during a pacman installation
hook, unchanged active root/EFI after that interruption, deliberate boot
corruption, matched live-media recovery and normal password/PAM desktop boots.
Those test packages and credentials are excluded from normal images and
installations. A successful fixture qualifies that bounded transition only;
it does not qualify arbitrary kernel upgrades, real hardware or a release key.

Current status: the bounded end-to-end VM qualification passed in run
[36805999628](https://github.com/MichaelWave369/PhiOS/actions/runs/36805999628),
including enrollment, successful signed addition, refusal cases, actual
interrupted installation, a kernel boot failure, matched live recovery and
three authenticated disk-only desktop boots. Exact source/ISO hashes and
evidence digests are in `docs/os/evidence/recovery-29def30a.json`. The QA image
contains disposable fixtures and ephemeral signing identity; this evidence
does not qualify another artifact, arbitrary upgrades or hardware.
`whole_os_rollback_available` remains false for the supported product.
See IMPLEMENTATION_STATUS.md and RELEASE_CONTRACT.md for remaining gates.
