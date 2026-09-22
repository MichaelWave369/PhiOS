import { useEffect, useMemo, useState } from "react";

type ViewMode = "system" | "authority" | "evidence";

type ArchitectureNode = {
  id: string;
  name: string;
  line: string;
  summary: string;
  principle: string;
  docs: string;
  modes: ViewMode[];
  authority: "none" | "bounded" | "explicit";
};

type ProjectStatus = {
  repository: string;
  commit: string;
  commitShort: string;
  commitDate: string;
  latestMergedPr: number | null;
  siteBuild: string;
  versionLines: {
    spine: string;
    appPlatform: string;
    phiReflex: string;
    hardening: string;
  };
  source: string;
  authority: string;
};

const architecture: ArchitectureNode[] = [
  {
    id: "shell",
    name: "Shell / MCP",
    line: "operator boundary",
    summary: "Human, client, and local-agent requests enter through explicit capability surfaces.",
    principle: "A request is not permission.",
    docs: "README.md",
    modes: ["system", "authority"],
    authority: "bounded",
  },
  {
    id: "spine",
    name: "Spine",
    line: "v0.24",
    summary: "Authority-aware observation, verification, evidence, and bounded receipts.",
    principle: "Observation != truth.",
    docs: "docs/PHIOS_SPINE_V0.24_NUMERIC_TRANSITION_CONTRACT.md",
    modes: ["system", "evidence"],
    authority: "none",
  },
  {
    id: "apps",
    name: "App Platform",
    line: "v0.50",
    summary: "Governed intake, build, install, update, rollback, cleanup, and release lineage.",
    principle: "Installed != runnable.",
    docs: "docs/PHIOS_APP_PLATFORM_V0.50_RELEASE_INSTALL_PROPOSAL_GATE.md",
    modes: ["system", "authority"],
    authority: "bounded",
  },
  {
    id: "reflex",
    name: "PhiReflex",
    line: "v0.10",
    summary: "Fast provider-neutral advisory routing with authenticated, constrained influence.",
    principle: "Routing influence != execution authority.",
    docs: "docs/PHIOS_REFLEX_V0.10_ROOT_ATTESTATION.md",
    modes: ["system", "evidence"],
    authority: "none",
  },
  {
    id: "reality",
    name: "Reality Gate",
    line: "verification",
    summary: "Tests claims against bounded observations without promoting evidence into truth.",
    principle: "Detection != remediation authority.",
    docs: "docs/PHIOS_SPINE_V0.10_REALITY_GATE.md",
    modes: ["system", "evidence"],
    authority: "none",
  },
  {
    id: "memory",
    name: "Governed Memory",
    line: "canonical + derived index",
    summary: "Canonical local records, replaceable semantic retrieval, currentness and admissibility.",
    principle: "Retrievable != currently admissible.",
    docs: "docs/governed-memory.md",
    modes: ["system", "evidence"],
    authority: "none",
  },
  {
    id: "covenant",
    name: "Covenant",
    line: "CR-01 + recovery",
    summary: "Zero-authority identity, topology, epoch continuity, and recovery contracts.",
    principle: "Recovered state != recovered authority.",
    docs: "docs/PHIOS_IDENTITY_RECOVERY_V0.1.md",
    modes: ["system", "evidence"],
    authority: "none",
  },
  {
    id: "mandala",
    name: "Mandala",
    line: "typed contracts",
    summary: "Typed authority and evidence contracts bind consequential transitions.",
    principle: "Capability != authority.",
    docs: "docs/PHIOS_SPINE_V0.2_MANDALA_CONTRACT.md",
    modes: ["system", "authority", "evidence"],
    authority: "explicit",
  },
  {
    id: "action",
    name: "Governed Action",
    line: "execution handoff",
    summary: "Explicit authority is revalidated before consequential execution is handed off.",
    principle: "Plan adoption != action authority.",
    docs: "docs/PHIOS_GOVERNED_EXECUTION_HANDOFF_V0.8.md",
    modes: ["system", "authority"],
    authority: "explicit",
  },
  {
    id: "ledger",
    name: "Reality Ledger",
    line: "append-only evidence",
    summary: "Typed receipts remain auditable while analytics stay read-only and non-authoritative.",
    principle: "History remains evidence.",
    docs: "docs/PHIOS_LEDGER_REPORTS_V0.1.md",
    modes: ["system", "authority", "evidence"],
    authority: "none",
  },
];

const hardening = [
  ["#181", "Memory No-Mint", "Derived memory cannot originate authority."],
  ["#182", "Control Plane Isolation", "Actors cannot re-enter declared governing surfaces."],
  ["#183", "Effect Boundary", "Capability is classified by environmental effect."],
  ["#184", "Observation Frontier", "Negative claims cannot exceed demonstrated coverage."],
  ["#185", "Transformation Lineage", "Source, taint, derivation, and exactness stay bound."],
  ["#186", "Evidence Independence", "Agreement is not independent corroboration."],
  ["#187", "Governance Escalation", "Detection can request review without minting remediation authority."],
  ["#188", "Dynamic State Lifecycle", "Advisory state decays and terminates deterministically."],
  ["#189", "Evidence Horizon + API Keys", "Currentness and authentication remain separate from authority."],
  ["#190", "Identity Recovery", "Continuity cannot silently restore prior authority."],
] as const;

const laws = [
  "capability != authority",
  "observation != truth",
  "retrievable != currently admissible",
  "authentication != authorization",
  "detection != authorized remediation",
  "recovered state != recovered authority",
];

function repoDocUrl(path: string) {
  return `https://github.com/MichaelWave369/PhiOS/blob/main/${path}`;
}

export default function App() {
  const [mode, setMode] = useState<ViewMode>("system");
  const [crt, setCrt] = useState(false);
  const [selected, setSelected] = useState("mandala");
  const [status, setStatus] = useState<ProjectStatus | null>(null);

  useEffect(() => {
    fetch(`${import.meta.env.BASE_URL}project-status.json`)
      .then((response) => {
        if (!response.ok) throw new Error("status unavailable");
        return response.json() as Promise<ProjectStatus>;
      })
      .then(setStatus)
      .catch(() => setStatus(null));
  }, []);

  const visibleNodes = useMemo(
    () => architecture.filter((node) => node.modes.includes(mode)),
    [mode],
  );

  useEffect(() => {
    if (!visibleNodes.some((node) => node.id === selected)) {
      setSelected(visibleNodes[0]?.id ?? "mandala");
    }
  }, [mode, selected, visibleNodes]);

  const selectedNode = architecture.find((node) => node.id === selected) ?? architecture[0];

  return (
    <div className={crt ? "app crt" : "app"}>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="PhiOS home">
          <span className="phi">φ</span>
          <span>PhiOS</span>
        </a>
        <nav className="navlinks" aria-label="Primary navigation">
          <a href="#architecture">Architecture</a>
          <a href="#hardening">Hardening</a>
          <a href="#status">Live Project</a>
          <a href="https://github.com/MichaelWave369/PhiOS">GitHub</a>
        </nav>
        <button
          className="crt-toggle"
          type="button"
          aria-pressed={crt}
          onClick={() => setCrt((value) => !value)}
        >
          {crt ? "CRT ON" : "CRT MODE"}
        </button>
      </header>

      <main id="top">
        <section className="hero">
          <div className="eyebrow">LOCAL-FIRST · AUTHORITY-AWARE · OPEN SOURCE</div>
          <h1>
            Sovereign. Coherent.
            <br />
            Local. <span>Free.</span>
          </h1>
          <p className="hero-copy">
            PhiOS is an operator shell, verification spine, governed application platform,
            memory/ledger system, and constrained agent runtime built around one hard rule.
          </p>
          <div className="law-card">
            <span>PRIMARY INVARIANT</span>
            <strong>CAPABILITY != AUTHORITY</strong>
          </div>
          <div className="hero-actions">
            <a className="button primary" href="#architecture">Explore the system</a>
            <a className="button" href="https://github.com/MichaelWave369/PhiOS">View source</a>
          </div>
        </section>

        <section className="laws" aria-label="Architectural laws">
          {laws.map((law) => (
            <div className="law" key={law}>{law}</div>
          ))}
        </section>

        <section className="section" id="architecture">
          <div className="section-heading">
            <div>
              <span className="kicker">INTERACTIVE ARCHITECTURE</span>
              <h2>The graph changes with the question.</h2>
            </div>
            <p>
              System structure, authority flow, and evidence flow are related, but they are
              deliberately not the same graph.
            </p>
          </div>

          <div className="mode-switch" role="group" aria-label="Architecture view">
            {(["system", "authority", "evidence"] as ViewMode[]).map((item) => (
              <button
                key={item}
                type="button"
                className={mode === item ? "active" : ""}
                onClick={() => setMode(item)}
              >
                {item.toUpperCase()}
              </button>
            ))}
          </div>

          <div className="architecture-layout">
            <div className="node-grid">
              {visibleNodes.map((node) => (
                <button
                  type="button"
                  key={node.id}
                  className={selected === node.id ? "node selected" : "node"}
                  onClick={() => setSelected(node.id)}
                >
                  <span className="node-line">{node.line}</span>
                  <strong>{node.name}</strong>
                  <small>{node.principle}</small>
                  <span className={`authority authority-${node.authority}`}>
                    {node.authority === "none" ? "ZERO AUTHORITY" : `${node.authority.toUpperCase()} AUTHORITY`}
                  </span>
                </button>
              ))}
            </div>

            <aside className="detail-panel">
              <span className="kicker">SELECTED SURFACE</span>
              <h3>{selectedNode.name}</h3>
              <p>{selectedNode.summary}</p>
              <blockquote>{selectedNode.principle}</blockquote>
              <a href={repoDocUrl(selectedNode.docs)}>Open governing contract →</a>
            </aside>
          </div>

          <div className="mode-explainer">
            {mode === "system" && "SYSTEM shows the major runtime surfaces and how they fit together."}
            {mode === "authority" && "AUTHORITY strips away advisory-only paths and highlights surfaces that can participate in consequential action."}
            {mode === "evidence" && "EVIDENCE follows observation, provenance, memory, verification, identity evidence, and receipts without pretending any of them are permission."}
          </div>
        </section>

        <section className="section hardening-section" id="hardening">
          <div className="section-heading">
            <div>
              <span className="kicker">RESEARCH HARDENING</span>
              <h2>Ten seams. Ten bounded increments.</h2>
            </div>
            <p>
              The #181 → #190 ladder hardened specific failure modes without redesigning
              PhiOS around the research.
            </p>
          </div>
          <div className="ladder">
            {hardening.map(([pr, name, description], index) => (
              <article className="rung" key={pr}>
                <div className="rung-index">{String(index + 1).padStart(2, "0")}</div>
                <div>
                  <span>{pr}</span>
                  <h3>{name}</h3>
                  <p>{description}</p>
                </div>
                <div className="check">✓ MERGED</div>
              </article>
            ))}
          </div>
          <a
            className="text-link"
            href={repoDocUrl("docs/ENTER_THE_FIELD_PHIOS_HARDENING.md")}
          >
            Read the full research-to-architecture traceability document →
          </a>
        </section>

        <section className="section" id="status">
          <div className="section-heading">
            <div>
              <span className="kicker">LIVE PROJECT</span>
              <h2>Build facts, not browser secrets.</h2>
            </div>
            <p>
              This panel is generated from the repository checkout that produced the site.
              It carries no operational, action, or execution authority.
            </p>
          </div>

          <div className="status-grid">
            <div className="status-card">
              <span>MAIN COMMIT</span>
              <strong>{status?.commitShort ?? "loading…"}</strong>
              <small>{status?.commitDate ?? "repository build metadata"}</small>
            </div>
            <div className="status-card">
              <span>LATEST MERGED PR</span>
              <strong>{status?.latestMergedPr ? `#${status.latestMergedPr}` : "—"}</strong>
              <small>from local Git history</small>
            </div>
            <div className="status-card">
              <span>SITE BUILD</span>
              <strong>{status?.siteBuild?.toUpperCase() ?? "LOADING…"}</strong>
              <small>Pages artifact validation</small>
            </div>
            <div className="status-card">
              <span>AUTHORITY</span>
              <strong>NONE</strong>
              <small>public informational projection</small>
            </div>
          </div>

          <div className="versions">
            <div><span>Spine</span><strong>{status?.versionLines.spine ?? "v0.24"}</strong></div>
            <div><span>App Platform</span><strong>{status?.versionLines.appPlatform ?? "v0.50"}</strong></div>
            <div><span>PhiReflex</span><strong>{status?.versionLines.phiReflex ?? "v0.10"}</strong></div>
            <div><span>Hardening</span><strong>{status?.versionLines.hardening ?? "v0.10"}</strong></div>
          </div>
        </section>

        <section className="closing">
          <span className="phi giant">φ</span>
          <div>
            <span className="kicker">PHIOS</span>
            <h2>Powerful local computation without quietly turning ability into permission.</h2>
            <a className="button primary" href="https://github.com/MichaelWave369/PhiOS">
              Explore the repository
            </a>
          </div>
        </section>
      </main>

      <footer>
        <span>φ PhiOS · MIT licensed project-owned code unless otherwise noted.</span>
        <span>CAPABILITY != AUTHORITY</span>
      </footer>
    </div>
  );
}
