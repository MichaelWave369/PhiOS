# Φ PhiOS Universal Application Integration · Workspace Bridge v1

## Scope
This milestone establishes a small, **read-only, consent-gated** protocol for
sharing an *opaque project reference* from PhiShell with a separately reviewed
application. It extends the existing PhiShell app catalog and window manager.
It does **not** enable iframe embedding, installation, execution, artifact
transfer, identity delegation or automatic permissions.

The browser-side contract is in `phishell/src/shell/workspaceBridge.ts`,
with hostile input tests next to it. The application side must be independently
implemented and reviewed before an integration is promoted.

## Trust boundaries
- Host registration binds one explicit app ID to an exact HTTPS origin (or
  local-loopback development origin), one frame source object, and a freshly
  generated session ID.
- The host sends a `host.bootstrap` packet using the exact origin, never `*`.
- Only messages from the registered source and origin with matching protocol,
  app ID and session ID are considered. Unknown fields and out-of-bounds
  packets are discarded.
- The host answers `app.hello` with `host.ready`; no project identity leaks
  in the readiness response.
- `app.context.request` receives `host.denied` until an operator explicitly
  approves a bounded `project:...` reference. Approval is revocable.
- Every host response is marked `execution_authority: false`. There are no
  privileged effects, shell commands, filesystem paths, document contents,
  storage handles, access tokens or PhiID/PhiCloud tokens.

## API sketch (not automatic activation)
```ts
const frameSource = iframe.contentWindow; // after a separately reviewed embed
const host = createWorkspaceBridgeHost({
  appId: "phioffice",
  appOrigin: "https://example-approved-origin.test",
  frameSource,
  sessionId: generateBridgeSessionId(),
});
frameSource.postMessage(host.bootstrap().message, host.bootstrap().targetOrigin);
window.addEventListener("message", (event) => {
  const reply = host.handle(event);
  if (reply) frameSource.postMessage(reply.message, reply.targetOrigin);
});
// Only following an explicit operator action, with an actual known project:
host.approveProject("project:example");
host.revokeProject(); // on leaving project, app closure, logout, or user request
```

The example URL and project ref are placeholders, not an approved PhiOffice
deployment. The embedding host must not trust a public source bookmark,
unverified homepage URL or a repository name as an installation certificate.

## Security limitation
This first protocol does not attest the code running inside an origin.
A compromised registered app at its trusted origin could request an approved
project ref. Therefore this protocol carries **only an opaque identifier**, no
project data, and has no authority over the host. Exact origin checks alone are
not a complete application trust model.

## Next gate
Pair the host contract with a tested, opt-in PhiOffice369 client and a
disposable browser fixture. Verify exact origin/source binding, pending-request
correlation, denial behavior and revocation before using real project IDs.
The browser UI, installation authority and user-data synchronization remain
separate milestones.

## Checks
```sh
cd phishell
npm ci
npm test
npm run build
```
