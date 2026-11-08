# PhiOS R14 · Governed PixelForge browser pilot discovery

**Scope:** first-class PhiShell *navigation and readiness*, not native installation, external application execution, asset access, or permission transfer.

## Verified prerequisite

PhiOS [#411](https://github.com/MichaelWave369/PhiOS/pull/411) merged at `55905efcca3abb3118e4cf305a19cc7927140deb`. Its [post-merge full qualification](https://github.com/MichaelWave369/PhiOS/actions/runs/42453270834), [real two-origin PixelForge consent/revocation test](https://github.com/MichaelWave369/PhiOS/actions/runs/42453270665), and site build all passed. PixelForge R12 [#89](https://github.com/MichaelWave369/parallax-pixelforge/pull/89) was independently merged and verified, pinned at `b1c6314da005de801ba3b0417ffe4b4abe461828`.

## R14 launch contract

The PixelForge tile appears in **PhiOS Home → App Launcher**, **Apps**, and the universal command overlay. Its exact state is **Browser pilot · gated**. Clicking the tile triggers the existing `OPEN_WINDOW` reducer event for `build-window`. It does not create a new app runtime, fetch code, make a network request, open the PixelForge iframe, choose an identity, or grant access. The same Build window can still be reached through the existing Builder tile or command overlay.

Inside **Apps**, the **PixelForge browser pilot discovery** card provides a **read-only, manually refreshable** readiness summary. It reports:

1. **DISABLED** unless `VITE_PHIOS_PIXELFORGE_BRIDGE_URL` and `VITE_PHIOS_PIXELFORGE_BRIDGE_APPROVED_ORIGIN` are both explicitly configured, exact-origin, and different from the PhiOS origin.
2. **HELD** if the browser-local V2 identity registry is missing or invalid.
3. **HELD** if V2 contains no reviewed PixelForge identities, even if PhiOffice has the same text project ID.
4. **BROWSER PILOT ELIGIBLE** when the exact endpoint config and at least one reviewed PixelForge V2 identity are present. This **does not** prove the remote endpoint is reachable or authenticated, and it never claims an installed native app.

The operator can use **Open PixelForge pilot in Build Field** to navigate to the same Build window. From there, the existing R12/R13 controls must still be explicitly exercised: **Start PixelForge pilot**, choose a provider-qualified PixelForge ID, and separately approve sharing for that frame session. Cross-origin frame binding, default denial, revocation on V2 drift, fresh reconnect denial, and zero world-file transfer are unchanged.

No new environment variable defaults, trusted domains, app installs, persistent permissions, source repositories, automatic launches, or local project data changes are introduced. Readiness is refreshed manually and never acts as a host-status or native-install probe.

## Acceptance

- **PhiShell unit tests:** tile maps to `build-window`, no native-installed assertion, and read-only status distinguishes unconfigured, corrupted V2, PhiOffice-only V2 and reviewed PixelForge metadata.
- **Real two-origin Chromium:** from the actual compiled PhiOS home app tile, navigate to Build and assert the PixelForge iframe is still **absent** with no project approval, *before* manually clicking Start. Existing consent, default denial, wrong-provider separation, V2-change revocation, restoration-requires-reapproval, explicit revoke and reconnect checks still pass against the exact merged PixelForge #89 commit.
- **Full PhiOS qualification:** PhiShell tests/build and fixture-free native-image VM gates must all pass independently; a browser tile is not a signed native release.

**Held for review:** no merge, production environment change, native installer, authorization or deployment is implied by this R14 proposal.
