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
```

Snapshot mode generates a one-shot artifact from current PhiKernel state.
Live mode rewrites the local artifact on an interval and the browser auto-refreshes to reflect new state.

The adapter reads PhiKernel field_state, maps it into visual parameters, renders a local HTML artifact,
and opens it in the default browser.

## Security posture

- Local-first by default.
- Unknown command passthrough executes without `shell=True` to reduce injection risk.
- PhiKernel adapter commands execute with `shell=False` and strict JSON parsing.
- Sovereign export validates output path shape (`.json`, no `..` traversal segments).
- No runtime tracking code and no mandatory cloud dependencies.
