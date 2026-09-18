# PhiOS Spine v0.1

PhiOS Spine v0.1 is the first runnable vertical slice of the modern PhiOS architecture.

## Contract

```text
Operator / PhiOS shell
        ↓
PhiVessel adapter (plans, never authorizes)
        ↓
Capability Registry
        ↓
Permission Gate (fail closed)
        ↓
Bounded Executor
        ↓
Artifact Store
        ↓
Reality Ledger receipt
```

The first capability is intentionally small: `commons.text_artifact`. It writes user-supplied text to the local PhiOS artifact store. Its value is not the text file; its value is proving the architecture end-to-end.

## Frozen v0.1 rules

1. **Capability is not authority.** Registration does not grant permission to execute.
2. **PhiVessel plans; PhiKernel-style policy authorizes.** The collaborator layer cannot self-grant permissions.
3. **Unknown capabilities do not execute.** The registry is explicit.
4. **Permissions fail closed.** Every requested permission must be explicitly granted for the invocation.
5. **Every attempt is receipted.** Successes, denials, and executor failures are appended to the Reality Ledger.
6. **Artifacts are content-addressable by receipt.** Successful artifacts carry a SHA-256 digest.
7. **Local first.** v0.1 uses no cloud service and requires no model provider.
8. **Linux remains the host OS.** PhiOS Spine is a supervisory/runtime layer and does not replace the Linux kernel.

## Run

After installing the PhiOS package from this branch:

```bash
phi-spine status
phi-spine list
```

A run without permission is denied and receipted:

```bash
phi-spine run commons.text_artifact \
  --input '{"text":"hello PhiOS","name":"hello"}'
```

Explicitly grant the required permission:

```bash
phi-spine --allow artifact.write run commons.text_artifact \
  --input '{"text":"hello PhiOS","name":"hello"}'
```

Inspect the ledger:

```bash
phi-spine ledger --limit 10
```

Default state is stored under:

```text
~/.phios/spine-v0.1/
├── artifacts/
└── ledger/
    └── receipts.jsonl
```

## What v0.1 deliberately does not do

- no automatic model-driven routing
- no shell command execution
- no arbitrary filesystem access
- no network access
- no EVIE publishing or monetization actions
- no background agents
- no privilege escalation
- no hidden permission inheritance

Those omissions are the point. The spine establishes custody before capability growth.

## Next integrations

The next safe additions are adapters, not rewrites:

- EVIE / Sovereign Shelf card definitions → capability manifests
- BrainC local model service → PhiVessel model adapter
- SOMA → perception capabilities
- Browsallax → research capabilities
- PhiOffice → document capabilities
- Reality Ledger UI → receipt browser

Old repositories are donors, not runtime dependencies.
