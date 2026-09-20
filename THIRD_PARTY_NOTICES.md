# Third-Party Notices

PhiOS is MIT-licensed for project-owned code, but its dependencies are independent works governed by their own licenses.

This document is informational and does not replace any upstream license text.

## Runtime dependencies

### psutil

- Purpose: local process/system information
- PhiOS requirement: `psutil>=5.9.0`
- Upstream license: BSD 3-Clause

### MCP Python SDK

- Purpose: Model Context Protocol client/server integration
- PhiOS requirement: `mcp>=1.26,<2`
- Upstream license: MIT

### TypeSafe AI Python SDK (optional)

- Purpose: optional Jev / System One provider for PhiReflex shadow evaluation
- PhiOS extra: `reflex-jev`
- PhiOS requirement: `typesafe-sdk>=0.7,<1`
- Upstream license: MIT
- Runtime note: the SDK calls TypeSafe's external API when configured; Jev model weights are not bundled or redistributed by PhiOS.

## Development and test dependencies

The project also uses development tools listed in `pyproject.toml` such as build, twine, requests, pytest, Ruff, and mypy.

Those tools are not relicensed by PhiOS. Their upstream licenses govern them. Before redistributing a bundled environment, installer image, or vendored copy, release maintainers must review the exact dependency versions and preserve any notices required by those upstream licenses.

## Vendored or copied code

If future PhiOS releases vendor third-party source, that material must retain its original copyright and license notice and must be recorded here or in a more specific notice file.
