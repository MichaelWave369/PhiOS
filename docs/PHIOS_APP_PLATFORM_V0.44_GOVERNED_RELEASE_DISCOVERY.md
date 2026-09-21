# PhiOS App Platform v0.44 — Governed Release Discovery / Candidate Selection

## Status

Alpha contract.

Schemas:

- phios.release_discovery.v0.1
- phios.release_candidate_selection.v0.1
- phios.release_candidate_intake.v0.1

Runtime surfaces:

- phios.apps.release_discovery
- phi-app discover-releases
- phi-app select-release
- phi-app inspect-selected-release

## Purpose

v0.44 lets PhiOS observe bounded GitHub Release evidence for one currently active governed desktop app, let the operator explicitly select one exact release, and then re-enter the existing v0.26/v0.27 intake/acquisition pipeline at that release's exact commit.

The central rule is:

> Discovery can reveal capability. Selection can record intent. Neither grants update authority.

v0.44 does not download source archives, build, install, switch desktop launchers, or invoke the v0.40 update service.

## Starting boundary

Release discovery starts from one active governed desktop bundle.

Before network discovery, PhiOS revalidates the exact desktop bundle, active launch grant, installed ancestry, current desktop-entry digest, installed .phios/manifest.json, install-receipt manifest digest, and app ID/version agreement.

The source repository comes from the installed manifest and must be a canonical public GitHub repository URL. The operator does not supply an arbitrary repository URL when asking whether one installed app has releases.

## Network boundary

The built-in release provider uses bounded HTTPS requests only to api.github.com for repository metadata, the first Releases response, tag refs, and bounded annotated-tag dereference.

v0.44 observes at most eight releases. There is no pagination.

Persisted release evidence contains only:

- GitHub release ID
- provider position
- tag name
- bounded release name
- bounded published-at string
- draft flag
- prerelease flag
- exact resolved commit SHA

Release body text, assets, author profiles, reactions, arbitrary provider fields, and release download URLs are excluded.

## Exact tag-to-commit resolution

A Release tag is not accepted as a commit identifier.

For each release PhiOS resolves:

    release tag
        ↓
    git/ref/tags/TAG
        ↓
    commit

Annotated tags are dereferenced through bounded git/tags object reads until an exact commit is reached. Unsupported object types or excessive dereference depth fail closed.

## Provider order is not ranking

Each discovery states:

    ordering_semantics = provider_order_only

Provider position records the order GitHub returned. PhiOS does not claim that position zero is newest, best, safest, compatible, or recommended.

v0.44 performs no SemVer ranking, date ranking, compatibility ranking, or security ranking.

No release is automatically selected.

## Discovery identity and authority

The release-discovery digest binds the active app ID, installed version, repository, active governed bundle path, active grant digest, archived state, ordered bounded release evidence, provider request count, and provider-order-only semantics.

Discovery always carries:

    selection_authority = false
    acquisition_authority = false
    update_authority = false

## Explicit candidate selection

Selection requires:

1. the exact release-discovery JSON;
2. the exact approved discovery SHA-256;
3. one explicit tag name.

Example:

    phi-app select-release       release-discovery.json       --tag v2.0.0       --approve-release-discovery-sha EXACT_DISCOVERY_SHA

The tag must identify exactly one observed release.

Draft releases cannot be selected.

Prereleases require an additional explicit --allow-prerelease flag.

Prerelease opt-in is candidate policy only. It grants no build, install, acquisition, or update authority.

## Candidate-selection record

The selection binds the discovery SHA, app ID, currently installed version, repository URL, release ID, exact tag, exact commit SHA, and prerelease flag.

It records:

    candidate_selected = true
    acquisition_authority = false
    build_authority = false
    install_authority = false
    update_authority = false

## Exact-commit intake

The selected release can be inspected with:

    phi-app inspect-selected-release       release-selection.json       --approve-release-selection-sha EXACT_SELECTION_SHA

This extends the bounded v0.26 provider with exact-commit inspection.

Exact-commit intake:

1. re-reads public repository metadata;
2. asks GitHub for the exact selected commit;
3. requires the returned commit SHA to equal the selection;
4. reads the bounded root listing at that commit;
5. reads the same bounded known discovery files at that commit;
6. runs the existing v0.26 analyzer.

It does not inspect default-branch content and pretend those bytes belong to the selected release.

## App identity continuity

If exact-commit intake produces a manifest candidate, its app_id must match the active app identity from the release selection.

A release that changes PhiOS app identity fails the v0.44 candidate-intake bridge.

Version ordering is still not interpreted here. The existing v0.40 update contract remains responsible for requiring a different candidate version.

## v0.27 acquisition bridge

v0.44 wraps exact-commit v0.26 output in a phios.release_candidate_intake.v0.1 envelope.

The envelope binds the exact selection, exact intake result, and a canonical envelope SHA-256.

The existing v0.27 review_intake_for_acquisition recognizes this envelope, validates repository continuity, selected commit against intake evidence head SHA, app identity, and envelope digest, then continues through the ordinary acquisition review.

Source acquisition still requires the existing explicit exact commit approval and exact manifest SHA-256 approval.

v0.44 does not create a second source downloader.

## End-to-end flow

    active governed app
        ↓
    discover-releases
        ↓
    human reviews bounded evidence
        ↓
    select-release + exact discovery digest
        ↓
    inspect-selected-release + exact selection digest
        ↓
    v0.26 exact-commit intake
        ↓
    v0.27 review and source acquisition
        ↓
    existing build/install pipeline
        ↓
    separately reviewed v0.40 update

## v0.43 interaction

v0.43 blocks destructive lifecycle mutation when cleanup evidence is unresolved.

v0.44 discovery, selection, and exact-commit intake are read-only and may still occur. The unresolved transition must still be reconciled before later update, rollback, or cleanup execution.

## CI verification model

v0.44 tests cover:

- bounded provider-order preservation
- lightweight tag resolution
- annotated tag resolution
- discovery digest approval
- explicit tag selection
- no automatic provider-order ranking
- prerelease opt-in
- draft rejection
- duplicate-tag ambiguity rejection
- zero mutation authority in discovery/selection
- exact-commit intake without default-branch drift
- exact selection digest approval
- app identity continuity
- candidate-envelope validation
- direct compatibility with v0.27 acquisition review

## Explicit non-capabilities

v0.44 does not automatically select a release, compare versions, infer compatibility, inspect changelog prose for trust, infer security quality, download release assets, acquire source, build, install, change the active desktop entry, grant update authority, bypass v0.27 approvals, or bypass v0.43 lifecycle gating.

## Planned next rung

v0.45 should add a Release Compatibility / Change Evidence Contract.

That rung can compare the active manifest/build shape against the explicitly selected exact-commit candidate and produce bounded structural compatibility evidence without authorizing update. Changelog prose remains untrusted, observed structural changes remain separate from inferred risk, and human review remains the bridge into the existing build/install/update workflow.
