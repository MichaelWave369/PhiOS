# Φ PhiOS Workspace Continuity v1

## Delivered surface

PhiShell now has an explicit, local-first **layout-only** snapshot format
(`phios.workspace-layout`, version 1). Existing typed desktop windows are
restored after browser restart, and users can export/import a portable JSON file.
Windows can be moved, resized, minimized, maximized and closed.

This reuses the existing PhiShell window manager and app catalog, rather than
creating a competing desktop or an independent application registry.

The wire format carries only `format`, `version`, `view` and an array of
bounded, known window identities and geometry. Import reconstructs titles,
subtitles and kinds from the **installed PhiShell shell catalog**, never from
untrusted JSON. It rejects unknown fields, unknown windows, duplicate IDs,
invalid geometry, excessive window counts and files over 16 KiB. Browser
localStorage is used only for the same-origin automatic layout snapshot. The
user can export the portable layout without a PhiID account or PhiCloud.

**Not persisted or shared:** document contents, project files, app memory,
access tokens, credentials, identity, agent transcripts, system observations,
authority requests, approved intents, grants, execution handles, or installation
claims. Import never fetches, installs, launches or executes third-party apps.

## Honest integration boundary

The source-only App Shelf and PhiOS App Platform governed installation,
desktop launch, signed release, lifecycle and rollback paths remain separate.
`app:phioffice` in a saved layout restores the **existing integration status**
window, **not** an embedded or installed PhiOffice runtime. An app being listed
in PhiOS is not evidence that it is installed or launchable.

## Next incremental integration gates

1. Publish a separately versioned app-to-workspace event contract, including
   strict message origin binding, workspace-scoped opaque references and
   capability declarations. Nothing automatically gains execution authority.
2. Add an explicit operator-approved embedding/launch registration for one
   tested app, beginning with PhiOffice369. Do not treat GitHub Pages or
   homepage metadata as a trusted execution endpoint.
3. Bind per-project artifact references through explicit, least-privilege
   PhiID/PhiCloud adapters. Preserve usable offline/no-account workflows.
4. Test cross-app context transfer in a disposable environment before allowing
   agent operations, host filesystem access, native execution or network effects.

## Local verification

```sh
cd phishell
npm ci
npm test
npm run build
```

Manual smoke: open two shell windows, resize/move one, reload the same origin,
check restoration; export JSON, reset, import, and confirm only visual desktop
state returns. Malformed layouts must be rejected without invoking effects.
