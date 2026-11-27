# ΦSimReady R0.1: local-first intake research

**Status:** advisory prototype. Not an importer, physics simulator, renderer, or downloader.

Source: [NVIDIA SimReady Assets](https://huggingface.co/datasets/nvidia/simready-assets)
(2,919 assets, 518 GB, dataset-level CC BY 4.0, observed 2026-11-27).
Package discovery convention: [Hugging Face 3D datasets](https://huggingface.co/docs/hub/datasets-3d).
Per-asset license and dependencies must be reviewed before redistribution.
No third-party asset bytes are included here. PhiOS code licensing is unchanged.

## R0.1 local receipt

Supply a locally curated inventory JSON with dataset, immutable 40-character commit
revision and file rows (path and declared byte size). Example, entirely synthetic:

```json
{"dataset":"nvidia/simready-assets","revision":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
"files":[{"path":"box/com.nvidia.simready.packaging.json","size":2},
{"path":"box/model.usd","size":8}]}
```

```sh
python -m phios.simready_intake inventory.json --package box --budget-bytes 10
python -m pytest tests/test_simready_intake.py
```

Select at most 36 explicit package roots. The tool is offline, prints a deterministic
advisory receipt, rejects unsafe/ambiguous paths, duplicate entries, unpinned revisions
and invalid sizes, and exits 3 for over-budget plans. Exit 0 means review-only, not
approval. The inventory is untrusted and may be incomplete. No assets are downloaded.

## Next acceptance gates

1. R0.2: opt-in Hugging Face tree retrieval with complete pagination, exact pinned
   revision, manifest schema inspection, byte budget and bounded streaming. Verify
   actual file lengths and SHA-256; reject unsafe local destinations and external
   dependencies. Atomic staging, cache receipts, explicit operator approval.
2. R0.3: choose 36 actual packages across six categories after reviewing metadata and
   measured byte totals; start with one low-cost box. Preserve native USD, licenses,
   material dependencies and source checksums. Validate OpenUSD composition in an
   isolated worker; no implicit network resolution.
3. R0.4: produce static GLB derivatives and separate physics/semantic receipts.
   Framefield's guarded GLB import is a candidate target; textures/PBR and physics are
   not assumed supported. Check geometry, unit scale, transforms and texture limits.
4. R0.5: isolated engine-specific physics sandbox; compare rest/drop/stack outcomes
   against explicit tolerances. SimReady metadata is not proof of physical accuracy.
5. R0.6: optional adapters for PhiMemory9 object identity, PhiGenesis observation/action
   experiments, Agentora orchestration, and an independent asset-tier cache. PhiStream
   inference engine remains untouched. PhiOS authority is never inferred from metadata.

Proposed pilot categories: containers, hand tools, workshop objects, furniture,
household objects, industrial equipment (six each, subject to verified availability).
Proposed initial disk budget 2 GiB, revise only after actual inventory measurements.
The 36 assets have not been selected or downloaded.
