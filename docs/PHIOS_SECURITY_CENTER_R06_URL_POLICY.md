# Security Center R0.6: strict cross-runtime URL authority policy

FieldShield Sentinel and PhiOS's browser-based exact-indicator matcher can now reject the same common **ambiguous URL host forms**, instead of letting Python `urlsplit` and browser `URL` produce contradictory hostnames.

This does **not** introduce a device scan, background check, remote lookup or any host authority. Security Center continues to require user-selected JSON observations and freshly verified signed IOC pack bytes.

## Authority profile

The shared policy accepts HTTP(S) URLs with conservative ASCII DNS authorities. Accepted values retain their exact text. It rejects: percent-encoded or Unicode hostnames, backslashes, IPv6 literals, shorthand or numeric-only IP hosts, credentials, DNS-invalid labels, ambiguous ports, whitespace and control characters. Punycode must be supplied explicitly as ASCII, rather than dynamically introduced by browser normalization.

This is intentionally narrower than all legal URLs. Previously accepted unusual URLs can now fail closed. Invalid observation entries count toward **uninspected** and make the scope INCOMPLETE. A signed pack containing an unsupported URL indicator is rejected entirely after signature verification but before matching.

The canonical cross-runtime regression corpus is duplicated byte-for-byte in
`FieldShield/tests/fixtures/fieldshield-url-authority-parity.v1.json` and
`PhiOS/phishell/src/security/fixtures/fieldshield-url-authority-parity.v1.json`.

Separate test suites verify accepted hostname behavior, rejected parser ambiguities and negative consented-observation matching. Regression tests cannot prove universal parser parity or accurately identify device compromise.

Run `cd phishell && npm test && npm run build`. Review paired FieldShield PR before merging either change.
