# R17.4 · Xi ⇄ Φ Commons public source tile in PhiOS

**Status:** bundled **offline catalog description** only. The Xi Commons Gateway web app has **not** been bundled as an offline-launchable PhiOS app, nor has a real Xi partner endpoint been authenticated.

The existing PhiShell `Φ ECOSYSTEM` public-source catalog now includes a clearly separated Xi ⇄ Φ Common collaboration reference panel (`XiCommonsSourceTile.tsx`). It uses the same tested, source-only boundary as the existing public repository catalog:

- **Canonical public source:** `https://github.com/MichaelWave369/xi-vessel-bridge`
- **Gateway design and publishing instructions:** `https://github.com/MichaelWave369/xi-vessel-bridge/blob/main/docs/XI_COMMONS_GATEWAY_R173.md`
- **Offline availability:** only the text and source URLs of this PhiShell catalog tile, which ship in the compiled shell; the Xi-Phi website, scripts and partner files are *not* in the PhiOS image.
- **Known local evidence:** R15 read-only porch fixture; R16 signed two-process loopback fixture.
- **Unresolved external evidence:** R17 partner crossing **BLOCKED**; R18 real two-host pilot **NOT RUN**.
- **Launch status:** `installed=false`, `launchAuthorized=false`, `bundledWebApp=false`, `repoWriteAuthorized=false`, `liveXiConnected=false`.

This is intentionally not inserted into `app-candidates.json`, the v0.25–v0.58 App Platform lifecycle, XDG desktop entries or runtime permission broker. A public catalog entry is not proof of a deployed GitHub Pages app or permission for PhiOS to invoke an Xi-side function.

## Human-led future promotion

Only once the Commons Gateway is publicly deployed and independently verified should PhiOS consider an **additional** web destination link. Only after complete source/dependency/install review and explicit operator consent can a separate process propose a native offline PhiOS app.

Nothing from Hunter's side is required to view this source tile, and an offline PhiOS boot can display the catalog text without making network requests. Following the GitHub source link while offline naturally requires internet connectivity.

The `public-ecosystem-catalog.yml` GitHub Action now checks this tile's scope, refuses accidental installation/authority claims, and requires the tile's honest labels in the bundled offline shell JavaScript.

**Capability ≠ Authority · Both houses keep their keys.**
