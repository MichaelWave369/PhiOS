import {describe,expect,it} from "vitest";
import {PhiPoseNavigationHost,PHIPOSE_NAV_PROTOCOL} from "./phiPoseNavigationHost";

const source={} as Window;
const now=1_000_000;
const sessionId="test-gesture-session-000001";
const intent=(actionId="phios.view.research",sequence=1,src="webxr")=>({
  schema:"overstrings.phipose.intent.v0.1",version:1,
  advisory:true,action_authority:false,execution_authority:false,
  program:"L:open > R:pinch",source:src,action_id:actionId,sequence,timestamp_ms:125
});
const message=(payload:unknown=undefined,src:MessageEventSource=source,origin="https://example.test")=>({
  source:src,origin,
  data:payload??{protocol:PHIPOSE_NAV_PROTOCOL,type:"command",
    session_id:sessionId,sent_at:now,intent:intent()}
});
const make=(allowSyntheticDemo=false)=>{
  const host=new PhiPoseNavigationHost();
  host.enable({source,origin:"https://example.test",sessionId,
    expiresAt:now+60_000,allowSyntheticDemo},now);
  return host;
};
describe("PhiPose safe PhiShell navigation host",()=>{
  it("starts disabled and requires an explicitly bounded operator session",()=>{
    const h=new PhiPoseNavigationHost();
    expect(h.accept(message(),now)).toEqual({accepted:false,reason:"disabled"});
    expect(()=>h.enable({source,origin:"https://example.test",sessionId,
      expiresAt:now+600_000,allowSyntheticDemo:false},now)).toThrow();
    expect(h.active).toBe(false);
  });
  it("accepts only a verified scoped and fresh safe UI event",()=>{
    const h=make();
    const result=h.accept(message(),now);
    expect(result.accepted).toBe(true);
    if(result.accepted){
      expect(result.event).toEqual({type:"SET_VIEW",view:"research"});
      expect(result.actionId).toBe("phios.view.research");
    }
    expect(h.accept(message(),now+1200)).toEqual({accepted:false,reason:"invalid_envelope"});
  });
  it("maps command palette but never allows an arbitrary app or OS execution",()=>{
    const h=make();
    const shell=h.accept(message({protocol:PHIPOSE_NAV_PROTOCOL,type:"command",session_id:sessionId,
      sent_at:now,intent:intent("phios.command.open")}),now);
    expect(shell.accepted).toBe(true);
    if(shell.accepted)expect(shell.event).toEqual({type:"OPEN_COMMAND"});
    const blocked=make().accept(message({protocol:PHIPOSE_NAV_PROTOCOL,type:"command",session_id:sessionId,
      sent_at:now,intent:intent("phios.execute.shell")}),now);
    expect(blocked).toEqual({accepted:false,reason:"invalid_intent"});
  });
  it("requires exact opener source and origin independently",()=>{
    const h=make();
    expect(h.accept(message(undefined,{} as Window),now).reason).toBe("untrusted_source");
    expect(h.accept(message(undefined,source,"https://evil.example"),now).reason).toBe("untrusted_source");
    expect(h.accept(message(),now).accepted).toBe(true);
  });
  it("denies wrong sessions, stale messages, forged power and dynamic scripts",()=>{
    const h=make();
    const base={protocol:PHIPOSE_NAV_PROTOCOL,type:"command",session_id:sessionId,sent_at:now};
    for(const v of [
      {...base,session_id:"different",intent:intent()},
      {...base,sent_at:now-3000,intent:intent()},
      {...base,sent_at:now+300,intent:intent()},
      {...base,intent:{...intent(),action_authority:true}},
      {...base,intent:{...intent(),execution_authority:true}},
      {...base,intent:{...intent(),program:"L:open > R:pinch; alert(1)"}},
      {...base,intent:{...intent(),action_id:"constructor"}},
      {...base,intent:{...intent(),sequence:0}},
    ])expect(h.accept(message(v),now).accepted).toBe(false);
    expect(h.accept(message(),now).accepted).toBe(true);
  });
  it("tracks bounded session expiry and revocation",()=>{
    const h=make();
    expect(h.accept(message(),now+60_001).reason).toBe("expired");
    expect(h.active).toBe(false);
    h.enable({source,origin:"https://example.test",sessionId,
      expiresAt:now+60_000,allowSyntheticDemo:false},now);
    h.revoke();
    expect(h.accept(message(),now).reason).toBe("disabled");
  });
  it("denies synthetic tokens without host sandbox consent",()=>{
    const p={protocol:PHIPOSE_NAV_PROTOCOL,type:"command",session_id:sessionId,sent_at:now,
      intent:intent("phios.view.home",1,"synthetic")};
    expect(make().accept(message(p),now).reason).toBe("invalid_intent");
    const ok=make(true).accept(message(p),now);
    expect(ok.accepted).toBe(true);
  });
  it("rejects duplicate/reordered events and rapid repeat attempts",()=>{
    const h=make();
    expect(h.accept(message(),now).accepted).toBe(true);
    const second={protocol:PHIPOSE_NAV_PROTOCOL,type:"command",session_id:sessionId,sent_at:now+150,
      intent:intent("phios.view.build",2)};
    expect(h.accept(message(second),now+150).reason).toBe("cooldown");
    second.sent_at=now+1200;
    expect(h.accept(message(second),now+1200).accepted).toBe(true);
    const duplicate={...second,sent_at:now+1400};
    expect(h.accept(message(duplicate),now+1400).reason).toBe("replay");
  });
});
