const TOP_KEYS=["availability","block","capturedAt","cpuTopology","drm","effectPerformed","executionAuthority","limits","network","pci","power","readOnly","reason","schemaVersion","source","usb"];
function rec(v){return typeof v==="object"&&v!==null&&!Array.isArray(v)}
function keys(v,e){return rec(v)&&Object.keys(v).sort().join("\0")=== [...e].sort().join("\0")}
function str(v,m){return v===null||(typeof v==="string"&&v.length>0&&v.length<=m)}
function nni(v){return Number.isInteger(v)&&v>=0}
export function validateDeviceObservation(o){
  const e=[];
  if(!keys(o,TOP_KEYS)) return {ok:false,errors:["top-level device fields invalid"]};
  if(o.schemaVersion!=="phios.device-observation.v1") e.push("schema");
  if(o.source!=="linux-sysfs-bounded") e.push("source");
  if(!["available","unavailable"].includes(o.availability)) e.push("availability");
  if(o.availability==="available"&&o.reason!==null) e.push("reason");
  if(o.availability==="unavailable"&&!["non-linux-host","sysfs-unavailable"].includes(o.reason)) e.push("reason");
  if(o.readOnly!==true||o.executionAuthority!==false||o.effectPerformed!==false) e.push("authority");
  const limits={block:16,network:16,pci:16,usb:16,drm:8,power:8};
  if(!keys(o.limits,Object.keys(limits))) e.push("limits");
  else for(const [k,v] of Object.entries(limits)) if(o.limits[k]!==v) e.push("limit "+k);
  if(!keys(o.cpuTopology,["logicalCpuCount","physicalPackageCount","physicalCoreCount"])||!nni(o.cpuTopology.logicalCpuCount)||!nni(o.cpuTopology.physicalPackageCount)||!nni(o.cpuTopology.physicalCoreCount)) e.push("cpuTopology");
  for(const [name,limit] of Object.entries(limits)) if(!Array.isArray(o[name])||o[name].length>limit) e.push(name);
  if(Array.isArray(o.network)) for(const r of o.network) if(!keys(r,["name","type","operState","vendorId","deviceId"])||!str(r.name,128)||!(r.type===null||nni(r.type))||!str(r.operState,32)||!str(r.vendorId,16)||!str(r.deviceId,16)) {e.push("network row");break}
  if(Array.isArray(o.pci)) for(const r of o.pci) if(!keys(r,["slot","vendorId","deviceId","classId"])||!str(r.slot,128)||!str(r.vendorId,16)||!str(r.deviceId,16)||!str(r.classId,16)) {e.push("pci row");break}
  if(Array.isArray(o.usb)) for(const r of o.usb) if(!keys(r,["pathId","vendorId","productId","deviceClass","manufacturer","product"])||!str(r.pathId,128)||!str(r.vendorId,16)||!str(r.productId,16)||!str(r.deviceClass,16)||!str(r.manufacturer,120)||!str(r.product,120)) {e.push("usb row");break}
  if(Array.isArray(o.block)) for(const r of o.block) if(!keys(r,["name","sizeBytes","removable","rotational","vendor","model"])||!str(r.name,128)||!(r.sizeBytes===null||(Number.isSafeInteger(r.sizeBytes)&&r.sizeBytes>=0))||typeof r.removable!=="boolean"||!(r.rotational===null||typeof r.rotational==="boolean")||!str(r.vendor,80)||!str(r.model,120)) {e.push("block row");break}
  if(Array.isArray(o.drm)) for(const r of o.drm) if(!keys(r,["name","vendorId","deviceId"])||!str(r.name,128)||!str(r.vendorId,16)||!str(r.deviceId,16)) {e.push("drm row");break}
  if(Array.isArray(o.power)) for(const r of o.power) if(!keys(r,["name","type","manufacturer","model"])||!str(r.name,128)||!str(r.type,64)||!str(r.manufacturer,120)||!str(r.model,120)) {e.push("power row");break}
  return {ok:e.length===0,errors:e};
}
export function assertValidDeviceObservation(o){const r=validateDeviceObservation(o);if(!r.ok) throw new Error("invalid device observation: "+r.errors.join("; "));return o}
