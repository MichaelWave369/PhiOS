# PhiOS R1-H6: GitPorch HomeNode native trust adapter

**Status: operator-initiated native observation adapter. Not a daemon, browser bridge, fully installed OS integration or field-tested LAN deployment.**

This milestone connects PhiOS's existing Python networking package to the exact metadata-only capability handshake implemented in [GitPorch R1-H4](https://github.com/MichaelWave369/GitPorch/pull/19) and the [GitPorch R1-H5 native companion](https://github.com/MichaelWave369/GitPorch/pull/20).

The interface is **not** a Git remote, backup manager, GitHub sync client, app launcher, model runner or authority broker. It never calls the old unsecured GitPorch ports `3690` and `9418`.

## Interface

Install PhiOS as already documented in its README, then use the `phi-homenode` CLI or `python -m phios.network.homenode_cli`:

~~~powershell
# Safe with no configuration and no network calls:
phi-homenode status --mode offline
phi-homenode status --mode public

# LOCAL mode requires an operator-provisioned, trusted GitPorch gateway
phi-homenode status --mode local
~~~

### Mode semantics

| Requested | Network | Returned state |
| --- | --- | --- |
| OFFLINE | None | `OFFLINE_SELECTED_NOT_VERIFIED` |
| PUBLIC | None | `PUBLIC_SELECTED_NOT_PROBED` |
| LOCAL | Single authenticated HTTPS GET to trusted private IPv4 | `LOCAL_GATEWAY_VERIFIED_ONLY` on exact valid gateway contract |
| LOCAL failure | Never retries via public internet | `LOCAL_FAILED_OFFLINE_MODE_SELECTED` with explicit `offlineServicesVerified: false` |

In all cases, `actionAuthority: false`. Even successful LOCAL is only evidence that the specific pinned gateway responded with the expected restricted capability schema. It is **not proof** of working repo access, file integrity, backup restoration, server identity independent of trust provisioning, PhiOS app readiness, or machine availability after the probe.

### Operator-provisioned credentials

First provision the separate GitPorch R1-H4 gateway on a trusted LAN machine, with a valid TLS certificate carrying an IP Subject Alternative Name for its **specific RFC1918 IP address**. Store its public TLS certificate and an independently provisioned bearer token in private files on the PhiOS client machine. This pilot uses GitPorch's shared gateway token rather than per-client scoped credentials. No key or token should be copied into source control.

~~~powershell
# Example only: replace private IP, paths and independently verified fingerprint.
$env:PHIOS_HOMENODE_IP = '192.168.1.50'
$env:PHIOS_HOMENODE_PORT = '3743'
$env:PHIOS_HOMENODE_CERT_FILE = 'C:\Private\PhiOS\homenode-cert.pem'
$env:PHIOS_HOMENODE_TOKEN_FILE = 'C:\Private\PhiOS\homenode-token.txt'
$env:PHIOS_HOMENODE_CERT_SHA256 = '<64-lowercase-or-uppercase-hex-certificate-fingerprint>'

phi-homenode preflight
phi-homenode status --mode local
~~~

Only explicit LOCAL mode uses these variables. Neither PUBLIC nor OFFLINE reads the files or connects to a network.

`phi-homenode fingerprint <absolute-path-to-public-cert.pem>` reports a **candidate** SHA-256 fingerprint for local inspection. It **cannot authenticate the certificate by itself**. Verify the fingerprint separately through a trusted operator-controlled channel before setting it in the environment.

### Trust and transport contract

The Python standard library client is deliberately small and has no added packages:

- Enforces an exact specific RFC1918/loopback IPv4, not a hostname, redirect, public IP, wildcard bind, or proxy URL.
- Loads a regular certificate file and regular token file from operator-set absolute paths, denying symlinks and excessive file sizes.
- Matches the expected certificate's SHA-256 fingerprint using a constant-time comparison.
- Creates a TLS-verifying context from the operator-approved PEM; TLS checks the remote IP identity against the certificate SAN, its validity and trust.
- Verifies the connected peer certificate's SHA-256 fingerprint **before** sending the Authorization Bearer header.
- Performs **only** `GET /v1/capabilities` over HTTPS, with a 5-second socket timeout, 16 KiB response bound, no redirect handling, and a strict JSON schema for R1-H4.
- Returns only a sanitized capability subset (`localGitStorage`, `localSnapshots`, `publicGitHubImport`); explicitly rejects a server claiming remote Git read/push, builds, browser access or sync.
- Emits categorized failures only (`LOCAL_CONFIGURATION_REQUIRED`, `LOCAL_UNTRUSTED`, `LOCAL_REJECTED`, `LOCAL_TIMEOUT`, `LOCAL_BAD_RESPONSE`, `LOCAL_UNAVAILABLE`). Local secrets, raw network errors, URLs and certs never appear in the output.

The certificates and token are still **files**. This milestone does not use Windows DPAPI, an OS keychain, client-specific scoped tokens, a revocation registry or enterprise certificate issuance. A compromised client process can read its token. Review and restrict filesystem ACLs manually.

### Integration in PhiOS

The adapter is a normal PhiOS Python module at `phios.network.homenode`, exported via `phios.network.select_homenode_mode`, and packaged as the `phi-homenode` entry point. It does not alter PhiShell's current Home user interface, the PhiOS Pages site, the App Platform, network discovery broadcasting, any service startup, or Linux image build.

**Do not add the private bearer token or user-specific LAN IP to the public React site or EnterTheField.org.** GitPorch's gateway intentionally blocks browser Origin/CORS requests. A future secured, separately approved native IPC/same-origin adapter may expose **sanitized status only**, after authentication, origin validation and a security review. Even there, simply changing the selected mode must not grant a network connection, app launch or Git write authority.

### Tests and deployment reality

Focused `tests/test_homenode_r1h6.py` cover offline/public network silence, forbidden IP/port configurations, missing credentials, certificate pinning, real locally generated TLS with the GitPorch response contract, invalid bearer token, malformed/overprivileged JSON, and symlink rejection where supported.

~~~bash
python -m pytest tests/test_homenode_r1h6.py -q
ruff check phios/network/homenode.py phios/network/homenode_cli.py
mypy phios/network/homenode.py phios/network/homenode_cli.py --ignore-missing-imports
~~~

Full-repository CI, Windows certificate file permission behavior, on-device two-PC LAN interoperability against the **actual Node gateway**, firewall policies, restart/shutdown and loss-of-WAN operation must still be tested before declaring production readiness.

**Ledger Above Ego:** a capability observation is not authority or an offline disaster-recovery certification.
