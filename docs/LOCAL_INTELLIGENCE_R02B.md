# Operation Local Intelligence R0.2b — Ollama manifest-to-blob review

An explicit, offline companion to R0.1 and R0.2. It reads one selected
Ollama schemaVersion 2 manifest and checks every referenced config and layer
blob against the manifest's declared byte count and SHA-256.

## Windows operator pilot

From the PhiOS checkout, select your actual model root and manifest path.
The following is an example only; it assumes the conventional per-user
Ollama layout and the example tag is installed. A custom OLLAMA_MODELS
directory must be supplied explicitly.

```powershell
python -m phios.local_ollama_blobs --root "$env:USERPROFILE\\.ollama\\models" --manifest "manifests/registry.ollama.ai/library/qwen3/4b"
python -m pytest tests/test_local_ollama_blobs.py
```

The manifest argument is a forward-slash relative path under manifests.
No recursive inventory, tag resolution, environment lookup, network calls,
downloads, subprocesses, inference, or writes are performed. The tool
accepts at most 64 descriptors, a 256 KiB manifest, and a default 32 GiB
logical blob read budget (configurable up to 128 GiB with --max-bytes).
Repeated matching digests are counted once for bytes. Declared totals and
ordinary file sizes are checked before hashing any blobs.

## Receipt meanings

- BLOB_BYTES_MATCH_REVIEW_ONLY: all listed descriptors match their local
  readable bytes and each model-weight descriptor has a plausible GGUF header.
- BLOB_BYTES_MATCH_WEIGHT_FORMAT_UNVERIFIED: bytes match, but at least one
  model-weight header does not match the narrow supported hint.
- NO_MODEL_WEIGHT_DESCRIPTOR: no recognized model-weight layer.
- HASH_MISMATCH: one or more blob hashes differ.
- INVALID_OR_UNREADABLE_SELECTION: malformed manifest, missing blob, size
  mismatch, exceeded budget, unsupported path or filesystem failure.

Only the first state exits 0; review states other than that exit 3, and
invalid selections exit 2. The receipt omits paths, tags, filenames and
digests; sizes and layer counts can still reveal identifying information.

## Evidence boundary

The manifest is operator-selected and unauthenticated. Matching bytes do
not prove publisher provenance, complete model semantics, architecture,
tensor validity, licensing, GPU residency or offline generation.
Cloud references must not be inferred local from an API tag alone.
A deliberately forged manifest can point to arbitrary bytes in the
selected blob store. Header hints are not validation. No model is loaded.

This is a cooperative local operator utility, not a hostile-filesystem
sandbox: selected directories and final file entries reject symlinks and
Windows reparse points, and per-file metadata is checked while reading.
Root ancestors, remote mounts, cloud placeholders, cross-file mutations
and all race conditions are not qualified. Use a trusted local disk and
stable, non-mutating model store. The receipt is not an atomic snapshot.
Large hashes can consume disk bandwidth.

Next rung: opt-in live local chat smoke test with a fixed short public
prompt, explicit model selection and no tools, followed by separate
operator-observed hardware and offline checks. Green fixture CI alone is
not a field qualification.
