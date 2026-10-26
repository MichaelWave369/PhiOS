# PhiOS sovereignty exit test v0.1

This is a deliberately narrow, executable first rung. The test packer has **no dependency on PhiOS**, uses only Python 3.11+ standard library, and has no network functionality.

## Use

```bash
python scripts/sovereignty_exit_v01.py pack --source /path/to/my-data --output /path/to/backup.zip
python scripts/sovereignty_exit_v01.py verify --bundle /path/to/backup.zip
python scripts/sovereignty_exit_v01.py unpack --bundle /path/to/backup.zip --output /path/to/restored-data
```

The source must be a directory. Files are packed as `data/<relative-path>` with a root `manifest.json` recording SHA-256 and byte size. Archives and manifests are simple open formats. Export and restore reject symbolic links, pre-existing output paths, unsafe ZIP paths, duplicates, oversized archives and checksum mismatches. Empty directories are not preserved in v0.1.

**Archives are unencrypted.** Store them as carefully as the original data. Never collect secrets just to pass an exit test.

## CI scope

`python -m unittest discover -s tests -p 'test_sovereignty_exit_v01.py' -v`

CI checks sample export/verify/restore, tampering, traversal, duplicate entries, and symlinks. The tests run locally without a network request. No CI green check should be presented as proof that PhiOS itself is network-independent. The full exit test additionally requires application-state adapters, fresh-host trials, true network-denied OS tests, key revocation, user-facing restore exercises, and signed reproducible evidence.

## Future rungs

- **R2:** Real PhiShell/GitPorch user-data export adapters and exact state inventory.
- **R3:** PhiARK offline content manifests and licensed distribution checks.
- **R4:** SuperPhiVessel memory/model-provider portability, no cloud lock.
- **R5:** PhiKeyhole revoke/recovery ceremony with zero secret exposure.
- **R6:** Disconnected fresh-install/boot lab, restore on non-Phi host, and independent attestation.

Reviewers must distinguish a manual checklist from evidence. Exporting files does not establish their semantic completeness.
