# Contributing to PhiOS

Thank you for contributing to PhiOS.

## Why GPLv3

PhiOS stays GPLv3 because the project promises sovereign, auditable, local-first computing for everyone. GPLv3 ensures improvements remain open and available to the public, including downstream modifications.

We appreciate community discussion, including suggestions for permissive licensing (for example MIT), and we value the spirit behind those suggestions. For PhiOS, GPLv3 remains the license because it best protects the manifesto commitments.

## How to contribute

1. Fork and create a feature branch.
2. Run local checks before opening a PR:
   - `ruff check phios/`
   - `mypy phios/ --ignore-missing-imports`
   - `pytest -q`
   - `bash scripts/policy_no_telemetry_runtime.sh`
3. Open a PR with clear scope and rationale.

## Attribution policy

Contributors keep attribution in git history and release notes.

By contributing, you agree your changes are licensed under GPLv3 with the rest of the project.
