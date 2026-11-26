# Phi Independence R06-A — authenticated two-node challenge

Experimental. Reuses PhiOS HomeNode trust loading and certificate pinning rules.
This is a fixed synthetic challenge, not a model router or an Agentora worker API.
No discovery, public fallback, remote shell, model invocation, archive transfer,
credential delegation, or task persistence. Only explicit RFC1918 IPv4 or 127.0.0.1.

## Private LAN pilot

Use a trusted private network, Python 3.11+ and a local PhiOS checkout on both PCs
(with PhiOS installed if needed). Run from the repository root as a module.
Choose actual private IPv4 addresses; examples below are placeholders.
Independently block WAN while retaining LAN. No router port forwards. Limit inbound
TCP 3769 on the secondary PC to the primary PC's exact LAN IP using the OS firewall.

Generate a dedicated TLS server certificate with its exact secondary IP in the
IP subjectAltName, using a trusted local certificate tool. Protect the private key
with owner-only permissions/Windows ACLs on the secondary PC. Copy only the
public certificate to the primary PC by a trusted out-of-band method. Compute
and independently compare the certificate SHA-256 fingerprint on both machines:
`python -m phios.network.homenode_cli fingerprint ABSOLUTE_CERT_PATH`.
Do not bypass certificate verification. Generate a separate random 32-byte token
as 64 lowercase hex characters using a trusted local secrets generator. Transfer
it securely to the primary PC; store both copies in owner-only files outside Git.
Never copy the TLS private key to the primary PC, commit secrets, or use a shared
general-purpose API key.

Secondary PC (example PowerShell, absolute private paths):

```powershell
python -m scripts.phi_mesh_r06a serve --bind 192.168.1.20 --peer 192.168.1.10 --node node02 --cert D:/PhiMesh/cert.pem --key D:/PhiMesh/key.pem --token-file D:/PhiMesh/token.txt --confirm-private-lan
```

Primary PC:

```powershell
python -m scripts.phi_mesh_r06a probe --ip 192.168.1.20 --node node02 --cert D:/PhiMesh/cert.pem --pin YOUR_VERIFIED_CERT_SHA256 --token-file D:/PhiMesh/token.txt --confirm-private-lan
```

The server accepts only the named client IP, uses TLS 1.2+, validates exact Host
and bearer token, and permits only POST /v1/challenge with one nonce. It computes
369 fixed SHA-256 rounds. The client independently checks the nonce, node name,
result and entire expected response. The token is sent only after certificate
chain/IP and exact live leaf pin validation. There is no automatic reconnect or
retry. Successful result PINNED_PEER_CHALLENGE_PASSED proves this particular
authenticated challenge exchange, not hardware identity or actual remote
inference capability. A peer could simulate the fixed computation.

Listener is explicit and foreground, with three handle_request iterations
and nominal 60-second accept / 5-second socket operation timeouts; slow
clients can extend wall time. Ctrl+C stops it. Single worker; no rate limiting,
service installation, mutual TLS, signed receipts, hardened hostile-client
HTTP parsing, or network isolation proof. Same-user access and compromised
peers are out of scope. Token authenticates possession, not user identity.
No real hardware benchmarks or scheduling authority. On failure do not bypass
TLS or switch to a public endpoint. Inspect routing, firewall and trust files.
Stop the listener before changing addresses or network configuration.

Tests: `pytest -q tests/test_phi_mesh_r06a.py`. Real ephemeral loopback TLS tests
when openssl CLI is available, plus refusal tests. Actual two-PC Windows
field validation, firewall policy and disconnected operation remain unverified.
Next R06-B: explicit remote synthetic inference task with local allowlist
and separate operator approval, then restart-safe task receipts.
