/** R17.4 public-only collaboration tile. Separate from AppManifest/install/launch flows. */
export const XI_PHI_COMMONS_SOURCE = Object.freeze({
  id: "phios.catalog.xi-phi-commons-source",
  label: "Ξ ⇄ Φ · Sovereign Commons Gateway",
  sourceUrl: "https://github.com/MichaelWave369/xi-vessel-bridge",
  docsUrl: "https://github.com/MichaelWave369/xi-vessel-bridge/blob/main/docs/XI_COMMONS_GATEWAY_R173.md",
  status: "SOURCE_ONLY",
  localSnapshotAvailableOffline: true,
  externalSiteVerified: false,
  installed: false,
  bundledWebApp: false,
  launchAuthorized: false,
  repoWriteAuthorized: false,
  liveXiConnected: false,
  r17ExternalPilot: "BLOCKED",
  r18TwoHostTest: "NOT_RUN",
});
export function XiCommonsSourceTile() {
  const entry = XI_PHI_COMMONS_SOURCE;
  return <section className="ecosystem-candidates" aria-label="Xi Phi Commons public source and offline status">
    <div className="panel-title">Ξ ⇄ Φ COMMONS · PUBLIC COLLABORATION SOURCE</div>
    <div className="ecosystem-candidate-list">
      <article className="ecosystem-candidate">
        <div className="ecosystem-candidate-header">
          <strong>{entry.label}</strong>
          <small>SOURCE ONLY · NOT INSTALLED</small>
        </div>
        <p>Public Xi–Φ369 engineering roadmap, candidate capability registry and offline-intake
          specifications. R15/R16 have local-only fixture evidence. R17 external pilot is blocked;
          an authenticated R18 two-machine crossing has not run.</p>
        <dl>
          <div><dt>OFFLINE READY</dt><dd>Only this catalog description is bundled; no gateway web app or Xi data is cached by PhiOS.</dd></div>
          <div><dt>WEBSITE</dt><dd>Not verified deployed; public GitHub source remains the reviewed entry.</dd></div>
          <div><dt>LAUNCH AUTHORITY</dt><dd>None. No installed app, model routing, remote tool or repo writes.</dd></div>
          <div><dt>RESEARCH PILOT</dt><dd>R17: BLOCKED · R18: NOT RUN</dd></div>
        </dl>
        <a href={entry.sourceUrl} target="_blank" rel="noopener noreferrer">
          OPEN PUBLIC SOURCE ↗
        </a>
        <p className="muted">Source link requires network access. Displaying this tile does not
          create an installation, security grant or live Xi connection.</p>
      </article>
    </div>
  </section>;
}
