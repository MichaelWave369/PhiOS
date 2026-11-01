# PhiOS Rung 8: PhiVine advisory intake (review-only)

Contract: phios.phivine_advisory_review.v0.1
Producer: phivine.phios_advisory.v0.1 (https://github.com/MichaelWave369/PhiVine)

Status: native Python CLI review ONLY, no binary import, installation, compatibility approval, or Windows execution.

## Operator workflow

On Linux with PhiVine, generate an advisory file:

    PYTHONPATH=src python -m phivine plan ./legacy.exe > proposal.json
    PYTHONPATH=src python -m phivine phios-handoff proposal.json > phivine-handoff.json

The PhiVine handoff command intentionally exits 3 even for valid held evidence. Automation should separately parse the JSON and not treat the exit code as permission or general failure-free success.

PhiOS can review that local JSON with its existing App Platform entrypoint:

    phi-app review-phivine phivine-handoff.json

The PhiOS side does not require PhiVine installed to review a produced file. It performs bounded read-only JSON validation and emits a review record. **The command always exits 3**. Valid Rung 7 evidence produces status HELD_NATIVE_WINDOWS_BINARY_INTAKE_UNAVAILABLE. Invalid, unknown, forged or tampered records produce HELD_INVALID_OR_UNTRUSTED_PHIVINE_ADVISORY.

No Windows binary, Wine, untrusted shell command, network client, installer, registry mutation, execution backend or authority service is invoked. Input is limited to 64 KiB; symlink inputs are refused.

## Strict input checks

- Exact version, producer, target and handoff type; required and no unknown fields.
- SHA-256-derived handoff checksum. This is **not** a signature or trusted origin attestation. Anyone could recompute it.
- Artifact digest/size/candidate type and safe basename, without absolute local paths.
- Network request restricted to deny_requested or operator_review_requested; no arbitrary filesystem access.
- Exactly nine unmet Rung 7 gates, including a separate native Windows binary intake.
- Every producer authority value is literally false, not zero or an equivalent string.
- Boolean observation flags must match their corresponding source, staged and runner status.
- PhiVine producer-invalid proposals are kept invalid, not promoted to displayable artifact evidence.

The generated PhiOS review is deterministic and separately has constant-false app registry, install, launch, consent, effect lease and execution flags. Even successful checks do not change those flags.

## Separate input category

The existing PhiOS App Platform v0.58 profiles PUBLIC GITHUB SOURCE REPOSITORIES using schemas phios.repo_profile.v0.1 and phios.repo_compatibility.v0.1. A PhiVine handoff instead concerns one LOCAL WINDOWS BINARY CANDIDATE. It cannot become SUPPORTED_AFTER_OPERATOR_APPROVAL or automatically enter the repository build/install pipeline.

This Rung 8 PR adds a producer-compatible consumer and a review CLI, not a native Windows binary registration workflow or a PhiOS authorization API. The Linux release contract still requires an independently qualified restricted broker, sandbox, genuine consent and effect-bound leases before real Windows execution.

## Testing

    python -m pytest tests/test_phivine_advisory_intake.py tests/test_phivine_advisory_cli.py -q

Tests include complete matching evidence, tampered checksums, recomputed forged approvals, changed permissions, invalid formats, status/flag inconsistencies, path injection, size limits, missing files, symlinks, malformed JSON and CLI held exit codes.

PhiOS original code and PhiVine original code are MIT; external Wine/Proton dependencies keep their own licensing.
