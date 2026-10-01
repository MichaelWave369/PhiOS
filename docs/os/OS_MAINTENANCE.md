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

Enrollment is manual Linux administration: create root-owned `/etc/phios`
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
read-only probe disables log replay. No target write occurs for `--plan` or
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
counter. Re-enroll the independently authenticated current public key before
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

Current status: signature/transition verification and offline root/EFI recovery
are implemented as candidates. Package application and VM recovery failure
evidence are pending. `whole_os_rollback_available` remains false. Do not substitute the
application platform's rollback receipt for these OS gates.
