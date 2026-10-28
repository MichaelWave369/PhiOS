# PhiOS Security Center v0.1: local read-only receipt review

**Status: historical browser-only JSON preview, not a host security claim.**

This milestone registers Security Center under PhiShell's existing Apps menu
and opens it in a normal desktop window. It is the visual integration seam
for FieldShield Sentinel and PhiARK. Neither project is automatically
installed, started, polled, network-connected, or granted privileges.

## Operator workflow

1. In an independently installed PhiARK vault, use
   `npm run intel -- verify ./my-trust.json` with a separately authenticated
   local trust file, and explicitly save the command's JSON output.
2. In FieldShield, run a user-consented local scan using
   `sentinel_verified.py scan` with independently trusted and reviewed IOC
   packs and locally collected evidence. Save the JSON report yourself.
3. In PhiShell's Security Center, select the corresponding local JSON file.
   Its summary is shown only in this window's memory; nothing is uploaded.

### What is displayed

PhiARK verification command outputs contain claimed checked, passed, and
failed counts plus publisher labels. They are not signed receipts, so their
status is IMPORTED INVENTORY - NOT LIVE VERIFIED. Historic VERIFIED_NOW rows
are treated as claims in a local file, not current cryptographic proof.

Sentinel scan report previews show reported mode, decision, inspected and
uninspected counts, finding count, a limited set of indicator IDs, and whether
the source report claims to have used an Ed25519-verified IOC pack. The
viewer does not verify this claim. Raw forensic observation values and raw
file paths are deliberately excluded from the browser projection.

No-match results do not establish a safe device. A matched indicator does
not alone prove compromise. An imported JSON report might be fabricated.

## Architecture and privacy

- Only existing React PhiShell window and app catalog are extended.
- No HTTP endpoint, background fetch, browser persistence, external assets,
  upload, automatic scan, remediation, install, trust enrollment or
  privileges are introduced.
- Files are operator-selected, limited to 1 MiB before reading, and parsed as
  untrusted JSON. The projection model validates expected schemas, bounded
  counts and row consistency and renders text with ordinary React escaping.
- The operator must independently authenticate IOC publishers and trust roots.
- This adds no live security status, no isolated OS worker and no PhiARK runtime
  authorization. PhiOS governance and the existing independent apps are
  unchanged.

## Future gates

Before presenting live host security status, build a separately reviewed
operator-authorized local verifier, bind receipts to the real evidence scope
and trusted source, ensure host isolation and consent, verify age/anti-replay,
and keep unsigned/expired/partial coverage visibly distinct. No automatic
execution authority can be inferred from a browser file chooser.

## Test commands

    cd phishell
    npm test
    npm run build

Tests cover receipt validation, malformed and contradictory JSON, size bounds,
limited projection of indicator IDs, omission of raw forensic paths, and a
static render showing NO LIVE SECURITY STATUS CLAIM.
