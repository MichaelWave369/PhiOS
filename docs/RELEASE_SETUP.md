# PhiOS Release Setup (PyPI Trusted Publishing)

This document describes one-time setup for token-free publishing of `phios` using PyPI Trusted Publishing (OIDC).

## 1) Configure PyPI Trusted Publishing

1. In PyPI, open the `phios` project settings.
2. Add a new Trusted Publisher.
3. Set owner/repository to `MichaelWave369/PhiOS`.
4. Set workflow file to `.github/workflows/release.yml`.
5. Set environment name to `pypi` (recommended).

No API token is needed.

## 2) Create GitHub Environment

1. In GitHub repo settings, create environment: `pypi`.
2. Add branch protections/rules as desired.
3. Do not store PyPI tokens; OIDC is used.

## 3) Triggering releases

- Automatic: push/merge to `main` (per workflow).
- Manual: use `workflow_dispatch` from Actions tab.

The pipeline runs tests, builds packages, publishes to PyPI via OIDC, generates release notes from `CHANGELOG.md`, and creates a GitHub Release.

## Security posture

- OIDC only.
- No hardcoded credentials.
- No committed secrets.
