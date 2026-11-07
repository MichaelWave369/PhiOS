# PhiOS R1: Operator-controlled PhiOffice browser pilot

## Purpose
The existing PhiShell window manager and the merged `workspaceBridge.ts` protocol
are now connected through a **disabled-by-default** React pilot panel inside the
Build Field. No default external URL, production install, or automatic
cross-app data sharing has been introduced.

## Configuration
A PhiShell *developer/operator build* needs two explicit Vite settings:

```sh
# Example only: run the reviewed PhiOffice Vite dev server separately on 5174.
VITE_PHIOS_OFFICE_BRIDGE_URL=http://localhost:5174/ \
VITE_PHIOS_OFFICE_BRIDGE_APPROVED_ORIGIN=http://localhost:5174 \
npm run dev -- --port 5173
```

PhiOffice must separately set `VITE_PHIOS_PARENT_ORIGIN=http://localhost:5173`
when building its client-side pilot UI. The embedded site must be a reviewed,
independently served application at a **different browser origin**. A
GitHub Pages source link is not reviewed configuration.

The gate rejects wrong origins, same-origin frames, insecure non-loopback HTTP,
URL credentials, query strings, fragments, and an origin mismatch. Users
click **Start opt-in pilot**. Nothing loads before this. The iframe has
restricted capabilities and is bound to a fresh session on load.

## Runtime
- The host runs the existing `createWorkspaceBridgeHost` with the actual
  iframe `WindowProxy`, an exact approved child origin and a fresh session ID.
- The child can `app.hello`; the host responds without project identity.
- The operator may click **Approve synthetic ref**. Only the deliberately
  non-sensitive `project:phios-pilot` string can be sent on request.
- **Revoke** denies future requests; **Disconnect** drops the iframe and
  session. Neither can erase a reference already delivered.
- No PhiID credentials, PhiCloud data, local files, host commands, agent tasks,
  service privileges or real project IDs cross the bridge.
- The pilot is not persisted in workspace layout snapshots; reloading resets
  consent. Network access to the explicitly selected origin occurs only when
  the operator starts the pilot.

The iframe's scripts and origin are enabled so the actual cross-origin app
can run; this is not a hostile-code sandbox. **Never embed untrusted URLs**.
The parent and iframe must not share a browser origin. Treat this as a
reviewed development pilot, not a production isolation guarantee.

## Tests
`cd phishell && npm test && npm run build` checks endpoint validation,
existing protocol tests, and normal shell build. PhiOffice separately tests
the real cross-origin protocol in Chrome with
`npm run test:browser:bridge`. A full browser test of the rendered panel
with both app servers is still a follow-on gate.
