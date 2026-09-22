export interface PackageRow {
  name: string;
  version: string;
  architecture: string;
  essential: boolean;
}
export interface PackageObservationSnapshot {
  schemaVersion: "phios.package-observation.v1";
  source: "dpkg-status-file" | "fixture";
  capturedAt: string;
  availability: "available" | "unavailable";
  reason: null | "non-linux-host" | "os-release-unavailable" | "unsupported-package-database" | "package-database-unavailable" | "transport-unavailable";
  adapter: "debian-dpkg-status";
  packageLimit: 64;
  readOnly: true;
  executionAuthority: false;
  effectPerformed: false;
  distro: { id: string; name: string } | null;
  totalInstalledPackageCount: number;
  packages: PackageRow[];
}
export const FIXTURE_PACKAGE_OBSERVATION: PackageObservationSnapshot = {
  schemaVersion:"phios.package-observation.v1",source:"fixture",capturedAt:"2026-09-21T00:00:00.000Z",
  availability:"unavailable",reason:"transport-unavailable",adapter:"debian-dpkg-status",packageLimit:64,
  readOnly:true,executionAuthority:false,effectPerformed:false,distro:null,totalInstalledPackageCount:0,packages:[]
};
function rec(v:unknown):v is Record<string,unknown>{return typeof v==="object"&&v!==null&&!Array.isArray(v)}
function num(v:unknown):v is number{return typeof v==="number"&&Number.isFinite(v)}
function int(v:unknown):v is number{return typeof v==="number"&&Number.isInteger(v)}
function native(v:unknown):v is PackageObservationSnapshot{
  if(!rec(v)) return false;
  if(v.schemaVersion!=="phios.package-observation.v1"||v.source!=="dpkg-status-file"||typeof v.capturedAt!=="string"||Number.isNaN(Date.parse(v.capturedAt))||
    !["available","unavailable"].includes(String(v.availability))||v.adapter!=="debian-dpkg-status"||v.packageLimit!==64||
    v.readOnly!==true||v.executionAuthority!==false||v.effectPerformed!==false||!int(v.totalInstalledPackageCount)||v.totalInstalledPackageCount<0||
    !Array.isArray(v.packages)||v.packages.length>64||v.packages.length>v.totalInstalledPackageCount) return false;
  if(v.availability==="available"&&v.reason!==null) return false;
  if(v.availability==="unavailable"&&!["non-linux-host","os-release-unavailable","unsupported-package-database","package-database-unavailable"].includes(String(v.reason))) return false;
  if(!(v.distro===null||(rec(v.distro)&&typeof v.distro.id==="string"&&typeof v.distro.name==="string"))) return false;
  return v.packages.every(p=>rec(p)&&typeof p.name==="string"&&p.name.length>0&&p.name.length<=128&&typeof p.version==="string"&&p.version.length>0&&p.version.length<=256&&typeof p.architecture==="string"&&p.architecture.length>0&&p.architecture.length<=64&&typeof p.essential==="boolean"&&!["description","maintainer","homepage"].some(k=>k in p));
}
export function isPackageTransportEnvelope(v:unknown,maxAgeMs=5000){
  if(!rec(v)) return false;
  return v.transportSchemaVersion==="phios.package-transport.v1"&&v.transport==="loopback-http"&&v.transportIdentity==="phishell-local-observer"&&
    v.localOnly===true&&v.readOnly===true&&v.executionAuthority===false&&v.effectPerformed===false&&typeof v.servedAt==="string"&&!Number.isNaN(Date.parse(v.servedAt))&&
    num(v.snapshotAgeMs)&&v.snapshotAgeMs>=0&&v.snapshotAgeMs<=maxAgeMs&&native(v.observation);
}
export function createPackageObservationProvider({fetcher=globalThis.fetch.bind(globalThis),fallback=FIXTURE_PACKAGE_OBSERVATION,timeoutMs=1500,maxAgeMs=5000}:{fetcher?:typeof fetch;fallback?:PackageObservationSnapshot;timeoutMs?:number;maxAgeMs?:number}={}){
  return {readOnly:true as const,executionAuthority:false as const,async observe():Promise<PackageObservationSnapshot>{
    const controller=new AbortController(); const timeout=globalThis.setTimeout(()=>controller.abort(),timeoutMs);
    try{
      const response=await fetcher("/api/v1/package-observation",{method:"GET",cache:"no-store",credentials:"same-origin",headers:{accept:"application/json"},signal:controller.signal});
      if(!response.ok) return fallback;
      const envelope:unknown=await response.json();
      if(!isPackageTransportEnvelope(envelope,maxAgeMs)||!rec(envelope)) return fallback;
      return envelope.observation as PackageObservationSnapshot;
    }catch{return fallback}finally{globalThis.clearTimeout(timeout)}
  }};
}
export const packageObservationProvider=createPackageObservationProvider();
