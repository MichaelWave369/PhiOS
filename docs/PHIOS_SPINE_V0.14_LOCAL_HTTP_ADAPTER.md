# PhiOS Spine v0.14 - Bounded Live Loopback HTTP Adapter

Spine v0.14 implements the first live transport adapter for the local HTTP response contract frozen in v0.13.

The Reality Gate contract does not change.

## What v0.14 adds

`StdlibLoopbackHttpStateProvider` performs one bounded HTTP GET against an explicitly claimed loopback URL.

The adapter uses only the Python standard library. No new runtime dependency is required.

## Authority remains explicit

A live observation still requires both grants:

- `reality.verify`
- `reality.local_http.read`

The provider class existing in the package does not itself grant network authority.

The core `RealityVerificationService` still defaults to `UnavailableLocalHttpStateProvider`.

The `phi-spine verify-claim` CLI explicitly installs the live adapter only for `local_http_response_state` claims.

## Loopback containment

The v0.13 URL contract still accepts only:

- `localhost`
- literal loopback IPv4
- literal loopback IPv6
- `http://` only

Before connecting, v0.14 resolves the host and requires every returned address to be loopback.

The connection then targets the resolved numeric loopback address while preserving the original HTTP Host header.

This prevents validation of one hostname from silently turning into a connection to a non-loopback target.

## Bounded request

The adapter performs exactly:

`GET <explicit path and query>`

It does not:

- follow redirects
- use HTTPS
- use proxy environment variables
- send cookies
- send credentials
- perform POST, PUT, PATCH, or DELETE
- retry outside the bounded loopback address set
- contact remote hosts

The total observation uses the claim timeout budget, bounded by the existing v0.13 contract to 0.1 through 10 seconds.

## Response evidence

The adapter records:

- exact claimed URL
- GET method
- HTTP status
- reason
- a small safe response-header allowlist
- SHA-256 of observed response bytes
- observed byte count
- whether the body exceeded the byte budget
- digest scope: `full` or `prefix`
- redirect-followed = false
- timeout and body budget
- elapsed milliseconds
- provider and Python version
- UTC capture timestamp

The response body itself is not written into the HTTP observation record.

Potentially sensitive headers such as `Set-Cookie`, `Authorization`, and redirect `Location` are not admitted to the recorded header subset.

## Truncation semantics

The adapter reads at most `max_body_bytes + 1` bytes.

If the sentinel byte exists:

- `body_truncated = true`
- only the bounded prefix is hashed
- `body_digest_scope = "prefix"`

Otherwise the digest scope is `full`.

## Verdict meaning

A supported result means only:

`This exact bounded loopback HTTP observation returned the expected status at the recorded time.`

It does not establish:

- semantic application health
- database health
- model readiness
- authentication correctness
- remote reachability
- firewall reachability
- upstream connectivity

## Example

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  verify-claim \
  --kind local_http_response_state \
  --statement "Ollama version endpoint returned HTTP 200." \
  --http-url http://127.0.0.1:11434/api/version \
  --expected-http-status 200
```

The next semantic rung should remain separate: validating an explicitly defined response schema or service contract is not the same operation as observing an HTTP status.
