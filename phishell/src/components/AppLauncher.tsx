import { SHELL_APPS, type ShellApp } from "../shell/appLauncher";

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
      <p className="muted">This list describes the shipped image, not a scan of apps you added separately.</p>
    </section>
  );
}
