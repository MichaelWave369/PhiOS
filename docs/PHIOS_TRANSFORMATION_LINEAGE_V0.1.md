# PhiOS Transformation Lineage v0.1

## Status

Research-hardening candidate.

Primary schema:

```text
phios.transformation_lineage_receipt.v0.1
```

Primary rule:

```text
DERIVED FROM X
!=
IDENTICAL TO X
```

Transformation lineage is evidence about derivation. It grants no operational, action,
or execution authority.

## Purpose

PhiOS already preserved native evidence and recorded several transformation-specific
details in SOMA. v0.1 turns that pattern into one reusable contract so downstream
systems do not have to infer whether a crop, normalization, OCR result, import, or other
derived artifact is equivalent to its source.

The contract answers four separate questions:

1. exactly which source artifacts were used;
2. exactly which output artifact was produced;
3. what representational exactness PhiOS is willing to claim;
4. what limitations or taints must survive downstream use.

It does not answer whether the derived content is true.

## ExactnessClass

The bounded vocabulary is:

```text
BYTE_EXACT
REVERSIBLE
NORMALIZED
LOSSY_DERIVED
INTERPRETIVE
UNKNOWN
```

The ordering is conservative. When transformations are chained, effective exactness is
the weakest class present in the lineage.

### BYTE_EXACT

The output bytes are identical to exactly one source according to SHA-256.

Requirements:

- exactly one source;
- source SHA-256 equals output SHA-256;
- no semantic inference;
- no possible information loss.

### REVERSIBLE

The transform contract asserts that the source representation can be recovered without
information loss.

v0.1 defines the class but does not promote a current PhiOS adapter into this class
merely because a transform appears mechanically invertible.

### NORMALIZED

The output changes representation in a bounded non-semantic normalization.

Current example:

- UTF-8 BOM removal / newline normalization.

The native source remains preserved. A normalized artifact is not byte-exact to a
changed source.

### LOSSY_DERIVED

The output is derived and the transform admits possible information loss or lost
context.

Current examples include:

- tight screen crop;
- nearest-neighbor enlargement after recovery;
- deterministic sharpening/enhancement;
- extraction of one legacy deliberation from a larger source file.

### INTERPRETIVE

The output contains machine interpretation rather than merely representational
transformation.

Current example:

- OCR image → text.

An interpretive artifact is never treated as source-equivalent merely because the OCR
engine reports high confidence.

### UNKNOWN

Exactness cannot be established.

Unknown is representable for evidence but should not be silently upgraded by a later
transform.

## Exactness monotonicity

A downstream transform cannot increase inherited exactness.

For example:

```text
source image
   ↓ tight crop
LOSSY_DERIVED
   ↓ byte-for-byte copy of cropped output
requested: BYTE_EXACT
effective: LOSSY_DERIVED
```

The copy can be byte-exact to the cropped artifact while still being lossy relative to
the original source lineage.

This avoids exactness laundering through intermediate artifacts.

## TransformationLineageReceipt

Each receipt binds:

```text
schema_version
receipt_id

transform_id
transform_version

source_refs[]
source_sha256s[]

output_ref
output_sha256

parameters_sha256
parent_receipt_sha256s[]

requested_exactness
exactness_class

source_taints[]
added_taints[]
effective_taints[]

information_loss_possible
semantic_inference
limitations[]

operational_authority = false
action_authority      = false
execution_authority   = false

receipt_sha256
```

Receipt identity is deterministic for a fixed transformation contract and lineage.

## Taint propagation

A taint label means a limitation or provenance condition that must survive downstream
use. It is not a malware label and not an automatic confidence score.

v0.1 examples include:

```text
normalized_representation
cropped_context
resampled_pixels
enhanced_pixels
machine_interpretation
canonicalized_representation
extracted_subset
```

Effective taints are the union of inherited and newly-added taints.

Downstream lineage validation rejects a chain where a parent taint disappears.

## SOMA integration

### Text perception

Unchanged admitted text receives a `BYTE_EXACT` lineage receipt.

If configured normalization changes the text, the observation is `NORMALIZED` with:

```text
normalized_representation
```

The native source bytes remain content-addressed and preserved.

### Screen recovery

A tight crop is `LOSSY_DERIVED` because pixels outside the selected region are absent
from the output.

Nearest-neighbor enlargement is also conservatively `LOSSY_DERIVED` in v0.1. PhiOS
does not use enlargement to claim recovered native detail.

The crop and enlargement receipts form an explicit parent chain.

### Screen enhancement

Deterministic sharpening is `LOSSY_DERIVED`.

The lineage explicitly records that enhancement can amplify artifacts and does not
recover information that was never present in the input.

Even a quarantined derived enhancement can retain a lineage receipt when the output
bytes were actually produced and preserved.

### OCR

OCR text is `INTERPRETIVE`.

The receipt records the provider/engine identity and OCR parameters in the transformation
parameter digest. The output is marked:

```text
machine_interpretation
```

Engine confidence remains metadata, not a probability of truth.

## Receipt integration

Transformation receipts are inline derivation artifacts.

Existing persisted receipts bind their hashes and bounded summary metadata:

- `PerceptionReceipt`
- `OcrReceipt`
- `MemoryOperationReceipt`
- `ReadAdmissibilityReceipt`

This avoids introducing another Mandala authority plane or another persisted row merely
because a representation was transformed.

## Governed memory integration

Derived canonical memory now requires explicit transformation metadata.

A derived `MemoryRecord` must carry:

```text
derived_from
exactness_class
transformation_lineage_sha256s
taint_labels
```

At write time, `GovernedMemoryService` validates the supplied full transformation
receipt chain.

The write fails closed when:

- no lineage receipts are supplied;
- any receipt is malformed or hash-invalid;
- record lineage hashes differ from supplied receipts;
- a parent link is broken;
- effective exactness was upgraded;
- an inherited taint disappeared;
- the final lineage output digest differs from canonical memory content;
- exactness or taints differ from the record;
- declared source lineage is not represented.

The canonical memory record stores only the bounded lineage references and exactness
metadata. The durable `MemoryOperationReceipt` binds the full supplied lineage used for
the write.

## Legacy import integration

Legacy agent-memory import is a concrete example of why the distinction matters.

One deliberation extracted from a larger JSON file is not the original JSON file.

The importer therefore emits:

```text
ExactnessClass = LOSSY_DERIVED

taints:
  canonicalized_representation
  extracted_subset
```

while preserving the complete source-file SHA-256.

## Consumption boundary

When derived memory is later read, `ReadAdmissibilityReceipt` exposes:

- derived/source epistemic kind;
- exactness class;
- transformation receipt hashes;
- taint labels.

It still fixes:

```text
operational_authority = false
action_authority      = false
execution_authority   = false
```

Exact provenance does not become authority.

## Operator boundary

The generic `phi-memory put` path cannot create an arbitrary derived record by merely
setting `--epistemic-kind derived`.

Derived writes need a subsystem/importer capable of producing transformation receipts
that pass the canonical service validator.

Source writes remain available through the normal governed memory path.

## Ledger analytics

Read-only Ledger projection includes bounded transformation metadata from existing
receipt types:

```text
transformation_lineage_sha256s
exactness_class / exactness_classes
taint_labels
```

The full derived content and authority internals are not added merely to support
analytics.

## Security properties

v0.1 is designed to prevent:

- exactness laundering through downstream copies;
- taint disappearance;
- source substitution;
- unreceipted derived memory;
- output-hash substitution;
- treating OCR as byte-equivalent source text;
- treating an extracted subset as the complete source;
- transformation metadata from minting authority.

## Non-goals

v0.1 does not prove:

- factual truth;
- semantic equivalence;
- summary completeness;
- OCR correctness;
- recovery of missing image detail;
- absence of model hallucination;
- independence of multiple derivation paths;
- contamination remediation.

Those properties require different evidence.

The next P1 candidate is evidence-path independence and disagreement decomposition.
