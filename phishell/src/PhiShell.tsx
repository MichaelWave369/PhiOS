import { useMemo, useState } from "react";

type View = "home" | "research" | "build" | "memory" | "ledger" | "governance" | "settings";
type VesselMode = "chat" | "dream" | "translate" | "build" | "ledger";

const nav: Array<{id: View; icon: string; label: string}> = [
  { id: "home", icon: "⌂", label: "Home" },
  { id: "research", icon: "◈", label: "Research" },
  { id: "build", icon: "⌘", label: "Build" },
  { id: "memory", icon: "◎", label: "Memory" },
  { id: "ledger", icon: "▤", label: "Ledger" },
  { id: "governance", icon: "◇", label: "Governance" },
  { id: "settings", icon: "⚙", label: "Settings" },
];

const projects = [
  ["PhiOS Platform", "System", "active"],
  ["UFP Research", "Research", "2h"],
  ["Domistika", "Creative", "5h"],
  ["Browsallax", "Browser", "1d"],
];

const apps = [
  ["Browsallax", "◉"], ["PhiOffice", "▧"], ["Domistika", "⌂"], ["SOMA", "◌"],
  ["Professor Φ", "Φ"], ["Reality Ledger", "▤"], ["Builder", "⌘"], ["Apps", "⊞"],
];

function TopBar() {
  return <header className="topbar">
    <div className="brand"><b>Φ</b><span>PhiOS</span></div>
    <div className="topphrase">PEOPLE + INTELLIGENCE + POSSIBILITY</div>
    <div className="sys"><span>NET</span><span>AUDIO</span><span>LOCAL</span><time>19:50</time></div>
  </header>;
}

function Rail({view, setView}:{view:View;setView:(v:View)=>void}) {
  return <aside className="rail">
    {nav.map(item => <button
      key={item.id}
      onClick={()=>setView(item.id)}
      className={view===item.id ? "rail-item active" : "rail-item"}
      aria-label={item.label}
    >
      <span className="rail-icon">{item.icon}</span>
      <span>{item.label}</span>
    </button>)}
  </aside>;
}

function Home() {
  return <div className="home-grid">
    <section className="hero-card">
      <div className="orbit">
        <div className="orbital orbital-a" />
        <div className="orbital orbital-b" />
        <div className="core">Φ</div>
      </div>
      <div className="hero-copy">
        <div className="eyebrow">PHIOS OPERATING ENVIRONMENT</div>
        <h1>PhiOS</h1>
        <p className="purpose">YOUR COMPUTER. A HIGHER PURPOSE.</p>
        <p className="triad">SOVEREIGN · COHERENT · LOCAL · FREE</p>
      </div>
      <div className="hero-law">
        <small>PRIMARY INVARIANT</small>
        <strong>CAPABILITY != AUTHORITY</strong>
      </div>
    </section>

    <section className="panel status">
      <div className="panel-title">SYSTEM STATUS</div>
      {[
        ["PhiVessel","Online"],["Models","Ready"],["Memory","Nominal"],
        ["SOMA","Active"],["Ledger","Recording"],["Network","Connected"]
      ].map(([a,b])=><div className="status-row" key={a}><span>{a}</span><b>{b}</b></div>)}
    </section>

    <section className="panel recent">
      <div className="panel-title">RECENT PROJECTS</div>
      {projects.map(([name,type,when])=><div className="project" key={name}>
        <div className="project-dot" />
        <div><b>{name}</b><small>{type}</small></div>
        <time>{when}</time>
      </div>)}
    </section>

    <section className="panel launcher">
      <div className="panel-title">APP LAUNCHER</div>
      <div className="app-grid">{apps.map(([name,icon])=><button className="app-tile" key={name}><span>{icon}</span><small>{name}</small></button>)}</div>
    </section>

    <section className="panel notices">
      <div className="panel-title">NOTIFICATIONS</div>
      <div className="notice"><b>PhiOS site deployed</b><small>Public explorer is live from main.</small></div>
      <div className="notice"><b>Memory nominal</b><small>Canonical store and retrieval boundaries healthy.</small></div>
      <div className="notice"><b>Authority plane quiet</b><small>No pending consequential requests.</small></div>
    </section>

    <section className="panel resources">
      <div className="panel-title">SYSTEM RESOURCES</div>
      {[["CPU",18],["GPU",32],["MEM",46],["STORAGE",38]].map(([n,v])=><div className="meter" key={String(n)}>
        <span>{n}</span><div><i style={{width:`${v}%`}} /></div><b>{v}%</b>
      </div>)}
    </section>
  </div>;
}

function Workspace({title,subtitle}:{title:string;subtitle:string}) {
  return <section className="workspace">
    <div className="workspace-heading"><div className="eyebrow">PHISHELL WORKSPACE</div><h1>{title}</h1><p>{subtitle}</p></div>
    <div className="workspace-columns">
      <div className="panel"><div className="panel-title">FIELD</div><p className="muted">This surface is a visual shell prototype. Runtime bindings arrive through explicit PhiOS contracts, never by pretending a UI control already owns authority.</p></div>
      <div className="panel"><div className="panel-title">CONTEXT</div><div className="empty-state">No active runtime context yet.</div></div>
    </div>
  </section>;
}

function Center({view}:{view:View}) {
  if (view==="home") return <Home />;
  const copy:Record<Exclude<View,"home">,[string,string]>={
    research:["Research","Sources, evidence, notes, synthesis, and provenance in one governed workspace."],
    build:["Build","Projects, code, tests, artifacts, and execution proposals without authority laundering."],
    memory:["Memory","Canonical records, semantic retrieval, currentness, lineage, and read admissibility."],
    ledger:["Reality Ledger","Append-only receipts and bounded read-only projections of system history."],
    governance:["Governance","Authority, grants, capabilities, effect boundaries, escalations, and control-plane state."],
    settings:["Settings","Operator configuration for the PhiOS environment and Linux substrate."]
  };
  return <Workspace title={copy[view][0]} subtitle={copy[view][1]} />;
}

function PhiVessel() {
  const [mode,setMode]=useState<VesselMode>("chat");
  return <aside className="vessel">
    <div className="vessel-head"><div className="vessel-mark">◉</div><div><b>PhiVessel</b><small>Always here. Thinking with you.</small></div></div>
    <div className="vessel-tabs">{(["chat","dream","translate","build","ledger"] as VesselMode[]).map(m=><button className={mode===m?"active":""} key={m} onClick={()=>setMode(m)}>{m}</button>)}</div>
    <div className="vessel-body">
      <small className="mode-label">{mode.toUpperCase()} MODE · ADVISORY</small>
      <h2>Good evening.</h2>
      <p>PhiShell is online as a visual environment prototype.</p>
      <p className="muted">No action or execution authority is implied by this panel.</p>
      <div className="quick-actions">
        <button>Continue last session</button>
        <button>Search my knowledge</button>
        <button>Analyze this workspace</button>
        <button>Help me build something</button>
      </div>
    </div>
    <div className="prompt"><input placeholder="Ask PhiVessel anything…" /><button>→</button></div>
  </aside>;
}

function StartMenu({close}:{close:()=>void}) {
  return <div className="start-menu">
    <div className="start-title"><b>Φ</b><span>PhiOS</span><button onClick={close}>×</button></div>
    <input autoFocus placeholder="Search apps, files, memory, commands…" />
    <div className="start-section">PINNED</div>
    <div className="start-apps">{apps.slice(0,6).map(([n,i])=><button key={n}><span>{i}</span>{n}</button>)}</div>
    <div className="start-footer"><span>Operator</span><div><button>Lock</button><button>Power</button></div></div>
  </div>;
}

export function PhiShell() {
  const [view,setView]=useState<View>("home");
  const [start,setStart]=useState(false);
  const title=useMemo(()=>nav.find(x=>x.id===view)?.label ?? "Home",[view]);
  return <div className="shell">
    <TopBar />
    <Rail view={view} setView={setView} />
    <main className="field">
      <div className="field-title"><span>{title}</span><small>PhiShell v0.1 · Linux-based environment prototype</small></div>
      <Center view={view} />
    </main>
    <PhiVessel />
    <footer className="commandbar">
      <button className="start-button" onClick={()=>setStart(!start)}><b>Φ</b><span>Start</span></button>
      <button className="search-button">⌕ <span>Search anything…</span></button>
      <div className="task-icons"><span>▣</span><span>◉</span><span>▤</span><span>⌘</span></div>
      <div className="motto">LEDGER ABOVE EGO</div>
      <div className="tray"><span>NET</span><span>VOL</span><span>LOCAL</span></div>
    </footer>
    {start && <StartMenu close={()=>setStart(false)} />}
  </div>;
}
