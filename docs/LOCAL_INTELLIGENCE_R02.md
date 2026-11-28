# Operation Local Intelligence R0.2 — explicit checkpoint byte inventory

R0.1 lists documented AI capabilities and optionally reads Ollama tags.
R0.2 adds a separate, offline Python 3.11+ command for operator-selected
checkpoint files. It does not alter any inference backend.

## Windows pilot

From the repository root (replace the example paths with your own files):

```powershell
python -m phios.local_intelligence --ollama
python -m phios.local_checkpoint_inventory --checkpoint "D:\\Models\\example.gguf"
python -m phios.local_checkpoint_inventory --checkpoint "D:\\Models\\example.gguf" --expected-sha256 YOUR_TRUSTED_LOWERCASE_SHA256
```

Repeat --checkpoint for up to nine explicitly selected files. When supplying
expected digests, provide exactly one per file in the same order. Supply
--max-bytes to change the default 32 GiB cumulative logical read budget
(maximum 128 GiB). Large file hashes can take time and disk bandwidth.
No recursive discovery, automatic Ollama blob resolution, downloading,
GPU allocation, model execution, subprocesses or network API calls.

The receipt contains selection order, actual bytes read, SHA-256, optional
expected-hash comparison and conservative header hints. It omits paths,
filenames and expected digests. Actual hashes and sizes may identify a model;
review before sharing. Exit 0 = REVIEW_ONLY; 3 = HASH_MISMATCH;
2 = invalid/unreadable selection. Failed reads return no partial receipt.
Argument parser errors may display user-supplied arguments locally.

GGUF hints check magic, supported header version and minimum file size.
Safetensors hints check a bounded JSON header and basic tensor offsets.
Neither validates tensor contents, dimensions, quantization, architecture,
complete sharded checkpoints, license or inference readiness. Larger headers
can be unrecognized. Hash matches prove only equality to the supplied digest,
not authenticity of that digest. Obtain expected hashes independently from
a trusted pinned source.

The reader rejects nonregular files, final-component symlinks/reparse points
and duplicate file identities, and compares open-file and named-file metadata
before/after reading. This is a cooperative operator tool, not an adversarial
filesystem sandbox or atomic snapshot. Use ordinary files on a trusted local
disk, with other processes stopped from modifying them. Parent directories,
network mounts, sparse/cloud-placeholder files and all filesystem races
are not independently qualified. Logical bytes read do not prove physical
disk allocation or GPU residency.

## Acceptance and next rung

```powershell
python -m pytest tests/test_local_checkpoint_inventory.py
```

Synthetic fixtures exercise hashing, mismatches, malformed headers, budgets,
alias rejection, metadata changes and redacted operational errors.
Operator field run remains required. Next: explicit Ollama manifest-to-blob
verification on the actual Windows installation and a separate live chat
smoke test on one known local model. Do not infer local residency from a
model name or successful API response alone.
