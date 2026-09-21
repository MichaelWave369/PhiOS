# PhiOS API Key Boundary v0.1

## Status

Implementation candidate on the research-hardening v0.9 branch.

Primary contracts:

```text
phios.api_key_boundary.v0.1
phios.api_key_auth_receipt.v0.1
phios.api_key_lease_receipt.v0.1
```

Primary rule:

```text
AUTHENTICATED
!=
AUTHORIZED
```

API keys prove configured credential possession or provide a bounded credential to an
adapter. They do not create PhiOS action authority.

## Two directions

PhiOS treats input and output keys as different contracts.

### Input / inbound key

An inbound key authenticates a caller to a configured PhiOS-facing audience.

The stored contract contains:

```text
key_id
audience
SHA-256(secret)
scopes
```

The plaintext secret is not part of the public contract and is not written to receipts.

Keys can be configured either from a transient plaintext setup value or directly from a
precomputed SHA-256 digest.

Authentication uses constant-time digest comparison.

## Inbound header helper

For HTTP/API gateways, the boundary can authenticate a presented header directly:

```python
receipt = spine.api_keys.authenticate_inbound_headers(
    key_id="operator-input",
    headers=request_headers,
    audience="phios.http",
    header_name="X-API-Key",
)
```

Successful authentication may return the scopes attached to that key slot.

Failed authentication returns no scopes.

The receipt always fixes:

```text
credential_exposed    = false
operational_authority = false
action_authority      = false
execution_authority   = false
```

Authentication therefore cannot widen `AuthorityContext`.

## Output / outbound key

An outbound key lets an adapter obtain a credential for a named provider.

The configured contract contains:

```text
key_id
provider
environment-variable reference
header name
header-prefix mode
scopes
```

The raw secret is resolved only when a lease is requested.

Example:

```python
spine.api_keys.register_outbound(
    OutboundApiKeySpec(
        key_id="vendor-output",
        provider="vendor",
        environment_variable="VENDOR_API_KEY",
    )
)

lease = spine.api_keys.lease_outbound(
    key_id="vendor-output",
    provider="vendor",
)

headers = lease.authorization_headers()
```

The resulting header defaults to:

```text
Authorization: Bearer <secret>
```

Custom API-key headers are also supported:

```python
OutboundApiKeySpec(
    key_id="vendor-output",
    provider="vendor",
    environment_variable="VENDOR_API_KEY",
    header_name="X-API-Key",
    header_prefix="",
)
```

## Ephemeral secret handling

`OutboundApiKeyLease` holds the secret only for use by the current process.

Its normal repr hides the secret.

Its serializable metadata returns:

```text
secret = [REDACTED]
```

The lease receipt does not include:

- the raw API key;
- the environment-variable name;
- an authorization header value.

The boundary also refuses to overwrite an already-present credential header, avoiding
ambiguous stacked authentication.

## Provider binding

An output key is bound to one configured provider.

A key registered for:

```text
provider = vendor-a
```

cannot be leased under:

```text
provider = vendor-b
```

without a separate key contract.

Input and output key IDs share one namespace, so the same key ID cannot accidentally be
registered in both directions.

## Relationship to capability effects

The API-key boundary only manages credentials.

It does not perform network I/O.

A capability that actually calls an external API should separately declare the real
environmental effects, typically including:

```text
credential.read
network.request
```

and, when applicable:

```text
external_state.read
external_state.change
```

Those effects remain governed by the existing EffectBoundaryPolicy and downstream
authority/execution contracts.

## Secret configuration

Do not commit real API keys to the PhiOS repository.

For outbound keys, keep plaintext credentials in the process environment or a future
replaceable secret provider.

For inbound keys, deployments may store only a SHA-256 digest when the plaintext key is
needed solely for verification.

The current boundary is intentionally storage-neutral. It does not create a plaintext
secret database inside PhiOS.

## Security properties

v0.1 is designed to prevent:

- raw API-key material in ordinary receipts;
- wrong-audience inbound authentication;
- scope disclosure on failed authentication;
- output-key use under the wrong provider identity;
- implicit replacement of an existing credential header;
- API-key possession becoming action or execution authority.

## Bounded claim

This contract does not claim that environment variables are the final ideal secret
backend, that API keys cannot be stolen from a compromised process, or that successful
authentication proves a caller should be allowed to perform a requested PhiOS action.

It proves a narrower boundary:

> PhiOS can accept input API keys and supply output API keys without storing them in
> ordinary receipts or confusing credential possession with execution authority.

Future secret backends can replace environment lookup without changing this governing
contract.
