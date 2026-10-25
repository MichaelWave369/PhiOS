# PhiOS foundation R1.2: one honest offline integration observation

**Status:** native, read-only, operator-run report. No system installation, verified full-stack offline deployment, or PhiKernel native boot.

This joins the currently separate PhiOS adapters and their existing trust requirements without silently bridging permissions:

- **GitPorch HomeNode:** calls `phios.network.homenode.select_mode`; OFFLINE and PUBLIC never connect or inspect credentials, LOCAL opts into the existing pinned HTTPS R1-H6 capability handshake and its separately provisioned secrets. Even verified LOCAL means the limited GitPorch gateway capability contract answered, not that Git operations or backup restore work.
- **PhiARK Knowledge Vault:** calls `phios.apps.phiark_bridge.observe_phiark` only when the operator supplies an absolute data directory. Hashes local catalog documents, never imports/downloads them or starts the reader. An optional explicitly selected Kiwix hash recheck can be expensive. The optional loopback PhiARK HTTP probe additionally requires LOCAL mode. Hash matching is not content safety or redistribution approval.
- **Infinite Porch:** retains the separate R1.1 manual PhiShell Home health button. The combined CLI **never requests Porch credentials, calls its API, connects peers, invokes models or reports node identity as verified**.
- **PhiOS/PhiKernel:** no app install, runtime launch, boot claim, OS effect, permission grant, network configuration, git push or model inference.

## Operator commands

```sh
# Safe: no credentials, host network calls, or local disk inventory
phi-foundation status

# Safe: selects public mode without testing whether internet actually works
phi-foundation status --mode public

# Checks only the operator-supplied vault document catalog hashes, no web access
phi-foundation status --mode offline --phiark-data-root /absolute/PhiARKVault

# Explicit authenticated GitPorch LOCAL gateway handshake.
# Provision PHIOS_HOMENODE_* from docs/PHIOS_GITPORCH_HOMENODE_R1H6.md
phi-foundation status --mode local --phiark-data-root /absolute/PhiARKVault

# Opt-in checks for costly existing local ZIM bytes or loopback PhiARK HTTP status
phi-foundation status --mode local --phiark-data-root /absolute/PhiARKVault --verify-kiwix --probe-phiark-loopback
```

The output excludes the PhiARK data root, private file paths, HomeNode token, TLS certificate, raw errors and document contents. It returns `UNVERIFIED`, `PARTIAL_EVIDENCE`, or `BLOCKED`, **never `OFFLINE_READY`**; `acceptance.offlineReady` is always false. A successful command exit only proves it generated an observation, not that services work.

## Next real field acceptance, not claimed by this PR

On the operator's independently configured hardware, run a controlled, reversible test with WAN physically disconnected. Verify *all* of: (1) boot and login PhiOS; (2) access GitPorch repository; (3) commit and read a branch; (4) restore a separate mirror and check objects/refs; (5) build from locally cached dependencies; (6) read an actual PhiARK document; (7) launch an independently vetted genuine `kiwix-serve` binary on a SHA-verified real ZIM and search it; (8) manually authenticate Porch and run a preinstalled local model with a scoped grant; (9) stop services and reboot cleanly. Record host hardware, OS, exact source commits, SHA-256 of recovered bytes, operator permissions, WAN state and failures.

The existing PhiARK sandbox and GitPorch network constraints still apply. Never put LAN credentials in browser JavaScript, private archive content in a public Pages site, or agent execution behind a mere link. A machine claiming a correct health status could be spoofed and may not be the intended daemon.

## Verification

```sh
python -m pytest tests/test_foundation_status_r12.py -q
ruff check phios/foundation_status.py phios/foundation_cli.py tests/test_foundation_status_r12.py
mypy phios/foundation_status.py phios/foundation_cli.py --ignore-missing-imports
```

Existing full CI continues to own actual qualification. This report does not replace the independent PhiARK, GitPorch, Porch or OS image tests.

**Ledger Above Ego.**
