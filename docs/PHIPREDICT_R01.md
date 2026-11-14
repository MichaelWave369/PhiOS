# ΦPredict R0.1 · Governed Prediction Ledger

**Status: experimental offline CI prediction evaluation, not active inference or
a biological-brain model.** Implemented in PhiOS as `phios/predict.py`.
No new dependencies, model weights, credentials, network access, or hooks into
live PhiOS authority, memory, or routing. The module deliberately does not
modify any existing runtime behavior.

## Question

Can explicitly registered, pre-run binary predictions of GitHub Actions
workflow success outperform a fixed 50% probability baseline on a
separately declared holdout cohort? This is an *engineering measurement*
of prediction error, not evidence for the neuroscientific free-energy
principle or a claim of autonomous intelligence.

## Local first: PowerShell example

Run in a PhiOS checkout with Python 3.11+. Use a fresh, nonsecret location
for the ledger. The commit SHA must be the **exact planned workflow head**;
the workflow name must exactly match the GitHub Actions API `name`.

~~~powershell
$ledger = ".\phipredict-ledger.jsonl"
python -m phios.predict --ledger $ledger register --id trial-001 --repo MichaelWave369/PhiOS --sha "REPLACE_WITH_40_CHARACTER_COMMIT_SHA" --workflow "CI" --probability 0.65 --cohort holdout

# Start or wait for the matching workflow AFTER the prediction is committed.
# Fetch completed run evidence separately. This CLI never accesses GitHub.
gh api repos/MichaelWave369/PhiOS/actions/runs/RUN_ID > run.json
python -m phios.predict --ledger $ledger observe --id trial-001 --run-json run.json
python -m phios.predict --ledger $ledger verify
python -m phios.predict --ledger $ledger report
~~~

`gh` is optional and external to PhiOS. For the initial experiment the
operator explicitly supplies the GitHub Actions API workflow-run JSON.
`run.json` must include: `id`, `name`, `repository.full_name`, `head_sha`,
`status` (`completed`), `conclusion`, canonical `html_url`, and an
offset-aware `run_started_at`. A completed workflow cannot start after the
local observation time. Identity mismatches, unfinished runs, duplicate
targets, duplicate outcomes, malformed JSON and inconsistent hashes HOLD.

## Predictions

Each prediction defines:
- A unique prediction ID, owner/repo, 40-hex commit SHA, exact workflow name.
- A numeric probability that the **completed workflow will conclude success**,
  from 0 to 1, registered by the operator *before* workflow execution.
- `pilot` or operator-declared `holdout` cohort.
- Local registration timestamp.

An observation is a separate append event with the GitHub run ID, conclusion,
workflow start time, canonical run URL and SHA-256 of the supplied raw JSON
bytes. The module never triggers workflows, edits code, requests model drafts,
or takes recovery actions.

## Evidence and scoring

- Every local JSONL event has a sequential number, previous hash and hash of
  its canonical content. The ledger is *logically* append-only, written via
  an atomic replacement and a fail-closed local lock. No event may be edited
  or deleted through the API.
- The chain detects changes within the retained local file. **It is not a
  digital signature, external timestamp, authenticated GitHub observation,
  or proof the original file has not been replaced in its entirety.**
- Only `holdout` entries with success/failure outcomes and a locally
  timestamped prediction *earlier* than the GitHub-declared start time score.
  Late predictions and neutral/cancelled/skipped runs are excluded explicitly.
- Binary Brier error is `(p - observed_success)^2`; lower is better.
  Fixed baseline `p=0.5` yields 0.25 Brier error for every binary result.
  Report also includes five calibration bins with counts, mean forecast and
  empirical success frequency. These are descriptive statistics.
- Fewer than 20 eligible holdout observations: `HOLD_INSUFFICIENT_HOLDOUT`.
  At 20+ observations, a lower mean Brier is labeled
  `DESCRIPTIVE_LOWER_ERROR_NOT_VALIDATED`, not scientific superiority.
  No confidence interval, significance, base-rate adjustment, leakage
  attestation, or drift detection is implemented yet.

**Important:** `holdout` is a user-declared label, not proof of blinding or
independence. Local time can be changed. GitHub run JSON can be fabricated,
modified, or saved after the fact. For credible evaluation, freeze a prediction
before run creation, preserve the file and optionally anchor its digest
externally, exclude training examples, and collect independent verification
of run identity/timing. This rung does not claim those controls.

## Fail-closed and offline boundaries

- No network or secrets handling.
- No writing to PhiOS governed memory, ledger, or other repositories.
- No model routing, auto-training, CI triggering, GitHub modifications,
  autonomous remediation, permission grants, or action authority.
- Two size caps: 8 MB for the event ledger, 2 MB per input run JSON.
- The `.lock` file prevents concurrent local writes. After a crash, inspect
  the ledger before manually removing a stale lock. Do not run two writers
  from different machines sharing the same folder.
- Store the ledger privately if repo names, workflow names or workflow timing
  could be sensitive. Do not commit it to a public repository.

## Tests and future gates

~~~bash
python -m pytest -q tests/test_predict_r01.py
python -m phios.predict --ledger ./phipredict-ledger.jsonl verify
python -m phios.predict --ledger ./phipredict-ledger.jsonl report
~~~

R0.2 candidates: independent GitHub run verification with operator-approved
read-only transport; signed/externally anchored prediction commitments;
prequential historical-rate comparator; frozen evaluation split and
leakage/selection audit; rolling reliability visualization. Only after
measured improvements should any advisory-only connection to PhiReflex,
Agentora, PhiDiscovery, or PhiMemory9 be considered.
