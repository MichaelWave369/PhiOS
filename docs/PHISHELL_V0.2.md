# PhiShell v0.2 — Desktop and Authority Contracts

Status: **candidate implementation**  
Target substrate: **Linux / Wayland path**  
Primary invariant: **CAPABILITY != AUTHORITY**

PhiShell v0.2 is the first increment where the visual shell behaves like a desktop state machine rather than a static shell mockup.

It still does **not** possess privileged Linux execution authority.

## Scope

v0.2 introduces:

- typed shell state and shell events;
- persistent workspace windows;
- focus and z-order;
- move, minimize, restore, maximize, and close behavior;
- universal Search / command overlay;
- keyboard access through Ctrl/⌘ + K;
- explicit authority-request UI;
- deterministic authority receipts;
- a Linux service adapter interface;
- a zero-privilege mock Linux adapter;
- automated reducer and authority-boundary tests.

## Desktop event model

UI transitions flow through typed events:

```text
operator interaction
        ↓
ShellEvent
        ↓
deterministic reducer
        ↓
ShellState
        ↓
visual projection
```

Representative events include:

```text
FOCUS_WINDOW
MOVE_WINDOW
MINIMIZE_WINDOW
RESTORE_WINDOW
TOGGLE_MAXIMIZE_WINDOW
CLOSE_WINDOW
OPEN_COMMAND
REQUEST_AUTHORITY
RESOLVE_AUTHORITY
```

Window state itself does not carry operating-system authority.

## Command overlay

The universal command field can:

- navigate PhiShell destinations;
- restore or open known desktop windows;
- discover modeled capabilities;
- create authority requests.

It cannot directly execute Linux commands.

The contract remains:

```text
discover capability
    !=
request capability
    !=
approve intent
    !=
possess execution authority
    !=
perform effect
```

## Authority request model

PhiShell displays authority requests explicitly.

A request records:

- request identity;
- capability;
- requested scope;
- reason;
- requester;
- decision state;
- execution-authority state.

The prototype supports:

```text
pending
approved_intent
denied
```

Even an `approved_intent` preserves:

```text
executionAuthority = false
```

Approval in v0.2 means only that the operator approved the modeled intent for the prototype. It does not authorize or perform a Linux effect.

## Linux service adapter

v0.2 defines a replaceable adapter interface for future Linux integration.

Current adapter:

```text
mock-zero-privilege
```

Its hard properties are:

```text
operationalAuthority = false
actionAuthority      = false
executionAuthority   = false
```

Any service request returns a blocked receipt:

```text
status             = blocked
effectPerformed    = false
executionAuthority = false
```

The adapter therefore proves the UI path without introducing a privileged execution path.

## Power control example

The Phi Start menu now demonstrates the authority boundary directly.

Selecting **Power** performs this sequence:

```text
Power selected
    ↓
authority request created
    ↓
operator may deny or approve intent
    ↓
zero-privilege adapter receives intent
    ↓
blocked receipt
    ↓
no operating-system effect
```

There is deliberately no `exec`, `sudo`, systemd mutation, D-Bus mutation, or privileged broker in this increment.

## Tests

The v0.2 test lane verifies that:

1. focusing a window updates z-order deterministically;
2. minimizing and restoring preserves the window object;
3. approving an intent does not create execution authority;
4. the Linux adapter cannot convert an intent into an operating-system effect.

CI runs:

```bash
npm test
npm run build
```

## Boundary

PhiShell remains a browser-rendered reference shell.

This increment does not choose or implement the final Wayland compositor host.

The intended future stack remains:

```text
Linux kernel
    ↓
Wayland compositor/session
    ↓
PhiShell
    ↓
PhiOS governed userland
    ↓
separately reviewed privileged broker
```

No privileged broker should be added merely to make prototype controls appear functional.

## Next increment

A safe v0.3 candidate can begin binding **read-only** Linux substrate observations to the adapter interface, for example:

- session identity;
- host identity;
- CPU/memory/storage telemetry;
- network interface observation;
- service status observation;
- power capability discovery without mutation.

Mutating Linux effects should remain out of scope until the broker contract, authority grants, effect receipts, and failure semantics receive separate review.
