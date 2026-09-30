import {describe,expect,it} from "vitest";
import {FIXTURE_PACKAGE_OBSERVATION,createPackageObservationProvider,isPackageTransportEnvelope} from "./packageObservation";
function live(){return {...FIXTURE_PACKAGE_OBSERVATION,source:"dpkg-status-file" as const,capturedAt:new Date().toISOString(),availability:"available" as const,reason:null,distro:{id:"ubuntu",name:"Ubuntu"},totalInstalledPackageCount:1,packages:[{name:"base-files",version:"1.0",architecture:"amd64",essential:true}]}}
function envelope(age=1){return {transportSchemaVersion:"phios.package-transport.v1",transport:"loopback-http",transportIdentity:"phishell-local-observer",localOnly:true,readOnly:true,executionAuthority:false,effectPerformed:false,servedAt:new Date().toISOString(),snapshotAgeMs:age,observation:live()}}
describe("package observation transport",()=>{
  it("accepts native Arch inventory and rejects a mismatched adapter",async()=>{
    const payload={...envelope(),observation:{...live(),source:"pacman-local-desc",adapter:"arch-pacman-local",distro:{id:"phios",name:"PhiOS"}}};
    const p=createPackageObservationProvider({fetcher:async()=>new Response(JSON.stringify(payload),{status:200})});
    expect((await p.observe()).source).toBe("pacman-local-desc");
    expect(isPackageTransportEnvelope({...payload,observation:{...payload.observation,adapter:"debian-dpkg-status"}})).toBe(false);
  });
  it("accepts fresh bounded package metadata",async()=>{const p=createPackageObservationProvider({fetcher:async()=>new Response(JSON.stringify(envelope()),{status:200})});const o=await p.observe();expect(o.source).toBe("dpkg-status-file");expect(o.packages[0].essential).toBe(true);expect(o.executionAuthority).toBe(false)});
  it("rejects package descriptions smuggled into rows",async()=>{const u=JSON.parse(JSON.stringify(envelope())) as {observation:{packages:Array<Record<string,unknown>>}};u.observation.packages[0].description="secretly too much";const p=createPackageObservationProvider({fetcher:async()=>new Response(JSON.stringify(u),{status:200})});expect((await p.observe()).source).toBe("fixture")});
  it("rejects stale or authority-bearing envelopes",()=>{expect(isPackageTransportEnvelope(envelope(60000))).toBe(false);expect(isPackageTransportEnvelope({...envelope(),executionAuthority:true})).toBe(false)});
});
