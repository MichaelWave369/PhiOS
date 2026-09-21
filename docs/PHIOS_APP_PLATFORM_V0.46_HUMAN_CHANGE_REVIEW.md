# PhiOS App Platform v0.46 — Human Release Change Review / Acceptance Record

## Status

Alpha contract.

Schema:

- phios.release_change_acceptance.v0.1

Runtime surfaces:

- phios.apps.release_review
- phi-app accept-release-changes

## Purpose

v0.46 records a human acknowledgement of one exact v0.45 release-change evidence object.

The central rule is:

> Human acknowledgement records review. It does not create a compatibility verdict and it grants no operational authority.

v0.46 does not build, install, grant permissions, switch desktop launchers, or execute an update.

## Input

The operator supplies:

1. one phios.release_change_evidence.v0.1 object;
2. the exact operator-approved v0.45 evidence SHA-256;
3. explicit acknowledgements for every observed non-unchanged change;
4. an optional bounded review note.

The v0.45 object is strictly reconstructed before review.

Unknown fields, malformed nested markers, authority-bearing evidence, or digest mismatch fail closed.

## Exact acknowledgement rule

Acceptance requires exact equality between the v0.45 evidence and the supplied acknowledgement sets.

The operator must acknowledge every observed manifest change label.

The operator must separately acknowledge every permission addition and every permission removal.

The operator must acknowledge every source marker whose v0.45 state is:

- added;
- removed;
- changed;
- type_changed.

A source marker with state unchanged requires no acknowledgement.

## Marker syntax

CLI marker acknowledgements use:

    PATH=CHANGE

Examples:

    package.json=changed
    package-lock.json=removed
    index.html=added

The accepted change names are exactly:

- added
- removed
- changed
- type_changed

An unchanged acknowledgement is rejected because unchanged is not an observed change requiring acceptance.

## Exact means exact

Acceptance fails when acknowledgements are:

- missing;
- extra;
- duplicated;
- stale relative to a different evidence digest;
- attached to a tampered v0.45 payload.

This prevents a broad acknowledgement such as "looks fine" from silently covering changes the operator never actually reviewed.

## Acceptance semantics

A successful record fixes:

    review_scope = observed_changes_only
    review_state = accepted_for_further_review
    compatibility_verdict = not_assessed
    permission_grant_authority = false
    build_authority = false
    install_authority = false
    update_authority = false

accepted_for_further_review means only that the operator has acknowledged the exact observed changes and permits the candidate to remain under consideration.

It does not mean the candidate is compatible, secure, recommended, deployable, or authorized for mutation.

## Record identity

The canonical acceptance record binds:

- release_change_evidence_sha256;
- app ID;
- repository URL;
- active version;
- candidate version;
- active commit SHA;
- candidate commit SHA;
- exact acknowledged manifest changes;
- exact acknowledged permissions added;
- exact acknowledged permissions removed;
- exact acknowledged non-unchanged source-marker changes;
- optional bounded review note;
- fixed review/no-authority fields.

Acknowledgement arrays are canonically sorted and may not contain duplicates.

The record SHA-256 is computed from canonical JSON.

## Strict reconstruction

phios.release_change_acceptance.v0.1 supports strict from-dict reconstruction.

A record is rejected if:

- required fields are missing;
- unknown fields are present;
- acknowledgement arrays are unsorted or duplicated;
- authority fields are non-boolean or true;
- review scope/state change;
- compatibility verdict changes;
- canonical digest does not match.

This allows later App Platform rungs to consume the acceptance record without relying on informal JSON conventions.

## CLI

Example:

    phi-app accept-release-changes \
      release-change-evidence.json \
      --approve-release-change-evidence-sha EXACT_SHA \
      --ack-manifest-change version_changed \
      --ack-manifest-change permissions_changed \
      --ack-permission-added workspace.read \
      --ack-marker-change package.json=changed

The command prints the canonical acceptance record.

It does not persist an execution grant, mutate the active app, or call the update service.

## Optional review note

--review-note may carry a bounded human note.

The note is included in the acceptance-record digest but carries no authority and is not interpreted by PhiOS as evidence of compatibility.

## No-change evidence

If the v0.45 evidence contains no manifest changes, no permission changes, and no non-unchanged marker changes, v0.46 may create an acceptance record with empty acknowledgement sets.

This still means only that the operator reviewed that exact evidence object.

## Relationship to v0.45

v0.45 answers:

    What bounded structural differences were observed?

v0.46 answers:

    Did a human explicitly acknowledge exactly those observed differences?

Neither answers:

    Is this candidate compatible?
    Should it be installed?
    May it update the active app?

## CI verification model

v0.46 tests cover:

- exact acknowledgement success;
- unchanged markers excluded from acknowledgement requirements;
- missing manifest acknowledgement rejection;
- missing added-permission acknowledgement rejection;
- missing removed-permission acknowledgement rejection;
- missing marker acknowledgement rejection;
- extra invented acknowledgement rejection;
- duplicate acknowledgement rejection;
- stale operator digest rejection;
- tampered v0.45 evidence rejection;
- strict acceptance-record round trip;
- acceptance-record tamper rejection;
- PATH=CHANGE parser validation;
- no-change evidence review;
- fixed not_assessed compatibility verdict;
- zero permission/build/install/update authority.

## Explicit non-capabilities

v0.46 does not:

- infer compatibility;
- score compatibility;
- recommend an update;
- grant a new app permission;
- grant build authority;
- grant install authority;
- grant update authority;
- bypass v0.43 lifecycle gating;
- bypass v0.27 source approval;
- bypass later build/install/update review.

## Planned next rung

A future v0.47 can add a **Candidate Advancement Gate** that requires the exact v0.46 acceptance record before the selected release candidate may proceed into a newly planned build/install/update workflow.

That gate should still create no execution authority by itself. It should only prove that the human review prerequisite was satisfied for the exact candidate evidence chain.
