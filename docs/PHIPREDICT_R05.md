# ΦPredict R0.5: current-state audit of public forecast commitments

**Experimental, opt-in and strictly read-only.** This does not schedule
checks, publish, edit, merge, retrain, or promote model actions.

## Why add R0.5?

R0.4 verified the public GitHub issue comment **once** and recorded a
hash-linked local receipt. Afterward, an operator can edit or delete the
comment, or someone can rerun the associated GitHub Actions job.
R0.4's local receipt is still historically meaningful, but it cannot
tell us whether those public records **remain the same right now**.

R0.5 checks a single registered, completed, R0.2-verified and
R0.4-anchored prediction against the two public sources again.

## One explicit audit

~~~powershell
$ledger = ".\phipredict-ledger.jsonl"

# No network by default: this fails closed.
python -m phios.predict_audit --ledger $ledger --id run-001

# Operator explicitly approves exactly two read-only GitHub API GETs:
python -m phios.predict_audit --ledger $ledger --id run-001 --allow-public-network
~~~

The audit reads, in order:

1. `https://api.github.com/repos/OWNER/REPO/issues/comments/COMMENT_ID`
2. `https://api.github.com/repos/OWNER/REPO/actions/runs/RUN_ID`

Both URLs are **constructed from the already validated local ledger**;
there is no user-supplied URL, token, proxy or redirect. A disabled
network flag refuses before either GET.

The issue comment must still have the same exact ID, repository/issue
URL, GitHub HTML URL, commitment text and created/updated timestamps
recorded by R0.4. The GitHub workflow must still have the same run ID,
repository, commit SHA, workflow, URL, completed status, conclusion,
original run creation and start timestamps, and `run_attempt=1`.
Everything must preserve the chronological relationship originally
established: locally registered forecast, public comment,
last edit, workflow run creation, workflow start.

An invalid, missing, removed, malformed or oversized source is a
**HOLD**, never an audit success. A rerun is also a HOLD.
Changes to *unrelated* public API metadata can change raw response
hashes; only the explicitly enumerated identity, body and chronology
fields are evaluated.

## Output

The terminal receives a JSON receipt:
- `result: UNCHANGED_AT_THIS_CHECK`
- exact audited forecast, comment and workflow IDs
- current API response SHA-256 hashes
- the local ledger chain head and check timestamp
- `ledger_mutated: false` and `action_authority: false`
- explicit limits of what that one-time observation establishes

Nothing is stored or changed automatically: **the existing ledger
remains byte-for-byte identical**, and the previous R0.1–R0.4 reports
are unchanged. Operators can save the terminal output explicitly if
they need a dated local record, but a saved file is not a signed
third-party attestation.

## Security, privacy and epistemic limits

- GitHub API data is independent of the local file but is not
  cryptographically signed; a reported timestamp is not a guarantee
  against GitHub server errors or account compromise.
- A comment that is edited **after** a successful R0.5 check becomes
  stale again. There is no ongoing monitor.
- GitHub may represent edits with timestamps of limited precision.
  This check catches changed timestamps and bodies visible through
  the GitHub API, not every conceivable change history.
- A legitimate rerun must be modeled as a new experiment rather than
  silently reassigned to the first result.
- Even fully intact evidence does **not** prove that a model has
  special predictive skill, honest sample selection, unbiased holdout
  separation, or safe autonomy. No score grants execution authority.

## Development

~~~bash
python -m pytest -q tests/test_predict_r01.py tests/test_predict_r02.py tests/test_predict_r03.py tests/test_predict_r04.py tests/test_predict_r05.py
ruff check phios/predict.py phios/predict_source.py phios/predict_calibration.py phios/predict_anchor.py phios/predict_audit.py tests/test_predict_r01.py tests/test_predict_r02.py tests/test_predict_r03.py tests/test_predict_r04.py tests/test_predict_r05.py
mypy phios/predict.py phios/predict_source.py phios/predict_calibration.py phios/predict_anchor.py phios/predict_audit.py --ignore-missing-imports
~~~
