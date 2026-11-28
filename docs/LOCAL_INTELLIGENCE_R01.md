# Operation Local Intelligence — R0.1

**Status:** documentation-backed census and optional local API observation. Not a
complete repository audit, live inference test, model download, or grant of
authority. No existing PhiOS interfaces or agent behavior are changed.

## Run

From a PhiOS checkout with Python 3.11+:

```powershell
python -m phios.local_intelligence
python -m phios.local_intelligence --ollama
python -m pytest tests/test_local_intelligence.py
```

The first command is offline. The optional second command makes only a GET to
127.0.0.1:11434/api/tags with no proxy, redirect following, model loads or
generation. The response is bounded to 2 MiB; unavailable or malformed
responses are reported rather than treated as an empty installed fleet.
Names and declared sizes are API reports, not proof of weight residency.
Cloud hints are conservative; all other locations remain UNVERIFIED.
The JSON is printed locally; it can contain private model names. Do not
publish inventory output without review. No prompt, transcript, environment
secret, filesystem scan or remote endpoint is requested.

The registry includes 26 documented capability entries across 24 repositories.
BrainC and PhiStream each have two separately classified entries. Every
entry carries a documentation URL and an explicit limitation; these mutable
main-branch links are navigation aids, not immutable audit provenance.
No custom independently trained checkpoint has been established by this census.

## Qualification ladder (proposed)

1. Complete paginated repository census and deduplicate by immutable repo ID;
   pin source commits and inspect model configurations, checkpoints, licenses,
   launch entrypoints and inference pathways. Keep unknowns visible.
2. Operator PC: compare Ollama inventory with explicit local checkpoint
   hashes and actual disk/GPU observations. No upload of personal paths or data.
3. Chat pilot: BrainC (custom Qwen configuration), PhiBuddy (solo then council),
   PocketBrain (browser or bridge), GAIA (local Oracle), PrivateSpark,
   Vessie (explicit local pilot), and ThinkTank (explicit bridge).
   Separate deterministic demo from real generation.
4. Build pilot: Agentora with mock mode disabled, followed by governed PhiBot
   tests. Start with an empty disposable workspace, no secrets, no network,
   no write permissions by default; separately approve exact local actions.
5. Serving pilot: run one existing GGUF through PhiServe, compare the same
   model/workload with a matched llama.cpp baseline; measure GPU/host memory,
   latency and tokens/sec. Do not assume multiple models fit in 12 GiB VRAM.
6. Model Forge pilot: approved dataset, pinned base checkpoint, QLoRA, held-out
   blinded comparison and adapter provenance. No automatic model promotion.
7. Shared inference and isolated memory: design per-companion identity,
   context, permission and storage boundaries; test cross-app isolation before
   enabling any live data transfer. PhiStream and PhiGenesis remain separately
   gated research paths.

First target machine: Windows 11, 12 GB GPU; measured readiness is required.
Start with one small installed local model before attempting a larger one.
A green CI run establishes fixture behavior only, not hardware readiness.

## Acceptance for R0.1

- Offline default and deterministic catalog; no inference or action authority.
- Bounded, explicit loopback inventory with honest unverified location labels.
- Source links and limitations distinguish model configuration, neural
  execution, serving, training, agents, memory and research.
- Fixture tests cover malformed inventories, cloud references, redirects,
  size limits and default network isolation.
