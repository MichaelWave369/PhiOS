# Apps in the experimental PhiOS image

The desktop boots, but that does not mean every app named in the original shell
mockup has been packaged. The owner reported on 2026-10-01 that app tiles could
not be clicked. Source inspection confirmed that the Home and Start tiles had
no click handlers. The PhiVessel prompt and quick actions were also inert.
This observation is preserved in `evidence/app-launcher-field-observation.json`.

The exact normal #283 package inventory contains Chromium, Foot, Wayfire,
Waybar, Wofi, the PhiOS Python tools and PhiShell. It contains no Browsallax
package, Ollama runtime or model weights. The source package contains BrainC
client code and SOMA contracts/tools; those are not complete graphical apps.

## What the shell opens

| Entry | Included behavior |
| --- | --- |
| System Inspector | Existing host/service/process/package/device observations |
| Reality Ledger | Existing governed canonical-history panel; existing read/compare grants still apply |
| ΦDream | Existing Symbol Lab curiosity workspace |
| Builder | Build workspace preview; no compilation or command execution |
| Apps | Included-tool status and ordinary desktop-app instructions |
| Browsallax | Not bundled; status explains the included Chromium alternative |
| PhiVessel | Advisory context dock; conversational runtime not connected |
| BrainC | Client/terminal status command only; Ollama and weights not bundled |
| SOMA | Contracts/terminal tools only; separate graphical app not bundled |
| PhiOffice, Domistika, Professor Φ | Application runtimes not bundled |

Home, Start and command search use the same entries. Selecting an included tool
opens, restores or focuses its shell window. Selecting an unfinished integration
opens a status explanation. The unconnected chat/translation controls are
explicitly unavailable. These labels describe the shipped image, not a scan
of apps installed separately and not a runtime-health assertion.
The **Apps** button above the desktop windows also opens the library, so the
initial overlapping windows do not hide the entry point.

## Use the included desktop basics

- **Chromium:** Super+Space, then choose Chromium.
- **Foot:** Super+Alt+Enter.
- **PhiOS tools:** Super+Enter; enter `help` for commands.
- **BrainC endpoint check:** in the Phi terminal, enter `brainc status`. This
  checks the configured endpoint; it does not install a model or establish
  inference quality.
- **Network settings:** Super+N.
- **SOMA/Spine tools:** in Foot, run `phi-spine --help`.
- **Lock:** Super+L; enter the account password to unlock. The separate
  VirtualBox wrong-password/unlock test remains pending.

Approved external app desktop entries continue through the existing governed
desktop-launch path. `phi-app catalog-desktop-apps` in Foot inspects the catalog;
it does not install an app or grant launch permissions. Empty discovery is not
evidence that the ecosystem apps were installed.

## Candidate boundary

The launcher repair changes UI state and connects existing read-only panels.
It introduces no HTTP process-launch endpoint, download, install, model pull,
grant, policy change or private kernel implementation. Packaging increments
PhiShell's Arch package revision from 3 to 4 at the same `0.16.0` version.
The OS release remains `0.1.0-alpha.1` experimental. Full external app integration
needs its own exact source/artifact selection, runtime contract and qualification.

The qualified #283 source/ISO and #285 field report remain historical evidence.
Changed frontend/package bytes require their own normal/QA image qualification
and a fresh VirtualBox click test. This correction does not qualify the physical
Skytech/RTX 5070 machine or authorize merging, tagging or publishing.
