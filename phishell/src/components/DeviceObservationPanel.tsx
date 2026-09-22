import {useCallback,useEffect,useState} from "react";
import {deviceObservationProvider,type DeviceObservationSnapshot} from "../shell/deviceObservation";
function gib(bytes:number|null){return bytes===null?"n/a":(bytes/1024**3).toFixed(1)+" GiB"}
export function DeviceObservationPanel(){
  const [o,setO]=useState<DeviceObservationSnapshot|null>(null);const [busy,setBusy]=useState(false);
  const refresh=useCallback(async()=>{setBusy(true);try{setO(await deviceObservationProvider.observe())}finally{setBusy(false)}},[]);
  useEffect(()=>{void refresh()},[refresh]);
  if(!o)return <div className="observation-loading">Reading hardware inventory…</div>;
  const live=o.source==="linux-sysfs-bounded";
  return <section className="device-observation">
    <div className="service-observation-head"><div><small>HARDWARE INVENTORY · SYSFS READ ONLY</small><b>{live?"LINUX SYSFS / LIVE LOCAL":"FIXTURE FALLBACK"}</b></div><div className="service-observation-actions"><span>{o.pci.length+o.usb.length+o.block.length+o.network.length} DEVICES</span><button onClick={()=>void refresh()} disabled={busy}>{busy?"Reading…":"Refresh"}</button></div></div>
    {o.availability==="unavailable"&&<div className="observation-fixture-warning">Device observation unavailable{o.reason?" · "+o.reason:""}. No hardware state is inferred.</div>}
    <div className="device-summary"><span>logical cpu {o.cpuTopology.logicalCpuCount}</span><span>cores {o.cpuTopology.physicalCoreCount}</span><span>pci {o.pci.length}</span><span>usb {o.usb.length}</span><span>block {o.block.length}</span><span>net {o.network.length}</span><span>drm {o.drm.length}</span><span>power {o.power.length}</span></div>
    <div className="device-columns">
      <div><h4>BLOCK</h4>{o.block.map(d=><div className="device-row" key={d.name}><b>{d.name}</b><span>{d.vendor??""} {d.model??""}</span><em>{gib(d.sizeBytes)}{d.removable?" · REMOVABLE":""}</em></div>)}</div>
      <div><h4>PCI / GPU</h4>{o.pci.map(d=><div className="device-row" key={d.slot}><b>{d.slot}</b><span>{d.vendorId}:{d.deviceId}</span><em>{d.classId}</em></div>)}{o.drm.map(d=><div className="device-row" key={d.name}><b>{d.name}</b><span>{d.vendorId??"vendor n/a"}</span><em>{d.deviceId??"device n/a"}</em></div>)}</div>
      <div><h4>USB</h4>{o.usb.map(d=><div className="device-row" key={d.pathId}><b>{d.product??d.pathId}</b><span>{d.manufacturer??"unknown"}</span><em>{d.vendorId}:{d.productId}</em></div>)}</div>
      <div><h4>NETWORK / POWER</h4>{o.network.map(d=><div className="device-row" key={d.name}><b>{d.name}</b><span>{d.operState??"state n/a"}</span><em>{d.vendorId??"vendor n/a"}</em></div>)}{o.power.map(d=><div className="device-row" key={d.name}><b>{d.name}</b><span>{d.manufacturer??d.type??"power"}</span><em>{d.model??""}</em></div>)}</div>
    </div>
    <div className="observation-receipt"><span>sysfs = read_only</span><span>serials = omitted</span><span>mac = omitted</span><span>driver_control = false</span><span>execution_authority = false</span><span>effect_performed = false</span></div>
  </section>
}
