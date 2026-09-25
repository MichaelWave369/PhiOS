# PhiOS Curiosity Store v0.2

**Status:** implementation rung  
**Depends on:** Curiosity Lane v0.1  
**Core rule:** preserve the spark without promoting the claim.

## Purpose

Curiosity Lane v0.1 established a protected epistemic lane for symbols,
metaphors, questions, hypotheses, associations, patterns, dream fragments, and
creative seeds.

v0.2 gives that lane memory.

The Curiosity Store is an append-only local persistence layer for:

- immutable curiosity artifacts
- explicit parent/child lineage
- deterministic text/tag/kind lookup
- deterministic related-seed discovery
- immutable return pointers

The store remembers what the operator was exploring without asserting that the
exploration is true.

## Why this exists

A creative system can fail in two opposite ways:

1. it can treat every interesting association as truth;
2. it can discard anything that is not yet proven.

PhiOS already has strong machinery against the first failure. The Curiosity
Store protects against the second.

An unfinished symbolic thread is not the same thing as a failed thread.

## Storage model

The store uses two append-only JSONL streams:

```text
<root>/
  artifacts.jsonl
  return-pointers.jsonl
```

There are no update or delete methods in v0.2.

Exact retry of an already persisted immutable object is idempotent and does not
append a duplicate line.

On read, canonical hashes are recomputed. Tampered persisted artifacts or return
pointers fail validation rather than being silently accepted.

## Artifact lineage

`CuriosityArtifact.parent_artifact_sha256s` is used as explicit ancestry.

The store can return:

- direct children
- locally known lineage, oldest first

Missing historical parents are not fabricated. If an imported artifact names a
parent that is absent locally, the store reports only the lineage it actually
knows.

## Search

Search is deterministic and local.

It can filter by:

- free text tokens
- artifact kind
- required tags

Results are newest first.

This is retrieval, not truth ranking.

## Related-seed discovery

`CuriosityStore.related(...)` finds nearby curiosity artifacts using only
transparent local relationships:

- shared tags
- lexical overlap
- explicit parent/child lineage

Every related result includes its score and reasons.

The score is a retrieval convenience. It is not:

- confidence
- truth probability
- evidence quality
- promotion authority

Related-seed results carry zero operational, action, and execution authority.

## Return pointers

A `CuriosityReturnPointer` answers:

> Where should we pick this thread back up?

A pointer binds to one immutable curiosity artifact and contains:

- creator
- timestamp
- return prompt
- optional context
- tags

Pointers are append-only. A newer pointer does not erase an older one.

This is intentionally compatible with the No-Zero Spiral / GoldenJoy idea:
inactive work can retain an explicit place to return without pretending it is
complete.

## Authority boundary

Persistence is not promotion.

The Curiosity Store does not:

- verify facts
- admit evidence
- authorize action
- issue ActionLeases
- execute tools
- change a CuriosityPromotionRequest from `proposal_only`
- write to the Reality Ledger on its own

A hosting runtime is responsible for obtaining any permission required to write
the local files.

The persisted objects themselves remain zero-authority.

## Flow

```text
symbol / dream / strange question
              |
              v
      CuriosityArtifact
              |
              v
     append-only store
       /      |       \
      /       |        \
 search    related     lineage
              |
              v
       Return Pointer
              |
       "come back here"
              |
              v
  later Curiosity session
              |
              v
 optional explicit promotion
              |
       proposal_only
       /      |       \
 Research   Build   Ledger Review
```

## What v0.2 deliberately does not do

No embedding model is required.

No LLM decides what two symbols mean.

No background process promotes ideas.

No artifact receives a "truth score."

No symbolic object can become an action because it happens to resemble another
symbolic object.

Those belong to later, separately governed rungs.

## Next rung

**v0.3 — ΦDream / Symbol Lab UI**

The UI should expose the v0.1 and v0.2 contracts visually:

- constellation/canvas view
- capture palette for each curiosity artifact kind
- visible claim-class badges
- parent/child threads
- related seeds with transparent reasons
- return pointers
- explicit "Offer to Research / Build / Ledger Review" controls
- no Execute control

The point is not to make the dream less strange.

The point is to make sure we can find the strange thing again.
