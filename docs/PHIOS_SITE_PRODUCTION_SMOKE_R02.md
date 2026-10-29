# PhiOS Site R0.2: production Pages smoke and exact deployed-commit evidence

## The gap

R0.1 qualifies a locally built Vite site in headless Chromium **before** GitHub Pages deployment. That is valuable but does not establish what GitHub Pages actually delivered. R0.2 adds a second, independent post-deployment smoke gate for the **public** URL:

https://michaelwave369.github.io/PhiOS/

This all runs on GitHub-hosted CI. No installation on the operator's Windows machine is needed.

## Workflow

The \`PhiOS Site\` workflow keeps the R0.1 \`validate\` job as a prerequisite to \`deploy\`. For **pushes to main only**, a new \`production-smoke\` job requires successful \`deploy\` and:

1. Installs dependencies and Chromium **on its temporary GitHub runner**.
2. Repeatedly requests only \`https://michaelwave369.github.io/PhiOS/project-status.json\`, with an explicit no-cache query and no redirects, while Pages/CDN is propagating. The public JSON must identify \`MichaelWave369/PhiOS\`, \`authority: none\`, \`siteBuild: verified\`, and the **exact** \`github.sha\` that produced the deployment. Checks are bounded to at most 18 attempts, each with a 10-second request timeout and a 10-second inter-attempt delay.
3. Only after exact commit metadata is visible, runs isolated Chromium tests against the **production HTTPS origin**, with no local Vite server and no login. Verifies the page title and visible landing content, absence of browser page exceptions and unexpected off-origin initial resource requests, exact public status JSON, Architecture/Sovereignty/Live Project navigation, architecture view changes, and CRT toggle behavior.
4. On failure, marks **the overall site workflow** red, and uploads short-lived failure screenshots/traces. The production job has a bounded 12-minute timeout.

R0.2 **does not alter** main source, modify public UI, run private-site commands, push changes, auto-open external GitHub links, or collect authentication tokens. External requests attempted by the production frontend are blocked and reported in the initial-load test.

## Two kinds of success

| Check | What it proves |
| --- | --- |
| \`validate\` | Built source renders and selected interactions work on the GitHub runner |
| \`deploy\` | GitHub Pages says this workflow deployed its artifact |
| \`production-smoke\` | At test time, the public Pages URL exposed expected commit metadata and selected browser interactions worked |
| Physical offline recovery | **Not tested** |
| PhiOS Linux OS boot | **Not tested** |
| All browsers, devices, geographies and integrations | **Not tested** |

The public metadata has no cryptographic publisher signature. Exact \`project-status.json\` commit identity establishes the *reported* deployment identity and guards stale CDN propagation; it does **not** prove every HTML/JS byte came from that commit independently. Browser smoke adds independent rendering observations but is not a comprehensive provenance audit.

## Failure response

**Post-deployment is not a pre-publish veto.** GitHub Pages may already be serving the artifact before \`production-smoke\` fails. A failed job records a real release problem, rather than rolling back published pages automatically. An operator reviews the job and its artifacts, checks if a newer deployment superseded it, and deliberately reverts/repairs the site if needed.

Do not suppress actual failures with indefinite retries or silently accept a previous commit. A stale CDN result on a bounded observation window is a red check with its exact expected and observed SHA prefixes.

## Repository tests

- \`npm run test:rollout\`: network-free Node tests of the bounded commit-identity probe, stale cache retry, forged metadata refusal and invalid inputs.
- \`npm run test:browser\`: R0.1 built-site Chromium tests over ephemeral local Vite preview.
- \`npm run test:production\`: R0.2 Chromium tests against *real public Pages*; the workflow supplies the expected commit via \`EXPECTED_DEPLOY_SHA\` after the deployment succeeds.

The production browser job is intentionally **skipped on pull requests**, because no PR preview is deployed at the public URL. A PR can still run and validate the unit tests and R0.1 built-site smoke. A green PR validation run **does not** claim that R0.2 has been observed running successfully after merge. The first actual production smoke evidence is available only after a main deployment.

**Ledger Above Ego. DONE Means Verified.**
