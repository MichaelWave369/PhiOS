const TOP_LEVEL_KEYS = [
  "adapter","availability","capturedAt","distro","effectPerformed","executionAuthority",
  "packageLimit","packages","readOnly","reason","schemaVersion","source","totalInstalledPackageCount"
];
const PACKAGE_KEYS = ["architecture","essential","name","version"];

function isRecord(v){return typeof v==="object"&&v!==null&&!Array.isArray(v)}
function exactKeys(v,e){return isRecord(v)&&Object.keys(v).sort().join("\0")=== [...e].sort().join("\0")}
function bounded(v,m){return typeof v==="string"&&v.length>0&&v.length<=m}
function nonneg(v){return Number.isInteger(v)&&v>=0}

export function validatePackageObservation(o){
  const errors=[];
  if(!exactKeys(o,TOP_LEVEL_KEYS)) return {ok:false,errors:["top-level package fields invalid"]};
  if(o.schemaVersion!=="phios.package-observation.v1") errors.push("schemaVersion");
  if(o.source!=="dpkg-status-file") errors.push("source");
  if(o.adapter!=="debian-dpkg-status") errors.push("adapter");
  if(!bounded(o.capturedAt,64)||Number.isNaN(Date.parse(o.capturedAt))) errors.push("capturedAt");
  if(!["available","unavailable"].includes(o.availability)) errors.push("availability");
  if(o.reason!==null&&!["non-linux-host","os-release-unavailable","unsupported-package-database","package-database-unavailable"].includes(o.reason)) errors.push("reason");
  if(o.availability==="available"&&o.reason!==null) errors.push("available reason");
  if(o.availability==="unavailable"&&o.reason===null) errors.push("unavailable reason");
  if(o.packageLimit!==64) errors.push("packageLimit");
  if(o.readOnly!==true||o.executionAuthority!==false||o.effectPerformed!==false) errors.push("authority");
  if(!nonneg(o.totalInstalledPackageCount)) errors.push("count");
  if(!(o.distro===null||(exactKeys(o.distro,["id","name"])&&bounded(o.distro.id,64)&&bounded(o.distro.name,160)))) errors.push("distro");
  if(!Array.isArray(o.packages)||o.packages.length>64||o.packages.length>o.totalInstalledPackageCount) errors.push("packages");
  else for(const p of o.packages){
    if(!exactKeys(p,PACKAGE_KEYS)||!bounded(p.name,128)||!bounded(p.version,256)||!bounded(p.architecture,64)||typeof p.essential!=="boolean"){errors.push("package row");break}
  }
  return {ok:errors.length===0,errors};
}
export function assertValidPackageObservation(o){
  const r=validatePackageObservation(o);
  if(!r.ok) throw new Error(`invalid package observation: ${r.errors.join("; ")}`);
  return o;
}
