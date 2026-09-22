import {useCallback,useEffect,useState} from "react";
import {packageObservationProvider,type PackageObservationSnapshot} from "../shell/packageObservation";
export function PackageObservationPanel(){
  const [o,setO]=useState<PackageObservationSnapshot|null>(null); const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{setBusy(true);try{setO(await packageObservationProvider.observe())}finally{setBusy(false)}},[]);
  useEffect(()=>{void refresh()},[refresh]);
  if(!o) return <div className="observation-loading">Reading package inventory…</div>;
  const live=o.source==="dpkg-status-file";
  return <section className="package-observation">
    <div className="service-observation-head"><div><small>PACKAGE INVENTORY · READ ONLY</small><b>{live?"DPKG STATUS DATABASE":"FIXTURE FALLBACK"}</b></div><div className="service-observation-actions"><span>{o.totalInstalledPackageCount} INSTALLED</span><button onClick={()=>void refresh()} disabled={busy}>{busy?"Reading…":"Refresh"}</button></div></div>
    {o.availability==="unavailable"&&<div className="observation-fixture-warning">Package observation unavailable{o.reason?" · "+o.reason:""}. No package state is inferred.</div>}
    {o.distro&&<div className="package-distro"><span>DISTRO</span><b>{o.distro.name}</b><em>{o.adapter}</em></div>}
    <div className="package-table"><div className="package-row package-header"><span>PACKAGE</span><span>VERSION</span><span>ARCH</span><span>ESSENTIAL</span></div>{o.packages.map(p=><div className="package-row" key={p.name+":"+p.architecture}><b>{p.name}</b><code>{p.version}</code><span>{p.architecture}</span><em>{p.essential?"YES":"NO"}</em></div>)}</div>
    <div className="observation-receipt"><span>detail_limit = {o.packageLimit}</span><span>descriptions = omitted</span><span>maintainers = omitted</span><span>package_manage = false</span><span>execution_authority = false</span></div>
  </section>
}
