# ΦPredict R0.3: prequential calibration and offline dashboard

**Status: experimental, descriptive, read-only.** This new rung does
not touch live routing, execution authority, GitHub, model weights,
production workflows or the existing ΦPredict R0.1/R0.2 data format.

## Question

Does a user-supplied CI success probability beat a reasonable
**historical-rate baseline** instead of only the 50/50 guess used in R0.1/R0.2?

For each eligible, verified *holdout* prediction, the baseline uses
**only previously GitHub-checked binary outcomes that were already
known before the new prediction's local registration timestamp**.
It is grouped by repository and exact workflow name.

The smoothed empirical rate is:

~~~text
historical_probability = (earlier_successes + 1) / (earlier_observations + 2)
~~~

This is Beta(1,1)/Laplace smoothing. With zero prior observations,
the baseline is 0.5. Pilot and holdout runs can contribute to the
historical evidence **only after** they have been separately GitHub
checked and are otherwise eligible. The denominator scored remains
strictly verified holdout.

A previously seen run is eligible as historical evidence only if its
original locally dated prediction preceded GitHub's run creation time,
its conclusion was exactly `success` or `failure`, and its R0.2
`github_verification.checked_at` timestamp was earlier than the
*new forecast's* registration timestamp. Equal timestamps do not count.
The current forecast cannot use its own outcome. Different repositories
and workflows do not share historical evidence.

**Important:** The local timestamps can be forged; the hash-linked ledger is
not externally anchored. This filters lookahead in a coherent local ledger
but does not certify true temporal independence, a frozen evaluation split,
authentic forecasts, or a scientifically valid accuracy advantage. A
correlated CI population is not an independent sample. Repeated tuning
against holdout outcomes is a form of evaluation leakage.

## Commands (no network)

~~~powershell
$ledger = ".\phipredict-ledger.jsonl"

# Read-only JSON report:
python -m phios.predict_calibration --ledger $ledger

# Explicitly create a standalone dashboard file:
python -m phios.predict_calibration --ledger $ledger --html ".\calibration.html"
~~~

The dashboard is a static HTML document with inline SVG, local CSS,
a Content Security Policy prohibiting scripts and remote resources,
five calibration bins, per-run metrics, three mean Brier scores,
and a compact explanation of the evidence limits. It is generated only
when `--html` is supplied. No browser automation, web access or cloud
credentials are needed. Its table displays ledger metadata; share that
file only if the repository and workflow labels are public or safe to share.

The JSON report includes:
- Eligible verified holdout count and explicit exclusion reasons
  (`pending_outcome`, `not_github_checked`, `late_after_run_creation`,
  `nonbinary_outcome`).
- Per-example candidate probability, historical baseline, count of
  previously known qualifying outcomes and Brier scores.
- Mean candidate Brier, empirical historical Brier, fixed-half Brier (0.25),
  and candidate-minus-baseline differences (lower = better).
- Five descriptive reliability bins with mean forecast and actual fraction.
- `action_authority: false` and a first-class limitation statement.

With fewer than 20 eligible holdout examples the verdict is
`HOLD_INSUFFICIENT_VERIFIED_HOLDOUT`. At 20 or more, a lower Brier score
than history is reported as `DESCRIPTIVE_LOWER_ERROR_THAN_HISTORICAL`,
never scientific validation or autonomous learning. If not lower, the
verdict is `DESCRIPTIVE_NO_IMPROVEMENT_OVER_HISTORICAL`.

This is an **offline analysis layer**. R0.1 still registers and ingests
predictions; R0.2 independently checks public GitHub API run metadata
only when explicitly requested. R0.3 never makes network calls.

## Development

~~~bash
python -m pytest -q tests/test_predict_r01.py tests/test_predict_r02.py tests/test_predict_r03.py
ruff check phios/predict.py phios/predict_source.py phios/predict_calibration.py tests/test_predict_r01.py tests/test_predict_r02.py tests/test_predict_r03.py
mypy phios/predict.py phios/predict_source.py phios/predict_calibration.py --ignore-missing-imports
~~~

Next experiments: externally anchor prediction commitments, protect the
holdout from repeated tuning, add confidence intervals only after a
dependence-aware validation design, and evaluate reliability drift on
predeclared cohorts. No automated action or model promotion from scores.
