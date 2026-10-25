import "./InfiniteHomeDock.css";

/**
 * Operator-initiated navigation only. These destinations are NOT health probes,
 * installed-app registry entries, provider clients, or grants.
 */
export const HOME_DOORWAYS = [
  {
    id: "porch",
    title: "Infinite Porch",
    description: "Local AI home and trusted-device control UI. Requires a separately running Porch node.",
    href: "http://127.0.0.1:7331/",
    action: "OPEN LOCAL PORCH",
    status: "NOT OBSERVED · LOGIN REQUIRED",
  },
  {
    id: "commons",
    title: "Infinite Commons",
    description: "Shared portal/world experience. Opens the public website only when chosen.",
    href: "https://michaelwave369.github.io/Infinite-Commons/",
    action: "VISIT COMMONS PORTAL",
    status: "EXTERNAL WEBSITE · NOT INSTALLED",
  },
] as const;

export function InfiniteHomeDock() {
  return (
    <section className="panel infinite-home-dock" aria-label="Infinite Porch and Commons doorways">
      <div className="panel-title">Φ HOME · YOUR AI'S PLACE IN PHIOS</div>
      <p className="infinite-home-intro">
        Every PhiOS workspace should have a home for local intelligence and a doorway into
        the Commons. This first step supplies <strong>explicit operator-opened links</strong>.
        It does not start Porch, load a model, join a peer, or install a Commons world.
      </p>
      <div className="infinite-home-grid">
        {HOME_DOORWAYS.map((door) => (
          <article className="infinite-home-door" key={door.id}>
            <div className="infinite-home-door-header">
              <strong>{door.title}</strong>
              <small>{door.status}</small>
            </div>
            <p>{door.description}</p>
            <a href={door.href} target="_blank" rel="noopener noreferrer">
              {door.action} ↗
            </a>
          </article>
        ))}
      </div>
      <p className="infinite-home-caution">
        <strong>Connection boundary:</strong> No endpoint probe or background network request
        is made by this dock. The local Porch page uses its own operator token.
        Opening a link grants PhiOS no account, model, file, network, or execution rights.
        Offline availability, device trust, and deployment health remain unverified here.
      </p>
    </section>
  );
}
