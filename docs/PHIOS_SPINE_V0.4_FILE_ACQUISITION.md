# PhiOS Spine v0.4 - Bounded File Acquisition

Spine v0.4 adds the first local acquisition adapter to the SOMA North Gate.

The adapter reads one text-like file from an explicitly configured source root, preserves the native bytes as evidence, and then passes the decoded observation into the existing perception contract.

## Boundary rules

- source paths must be relative to the configured root
- parent traversal is blocked
- absolute paths are blocked
- symlinked source paths are blocked
- only an allowlist of text-like suffixes is accepted
- files are capped at a caller-controlled size, defaulting to 1 MiB
- invalid UTF-8 is quarantined after native bytes are preserved
- every blocked or quarantined attempt emits GateReceipt and PerceptionReceipt records
- file perception never expands the Phi Core authority envelope

## Supported suffixes

txt, md, json, csv, yaml, yml, toml, py, and log.

## Provenance

The receipt records the relative source locator and a hashed source-root reference rather than promoting the source path into authority.

Native bytes are copied into the local content-addressed evidence store before interpretation.

## Security boundary

This release rejects ordinary path traversal and symlink escapes and uses O_NOFOLLOW when the host exposes it.

It is not claimed to be a formal kernel-level race-proof filesystem sandbox. Stronger openat/openat2-style acquisition can be added as a later hardening layer without changing the receipt contract.

## Deliberate exclusions

No image files, PDFs, Office documents, OCR, browser capture, screenshots, camera input, or model interpretation are added in v0.4.
