export interface DeviceLimits { block:16; network:16; pci:16; usb:16; drm:8; power:8 }
export interface CpuTopology { logicalCpuCount:number; physicalPackageCount:number; physicalCoreCount:number }
export interface BlockDevice { name:string; sizeBytes:number|null; removable:boolean; rotational:boolean|null; vendor:string|null; model:string|null }
export interface NetworkDevice { name:string; type:number|null; operState:string|null; vendorId:string|null; deviceId:string|null }
export interface PciDevice { slot:string; vendorId:string; deviceId:string; classId:string }
export interface UsbDevice { pathId:string; vendorId:string; productId:string; deviceClass:string|null; manufacturer:string|null; product:string|null }
export interface DrmDevice { name:string; vendorId:string|null; deviceId:string|null }
export interface PowerDevice { name:string; type:string|null; manufacturer:string|null; model:string|null }
export interface DeviceObservationSnapshot {
  schemaVersion:"phios.device-observation.v1"; source:"linux-sysfs-bounded"|"fixture"; capturedAt:string;
  availability:"available"|"unavailable"; reason:null|"non-linux-host"|"sysfs-unavailable"|"transport-unavailable";
  readOnly:true; executionAuthority:false; effectPerformed:false; limits:DeviceLimits; cpuTopology:CpuTopology;
  block:BlockDevice[]; network:NetworkDevice[]; pci:PciDevice[]; usb:UsbDevice[]; drm:DrmDevice[]; power:PowerDevice[];
}
export const FIXTURE_DEVICE_OBSERVATION:DeviceObservationSnapshot={
  schemaVersion:"phios.device-observation.v1",source:"fixture",capturedAt:"2026-09-21T00:00:00.000Z",availability:"unavailable",reason:"transport-unavailable",
  readOnly:true,executionAuthority:false,effectPerformed:false,limits:{block:16,network:16,pci:16,usb:16,drm:8,power:8},
  cpuTopology:{logicalCpuCount:0,physicalPackageCount:0,physicalCoreCount:0},block:[],network:[],pci:[],usb:[],drm:[],power:[]
};
function rec(v:unknown):v is Record<string,unknown>{return typeof v==="object"&&v!==null&&!Array.isArray(v)}
function int(v:unknown):v is number{return typeof v==="number"&&Number.isInteger(v)}
function num(v:unknown):v is number{return typeof v==="number"&&Number.isFinite(v)}
function exact(v:Record<string,unknown>,keys:string[]){return Object.keys(v).sort().join("\0")===[...keys].sort().join("\0")}
function nullableString(v:unknown,max:number){return v===null||(typeof v==="string"&&v.length>0&&v.length<=max)}
function row(v:unknown,keys:string[]){return rec(v)&&exact(v,keys)}
function native(v:unknown):v is DeviceObservationSnapshot{
  if(!rec(v)||v.schemaVersion!=="phios.device-observation.v1"||v.source!=="linux-sysfs-bounded"||typeof v.capturedAt!=="string"||Number.isNaN(Date.parse(v.capturedAt))||
    !["available","unavailable"].includes(String(v.availability))||v.readOnly!==true||v.executionAuthority!==false||v.effectPerformed!==false) return false;
  if(v.availability==="available"&&v.reason!==null) return false;
  if(v.availability==="unavailable"&&!["non-linux-host","sysfs-unavailable"].includes(String(v.reason))) return false;
  if(!rec(v.limits)||v.limits.block!==16||v.limits.network!==16||v.limits.pci!==16||v.limits.usb!==16||v.limits.drm!==8||v.limits.power!==8) return false;
  if(!rec(v.cpuTopology)||!int(v.cpuTopology.logicalCpuCount)||v.cpuTopology.logicalCpuCount<0||!int(v.cpuTopology.physicalPackageCount)||v.cpuTopology.physicalPackageCount<0||!int(v.cpuTopology.physicalCoreCount)||v.cpuTopology.physicalCoreCount<0) return false;
  if(!Array.isArray(v.block)||v.block.length>16||!Array.isArray(v.network)||v.network.length>16||!Array.isArray(v.pci)||v.pci.length>16||!Array.isArray(v.usb)||v.usb.length>16||!Array.isArray(v.drm)||v.drm.length>8||!Array.isArray(v.power)||v.power.length>8) return false;
  if(!v.block.every(x=>row(x,["name","sizeBytes","removable","rotational","vendor","model"])&&typeof x.name==="string"&&(x.sizeBytes===null||(num(x.sizeBytes)&&x.sizeBytes>=0))&&typeof x.removable==="boolean"&&(x.rotational===null||typeof x.rotational==="boolean")&&nullableString(x.vendor,80)&&nullableString(x.model,120))) return false;
  if(!v.network.every(x=>row(x,["name","type","operState","vendorId","deviceId"])&&typeof x.name==="string"&&(x.type===null||(int(x.type)&&x.type>=0))&&nullableString(x.operState,32)&&nullableString(x.vendorId,16)&&nullableString(x.deviceId,16)&&!("mac" in x)&&!("address" in x))) return false;
  if(!v.pci.every(x=>row(x,["slot","vendorId","deviceId","classId"])&&typeof x.slot==="string"&&typeof x.vendorId==="string"&&typeof x.deviceId==="string"&&typeof x.classId==="string")) return false;
  if(!v.usb.every(x=>row(x,["pathId","vendorId","productId","deviceClass","manufacturer","product"])&&typeof x.pathId==="string"&&typeof x.vendorId==="string"&&typeof x.productId==="string"&&nullableString(x.deviceClass,16)&&nullableString(x.manufacturer,120)&&nullableString(x.product,120)&&!("serial" in x))) return false;
  if(!v.drm.every(x=>row(x,["name","vendorId","deviceId"])&&typeof x.name==="string"&&nullableString(x.vendorId,16)&&nullableString(x.deviceId,16))) return false;
  if(!v.power.every(x=>row(x,["name","type","manufacturer","model"])&&typeof x.name==="string"&&nullableString(x.type,64)&&nullableString(x.manufacturer,120)&&nullableString(x.model,120)&&!("serial" in x))) return false;
  return true;
}
export function isDeviceTransportEnvelope(v:unknown,maxAgeMs=5000){
  if(!rec(v)) return false;
  return v.transportSchemaVersion==="phios.device-transport.v1"&&v.transport==="loopback-http"&&v.transportIdentity==="phishell-local-observer"&&v.localOnly===true&&v.readOnly===true&&v.executionAuthority===false&&v.effectPerformed===false&&typeof v.servedAt==="string"&&!Number.isNaN(Date.parse(v.servedAt))&&num(v.snapshotAgeMs)&&v.snapshotAgeMs>=0&&v.snapshotAgeMs<=maxAgeMs&&native(v.observation);
}
export function createDeviceObservationProvider({fetcher=globalThis.fetch.bind(globalThis),fallback=FIXTURE_DEVICE_OBSERVATION,timeoutMs=1500,maxAgeMs=5000}:{fetcher?:typeof fetch;fallback?:DeviceObservationSnapshot;timeoutMs?:number;maxAgeMs?:number}={}){
  return {readOnly:true as const,executionAuthority:false as const,async observe():Promise<DeviceObservationSnapshot>{
    const controller=new AbortController();const timeout=globalThis.setTimeout(()=>controller.abort(),timeoutMs);
    try{const response=await fetcher("/api/v1/device-observation",{method:"GET",cache:"no-store",credentials:"same-origin",headers:{accept:"application/json"},signal:controller.signal});if(!response.ok)return fallback;const envelope:unknown=await response.json();if(!isDeviceTransportEnvelope(envelope,maxAgeMs)||!rec(envelope))return fallback;return envelope.observation as DeviceObservationSnapshot}catch{return fallback}finally{globalThis.clearTimeout(timeout)}
  }};
}
export const deviceObservationProvider=createDeviceObservationProvider();
