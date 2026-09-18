# Contributing to PhiOS

Thank you for contributing to PhiOS.

## Phi Commons license

PhiOS project-owned code and documentation are released under the MIT License unless otherwise noted.

By submitting a contribution for inclusion, you agree that the contribution may be distributed under the MIT License and represent that you have the right to submit it under those terms.

Do not submit third-party code, model weights, datasets, fonts, media, or other material unless its license permits the intended use and the required attribution/notice is included.

## How to contribute

1. Fork and create a feature branch.
2. Keep capability separate from authority. New executors, agents, models, and tools do not receive permissions merely because they exist.
3. Run local checks before opening a PR:
   - `ruff check phios/`
   - `mypy phios/ --ignore-missing-imports`
   - `pytest -q`
   - `bash scripts/policy_no_telemetry_runtime.sh`
4. Open a PR with clear scope, rationale, and any new dependency or license impact.

## Third-party dependency changes

A PR adding a runtime dependency must identify:

- package/project name;
- version range;
- upstream source;
- license;
- whether PhiOS redistributes or merely depends on it.

If a dependency introduces a redistribution obligation, update `THIRD_PARTY_NOTICES.md`.

## Model and dataset changes

A PR that bundles or automatically downloads model weights or datasets must update `MODEL_LICENSES.md` and clearly distinguish PhiOS's MIT-licensed integration code from the separate model or dataset license.

## Attribution policy

Contributors keep attribution in git history and release notes.

The repository license does not grant rights to third-party trademarks or identity marks.
