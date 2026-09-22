import { describe, expect, it } from "vitest";
import {
  EMPTY_SYSTEM_STATE_HISTORY,
  SYSTEM_HISTORY_LIMIT,
  appendSystemStateHistory,
  deriveSystemChangeReceipt,
} from "./systemHistory";
import type { SystemStateReceipt } from "./systemState";

function state(seed: number): SystemStateReceipt {
  const now = new Date(1_800_000_000_000 + seed * 1000).toISOString();
  const componentIds = ["host","services","processes","packages","devices"] as const;
  const sources = [
    "linux-readonly-node-probe","systemd-dbus-list-units","procfs-current-user",
    "dpkg-status-file","linux-sysfs-bounded",
  ];
  return {
    schemaVersion:"phios.system-state.v1",
    source:"phios-system-state-composer",
    composedAt:now,
    captureWindowStart:now,
    captureWindowEnd:now,
    captureSkewMs:0,
    maxCoherentSkewMs:5000,
    coherence:"coherent",
    componentCount:5,
    availableComponentCount:5,
    readOnly:true,
    executionAuthority:false,
    effectPerformed:false,
    components:componentIds.map((id,index)=>({
      id,
      schemaVersion:["phios.host-observation.v1","phios.service-observation.v1","phios.process-observation.v1","phios.package-observation.v1","phios.device-observation.v1"][index],
      source:sources[index],
      capturedAt:now,
      availability:"available" as const,
      digest:"sha256:"+String(index+seed).padStart(64,"a").slice(-64),
      readOnly:true,
      executionAuthority:false,
      effectPerformed:false,
    })),
    summary:{
      cpuLogicalCores:8,
      memoryTotalBytes:32,
      rootStorageTotalBytes:100,
      observedServiceCount:4,
      activeServiceCount:3,
      currentUserProcessCount:10+seed,
      installedPackageCount:500,
      blockDeviceCount:2,
      networkDeviceCount:2,
      pciDeviceCount:8,
      usbDeviceCount:3,
      drmDeviceCount:1,
      powerDeviceCount:0,
    },
    composeDurationMs:10,
    receiptDigest:"sha256:"+String(seed).padStart(64,"b").slice(-64),
  };
}

describe("system observation history",()=>{
  it("derives descriptive change without cause or severity",async()=>{
    const first=state(1);
    const second=state(2);
    second.summary.installedPackageCount=501;
    const change=await deriveSystemChangeReceipt(first,second,1);
    expect(change.changedSummaryMetricCount).toBe(2);
    expect(change.summaryChanges.map(x=>x.metric)).toEqual([
      "currentUserProcessCount",
      "installedPackageCount",
    ]);
    expect(change.causeAssigned).toBe(false);
    expect(change.severityAssigned).toBe(false);
    expect(change.executionAuthority).toBe(false);
    expect(change.effectPerformed).toBe(false);
    expect(change.changeDigest).toMatch(/^sha256:[0-9a-f]{64}$/);
  });

  it("keeps at most sixteen session receipts",async()=>{
    let history=EMPTY_SYSTEM_STATE_HISTORY;
    for(let i=1;i<=20;i+=1) history=await appendSystemStateHistory(history,state(i));
    expect(history.receipts).toHaveLength(SYSTEM_HISTORY_LIMIT);
    expect(history.changes).toHaveLength(SYSTEM_HISTORY_LIMIT-1);
    expect(history.receipts[0].composedAt).toBe(state(5).composedAt);
    expect(history.changes.at(-1)?.sequence).toBe(19);
  });

  it("does not persist history outside supplied session state",()=>{
    expect(EMPTY_SYSTEM_STATE_HISTORY.receipts).toEqual([]);
    expect(EMPTY_SYSTEM_STATE_HISTORY.changes).toEqual([]);
  });
});
