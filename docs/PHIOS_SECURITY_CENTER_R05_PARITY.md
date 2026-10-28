# PhiOS Security Center R0.5: FieldShield cross-runtime parity

This is a **test and validation rung**, not a new privileged scanning feature.

FieldShield's Python Sentinel and PhiOS's browser matcher now consume
identical synthetic golden vectors from the same versioned JSON contract.
The fixture is committed to both repositories:
`FieldShield/tests/fixtures/fieldshield-observation-parity.v1.json` and
`PhiOS/phishell/src/security/fixtures/fieldshield-observation-parity.v1.json`.

The FieldShield regression test runs actual Python Sentinel code. The
PhiOS test generates a fresh in-memory Ed25519 signer, verifies the
fixture pack using its normal WebCrypto signed-pack gate, then matches
the same synthetic observations. Both assert the same ordered findings,
decisions and inspected/uninspected counts.

Covered cases: every observation kind, URL hostname fallback, exact
near-misses, invalid partial evidence, an empty evidence scope, trailing
domain dots and private URL queries excluded from reported results.

The PhiOS matcher now validates an observation before incrementing
`inspected`. A rejected normalization path cannot double-count an
observation as both inspected and uninspected. Matching continues to
be **operator-selected JSON only**, with no host/file/process scanning,
file upload, network activity, IPC, telemetry, remediation or authority.

Run:

    cd phishell
    npm test
    npm run build

These vectors establish tested parity for **these cases only**, not all
possible inputs. Python `urllib.parse.urlsplit` and browser `URL`
differ on certain malformed or unusual URL forms. Before claiming complete
parity, add negative/fuzz corpus coverage and decide documented
compatibility policy for those forms. Invalid or unmatched evidence
remains non-authoritative and never means that a device is safe.

All IOC values are synthetic. No trusted signing keys, sensitive evidence,
system-scanning privileges or spyware claims are added.
