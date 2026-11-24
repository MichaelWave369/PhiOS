# Convergence R3 · source-only capability discovery

This offline pilot indexes four public source declarations using the existing PhiOS public catalog as its local membership gate. It is not an AppManifest, App Registry, ActionLease, PocketMesh admission record, worker dispatch, installation or launch permission. No existing runtime or authority path is changed.

The contract labels are catalog-local identifiers for the referenced native formats, not newly published native schemas, wire compatibility promises or automatic adapters. Some native formats have no formal schema identifier; the catalog label is only a descriptive handle. Every record includes a pinned source revision and line range, operating mode and limitations. The catalog cannot authenticate those claims, verify current public visibility or prove installation. Both resource estimates are null until a separately reviewed measurement contract exists.

Run from the repository root:

```sh
python -m interop.capability_discovery_v1
python -m interop.capability_discovery_v1 --capability causal.schedule --input-contract altermath.causal-score.r1 --output-contract altermath.causal-receipt.r1 --mode synthetic
python -m unittest discover -s tests -p 'test_capability_discovery_v1.py' -v
```

Only exact matches are returned for manual review, never admission. Synthetic and opt-in-local declarations cannot substitute for each other. No remote endpoint, credentials, arbitrary execution or conversion into PocketMesh admitted manifests is supported. Do not publish private catalog inputs.

Next gate: one bounded Altermath-to-Agentora offline fixture adapter with ordinary DAG baseline, exact output comparison, negative cases, no real agent execution and independent resource accounting. Only after a real authority contract is separately reviewed may an actual local worker be considered.
