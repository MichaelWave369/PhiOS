import test from "node:test";
import assert from "node:assert/strict";
import {networkPolicy,reviewedAction} from "../scripts/cold_restart_web_smoke.mjs";

test("only bounded browser-local Vessie/ThinkTank actions",()=>{
  assert.equal(reviewedAction("vessie-web"),"atlas-filter");
  assert.equal(reviewedAction("thinktank-web"),"audit-mode");
  for(const key of ["../../etc","unknown","other"])assert.throws(
    ()=>reviewedAction(key),/UNREVIEWED_APP/);
});

test("only static app origin is served; local health probes are denied",()=>{
  const base="http://127.0.0.1:55557";
  assert.equal(networkPolicy(base+"/assets/app.js",base),"static");
  assert.equal(networkPolicy(base+"/",base),"static");
  assert.equal(networkPolicy("http://127.0.0.1:3691/providers/status",base),
    "denied-local-health");
  assert.equal(networkPolicy("http://127.0.0.1:3691/models/run",base),"denied-other");
  assert.equal(networkPolicy("http://127.0.0.1:3691/providers/status",base,"POST"),
    "denied-other");
  assert.equal(networkPolicy("http://localhost:55557/",base),"denied-other");
  assert.equal(networkPolicy("https://example.net/",base),"denied-other");
});
