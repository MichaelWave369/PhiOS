# Operation Phi Independence — Rung 01

Status: experimental, UNVERIFIED. Governed by [Sovereignty Contract](../SOVEREIGNTY_CONTRACT.md).
Cloud services remain optional; no provider is presumed interchangeable at equal quality.

## First milestone: local readiness

From the PhiOS root with Python 3.11+:

```powershell
python scripts/independence_r01.py
ollama list
```

Inventory only checks PATH visibility; it does not execute discovered tools, inspect files,
read credentials, or make network calls. No private paths are printed.
A missing tool does not mean it is uninstalled. Exit 0 means the report was emitted,
not that the workstation is ready.

For the optional inference smoke, first install the desired model while connected,
start Ollama, and independently block external internet access while retaining IPv4
loopback. Confirm the exact locally installed tag with Ollama. Do not use cloud-backed
models. Substitute that exact tag below:

```powershell
python scripts/independence_r01.py --model qwen3:4b --confirm-offline
```

The only request is a fixed synthetic marker prompt to 127.0.0.1:11434.
The tool does not pull models, follow redirects, use proxies or retry. It reports a
bounded response check, not model quality, GPU residency, server identity, or network
isolation. A loopback daemon could forward traffic; operator-declared offline is not
independent proof. An exact marker failure may be formatting rather than lack of inference.
Timeout is a socket operation timeout, not a hard wall-clock deadline.
Failure exits 1; invalid arguments exit 2. Reports remain UNVERIFIED even on marker success.

## Parallel preservation milestone

Request provider exports manually; keep raw exports private and encrypted at rest.
Never upload conversation exports, credentials, personal paths, or private repository
content to public CI or Git. Preserve original message identifiers, relationships, dates,
and checksums where available; keep derived summaries separate. Use existing PhiOS
sovereignty exit utilities only on an explicitly selected scope; their archives are
unencrypted and are not complete application backups. Restore and verify independently.

## Subsequent rungs (proposed, not implemented here)

1. Private archive format and non-destructive import with synthetic fixtures.
2. Measured model benchmarks and local-first routing.
3. Versioned PhiBuddy/Agentora handoff with explicit consent, scoped context and no
   inherited execution authority.
4. Approval-gated development in isolated worktrees; no automatic push/merge.
5. Optional second node with authentication and least privilege.
6. Network-denied end-to-end execution, cold restart, export and independent restore.

No new repositories or mandatory cloud integrations. PhiGenesis remains experimental
and is not a dependency of the production baseline. No existing service behavior changes.
Test with `pytest -q tests/test_independence_r01.py`.
