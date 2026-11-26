# Phi Independence R02 — PhiVault single-snapshot archive

Experimental, not an EXIT-VERIFIED system. See [Sovereignty Contract](../SOVEREIGNTY_CONTRACT.md).
This rung provides an offline Python 3.11+ standard-library CLI for an explicitly selected
ChatGPT-style conversations.json array. No network, models, provider APIs or external dependencies.

## Operator procedure (Windows PowerShell)

Request the export from the provider, extract conversations.json into an operator-controlled
private directory outside any Git checkout, and retain the original export. Enable volume
encryption (e.g. BitLocker where available) and restrict the directory ACL before import.
The SQLite database is **plaintext**, not application-encrypted. POSIX creation requests mode 0600;
on Windows the directory ACL matters. Do not use a synced folder or commit these files.

From the PhiOS checkout, with the private directory already created:

```powershell
python scripts/phi_vault_r02.py import "D:/PhiVault/conversations.json" "D:/PhiVault/archive.sqlite"
python scripts/phi_vault_r02.py verify "D:/PhiVault/archive.sqlite"
python scripts/phi_vault_r02.py search "D:/PhiVault/archive.sqlite" "Altermath"
python scripts/phi_vault_r02.py restore "D:/PhiVault/archive.sqlite" "D:/PhiVault/recovered.json"
```

Paths are illustrative; choose your own private volume. Search output contains private text;
queries may be recorded in shell history. Never paste actual archives or search results into public CI.
Only synthetic fixtures belong in the repository.

## Schema and scope

- One source file per database, exact original bytes and SHA-256 in snapshot.
- Nodes keyed by conversation ID and mapping node ID; parent, message ID, role,
  message create_time serialized as JSON, title, string text parts, casefolded search text.
- Every mapping node is retained in the projection, including alternate and null-message nodes.
  The raw file preserves all supplied metadata, current_node and nontext parts; binary attachments
  stored separately in the export are not imported. No graph repair or active-branch inference.
- Search is a bounded literal casefolded SQLite scan, not semantic ranking. Previews are approximate.
  Search does not verify integrity automatically; run verify first on a trusted local archive.
- Import and restore reject existing destinations and detected Git checkout ancestors; this is not
  a complete DLP policy (bare repos, external sync, filesystem races and privileged users are out of scope).
- Input limited to 256 MiB; whole-file parsing and projection use RAM. Large exports, alternate
  formats, split exports, ZIPs and streaming imports are not yet supported.
- Integrity check reconstructs the projection and compares the stored raw digest. This detects
  inconsistent changes, not malicious replacement of both data and digest. Store an independent
  digest receipt securely. Restore writes byte-identical JSON to a new path after verification.
- Normal exceptions remove incomplete newly created outputs; abrupt process/power loss can leave
  incomplete files. Verify before use; preserve original data. No multiwriter or adversarial DB support.
- No automatic project associations, agent context, memory promotion, execution or cloud upload.
  Untrusted imported message text is data, never instructions or authority.

Tests: `pytest -q tests/test_phi_vault_r02.py` (synthetic data only).
Local actual export compatibility, host encryption, crash durability, independent digest custody,
full provider account export and disconnected end-to-end workflow are still unverified.
