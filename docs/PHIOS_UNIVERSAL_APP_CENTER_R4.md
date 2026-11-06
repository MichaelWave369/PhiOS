# Φ Universal App Center R4 — first reviewed browser application

**Status: R4 first-party browser PWA release candidate.** This is not a generic GitHub installer, native package manager, firmware or release authorization.

## First reviewed profile: PhiOS Web

Canonical reviewed registry: `interop/app-center-reviews.v1.json`, validated offline by `python interop/app_center_reviews_v1.py`. The public catalog remains **225 source-only repository identities**. A separate reviewed-app overlay grants exactly one *bounded browser action* without changing those source records.

- Identity: `github:1442243366` / `MichaelWave369/phi-field`.
- Runtime: unprivileged **browser PWA** at `https://phi-field.com/os/` (`/os/` scope). This is **not native Linux or Android**.
- Evidence: `phi-field` PR #8 and `tests/browser_web_os.py` passed static-bundle Chromium desktop/phone/persistence acceptance. The bundled manifest and scoped offline service worker are observed in the source. That review **does not independently verify today's live production endpoint** or every browser's installation offer.
- Qualification badge: **CI-REVIEWED WEB PWA · PRODUCTION ENDPOINT NOT INDEPENDENTLY VERIFIED**.
- User action: explicit **Open PhiOS Web** navigation. The current website's **App Center** displays a browser install button *only if the browser offers a real `beforeinstallprompt` event*. Other browsers use their own menu or Add to Home Screen options. No app installation succeeds without the browser's UI and the user's approval.
- The browser may offer installation even when `beforeinstallprompt` does not fire. R4 cannot guarantee a prompt on any specific device. The `appinstalled` event is informational, not a privilege receipt.
- Android Mobile PWA opens the exact HTTPS link after a tap; it does **not** install an APK. Native Android HOME and native Linux App Platform do not gain software-install authority from this entry.
- All **224 other** public catalog entries remain **SOURCE ONLY**, including records with a declared homepage. Their runtime, license, launch safety and packaging require independent review.

## Review invariants

`interop/app_center_reviews_v1.py` denies wrong catalog snapshot, wrong stable ID/source, extra fields, altered first-party origin/path, forged live verification, fake evidence or any change suggesting native or automatic install. R4 is *exactly one* pinned initial record; additional reviewed entries require an explicit new schema/policy approval and CI qualification.

A future app intake pipeline must resolve every candidate's actual platform, exact commit/build artifact, authorship/license, security permissions, user intent, independent launch/rollback verification and signed release receipts where required. A green repository CI does not automatically qualify its application.

## Test and release

- Core: `pytest -q tests/test_app_center_reviews_v1.py`. Full native Linux image/recovery release gates remain separate.
- Web: static package checks and Chromium `tests/browser_web_os.py` validate App Center display, explicit prompt, and no automatic installation. Manual Netlify upload only, after review.
- Mobile PWA: `npm run check && npm test && npm run build` validates same JSON and safe external link. No PWA auto-publish or Android APK revision.
- R4 registry is a local reviewed metadata overlay. It does not grant automation, native effects, filesystem access, tokens, bridge connections, repository execution or unattended updates.

**Capability != authority. CI-reviewed != verified live. PWA install != native operating system install.**
