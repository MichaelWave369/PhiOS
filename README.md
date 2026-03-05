# φ PhiOS — Sovereign Computing Shell

> “We did not come here to improve the cage. We came here to end it.”

PhiOS is a sovereign computing environment built on Linux, powered by local AI, grounded in TIEKAT mathematics.

Read the manifesto: https://enterthefield.org/phios  
Built by: PHI369 Labs / Parallax

Sovereign. Coherent. Local. Free.

## Install

```bash
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Quick start

```bash
phi
phi status
phi coherence
phi coherence live
phi sovereign export ./phi_snapshot.json
```

## Command reference (v0.3)

- `phi help`
- `phi version`
- `phi status`
- `phi coherence`
- `phi coherence live`
- `phi sovereign export [path]`
- `phi sovereign verify <path>`
- `phi sovereign compare <path_a> <path_b>`
- `phi sovereign annotate <path> <note>`
- `phi brainc status`
- `phi tbrc status`
- `phi memory [status|search <query>|recent]`
- `phi archive [timeline|add|export]`
- `phi kg [stats|search <concept>]`
- `phi sync [status|push|pull|both]`

## Security posture

- Local-first by default.
- Unknown command passthrough executes without `shell=True` to reduce injection risk.
- Sovereign file operations validate paths to prevent relative traversal outside working directory.
- No runtime tracking code and no mandatory cloud dependencies.
