# Public source census — November 20, 2026

The connected owner listing and a separately paginated owner-affiliation listing
were traversed through their terminal empty pages. Filtering verified public
visibility gives 270 public `MichaelWave369` repositories. The catalog previously
contained 266. This patch adds four source entries:

- AppalachianApplications
- PhiCloneLab
- SaaC
- bitcoin

The existing `create_snapshot` and `validate_snapshot` functions generated and
validated the deterministic public-only projection. The connected listing's
`page_offset` behaved as a zero-based page index despite its item-offset help
text; observed page sizes were 100, 100, 100, 5, then 0 before the public filter.
The independent owner-affiliation enumeration returned the identical ID set.

All four entries remain `SOURCE_ONLY`, with `installed`, `launch_authorized`
and `redistribution_reviewed` false. Repository listing proves visibility;
it does not install an application, approve source execution or qualify the
upstream Bitcoin Core fork as a PhiOS service. Existing pinned readiness
profiles and governed application candidates are unchanged.
