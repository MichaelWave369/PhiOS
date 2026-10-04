# PhiOS App Platform v0.52 — Toolchain Capsule Acquisition and Verification

## Status

Alpha contract.

New schemas:

- `phios.capsule_acquisition_request.v0.1`
- `phios.capsule_acquisition_receipt.v0.1`

Consumes the v0.51 contracts:

- `phios.toolchain_requirement.v0.1`
- `phios.toolchain_capsule.v0.1`
- `phios.toolchain_binding.v0.1`

## Purpose

v0.51 can prove that one reviewed capsule description is compatible with one reviewed build plan.

v0.52 answers the next question:

> Do the capsule bytes actually available to PhiOS match the exact artifact identity that was reviewed?

The central rule is:

> Verified capsule bytes are evidence of availability. They are not execution authority.

## Acquisition request

A request carries:

- the exact v0.51 requirement;
- the exact v0.51 capsule;
- the exact v0.51 binding;
- explicit approval of that binding's canonical SHA-256.

Request construction reconstructs the v0.51 binding from the requirement and capsule and requires byte-for-byte canonical identity.

Therefore a binding from another build, capsule, family or artifact cannot be reused.

The approval authorizes only this bounded acquisition attempt. It does not authorize build execution.

## Providers

v0.52 defines a narrow provider boundary.

The provider returns:

- one local path containing the candidate capsule artifact bytes;
- the source artifact reference those bytes were obtained for.

The included `LocalCapsuleArtifactProvider` accepts only an explicit operator-supplied map from reviewed artifact references to local files.

There is intentionally no registry client in this rung.

No Docker, Podman, containerd, OCI registry authentication, image pull, layer extraction or container start is performed.

A future network provider may satisfy the same boundary, but it must receive its own authority and qualification.

## Artifact verification

Before new bytes enter the PhiOS capsule store, v0.52 requires:

- the provider source reference to equal the reviewed v0.51 artifact reference;
- a regular file;
- no symlink;
- non-empty bytes;
- bounded size;
- streaming SHA-256 over the exact source file;
- exact equality with `ToolchainCapsule.artifact_sha256`.

The source is copied into a digest-addressed store path:

```text
STORE/sha256/AB/FULL_SHA256.oci
```

The temporary file is created in the destination directory and renamed only after the complete expected digest is observed.

The stored artifact is made read-only when the host permits it.

## Existing store entries

If the exact digest path already exists, v0.52 does not call the provider.

It re-hashes the existing regular file and requires the bytes to match the digest encoded in the path and reviewed capsule.

A valid reuse records:

```text
storage_state = reused_verified
```

A new verified copy records:

```text
storage_state = created
```

An existing wrong artifact fails closed.

## Receipt

The acquisition receipt binds:

- app and exact source commit;
- build-plan SHA-256;
- v0.51 requirement SHA-256;
- v0.51 capsule SHA-256;
- v0.51 binding SHA-256;
- capsule ID and family;
- artifact kind and reference;
- verified artifact SHA-256;
- verified byte count;
- absolute digest-store path;
- storage state;
- status = `verified_available`;
- canonical receipt SHA-256.

The receipt is written atomically.

## Receipt authority fields

Every v0.52 receipt fixes:

```text
execution_authority = false
network_authority = false
install_authority = false
host_write_authority = false
```

These fields describe authority conferred to downstream build/runtime activity by the receipt.

The acquisition service itself may write only to its configured capsule store and receipt root in order to perform the bounded acquisition operation.

Therefore:

```text
capsule description reviewed
!= bytes acquired

bytes acquired
!= bytes verified

bytes verified
!= capsule may execute

capsule may execute
!= build network authority

build succeeds
!= app install authority
```

## Fail-closed behavior

v0.52 rejects:

- stale binding approval;
- a binding that does not reconstruct from the exact requirement/capsule;
- provider source-ref mismatch;
- missing artifact files;
- symlink artifacts;
- non-regular artifacts;
- empty artifacts;
- over-limit artifacts;
- source mutation during acquisition;
- SHA-256 mismatch;
- corrupt existing CAS entries;
- unknown receipt fields;
- receipt digest tampering;
- authority fields changed from false.

## Explicit non-capabilities

v0.52 does not:

- download from an OCI registry;
- authenticate to a registry;
- unpack or inspect OCI layers;
- attest tool binaries inside the artifact;
- execute a capsule;
- mount a capsule into the v0.30 build sandbox;
- grant dependency-network access;
- install an application;
- launch an application;
- change release or publication authority.

The v0.51 tool/version declarations remain claims bound to the reviewed capsule metadata. v0.52 proves only the identity of the opaque artifact bytes.

## Next boundary

v0.53 should inspect and attest the verified capsule's declared tool binaries and construct a sandbox execution plan bound to:

- the v0.52 acquisition receipt;
- the exact v0.51 capsule;
- the exact v0.28 build plan.

That future plan must still preserve:

```text
attested toolchain
!= execution authority
```

Execution should remain a separate, explicitly approved transition.
