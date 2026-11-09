# PhiOS R15: qualify the *assembled* PixelForge GitHub Pages VR Studio

**Review-only integration gate.** No production Netlify or GitHub Pages configuration, custom-domain trust, native installation, or app permission is added.

## Why

PhiOS #412 is merged at `52141a9e3e234cf001fea005a815776acec1ca11` with all post-merge gates green. R12/R13/R14 real Chromium tests exercised PixelForge's source `vr-studio/` served at an ephemeral origin root. However, PixelForge's actual `.github/workflows/pages.yml` builds its **React Pages distribution** with `site/vite.config.js` base `/parallax-pixelforge/` and `site/scripts/assemble.mjs` explicitly copies `vr-studio` into `dist/vr-studio/`. These are two different route layouts. A green source-folder test alone does not certify the packaged URL layout.

## R15 acceptance changes

The existing two-origin PhiOS workflow continues to checkout **exact reviewed merged PixelForge #89 commit** `b1c6314da005de801ba3b0417ffe4b4abe461828`, not its moving `main` branch. It now runs the **actual PixelForge public Pages builder** from this pinned commit. The browser serves `.interop/pixelforge/dist/` under the site project-path prefix `/parallax-pixelforge/`, so VR Studio must load from:

```text
http://127.0.0.1:<ephemeral-pixel-port>/parallax-pixelforge/vr-studio/
```

The parent PhiOS app runs on a **different** loopback origin. It builds with the exact PixelForge project-path URL and origin. Test setup hashes `index.html`, `studio.js`, `phios-bridge-client.js`, and `phios-bridge-ui.js` in the assembled artifact, asserting byte identity with the reviewed pinned source files. The loopback static server **refuses unexpected/unpublished routes** and does not use an SPA fallback for missing PixelForge scripts.

The existing real Chromium test remains intact: standalone child bridge hidden, Home launcher opens Build without starting a frame, explicit child start and handshake, default denial, cancellation denial, same-text PhiOffice ID exclusion, explicit one-ref sharing, V2 metadata-drift revocation, rejection after V2 restoration, required fresh approval, manual revocation, disconnect and reconnect default denial. It also verifies no world data is saved and no V1/V2 migration takes place.

## Important limits

- This proves the reviewed source can be assembled into a local GitHub **project Pages-shaped artifact**. It does **not** prove the live public GitHub Pages URL currently serves that artifact, is reachable through Netlify, or allows framing under its production response headers.
- The public website is not an installed PhiOS native application. Both actual production origins and any embed policy still require separate manual review.
- The GitHub Pages build intentionally uses the pinned PixelForge site package manifest and existing install/build process, rather than importing a new runtime tool. CI must fail if assembly, asset preservation, public exclusions, iframe handshake, or native PhiOS qualification fail.
- No default production `VITE_PHIOS_PIXELFORGE_BRIDGE_*` values are added, and no permissions or persistent app grants are modified.

**Review gate:** require full [R12 PixelForge browser workflow](../.github/workflows/phios-r12-pixelforge-browser.yml) green, public catalog and full PhiOS native-image/VM qualification green; separately inspect actual live host response headers before approving any real-world embedding.
