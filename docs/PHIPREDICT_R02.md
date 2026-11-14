# ΦPredict R0.2 · Public GitHub Source Verification

**Status: experimental and opt-in.** This rung adds one read-only live GitHub
API check to the existing R0.1 offline ledger. It is *not* active inference,
autonomous learning, cryptographically authenticated preregistration, or
permission to take actions.

## Purpose

R0.1 can score an operator-supplied saved GitHub Actions run JSON document.
That document can be wrong, edited, stale or fabricated.

R0.2 adds a separate, explicit evidence check against the public GitHub REST
Actions run endpoint for the exact already recorded repository and run ID.
It matches:

- owner/repo, workflow name, full commit SHA, canonical GitHub URL and run ID
- final workflow status and exact conclusion
- run start timestamp against the existing recorded observation
- run creation timestamp, which must precede the workflow start
- attempt number, which must equal **1**. A rerun is held in R0.2, not
  silently equated with the first run's outcome.

The checked API response is not stored in the ledger. Its raw bytes are hashed,
and the check's local timestamp, creation timestamp, run attempt and identity
are recorded in a new hash-linked *github_verification* event.

## Use (PowerShell)

Run in a PhiOS checkout on Python 3.11+ after R0.1 registration and observation:

~~~powershell
$ledger = ".\phipredict-ledger.jsonl"
# Check the existing ledger offline, no network:
python -m phios.predict --ledger $ledger verify

# One explicitly approved read-only request to api.github.com:
python -m phios.predict_source --ledger $ledger verify-github --id trial-001 --allow-public-network

# This report is offline; it does not contact GitHub:
python -m phios.predict_source --ledger $ledger verified-report
~~~

The command makes one unauthenticated HTTPS GET to exactly
`https://api.github.com/repos/OWNER/REPO/actions/runs/RUN_ID`, derived from
the validated ledger. It never accepts a user-supplied remote URL, sends
credentials, follows redirects, uses environment proxies, or requests other
GitHub endpoints. It requires a **public** repository/run. Private repos,
rate limits, non-JSON responses, missing fields, incomplete runs, reruns,
mismatches, request failures and oversized responses fail closed; the operator
can inspect the circumstances instead of getting a claimed verification.

R0.1 commands remain offline and unchanged. No global background checking.

## New verified-only calibration report

`verified-report` scores only observations that:

1. Were initially designated `holdout` by the operator.
2. Have a corresponding immutable earlier R0.1 observation event.
3. Have one consistent `github_verification` event.
4. Have a locally recorded prediction timestamp **earlier** than the
   GitHub-reported workflow *creation* time, not merely its start.
5. Have a success/failure conclusion, not cancelled or skipped.

It reports a count, excluded reasons, average binary Brier error and the
fixed 0.5-probability baseline of 0.25. With fewer than 20 eligible
observations the verdict is `HOLD_INSUFFICIENT_VERIFIED_HOLDOUT`. Above
that threshold the verdict is still **descriptive**, never independent
statistical validation or proof of improved intelligence. The original
R0.1 report remains separately available and is not silently relabeled
as verified.

## Important verification and security limits

- HTTPS to GitHub is stronger than trusting a saved local file, but API
  observations are still **not signed attestations of model performance**.
  The response may change if GitHub reruns or updates a workflow.
- A local prediction timestamp is **not externally anchored**. Even
  GitHub's independently reported creation timestamp cannot prove that the
  local forecast was committed earlier. The report names this limitation.
- A SHA-256 chain detects non-coherent local edits only if the original chain
  head is independently retained. An attacker controlling the whole file
  can regenerate the ledger.
- Cohort assignment is not proof of an untouched or unbiased holdout set.
  Scores are not adjusted for model selection, pretraining leakage, baseline
  class frequency, overlapping workflows, retries or drift.
- The live verifier has no authority to run CI, create issues or PRs, install
  software, retrain a model, apply repairs, merge, or change PhiOS routing.
- Public-only transport is intentional. Do not paste access tokens into
  arguments, environment variables or files to work around private repo
  failures. No credentials are needed for this rung.

## Development

~~~bash
python -m pytest -q tests/test_predict_r01.py tests/test_predict_r02.py
ruff check phios/predict.py phios/predict_source.py tests/test_predict_r01.py tests/test_predict_r02.py
mypy phios/predict.py phios/predict_source.py --ignore-missing-imports
~~~

R0.3 should focus on reproducible externally anchored prediction commits,
prequential empirical base-rate comparison (rather than only p=0.5),
evaluation cohort freezing, leakage review, uncertainty intervals, and
read-only calibration visualization. No authority promotion from scores.
