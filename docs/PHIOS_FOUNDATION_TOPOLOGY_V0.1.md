# PhiOS foundation topology R0: one OS, owned AI home, governed apps

**Status:** architecture + offline read-only topology candidate. Not an OS build, kernel port, deployment, permission, install receipt, or runtime qualification.

## Decision

- **PhiOS** owns the operator shell, app catalog, release state and the current bootable **Linux-based** OS qualification path.
- **PhiKernel** owns constitutional identity, continuity and governed transition boundaries. Its current published runtime is hosted on Linux. This public topology references only a normalized boundary, never PhiKernel internals or TIEKAT code.
- **Infinite Porch** is the proposed local-first AI home for each qualified device, with identity and explicitly granted device/model relationships. A remote peer is not automatically trusted or runnable.
- **Infinite Commons** is a separately owned artifact/world/portal experience. Opening a portal is not permission to run its code or access a local model.
- **Infinite Interconnects** is a simulator/contract lab, not a shipping transport or delegated authority layer.
- **BrainC**, **SuperPhiVessel**, **ThinkTank** and **PocketBrain** are distinct model interfaces/clients, not competing kernels.
- **BudgetGenius** proposes qualified low-cost routes. **PhiReflex** remains a bounded advisory/routing-influence component within PhiOS. **PhiStream** is an experimental memory-tiered **inference engine**, not a CPU memory manager or universal model loader. Model weights are separately licensed data.

## Native PhiKernel goal: truly remove Linux, not rename it

"PhiOS without Linux" is a **future independently implemented hardware substrate**, not achieved by installing AI model weights. Keep two explicitly separate tracks:

1. **L track (working compatibility bridge):** existing Arch/Wayfire PhiOS development image; Linux handles boot, CPU scheduling, virtual memory, drivers, device security and GPU support. No claim of Linux independence.
2. **N track (future native kernel R0):** first a small, testable, self-owned x86_64 UEFI QEMU target with serial console, deterministic boot, timers, exception/interrupt handling, page tables/isolated address spaces, syscall/effect boundary, verified disk/recovery, and a minimal non-AI scheduler. Stubbed interfaces must report NOT_IMPLEMENTED, never PASS. No bare-metal or secure-boot readiness claim without actual evidence.
3. **N1:** implement signed image/rollback, memory and process isolation and device I/O proofs. Keep a Linux fallback, untouched user files, and source/license/firmware audit.
4. **N2:** add gated user-space local inference adapters, not privileged weights. Large-model IO, GPU drivers, GPU residency, model licenses, context/KV memory and runtime recovery must be measured separately. An OOM or hung model must not stall the kernel.
5. **N3:** only after native bare-metal keyboard/storage/network/graphics, isolation, recovery and sustained-model tests pass consider a user migration. Do not overwrite Windows or the user's working Linux installation during experimental development.

Passing a deterministic QEMU smoke test is not passing hardware support. Using Linux drivers in an alternative desktop remains Linux-dependent.

## Read-only machine-readable portfolio subset

`phishell/src/ecosystem/foundation-topology.v0.1.json` records **16 inspected public source repos**, **14 directional candidate/documented links**, role classifications and zero runtime permission bits. It is a **curated dependency-design subset**, not a full portfolio census, and intentionally does not list private repos or model checkpoints. It cannot be used as an install manifest, PhiOS grant, source hash attestation, licensed-weight certificate, or signed discovery result.

The already established `phishell/src/ecosystem/public-repos.json` and `app-candidates.json` remain authoritative for source discovery and the two first-wave held-for-review application proposals. The existing App Platform v0.25–v0.58 controls intake, sandbox, install, launch, update, rollback and review. This topology never enrolls into those registries.

Run from the repository root:

```shell
python scripts/verify_foundation_topology.py --check
python -m unittest discover -s tests -p 'test_foundation_topology_v01.py' -v
```

These commands read a checked-in local JSON file, print a fingerprint and check closed schemas; they do not fetch URLs, execute apps, load models, build images, modify the OS or mutate grants. SOURCE_REVIEW_ONLY never implies source has been fully audited.

## The first usable acceptance vertical

- **Home:** A verified local PhiOS session displays an operator-launched Infinite Porch *status* view. The first step is a strictly read-only local adapter with origin binding and explicit operator activation, no model invocation.
- **Doorway:** From that home, one reviewed Commons portal opens as navigation only, without executing imported Commons instructions or granting filesystem/network privileges.
- **Model:** A separately approved BrainC/Ollama local endpoint is observed and reported as present or unavailable. No automatic inference or silent cloud fallback.
- **One app:** Promote exactly one Vessie/ThinkTank reviewed build using the existing App Platform and v0.69 HOLD preflight. All license/release and actual OS-image gates remain binding.
- **Creative:** Run a manual, license-appropriate static Unreal GLB handoff into PixelForge; Framefield GLB import must be implemented/tested before any PixelForge→Framefield animation success claim, followed by an independently tested ParaCut media handoff.
- **Native proof:** Start the separate native PhiKernel boot ladder in a VM, while retaining the Linux candidate as the only current OS execution substrate.

**Completion rule:** Every claimed integration gets exact commit, machine, runtime, result, permission boundary and reproducible negative tests. A link, simulated fixture, green static build, or AI answer is not an installed app or a native operating system.
