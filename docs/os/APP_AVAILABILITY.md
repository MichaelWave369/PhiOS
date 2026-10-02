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

The owner-local #286 test reported that Wofi initially put literal `drun` in the
search field on both passes. Selecting that text and replacing it with
`Chromium` successfully opened the browser. This workaround and unresolved
launcher quirk are retained in the field receipt below.

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
The changed #286 source passed its complete normal/QA qualification in
[run 36939975061](https://github.com/MichaelWave369/PhiOS/actions/runs/36939975061).
The owner then supplied a local GPT-5.6 report and two screenshots for the exact
normal ISO. Home, Start, search, Apps and the four included tools' window
lifecycles passed before and after a cold boot in `PhiOS-PR286`; Chromium and
Foot also opened through their documented shortcuts. See
[virtualbox-field-0f17bac1.json](evidence/virtualbox-field-0f17bac1.json) and
[VIRTUALBOX_COMPATIBILITY.md](VIRTUALBOX_COMPATIBILITY.md) for the full binding,
reported scope, screenshot digests and preserved observations.
Reality Ledger's window opened, while the final screenshot explicitly shows
its governed canonical-history backend as unavailable. The test did not install
external runtimes or prove chat/model inference. This documentation continuation
does not qualify a replacement ISO, the physical Skytech/RTX 5070 machine or
authorize merging, tagging or publishing.
