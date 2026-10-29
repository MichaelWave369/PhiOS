# PhiOS Site Browser Smoke Gate R0.1

## What is proven

The **PhiOS Site** GitHub Actions workflow validates actual browser rendering before the Pages deploy job can proceed. This checks a **built** Vite/React/TypeScript site, not just compilation, and performs the smoke tests against a temporary HTTP preview on the GitHub-hosted runner.

The validation job on a GitHub pull request or push:

1. Checks out the exact source revision and runs the existing site build.
2. Installs pinned `@playwright/test` and Chromium **on the GitHub-hosted runner only**.
3. Runs `npm run test:browser` in `site/`. Playwright starts `vite preview` on `127.0.0.1:4173` and requests `/PhiOS/`, matching the configured GitHub Pages base.
4. Verifies title/main content, the expected top-level navigation, Architecture/Sovereignty/Live Project anchors, architecture mode and selected node interactions, the CRT toggle, `project-status.json` and a small-screen landing page.
5. Asserts that the initial page loads without browser JavaScript exceptions or unexpected outbound network requests. For that test, non-loopback requests are blocked and reported.
6. If a browser test fails, the job fails and uploads short-lived Playwright traces/screenshots. The **deploy** job depends on successful validation.

This is a targeted smoke suite, **not** full browser accessibility certification, security testing, integration testing, browser-matrix testing, or an OS readiness audit.

## No local installation required

Operators can merge reviewed PRs and inspect GitHub Actions results from a browser. Chromium and its required dependencies are installed on temporary GitHub runners, **not on the operator's Windows PC**.

The public site remains at:

https://michaelwave369.github.io/PhiOS/

Browser smoke tests use the local built `dist` output from the same source revision. They do **not** require authentication, mutate content, use deployment credentials, or browse the GitHub Pages production site to qualify PR changes. A separate actual production smoke test is still valuable.

## Optional developer commands

From a checkout that already has Node.js and npm installed:

```sh
cd site
npm install --no-audit --no-fund
npm run build
npx playwright install --with-deps chromium
npm run test:browser
```

Do **not** infer that `npm install` or Chromium ran offline. The runner is internet-connected and may download packages and browser binaries.

The Playwright web server is an automatically managed temporary `vite preview` bound to `127.0.0.1`. The browser tests don't install any system service and don't persist a running production server.

## Evidence boundaries

- **Browser smoke passed on CI:** the built frontend rendered and selected controls responded to Chromium on that particular runner and revision.
- **GitHub Pages deployment succeeded:** GitHub's Pages deployment reported success for its artifact.
- **Public production site works for every user:** NOT proven by CI alone; browsers, cache, geographies and external integrations can differ.
- **PhiOS runs offline:** NOT proven. CI installs dependencies on a connected runner and serves a local site on that runner.
- **PhiOS Linux OS or entire ecosystem is bootable/restorable:** NOT proven. This gate tests only the public website frontend.

The suite records no private account data. No login, private status or third-party links are opened by its tests. Links to GitHub are checked as link attributes, not visited.

**Ledger Above Ego. DONE Means Verified.**
