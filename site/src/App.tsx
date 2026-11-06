import { useEffect, useMemo, useState } from "react";
import FieldCompanionReceiver from "./FieldCompanionReceiver";
import BrowserGpuInspector from "./BrowserGpuInspector";

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
  linuxImage?: {
    version: string;
    stage: string;
    architecture: string;
    secureBoot: boolean;
  };
};

const experiences = [
  {
    code: "01 / DESKTOP",
    title: "PhiOS Web",
    badge: "BROWSER EXPERIENCE",
    copy: "Enter the local-first browser desktop. No native OS installation or special device permissions.",
    href: "https://phi-field.com/os/",
    action: "Launch PhiOS Web",
    featured: true,
  },
  {
    code: "02 / IMMERSIVE",
    title: "PhiOS XR",
    badge: "BROWSER + OPTIONAL WEBXR",
    copy: "Explore the spatial PhiOS interface in a browser, with WebXR on compatible headsets.",
    href: "https://michaelwave369.github.io/PhiOS-XR/",
    action: "Enter PhiOS XR",
    featured: false,
  },
  {
    code: "03 / TOUCH",
    title: "PhiOS Mobile",
    badge: "BROWSER / PWA PREVIEW",
    copy: "Open the touch-first PhiOS experience. It is not a replacement Android operating system.",
    href: "https://michaelwave369.github.io/PhiOS-Mobile/",
    action: "Open PhiOS Mobile",
    featured: false,
  },
] as const;

const ecosystem = [
  {
    index: "01",
    title: "Infinite Porch",
    role: "LOCAL AI HOME",
    copy: "Local-first model and assistant home, with opt-in peer and model identity.",
    href: "https://github.com/MichaelWave369/Infinite-Porch",
    label: "View AI home source",
  },
  {
    index: "02",
    title: "Infinite Commons",
    role: "WORLDS & PORTALS",
    copy: "Shared worlds and portals, linked to PhiOS rather than claimed as native installs.",
    href: "https://github.com/MichaelWave369/Infinite-Commons",
    label: "Explore worlds",
  },
  {
    index: "03",
    title: "Universal App Center",
    role: "GOVERNED APPLICATIONS",
    copy: "App discovery, bounded permissions, versioned transitions and evidence. A catalog link is not an install.",
    href: "https://github.com/MichaelWave369/PhiOS/blob/main/docs/PHIOS_UNIVERSAL_APP_CENTER_R5D.md",
    label: "Review app lifecycle",
  },
  {
    index: "04",
    title: "Infinite Interconnects",
    role: "PROPOSED GOVERNED BRIDGE",
    copy: "Cross-system bridge research. Simulator and proposals only, not a production transport.",
    href: "https://github.com/MichaelWave369/InfiniteInterconnects",
    label: "View bridge research",
  },
] as const;

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
    line: "test contracts through v0.61",
    summary: "Governed intake, build, install, update, rollback, cleanup and release lineage, with installed-VM qualification still evolving.",
    principle: "Installed != runnable.",
    docs: "docs/PHIOS_UNIVERSAL_APP_CENTER_R5D.md",
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
    docs: "docs/ledger-analytics.md",
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
  const [menuOpen, setMenuOpen] = useState(false);
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
      <a className="skip-link" href="#experiences">Skip to experiences</a>
      <header className="topbar">
        <a className="brand" href="#top" aria-label="PhiOS home">
          <span className="phi">φ</span>
          <span>PhiOS</span>
          <span className="brand-subtitle">/ MISSION CONTROL</span>
        </a>
        <nav className="navlinks" aria-label="Primary navigation">
          <a href="#experiences">Experiences</a>
          <a href="#ecosystem">Ecosystem</a>
          <a href="#linux-image">Linux Image</a>
          <a href="#architecture">Architecture</a>
          <a href="#sovereignty">Sovereignty</a>
          <a href="#status">Live Project</a>
          <a href={`${import.meta.env.BASE_URL}operator-passport/`}>Operator Passport</a>
          <a href="https://github.com/MichaelWave369/PhiOS">GitHub</a>
        </nav>
        <div className="topbar-controls">
          <button
            className="crt-toggle"
            type="button"
            aria-pressed={crt}
            onClick={() => setCrt((value) => !value)}
          >
            {crt ? "CRT ON" : "CRT MODE"}
          </button>
          <button className="menu-toggle" type="button"
            aria-label={menuOpen ? "Close menu" : "Open menu"}
            aria-expanded={menuOpen} aria-controls="mobile-site-nav"
            onClick={() => setMenuOpen((value) => !value)}>
            {menuOpen ? "CLOSE" : "MENU"}
          </button>
        </div>
      </header>
      <nav id="mobile-site-nav" className={menuOpen ? "mobile-nav open" : "mobile-nav"} aria-label="Mobile navigation">
        {[
          ["Experiences", "#experiences"], ["Ecosystem", "#ecosystem"],
          ["Linux Image", "#linux-image"], ["Architecture", "#architecture"],
          ["Sovereignty", "#sovereignty"], ["Live Project", "#status"],
        ].map(([label, href]) => (
          <a key={href} href={href} onClick={() => setMenuOpen(false)}>{label}</a>
        ))}
        <a href="https://github.com/MichaelWave369/PhiOS">GitHub source</a>
      </nav>

      <main id="top">
        <section className="hero">
          <div className="eyebrow"><span className="signal-dot" /> Φ369 LABS / THE FIELD IS OPEN</div>
          <h1>
            Sovereign. Coherent.
            <br />
            Local. <span>Free.</span>
          </h1>
          <p className="hero-copy">
            One platform. Many worlds. Enter the browser desktop, explore the XR and mobile
            experiences, or follow the evidence behind the developing Linux operating system.
            Local-first by design, with explicit permission before consequential action.
          </p>
          <div className="law-card">
            <span>PRIMARY INVARIANT</span>
            <strong>CAPABILITY != AUTHORITY</strong>
          </div>
          <div className="hero-actions">
            <a className="button primary" href="https://phi-field.com/os/">Launch PhiOS Web ↗</a>
            <a className="button" href="#architecture">Explore the system</a>
            <a className="button subtle" href="#linux-image">Linux image status</a>
          </div>
          <div className="hero-footnote">
            <span className="signal-dot" /> Browser experiences are previews, not native OS installs.
          </div>
        </section>


        <section className="section experiences-section" id="experiences">
          <div className="section-heading">
            <div>
              <span className="kicker">THREE EXPERIENCES / ONE FIELD</span>
              <h2>Choose how to enter.</h2>
            </div>
            <p>Three real browser destinations, without confusing them with the experimental Linux image or granting device authority.</p>
          </div>
          <div className="experience-grid">
            {experiences.map((experience) => (
              <article className={experience.featured ? "experience-card featured" : "experience-card"} key={experience.title}>
                <div className="experience-meta">
                  <span>{experience.code}</span>
                  <span className="experience-badge">{experience.badge}</span>
                </div>
                <div className="experience-glyph" aria-hidden="true">{experience.featured ? "Φ" : experience.title === "PhiOS XR" ? "◉" : "▣"}</div>
                <h3>{experience.title}</h3>
                <p>{experience.copy}</p>
                <a className="experience-link" href={experience.href}>{experience.action} <span aria-hidden="true">↗</span></a>
              </article>
            ))}
          </div>
          <p className="experience-footnote">
            Looking for the cinematic gateway? <a href="https://phi-field.com/">Enter Φ Field ↗</a>.
            No browser experience replaces the separately qualified native Linux system.
          </p>
        </section>

        <BrowserGpuInspector />
        <FieldCompanionReceiver />

        <section className="section ecosystem-section" id="ecosystem">
          <div className="section-heading">
            <div>
              <span className="kicker">THE PHIOS ECOSYSTEM</span>
              <h2>One system, connected by choice.</h2>
            </div>
            <p>PhiOS is the governed runtime. Porch brings local AI home, Commons connects worlds, and bridge research remains explicitly opt-in.</p>
          </div>
          <div className="ecosystem-grid">
            {ecosystem.map((item) => (
              <article className="ecosystem-card" key={item.index}>
                <div className="ecosystem-index">{item.index} / Φ</div>
                <span className="kicker">{item.role}</span>
                <h3>{item.title}</h3>
                <p>{item.copy}</p>
                <a href={item.href}>{item.label} <span aria-hidden="true">↗</span></a>
              </article>
            ))}
          </div>
          <p className="ecosystem-footnote">A linked or cataloged project is not automatically installed or authorized on any PhiOS device.</p>
        </section>

        <section className="laws" aria-label="Architectural laws">
          {laws.map((law) => (
            <div className="law" key={law}>{law}</div>
          ))}
        </section>

        <section className="section" id="sovereignty">
          <div className="section-heading">
            <div>
              <span className="kicker">THE Φ EXIT TEST</span>
              <h2>Build a system people can leave.</h2>
            </div>
            <p>
              Seven rights. Independently verifiable restoration. No mandatory cloud account,
              no artificial export barrier, and no platform self-certification.
            </p>
          </div>
          <div className="sovereignty-site-grid">
            <article>
              <span>PUBLIC CONTRACT</span>
              <h3>Your data and capability remain yours</h3>
              <p>The right to inspect, migrate, fork, operate offline, and leave is a release requirement, not a marketing badge.</p>
              <a href={repoDocUrl("SOVEREIGNTY_CONTRACT.md")}>Read the Φ Sovereignty Contract →</a>
            </article>
            <article>
              <span>FIRST EXECUTABLE RUNG</span>
              <h3>Portable directory backup</h3>
              <p>Standalone Python creates verifiable ZIP archives and restores ordinary files without PhiOS. Archives are unencrypted.</p>
              <a href={repoDocUrl("docs/PHIOS_SOVEREIGNTY_EXIT_V01.md")}>See independent export commands →</a>
            </article>
            <article>
              <span>OVERALL STATUS: UNVERIFIED</span>
              <h3>No imaginary green checkmarks</h3>
              <p>OS cold boot, application state completeness, provider swaps, and identity recovery need independent evidence.</p>
              <a href="https://github.com/MichaelWave369/PhiOS/issues">Track the remaining engineering work →</a>
            </article>
          </div>
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


        <section className="section linux-section" id="linux-image">
          <div className="section-heading">
            <div>
              <span className="kicker">NATIVE OS / EXPERIMENTAL ALPHA</span>
              <h2>From boot to recovery.</h2>
            </div>
            <p>The x86_64 UEFI image is a separate Arch-based Wayfire/PhiShell development effort, with bounded installed-VM evidence and release gates still open.</p>
          </div>
          <div className="image-status-banner">
            <div>
              <span className="kicker">IMAGE TRACK</span>
              <h3>PhiOS Linux <span>{status?.linuxImage?.version ?? "0.1.0-alpha.1"}</span></h3>
              <p>Development preview. Not a general-purpose supported installer, verified physical-device release, or Secure Boot image.</p>
            </div>
            <div className="image-status-label">NOT PUBLIC RELEASE-READY</div>
          </div>
          <div className="image-milestones">
            <article>
              <span>01 / BOOT</span>
              <h3>UEFI and graphical desktop</h3>
              <p>Normal live boot, non-root Wayfire/PhiShell session and bounded QEMU qualification.</p>
            </article>
            <article>
              <span>02 / RECOVER</span>
              <h3>State and root/EFI recovery</h3>
              <p>Installed disposable-VM persistence and OS recovery exercises, not physical power-loss certification.</p>
            </article>
            <article>
              <span>03 / APP LIFECYCLE</span>
              <h3>Governed application tests</h3>
              <p>R5D exercises live test processes and data. A complete signed third-party in-guest install remains unqualified.</p>
            </article>
          </div>
          <div className="image-actions">
            <a className="button primary" href={repoDocUrl("docs/os/RELEASE_HANDOFF.md")}>Review exact image evidence ↗</a>
            <a className="button" href={repoDocUrl("docs/os/RELEASE_CONTRACT.md")}>Read release gates</a>
          </div>
        </section>

        <section className="section hardening-section" id="hardening">
          <div className="section-heading">
            <div>
              <span className="kicker">RESEARCH HARDENING</span>
              <h2>The safeguards behind the system.</h2>
            </div>
            <p>
              Explore the ten historical research-hardening rungs. Preserved for auditability,
              without letting old milestones crowd out current image and application work.
            </p>
          </div>
          <details className="history-details">
            <summary>Explore ten merged research-hardening milestones</summary>
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
          </details>
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
              This panel reflects the checked-out source, including the latest App Platform
              test contract and Linux image manifest. It carries no operational authority.
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
            <div><span>App tests</span><strong>{status?.versionLines.appPlatform ?? "checking…"}</strong></div>
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
        <a href="https://phi-field.com/">ENTER Φ FIELD</a>
        <span>CAPABILITY != AUTHORITY</span>
      </footer>
    </div>
  );
}
