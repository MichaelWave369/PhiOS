# PhiOS R0.1: complete public inventory and honest source-family notes

**Date:** 2026-10-28
**Status:** Source-only catalog update and pinned README declarations; NOT an installation, offline app pack, local mirror, or Linux OS release.

## Observed owner inventory

The connected owner's fully paginated repository list returned **229** repositories: **194 public** and **35 private**. This change republishes only the 194 entries independently confirmed as visibility=public and exact owner `MichaelWave369`. The previous committed offline public snapshot held 132 entries. All 62 newly visible public repositories were added. Private repository names and contents were not added to the public snapshot, README review notes, public UI, or documentation.

The catalog uses provenance tag `GITHUB_CONNECTED_OWNER_PUBLIC_FILTERED_SNAPSHOT` because its data came from the owner-connected GitHub repository inventory filtered by explicit public visibility, **not** from the unauthenticated public REST owner endpoint. An explicitly operator-triggered `--refresh` continues to use the actual public REST endpoint and emits the existing `GITHUB_PUBLIC_OWNER_API_SNAPSHOT` source marker. Both snapshots must remain fail-closed, case-insensitively unique, deterministic, and public-only.

Each catalog entry remains exactly:
- `kind: source_catalog_entry`
- `availability: SOURCE_ONLY`
- `installed: false`
- `launch_authorized: false`
- `redistribution_reviewed: false`

## Source-family notes, not software qualification

`phishell/src/ecosystem/source-reviews.json` records **nine** pinned project README family notes covering PhiOS, GitPorch, PhiARK, Infinite-Porch, PhiOS-XR, SuperPhiVessel, think-tank, BTM and LENZ. Each includes a pinned Git commit SHA and an exact owner/repo/commit README link. Families are descriptive only: OS_CORE, LOCAL_SERVICE, KNOWLEDGE_TOOL, WEB_APP, GAME, XR_APP. The other **185** public entries remain **UNREVIEWED** by default, rather than being guessed into an app category.

A README assertion is **not** a code audit. Even these nine do not receive any verified offline-runnable, installed, launch-authorized, or redistribution-reviewed claim. The runtime/AppManifest gates in PhiOS v0.25-v0.58 remain distinct, as do first-wave Vessie/ThinkTank held application proposals.

The source-review manifest has a fail-closed schema with exact public-catalog membership, sorted unique names, pinned 40-hex source commits, exact same-owner/commit `README.md` URLs, and only fixed false authority fields. Unknown keys, foreign or uncataloged names, unpinned evidence, modified review claims and forged grants fail validation.

PhiShell's existing **Φ ECOSYSTEM** view now shows source family, UNREVIEWED fallback, and links to exact pinned README evidence. **README-CLASSIFIED** and **UNREVIEWED** filters never install, launch or copy code. Browsers are not allowed to infer an app's offline readiness from source family.

## Verification

Run without network access from repo root:

```sh
python scripts/sync_public_ecosystem_catalog.py --check
python -m scripts.verify_ecosystem_source_reviews
python -m unittest discover -s tests -p "test_public_ecosystem_catalog.py" -v
python -m unittest discover -s tests -p "test_ecosystem_source_reviews.py" -v
python scripts/verify_ecosystem_app_candidates.py
cd phishell
npm ci --no-audit --no-fund
npm test
npm run build
```

GitHub's existing `public-ecosystem-catalog.yml` workflow now runs the extra review gate and verifies built PhiShell assets contain the new labels.

## Boundaries and next milestone

This PR does **not** prove any repository has been cloned, mirrored, installed, built or booted on a device. Existing ISO files do not automatically acquire the new catalog; only an independently qualified new PhiShell/ISO build can ship it.

**R0.2 recommendation:** Use GitPorch's operator-controlled local mirroring and snapshot facilities for source preservation. Independently account for full refs, Git LFS, submodules, release assets, offline dependency caches, backup rotation and restoration after physical WAN disconnect. The 35 private repositories require a separate private authenticated mirror inventory and must never enter the public site or redistributable ISO by default.

**Ledger Above Ego. DONE Means Verified.**
