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


## MCP interface (Phase 1 + Phase 2)

PhiOS exposes an MCP interface layer over existing PhiOS/PhiKernel capabilities.
This is additive interface work only; it does not replace runtime internals.
**PhiKernel remains source of truth** for status, field, anchor, capsules, and pulse behavior.

Run the stdio MCP server:

```bash
phi-mcp
```

Resources:
- `phios://field/state`
- `phios://coherence/lt`
- `phios://system/status`
- `phios://history/recent_capsules`
- `phios://history/recent_sessions`
- `phios://history/recent_field_snapshots`

Tools:
- `phi_status`
- `phi_ask`
- `phi_pulse_once`

Prompt:
- `field_guidance`

Phase 2 additions:
- Schema versioning on MCP payloads via top-level `schema_version` plus `resource_version`/`tool_version` where applicable.
- Default-safe pulse capability gating for `phi_pulse_once`; enable explicitly with `PHIOS_MCP_ALLOW_PULSE=true`.
- Read-only history resources from grounded local/adapter data with sensible recent limits.

Framing discipline is preserved in MCP outputs and prompts:
- `C*` is treated as theoretical.
- bio-vacuum targets are experimental.
- Hunter's C remains unconfirmed.

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
phi view --gallery --search morning --filter-mode live --filter-preset stable
phi view --mode sonic --compare 20260101T120000Z_123456:0 20260102T073000Z_654321:0 --export-bundle ./exports/morning_pair_bundle --with-integrity --bundle-label morning_pair
phi view --create-narrative morning_story --narrative-title "Morning Story" --narrative-summary "Operator shift arc"
phi view --add-to-narrative morning_story --session 20260101T120000Z_123456:0 --entry-note "Initial field posture"
phi view --add-to-narrative morning_story --compare 20260101T120000Z_123456:0 20260102T073000Z_654321:0 --entry-note "Stability delta"
phi view --browse-narratives
phi view --load-narrative morning_story
phi view --export-atlas morning_story ./exports/morning_story_atlas --with-integrity
phi view --create-constellation sky_map --constellation-title "Sky Map" --constellation-summary "Cross-shift threads" --tags coherence,bridge
phi view --add-to-constellation sky_map --narrative morning_story --entry-note "Primary arc" --tags anchor
phi view --add-to-constellation sky_map --compare-set morning_pair --entry-note "Key delta"
phi view --browse-constellations
phi view --load-constellation sky_map
phi view --export-constellation sky_map ./exports/sky_map --with-integrity
phi view --link-narrative morning_story --link-type narrative --target-ref evening_story --entry-note "continuation" --tags bridge
phi view --create-pathway shift_journey --pathway-title "Shift Journey" --pathway-summary "Guided arc" --tags coherence,experimental
phi view --add-to-pathway shift_journey --session 20260101T120000Z_123456:0 --step-note "Entry baseline"
phi view --add-to-pathway shift_journey --narrative morning_story --step-note "Narrative anchor"
phi view --add-to-pathway shift_journey --atlas ./exports/morning_story_atlas --step-note "Atlas handoff"
phi view --add-to-pathway shift_journey --constellation sky_map --step-note "Cross-link context"
phi view --browse-pathways
phi view --load-pathway shift_journey
phi view --export-pathway shift_journey ./exports/shift_journey --with-integrity
phi view --search coherence --search-tags coherence --search-type pathway --search-bio experimental
```

Snapshot mode generates a one-shot artifact from current PhiKernel state.
Live mode writes the HTML artifact once, then updates a local JSON params file on interval while the page performs in-place polling (no full page reload).

Optional journaling writes reproducible visual-state archives under `~/.phios/journal/visual_bloom/<session_id>/` with `session.json` and `latest.params.json`. Replay mode renders a saved state locally without polling PhiKernel.

Phase 5 adds optional preset packs and named visual lenses (`stable`, `ritual`, `diagnostic`, `bloom`) that shape rendering interpretation deterministically without changing kernel truth.

Phase 6 adds named archive collections and local browse/compare workflows. You can tag sessions with `--collection`, browse collections/sessions from disk, and compare two saved states side-by-side without polling PhiKernel.

Phase 7 adds replay state stepping (`--state-idx`, `--next-state`, `--prev-state`), concise compare diff metrics, and optional JSON report export via `--export-report` for local observatory comparisons.

Phase 8 adds a static archive gallery (`--gallery`), saved compare sets (`--save-compare`, `--browse-compares`, `--load-compare`), and portable observatory compare bundles (`--export-bundle`).

Phase 9 adds richer gallery filtering/search (`--search`, `--filter-mode`, `--filter-preset`, `--filter-lens`, `--filter-audio`, `--filter-label`, `--filter-session`), preview metadata on sessions/bundles, and optional bundle integrity metadata (`--with-integrity`, `--bundle-label`).

Phase 10 adds curated narratives/storyboards and portable Field Atlas export (`--create-narrative`, `--add-to-narrative`, `--browse-narratives`, `--load-narrative`, `--export-atlas`) so saved sessions/compares can be assembled into ordered observatory arcs.

Phase 11 adds thematic tags (`--tags`), cross-narrative links (`--link-narrative`, `--link-type`, `--target-ref`), and constellation maps (`--create-constellation`, `--add-to-constellation`, `--browse-constellations`, `--load-constellation`, `--export-constellation`) for multi-artifact curation.

Phase 12 adds curated operator pathways/journeys (`--create-pathway`, `--add-to-pathway`, `--browse-pathways`, `--load-pathway`, `--export-pathway`) and local metadata search (`--search`, `--search-tags`, `--search-type`, `--search-bio`) across sessions/compares/narratives/atlases/constellations/pathways.


### Experimental bio-resonance framing (careful distinction)

PhiOS uses **explicitly experimental** bio-resonance metadata for operator interpretation only:

- `C_STAR_THEORETICAL = φ / 2 ≈ 0.809016994...`
- `BIO_VACUUM_TARGET = 0.81055`
- `BIO_VACUUM_BAND_LOW = 0.807`
- `BIO_VACUUM_BAND_HIGH = 0.813`
- `BIO_VACUUM_STATUS = "experimental"`
- `HUNTER_C_STATUS = "unconfirmed"`
- `BIO_MODEL_PROVENANCE = "proxy-calibrated, not empirically confirmed"`

Important: PhiOS does **not** present `BIO_VACUUM_TARGET` as a proven physical constant or as validated Hunter's C. This layer is optional, additive, and used for cautious operator-side annotation/search/journey guidance.

Audio-reactive coupling is optional and off by default (`--audio-reactive`). If local audio support is unavailable, PhiOS continues gracefully without audio modulation.

State references support optional indexing syntax (`<session_id>:<state_idx>`). If omitted, replay/compare defaults to the latest state. Older archives without new metadata fields still replay/compare with safe defaults.

Compare bundle manifest (`bundle_manifest.json`) uses a stable schema with: `bundle_version`, `manifest_version`, `bundle_type`, `bundle_label`, `bundle_created_at`, `source_refs`, `included_files`, `integrity_mode`, optional `file_hashes_sha256`, `report_schema_version`, `compatibility_version`, and `compatibility_notes`.

Field Atlas manifest (`atlas_manifest.json`) includes: `atlas_version`, `manifest_version`, `atlas_type`, `narrative_name`, `bundle_created_at`, `entry_count`, `included_files`, `integrity_mode`, optional `file_hashes_sha256`, `preview`, `compatibility_version`, and `compatibility_notes`.

Constellation manifest (`constellation_manifest.json`) includes: `constellation_version`, `manifest_version`, `constellation_type`, `constellation_name`, `bundle_created_at`, `entry_count`, `link_count`, `tags`, `included_files`, `integrity_mode`, optional `file_hashes_sha256`, `preview`, `compatibility_version`, and `compatibility_notes`.

Pathway manifest (`pathway_manifest.json`) includes: `pathway_version`, `manifest_version`, `pathway_type`, `pathway_name`, `bundle_created_at`, `step_count`, `tags`, `bio_context`, `included_files`, `integrity_mode`, optional `file_hashes_sha256`, `preview`, `compatibility_version`, and `compatibility_notes`.

The adapter reads PhiKernel field_state, maps it into visual parameters, renders a local HTML artifact,
and opens it in the default browser.

## Security posture

- Local-first by default.
- Unknown command passthrough executes without `shell=True` to reduce injection risk.
- PhiKernel adapter commands execute with `shell=False` and strict JSON parsing.
- Sovereign export validates output path shape (`.json`, no `..` traversal segments).
- No runtime tracking code and no mandatory cloud dependencies.


## Phase 13: Branching Journeys, Recommendations, and Golden Kernels

Phase 13 adds additive local curation surfaces while preserving existing snapshot/live/replay/compare/gallery/bundle/narrative/atlas/constellation/pathway flows.

### Exact theoretical and experimental framing

- `PHI = (1 + sqrt(5)) / 2`
- `C_STAR_THEORETICAL = PHI / 2 = (1 + sqrt(5)) / 4`
- Symbolic equivalence (documentational): `C_STAR_THEORETICAL = cos(36°) = sin(54°)`
- `BIO_VACUUM_TARGET = 0.81055`
- `BIO_VACUUM_BAND_LOW = 0.807`
- `BIO_VACUUM_BAND_HIGH = 0.813`
- `BIO_VACUUM_STATUS = "experimental"`
- `HUNTER_C_STATUS = "unconfirmed"`
- `BIO_MODEL_PROVENANCE = "proxy-calibrated, not empirically confirmed"`

This repository treats the bio target and golden kernels as optional experimental operator tooling, not empirical proof and not runtime source-of-truth logic.

### Experimental golden kernels

`phios.ml.golden_kernels` includes:

- `golden_rbf(...)`
- `golden_angular_rbf(...)`
- `golden_periodic(...)`
- `golden_target_angle_score(...)`

These are used only for local similarity/recommendation hints. They are not a claim of universal kernel optimality.

### New CLI additions

- `phi view --link-pathway-step <pathway> --from-step <id> --to-step <id> --branch-label <label>`
- `phi view --recommend-for <ref>`
- `phi view --dashboard [--output <path.html>] [--search <query>]`

### Backward compatibility

All new branching/recommendation/dashboard/golden-kernel data is additive. Older artifacts without tags, preview metadata, integrity metadata, bio metadata, or branching metadata continue to load with safe defaults.


## Phase 14: Golden Lattice, Adaptive Affinity, and Strategy Benchmarks

Phase 14 extends local recommendation tooling with an **experimental** 4D golden-lattice layer and adaptive local affinity scoring. These additions are optional and are not used for PhiKernel core truth logic.

### New experimental ML modules

- `phios.ml.golden_lattice`:
  - `build_lattice_4d_nodes(...)`
  - `golden_lattice_kernel_l1(...)`
  - `golden_lattice_sparse_graph(...)`
  - `golden_lattice_resonance_score(...)`
  - `estimate_local_scales(...)`
  - `adaptive_golden_affinity(...)`
  - `update_memory_weights(...)`
- `phios.ml.benchmark_recommendations`:
  - local exploratory strategy comparison and JSON summary helpers.

### Recommendation strategy options

`phi view --recommend-for <ref> --recommend-strategy <name>` now supports:

- `golden_rbf`
- `golden_angular`
- `golden_lattice_l1`
- `adaptive_golden_affinity`
- `baseline_rbf`
- `baseline_cosine`

Optional benchmark summary:

- `phi view --benchmark-recommendations`
- `phi view --benchmark-recommendations --recommend-strategy golden_rbf,baseline_rbf`

### Scientific framing (unchanged and explicit)

- `C_STAR_THEORETICAL` remains a theoretical reference from `PHI`,
- `BIO_VACUUM_TARGET` remains **experimental**,
- `HUNTER_C_STATUS` remains **unconfirmed**,
- lattice/adaptive scores are **experimental local similarity utilities**, not empirical proofs.

### Backward compatibility

Recommendation metadata is additive (strategy/score-type fields), and older artifacts without these fields continue to load safely.


## Phase 14.1: Experimental Golden Atlas Navigation

This phase adds `phios.ml.golden_atlas` as an optional local navigation layer over lattice/state-space metadata.

Key points:
- Atlas route costs use monotone increasing travel cost (distance-based), not `(phi/2)^distance` as direct Dijkstra cost.
- Golden decay/coupling remains a similarity annotation, separate from traversal cost.
- Targets supported include:
  - theoretical attractor region around `C_STAR_THEORETICAL`
  - experimental bio band `[BIO_VACUUM_BAND_LOW, BIO_VACUUM_BAND_HIGH]`
  - explicit node targets
- Scientific framing remains explicit: theoretical C* vs experimental bio target and unconfirmed Hunter's C.

CLI additions:
- `phi view --atlas`
- `phi view --atlas --atlas-target theoretical|bio_band|node`
- `phi view --atlas --atlas-node <idx>`
- `phi view --atlas --atlas-start-ref <session_ref>`
- `phi view --atlas --atlas-max-l1-radius <int>`
- `phi view --atlas --atlas-heat-mode target_proximity|path_density|connectivity|bio_band_proximity`

Golden Atlas is experimental and optional local guidance only; it does not alter core PhiKernel truth logic.


## Phase 15: Sector Ontology and Insight Packs

Phase 15 introduces a formal **experimental sector ontology** derived from HG/HB equation scaffolds for observatory UI/analysis context.

### Sector ontology (symbolic/interpretive)

- Added `phios.core.sectors` with HG/HB family sector definitions and metadata.
- This ontology is a symbolic observatory schema and is **not** an empirically validated physical law layer.

### Sector-aware atlas and dashboard surfacing

- Atlas heat modes now include sector-aware options:
  - `geometry_balance`
  - `vacuum_proximity`
  - `observer_entropy`
  - `collector_activity`
  - `mirror_alignment`
  - `emotion_field`
- Dashboard includes sector summary panels based on available local metadata with graceful fallback.

### Insight-pack export

- New export flow:
  - `phi view --export-insight-pack <pathway> <output-dir>`
  - `--insight-pack-title <title>`
  - `--insight-pack-include-atlas`
  - `--insight-pack-heat-mode <mode>`
- Insight packs are static/local bundles with pathway + branch context, sector summaries, recommendations, optional atlas summary, and framing metadata.

### Sector CLI helpers

- `phi view --list-sectors`
- `phi view --list-sectors --sector-family HG`

### Framing reminder

- `C_STAR_THEORETICAL` remains theoretical.
- `BIO_VACUUM_TARGET` and bio band remain experimental.
- `HUNTER_C_STATUS` remains unconfirmed.
- Sector ontology, atlas navigation, and insight packs are optional interpretive/operator layers and do not alter PhiKernel truth logic.


## Phase 16: Branch Replay, Sector Overlays, and Route Compare Bundles

Phase 16 adds branch-aware journey replay, sector overlays in replay/map contexts, richer recommendation diagnostics, and static route-compare bundles.

### Branch-aware replay

- `phi view --branch-replay <pathway>` renders static branch-aware replay context with:
  - current ordered steps
  - outgoing branch labels/notes
  - recommended next-step hints
  - sector overlay summaries

### Route compare bundles

- `phi view --export-route-compare <start-ref> <output-dir>`
- Optional flags:
  - `--route-compare-title <title>`
  - `--route-compare-heat-mode <mode>`
  - `--route-compare-include-sector-overlays`

Export includes static artifacts such as:
- `route_compare_manifest.json`
- `route_compare_index.html`
- `theoretical_route.json`
- `bio_band_route.json`
- `route_diff_summary.json`
- `strategy_diagnostics.json`
- optional `sector_overlay_summary.json`

### Strategy diagnostics

- `phi view --show-strategy-diagnostics <ref>`

Diagnostics remain local exploratory summaries (agreement/overlap behavior), not claims of strategy superiority.

### Scientific framing reminder

- Theoretical attractor routes are reference structures.
- Bio-band routes are experimental guidance structures.
- Hunter’s C remains unconfirmed.
- These overlays/comparisons are interpretive observatory layers and do not alter PhiKernel truth logic.


## Phase 17: Portable Observatory Storyboards

Phase 17 adds static storyboard bundles that combine insight packs, branch replay context, route compare outputs, thematic filters, and comparative summaries.

### Storyboard workflows

- `phi view --create-storyboard <name>`
- `phi view --browse-storyboards`
- `phi view --load-storyboard <name>`
- `phi view --add-to-storyboard <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-storyboard <name> <output-dir>`

Filter flags:
- `--storyboard-filter-tags <comma,separated>`
- `--storyboard-filter-sector <sector>`
- `--storyboard-filter-type <type>`

### Storyboard export artifacts

- `storyboard_manifest.json`
- `storyboard_index.html`
- `storyboard.json`
- `sections/section_*.json`
- `comparative_summary.json`
- preview metadata and optional integrity hashes

### Comparative report intent

Storyboards and comparative summaries are deterministic local observatory curation layers:
- they do not alter PhiKernel truth logic,
- they do not validate physical laws,
- theoretical attractor references are structural,
- bio-band references are experimental guidance,
- Hunter’s C remains unconfirmed.


## Phase 18: Atlas Gallery, Route Timelines, Sector Snapshots, and Longitudinal Summaries

Phase 18 adds archive-wide atlas gallery views, storyboard-linked route timeline surfacing, sector-comparison dashboard snapshots, and optional longitudinal summary exports over repeated archive artifacts.

### Atlas gallery and longitudinal workflows

- `phi view --atlas-gallery`
- `phi view --export-longitudinal-summary <output-dir>`

Optional filters/titles:
- `--longitudinal-title <title>`
- `--longitudinal-filter-tags <comma,separated>`
- `--longitudinal-filter-sector <sector>`
- `--longitudinal-filter-target <theoretical|bio_band|node>`

### Longitudinal export artifacts

- `longitudinal_manifest.json`
- `longitudinal_index.html`
- `longitudinal_summary.json`
- `sector_snapshot.json`
- `atlas_gallery_summary.json`
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Atlas galleries, route timelines, sector snapshots, and longitudinal summaries are local interpretive curation layers.
- Theoretical attractor references are structural.
- Bio-band references remain experimental guidance.
- Hunter’s C remains unconfirmed.
- None of these reports alter PhiKernel truth logic.


## Phase 19: Cross-Report Observatory Dossiers

Phase 19 adds portable static/local dossier bundles that unify storyboards, route-compare bundles, atlas-gallery outputs, longitudinal summaries, and archive-wide thematic curation into one cross-report navigation layer.

### Dossier workflows

- `phi view --create-dossier <name>`
- `phi view --browse-dossiers`
- `phi view --load-dossier <name>`
- `phi view --add-to-dossier <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-dossier <name> <output-dir>`

Optional dossier filters:
- `--dossier-tags <comma,separated>`
- `--dossier-filter-tags <comma,separated>`
- `--dossier-filter-sector <sector>`
- `--dossier-filter-type <type>`
- `--dossier-filter-target <theoretical|bio_band|node>`

### Dossier export artifacts

- `dossier_manifest.json`
- `dossier_index.html`
- `dossier.json`
- `sections/section_*.json`
- `dossier_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Dossiers and curation filters are local interpretive observatory layers.
- Theoretical attractor references are structural.
- Bio-band references remain experimental guidance.
- Hunter’s C remains unconfirmed.
- Dossiers do not alter PhiKernel truth logic.


## Phase 20: Archive-wide Field Libraries

Phase 20 adds static local Field Libraries that organize dossiers, storyboards, route-compare bundles, longitudinal summaries, and related artifacts into reusable thematic collections with lightweight local indexing/navigation.

### Field library workflows

- `phi view --create-field-library <name>`
- `phi view --browse-field-libraries`
- `phi view --load-field-library <name>`
- `phi view --add-to-field-library <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-field-library <name> <output-dir>`

Optional field-library filters:
- `--field-library-tags <comma,separated>`
- `--field-library-filter-tags <comma,separated>`
- `--field-library-filter-sector <sector>`
- `--field-library-filter-type <type>`
- `--field-library-filter-target <theoretical|bio_band|node>`

### Field library export artifacts

- `field_library_manifest.json`
- `field_library_index.html`
- `field_library.json`
- `collections/collection_*.json`
- `field_library_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Field libraries and thematic collections are local interpretive observatory layers.
- Theoretical attractor references are structural.
- Bio-band references remain experimental guidance.
- Hunter’s C remains unconfirmed.
- Field libraries do not alter PhiKernel truth logic.

## Phase 21: Observatory Shelves + Cross-Library Catalog

Phase 21 adds additive, static/local Observatory Shelves and cross-library Catalog views that sit above field libraries, dossiers, storyboards, and related observatory artifacts for archive-scale browsing.

### Shelf workflows

- `phi view --create-shelf <name>`
- `phi view --browse-shelves`
- `phi view --load-shelf <name>`
- `phi view --add-to-shelf <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-shelf <name> <output-dir>`

Optional shelf filters/tags:
- `--shelf-title <title>`
- `--shelf-summary <summary>`
- `--shelf-tags <comma,separated>`
- `--shelf-filter-tags <comma,separated>`
- `--shelf-filter-sector <sector>`
- `--shelf-filter-type <type>`

### Catalog workflows

- `phi view --browse-catalog`
- `phi view --browse-catalog --catalog-filter-tags <comma,separated>`
- `phi view --browse-catalog --catalog-filter-sector <sector>`
- `phi view --browse-catalog --catalog-filter-type <type>`
- `phi view --browse-catalog --catalog-group-by <artifact_type|collection|sector_family|dominant_sector|target_mode|heat_mode|has_bio|has_diagnostics>`
- `phi view --browse-catalog --output <path.html>` (static local catalog page)

### Shelf export artifacts

- `shelf_manifest.json`
- `shelf_index.html`
- `shelf.json`
- `items/item_*.json`
- `shelf_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Shelves, catalogs, collections, route comparisons, and longitudinal summaries are local observatory interpretation and curation only.
- `C_STAR_THEORETICAL = PHI / 2 = (1 + sqrt(5)) / 4` is a structural/theoretical reference.
- `BIO_VACUUM_TARGET = 0.81055` with `[BIO_VACUUM_BAND_LOW, BIO_VACUUM_BAND_HIGH] = [0.807, 0.813]` remains experimental guidance.
- `BIO_VACUUM_STATUS = "experimental"` and `HUNTER_C_STATUS = "unconfirmed"` remain explicit.
- Shelf/catalog layers do not alter PhiKernel truth logic.

### Backward compatibility note

Older field libraries, dossiers, storyboards, route-compare bundles, longitudinal summaries, insight packs, pathways, atlas exports, sessions, compare sets, narratives, and constellations continue loading with safe defaults even when shelf/catalog metadata is absent.

## Phase 22: Observatory Reading Rooms + Themed Collection Maps

Phase 22 adds additive, static/local Reading Rooms and Collection Maps above shelves/field libraries to provide curated archive entry points with deterministic metadata navigation.

### Reading room workflows

- `phi view --create-reading-room <name>`
- `phi view --browse-reading-rooms`
- `phi view --load-reading-room <name>`
- `phi view --add-to-reading-room <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-reading-room <name> <output-dir>`

Optional reading-room fields:
- `--reading-room-title <title>`
- `--reading-room-summary <summary>`
- `--reading-room-tags <comma,separated>`

### Collection map workflows

- `phi view --create-collection-map <name>`
- `phi view --browse-collection-maps`
- `phi view --load-collection-map <name>`
- `phi view --export-collection-map <name> <output-dir>`
- `--collection-map-tags <comma,separated>`
- `--collection-map-filter-tags <comma,separated>`
- `--collection-map-filter-sector <sector>`
- `--collection-map-filter-type <type>`
- `--collection-map-group-by <field>`

### Reading room export artifacts

- `reading_room_manifest.json`
- `reading_room_index.html`
- `reading_room.json`
- `sections/section_*.json`
- `reading_room_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Collection map export artifacts

- `collection_map_manifest.json`
- `collection_map_index.html`
- `collection_map.json`
- `collection_map_summary.json`
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Reading rooms, collection maps, shelves, catalogs, and downstream curation artifacts remain local interpretive layers only.
- `C_STAR_THEORETICAL = PHI / 2 = (1 + sqrt(5)) / 4` is structural/theoretical framing.
- `BIO_VACUUM_TARGET = 0.81055` and `[BIO_VACUUM_BAND_LOW, BIO_VACUUM_BAND_HIGH] = [0.807, 0.813]` remain experimental guidance.
- `BIO_VACUUM_STATUS = "experimental"` and `HUNTER_C_STATUS = "unconfirmed"` remain explicit.
- These layers do not alter PhiKernel truth logic.

### Backward compatibility note

Older artifacts (field libraries, dossiers, storyboards, route-compare bundles, longitudinal summaries, insight packs, pathways, atlas exports, sessions, compare sets, narratives, constellations, shelves, catalogs) continue loading with safe defaults even when reading-room/collection-map metadata is absent.

## Phase 23: Observatory Study Halls + Comparative Thematic Pathways

Phase 23 adds additive, static/local Study Halls and Thematic Pathways above reading rooms and collection maps to support archive-wide learning/exploration with deterministic metadata navigation.

### Study hall workflows

- `phi view --create-study-hall <name>`
- `phi view --browse-study-halls`
- `phi view --load-study-hall <name>`
- `phi view --add-to-study-hall <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-study-hall <name> <output-dir>`
- `--study-hall-title <title>`
- `--study-hall-summary <summary>`
- `--study-hall-tags <comma,separated>`

### Comparative thematic pathway workflows

- `phi view --create-thematic-pathway <name>`
- `phi view --browse-thematic-pathways`
- `phi view --load-thematic-pathway <name>`
- `phi view --export-thematic-pathway <name> <output-dir>`
- `--thematic-pathway-tags <comma,separated>`
- `--thematic-pathway-filter-tags <comma,separated>`
- `--thematic-pathway-filter-sector <sector>`
- `--thematic-pathway-filter-type <type>`
- `--thematic-pathway-group-by <field>`

### Study hall export artifacts

- `study_hall_manifest.json`
- `study_hall_index.html`
- `study_hall.json`
- `modules/module_*.json`
- `study_hall_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Thematic pathway export artifacts

- `thematic_pathway_manifest.json`
- `thematic_pathway_index.html`
- `thematic_pathway.json`
- `thematic_pathway_summary.json`
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Study halls, thematic pathways, reading rooms, collection maps, shelves, catalogs, and related curation artifacts are local observatory interpretation only.
- `C_STAR_THEORETICAL = PHI / 2 = (1 + sqrt(5)) / 4` remains structural/theoretical framing.
- `BIO_VACUUM_TARGET = 0.81055` and `[BIO_VACUUM_BAND_LOW, BIO_VACUUM_BAND_HIGH] = [0.807, 0.813]` remain experimental guidance.
- `BIO_VACUUM_STATUS = "experimental"` and `HUNTER_C_STATUS = "unconfirmed"` remain explicit.
- These layers do not alter PhiKernel truth logic.

### Backward compatibility note

Older reading rooms, collection maps, field libraries, dossiers, storyboards, route-compare bundles, longitudinal summaries, insight packs, pathways, atlas exports, sessions, compare sets, narratives, constellations, shelves, and catalogs continue loading with safe defaults when study-hall/thematic-pathway metadata is absent.

## Phase 24: Observatory Curricula + Comparative Journey Ensembles

Phase 24 adds additive, static/local Curricula and Comparative Journey Ensembles above study halls and thematic pathways to support reusable archive-wide learning tracks and deterministic comparative exploration.

### Curriculum workflows

- `phi view --create-curriculum <name>`
- `phi view --browse-curricula`
- `phi view --load-curriculum <name>`
- `phi view --add-to-curriculum <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-curriculum <name> <output-dir>`
- `--curriculum-title <title>`
- `--curriculum-summary <summary>`
- `--curriculum-tags <comma,separated>`

### Comparative journey ensemble workflows

- `phi view --create-journey-ensemble <name>`
- `phi view --browse-journey-ensembles`
- `phi view --load-journey-ensemble <name>`
- `phi view --export-journey-ensemble <name> <output-dir>`
- `--journey-ensemble-tags <comma,separated>`
- `--journey-ensemble-filter-tags <comma,separated>`
- `--journey-ensemble-filter-sector <sector>`
- `--journey-ensemble-filter-type <type>`
- `--journey-ensemble-group-by <field>`

### Curriculum export artifacts

- `curriculum_manifest.json`
- `curriculum_index.html`
- `curriculum.json`
- `units/unit_*.json`
- `curriculum_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Journey ensemble export artifacts

- `journey_ensemble_manifest.json`
- `journey_ensemble_index.html`
- `journey_ensemble.json`
- `journey_ensemble_summary.json`
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Curricula, comparative journey ensembles, study halls, thematic pathways, reading rooms, collection maps, shelves, catalogs, and related curation artifacts are local observatory interpretation only.
- `C_STAR_THEORETICAL = PHI / 2 = (1 + sqrt(5)) / 4` remains structural/theoretical framing.
- `BIO_VACUUM_TARGET = 0.81055` and `[BIO_VACUUM_BAND_LOW, BIO_VACUUM_BAND_HIGH] = [0.807, 0.813]` remain experimental guidance.
- `BIO_VACUUM_STATUS = "experimental"` and `HUNTER_C_STATUS = "unconfirmed"` remain explicit.
- These layers do not alter PhiKernel truth logic.

### Backward compatibility note

Older study halls, thematic pathways, reading rooms, collection maps, field libraries, dossiers, storyboards, route-compare bundles, longitudinal summaries, insight packs, pathways, atlas exports, sessions, compare sets, narratives, constellations, shelves, and catalogs continue loading with safe defaults when curriculum/journey-ensemble metadata is absent.

## Phase 25: Observatory Syllabi + Comparative Atlas Cohorts

Phase 25 adds additive, static/local Syllabi and Comparative Atlas Cohorts above curricula and journey ensembles to support reusable program-level tracks and deterministic cross-sequence comparison.

### Syllabus workflows

- `phi view --create-syllabus <name>`
- `phi view --browse-syllabi`
- `phi view --load-syllabus <name>`
- `phi view --add-to-syllabus <name> --section-type <type> --artifact-ref <ref>`
- `phi view --export-syllabus <name> <output-dir>`
- `--syllabus-title <title>`
- `--syllabus-summary <summary>`
- `--syllabus-tags <comma,separated>`

### Comparative atlas cohort workflows

- `phi view --create-atlas-cohort <name>`
- `phi view --browse-atlas-cohorts`
- `phi view --load-atlas-cohort <name>`
- `phi view --export-atlas-cohort <name> <output-dir>`
- `--atlas-cohort-tags <comma,separated>`
- `--atlas-cohort-filter-tags <comma,separated>`
- `--atlas-cohort-filter-sector <sector>`
- `--atlas-cohort-filter-type <type>`
- `--atlas-cohort-group-by <field>`

### Syllabus export artifacts

- `syllabus_manifest.json`
- `syllabus_index.html`
- `syllabus.json`
- `modules/module_*.json`
- `syllabus_summary.json`
- optional sector/diagnostics/route-context summaries
- preview metadata and optional integrity hashes

### Atlas cohort export artifacts

- `atlas_cohort_manifest.json`
- `atlas_cohort_index.html`
- `atlas_cohort.json`
- `atlas_cohort_summary.json`
- preview metadata and optional integrity hashes

### Scientific framing reminder

- Syllabi, atlas cohorts, curricula, journey ensembles, study halls, thematic pathways, reading rooms, collection maps, shelves, catalogs, and related curation artifacts are local observatory interpretation only.
- `C_STAR_THEORETICAL = PHI / 2 = (1 + sqrt(5)) / 4` remains structural/theoretical framing.
- `BIO_VACUUM_TARGET = 0.81055` and `[BIO_VACUUM_BAND_LOW, BIO_VACUUM_BAND_HIGH] = [0.807, 0.813]` remain experimental guidance.
- `BIO_VACUUM_STATUS = "experimental"` and `HUNTER_C_STATUS = "unconfirmed"` remain explicit.
- These layers do not alter PhiKernel truth logic.

### Backward compatibility note

Older curricula, journey ensembles, study halls, thematic pathways, reading rooms, collection maps, field libraries, dossiers, storyboards, route-compare bundles, longitudinal summaries, insight packs, pathways, atlas exports, sessions, compare sets, narratives, constellations, shelves, and catalogs continue loading with safe defaults when syllabus/atlas-cohort metadata is absent.
