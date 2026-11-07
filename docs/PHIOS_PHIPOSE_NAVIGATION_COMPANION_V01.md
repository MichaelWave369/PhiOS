# PhiOS ΦPose Navigation Companion v0.1

## Scope

An **optional**, short-lived, same-origin browser companion for OverStrings Rung 7. Recognized, deliberately armed gesture phrases can now request **real PhiShell UI navigation** in a separate PhiOS window, subject to the user's explicit permission on both sides. Scope is intentionally restricted to ordinary front-end reducer actions.

**Not** a privilege, authentication factor, remote management API, filesystem command, app execution mechanism, or replacement for PhiOS Spine / permission gates.

## Browser use

1. Open the OverStrings GitHub Pages playground over HTTPS, compose a phrase and choose a safe PhiOS navigation action.
2. Click **Open PhiOS companion** inside OverStrings. This opens a PhiOS window on the **same origin**.
3. In PhiOS, explicitly click **Enable ΦPose companion**. PhiOS binds to that exact opener Window, checks that its path is within `/OverStrings/`, and generates a random session ID with a five-minute expiry.
4. The ready signal is returned to the exact opener origin, never `*`.
5. Return to OverStrings. Arm exactly one gesture phrase, and perform it in WebXR. Alternatively, explicitly enable *synthetic sandbox mode* in **both** windows for desktop demonstrations.
6. PhiOS validates source object, origin, host-generated session, freshness, replay, cooldown, schema, action namespace and source restrictions.
7. Accepted actions dispatch **only typed PhiShell reducer events**: Home, Research, Build, Ledger, or Open Command Palette.
8. The app returns a receipt stating `accepted_for_ui_dispatch`, **not** `effect_completed`.

The same-origin popup approach requires the browser to keep both pages responsive. **Quest 3 multiwindow/background WebXR handling has not been verified.** If the browser suspends the gesture page when the host gains focus, native/in-origin host integration or a supported XR window model will be needed. This is a browser integration experiment, not a production XR guarantee.

## Explicit host controls

- PhiOS starts **disabled**. No incoming message can implicitly enable the bridge.
- Only the operator click enables a session, for at most **five minutes**.
- A visible **Disable ΦPose** control revokes permission immediately.
- Synthetic mode is off by default, and must be opted into separately on each page.
- No persistent permissions, tokens, gesture recordings or input-source identity data are stored.
- Host accepts only exact same-origin opener messages. It does not subscribe to arbitrary broadcast messages.
- Rejects out-of-window messages, unknown actions, replays and short-interval repeats.
- `phios.view.*` and `phios.command.open` are *UI-only*; they never invoke an app launcher or Linux/runtime action.
- Browser messages, origin and sender binding **do not attest the code** running in another same-origin page. A compromised same-origin app may attack this surface. Hence only harmless visual navigation is allowed.

## Relationship to existing governance

The host maps safe names to `ShellEvent`:

```text
phios.view.home       -> SET_VIEW: home
phios.view.research   -> SET_VIEW: research
phios.view.build      -> SET_VIEW: build
phios.view.ledger     -> SET_VIEW: ledger
phios.command.open    -> OPEN_COMMAND
```

Anything with external side effects must be proposed via the existing governed capabilities and ActionLease process. **We must not map gesture events directly to Spine execution.** Success here means only that a typed UI event was accepted for React dispatch.

## Contracts and testing

- Receiver: `phishell/src/shell/phiPoseNavigationHost.ts`
- Host UI: `phishell/src/components/PhiPoseCompanion.tsx`
- Tests: `phishell/src/shell/phiPoseNavigationHost.test.ts`
- Producer: OverStrings `web/phipose-phi-transport.mjs`, with `overstrings.phipose.intent.v0.1`
- Local verification: `cd phishell && npm test && npm run build`

There is no automatic privilege escalation, app install, shell command, arbitrary destination URL, or persistence of consent.
