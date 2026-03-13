# φ PhiOS — Sovereign Computing Shell

> “We did not come here to improve the cage. We came here to end it.”

PhiOS is the sovereign operator shell on top of PhiKernel.

Read the manifesto: https://enterthefield.org/phios  
Built by: PHI369 Labs / Parallax

Sovereign. Coherent. Local. Free.

## PhiOS on PhiKernel

Architecture relationship:

Linux  
↓  
PhiKernel = trusted runtime core (source of truth)  
↓  
PhiOS = sovereign shell / operator experience

Phase 1 integration is intentionally loose-coupled:

- PhiOS calls PhiKernel via stable CLI interfaces (`phik ... --json`).
- PhiOS re-renders operator-friendly output and composes workflows.
- PhiOS does **not** duplicate runtime internals.

PhiKernel remains authoritative for:

- anchor
- capsules
- heart
- coherence
- routing safety

## Install

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Verify toolchain

```bash
phi --help
phik --help
phik status --json
```

## Quick start

```bash
phi
phi status
phi coherence
phi ask "How should I begin?"
phi sovereign export ./phi_snapshot.json
```

## First Day with PhiOS

```bash
phi doctor
phi init --passphrase "change-me" --sovereign-name "Tal-Aren-Vox" --user-label "Ori"
phi pulse once
phi status
phi coherence
phi ask "How should I begin?"
```

## Command reference (v0.3)

- `phi help`
- `phi version`
- `phi doctor [--json]`
- `phi init --passphrase <value> --sovereign-name <name> --user-label <label> [--resonant-label <label>] [--json]`
- `phi pulse once [--checkpoint <path>] [--passphrase <value>] [--json]`
- `phi observatory [--json]`
- `phi observatory export <path.json>`
- `phi z map [--json]`
- `phi mind [--json]`
- `phi mind map [--json]`
- `phi mind export <path.json>`
- `phi session start [--json]`
- `phi session checkin [--json]`
- `phi session export <path.json>`
- `phi bio list [--json]`
- `phi bio add --name <name> --compound <compound> --source <source> [--dose <dose>] [--unit <unit>] [--timing <timing>] [--notes <notes>] [--json]`
- `phi bio show [--json]`
- `phi bio export <path.json>`
- `phi view --mode sonic`
- `phi view --mode sonic --live --refresh-seconds 2 --duration 60`
- `phi view --mode sonic --journal --label morning`
- `phi view --mode sonic --live --journal --label focus`
- `phi view --mode sonic --replay <session_id>`
- `phi view --mode sonic --preset stable --lens ritual`
- `phi view --mode sonic --live --preset diagnostic --audio-reactive`
- `phi view --mode sonic --journal --collection morning`
- `phi view --browse-collections`
- `phi view --browse-collection morning`
- `phi view --compare <session_a[:state_idx]> <session_b[:state_idx]>`
- `phi view --mode sonic --replay <session_id> --state-idx <n>`
- `phi view --mode sonic --replay <session_id> --next-state`
- `phi view --mode sonic --replay <session_id> --prev-state`
- `phi view --mode sonic --compare <left> <right> --export-report <path.json>`
- `phi status [--json]`
- `phi coherence [--json]`
- `phi coherence live`
- `phi ask <prompt> [--json]`
- `phi sovereign export <path.json>`
- `phi sovereign verify <path>`
- `phi sovereign compare <path_a> <path_b>`
- `phi sovereign annotate <path> <note>`
- `phi brainc status`
- `phi tbrc status`
- `phi memory [status|search <query>|recent]`
- `phi archive [timeline|add|export]`
- `phi kg [stats|search <concept>]`
- `phi sync [status|push|pull|both]`


## Hemavit Observatory

PhiOS can interpret PhiKernel runtime state through a Hemavit / TIEKAT observatory lens.
This layer is symbolic interpretation and operator workflow composition.
It does **not** replace PhiKernel's coherence engine or runtime source-of-truth.

```bash
phi observatory
phi z map
phi observatory export ./phi_observatory_snapshot.json
```


## Ψ_mind Observatory

PhiOS can interpret PhiKernel runtime state through a `Ψ_mind` observatory lens.
This layer is symbolic interpretation and operator workflow composition.
It does **not** replace PhiKernel's coherence engine or runtime source-of-truth.

```bash
phi mind
phi mind map
phi mind export ./phi_mind_snapshot.json
```


## Session Layer

PhiOS Session Layer is a composition surface across runtime + observatory + mind views.
It unifies startup and daily check-in workflows while keeping PhiKernel as source-of-truth.

It uses symbolic interpretation terms for operator check-ins, including:
- `observer_state`
- `self_alignment`
- `information_density` (`G_info(I)`)
- `entropy_load` (`η S_ent`)
- `emergence_pressure` (`T_emerge`)

```bash
phi session start
phi session checkin
phi session export ./phi_session_snapshot.json
```


## Bioeffector Layer

PhiOS can track compounds / extracts / herbal supports as part of operator workflow.
This is a local workflow and observatory layer for session correlation, not substrate truth.
It does **not** replace PhiKernel runtime truth and does **not** constitute medical advice.

```bash
phi bio add --name "Lion's Mane" --compound "Erinacine A" --source "mycelium" --dose 500 --unit mg --timing morning
phi bio list
phi bio show
phi bio export ./phi_bio_snapshot.json
```


## Visual Bloom Adapter

PhiOS can render a local visual bloom snapshot from live PhiKernel telemetry.
This is an operator-facing visual lens and composition layer, not a second runtime engine.

```bash
phi view --mode sonic
phi view --mode sonic --live
phi view --mode sonic --live --refresh-seconds 1.5 --duration 120
phi view --mode sonic --journal --label morning
phi view --mode sonic --live --journal --label focus
phi view --mode sonic --replay 20260101T120000Z_123456
phi view --mode sonic --preset stable --lens ritual
phi view --mode sonic --live --preset diagnostic --audio-reactive
phi view --mode sonic --journal --collection morning
phi view --browse-collections
phi view --browse-collection morning
phi view --compare 20260101T120000Z_123456:0 20260102T073000Z_654321:0
phi view --mode sonic --replay 20260101T120000Z_123456 --state-idx 3
phi view --mode sonic --replay 20260101T120000Z_123456 --next-state
phi view --mode sonic --compare 20260101T120000Z_123456:0 20260102T073000Z_654321:0 --export-report ./phi_compare_report.json
phi view --gallery
phi view --gallery --collection morning
phi view --mode sonic --compare 20260101T120000Z_123456:0 20260102T073000Z_654321:0 --save-compare morning_pair
phi view --browse-compares
phi view --mode sonic --load-compare morning_pair
phi view --mode sonic --compare 20260101T120000Z_123456:0 20260102T073000Z_654321:0 --export-bundle ./exports/morning_pair_bundle
```

Snapshot mode generates a one-shot artifact from current PhiKernel state.
Live mode writes the HTML artifact once, then updates a local JSON params file on interval while the page performs in-place polling (no full page reload).

Optional journaling writes reproducible visual-state archives under `~/.phios/journal/visual_bloom/<session_id>/` with `session.json` and `latest.params.json`. Replay mode renders a saved state locally without polling PhiKernel.

Phase 5 adds optional preset packs and named visual lenses (`stable`, `ritual`, `diagnostic`, `bloom`) that shape rendering interpretation deterministically without changing kernel truth.

Phase 6 adds named archive collections and local browse/compare workflows. You can tag sessions with `--collection`, browse collections/sessions from disk, and compare two saved states side-by-side without polling PhiKernel.

Phase 7 adds replay state stepping (`--state-idx`, `--next-state`, `--prev-state`), concise compare diff metrics, and optional JSON report export via `--export-report` for local observatory comparisons.

Phase 8 adds a static archive gallery (`--gallery`), saved compare sets (`--save-compare`, `--browse-compares`, `--load-compare`), and portable observatory compare bundles (`--export-bundle`).

Audio-reactive coupling is optional and off by default (`--audio-reactive`). If local audio support is unavailable, PhiOS continues gracefully without audio modulation.

State references support optional indexing syntax (`<session_id>:<state_idx>`). If omitted, replay/compare defaults to the latest state. Older archives without new metadata fields still replay/compare with safe defaults.

Compare bundle manifest (`bundle_manifest.json`) uses a stable schema with: `bundle_version`, `exported_at`, `bundle_type`, `source_refs`, `included_files`, `report_schema_version`, and `compatibility_notes`.

The adapter reads PhiKernel field_state, maps it into visual parameters, renders a local HTML artifact,
and opens it in the default browser.

## Security posture

- Local-first by default.
- Unknown command passthrough executes without `shell=True` to reduce injection risk.
- PhiKernel adapter commands execute with `shell=False` and strict JSON parsing.
- Sovereign export validates output path shape (`.json`, no `..` traversal segments).
- No runtime tracking code and no mandatory cloud dependencies.
