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

Before any supported installed beta, prove all of the following on the exact
image: offline root/EFI checkpoint; valid signed package installation; missing,
wrong-key, expired and tampered update refusal; interrupted package transaction;
unbootable root or initramfs; recovery using the live media; normal password
reauthentication; preservation and verification of canonical user data; inactive
historical authority; and a second disk-only boot. Root snapshots alone do not
back up `/home`, and same-disk checkpoints do not survive loss of that disk.
Maintain a verified data-only backup on separately owned storage.

Current status: signature/transition verification is implemented as a candidate.
Package application, matched root/EFI recovery and their VM failure evidence are
pending. `whole_os_rollback_available` remains false. Do not substitute the
application platform's rollback receipt for these OS gates.
