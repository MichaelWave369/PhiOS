# ΦPredict R0.4: public timestamped forecast commitments

**Experimental opt-in**. This rung adds public, independently timestamped
**hash commitments** to a previously registered local forecast.

## Why

R0.1 local ledger timestamps can be rewritten together with the hash chain;
R0.2 compares the observed run to public GitHub metadata; R0.3 blocks obvious
lookahead within the local timeline. None proves the forecast existed
before GitHub created its workflow run.

R0.4 lets the operator manually publish a digest of the exact existing
prediction event in a **public issue comment in the same GitHub repo**.
This issue comment is created *before* the workflow run. After the
workflow, R0.4 reads GitHub's public issue-comment API once on explicit
request and checks both GitHub timestamps against the R0.2 run-created
time. The digest ties back to the original R0.1 prediction event SHA-256,
which includes its contents and earlier ledger prefix.

The published comment contains only a hash, not the probability, labels
or personal data. Still, publishing the comment exposes its presence
and permanently associates it with a public issue.

## Operator process (PowerShell)

First use R0.1 to register a prediction, **before** a target workflow run
exists. Pick a newly planned workflow/commit SHA whose run has not been
created.

~~~powershell
$ledger = ".\phipredict-ledger.jsonl"
python -m phios.predict --ledger $ledger register --id run-001 --repo MichaelWave369/PhiOS --sha FULL40DIGITSHA --workflow "PhiOS qualification" --probability 0.80 --cohort holdout

# Offline: display the exact comment body; don't edit the digest.
python -m phios.predict_anchor --ledger $ledger anchor-payload --id run-001
~~~

Copy only the output's **comment_body** value. Manually post it as a
GitHub issue comment in that same repository **before** the intended
workflow run is created. Keep the numeric comment ID from the issue URL,
and do not edit or delete the comment. Public issue comments are the
only supported anchor format in R0.4. Do not use a private issue or
rely on a screenshot.

After the CI run is completed, R0.1 observes its saved public run JSON,
and R0.2 explicitly verifies the exact run via its public GitHub API:

~~~powershell
python -m phios.predict --ledger $ledger observe --id run-001 --run-json run.json
python -m phios.predict_source --ledger $ledger verify-github --id run-001 --allow-public-network
~~~

Then explicitly verify the *separate* public issue comment:

~~~powershell
python -m phios.predict_anchor --ledger $ledger verify-anchor --id run-001 --comment-id 123456789 --allow-public-network
python -m phios.predict_anchor --ledger $ledger anchored-report
~~~

The final report is offline; no network unless explicitly requested.
R0.4 **never publishes the comment, triggers CI, modifies a repo,
auto-merges, or changes an agent's authority**.

## Strict matching

The verifier uses only this fixed public GET endpoint, derived from
the already validated registered repository and an integer comment ID:

~~~text
https://api.github.com/repos/OWNER/REPO/issues/comments/COMMENT_ID
~~~

It refuses credentials, proxies, redirects, non-JSON, oversized responses,
wrong comment or issue ID, wrong repository, changed body, duplicate anchors,
missing independently verified workflow run, and contradictory chronology.

For acceptance the local registration timestamp is strictly before
the GitHub comment creation; comment creation is no later than its last
edit; the last edit is strictly before GitHub's workflow creation;
and the run has been independently checked via R0.2. GitHub time
resolution can make immediate adjacent events ineligible. Wait before
posting and before starting the workflow; never edit timestamps.

A successful receipt records a SHA-256 of the public API response,
the comment ID, the commitment digest, GitHub's public created/updated
timestamps, independently verified run creation time, and local check
time. R0.1's hash-chain replay checks every field and matches the digest
against the immutable prediction event. Old ledgers and old report
commands remain compatible.

R0.4's `anchored-report` only scores a *holdout* prediction if it has
an R0.2 source-verified completed run and a matching R0.4 public
anchor. Cancelled/skipped outcomes are excluded. With fewer than
20 examples the result is a hold, and larger samples are still
**descriptive**, not proof of forecasting superiority.

## Limitations

GitHub's timestamps are independently *reported*, not digitally signed
attestations. GitHub comments can be edited or deleted **after** a
one-time verification, so a later audit should re-check the endpoint.
There is no guarantee a private human or agent independently selected
the candidate or that any result was free of pretraining leakage,
cohort-tuning, sample dependence, or selection bias.

The comment is tied to a ledger event hash, not an independent public
publication of the prediction's contents. Auditors need the matching
ledger to reveal exactly what was forecast. No automatic action
promotion is ever permitted from scores.

## Development

~~~bash
python -m pytest -q tests/test_predict_r01.py tests/test_predict_r02.py tests/test_predict_r03.py tests/test_predict_r04.py
ruff check phios/predict.py phios/predict_source.py phios/predict_calibration.py phios/predict_anchor.py tests/test_predict_r01.py tests/test_predict_r02.py tests/test_predict_r03.py tests/test_predict_r04.py
mypy phios/predict.py phios/predict_source.py phios/predict_calibration.py phios/predict_anchor.py --ignore-missing-imports
~~~
