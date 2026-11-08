# PhiOS R13 · Merged PixelForge source pin and registry-drift consent revocation

**Status:** review candidate, no native application install or production endpoint change.

## Evidence and why this exists

PixelForge [PR #89](https://github.com/MichaelWave369/parallax-pixelforge/pull/89) merged on November 8, 2026 at `b1c6314da005de801ba3b0417ffe4b4abe461828`. PhiOS [PR #410](https://github.com/MichaelWave369/PhiOS/pull/410) also merged, and [PhiOS post-merge native qualification](https://github.com/MichaelWave369/PhiOS/actions/runs/42447121167) plus [the actual two-origin browser test](https://github.com/MichaelWave369/PhiOS/actions/runs/42447121077) were green.

However, the R12 test still checked out PixelForge's **pre-merge PR head** `31d7a64d220a907f72b9817b16f2ad57c88cdca1`, not the merged producer source. A passing test against unmerged source is not the same claim as a passing test against the shipped revision. This rung fixes the pin in both the GitHub Actions checkout and the browser test's independent SHA verification, using the exact reviewed #89 merge commit. PixelForge's later main changes in the Metroidvania UI do not alter the bridge, but are intentionally not silently pulled in. The fixture stays self-contained.

## Consent hardening

The R12 host originally revalidated only the selected provider-qualified project ID/title before each incoming message. That prevents a deleted or renamed project from being reused, but silently retained an approval if **other V2 metadata** changed. R13 additionally retains the exact V2 raw bytes observed at approval and fails closed if those bytes differ before a later host reply. A cross-tab `storage` change also revokes when reported by the browser. No grant is persisted.

An operator who changes or restores V2 must **approve the PixelForge project reference again** before any future `host.context` response, even if the selected ID and title are identical to before. Referrer, origin, frame, session ID and exact message schema checks are unchanged. Approval still conveys an inert `project_ref`, not a world/GLB file, credentials, owner signature or execution authority.

This is conservative metadata-snapshot consent, **not** a guarantee of cross-tab atomicity. The browser `localStorage` APIs do not provide multi-tab compare-and-swap; a tab can still race between checks. No design should treat opaque project refs as secrets or immutable proof of ownership.

## Acceptance

The pinned [R12 two-origin Chromium workflow](../.github/workflows/phios-r12-pixelforge-browser.yml) must pass against the exact merged PixelForge SHA. Its browser test now exercises a **valid, unrelated V2 identity addition after approval**, requires the next request to be **denied** and previous child label cleared, restores the original V2 bytes and still requires denial, then explicitly reapproves and verifies only the single opaque project ref is delivered. Existing cancellation, revocation, reconnection, standalone silence and V1 preservation gates remain.

Existing R11 browser tests, PhiShell/host tests and full native ISO/VM qualification must also pass. These tests do not establish automatic installed-app launch, publisher attestation, private world authorization, persistent sharing or real-device compatibility. Production endpoints remain unconfigured by default.
