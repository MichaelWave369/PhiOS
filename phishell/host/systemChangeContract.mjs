import {
  HISTORY_LIMIT,
  SUMMARY_METRICS,
  recomputeSystemChangeDigest,
} from "./systemChangeDeriver.mjs";

const TOP_KEYS = [
  "schemaVersion","source","recordedAt","sequence","historyScope","persistent","historyLimit",
  "fromReceiptDigest","toReceiptDigest","fromComposedAt","toComposedAt","elapsedMs","coherence",
  "changedComponentCount","componentChanges","changedSummaryMetricCount","summaryChanges",
  "causeAssigned","severityAssigned","readOnly","executionAuthority","effectPerformed","changeDigest"
];
const COMPONENT_KEYS = [
  "id","fromAvailability","toAvailability","availabilityChanged","fromDigest","toDigest","digestChanged"
];
const SUMMARY_CHANGE_KEYS = ["metric","from","to","delta"];
const COMPONENT_IDS = ["host","services","processes","packages","devices"];

function rec(v){return typeof v==="object"&&v!==null&&!Array.isArray(v)}
function exact(v,e){return rec(v)&&Object.keys(v).sort().join("\0")===[...e].sort().join("\0")}
function ts(v){return typeof v==="string"&&v.length<=64&&!Number.isNaN(Date.parse(v))}
function sha(v){return typeof v==="string"&&/^sha256:[0-9a-f]{64}$/.test(v)}
function nni(v){return Number.isInteger(v)&&v>=0}
function num(v){return typeof v==="number"&&Number.isFinite(v)}

export function validateSystemChangeReceipt(r){
  const errors=[];
  if(!exact(r,TOP_KEYS)) return {ok:false,errors:["top-level change fields invalid"]};
  if(r.schemaVersion!=="phios.system-change.v1") errors.push("schemaVersion");
  if(r.source!=="phios-system-change-deriver") errors.push("source");
  if(!ts(r.recordedAt)||!ts(r.fromComposedAt)||!ts(r.toComposedAt)) errors.push("timestamp");
  if(!Number.isInteger(r.sequence)||r.sequence<1) errors.push("sequence");
  if(r.historyScope!=="session-memory"||r.persistent!==false||r.historyLimit!==HISTORY_LIMIT) errors.push("history");
  if(!sha(r.fromReceiptDigest)||!sha(r.toReceiptDigest)||!sha(r.changeDigest)) errors.push("digest");
  if(!num(r.elapsedMs)||r.elapsedMs<0) errors.push("elapsedMs");
  if(!exact(r.coherence,["from","to","changed"])) errors.push("coherence fields");
  else {
    if(!["coherent","degraded"].includes(r.coherence.from)||!["coherent","degraded"].includes(r.coherence.to)) errors.push("coherence value");
    if(r.coherence.changed!==(r.coherence.from!==r.coherence.to)) errors.push("coherence derivation");
  }
  if(!Array.isArray(r.componentChanges)||r.componentChanges.length!==COMPONENT_IDS.length) errors.push("componentChanges");
  else {
    r.componentChanges.forEach((c,i)=>{
      if(!exact(c,COMPONENT_KEYS)||c.id!==COMPONENT_IDS[i]||!["available","unavailable"].includes(c.fromAvailability)||!["available","unavailable"].includes(c.toAvailability)||typeof c.availabilityChanged!=="boolean"||!sha(c.fromDigest)||!sha(c.toDigest)||typeof c.digestChanged!=="boolean") errors.push("component row "+COMPONENT_IDS[i]);
      else {
        if(c.availabilityChanged!==(c.fromAvailability!==c.toAvailability)) errors.push("component availability derivation "+c.id);
        if(c.digestChanged!==(c.fromDigest!==c.toDigest)) errors.push("component digest derivation "+c.id);
      }
    });
    const changed=r.componentChanges.filter(c=>c.availabilityChanged||c.digestChanged).length;
    if(r.changedComponentCount!==changed) errors.push("changedComponentCount");
  }
  if(!nni(r.changedSummaryMetricCount)||!Array.isArray(r.summaryChanges)||r.summaryChanges.length!==r.changedSummaryMetricCount||r.summaryChanges.length>SUMMARY_METRICS.length) errors.push("summaryChanges");
  else {
    const seen=new Set();
    let previousIndex=-1;
    for(const c of r.summaryChanges){
      const metricIndex=SUMMARY_METRICS.indexOf(c.metric);
      if(!exact(c,SUMMARY_CHANGE_KEYS)||metricIndex<0||seen.has(c.metric)||metricIndex<=previousIndex||!num(c.from)||!num(c.to)||!num(c.delta)||c.delta!==c.to-c.from){errors.push("summary change row");break}
      seen.add(c.metric); previousIndex=metricIndex;
    }
  }
  const expectedElapsed=Math.max(0,Date.parse(r.toComposedAt)-Date.parse(r.fromComposedAt));
  if(num(r.elapsedMs)&&r.elapsedMs!==expectedElapsed) errors.push("elapsed derivation");
  if(!nni(r.changedComponentCount)||r.changedComponentCount>5) errors.push("changedComponentCount range");
  if(r.causeAssigned!==false||r.severityAssigned!==false) errors.push("interpretation assignment");
  if(r.readOnly!==true||r.executionAuthority!==false||r.effectPerformed!==false) errors.push("authority");
  if(sha(r.changeDigest)&&r.changeDigest!==recomputeSystemChangeDigest(r)) errors.push("change digest mismatch");
  return {ok:errors.length===0,errors};
}
export function assertValidSystemChangeReceipt(r){const v=validateSystemChangeReceipt(r);if(!v.ok) throw new Error("invalid system change receipt: "+v.errors.join("; "));return r}
