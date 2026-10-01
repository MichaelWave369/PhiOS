# PhiOS Linux release contract

Target: **0.1.0-alpha.1 development preview**, x86_64, x64 UEFI, Arch Linux,
Wayfire and PhiShell. Linux supplies the kernel. Private PhiKernel/TIEKAT
implementation is not part of this image or a prerequisite to boot it.
`packaging/linux/release.json` supplies machine-readable candidate identity.
Python package versions and OS versions are independent. OS tags start with
`phios-linux-v`; the existing `v*` workflow publishes Python artifacts only.

## Included preview

- Current PhiOS Python code and built PhiShell, installed as pacman packages.
- Local observation of host, services, processes, devices and native packages.
- A non-root Wayfire session, Chromium application window, Waybar and terminal.
- Supervised user services with bounded loopback ports and private state umask.
- Optional governed history when an operator supplies an enabled memory config.
- Curiosity projection access, with consequential persistence approval held.

The default preview does not run an AI model or an autonomous agent. Ollama,
vector memory, OCR, Windows UI Automation/GhostWalk and hardware bridges are
optional or platform-specific. Missing capabilities must show unavailable.
No Linux desktop effect executor or lease issuance is advertised. The browser
cannot mint operator approvals; see OPERATOR_AUTHORIZATION.md.

## Deliberately unqualified capabilities

This preview is a volatile live image. Its experimental blank-disk installer
passed the named disposable VM gate (see INSTALLATION.md); it has no supported
hardware installer, whole-OS rollback, Secure Boot or BIOS support. Installed
data backup/restoration and abrupt VM restart passed; physical power-loss and
whole-system update recovery remain separate gates. No hardware compatibility claim follows from a VM boot. Agent
isolation requires separate OS principals and a verified restricted broker;
an operator-owned shell or pseudo-TTY is not human authentication.

## Acceptance gates

| Gate | Required evidence |
| --- | --- |
| Candidate packages | Source commit/archive hash, JS lock, signed Arch snapshot, installed wheel/entrypoints and UI smoke |
| Live boot | Exact ISO hash, UEFI VM serial log, non-root compositor/browser, local HTTP observations, screenshot |
| Session lifecycle | Login, sidecar failure/restart, logout stopping services, reboot, no sandbox bypass |
| Durable state | Private permissions, concurrent writers, abrupt termination, verified backup/restore and schema migration |
| Installed system | Explicit blank-disk identity/confirmation, disposable VM install, no-ISO reboot and persisted receipts |
| Updates/recovery | Verified signed update, interrupted update, recovery boot and restore; application rollback alone does not satisfy this |
| Linux workflow | Explicit operator decision, exact binding, single-use lease, Linux effect and independent post-effect verification |
| Hardware beta | Named machines, firmware/GPU/network/input/audio/storage results and recovery evidence |
| Public OS release | All applicable gates passed for the exact artifact; SHA256SUMS, signature, SBOM, third-party licenses/source provenance, notes and maintainer decision |

CI artifacts are unsigned **test candidates**. A successful build or boot does
not automatically promote an adapter, establish readiness or publish a release.
Maintain historical documents and licensing provenance rather than rewriting
past releases. PhiOS source is MIT; Linux and bundled packages retain their own
licenses. Full distribution source/license compliance remains a release gate.
