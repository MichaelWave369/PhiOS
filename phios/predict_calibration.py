"""ΦPredict R0.3: offline prequential baseline, calibration and static HTML view.

An empirical baseline may use only binary GitHub-checked outcomes for the
same repository and workflow whose CHECK time predates each new forecast.
No live APIs, model retraining, advice adoption, or execution authority.
"""

from __future__ import annotations

import argparse
import bisect
import html
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from phios.predict import PredictionContractError, _replay, _when, load_ledger

MIN_DESCRIPTIVE_COUNT = 20
BINS = 5


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def calibration_report(path: Path) -> dict[str, Any]:
    """Compute a leakage-aware, descriptive prequential comparison from local receipts."""
    events = load_ledger(path)
    predictions, outcomes = _replay(events)
    checks = {
        event["data"]["prediction_id"]: event["data"]
        for event in events
        if event["kind"] == "github_verification"
    }

    records: list[dict[str, Any]] = []
    excluded: dict[str, int] = {}
    for pid, prediction in predictions.items():
        outcome = outcomes.get(pid)
        check = checks.get(pid)
        # Both a pilot and holdout may serve as *past* verified evidence.
        # The evaluation denominator, however, consists ONLY of holdout.
        if outcome is None:
            reason = "pending_outcome"
        elif check is None:
            reason = "not_github_checked"
        elif _when(prediction["registered_at"], "registered_at") >= _when(
            check["run_created_at"], "run_created_at"
        ):
            reason = "late_after_run_creation"
        elif outcome["conclusion"] not in {"success", "failure"}:
            reason = "nonbinary_outcome"
        else:
            reason = ""
        if reason:
            if prediction["cohort"] == "holdout":
                excluded[reason] = excluded.get(reason, 0) + 1
            continue
        assert check is not None
        assert outcome is not None
        records.append({
            "id": pid,
            "repo": prediction["repo"],
            "workflow": prediction["workflow"],
            "cohort": prediction["cohort"],
            "registered_at": _when(prediction["registered_at"], "registered_at"),
            "checked_at": _when(check["checked_at"], "checked_at"),
            "p": float(prediction["probability"]),
            "y": int(outcome["conclusion"] == "success"),
        })

    # Only previously known and checked outcomes from the SAME repo/workflow
    # qualify. A future result must never leak into an earlier prediction.
    prior_by_target: dict[tuple[str, str], list[tuple[datetime, str, int]]] = {}
    for rec in records:
        key = (rec["repo"], rec["workflow"])
        prior_by_target.setdefault(key, []).append(
            (rec["checked_at"], rec["id"], rec["y"])
        )
    times_by_target: dict[tuple[str, str], list[datetime]] = {}
    successes_by_target: dict[tuple[str, str], list[int]] = {}
    for target, history in prior_by_target.items():
        history.sort(key=lambda item: (item[0], item[1]))
        times_by_target[target] = [item[0] for item in history]
        prefix = [0]
        for _, _, y in history:
            prefix.append(prefix[-1] + y)
        successes_by_target[target] = prefix

    rows: list[dict[str, Any]] = []
    for rec in sorted(
        (r for r in records if r["cohort"] == "holdout"),
        key=lambda r: (r["registered_at"], r["id"]),
    ):
        target = (rec["repo"], rec["workflow"])
        earlier_count = bisect.bisect_left(
            times_by_target[target], rec["registered_at"]
        )
        earlier_successes = successes_by_target[target][earlier_count]
        # Beta(1,1) / Laplace-smoothed empirical rate, 0.5 before history.
        base_p = (earlier_successes + 1) / (earlier_count + 2)
        y = rec["y"]
        row = {
            "prediction_id": rec["id"],
            "repo": rec["repo"],
            "workflow": rec["workflow"],
            "registered_at": rec["registered_at"].isoformat(),
            "candidate_probability": rec["p"],
            "historical_probability": base_p,
            "historical_known_count": earlier_count,
            "observed_success": y,
            "candidate_brier": (rec["p"] - y) ** 2,
            "historical_brier": (base_p - y) ** 2,
        }
        rows.append(row)

    count = len(rows)
    candidate = _mean([r["candidate_brier"] for r in rows])
    historical = _mean([r["historical_brier"] for r in rows])
    fixed = 0.25 if count else None
    bins: list[dict[str, Any]] = []
    for index in range(BINS):
        band = [
            r for r in rows
            if min(BINS - 1, int(r["candidate_probability"] * BINS)) == index
        ]
        bins.append({
            "probability_from": index / BINS,
            "probability_to": (index + 1) / BINS,
            "count": len(band),
            "mean_forecast": _mean([r["candidate_probability"] for r in band]),
            "observed_success_rate": _mean([float(r["observed_success"]) for r in band]),
        })
    if count < MIN_DESCRIPTIVE_COUNT:
        verdict = "HOLD_INSUFFICIENT_VERIFIED_HOLDOUT"
    elif candidate is not None and historical is not None and candidate < historical:
        verdict = "DESCRIPTIVE_LOWER_ERROR_THAN_HISTORICAL"
    else:
        verdict = "DESCRIPTIVE_NO_IMPROVEMENT_OVER_HISTORICAL"

    return {
        "schema": "phios.predict.prequential_report.r0.3",
        "verdict": verdict,
        "predictions": len(predictions),
        "observations": len(outcomes),
        "github_checked": len(checks),
        "eligible_verified_history": len(records),
        "scored_holdout": count,
        "holdout_excluded": excluded,
        "candidate_mean_brier": candidate,
        "historical_mean_brier": historical,
        "fixed_half_mean_brier": fixed,
        "candidate_minus_historical": (
            candidate - historical
            if candidate is not None and historical is not None else None
        ),
        "candidate_minus_fixed_half": candidate - fixed if candidate is not None
        and fixed is not None else None,
        "calibration_bins": bins,
        "holdout_rows": rows,
        "source_chain_head": events[-1]["sha256"] if events else None,
        "action_authority": False,
        "limits": (
            "The empirical baseline is a Laplace-smoothed prior rate for each "
            "repo/workflow using only earlier locally recorded GitHub checks. "
            "Local timestamps and ledger custody are not independently attested; "
            "selection, correlation, lookahead manipulation and repeated tuning "
            "are not ruled out. Reported differences are descriptive, not proof "
            "of improved forecasting or a statistically validated learning system."
        ),
    }


def _fmt(value: float | None) -> str:
    return f"{value:.4f}" if value is not None else "No data"


def render_static_dashboard(result: dict[str, Any]) -> str:
    """Safe offline HTML with inline SVG and zero JavaScript or remote assets."""
    bins = result["calibration_bins"]
    points: list[str] = []
    for band in bins:
        if not band["count"]:
            continue
        p, y = band["mean_forecast"], band["observed_success_rate"]
        x = 60 + 500 * p
        cy = 225 - 170 * y
        points.append(
            f'<circle cx="{x:.2f}" cy="{cy:.2f}" r="6" fill="#4fd1bb">'
            f'<title>n={band["count"]}; predicted {p:.3f}; observed {y:.3f}</title>'
            "</circle>"
        )
    dot_text = "".join(points)
    ticks = "".join(
        f'<text x="{60 + i * 100}" y="248" text-anchor="middle" '
        f'font-size="12" fill="#cad4de">{i / 5:.1f}</text>'
        for i in range(6)
    )
    bars = [
        ("Candidate", result["candidate_mean_brier"], "#4fd1bb"),
        ("Historical", result["historical_mean_brier"], "#73aef3"),
        ("Fixed 0.5", result["fixed_half_mean_brier"], "#d8ad72"),
    ]
    bar_lines: list[str] = []
    for label, value, color in bars:
        safe_label = html.escape(label)
        width = max(0, min(100, 100 * float(value))) if value is not None else 0
        bar_lines.append(
            f'<div class="bar-label">{safe_label}: {_fmt(value)}</div>'
            f'<div class="track"><div class="bar" style="width:{width:.2f}%;'
            f'background:{color}"></div></div>'
        )
    rows: list[str] = []
    for row in result["holdout_rows"]:
        pid = html.escape(row["prediction_id"])
        repo = html.escape(row["repo"])
        workflow = html.escape(row["workflow"])
        rows.append(
            f"<tr><td>{pid}</td><td>{repo}</td><td>{workflow}</td>"
            f'<td>{row["historical_known_count"]}</td>'
            f'<td>{row["candidate_probability"]:.3f}</td>'
            f'<td>{row["historical_probability"]:.3f}</td>'
            f'<td>{row["observed_success"]}</td></tr>'
        )
    safe_verdict = html.escape(result["verdict"])
    table_rows = "".join(rows) or "<tr><td colspan='7'>No eligible holdout outcomes</td></tr>"
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<title>ΦPredict R0.3 | Offline calibration</title>
<style>
body{{background:#101721;color:#e4edf3;font:15px system-ui,Arial,sans-serif;max-width:1020px;margin:auto;padding:32px}}
h1,h2{{letter-spacing:-.035em}}h1{{font-size:2.1rem}}.muted{{color:#a9b9c6}}
.panel{{background:#1a2531;border:1px solid #344657;border-radius:15px;padding:24px;margin:20px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:14px}}
.metric{{background:#223140;padding:18px;border-radius:10px}}.metric b{{display:block;font-size:1.7rem}}
svg{{max-width:100%;height:auto}}.track{{height:14px;background:#304053;border-radius:8px;margin-bottom:14px}}
.bar{{height:100%;border-radius:8px}}.bar-label{{margin-bottom:5px}}
table{{width:100%;border-collapse:collapse}}th,td{{text-align:left;padding:10px;border-bottom:1px solid #344657}}
.scroll{{overflow-x:auto}}.warning{{border-left:3px solid #d8ad72;padding-left:14px;color:#d4c1a4}}
</style></head><body>
<h1>ΦPredict <span class="muted">R0.3</span></h1>
<p class="muted">Read-only offline calibration dashboard • no remote data or scripts</p>
<div class="panel"><strong>{safe_verdict}</strong>
<div class="grid">
<div class="metric">Scored holdout<b>{result["scored_holdout"]}</b></div>
<div class="metric">Candidate Brier<b>{_fmt(result["candidate_mean_brier"])}</b></div>
<div class="metric">Historical Brier<b>{_fmt(result["historical_mean_brier"])}</b></div>
<div class="metric">Verified history<b>{result["eligible_verified_history"]}</b></div>
</div></div>
<div class="panel"><h2>Reliability diagram</h2>
<p class="muted">X: mean prediction. Y: observed success rate. Dashed: perfect calibration.</p>
<svg viewBox="0 0 620 270" role="img" aria-label="Five-bin forecast calibration plot">
<path d="M60 55V225H560" fill="none" stroke="#8ca1b4" stroke-width="2"/>
<line x1="60" y1="225" x2="560" y2="55" stroke="#a6b5c4" stroke-dasharray="7 6"/>
{ticks}
<text x="310" y="267" text-anchor="middle" font-size="12" fill="#cad4de">Forecast probability</text>
<text x="20" y="65" font-size="12" fill="#cad4de">1</text>
<text x="20" y="225" font-size="12" fill="#cad4de">0</text>
{dot_text}</svg></div>
<div class="panel"><h2>Mean Brier error <span class="muted">(lower is better)</span></h2>
{''.join(bar_lines)}
<p class="muted">Historical baseline: Beta(1,1) smoothed success rate, using only
earlier verified outcomes from the same repository and workflow.</p></div>
<div class="panel"><h2>Eligible holdout observations</h2><div class="scroll">
<table><thead><tr><th>ID</th><th>Repository</th><th>Workflow</th><th>Past runs</th>
<th>Candidate p</th><th>History p</th><th>Success</th></tr></thead>
<tbody>{table_rows}</tbody></table></div></div>
<div class="panel warning">{html.escape(result["limits"])}</div>
</body></html>"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ledger", type=Path, default=Path("phipredict-ledger.jsonl"))
    parser.add_argument(
        "--html", type=Path,
        help="explicitly create a standalone offline HTML dashboard at this path",
    )
    args = parser.parse_args(argv)
    try:
        result = calibration_report(args.ledger)
        if args.html:
            # Never write a dashboard as a side effect of a plain report.
            args.html.parent.mkdir(parents=True, exist_ok=True)
            args.html.write_text(render_static_dashboard(result), encoding="utf-8")
    except (PredictionContractError, OSError, ValueError) as exc:
        print(f"ΦPredict R0.3 HOLD: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
