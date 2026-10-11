import {useMemo,useState} from "react";
import publicRepositories from "../ecosystem/public-repos.json";
import appCandidates from "../ecosystem/app-candidates.json";

type Entry=(typeof publicRepositories.entries)[number];
type View="all"|"web";
const publicWebDestinations:Readonly<Record<string,{label:string;url:string}>>={
  SuperPhiVessel:{label:"Vessie React (public website)",url:"https://michaelwave369.github.io/SuperPhiVessel/vessie/"},
  "think-tank":{label:"ThinkTank (public website)",url:"https://michaelwave369.github.io/think-tank/"}
};
const entries=publicRepositories.entries as Entry[];

export function EcosystemCatalog(){
  const [query,setQuery]=useState("");
  const [view,setView]=useState<View>("all");
  const [visible,setVisible]=useState(32);
  const matching=useMemo(()=>{
    const q=query.trim().toLocaleLowerCase();
    return entries.filter(entry=>{
      if(view==="web"&&!Object.hasOwn(publicWebDestinations,entry.name))return false;
      return !q||entry.name.toLocaleLowerCase().includes(q);
    });
  },[query,view]);
  function setSearch(text:string){setQuery(text);setVisible(32)}
  function setFilter(filter:View){setView(filter);setVisible(32)}
  return <section className="ecosystem-catalog" aria-label="MichaelWave369 public repo ecosystem catalog">
    <div className="panel-title">Φ ECOSYSTEM · PUBLIC SOURCE CATALOG</div>
    <p>
      {entries.length} public GitHub repositories are listed in this <strong>offline-bundled snapshot</strong>.
      These entries are <strong>not installed apps</strong>. Listing a repository does not establish
      a runnable application, redistribution license, device compatibility, or execution permission.
    </p>
    <p className="muted">
      Source snapshot comes from public GitHub repository discovery. It may be stale until rebuilt.
      Nothing is fetched from GitHub on opening this screen, and no code is downloaded or executed.
      Actual application installation still requires PhiOS's separate governed intake and launch gates.
    </p>
    <section className="ecosystem-candidates" aria-label="Reviewed PhiOS application candidates">
      <div className="panel-title">FIRST WAVE · TWO GOVERNED APP CANDIDATES</div>
      <p className="muted">These are pinned, schema-checked application <strong>proposals</strong>, not installed apps.
        The established PhiOS App Platform must independently verify a reproducible Linux/offline build,
        dependency and redistribution inventory, exact installed files, desktop entry, and operator launch grant.</p>
      <div className="ecosystem-candidate-list">
        {appCandidates.candidates.map(candidate => <article className="ecosystem-candidate" key={candidate.app_key}>
          <div className="ecosystem-candidate-header">
            <strong>{candidate.manifest.name}</strong>
            <small>REVIEW HELD · NOT INSTALLED</small>
          </div>
          <p>{candidate.manifest.description}</p>
          <dl>
            <div><dt>APP ID</dt><dd>{candidate.manifest.app_id}</dd></div>
            <div><dt>RUNTIME PROPOSAL</dt><dd>{candidate.manifest.entrypoint.runtime} · {candidate.manifest.entrypoint.target}</dd></div>
            <div><dt>SOURCE COMMIT</dt><dd><code>{candidate.source_sha.slice(0,12)}</code> · pinned</dd></div>
            <div><dt>SOURCE BUILD</dt><dd><code>{candidate.source_build.working_directory}</code> → <code>{candidate.source_build.current_output_from_repo_root}</code></dd></div>
            <div><dt>OFFLINE READINESS</dt><dd>Unverified dependency closure, license inventory and bundled frontend</dd></div>
          </dl>
          <p className="muted">Current web bundle base: <code>{candidate.source_build.current_asset_base}</code>;
            PhiOS offline target: <code>{candidate.source_build.required_offline_asset_base}</code>.
            Website availability does not confer local launch or model permissions.</p>
          <a href={candidate.manifest.source.repository_url+"/tree/"+candidate.source_sha} target="_blank" rel="noopener noreferrer">
            REVIEW PINNED SOURCE ↗
          </a>
        </article>)}
      </div>
    </section>
    <div className="ecosystem-controls">
      <label>
        <span>SEARCH REPOSITORIES</span>
        <input aria-label="Search ecosystem repositories" type="search" value={query}
          placeholder="ThinkTank, Domistika, Vessie…" onChange={event=>setSearch(event.target.value)} />
      </label>
      <label>
        <span>CATALOG FILTER</span>
        <select aria-label="Filter ecosystem repositories" value={view}
          onChange={event=>setFilter(event.target.value as View)}>
          <option value="all">ALL PUBLIC SOURCE</option>
          <option value="web">KNOWN WEB DESTINATIONS</option>
        </select>
      </label>
    </div>
    <div className="ecosystem-summary" role="status">
      Showing {Math.min(visible,matching.length)} of {matching.length} matching repositories ·
      installation status: <strong>UNKNOWN / NOT INSTALLED BY THIS CATALOG</strong>
    </div>
    <div className="ecosystem-repos">
      {matching.slice(0,visible).map(entry=>{
        const site=publicWebDestinations[entry.name];
        return <article className="ecosystem-repo" key={entry.name}>
          <div className="ecosystem-repo-name">
            <strong>{entry.name}</strong>
            <small>{site?"WEB LINK AVAILABLE · NOT BUNDLED":"SOURCE LISTING · REVIEW REQUIRED"}</small>
          </div>
          <div className="ecosystem-repo-actions">
            <a href={entry.repository_url} target="_blank" rel="noopener noreferrer"
              aria-label={"Open GitHub source for "+entry.name}>SOURCE ↗</a>
            {site&&<a href={site.url} target="_blank" rel="noopener noreferrer"
              aria-label={"Open public website for "+entry.name}>WEB SITE ↗</a>}
          </div>
        </article>
      })}
      {matching.length===0&&<p className="muted">No matching repositories in this bundled snapshot.</p>}
    </div>
    {visible<matching.length&&<button type="button" className="ecosystem-more"
      onClick={()=>setVisible(v=>Math.min(v+32,matching.length))}>
      SHOW MORE ({matching.length-visible} REMAINING)
    </button>}
    <p className="muted">A public source link opens a website; it is not an executable PhiOS app.
      The real PhiOS v0.57 application pipeline still separately reviews source, licensing, build plans,
      installation and current operator authorization before any local execution.
    </p>
  </section>;
}
