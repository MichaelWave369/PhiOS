import assert from "node:assert/strict";
import { createLocalObservationServer } from "./localTransport.mjs";

if (process.platform !== "linux") {
  process.exit(0);
}

const transport = createLocalObservationServer({ port: 0 });
const address = await transport.listen();
const base = `http://127.0.0.1:${address.port}`;

try {
  const shell = await fetch(`${base}/`);
  assert.equal(shell.status, 200);
  assert.match(shell.headers.get("content-type") ?? "", /text\/html/);
  const html = await shell.text();
  assert.match(html, /<div id="root"><\/div>/);

  const observation = await fetch(`${base}/api/v1/host-observation`);
  assert.equal(observation.status, 200);
  assert.equal(observation.headers.get("access-control-allow-origin"), null);

  const envelope = await observation.json();
  assert.equal(envelope.transportSchemaVersion, "phios.host-transport.v1");
  assert.equal(envelope.transportIdentity, "phishell-local-observer");
  assert.equal(envelope.localOnly, true);
  assert.equal(envelope.readOnly, true);
  assert.equal(envelope.executionAuthority, false);
  assert.equal(envelope.effectPerformed, false);
  assert.equal(envelope.snapshot.source, "linux-readonly-node-probe");

  const mutation = await fetch(`${base}/api/v1/host-observation`, { method: "POST" });
  assert.equal(mutation.status, 405);
} finally {
  await transport.close();
}
