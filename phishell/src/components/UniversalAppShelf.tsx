import { useEffect, useMemo, useRef, useState, type ChangeEvent } from "react";
import catalogJson from "../data/public-repo-catalog.v1.json";

interface PublicRepo {
  id: string;
  name: string;
  repository: string;
  description: string;
  declared_homepage: string;
  language: string | null;
  availability: "source_only";
}
interface PublicCatalog {
  schema: string;
  provenance: { owner: string; scope: string; complete: boolean; source_blob_sha: string; snapshot_fetched_at: string };
  policy: { automatic_install: boolean; automatic_launch: boolean; review_required: boolean };
  apps: PublicRepo[];
}
interface ShelfApi {
  LIMIT: number;
  MAX_BYTES: number;
  catalogMap: (c: PublicCatalog) => Map<string, PublicRepo>;
  normalize: (ids: string[], c: PublicCatalog) => string[];
  pin: (ids: string[], id: string, c: PublicCatalog) => string[];
  unpin: (ids: string[], id: string, c: PublicCatalog) => string[];
  move: (ids: string[], id: string, offset: number, c: PublicCatalog) => string[];
  packet: (ids: string[], c: PublicCatalog) => unknown;
  parse: (text: string, c: PublicCatalog) => string[];
  badge: (entry: PublicRepo) => string;
}
const CATALOG = catalogJson as PublicCatalog;
const STORAGE_KEY = "phishell.source-shelf.r3";

function getContract(): { api: ShelfApi; sources: Map<string, PublicRepo> } | null {
  const api = (globalThis as typeof globalThis & { PhiShelf?: ShelfApi }).PhiShelf;
  if (!api) return null;
  try {
    const sources = api.catalogMap(CATALOG);
    if (sources.size !== CATALOG.apps.length) return null;
    return { api, sources };
  } catch {
    return null;
  }
}

/**
 * Runs in the existing non-privileged PhiShell web rendering context. Pinned
 * sources are NOT installed Linux apps, installer proposals or execution grants.
 * The operator transfers JSON by hand; no OS host API or remote fetch is used.
 */
export function UniversalAppShelf() {
  const contract = useMemo(getContract, []);
  const [pinned, setPinned] = useState<string[]>([]);
  const [status, setStatus] = useState("Local browser storage · no remote synchronization");
  const [search, setSearch] = useState("");
  const [shown, setShown] = useState(20);
  const fileInput = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (!contract) {
      setStatus("Portable shelf contract or public catalog unavailable; no native actions permitted.");
      return;
    }
    try {
      const stored = globalThis.localStorage.getItem(STORAGE_KEY);
      if (stored) setPinned(contract.api.parse(stored, CATALOG));
    } catch {
      setStatus("Local shelf storage unavailable/invalid. Session-only bookmarks; export to preserve.");
    }
  }, [contract]);

  const matches = useMemo(() => {
    const needle = search.trim().toLowerCase().slice(0, 100);
    return CATALOG.apps.filter((entry) =>
      entry.name.toLowerCase().includes(needle) ||
      entry.description.toLowerCase().includes(needle)
    );
  }, [search]);

  function update(next: string[]) {
    if (!contract) return;
    try {
      const safe = contract.api.normalize(next, CATALOG);
      setPinned(safe);
      try {
        globalThis.localStorage.setItem(STORAGE_KEY, JSON.stringify(contract.api.packet(safe, CATALOG)));
        setStatus(safe.length + " source bookmarks stored locally; no apps installed.");
      } catch {
        setStatus("Session-only: storage refused; use Export to preserve source bookmarks.");
      }
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Invalid shelf operation.");
    }
  }

  function exportShelf() {
    if (!contract) return;
    try {
      const contents = JSON.stringify(contract.api.packet(pinned, CATALOG), null, 2);
      const url = URL.createObjectURL(new Blob([contents], { type: "application/json" }));
      const a = document.createElement("a");
      a.href = url;
      a.download = "phios-app-shelf-r2.json";
      document.body.append(a);
      a.click();
      a.remove();
      globalThis.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setStatus("Portable source-only JSON exported. This is not a package or credential.");
    } catch {
      setStatus("Export unavailable on this session.");
    }
  }

  async function importShelf(event: ChangeEvent<HTMLInputElement>) {
    const file = event.currentTarget.files?.[0];
    event.currentTarget.value = "";
    if (!file || !contract) return;
    if (file.size > contract.api.MAX_BYTES) {
      setStatus("Import refused: shelf exceeds 16 KiB.");
      return;
    }
    try {
      const imported = contract.api.parse(await file.text(), CATALOG);
      if (!globalThis.confirm(
        "Replace your " + pinned.length + " local public-source pins with " + imported.length +
        " imported pins? Existing native apps and privileges will be unaffected."
      )) return;
      update(imported);
    } catch (error) {
      setStatus("Import refused: " + (error instanceof Error ? error.message : "bad shelf JSON"));
    }
  }

  if (!contract) return (
    <section className="native-universal-shelf">
      <div className="panel-title">UNIVERSAL APP SHELF · NOT CONNECTED</div>
      <p role="status">Pinned source data unavailable. No install or launch permissions granted.</p>
    </section>
  );

  const { api, sources } = contract;
  return (
    <section className="native-universal-shelf" aria-labelledby="native-shelf-title">
      <div className="panel-title">Φ UNIVERSAL SHELL R3 · SOURCE BOOKMARKS</div>
      <h2 id="native-shelf-title">My App Shelf</h2>
      <p>Same portable source IDs as PhiOS Web and Mobile PWA. This PhiShell desktop stores only local bookmarks, not installed Linux apps. No automatic sync.</p>
      <div className="native-shelf-actions">
        <button type="button" onClick={exportShelf}>Export shelf JSON</button>
        <button type="button" onClick={() => fileInput.current?.click()}>Import shelf JSON</button>
        <input ref={fileInput} type="file" accept=".json,application/json" className="native-shelf-file" aria-label="Choose portable PhiOS shelf JSON" onChange={(event) => { void importShelf(event); }} />
      </div>
      <p className="native-shelf-status" role="status">{pinned.length} / {api.LIMIT} pinned public sources · {status}</p>
      <div className="native-shelf-pins" role="list" aria-label="Pinned public source projects">
        {pinned.length === 0 && <p className="muted">Nothing pinned yet. Search a public project below and choose Pin source.</p>}
        {pinned.map((id, index) => {
          const entry = sources.get(id);
          if (!entry) return null;
          return <article className="native-shelf-item" role="listitem" key={id}>
            <div><strong>{entry.name}</strong><small>{api.badge(entry)}</small>
              <a href={entry.repository} target="_blank" rel="noopener noreferrer">View GitHub source ↗</a>
            </div>
            <div className="native-shelf-order">
              <button type="button" disabled={index === 0} aria-label={"Move " + entry.name + " up"} onClick={() => update(api.move(pinned, id, -1, CATALOG))}>↑</button>
              <button type="button" disabled={index === pinned.length - 1} aria-label={"Move " + entry.name + " down"} onClick={() => update(api.move(pinned, id, 1, CATALOG))}>↓</button>
              <button type="button" aria-label={"Unpin " + entry.name} onClick={() => update(api.unpin(pinned, id, CATALOG))}>×</button>
            </div>
          </article>;
        })}
      </div>
      <h3>Find public sources</h3>
      <label className="native-shelf-search">Search public catalog
        <input value={search} maxLength={100} onChange={(event) => { setSearch(event.currentTarget.value); setShown(20); }} placeholder="Repository name or description" />
      </label>
      <p className="native-shelf-status">{matches.length} of {CATALOG.apps.length} public sources · dated {CATALOG.provenance.snapshot_fetched_at}. Sites are unverified.</p>
      <div className="native-shelf-results" role="list" aria-label="Public project discovery">
        {matches.slice(0, shown).map((entry) =>
          <article role="listitem" className="native-shelf-item" key={entry.id}>
            <div><strong>{entry.name}</strong><small>{api.badge(entry)}</small><p>{entry.description || "No description supplied"}</p>
              <a href={entry.repository} target="_blank" rel="noopener noreferrer">View source ↗</a>
            </div>
            <button type="button" aria-pressed={pinned.includes(entry.id)}
              onClick={() => update(pinned.includes(entry.id) ? api.unpin(pinned, entry.id, CATALOG) : api.pin(pinned, entry.id, CATALOG))}>
              {pinned.includes(entry.id) ? "Unpin" : "Pin source"}
            </button>
          </article>
        )}
      </div>
      {shown < matches.length && <button type="button" onClick={() => setShown((count) => count + 20)}>Show more public sources</button>}
      <p className="muted">Capability ≠ authority. Pinning a repository never downloads, installs, launches or approves its code. A declared site URL is not proof of a working Web app.</p>
    </section>
  );
}
