# PhiOS R16: live GitHub Pages PixelForge iframe + provenance audit

**Review-only; no production setting change, account connection, persistent permission, native app install, browser credential, or deployment.**

## Why this exists

PhiOS [PR #413](https://github.com/MichaelWave369/PhiOS/pull/413) merged at `a2b70cf965b3c6d6b09899d1cd953ff87a55e79b`. Its post-merge [full native-image qualification](https://github.com/MichaelWave369/PhiOS/actions/runs/42549518976), [two-origin Chromium](https://github.com/MichaelWave369/PhiOS/actions/runs/42549518974), and PhiOS Site were green. R15 correctly tested PixelForge's assembled public GitHub project Pages path but served it from an *isolated local HTTP server*, **not** the actual published HTTPS endpoint.

The public PixelForge VR Studio route and its bridge client script were independently fetched successfully, but reachability does not certify that cross-origin embedding works or that the published script matches the reviewed version.

## New, separately gated R16 evidence

An independent workflow runs the existing full R12–R15 browser test in explicit **live-site audit** mode, not in the default local-artifact mode. It:

1. Checks out the **exact merged PixelForge #89** source `b1c6314da005de801ba3b0417ffe4b4abe461828`, independently from PhiOS and without retained GitHub credentials.
2. Builds PixelForge's pinned public Pages artifact as an offline assembly reference.
3. Fetches `https://michaelwave369.github.io/parallax-pixelforge/vr-studio/index.html` plus the two reviewed bridge modules from actual HTTPS GitHub Pages. Requires explicit HTTP 200 and no redirects. Records status, HTML MIME type, `X-Frame-Options`, `Content-Security-Policy` and `Referrer-Policy` headers; the browser determines actual embed acceptability.
4. Requires **SHA-256 byte identity** between live `phios-bridge-client.js` / `phios-bridge-ui.js` and the exact merged #89 source files. Later unreviewed script changes fail closed, not auto-whitelisted by current PixelForge `main`.
5. Builds PhiOS with the **live HTTPS PixelForge path as a CI-only explicit endpoint**, and serves only PhiOS itself over a separate disposable local loopback origin.
6. Drives real Chrome through the existing full R12 test: PixelForge standalone client hidden, launcher opening Build without iframe, manually starting the live GitHub Pages iframe, true parent-origin/referrer/session binding, unapproved request denied, cancelled approval still denied, single operator-approved opaque `project_ref`, zero saved world contents, V2 mutation revocation, restored-V2 still denied, renewed approval, explicit revoke, disconnect and fresh reconnect denial. Cross-site out-of-process iframes are handled through the appropriate Chrome debugging target/session when needed.

The live audit emits `PHIOS_R16_PIXELFORGE_LIVE_HTTP` and the existing `PHIOS_R12_PIXELFORGE_TWO_ORIGIN_CHROME` receipt annotated with `pixelForgeServedFromActualPublicPages=true`.

## What success does and does not mean

A passing public-site browser audit can support **this exact live GitHub Pages URL** permitting a Chromium iframe from a loopback test origin at the time of the run. It does **not** authorize production `VITE_PHIOS_PIXELFORGE_BRIDGE_URL` or `_APPROVED_ORIGIN` configuration, claim all browsers will embed the site, attest a publisher, grant actual world file access, or establish that a different PhiOS Netlify domain is allowed by `frame-ancestors`. The production PhiOS origin, its HTTPS response headers, and a real deployed-parent-to-deployed-child run remain independent acceptance criteria.

Because GitHub Pages changes independently, live HTTP failure (network, missing asset, changed source hash, redirect or restrictive framing) is reported as a failed separate **non-release** audit. It must not bypass or redefine the existing fixture-free native image, signature, SBOM, QEMU, installed-recovery or release gate.

All test project refs are synthetic and manually created inside the isolated browser profile. No user project file, purchased GLB, account credential, actual PhiOffice record, local machine path, or private token is sent to the live website.

## How to read a failure

- **HTTP 200 / HTML / asset SHA failure:** inspect Pages deployment and exact source drift. Never silently repin to the latest branch.
- **CSP / X-Frame-Options / referrer failure:** test the live origin headers and site's framing contract; do not disable browser security to get green.
- **CDP target / timeout:** distinguish test harness out-of-process frame routing from real browser-frame blocking and add evidence before changing product code.
- **Permission or project content leak:** release-blocking bridge regression. Do not weaken allowlists to satisfy tests.

**R16 does not modify runtime application controls or activate a new production endpoint.**
