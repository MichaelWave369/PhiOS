# Phi Independence R07-A — private field qualification

Status: **UNVERIFIED**. This is a review preparation tool, not a certification
issuer. It complements the [Sovereignty Contract](../SOVEREIGNTY_CONTRACT.md);
even nine correlated gates earn only PARTIAL, never EXIT-VERIFIED.

## Scope

One synthetic local-workspace campaign across PhiOS, PhiBuddy, Agentora,
Ollama and two operator-controlled PCs. No real conversation content needed.
Use disposable databases, one synthetic conversation export, one harmless UI
candidate and one fixed mesh task. Never disconnect during critical work.
Prepare dependencies, source and models beforehand. Retain independent recovery
media. Keep evidence private, on encrypted storage with restricted ACLs,
outside Git and cloud-sync folders. Do not copy private evidence to public CI.

Reviewed implementation baselines before R07-A (record actual tested SHAs instead):
PhiOS da87f8fe7d26036a61a97aca6eebc2afc2a747c3;
PhiBuddy 5832141379174938bdd4d5487c698e228ccb9537;
Agentora 49166bb5365975d68df744678f91a837b0da48f2.

## Nine gates, in order

| Gate | Procedure | Required files |
| --- | --- | --- |
| wan_denied | Independently deny WAN on both hosts, retain LAN and loopback, observe failed external connectivity and absence of cloud credentials in test environment | wan-observation.json |
| readiness | R01 real installed local model marker | r01.json |
| vault_restore | R02 import, verify, restore on fresh compatible environment, independently hash original and restored bytes and read without account | vault-verify.json, vault-restore.json, restore-observation.json |
| inference | R03 complete comparison of at least two installed non-cloud model tags, each with at least one correct task | r03.json |
| bridge | R04-A/B manually select synthetic PhiBuddy completed event and approve local review | r04b.json |
| forge | R05-B proposal, separate R05-A exact plan approval and offline Docker build | r05b.json, r05a-plan.json, r05a.json |
| mesh | R06-A pinned challenge and R06-B correct synthetic inference; stop listener, reopen same intact journal, query status and compare | r06a.json, r06b-submit.json, r06b-restart.json |
| cold_recovery | Cold restart both PCs, read archive and query original mesh journal; observe no duplicate admission | cold-observation.json |
| exit_rights | Document scope completeness, exercise alternate model, revoke old optional credentials, read and restore independently | exit-observation.json |

Follow the original rung guides, including explicit approvals and private trust
setup. Capture stdout JSON from each named command to the named file (PowerShell
7 UTF-8 or other UTF-8 shell; avoid Windows PowerShell 5 UTF-16). Save R05-A plan
wrapper exactly as emitted. Do not include full original exports in this evidence
directory; independent byte comparison happens separately. Preserve failure
evidence privately; mark failed gates FAIL, unattempted gates NOT_RUN.
Never manufacture observations or overwrite a failed run to simulate success.

Manual observation files use exact fields (example shape, not evidence):

```json
{
  "schema": "phios.field-observation.v1",
  "observed_utc": "REPLACE_WITH_ACTUAL_ISO_UTC",
  "observer": "REPLACE_WITH_OBSERVER_LABEL",
  "method": "Describe actual procedure and result without secrets",
  "checks": {
    "both_hosts_wan_denied": false,
    "lan_and_loopback_available": false,
    "no_cloud_credentials_used": false,
    "negative_external_probe": false
  }
}
```

Use the exact MANUAL keys in the script for each other observation. The restore
observation additionally requires original_sha256 and restored_sha256. False
or missing checks cannot correlate. Record host OS, runtime versions, model tags,
source commit IDs and observation times. No names, tokens, paths or private
transcripts need to be published.

## Review

Create a private directory first. From PhiOS root (PowerShell 7):

```powershell
python scripts/phi_independence_r07a.py template > D:/PhiVault/field/campaign.json
python scripts/phi_independence_r07a.py inventory --directory D:/PhiVault/field
```

Fill actual manifest metadata and each artifact SHA-256 from inventory after
reviewing that artifact; explicitly record OBSERVED_PASS only for gates genuinely
observed. Then:

```powershell
python scripts/phi_independence_r07a.py review --directory D:/PhiVault/field
```

HELD means missing, failed, inconsistent or unobserved evidence; exit 1.
REVIEW_READY_NOT_CERTIFIED means nine self-reported evidence sets correlate; exit
0 means review preparation only. Reports never grant authority or certification.
The verifier reads a fixed set of bounded JSON files (2 MiB each), checks file
hashes, selected receipt semantics and cross-component hashes, and emits no raw
artifact contents. It does not write files or access the network.

The manifest and receipts are mutable self-reports. Hashes detect inconsistent
copies, not forged inputs. This does not verify source commit provenance, actual
hardware, network policy, independent reviewer identity, freshness relative to
one campaign, or that manual observations really occurred. It does not exercise
models, restore files, verify source-code behavior, inspect credentials, measure
GPU usage, or establish scope completeness. Fixed file names do not replace
filesystem ACLs. Trusted local directory required; no adversarial file race
protection. An independent reviewer must reproduce the tests and apply the full
Sovereignty Contract separately. A synthetic pilot cannot certify all app data,
full OS recovery, account portability or commercial-provider replacement parity.

Tests: pytest -q tests/test_phi_independence_r07a.py.
No field measurements are included. The next step is actual workstation
qualification, followed by a separately reviewed evidence/reporting policy.
