# PhiOS App Platform v0.46

**Human acknowledgement is not compatibility authority.**

v0.46 adds a deterministic human review record for one exact v0.45 release-change evidence object.

The operator must approve the exact v0.45 digest and explicitly acknowledge every observed non-unchanged change:

- manifest change labels;
- permissions added;
- permissions removed;
- source-marker changes.

A stale digest, missing acknowledgement, extra invented acknowledgement, duplicate acknowledgement, or tampered v0.45 artifact fails closed.

## Operator flow

    phi-app accept-release-changes \
      release-change-evidence.json \
      --approve-release-change-evidence-sha EXACT_SHA \
      --ack-manifest-change runtime_changed \
      --ack-manifest-change version_changed \
      --ack-permission-added workspace.read \
      --ack-marker-change package.json=changed

The exact flags required depend on the exact v0.45 evidence.

Unchanged source markers do not require ceremonial acknowledgement because v0.46 is about acknowledging observed changes, not clicking through facts that did not change.

## Meaning of acceptance

The record means:

    I reviewed these exact observed changes
    and accept this candidate for further review.

It does not mean:

    the candidate is compatible
    the candidate is safe
    permissions are granted
    build is authorized
    install is authorized
    update is authorized

Every record fixes:

    review_scope = observed_changes_only
    review_state = accepted_for_further_review
    compatibility_verdict = not_assessed
    permission_grant_authority = false
    build_authority = false
    install_authority = false
    update_authority = false

## Exact binding

The acceptance record binds:

- the exact v0.45 evidence SHA-256;
- app identity;
- repository;
- active and candidate versions;
- active and candidate exact commits;
- the complete acknowledged manifest-change set;
- the complete acknowledged permission-addition set;
- the complete acknowledged permission-removal set;
- the complete acknowledged non-unchanged marker-change set;
- optional bounded review note.

The record itself is canonical JSON with its own SHA-256 and strict round-trip validation.

## Detailed contract

See [docs/PHIOS_APP_PLATFORM_V0.46_HUMAN_CHANGE_REVIEW.md](docs/PHIOS_APP_PLATFORM_V0.46_HUMAN_CHANGE_REVIEW.md).
