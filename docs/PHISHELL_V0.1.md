# PhiShell v0.1 — Linux Visual Shell Frame

Status: **candidate implementation**  
Target substrate: **Linux / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell is the operator-facing visual environment for PhiOS.

It is distinct from the public `site/` application:

- the public site explains PhiOS;
- PhiShell is the visual shell the operator will eventually enter after login.

## v0.1 scope

The first increment deliberately builds the visual shell frame before binding privileged
Linux operations.

Implemented surfaces:

- persistent system top bar;
- left navigation rail;
- Home field;
- PhiVessel right dock;
- bottom command strip;
- Start menu;
- Home, Research, Build, Memory, Ledger, Governance, and Settings destinations;
- visual system-status, project, app, notification, and resource panels;
- explicit advisory-only PhiVessel state.

This is a browser-rendered shell prototype used to freeze interaction structure and
visual contracts before compositor/runtime integration.

## Authority boundary

PhiShell v0.1 does **not** grant Linux authority.

Buttons and visual controls are not treated as execution grants.

The current UI therefore implies:

```text
operational_authority = false
action_authority      = false
execution_authority   = false
```

Future Linux operations must pass through explicit PhiOS authority/effect contracts and
a separately reviewed privileged broker. A visually available action is never sufficient
evidence that the action is authorized.

## Visual system

v0.1 establishes the canonical shell vocabulary:

- near-black field background;
- brass/gold for identity and authority-significant surfaces;
- cyan for intelligence/interaction;
- teal/green for active or healthy system state;
- persistent rail + intelligence dock + command strip composition;
- restrained instrument-panel depth rather than generic SaaS cards.

## Linux direction

The intended path is:

```text
Linux kernel
    ↓
Wayland compositor/session
    ↓
PhiShell
    ↓
PhiOS userland + governed services
    ↓
explicit privileged broker for consequential OS operations
```

The browser-rendered v0.1 shell is not the final compositor implementation. It is the
interaction and visual reference implementation that allows the shell to be built and
tested before choosing the final native host technology.

## Local development

```bash
cd phishell
npm install
npm run dev
```

Production validation:

```bash
npm run build
```

## Next increment

PhiShell v0.2 should introduce the first real desktop-behavior contracts:

1. workspace/window model;
2. universal Search / command overlay;
3. authority-request component;
4. mock Linux system-service adapter interface with zero privileged implementation;
5. typed shell event model;
6. deterministic test fixtures for advisory vs authorized visual states.

No privileged Linux mutation should be added until that boundary is separately reviewed.
