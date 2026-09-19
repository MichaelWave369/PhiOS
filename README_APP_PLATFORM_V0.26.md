# PhiOS App Platform v0.26

PhiOS App Platform v0.26 adds **bounded public GitHub intake** above the v0.25 manifest + registry layer.

The intake path can inspect one explicitly named public GitHub repository and produce:

- bounded repository evidence;
- a deterministic app proposal;
- an optional v0.25 manifest candidate.

It still does **not** clone, install, build, register, trust, or launch the repository.

## Explicit command

```bash
phi-app inspect-github https://github.com/OWNER/REPO
```

The command is an explicit public-network read. It emits JSON only.

## Bounded intake

v0.26 reads only GitHub API metadata, the default branch head, the repository root, and up to eight known root discovery files.

Candidate discovery files include:

- `phios-app.json`;
- `package.json`;
- `pyproject.toml`;
- `index.html`;
- `Cargo.toml`;
- `go.mod`;
- selected Netlify/Vite markers.

No recursive checkout or arbitrary source crawl occurs.

## Proposal rules

A valid root `phios-app.json` is treated as an explicit declaration, not as trusted truth.

Without that file, v0.26 can propose bounded runtime candidates from known markers:

- `package.json` → Node;
- `pyproject.toml` → Python;
- `index.html` → static web;
- `Cargo.toml` / `go.mod` → native build candidate.

Permissions are **never inferred from source code** in v0.26.

If no explicit `phios-app.json` is present, the proposed permission list remains empty and is marked as requiring operator declaration before execution.

## License boundary

GitHub-reported SPDX metadata may populate `license_expression`.

Redistribution remains `unknown` for inferred candidates. PhiOS does not turn a public repository or a recognized SPDX identifier into an automatic legal redistribution decision.

## Evidence minimization

Discovery file contents are transient.

Persisted intake evidence includes only bounded metadata such as:

- repository identity;
- branch/head SHA;
- root paths;
- inspected file path;
- file byte count;
- file SHA-256.

Raw discovery file contents are not placed in the evidence object.

See `docs/PHIOS_APP_PLATFORM_V0.26_GITHUB_INTAKE.md`.
