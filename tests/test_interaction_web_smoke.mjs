import test from "node:test";
import assert from "node:assert/strict";
import {plan,REVIEWED_INTERACTIONS,allowedProbe} from "../scripts/interaction_web_smoke.mjs";

test("only Vessie and ThinkTank have reviewed, safe browser sequences",()=>{
  assert.deepEqual(plan("vessie-web"),[
    "atlas-navigation","atlas-filter","receipt-invalid-local","local-http-reload"]);
  assert.deepEqual(plan("thinktank-web"),["audit-mode-local","local-http-reload"]);
  for(const key of ["unknown","../../evil","think-tank"])assert.throws(()=>plan(key),/UNREVIEWED_APP/);
  assert.equal(Object.keys(REVIEWED_INTERACTIONS).length,2);
});
test("health status remains a blocked probe, never executable authority",()=>{
  const origin="http://127.0.0.1:51234";
  assert.equal(allowedProbe("http://127.0.0.1:3691/providers/status",origin),true);
  assert.equal(allowedProbe("http://127.0.0.1:3691/providers/status",origin,"POST"),false);
  assert.equal(allowedProbe("http://127.0.0.1:3691/models/run",origin),false);
  assert.equal(allowedProbe("https://somewhere.invalid/api",origin),false);
  assert.equal(allowedProbe(origin+"/index.html",origin),false);
});
