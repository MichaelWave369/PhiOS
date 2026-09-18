# PhiOS Spine v0.13 - Local HTTP Response Verification Contract

Spine v0.13 freezes the Reality Gate contract for bounded loopback HTTP response observations.

It deliberately separates the verification contract from live HTTP transport.

## Bounded claim

```text
Did this exact loopback HTTP URL return this exact HTTP status code?
```

That is not the same claim as:

```text
Is the application healthy?
```

## New claim kind

`local_http_response_state`

Required:

- http_url
- expected_http_status

Observation parameters:

- http_timeout_seconds, default 2.0, bounded to 0.1 through 10.0
- http_max_body_bytes, default 65536, bounded to 1 through 1048576

## Local-only URL policy

The claim contract accepts only HTTP URLs using:

- `localhost`
- literal loopback IPv4
- literal loopback IPv6

It rejects:

- non-loopback hosts
- HTTPS in v0.13
- URL userinfo
- fragments
- invalid ports

## Authority

Two grants are required:

`reality.verify`

and:

`reality.local_http.read`

## Provider boundary

v0.13 defines `LocalHttpStateProvider`.

The default implementation is intentionally:

`UnavailableLocalHttpStateProvider`

It fails closed with:

`local_http_provider_unavailable`

This means the core Reality Gate does not silently gain network-I/O authority merely because an HTTP claim type exists.

A live loopback transport adapter can be added later behind the same provider contract without changing claim or receipt semantics.

## Injected observation evidence

When an authorized provider returns a response observation, PhiOS stores content-addressed JSON containing:

- exact URL
- method
- HTTP status
- reason
- safe response-header subset supplied by the provider
- body SHA-256 metadata
- observed body byte count
- truncation state
- digest scope
- redirect-followed flag
- timeout and body budget
- elapsed milliseconds
- provider and version
- capture timestamp

The response body itself is not required in the Reality observation record.

## Verdicts

Observed status equals expected status:

`SUPPORTED`

Observed status differs:

`CONTRADICTED`

Provider unavailable or observation fails:

`UNRESOLVED`

Invalid URL/parameters or missing permissions:

`BLOCKED`

## Important non-claims

Even a supported HTTP 200 claim does not establish:

- semantic application health
- database health
- model readiness
- remote reachability
- firewall reachability
- authentication correctness
- upstream connectivity

It establishes only the exact bounded response-state claim represented by the provider observation.

## CLI

The claim can be expressed through the CLI:

```bash
phi-spine \
  --allow reality.verify \
  --allow reality.local_http.read \
  verify-claim \
  --kind local_http_response_state \
  --statement "The local health endpoint returns HTTP 200." \
  --http-url http://127.0.0.1:8000/health \
  --expected-http-status 200
```

Without an installed live transport adapter, the result is UNKNOWN / UNRESOLVED by design.

## Still excluded

v0.13 does not ship a live HTTP transport adapter, HTTPS, remote HTTP probing, redirect following, authentication, cookies, POST requests, application-specific health semantics, LAN discovery, or internet access.
