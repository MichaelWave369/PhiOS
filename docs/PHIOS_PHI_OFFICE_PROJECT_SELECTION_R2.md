# PhiOS → PhiOffice R2: operator-selected project identity (no file transfer)

This change replaces the hardcoded `project:phios-pilot` value from R1
with explicit, ephemeral selection of a **local PhiOffice369 project
manifest** by the operator.

## Procedure
1. Export a project manifest from PhiOffice369. Do not import a backup or
   an arbitrary JSON file. No automatic cross-origin storage access exists.
2. Start the separately configured, reviewed PhiOffice browser pilot in
   PhiOS's Build Field.
3. Use **Choose local PhiOffice project manifest** to select a JSON file
   from the operator's device. No upload or fetch occurs.
4. PhiOS reads only the versioned *manifest header*: `projectId` and `title`.
   The title is for local display only. It does not cross the bridge.
5. The operator sees the selected title and ID and clicks **Approve selected
   project ref**; a subsequent PhiOffice request receives the opaque ID
   prefixed by `project:`.
6. **Revoke**, replacement selection, iframe navigation, disconnect or
   component cleanup revoke future reads. On reload, no project is restored.

Only source manifests under **256 KiB** are accepted by this small pilot.
The file must contain the required PhiOffice v0.1 header fields, but the
pilot does **not** validate every artifact or attest that the manifest is
genuine. This is manual selection, not identity verification or PhiID login.

## Invariants
- Only a bounded `project:<id>` string crosses `postMessage`, using
  the existing exact-origin, exact-frame, session-bound v1 host.
- No file data, artifact list, private path, owner, tags, document content,
  manifest JSON, tokens, identity credentials, or cloud permission crosses.
- The reference is **not** a bearer credential. It grants zero artifact or
  filesystem operations. Future data APIs must independently authorize
  every request.
- Neither manifest nor ID nor approval is persisted in PhiShell's layout
  snapshots or browser storage.
- Previously delivered references remain known to the recipient, even
  after future requests are revoked. UI denial must not be confused with
  deletion of already shared information.
- A malicious or misconfigured reviewed app origin is not attested by this
  milestone. Keep the pilot disabled in ordinary builds.

## Quality gates
`cd phishell && npm ci && npm test && npm run build`

PhiOffice369's separate two-app Chrome acceptance must be updated to
import a *test-only* v0.1 manifest, approve the selected ID, and verify
denial, revocation, disconnect and standalone operation.

The test fixture should confirm that no title, artifact path or private
manifest content enters any `host.context` reply.

## Follow-on
A user-selected manifest is a useful manual continuity bridge, but it is
not a live project registry. The next rung can expose project metadata via
a separate, consented, versioned PhiOffice/PhiID/PhiCloud adapter, without
granting cross-app file access or requiring online accounts.
