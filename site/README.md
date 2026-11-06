# Φ PhiOS Mission Control (GitHub Pages)

This is the **public informational React site** at `michaelwave369.github.io/PhiOS/`, not the PhiOS Web desktop, an operating-system image, or a native app installer.

## Entry points and responsibility boundaries

- **PhiOS Web:** `https://phi-field.com/os/` is the separate local-first browser desktop, with no native OS permissions.
- **PhiOS XR:** `https://michaelwave369.github.io/PhiOS-XR/` is the browser/optional WebXR experience.
- **PhiOS Mobile:** `https://michaelwave369.github.io/PhiOS-Mobile/` is a touch-first browser preview, not an Android ROM.
- **PhiOS Linux:** experimental, unpublished x86_64 UEFI Arch-based image under `docs/os/RELEASE_HANDOFF.md`. It is not a supported native install.
- **Infinite Porch / Commons / Interconnects:** source-linked ecosystem projects, not preinstalled software or auto-authorized network connections.

The architecture explorer, Sovereignty Contract, CRT toggle, and source-bound project metadata remain separate from these launch links. There are no remote scripts, telemetry calls, external media hotlinks, or installation actions on the page.

## Source-bound build status

`scripts/generate-status.mjs` regenerates `public/project-status.json` from the *exact Git checkout being built*. App Platform **test contract** labels are derived from checked-in `tests/test_app_platform_vNNN*.py` filenames, rather than old `docs/VERSION_HISTORY.md` entries. The native image label is read from `packaging/linux/release.json`. Neither is a claim that a signed native application or image has passed physical-device acceptance.

The checked-in `public/project-status.json` is a non-authoritative dev fallback. Do not edit it to manufacture a release version.

## Test and deployment commands

Within `site/` run `npm install --no-audit --no-fund`, `npm run build`, `npm run test:rollout`, then `npx playwright install chromium` and `npm run test:browser`. The GitHub Pages workflow performs its own browser tests before deploying. **Only a push to main** triggers Pages deployment and its subsequent exact-commit public smoke test. Opening a PR only exercises validation, not publication.

Keep all build gates green and review the actual navigation/accessibility, status JSON, and performance before merging. Any promise of public installability requires a separate signed release decision and evidence.
