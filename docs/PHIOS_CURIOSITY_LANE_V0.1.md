# PhiOS Curiosity Lane v0.1

**Status:** proposed runtime contract  
**Lane:** `curiosity`  
**Core rule:** **exploration may create meaning without creating authority.**

## Purpose

PhiOS needs a first-class place for symbols, metaphors, dreams, strange
associations, visual motifs, unanswered questions, speculative connections, and
creative seeds.

The Curiosity Lane exists so those things can be preserved and explored
without being flattened into either "verified fact" or "discarded nonsense."

It is intentionally upstream of judgment.

## Doctrine

### 1. Curiosity is not a truth grant

A CuriosityArtifact may be useful, beautiful, suggestive, or personally
meaningful. None of those properties make it verified.

The lane records what was explored. It does not certify what is real.

### 2. Symbols may remain symbols

Symbolic meaning does not need to impersonate empirical fact in order to
matter.

The canonical v0.1 artifact classes are:

- `symbol`
- `metaphor`
- `question`
- `hypothesis`
- `association`
- `pattern`
- `dream_fragment`
- `creative_seed`

Each kind carries an explicit claim class:

| Artifact kind | Claim class |
| --- | --- |
| symbol, metaphor, dream_fragment, creative_seed | `non_claim` |
| question | `open_question` |
| hypothesis | `hypothesis` |
| association, pattern | `unverified_association` |

This prevents a symbolic artifact from silently becoming a factual assertion.

### 3. Curiosity carries zero authority

Every CuriosityArtifact and CuriosityPromotionRequest is required to state:

- `effect_performed = false`
- `operational_authority = false`
- `action_authority = false`
- `execution_authority = false`

The Curiosity Lane cannot execute tools, mutate governed state, grant
permissions, create an ActionLease, or certify evidence.

**CAPABILITY != AUTHORITY still applies here. Curiosity is simply allowed more
freedom before the authority boundary.**

### 4. No silent promotion

Curiosity artifacts cannot promote themselves.

Moving an idea toward Research, Build, or Ledger Review requires an explicit
`CuriosityPromotionRequest`.

The request status is always:

`proposal_only`

The destination lane must apply its own admission, evidence, testing,
governance, and authority rules.

There is intentionally no direct Curiosity -> Execute target.

### 5. Provenance survives the dream

Artifacts carry:

- creator identity
- timestamp
- canonical content hash
- tags
- optional EvidenceRef hashes
- optional parent curiosity-artifact hashes

A later idea can therefore say where it came from without pretending its
ancestry proves it.

### 6. Ambiguity is permitted

The Curiosity Lane does not require one interpretation to defeat all others.

Competing symbols, hypotheses, and associations may coexist until a downstream
lane has a reason and a method to discriminate among them.

### 7. The Ledger records provenance, not meaning

A curiosity artifact may eventually be referenced by the Reality Ledger.

That ledger entry proves that the artifact existed with a particular identity
and provenance. It does **not** prove that the artifact's symbolic
interpretation is true.

## Boundary model

```text
DREAM / SYMBOL / CURIOSITY
          |
          |  CuriosityArtifact
          v
   protected exploration
          |
          |  explicit promotion request
          v
  +-------+---------+----------------+
  |                 |                |
RESEARCH           BUILD       LEDGER REVIEW
  |                 |                |
evidence          prototype        provenance
testing           experiment       historical truth
  |                 |                |
  +------- governed boundaries -----+
                    |
                    v
              possible action

Curiosity itself has no action path.
```

## Relationship to existing PhiOS architecture

The Curiosity Lane complements rather than weakens the current governance
spine.

- **Dream / Curiosity** explores possibility.
- **Research** tests claims.
- **Build** constructs experiments and artifacts.
- **Reality** observes external state.
- **PhiKernel / governance** evaluates authority.
- **Execution** performs authorized effects.
- **Ledger** preserves what actually happened.

This separation lets PhiOS recover symbolic play without asking the Reality or
authority layers to pretend that speculation is evidence.

## v0.1 implementation

`phios.curiosity` provides two immutable contracts:

### CuriosityArtifact

A canonical, hashed exploration object with zero authority.

### CuriosityPromotionRequest

A canonical, hashed proposal to offer an artifact to one of:

- `research`
- `build`
- `ledger_review`

The request itself performs no transition.

## Planned next rungs

### v0.2 — Curiosity Store

Local append-only storage and lookup for curiosity artifacts and explicit
lineage between them.

### v0.3 — PhiShell / PhiVessel Symbol Lab

A visual workspace for capturing symbols, dream fragments, associations,
questions, sketches, and creative seeds without demanding premature
resolution.

### v0.4 — Dreamer synthesis

Optional local-model support for generating associations and alternate
interpretations. Generated material remains explicitly model-originated and
zero-authority.

### v0.5 — governed promotion adapters

Research, Build, and Ledger Review adapters that accept promotion proposals,
apply their own contracts, and emit acceptance/rejection receipts.

## Design sentence

> **Permission to explore without permission to declare.**

That is the lane.
