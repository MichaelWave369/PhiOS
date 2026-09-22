# PhiOS Public Site v0.1

The PhiOS public site lives in `site/` and is deployed as a static GitHub Pages artifact.

## Boundary

The site is an informational projection of public repository state.

It has:

```text
operational_authority = false
action_authority      = false
execution_authority   = false
```

The browser receives no PhiOS API key, repository write token, runtime secret, or privileged
control-plane endpoint.

## Stack

- React
- TypeScript
- Vite
- GitHub Pages
- GitHub Actions

No server runtime is required.

## Architecture views

The first public explorer exposes three deliberately different views:

- **SYSTEM** — major PhiOS surfaces and their relationships.
- **AUTHORITY** — surfaces that can participate in paths toward consequential action.
- **EVIDENCE** — observation, provenance, memory, identity evidence, verification, and ledger surfaces.

The distinction is intentional:

> the evidence graph and the authority graph are not the same graph.

## Build-time project status

`site/scripts/generate-status.mjs` creates `site/public/project-status.json` from the
exact repository checkout used for the build.

The artifact contains only public metadata:

- commit SHA and commit timestamp;
- latest merge PR number visible in local Git history;
- current Spine, App Platform, PhiReflex, and research-hardening version lines;
- site-build state.

It does not claim that every repository CI lane is green. The Pages deployment depends
on the site validation job, so `siteBuild = verified` means the site artifact itself
built successfully.

## Deployment

`.github/workflows/site.yml` validates the site on relevant pull requests.

After a relevant change reaches `main`, the same workflow:

1. checks out full Git history;
2. installs the pinned site dependencies;
3. generates the public status artifact;
4. type-checks and builds the Vite site;
5. uploads the static artifact;
6. deploys with GitHub's Pages deployment action.

GitHub Pages must be configured to use **GitHub Actions** as the Pages source.

## Local development

From the repository root:

```bash
cd site
npm install
npm run dev
```

Production build:

```bash
npm run build
```

The Vite base path is `/PhiOS/`, matching the repository project-page path.
