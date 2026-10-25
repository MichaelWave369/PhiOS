import test from "node:test";
import assert from "node:assert/strict";
import { createLocalObservationServer } from "./localTransport.mjs";

function fixture() {
  return {
    schemaVersion: "phios.porch_health_preflight.v0.1",
    endpoint: "127.0.0.1:7331/health",
    outcome: "CANDIDATE_RESPONSE_OBSERVED",
    protocolVersion: 1,
    candidateVersion: "0.1.2",
    origin: "UNAUTHENTICATED_LOCAL_HEALTH",
    identityVerified: false,
    authenticationPerformed: false,
    modelExecutionAuthorized: false,
    peerAuthority: false,
    operationalAuthority: false,
    actionAuthority: false,
    executionAuthority: false,
    effectPerformed: false,
  };
}

test("manual same-origin preflight serves only sanitized read-only health result", async () => {
  let calls = 0;
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    porchHealthProber: async () => { calls++; return fixture(); },
  });
  const address = await transport.listen();
  try {
    const base = `http://127.0.0.1:${address.port}`;
    const r = await fetch(base + "/api/v1/porch-health-preflight", {
      headers: { "x-phios-porch-preflight": "1" },
    });
    assert.equal(r.status, 200);
    assert.equal(r.headers.get("access-control-allow-origin"), null);
    assert.equal(r.headers.get("cache-control"), "no-store");
    const body = await r.json();
    assert.deepEqual(body, fixture());
    assert.equal(calls, 1);
  } finally {
    await transport.close();
  }
});

test("requests without operator action header or with hostile origin, query or method refuse", async () => {
  let calls = 0;
  const transport = createLocalObservationServer({
    port: 0,
    serveShell: false,
    porchHealthProber: async () => { calls++; return fixture(); },
  });
  const address = await transport.listen();
  try {
    const base = `http://127.0.0.1:${address.port}/api/v1/porch-health-preflight`;
    const missing = await fetch(base);
    assert.equal(missing.status, 403);
    const origin = await fetch(base, {
      headers: { "x-phios-porch-preflight": "1", origin: "https://attacker.example" },
    });
    assert.equal(origin.status, 403);
    const site = await fetch(base, {
      headers: { "x-phios-porch-preflight": "1", "sec-fetch-site": "cross-site" },
    });
    assert.equal(site.status, 403);
    const query = await fetch(base + "?target=http://example.com", {
      headers: { "x-phios-porch-preflight": "1" },
    });
    assert.equal(query.status, 403);
    const post = await fetch(base, {
      method: "POST",
      headers: { "x-phios-porch-preflight": "1" },
    });
    assert.equal(post.status, 405);
    assert.equal(calls, 0);
  } finally {
    await transport.close();
  }
});
