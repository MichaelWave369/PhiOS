import { SHELL_APPS, type ShellApp } from "../shell/appLauncher";
import { EcosystemCatalog } from "./EcosystemCatalog";
import { UniversalAppShelf } from "./UniversalAppShelf";
import { PixelForgeLaunchCard } from "./PixelForgeLaunchCard";

export function AppTiles({ openApp, pinned = false }: {
  openApp: (id: string) => void;
  pinned?: boolean;
}) {
  const apps = pinned
    ? SHELL_APPS.filter((app) => ["browsallax", "phivessel", "brainc", "ledger", "system", "apps"].includes(app.id))
    : SHELL_APPS;
  return (
    <div className={pinned ? "start-apps" : "app-grid"}>
      {apps.map((app) => (
        <button className={pinned ? undefined : "app-tile"} key={app.id}
          onClick={() => openApp(app.id)} aria-label={`${app.name} · ${app.status}`}>
          <span aria-hidden="true">{app.icon}</span>
          <small>{app.name}</small>
          <em>{app.status}</em>
        </button>
      ))}
    </div>
  );
}

export function AppDetails({ app }: { app: ShellApp }) {
  return (
    <section className="app-details">
      <div className="panel-title">{app.name} · {app.status}</div>
      <p>{app.description}</p>
      <p className="muted">This describes the shipped PhiOS image. Apps added separately are not detected here.</p>
    </section>
  );
}

export function AppLibrary({ openApp }: { openApp: (id: string) => void }) {
  return (
    <section className="app-library">
      <div className="panel-title">PHIOS TOOLS AND INTEGRATIONS</div>
      <p>Select a tool to open it, or an integration to see what still needs setup.</p>
      <AppTiles openApp={openApp} />
      <div className="panel app-desktop-help">
        <div className="panel-title">INCLUDED LINUX DESKTOP APPS</div>
        <dl>
          <div><dt>Chromium browser</dt><dd>Super+Space, then choose Chromium.</dd></div>
          <div><dt>Foot terminal</dt><dd>Super+Alt+Enter.</dd></div>
          <div><dt>PhiOS terminal tools</dt><dd>Super+Enter. Enter help to see commands.</dd></div>
          <div><dt>Network settings</dt><dd>Super+N.</dd></div>
          <div><dt>Governed installed apps</dt><dd>Use the desktop menu for approved launchers. In Foot, phi-app catalog-desktop-apps inspects the existing catalog.</dd></div>
        </dl>
      </div>
      <section className="panel app-desktop-help" aria-labelledby="r5-lifecycle-title">
        <div className="panel-title" id="r5-lifecycle-title">Φ R5 APP INSTALLATION & LIFECYCLE</div>
        <p>Only the device's package database and PhiOS governed App Platform can report actual installation. A public source bookmark is never installed-app evidence.</p>
        <dl>
          <div><dt>What is installed?</dt><dd>Open System Inspector for a read-only observation of this Linux host's package database. This does not tie arbitrary packages to GitHub source IDs.</dd></div>
          <div><dt>Verify an artifact</dt><dd>In a development checkout, run <code>python interop/artifact_preflight_v1.py --manifest /path/manifest.json --artifact /path/release.zip</code>. Matching SHA-256 verifies selected bytes, not publisher identity, safety, or installation.</dd></div>
          <div><dt>Install or update</dt><dd>Use the separately governed <code>phi-app</code> intake, build, review, and approval gates. No R5 GUI install authority exists yet.</dd></div>
          <div><dt>Remove or rollback</dt><dd>Use the actual installed-app manager and its signed/approved recovery plan. An arbitrary catalog entry has no uninstall or rollback operation.</dd></div>
          <div><dt>Verify a signed publisher release (R5B)</dt><dd>From a development checkout, run <code>phi-app review-signed-release --help</code> and supply an existing v0.50 install proposal, exact detached Ed25519 signature, and externally pinned public key fingerprint. A verified signature is evidence of control of that key, <strong>not</strong> proof of trusted publisher identity or approval to install.</dd></div>
          <div><dt>Recovery qualification</dt><dd>Use the existing separate PhiOS desktop update and rollback plan/review/test gates on disposable hardware. R5B holds installation until an independently checked recovery rehearsal and device compatibility review exist.</dd></div>
        </dl>
        <button type="button" onClick={() => openApp("system")}>Inspect actual Linux package state</button>
        <p className="muted">R5 starts with local artifact verification and platform-owned app management. No silent package downloads, shell commands, or new privilege bridge.</p>
      </section>
      <PixelForgeLaunchCard openApp={openApp} />
      <EcosystemCatalog />
      <UniversalAppShelf />
      <p className="muted">This list describes the shipped image, not a scan of apps you added separately.</p>
    </section>
  );
}
