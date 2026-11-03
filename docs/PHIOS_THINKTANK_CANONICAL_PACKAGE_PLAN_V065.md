# PhiOS v0.65: ThinkTank canonical package-plan review gate

**Status: review only. Source candidate remains HELD. No production or guest
ThinkTank installation is qualified.**

## What was actually connected

PR #368 proved the *real pinned* ThinkTank offline React `dist/` bytes can be
translated to canonical PhiOS `PackageArtifact` paths, sizes, and SHA-256
inventory. That hosted build's receipt is **not** a PhiOS build execution
receipt, npm offline build receipt, or an install authorization.

`scripts/thinktank_package_plan_gate.py` bridges the last **schema and data
integrity gap** before an operator can review an install proposal. It requires
three independent inputs:

1. The v0.64 ThinkTank `thinktank-preinstall-handoff.json`, produced from
   the actual offline compiled files. It must remain
   `REVIEW_ONLY_VERIFIED_DIST_NOT_INSTALL_APPROVAL`.
2. An actual PhiOS v0.29/v0.49 **build-execution receipt**, produced by its
   existing governed build service.
3. An actual PhiOS v0.32 **npm-offline-build receipt**, produced by its existing
   network-denied sandbox and cache service.

The gate reuses PhiOS's production
`SuccessfulBuildBinding.from_payloads()`, `plan_build_package()`, and
`review_build_package()`. It also independently verifies the file closure,
root-relative Vite asset links, SHA-256 content, and path safety of the
*actual installed-workspace candidate bytes*, rather than simply accepting
the execution receipt's self-reported artifact hash.

The proposed package plan is generated through an **ephemeral** registry.
There is no persistent `AppRegistry.save()`, no app installation, and no
operator approval issued or simulated in production.

## Example review command (requires separately produced PhiOS receipts)

```bash
python scripts/thinktank_package_plan_gate.py \
  --handoff /private/review/thinktank-preinstall-handoff.json \
  --execution-receipt /private/review/real-build-execution-receipt.json \
  --offline-receipt /private/review/real-npm-offline-receipt.json \
  --output /private/review/thinktank-package-plan-review.json
```

The command exits nonzero for missing receipts, incorrect schemas, duplicate
JSON fields, source/manifest/commit drift, bad network denial, missing or
extra files, altered static links, changed bytes, and false authority.

A successful response means only:
`CANONICAL_PHIOS_PACKAGE_PLAN_REVIEW_ONLY`. The result includes a canonical
`package_plan` and `package_review` with an exact plan digest that can be
**considered** by an authorized operator. No executable or install effect is
triggered.

**Important limitation:** a hash-consistent pair of JSON receipts is not
independent proof of the receipts' producer identity. This gate does not
cryptographically attest who ran the actual build. Producer provenance, audit
review, and approvals remain separate.

## Test scope

```bash
pytest -q tests/test_thinktank_package_plan_gate.py
```

The tests construct **synthetic** canonical PhiOS receipts. They exercise
`plan_build_package()` and the **real** `AppInstallService.install()` on a
temporary directory with *only synthetic HTML/JS fixtures*, testing that a
wrong package-plan approval fails and a matching *test fixture* approval still
produces `launch_authority=False`.

This is not installing ThinkTank in a PhiOS image or proving source builder
provenance. A passing Python test and green CI are not permission to approve
an app, and must not be described as successful real guest execution.

## Remaining P0/P1 acceptance gates

1. Resolve third-party licensing/redistribution and source/native binary
   provenance gaps from the pre-existing PhiOS release preflight. No public
   app bundle, npm cache, or compiled third-party assets until approved.
2. Actually produce the authentic PhiOS build execution and offline build
   receipts for the exact reviewed commit
   `655d96f7ff892c9989f75cf874e74689f7694127`. The held candidate
   explicitly excludes the optional later PhiServe backend.
3. Reconcile the verified asset set with those receipts using this gate.
   Refuse if outputs differ; do not fake receipt digests or claim
   reproducibility from one build.
4. Obtain explicit, exact operator review/approval for a **disposable
   installed x86_64 PhiOS guest only** and the required package and desktop
   permissions. No automatic promotion from catalog status.
5. Run the existing `AppInstallService`, v0.35 static adapter and v0.38
   desktop launch service in an isolated test guest, observe actual visible
   UI, reboot/persistence, then separately exercise v0.40 update/rollback.
6. Retain only sanitized hash-bound receipts, independent no-ISO boot proof,
   denied provider/network actions, and human approval references.

Next shippable milestone is **a genuinely launched, reviewed ThinkTank UI in
a disposable PhiOS VM**. This PR helps verify its input but does not claim to
achieve that milestone.

Ledger Above Ego. DONE Means Verified.
