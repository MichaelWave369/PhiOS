import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { HostObservationPanel } from "./components/HostObservationPanel";
import {
  INITIAL_SHELL_STATE,
  type AuthorityRequest,
  type CommandItem,
  type ShellEvent,
  type ShellWindow as WindowModel,
  type VesselMode,
  type View,
} from "./shell/model";
import { shellReducer } from "./shell/reducer";
import {
  linuxServiceAdapter,
  type LinuxServiceReceipt,
} from "./shell/linuxAdapter";

const nav: Array<{ id: View; icon: string; label: string }> = [
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
  ["Browsallax", "◉"],
  ["PhiOffice", "▧"],
  ["Domistika", "⌂"],
  ["SOMA", "◌"],
  ["Professor Φ", "Φ"],
  ["Reality Ledger", "▤"],
  ["Builder", "⌘"],
  ["Apps", "⊞"],
];

const windowTemplates: Record<string, WindowModel> = {
  "research-window": {
    id: "research-window",
    title: "Research Field",
    subtitle: "Evidence, provenance, synthesis, and source context.",
    kind: "workspace",
    x: 7,
    y: 10,
    width: 54,
    height: 58,
    z: 1,
    state: "open",
  },
  "ledger-window": {
    id: "ledger-window",
    title: "Reality Ledger",
    subtitle: "Read-only receipts and system history projection.",
    kind: "system",
    x: 46,
    y: 30,
    width: 46,
    height: 48,
    z: 2,
    state: "open",
  },
  "build-window": {
    id: "build-window",
    title: "Build Field",
    subtitle: "Projects, tests, artifacts, and governed execution proposals.",
    kind: "workspace",
    x: 20,
    y: 16,
    width: 58,
    height: 56,
    z: 1,
    state: "open",
  },
  "system-window": {
    id: "system-window",
    title: "System Inspector",
    subtitle: "Live same-origin Linux observation over a loopback-only read transport.",
    kind: "system",
    x: 22,
    y: 10,
    width: 68,
    height: 72,
    z: 1,
    state: "open",
  },
};

const commands: CommandItem[] = [
  {
    id: "view-research",
    label: "Go to Research",
    detail: "Open the Research destination.",
    action: { type: "open-view", view: "research" },
  },
  {
    id: "window-research",
    label: "Open Research Field",
    detail: "Restore or focus the Research desktop window.",
    action: { type: "open-window", windowId: "research-window" },
  },
  {
    id: "window-ledger",
    label: "Open Reality Ledger",
    detail: "Restore or focus the read-only ledger window.",
    action: { type: "open-window", windowId: "ledger-window" },
  },
  {
    id: "window-build",
    label: "Open Build Field",
    detail: "Open the governed build workspace.",
    action: { type: "open-window", windowId: "build-window" },
  },
  {
    id: "window-system",
    label: "Open System Inspector",
    detail: "Inspect host observation data, provenance, and Linux capability boundaries.",
    action: { type: "open-window", windowId: "system-window" },
  },
  {
    id: "authority-network",
    label: "Request network configuration",
    detail: "Create an authority intent. No Linux effect will execute.",
    action: { type: "request-authority", capability: "network.configure" },
  },
  {
    id: "authority-service",
    label: "Request service control",
    detail: "Create an authority intent for a service operation.",
    action: { type: "request-authority", capability: "service.control" },
  },
];

function authorityRequest(capability: string, reason: string): AuthorityRequest {
  return {
    id: `authority:${capability}`,
    capability,
    scope: "prototype:operator-selected",
    reason,
    requestedBy: "operator",
    decision: "pending",
    executionAuthority: false,
  };
}

function TopBar() {
  return (
    <header className="topbar">
      <div className="brand">
        <b>Φ</b>
        <span>PhiOS</span>
      </div>
      <div className="topphrase">PEOPLE + INTELLIGENCE + POSSIBILITY</div>
      <div className="sys">
        <span>NET</span>
        <span>AUDIO</span>
        <span>LOCAL</span>
        <span className="authority-zero">AUTH 0</span>
      </div>
    </header>
  );
}

function Rail({
  view,
  dispatch,
}: {
  view: View;
  dispatch: (event: ShellEvent) => void;
}) {
  return (
    <aside className="rail">
      {nav.map((item) => (
        <button
          key={item.id}
          onClick={() => dispatch({ type: "SET_VIEW", view: item.id })}
          className={view === item.id ? "rail-item active" : "rail-item"}
          aria-label={item.label}
        >
          <span className="rail-icon">{item.icon}</span>
          <span>{item.label}</span>
        </button>
      ))}
    </aside>
  );
}

function Home() {
  return (
    <div className="home-grid">
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
          ["PhiVessel", "Online"],
          ["Models", "Ready"],
          ["Memory", "Nominal"],
          ["SOMA", "Active"],
          ["Ledger", "Recording"],
          ["Linux Effects", "Blocked"],
        ].map(([a, b]) => (
          <div className="status-row" key={a}>
            <span>{a}</span>
            <b>{b}</b>
          </div>
        ))}
      </section>

      <section className="panel recent">
        <div className="panel-title">RECENT PROJECTS</div>
        {projects.map(([name, type, when]) => (
          <div className="project" key={name}>
            <div className="project-dot" />
            <div>
              <b>{name}</b>
              <small>{type}</small>
            </div>
            <time>{when}</time>
          </div>
        ))}
      </section>

      <section className="panel launcher">
        <div className="panel-title">APP LAUNCHER</div>
        <div className="app-grid">
          {apps.map(([name, icon]) => (
            <button className="app-tile" key={name}>
              <span>{icon}</span>
              <small>{name}</small>
            </button>
          ))}
        </div>
      </section>

      <section className="panel notices">
        <div className="panel-title">V0.4 LOCAL OBSERVATION TRANSPORT</div>
        <div className="notice">
          <b>Loopback transport is bound</b>
          <small>The built shell and live host-observation endpoint share one 127.0.0.1 origin.</small>
        </div>
        <div className="notice">
          <b>Live data must validate</b>
          <small>Freshness, transport identity, source identity, and authority invariants are checked before display.</small>
        </div>
        <div className="notice">
          <b>Observation is not authority</b>
          <small>Every snapshot carries execution_authority=false and effect_performed=false.</small>
        </div>
      </section>

      <section className="panel resources">
        <div className="panel-title">RESOURCE VISUAL PREVIEW · DEMO VALUES</div>
        {[
          ["CPU", 18],
          ["GPU", 32],
          ["MEM", 46],
          ["STORAGE", 38],
        ].map(([name, value]) => (
          <div className="meter" key={String(name)}>
            <span>{name}</span>
            <div>
              <i style={{ width: `${value}%` }} />
            </div>
            <b>{value}%</b>
          </div>
        ))}
      </section>
    </div>
  );
}

function Workspace({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <section className="workspace">
      <div className="workspace-heading">
        <div className="eyebrow">PHISHELL WORKSPACE</div>
        <h1>{title}</h1>
        <p>{subtitle}</p>
      </div>
      <div className="workspace-columns">
        <div className="panel">
          <div className="panel-title">FIELD</div>
          <p className="muted">
            Desktop windows persist above destinations. Runtime bindings remain explicit contracts,
            not UI shortcuts to operating-system privilege.
          </p>
        </div>
        <div className="panel">
          <div className="panel-title">CONTEXT</div>
          <div className="empty-state">Open the command field with Ctrl/⌘ + K.</div>
        </div>
      </div>
    </section>
  );
}

function Center({ view }: { view: View }) {
  if (view === "home") return <Home />;
  const copy: Record<Exclude<View, "home">, [string, string]> = {
    research: [
      "Research",
      "Sources, evidence, notes, synthesis, and provenance in one governed workspace.",
    ],
    build: [
      "Build",
      "Projects, code, tests, artifacts, and execution proposals without authority laundering.",
    ],
    memory: [
      "Memory",
      "Canonical records, semantic retrieval, currentness, lineage, and read admissibility.",
    ],
    ledger: [
      "Reality Ledger",
      "Append-only receipts and bounded read-only projections of system history.",
    ],
    governance: [
      "Governance",
      "Authority, grants, capabilities, effect boundaries, escalations, and control-plane state.",
    ],
    settings: ["Settings", "Operator configuration for the PhiOS environment and Linux substrate."],
  };
  return <Workspace title={copy[view][0]} subtitle={copy[view][1]} />;
}

function WindowBody({ item }: { item: WindowModel }) {
  if (item.id === "ledger-window") {
    return (
      <div className="window-ledger">
        <div>
          <span>shell.window.focus</span>
          <b>RECEIPT</b>
        </div>
        <div>
          <span>authority.execution</span>
          <b>FALSE</b>
        </div>
        <div>
          <span>linux.adapter</span>
          <b>ZERO PRIVILEGE</b>
        </div>
        <p>Projection only. No ledger entry displayed here grants authority.</p>
      </div>
    );
  }

  if (item.id === "system-window") {
    return (
      <>
        <HostObservationPanel />
        <div className="observation-section observation-capabilities">
          <div className="observation-section-title">CAPABILITY BOUNDARY</div>
          <div className="capability-list">
            {linuxServiceAdapter.listCapabilities().map((capability) => (
              <div key={capability.id}>
                <span>{capability.label}</span>
                <small>{capability.consequence}</small>
                <b className={capability.available ? "cap-read" : "cap-blocked"}>
                  {capability.available ? "OBSERVABLE" : "BLOCKED"}
                </b>
              </div>
            ))}
          </div>
        </div>
      </>
    );
  }

  if (item.id === "build-window") {
    return (
      <div className="window-field-grid">
        <article>
          <small>PROPOSAL</small>
          <b>Compile PhiShell</b>
          <p>Build capability can be described without inheriting execution authority.</p>
        </article>
        <article>
          <small>BOUNDARY</small>
          <b>Effect broker absent</b>
          <p>No privileged Linux effect adapter is attached in v0.4.</p>
        </article>
      </div>
    );
  }

  return (
    <div className="window-field-grid">
      <article>
        <small>ACTIVE THREAD</small>
        <b>PhiOS visual environment</b>
        <p>Window state now behaves like desktop state instead of a static mockup.</p>
      </article>
      <article>
        <small>PROVENANCE</small>
        <b>Typed shell events</b>
        <p>Every desktop transition is represented as an explicit reducer event.</p>
      </article>
    </div>
  );
}

function DesktopWindow({
  item,
  dispatch,
}: {
  item: WindowModel;
  dispatch: (event: ShellEvent) => void;
}) {
  const drag = useRef<{
    pointerId: number;
    startX: number;
    startY: number;
    windowX: number;
    windowY: number;
  } | null>(null);

  if (item.state === "minimized") return null;

  const maximized = item.state === "maximized";
  const style = maximized
    ? { left: "0%", top: "0%", width: "100%", height: "100%", zIndex: item.z }
    : {
        left: `${item.x}%`,
        top: `${item.y}%`,
        width: `${item.width}%`,
        height: `${item.height}%`,
        zIndex: item.z,
      };

  return (
    <section
      className={maximized ? "desktop-window maximized" : "desktop-window"}
      style={style}
      onPointerDown={() => dispatch({ type: "FOCUS_WINDOW", id: item.id })}
    >
      <header
        className="window-titlebar"
        onDoubleClick={() => dispatch({ type: "TOGGLE_MAXIMIZE_WINDOW", id: item.id })}
        onPointerDown={(event) => {
          if (maximized) return;
          drag.current = {
            pointerId: event.pointerId,
            startX: event.clientX,
            startY: event.clientY,
            windowX: item.x,
            windowY: item.y,
          };
          event.currentTarget.setPointerCapture(event.pointerId);
        }}
        onPointerMove={(event) => {
          const active = drag.current;
          if (!active || active.pointerId !== event.pointerId) return;
          dispatch({
            type: "MOVE_WINDOW",
            id: item.id,
            x: active.windowX + ((event.clientX - active.startX) / globalThis.innerWidth) * 100,
            y: active.windowY + ((event.clientY - active.startY) / globalThis.innerHeight) * 100,
          });
        }}
        onPointerUp={(event) => {
          if (drag.current?.pointerId === event.pointerId) {
            drag.current = null;
            event.currentTarget.releasePointerCapture(event.pointerId);
          }
        }}
      >
        <div className="window-identity">
          <span>{item.kind === "system" ? "▤" : "◈"}</span>
          <div>
            <b>{item.title}</b>
            <small>{item.subtitle}</small>
          </div>
        </div>
        <div className="window-controls">
          <button
            aria-label="Minimize"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => dispatch({ type: "MINIMIZE_WINDOW", id: item.id })}
          >
            −
          </button>
          <button
            aria-label="Maximize"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => dispatch({ type: "TOGGLE_MAXIMIZE_WINDOW", id: item.id })}
          >
            □
          </button>
          <button
            aria-label="Close"
            onPointerDown={(event) => event.stopPropagation()}
            onClick={() => dispatch({ type: "CLOSE_WINDOW", id: item.id })}
          >
            ×
          </button>
        </div>
      </header>
      <div className="window-content">
        <div className="window-boundary">
          ADVISORY / VISUAL STATE · EXECUTION AUTHORITY FALSE
        </div>
        <WindowBody item={item} />
      </div>
    </section>
  );
}

function DesktopLayer({
  windows,
  dispatch,
}: {
  windows: WindowModel[];
  dispatch: (event: ShellEvent) => void;
}) {
  return (
    <div className="desktop-layer" aria-label="PhiShell desktop windows">
      {[...windows]
        .sort((a, b) => a.z - b.z)
        .map((item) => (
          <DesktopWindow key={item.id} item={item} dispatch={dispatch} />
        ))}
    </div>
  );
}

function PhiVessel() {
  const [mode, setMode] = useState<VesselMode>("chat");
  return (
    <aside className="vessel">
      <div className="vessel-head">
        <div className="vessel-mark">◉</div>
        <div>
          <b>PhiVessel</b>
          <small>Always here. Thinking with you.</small>
        </div>
      </div>
      <div className="vessel-tabs">
        {(["chat", "dream", "translate", "build", "ledger"] as VesselMode[]).map((entry) => (
          <button
            className={mode === entry ? "active" : ""}
            key={entry}
            onClick={() => setMode(entry)}
          >
            {entry}
          </button>
        ))}
      </div>
      <div className="vessel-body">
        <small className="mode-label">{mode.toUpperCase()} MODE · ADVISORY</small>
        <h2>Local Linux bridge online.</h2>
        <p>PhiShell can now receive validated live host observations through its same-origin loopback transport.</p>
        <p className="muted">
          The intelligence layer may propose an action. Proposal is still not authority.
        </p>
        <div className="quick-actions">
          <button>Analyze active workspace</button>
          <button>Search governed memory</button>
          <button>Prepare build proposal</button>
          <button>Explain ledger receipt</button>
        </div>
      </div>
      <div className="prompt">
        <input placeholder="Ask PhiVessel anything…" />
        <button>→</button>
      </div>
    </aside>
  );
}

function StartMenu({
  close,
  openCommand,
  requestPower,
}: {
  close: () => void;
  openCommand: () => void;
  requestPower: () => void;
}) {
  return (
    <div className="start-menu">
      <div className="start-title">
        <b>Φ</b>
        <span>PhiOS</span>
        <button onClick={close}>×</button>
      </div>
      <button className="start-search" onClick={openCommand}>
        ⌕ Search apps, memory, windows, commands…
      </button>
      <div className="start-section">PINNED</div>
      <div className="start-apps">
        {apps.slice(0, 6).map(([name, icon]) => (
          <button key={name}>
            <span>{icon}</span>
            {name}
          </button>
        ))}
      </div>
      <div className="start-footer">
        <span>Operator</span>
        <div>
          <button>Lock</button>
          <button onClick={requestPower}>Power</button>
        </div>
      </div>
    </div>
  );
}

function CommandOverlay({
  query,
  dispatch,
}: {
  query: string;
  dispatch: (event: ShellEvent) => void;
}) {
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return commands;
    return commands.filter(
      (item) =>
        item.label.toLowerCase().includes(needle) || item.detail.toLowerCase().includes(needle),
    );
  }, [query]);

  function run(item: CommandItem) {
    if (item.action.type === "open-view") {
      dispatch({ type: "SET_VIEW", view: item.action.view });
    } else if (item.action.type === "open-window") {
      const template = windowTemplates[item.action.windowId];
      if (template) dispatch({ type: "OPEN_WINDOW", window: template });
    } else {
      dispatch({
        type: "REQUEST_AUTHORITY",
        request: authorityRequest(
          item.action.capability,
          "Requested through the PhiShell universal command overlay.",
        ),
      });
    }
    dispatch({ type: "CLOSE_COMMAND" });
  }

  return (
    <div className="overlay-scrim" onPointerDown={() => dispatch({ type: "CLOSE_COMMAND" })}>
      <section className="command-overlay" onPointerDown={(event) => event.stopPropagation()}>
        <div className="command-input-row">
          <span>⌕</span>
          <input
            autoFocus
            value={query}
            onChange={(event) =>
              dispatch({ type: "SET_COMMAND_QUERY", query: event.currentTarget.value })
            }
            placeholder="Search PhiOS…"
          />
          <kbd>ESC</kbd>
        </div>
        <div className="command-results">
          {filtered.map((item) => (
            <button key={item.id} onClick={() => run(item)}>
              <span>
                <b>{item.label}</b>
                <small>{item.detail}</small>
              </span>
              <em>{item.action.type.replaceAll("-", " ")}</em>
            </button>
          ))}
          {filtered.length === 0 && <div className="command-empty">No matching governed intent.</div>}
        </div>
        <footer>
          <span>Search discovers capabilities.</span>
          <b>Discovery never grants authority.</b>
        </footer>
      </section>
    </div>
  );
}

function AuthorityDialog({
  request,
  receipt,
  dispatch,
  approve,
  clear,
}: {
  request: AuthorityRequest;
  receipt: LinuxServiceReceipt | null;
  dispatch: (event: ShellEvent) => void;
  approve: () => void;
  clear: () => void;
}) {
  return (
    <div className="overlay-scrim authority-scrim">
      <section className="authority-dialog">
        <div className="authority-heading">
          <div>
            <small>AUTHORITY REQUEST</small>
            <h2>{request.capability}</h2>
          </div>
          <span>◇</span>
        </div>

        <dl>
          <div>
            <dt>Requested by</dt>
            <dd>{request.requestedBy}</dd>
          </div>
          <div>
            <dt>Scope</dt>
            <dd>{request.scope}</dd>
          </div>
          <div>
            <dt>Reason</dt>
            <dd>{request.reason}</dd>
          </div>
          <div>
            <dt>Execution authority</dt>
            <dd className="false-value">FALSE</dd>
          </div>
        </dl>

        {request.decision === "pending" ? (
          <>
            <div className="authority-warning">
              Approval below records operator intent only. PhiShell v0.4 has no privileged effect
              broker and cannot execute this Linux operation.
            </div>
            <div className="authority-actions">
              <button onClick={() => dispatch({ type: "RESOLVE_AUTHORITY", decision: "denied" })}>
                Deny
              </button>
              <button className="approve-intent" onClick={approve}>
                Approve intent only
              </button>
            </div>
          </>
        ) : (
          <>
            <div className={request.decision === "denied" ? "receipt denied" : "receipt"}>
              <small>DECISION</small>
              <b>{request.decision.replace("_", " ").toUpperCase()}</b>
              <span>execution_authority = false</span>
              {receipt && <span>effect_performed = {String(receipt.effectPerformed)}</span>}
              {receipt && <p>{receipt.reason}</p>}
            </div>
            <div className="authority-actions">
              <button className="approve-intent" onClick={clear}>
                Close receipt
              </button>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

export function PhiShell() {
  const [state, dispatch] = useReducer(shellReducer, INITIAL_SHELL_STATE);
  const [start, setStart] = useState(false);
  const [adapterReceipt, setAdapterReceipt] = useState<LinuxServiceReceipt | null>(null);
  const title = useMemo(
    () => nav.find((item) => item.id === state.view)?.label ?? "Home",
    [state.view],
  );

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        dispatch({ type: "OPEN_COMMAND" });
      }
      if (event.key === "Escape" && state.commandOpen) {
        dispatch({ type: "CLOSE_COMMAND" });
      }
    };
    globalThis.addEventListener("keydown", handleKey);
    return () => globalThis.removeEventListener("keydown", handleKey);
  }, [state.commandOpen]);

  const requestPower = () => {
    setStart(false);
    setAdapterReceipt(null);
    dispatch({
      type: "REQUEST_AUTHORITY",
      request: authorityRequest("system.power", "Power was selected from the Phi Start menu."),
    });
  };

  const approveAuthority = async () => {
    const request = state.authorityRequest;
    if (!request) return;

    dispatch({ type: "RESOLVE_AUTHORITY", decision: "approved_intent" });
    const receipt = await linuxServiceAdapter.request({
      id: `intent:${request.id}`,
      capability: request.capability,
      scope: request.scope,
      requestedBy: request.requestedBy,
    });
    setAdapterReceipt(receipt);
  };

  return (
    <div className="shell">
      <TopBar />
      <Rail view={state.view} dispatch={dispatch} />
      <main className="field">
        <div className="field-title">
          <span>{title}</span>
          <small>PhiShell v0.4 · loopback observation transport · execution authority false</small>
        </div>
        <Center view={state.view} />
        <DesktopLayer windows={state.windows} dispatch={dispatch} />
      </main>
      <PhiVessel />
      <footer className="commandbar">
        <button className="start-button" onClick={() => setStart(!start)}>
          <b>Φ</b>
          <span>Start</span>
        </button>
        <button className="search-button" onClick={() => dispatch({ type: "OPEN_COMMAND" })}>
          ⌕ <span>Search anything…</span>
        </button>
        <div className="task-icons">
          {state.windows.map((item) => (
            <button
              key={item.id}
              className={item.state === "minimized" ? "task-window minimized" : "task-window"}
              title={item.title}
              onClick={() =>
                dispatch({
                  type: item.state === "minimized" ? "RESTORE_WINDOW" : "FOCUS_WINDOW",
                  id: item.id,
                })
              }
            >
              {item.kind === "system" ? "▤" : "◈"}
            </button>
          ))}
        </div>
        <div className="motto">LEDGER ABOVE EGO</div>
        <div className="tray">
          <span>NET</span>
          <span>VOL</span>
          <span>LOCAL</span>
          <b>AUTH 0</b>
        </div>
      </footer>

      {start && (
        <StartMenu
          close={() => setStart(false)}
          openCommand={() => {
            setStart(false);
            dispatch({ type: "OPEN_COMMAND" });
          }}
          requestPower={requestPower}
        />
      )}

      {state.commandOpen && <CommandOverlay query={state.commandQuery} dispatch={dispatch} />}

      {state.authorityRequest && (
        <AuthorityDialog
          request={state.authorityRequest}
          receipt={adapterReceipt}
          dispatch={dispatch}
          approve={approveAuthority}
          clear={() => {
            setAdapterReceipt(null);
            dispatch({ type: "CLEAR_AUTHORITY" });
          }}
        />
      )}
    </div>
  );
}
