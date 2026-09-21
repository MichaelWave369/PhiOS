# PhiOS App Platform v0.44

**Governed release discovery without automatic update authority.**

v0.44 completes the next outward-facing loop in the PhiOS App Platform.

An already installed and active governed app can now be checked for bounded public GitHub Release evidence. PhiOS resolves each observed release tag to an exact commit, records provider order without treating it as a recommendation, and requires the operator to select one exact candidate by tag and discovery digest.

The selected candidate is then inspected at its exact commit using the existing v0.26 bounded intake logic and wrapped so the existing v0.27 acquisition review can consume it normally.

The authority chain remains:

    release exists
    ≠ candidate selected
    ≠ source acquired
    ≠ built
    ≠ installed
    ≠ update authorized

## Operator flow

    phi-app discover-releases ACTIVE_BUNDLE_PATH
            ↓
    review release-discovery SHA and bounded evidence
            ↓
    phi-app select-release release-discovery.json
      --tag EXACT_TAG
      --approve-release-discovery-sha EXACT_SHA
            ↓
    phi-app inspect-selected-release release-selection.json
      --approve-release-selection-sha EXACT_SHA
            ↓
    existing v0.27 review / acquire-github
            ↓
    existing build and install pipeline
            ↓
    separately reviewed v0.40 update

No release is automatically selected.

GitHub provider ordering is preserved as evidence only. v0.44 performs no SemVer ranking and does not call any candidate latest, best, safest, or recommended.

Draft releases cannot be selected. Prereleases require explicit opt-in.

## Exact revision rule

A release tag is resolved through GitHub Git refs to an exact commit SHA. Annotated tags are dereferenced with a fixed bound.

The selected release is then re-inspected at that exact commit. Default-branch content is not substituted.

## Lifecycle safety

v0.43 remains the destructive lifecycle gate. Release discovery, selection, and intake are read-only, but unresolved lifecycle evidence still blocks later update/rollback/cleanup mutation.

## Detailed contracts

- [v0.44 governed release discovery](docs/PHIOS_APP_PLATFORM_V0.44_GOVERNED_RELEASE_DISCOVERY.md)
- [v0.43 unresolved lifecycle gate](docs/PHIOS_APP_PLATFORM_V0.43_UNRESOLVED_LIFECYCLE_GATE.md)
- [v0.42 cleanup reconciliation](docs/PHIOS_APP_PLATFORM_V0.42_CLEANUP_RECONCILIATION.md)
- [complete App Platform trail](docs/README.md#app-platform-version-trail)
