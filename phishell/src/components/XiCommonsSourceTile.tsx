/** R17.6: verified public HTTPS website + source-only PhiOS reference.
 * No app installation, launch grant, Xi transport or private data is involved.
 */
export const XI_PHI_COMMONS_SOURCE = Object.freeze({
  id: "phios.catalog.xi-phi-commons-source",
  label: "Ξ ⇄ Φ · Sovereign Commons Gateway",
  websiteUrl: "https://michaelwave369.github.io/xi-vessel-bridge/",
  sourceUrl: "https://github.com/MichaelWave369/xi-vessel-bridge",
  proofRunUrl: "https://github.com/MichaelWave369/xi-vessel-bridge/actions/runs/40243474173",
  manifestSha256: "a85309f577e73d20b96fb1442f1f6d0628195805033b456fa81aa39fda9647f3",
  docsUrl: "https://github.com/MichaelWave369/xi-vessel-bridge/blob/main/docs/XI_PAGES_LIVE_READINESS_R175.md",
  status: "SOURCE_ONLY",
  localSnapshotAvailableOffline: true,
  externalSiteVerified: true,
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
  return <section className="ecosystem-candidates" aria-label="Xi Phi Commons verified public website, source and offline status">
    <div className="panel-title">Ξ ⇄ Φ COMMONS · VERIFIED PUBLIC WEBSITE</div>
    <div className="ecosystem-candidate-list">
      <article className="ecosystem-candidate">
        <div className="ecosystem-candidate-header">
          <strong>{entry.label}</strong>
          <small>PUBLIC HTTPS VERIFIED · NOT INSTALLED</small>
        </div>
        <p>The public static Gateway is deployed and verified against a source-linked SHA-256
          manifest. R15/R16 remain local-only fixtures. R17 external pilot is blocked;
          an authenticated R18 two-machine Xi crossing has not run.</p>
        <dl>
          <div><dt>OFFLINE READY</dt><dd>Only this catalog description is bundled; no gateway web app or Xi data is cached by PhiOS.</dd></div>
          <div><dt>WEBSITE</dt><dd>Public static site verified via GitHub Pages R17.5 deployment; requires internet to open.</dd></div>
          <div><dt>LAUNCH AUTHORITY</dt><dd>None. No installed app, model routing, remote tool or repo writes.</dd></div>
          <div><dt>RESEARCH PILOT</dt><dd>R17: BLOCKED · R18: NOT RUN</dd></div>
        </dl>
        <a href={entry.websiteUrl} target="_blank" rel="noopener noreferrer">OPEN PUBLIC COMMONS GATEWAY ↗</a>
        <a href={entry.sourceUrl} target="_blank" rel="noopener noreferrer">OPEN CANONICAL GITHUB SOURCE ↗</a>
        <p className="muted">Both links are user-clicked public web destinations. This tile
          does not install the Gateway, authenticate Xi, or create permissions.</p>
      </article>
    </div>
  </section>;
}
